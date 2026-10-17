"""Stage5 offline refund *preview* journal; never executes provider refunds.

The order database and this journal are separate SQLite files; consequently
this is not a cross-database financial transaction, reconciliation, or payment.
"""
import sqlite3
from scripts.community_merchant_contract import scope, valid_id
from scripts.community_order_store import state

SCHEMA = """
CREATE TABLE refund_events(
 tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
 reference TEXT NOT NULL, event_id TEXT NOT NULL UNIQUE,
 amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
 evidence_kind TEXT NOT NULL CHECK(evidence_kind='OFFLINE_PREVIEW'),
 PRIMARY KEY(tenant_id,merchant_id,store_id,reference,event_id)
);
CREATE TRIGGER refund_events_no_replace BEFORE INSERT ON refund_events
WHEN EXISTS(SELECT 1 FROM refund_events WHERE event_id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER refund_events_no_update BEFORE UPDATE ON refund_events
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER refund_events_no_delete BEFORE DELETE ON refund_events
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
"""
def _schema(db):
    return sorted(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL").fetchall())

def open_refund_store(path=":memory:"):
    db=sqlite3.connect(path)
    try:
        template=sqlite3.connect(":memory:")
        try:
            template.executescript(SCHEMA)
            expected=_schema(template)
        finally: template.close()
        actual=_schema(db)
        version=db.execute("PRAGMA user_version").fetchone()[0]
        if not actual and version==0:
            db.executescript("BEGIN IMMEDIATE;"+SCHEMA+"PRAGMA user_version=2;COMMIT;")
        elif actual!=expected or version!=2:
            raise ValueError("INVALID_REFUND_SCHEMA")
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("INVALID_REFUND_DATABASE")
        return db
    except BaseException:
        if db.in_transaction:db.rollback()
        db.close()
        raise

def preview_total(db,identity,reference):
    t,m,s=scope(identity)
    if not valid_id(reference): raise ValueError("INVALID_REFERENCE")
    return db.execute(
        "SELECT COALESCE(SUM(amount_minor),0) FROM refund_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?",
        (t,m,s,reference)).fetchone()[0]

def record_preview(db,orders,identity,reference,event_id,amount_minor):
    """Returns non-financial journal state; never mutates the order or provider."""
    t,m,s=scope(identity)
    if not valid_id(reference) or not valid_id(event_id):
        raise ValueError("INVALID_REFUND_ID")
    if type(amount_minor) is not int or not 1<=amount_minor<=100000000:
        raise ValueError("INVALID_REFUND_AMOUNT")
    from scripts.community_order_provider_projection import provider_evidence
    if provider_evidence(orders,identity,reference) is not None:
        raise PermissionError('REAL_ORDER_REQUIRES_PROVIDER_REFUND_WORKFLOW')
    original=state(orders,identity,reference)
    if original["state"]!="SUCCESS" or original["provider_settlement_verified"] is not False:
        raise ValueError("SIMULATED_SUCCESS_REQUIRED")
    if db.in_transaction:
        raise ValueError("EXTERNAL_TRANSACTION_NOT_ALLOWED")
    db.execute("BEGIN IMMEDIATE")
    try:
        seen=db.execute("SELECT tenant_id,merchant_id,store_id,reference,amount_minor FROM refund_events WHERE event_id=?",(event_id,)).fetchone()
        if seen is not None:
            if seen!=(t,m,s,reference,amount_minor):
                raise ValueError("REFUND_EVENT_COLLISION")
            total=preview_total(db,identity,reference)
            db.commit()
            return {"recorded":False,"preview_total_minor":total,"provider_refund_executed":False}
        total=preview_total(db,identity,reference)
        if total+amount_minor>original["amount_minor"]:
            raise ValueError("REFUND_PREVIEW_EXCEEDS_ORDER")
        db.execute("INSERT INTO refund_events VALUES(?,?,?,?,?,?,'OFFLINE_PREVIEW')",
                   (t,m,s,reference,event_id,amount_minor))
        db.commit()
        return {"recorded":True,"preview_total_minor":total+amount_minor,"provider_refund_executed":False}
    except BaseException:
        db.rollback()
        raise
