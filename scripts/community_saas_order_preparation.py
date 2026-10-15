"""Offline SaaS quote-to-order preparation, not a payment processor.

A prepared order cannot activate entitlements or represent confirmed payment.
External authoritative finance confirmation must be integrated in a later stage.
"""
import json
import hashlib
import sqlite3
from scripts.community_merchant_contract import valid_id
from scripts.community_saas_offer_catalog import read_quote

SCHEMA = """
CREATE TABLE IF NOT EXISTS saas_order_preparations(
 order_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
 quote_id TEXT NOT NULL, currency TEXT NOT NULL CHECK(currency IN ('CNY','USD')),
 created_at INTEGER NOT NULL, snapshot TEXT NOT NULL,
 UNIQUE(tenant_id,quote_id,currency));
CREATE TRIGGER IF NOT EXISTS saas_order_prep_immutable_update
BEFORE UPDATE ON saas_order_preparations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_ORDER_PREPARATION'); END;
CREATE TRIGGER IF NOT EXISTS saas_order_prep_immutable_delete
BEFORE DELETE ON saas_order_preparations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_ORDER_PREPARATION'); END;
"""
def install(db):
    if not isinstance(db,sqlite3.Connection):
        raise TypeError("SQLITE_CONNECTION_REQUIRED")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)

def _identifier(v):
    if type(v) is not str or not valid_id(v):
        raise ValueError("INVALID_IDENTIFIER")
    return v

def prepare(db,quote_db,order_id,tenant_id,quote_id,currency,now):
    _identifier(order_id);_identifier(tenant_id);_identifier(quote_id)
    if currency not in ("CNY","USD") or type(now) is not int or now<0:
        raise ValueError("INVALID_ORDER_CONTEXT")
    q=read_quote(quote_db,quote_id,tenant_id)
    if not q["created_at"]<=now<q["expires_at"]:
        raise ValueError("QUOTE_EXPIRED_OR_NOT_YET_VALID")
    if q["kind"] in ("METERED","CUSTOM"):
        # Real usage/contract authorization cannot be guessed from a preview.
        raise ValueError("MANUAL_CONTRACT_OR_USAGE_REQUIRED")
    if q["supplier_payment"]=="CUSTOMER":
        # No claim that third-party costs have been settled on behalf of customer.
        pass
    key=currency.lower()+"_minor"
    breakdown=q.get("totals_by_cycle",{})
    if not breakdown or any(group.get(key) is None for group in breakdown.values()):
        raise ValueError("UNKNOWN_QUOTE_AMOUNT")
    totals={cycle:group[key] for cycle,group in breakdown.items()}
    if any(type(v) is not int or v<0 for v in totals.values()):
        raise ValueError("INVALID_QUOTE_AMOUNT")
    quote_canonical=json.dumps(q,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    quote_sha256=hashlib.sha256(quote_canonical.encode("utf-8")).hexdigest()
    snapshot={"quote_sha256":quote_sha256,"quote_snapshot":q,"order_id":order_id,"tenant_id":tenant_id,"quote_id":quote_id,
              "module_id":q["module_id"],"offer_id":q["offer_id"],
              "offer_version":q["version"],"currency":currency,
              "created_at":now,"amounts_by_cycle_minor":totals,
              "state":"PREPARED_ONLY","payment_confirmed":False,
              "entitlement_granted":False,"procurement_authorized":False,
              "automatic_renewal_authorized":False}
    serialized=json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    with db:
        old=db.execute("SELECT snapshot FROM saas_order_preparations WHERE order_id=?",(order_id,)).fetchone()
        if old:
            if old[0]!=serialized:
                raise ValueError("ORDER_IDEMPOTENCY_CONFLICT")
            return json.loads(old[0])
        prior=db.execute("SELECT order_id FROM saas_order_preparations WHERE tenant_id=? AND quote_id=? AND currency=?",
                         (tenant_id,quote_id,currency)).fetchone()
        if prior:
            raise ValueError("DUPLICATE_QUOTE_ORDER")
        db.execute("INSERT INTO saas_order_preparations VALUES(?,?,?,?,?,?)",
                   (order_id,tenant_id,quote_id,currency,now,serialized))
    return snapshot

def read(db,order_id,tenant_id):
    _identifier(order_id);_identifier(tenant_id)
    row=db.execute("SELECT snapshot FROM saas_order_preparations WHERE order_id=? AND tenant_id=?",
                   (order_id,tenant_id)).fetchone()
    if not row:
        raise ValueError("ORDER_NOT_FOUND")
    return json.loads(row[0])
