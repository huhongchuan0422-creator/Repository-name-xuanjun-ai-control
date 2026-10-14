"""Loopback-only demo order API. Simulation token is NOT authentication.
No real payments, site publishing, secrets or external network binding.
"""
import json
import re
import socket
import time
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from scripts.community_order_store import connect, DDL, create_order, state, simulated_transition
from scripts.community_merchant_contract import scope
from scripts.community_storefront_snapshot import storefront_snapshot
from scripts.community_ad_contract import AMOUNT, SUCCESS
from scripts.community_ad_store import list_campaigns
from scripts.community_refund_preview_store import preview_total, open_refund_store

MAX_BODY = 2048
READ_TIMEOUT_SECONDS = 1.0
FIELDS = {"tenant_id", "merchant_id", "store_id", "reference"}
ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")

def _object(raw, expected):
    if type(raw) is not dict or set(raw) != expected:
        raise ValueError("INVALID_REQUEST")
    return raw

def _id(value):
    if type(value) is not str or not ID.fullmatch(value):
        raise ValueError("INVALID_ID")
    return value

class DemoService:
    """Trusted local demo service. This is not a production access boundary."""
    def __init__(self, db, merchant_db=None, ad_db=None, now=None, refund_db=None):
        self.db = db
        self.merchant_db = merchant_db
        self.ad_db = ad_db
        self.now = now
        self.refund_db = refund_db
    def dispatch(self, method, path, data):
        if type(data) is not dict:
            raise ValueError("INVALID_REQUEST")
        if method == "POST" and path == "/demo/ads/list":
            _object(data, {"tenant_id","merchant_id","store_id"})
            identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
            scope(identity)
            if self.ad_db is None:
                raise ValueError("AD_STORE_UNAVAILABLE")
            listed=list_campaigns(self.ad_db,identity,limit=50)
            return {"campaigns":listed["campaigns"],"has_more":listed["has_more"],
                    "simulation_only":True,"write_permissions":False}
        if method == "POST" and path == "/demo/refunds/preview":
            _object(data, FIELDS)
            identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
            scope(identity)
            reference=_id(data["reference"])
            order_state=state(self.db,identity,reference)
            if self.refund_db is None:
                raise ValueError("REFUND_PREVIEW_NOT_CONFIGURED")
            total=preview_total(self.refund_db,identity,reference)
            amount=order_state["amount_minor"]
            if type(total) is not int or total<0 or total>amount:
                raise ValueError("INVALID_REFUND_PREVIEW_TOTAL")
            return {"reference":reference,"order_state":order_state["state"],
                    "order_amount_minor":amount,"preview_total_minor":total,
                    "remaining_preview_minor":amount-total,
                    "provider_refund_executed":False,
                    "provider_settlement_verified":False,
                    "simulation_only":True,
                    "financial_receipt_issued":False}
        if method == "POST" and path == "/demo/orders/summary":
            _object(data, {"tenant_id","merchant_id","store_id"})
            identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
            t,m,st=scope(identity)
            rows=self.db.execute(
                "SELECT state,COUNT(*),COALESCE(SUM(amount_minor),0) FROM orders "
                "WHERE tenant_id=? AND merchant_id=? AND store_id=? GROUP BY state",
                (t,m,st)).fetchall()
            counts={name:0 for name in ("PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED")}
            total=0
            for name,count,amount in rows:
                counts[name]=count
                total+=amount
            return {"counts":counts,"order_total_minor":total,
                    "simulation_only":True,"provider_settlement_verified":False,
                    "real_revenue_minor":None}
        if method == "POST" and path == "/demo/orders/list":
            _object(data, {"tenant_id","merchant_id","store_id"})
            identity={k:data[k] for k in ("tenant_id","merchant_id","store_id")}
            t,m,st=scope(identity)
            rows=self.db.execute(
                "SELECT reference,amount_minor,currency,state FROM orders "
                "WHERE tenant_id=? AND merchant_id=? AND store_id=? "
                "ORDER BY reference LIMIT 50",(t,m,st)).fetchall()
            return {"orders":[{"reference":ref,"amount_minor":amount,"currency":currency,
                               "state":state_name} for ref,amount,currency,state_name in rows],
                    "simulation_only":True,"provider_settlement_verified":False}
        if method == "POST" and path == "/demo/storefront":
            _object(data, {"tenant_id", "merchant_id", "store_id"})
            identity = {k: data[k] for k in ("tenant_id","merchant_id","store_id")}
            scope(identity)
            if self.merchant_db is None or type(self.now) is not int:
                raise ValueError("STOREFRONT_NOT_CONFIGURED")
            snapshot = storefront_snapshot(self.merchant_db, self.ad_db, identity, self.now)
            # Never release success-placement candidates from simulated data.
            return {"merchant":snapshot["merchant"],"products":snapshot["products"],
                    "ads":{AMOUNT:snapshot["ads"][AMOUNT],SUCCESS:None},
                    "simulation_only":True,"provider_settlement_verified":False,
                    "escape_text_required":True}
        if method == "POST" and path == "/demo/orders":
            _object(data, FIELDS | {"amount_minor"})
            identity = {k: data[k] for k in ("tenant_id","merchant_id","store_id")}
            scope(identity)
            _id(data["reference"])
            return create_order(self.db, identity, data["reference"], data["amount_minor"])
        if method == "POST" and path == "/demo/orders/state":
            _object(data, FIELDS)
            identity = {k: data[k] for k in ("tenant_id","merchant_id","store_id")}
            scope(identity)
            return state(self.db, identity, _id(data["reference"]))
        if method == "POST" and path == "/demo/orders/simulate":
            _object(data, FIELDS | {"event_id","target","transaction_id","amount_minor"})
            identity = {k: data[k] for k in ("tenant_id","merchant_id","store_id")}
            scope(identity)
            evidence = {"simulation_only":True,"scope":identity,"reference":data["reference"],
                        "amount_minor":data["amount_minor"],"provider_transaction_id":data["transaction_id"]}
            return simulated_transition(self.db,identity,_id(data["reference"]),_id(data["event_id"]),
                                        data["target"],evidence)
        raise ValueError("UNKNOWN_ENDPOINT")

