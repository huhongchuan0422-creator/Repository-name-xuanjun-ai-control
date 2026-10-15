"""Stage5 offline commercial handoff: verification proposals, never payment settlement.

Reuses immutable SaaS order snapshots and the authoritative order lifecycle.
All output is read-only workflow intent. This module is not a payment gateway.
"""
import hashlib
import hmac
import json
import sqlite3
from scripts.community_merchant_contract import valid_id
from scripts.community_saas_order_preparation import read, status, quote_provenance

def _ident(v):
    if type(v) is not str or not valid_id(v):
        raise ValueError("INVALID_ID")
    return v

def _timestamp(v):
    if type(v) is not int or v < 0:
        raise ValueError("INVALID_TIME")
    return v

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")

def plan_finance_claim(db, order_id, tenant_id):
    """Return the exact items an external Finance verifier must attest to."""
    quote_provenance(db,order_id,tenant_id)
    order=read(db,order_id,tenant_id)
    breakdown=order["amounts_by_cycle_minor"]
    if not breakdown or any(type(v) is not int or v<0 for v in breakdown.values()):
        raise ValueError("UNSETTLEABLE_AMOUNT")
    return {"order_id":_ident(order_id),"tenant_id":_ident(tenant_id),
            "quote_id":order["quote_id"],"quote_sha256":order["quote_sha256"],
            "currency":order["currency"],"amounts_by_cycle_minor":dict(breakdown),
            "requires_finance_verification":True,"settled":False}

def make_test_attestation(claim,proof_id,at,key):
    """OFFLINE TEST FIXTURE ONLY. Never use it to validate provider callbacks."""
    _ident(proof_id);_timestamp(at)
    if type(key) is not bytes or len(key)<32:
        raise ValueError("INVALID_TEST_KEY")
    payload={**claim,"proof_id":proof_id,"verified_at":at}
    signature=hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()
    return {"payload":payload,"signature":signature}

def inspect_test_attestation(db, order_id, tenant_id, attestation, key, now):
    """Validate offline fixture provenance and exact order binding.

    A successful result is a TEST PASS, never production finance authority.
    """
    _timestamp(now)
    if type(key) is not bytes or len(key)<32:
        raise ValueError("INVALID_TEST_KEY")
    if type(attestation) is not dict or set(attestation)!={"payload","signature"}:
        raise ValueError("INVALID_ATTESTATION")
    payload,signature=attestation["payload"],attestation["signature"]
    if type(payload) is not dict or type(signature) is not str or len(signature)!=64:
        raise ValueError("INVALID_ATTESTATION")
    proof_id=payload.get("proof_id")
    verified_at=payload.get("verified_at")
    _ident(proof_id);_timestamp(verified_at)
    if verified_at < read(db,order_id,tenant_id)["created_at"]:
        raise ValueError("PRE_ORDER_ATTESTATION")
    if verified_at>now:
        raise ValueError("FUTURE_ATTESTATION")
    expected={**plan_finance_claim(db,order_id,tenant_id),
              "proof_id":proof_id,"verified_at":verified_at}
    if payload!=expected:
        raise ValueError("FINANCE_CLAIM_MISMATCH")
    expected_sig=hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected_sig):
        raise ValueError("INVALID_ATTESTATION_SIGNATURE")
    return {"order_id":order_id,"tenant_id":tenant_id,"proof_id":proof_id,
            "quote_sha256":payload["quote_sha256"],
            "verified_test_fixture":True,"production_eligible":False}

REVIEW_SCHEMA="""
CREATE TABLE IF NOT EXISTS saas_review_tasks(
 task_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, order_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('FINANCE_EVIDENCE','ENTITLEMENT','RENEWAL','CONTRACT','REFUND','DEPLOYMENT')),
 created_at INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('PENDING','RESOLVED','CANCELLED')),
 reason TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS saas_review_no_delete BEFORE DELETE ON saas_review_tasks
 BEGIN SELECT RAISE(ABORT,'REVIEW_TASK_DELETE_BLOCKED'); END;
CREATE TABLE IF NOT EXISTS saas_review_events(
 event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
 action TEXT NOT NULL, occurred_at INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS saas_review_events_update BEFORE UPDATE ON saas_review_events
 BEGIN SELECT RAISE(ABORT,'REVIEW_EVENT_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS saas_review_events_delete BEFORE DELETE ON saas_review_events
 BEGIN SELECT RAISE(ABORT,'REVIEW_EVENT_IMMUTABLE'); END;
"""
def install_reviews(db):
    if not isinstance(db,sqlite3.Connection):
        raise TypeError("SQLITE_CONNECTION_REQUIRED")
    db.executescript(REVIEW_SCHEMA)

