"""Loopback-only demo order API. Simulation token is NOT authentication.
No real payments, site publishing, secrets or external network binding.
"""
import json
import re
import socket
import time
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from scripts.community_order_store import connect, DDL, create_order, state, simulated_transition
from scripts.community_merchant_contract import scope

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
    def __init__(self, db):
        self.db = db
    def dispatch(self, method, path, data):
        if type(data) is not dict:
            raise ValueError("INVALID_REQUEST")
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
                "/demo/orders","/demo/orders/state","/demo/orders/simulate"):
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
            return self.send_json(405,{"error":"POST_ONLY"})
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

def serve_local(path=":memory:",port=18791):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("INVALID_PORT")
    db = server_database(path)
    # HTTPServer handles requests serially; no thread pool shares this connection.
    return HTTPServer(("127.0.0.1",port),handler(DemoService(db)))

if __name__=="__main__":
    print("OFFLINE_SIMULATION_ONLY_NO_REAL_WECHAT")
    serve_local().serve_forever()