class _HeaderDeadlineReader:
    """Unbuffered deadline-aware request-line/header reader.

    Socket recv() per byte avoids a buffered readline silently extending an
    absolute header deadline when a peer drip-feeds one character at a time.
    Once headers finish, read1() reads the body with its separate fixed deadline.
    """
    def __init__(self, connection):
        self.connection = connection
        self.header_deadline = time.monotonic() + READ_TIMEOUT_SECONDS

    def readline(self, limit=-1):
        data = bytearray()
        while limit < 0 or len(data) < limit:
            remaining = self.header_deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("HEADER_DEADLINE_EXPIRED")
            self.connection.settimeout(remaining)
            byte = self.connection.recv(1)
            if not byte:
                break
            data.extend(byte)
            if byte == b"\n":
                break
        return bytes(data)

    def read1(self, length):
        return self.connection.recv(length)

    def close(self):
        pass


def handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Stage5OfflineDemo"
        sys_version = ""
        def setup(self):
            super().setup()
            self.rfile.close()
            self.rfile = _HeaderDeadlineReader(self.connection)
        def log_message(self, fmt, *args):
            pass
        def do_POST(self):
            # Reject DNS-rebinding hostnames and cross-origin browser requests.
            address = self.headers.get("Host", "")
            expected_host = "127.0.0.1:" + str(self.server.server_address[1])
            if address != expected_host:
                return self.send_json(403, {"error":"LOOPBACK_ONLY"})
            origin = self.headers.get("Origin")
            if origin is not None and origin != "http://" + expected_host:
                return self.send_json(403, {"error":"ORIGIN_DENIED"})
            if urlsplit(self.path).query or self.path not in (
                "/demo/orders","/demo/orders/state","/demo/orders/simulate","/demo/storefront","/demo/orders/list","/demo/ads/list","/demo/orders/summary","/demo/refunds/preview"):
                return self.send_json(404, {"error":"NOT_FOUND"})
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self.send_json(415, {"error":"JSON_REQUIRED"})
            try:
                length = int(self.headers.get("Content-Length","-1"))
                if length < 1 or length > MAX_BODY:
                    raise ValueError("INVALID_BODY_SIZE")
                deadline = time.monotonic() + READ_TIMEOUT_SECONDS
                chunks = []
                remaining = length
                while remaining:
                    budget = deadline - time.monotonic()
                    if budget <= 0:
                        raise socket.timeout("BODY_DEADLINE_EXPIRED")
                    self.connection.settimeout(budget)
                    part = self.rfile.read1(min(remaining, 4096))
                    if not part:
                        raise ValueError("INCOMPLETE_BODY")
                    chunks.append(part)
                    remaining -= len(part)
                raw = b"".join(chunks).decode("utf-8")
                def unique_pairs(pairs):
                    values = {}
                    for key,value in pairs:
                        if key in values:
                            raise ValueError("DUPLICATE_KEY")
                        values[key] = value
                    return values
                data = json.loads(raw,object_pairs_hook=unique_pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))
                result = service.dispatch("POST",self.path,data)
                return self.send_json(200,result)
            except (socket.timeout, TimeoutError):
                self.close_connection = True
                return self.send_json(408,{"error":"BODY_TIMEOUT"})
            except (ValueError,KeyError,TypeError):
                self.close_connection = True
                return self.send_json(400,{"error":"INVALID_DEMO_REQUEST"})
            except Exception:
                return self.send_json(503,{"error":"DEMO_UNAVAILABLE"})
        def do_GET(self):
            expected_host = "127.0.0.1:" + str(self.server.server_address[1])
            if self.headers.get("Host", "") != expected_host:
                return self.send_json(403,{"error":"LOOPBACK_ONLY"})
            files={"/demo/":"index.html","/demo/app.js":"app.js","/demo/merchant/":"merchant.html","/demo/merchant/app.js":"merchant.js","/demo/platform/":"platform.html","/demo/platform/app.js":"platform.js","/demo/catalog-read.js":"catalog-read.js","/demo/order-list.js":"order-list.js","/demo/business-overview.js":"business-overview.js"}
            filename=files.get(self.path)
            if filename is None:
                return self.send_json(404,{"error":"NOT_FOUND"})
            data=(Path(__file__).resolve().parent.parent/"demos"/"community-local-e2e"/filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/javascript; charset=utf-8" if filename.endswith(".js") else "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy","default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers();self.wfile.write(data)
        def send_json(self,status,obj):
            payload=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return Handler

def server_database(path):
    """One connection, used by the strictly serial demo HTTP server only."""
    if path == ":memory:":
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.executescript(DDL)
        db.execute("PRAGMA user_version=1")
        return db
    checked = connect(path)
    checked.close()
    return sqlite3.connect(path, check_same_thread=False)

def _close_all_owned(connections):
    """Attempt every owned close; preserve first error for caller."""
    first = None
    for connection in connections:
        try:
            connection.close()
        except Exception as exc:
            if first is None:
                first = exc
    if first is not None:
        raise first

class _OwnedLocalDemoHTTPServer(HTTPServer):
    def __init__(self, address, service, owned_connections):
        self._owned_connections = owned_connections
        super().__init__(address, handler(service))
    def server_close(self):
        base_error = None
        try:
            super().server_close()
        except Exception as exc:
            base_error = exc
        connections, self._owned_connections = self._owned_connections, ()
        try:
            _close_all_owned(connections)
        except Exception:
            if base_error is None:
                raise
        if base_error is not None:
            raise base_error

def serve_local(path=":memory:",port=18791,seed_demo=True):
    """Loopback-only local fixture; never real merchant auth or provider receipt.

    seed_demo=True loads a fresh ephemeral non-customer fixture; no environment
    credentials, network payments, production DBs or user-supplied actors.
    seed_demo=False retains the original fail-closed storefront behavior.
    """
    if type(port) is not int or not (port == 0 or 1024 <= port <= 65535):
        raise ValueError("INVALID_PORT")
    if type(seed_demo) is not bool:
        raise ValueError("INVALID_DEMO_SEED")
    db = server_database(path)
    owned = [db]
    try:
        merchant_db = ad_db = now = None
        refund_db = open_refund_store()
        owned.append(refund_db)
        if seed_demo:
            from scripts.community_demo_bootstrap import fixture_stores
            merchant_db, ad_db, now = fixture_stores()
            owned.extend((merchant_db, ad_db))
        # HTTPServer handles requests serially; no thread pool shares the stores.
        return _OwnedLocalDemoHTTPServer(
            ("127.0.0.1",port),DemoService(db,merchant_db,ad_db,now,refund_db),owned)
    except BaseException:
        try:
            _close_all_owned(owned)
        except Exception:
            pass  # never replace original startup failure
        raise

if __name__=="__main__":
    print("OFFLINE_SIMULATION_ONLY_NO_REAL_WECHAT")
    serve_local().serve_forever()
