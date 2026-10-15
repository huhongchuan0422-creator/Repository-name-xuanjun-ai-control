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
CREATE TRIGGER saas_order_preparations_no_replace BEFORE INSERT ON saas_order_preparations
WHEN EXISTS(SELECT 1 FROM saas_order_preparations WHERE order_id=NEW.order_id)
BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CONFLICT'); END;
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

# Evidence is recorded as an append-only offline handoff. It does not attest
# third-party payment validity: production Finance must verify independently.
LIFECYCLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS saas_order_lifecycle(
 order_id TEXT PRIMARY KEY, state TEXT NOT NULL
 CHECK(state IN ('PREPARED','AWAITING_EXTERNAL','CONFIRMATION_UNKNOWN','CONFIRMED_EXTERNAL','CANCELLED','EXPIRED')),
 proof_ref TEXT, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS saas_order_lifecycle_events(
 event_key TEXT PRIMARY KEY, order_id TEXT NOT NULL, old_state TEXT NOT NULL,
 new_state TEXT NOT NULL, proof_ref TEXT, occurred_at INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS saas_lifecycle_event_no_update BEFORE UPDATE ON saas_order_lifecycle_events
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_LIFECYCLE_EVENT'); END;
CREATE TRIGGER IF NOT EXISTS saas_lifecycle_event_no_delete BEFORE DELETE ON saas_order_lifecycle_events
 BEGIN SELECT RAISE(ABORT,'IMMUTABLE_LIFECYCLE_EVENT'); END;
"""
TRANSITIONS={
    "PREPARED":{"AWAITING_EXTERNAL","CANCELLED","EXPIRED"},
    "AWAITING_EXTERNAL":{"CONFIRMATION_UNKNOWN","CANCELLED","EXPIRED"},
    "CONFIRMATION_UNKNOWN":{"CONFIRMED_EXTERNAL","CANCELLED","EXPIRED"},
}
def install_lifecycle(db):
    if not isinstance(db,sqlite3.Connection):
        raise TypeError("SQLITE_CONNECTION_REQUIRED")
    db.executescript(LIFECYCLE_SCHEMA)

def advance(db,order_id,tenant_id,event_key,new_state,at,proof_ref=None,
            trusted_finance_attestation=False):
    """Offline state transition; trusted attestation supplied by authorized caller.

    CONFIRMED_EXTERNAL means an external verification proof was recorded, not
    that this adapter verified the payment, provisioned access or credited money.
    """
    _identifier(order_id);_identifier(tenant_id);_identifier(event_key)
    if type(at) is not int or at<0 or type(trusted_finance_attestation) is not bool:
        raise ValueError("INVALID_TRANSITION_CONTEXT")
    if proof_ref is not None and (type(proof_ref) is not str or not valid_id(proof_ref)):
        raise ValueError("INVALID_PROOF_REF")
    if new_state=="CONFIRMED_EXTERNAL" and (
        not trusted_finance_attestation or proof_ref is None):
        raise ValueError("FINANCE_ATTESTATION_REQUIRED")
    if new_state not in ("AWAITING_EXTERNAL","CONFIRMATION_UNKNOWN","CONFIRMED_EXTERNAL","CANCELLED","EXPIRED"):
        raise ValueError("INVALID_TARGET_STATE")
    with db:
        row=db.execute("SELECT tenant_id,created_at FROM saas_order_preparations WHERE order_id=?",(order_id,)).fetchone()
        if row is None or row[0]!=tenant_id:
            raise ValueError("ORDER_NOT_FOUND")
        existing=db.execute("SELECT order_id,new_state,proof_ref,occurred_at FROM saas_order_lifecycle_events WHERE event_key=?",
                            (event_key,)).fetchone()
        if existing is not None:
            if existing!=(order_id,new_state,proof_ref,at):
                raise ValueError("EVENT_IDEMPOTENCY_CONFLICT")
            return status(db,order_id,tenant_id)
        current=db.execute("SELECT state,updated_at FROM saas_order_lifecycle WHERE order_id=?",(order_id,)).fetchone()
        old=current[0] if current else "PREPARED"
        if at<(current[1] if current else row[1]):
            raise ValueError("STALE_EVENT_TIME")
        if new_state not in TRANSITIONS.get(old,set()):
            raise ValueError("INVALID_STATE_TRANSITION")
        if current:
            db.execute("UPDATE saas_order_lifecycle SET state=?,proof_ref=?,updated_at=? WHERE order_id=?",
                       (new_state,proof_ref,at,order_id))
        else:
            db.execute("INSERT INTO saas_order_lifecycle VALUES(?,?,?,?)",
                       (order_id,new_state,proof_ref,at))
        db.execute("INSERT INTO saas_order_lifecycle_events VALUES(?,?,?,?,?,?)",
                   (event_key,order_id,old,new_state,proof_ref,at))
    return status(db,order_id,tenant_id)

def status(db,order_id,tenant_id):
    read(db,order_id,tenant_id)
    row=db.execute("SELECT state,proof_ref,updated_at FROM saas_order_lifecycle WHERE order_id=?",(order_id,)).fetchone()
    return {"order_id":order_id,"tenant_id":tenant_id,
            "state":row[0] if row else "PREPARED",
            "proof_ref":row[1] if row else None,
            "updated_at":row[2] if row else None,
            "entitlement_granted":False,"payment_settled_by_this_module":False}

def quote_provenance(db,order_id,tenant_id):
    """Verify the immutable quotation digest before an external handoff."""
    order=read(db,order_id,tenant_id)
    actual=hashlib.sha256(json.dumps(order["quote_snapshot"],ensure_ascii=False,
        sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    if actual!=order["quote_sha256"]:
        raise ValueError("QUOTE_SNAPSHOT_DIGEST_MISMATCH")
    return {"order_id":order_id,"quote_id":order["quote_id"],
            "quote_sha256":actual,"verified":True}

def renewal_intent(db,order_id,tenant_id,now,existing_valid_until=None):
    """Read-only schedule proposal; cannot authorize or execute a renewal.

    With an active subscription, propose a contiguous extension. An expired
    subscription is proposed to start at now. Neither grants entitlements.
    """
    if type(now) is not int or now<0 or (existing_valid_until is not None and
        (type(existing_valid_until) is not int or existing_valid_until<0)):
        raise ValueError("INVALID_RENEWAL_CONTEXT")
    order=read(db,order_id,tenant_id)
    if order["quote_snapshot"]["kind"] not in ("MONTHLY","YEARLY","PROMOTION"):
        raise ValueError("RENEWAL_KIND_UNSUPPORTED")
    start=max(now,existing_valid_until) if existing_valid_until is not None else now
    proposal=entitlement_intent(db,order_id,tenant_id,start)
    return {**proposal,"mode":"RENEWAL_REVIEW_ONLY",
        "existing_valid_until":existing_valid_until,
        "continuous":existing_valid_until is not None and existing_valid_until>=now,
        "payment_confirmed_by_adapter":False}

def entitlement_intent(db,order_id,tenant_id,start_at):
    """Return a non-executable entitlement proposal for a separate authority.

    The legacy module grant requires module_prices.price_version and a trusted
    payment callback: offer_version must never be silently treated as one.
    """
    if type(start_at) is not int or start_at<0:
        raise ValueError("INVALID_ENTITLEMENT_START")
    view=status(db,order_id,tenant_id)
    if view["state"]!="CONFIRMED_EXTERNAL":
        raise ValueError("CONFIRMATION_EVIDENCE_REQUIRED")
    quote_provenance(db,order_id,tenant_id)
    order=read(db,order_id,tenant_id)
    q=order["quote_snapshot"]
    term=q.get("term_days")
    if type(term) is not int or term<1:
        raise ValueError("TERM_OR_LICENSE_REVIEW_REQUIRED")
    return {"tenant_id":tenant_id,"order_id":order_id,
            "module_id":order["module_id"],"offer_id":order["offer_id"],
            "offer_version":order["offer_version"],"quote_sha256":order["quote_sha256"],
            "proposed_valid_from":start_at,"proposed_valid_until":start_at+term*86400,
            "legacy_price_version":None,"needs_authoritative_finance_link":True,
            "needs_entitlement_approval":True,"entitlement_granted":False,
            "automatic_renewal_authorized":False}