def create_review(db,task_id,tenant_id,order_id,kind,at,reason):
    _ident(task_id);_ident(tenant_id);_ident(order_id);_timestamp(at)
    if kind not in ("FINANCE_EVIDENCE","ENTITLEMENT","RENEWAL","CONTRACT","REFUND","DEPLOYMENT"):
        raise ValueError("INVALID_REVIEW_KIND")
    if type(reason) is not str or not reason.strip() or len(reason)>300:
        raise ValueError("INVALID_REASON")
    read(db,order_id,tenant_id)
    with db:
        existing=db.execute("SELECT tenant_id,order_id,kind,created_at,reason,state FROM saas_review_tasks WHERE task_id=?",
                            (task_id,)).fetchone()
        record=(tenant_id,order_id,kind,at,reason)
        if existing:
            if existing[:5]!=record: raise ValueError("REVIEW_TASK_CONFLICT")
            return {"task_id":task_id,"state":existing[5]}
        db.execute("INSERT INTO saas_review_tasks VALUES(?,?,?,?,?,'PENDING',?)",
                   (task_id,tenant_id,order_id,kind,at,reason))
    return {"task_id":task_id,"state":"PENDING"}

def change_review(db,task_id,tenant_id,event_id,state,at):
    _ident(task_id);_ident(tenant_id);_ident(event_id);_timestamp(at)
    if state not in ("RESOLVED","CANCELLED"):
        raise ValueError("INVALID_REVIEW_STATE")
    with db:
        row=db.execute("SELECT tenant_id,created_at,state FROM saas_review_tasks WHERE task_id=?",
                       (task_id,)).fetchone()
        if not row or row[0]!=tenant_id:
            raise ValueError("REVIEW_NOT_FOUND")
        event=db.execute("SELECT task_id,tenant_id,action,occurred_at FROM saas_review_events WHERE event_id=?",
                         (event_id,)).fetchone()
        expected=(task_id,tenant_id,state,at)
        if event:
            if event!=expected: raise ValueError("REVIEW_EVENT_CONFLICT")
            return {"task_id":task_id,"state":row[2]}
        if row[2]!="PENDING" or at<row[1]:
            raise ValueError("INVALID_REVIEW_TRANSITION")
        db.execute("UPDATE saas_review_tasks SET state=? WHERE task_id=?",(state,task_id))
        db.execute("INSERT INTO saas_review_events VALUES(?,?,?,?,?)",
                   (event_id,task_id,tenant_id,state,at))
    return {"task_id":task_id,"state":state}

def admin_snapshot(db,tenant_id,at):
    """Tenant-scoped read model. No global unfiltered customer data."""
    _ident(tenant_id);_timestamp(at)
    rows=db.execute("SELECT order_id,created_at,snapshot FROM saas_order_preparations WHERE tenant_id=? ORDER BY order_id",
                    (tenant_id,)).fetchall()
    orders=[]
    for oid,created,snapshot in rows:
        state=status(db,oid,tenant_id)
        item=json.loads(snapshot)
        orders.append({"order_id":oid,"created_at":created,
                       "state":state["state"],"currency":item["currency"],
                       "amounts_by_cycle_minor":item["amounts_by_cycle_minor"],
                       "payment_settled":False,"entitlement_granted":False})
    tasks=[{"task_id":tid,"order_id":oid,"kind":kind,"state":state,"reason":reason}
           for tid,oid,kind,state,reason in db.execute(
             "SELECT task_id,order_id,kind,state,reason FROM saas_review_tasks WHERE tenant_id=? ORDER BY task_id",
             (tenant_id,)).fetchall()]
    return {"tenant_id":tenant_id,"at":at,"orders":orders,"review_tasks":tasks,
            "production_payments_verified":False,"live_deployment":False}

def recovery_check(db,tenant_id):
    """Deterministic reconciliation report: no retry, no external side effects."""
    data=admin_snapshot(db,tenant_id,0)
    return {"tenant_id":tenant_id,
            "awaiting_review":[x["order_id"] for x in data["orders"]
                               if x["state"] in ("CONFIRMATION_UNKNOWN","AWAITING_EXTERNAL")],
            "open_tasks":[x["task_id"] for x in data["review_tasks"] if x["state"]=="PENDING"],
            "resend_payment_requests":False,"automatic_reconcile_executed":False}
