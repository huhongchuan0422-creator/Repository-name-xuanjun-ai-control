"""Offline SQLite simulated order state machine. No real payment or provider credentials."""
import sqlite3
from scripts.community_merchant_contract import scope, payment_amount

DDL = """
CREATE TABLE orders (
 tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
 reference TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(amount_minor>0),
 currency TEXT NOT NULL CHECK(currency='CNY'),
 state TEXT NOT NULL CHECK(state IN ('PENDING','SUCCESS','FAILED','CANCELLED','REFUNDED')),
 provider_transaction_id TEXT,
 PRIMARY KEY(tenant_id,merchant_id,store_id,reference)
);
CREATE UNIQUE INDEX provider_tx_unique ON orders(provider_transaction_id)
 WHERE provider_transaction_id IS NOT NULL;
CREATE TABLE order_events(
 event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL,
 store_id TEXT NOT NULL, reference TEXT NOT NULL, from_state TEXT NOT NULL,
 to_state TEXT NOT NULL, evidence_source TEXT NOT NULL
);
CREATE TRIGGER event_no_update BEFORE UPDATE ON order_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER event_no_delete BEFORE DELETE ON order_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
"""
def _catalog(db):
    return sorted(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                             "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall())

def connect(path=':memory:'):
    db=sqlite3.connect(path)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        template=sqlite3.connect(':memory:')
        try:
            template.executescript(DDL)
            expected=_catalog(template)
        finally:
            template.close()
        existing=_catalog(db)
        if not existing:
            if db.execute('PRAGMA user_version').fetchone()[0] != 0:
                raise ValueError('INCOMPATIBLE_ORDER_SCHEMA')
            db.executescript('BEGIN IMMEDIATE;'+DDL+'PRAGMA user_version=1;COMMIT;')
        elif existing != expected or db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('INCOMPATIBLE_ORDER_SCHEMA')
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError('INVALID_ORDER_DATABASE')
        return db
    except BaseException:
        if db.in_transaction: db.rollback()
        db.close()
        raise

def create_order(db, identity, reference, amount_minor):
    t,m,s=scope(identity)
    checked=payment_amount(amount_minor,'CNY',reference)
    with db:
        db.execute("INSERT INTO orders VALUES(?,?,?,?,?,'CNY','PENDING',NULL)",
                   (t,m,s,reference,checked['amount_minor']))
    return {'reference':reference,'state':'PENDING','provider_payment_started':False}

def state(db, identity, reference):
    t,m,s=scope(identity)
    row=db.execute("SELECT amount_minor,currency,state,provider_transaction_id FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?",(t,m,s,reference)).fetchone()
    if row is None: raise ValueError('ORDER_NOT_FOUND')
    return {'amount_minor':row[0],'currency':row[1],'state':row[2],
            'provider_transaction_id':row[3], 'provider_settlement_verified':False}

def simulated_transition(db, identity, reference, event_id, target, evidence):
    """Only a trusted local test caller may invoke. Never expose as HTTP endpoint."""
    t,m,s=scope(identity)
    from scripts.community_merchant_contract import valid_id
    if not valid_id(reference) or not valid_id(event_id) or target not in ('SUCCESS','FAILED','CANCELLED'):
        raise ValueError('INVALID_TRANSITION')
    if not isinstance(evidence,dict) or evidence.get('simulation_only') is not True or evidence.get('scope')!=identity:
        raise ValueError('SIMULATION_EVIDENCE_REQUIRED')
    if evidence.get('reference')!=reference or type(evidence.get('amount_minor')) is not int:
        raise ValueError('EVIDENCE_MISMATCH')
    tx=evidence.get('provider_transaction_id')
    if not valid_id(tx): raise ValueError('INVALID_TRANSACTION_ID')
    # Own the write transaction BEFORE reading either the event or order state.
    # An IMMEDIATE lock serializes competing connections and blocks stale writes.
    if db.in_transaction:
        raise ValueError('EXTERNAL_TRANSACTION_NOT_ALLOWED')
    db.execute('BEGIN IMMEDIATE')
    try:
        seen=db.execute('SELECT tenant_id,merchant_id,store_id,reference,to_state FROM order_events WHERE event_id=?',(event_id,)).fetchone()
        row=db.execute('SELECT amount_minor,state,provider_transaction_id FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,reference)).fetchone()
        if seen is not None:
            if (seen!=(t,m,s,reference,target) or row is None or
                row!=(evidence['amount_minor'],target,tx)):
                raise ValueError('EVENT_ID_COLLISION')
            db.commit()
            return {'state':target,'duplicate':True}
        if row is None: raise ValueError('ORDER_NOT_FOUND')
        if row[0]!=evidence['amount_minor'] or row[1]!='PENDING':
            raise ValueError('INVALID_ORDER_STATE')
        updated=db.execute("UPDATE orders SET state=?,provider_transaction_id=? "
            "WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? "
            "AND state='PENDING' AND amount_minor=? AND provider_transaction_id IS NULL",
            (target,tx,t,m,s,reference,evidence['amount_minor']))
        if updated.rowcount!=1: raise ValueError('CONCURRENT_STATE_CONFLICT')
        db.execute("INSERT INTO order_events VALUES(?,?,?,?,?,?,?,'SIMULATED')",
                   (event_id,t,m,s,reference,'PENDING',target))
        db.commit()
        return {'state':target,'duplicate':False,'provider_settlement_verified':False}
    except BaseException:
        db.rollback()
        raise
