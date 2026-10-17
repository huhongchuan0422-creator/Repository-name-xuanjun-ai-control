"""Project internally verified provider observations into the original order DB.

Called only after PartnerOrderReader signature/binding verification and current
customer ownership checks. No HTTP accepts evidence or a 'verified' boolean.
A paid observation is not Finance settlement or a fiscal receipt.
"""
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_merchant_contract import scope,valid_id
from scripts.community_order_store import state


def provider_evidence(db,identity,reference):
    t,m,s=scope(identity)
    if not valid_id(reference):raise ValueError('INVALID_ORDER_REFERENCE')
    row=db.execute('SELECT state,provider_transaction_id FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,reference)).fetchone()
    if row is None:raise ValueError('ORDER_NOT_FOUND')
    evidence=None
    for target,raw in db.execute('SELECT to_state,evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? ORDER BY rowid',(t,m,s,reference)):
        try:value=json.loads(raw)
        except (ValueError,TypeError):continue
        if (type(value) is dict and value.get('source') in ('WECHAT_SIGNED_ORDER_QUERY','WECHAT_SIGNED_REFUND_RESULT')
                and target==row[0] and value.get('transaction_id')==row[1]
                and type(value.get('body_sha256')) is str and len(value['body_sha256'])==64):evidence=value
    return evidence


def project_verified_query(db,identity,reference,expected,observation,at,key_id):
    """Internal writer: observation must be returned by the bound reader call."""
    t,m,s=scope(identity)
    if not valid_id(reference) or type(at) is not int or at<0:raise ValueError('INVALID_PROVIDER_PROJECTION')
    if (type(expected) is not dict or type(observation) is not dict
            or observation.get('source')!='SIGNED_PROVIDER_ORDER_QUERY'
            or observation.get('signature_key_id')!=key_id
            or observation.get('out_trade_no')!=expected['out_trade_no']
            or observation.get('amount_minor')!=expected['amount_minor'] or observation.get('currency')!='CNY'):
        raise PermissionError('INTERNAL_VERIFIED_ORDER_OBSERVATION_REQUIRED')
    provider_state=observation['provider_state']
    target='SUCCESS' if provider_state in ('SUCCESS','REFUND') else 'CANCELLED' if provider_state in ('CLOSED','REVOKED') else None
    if target is None:return dict(changed=False,provider_state=provider_state)
    tx=observation['transaction_id'] if target=='SUCCESS' else None
    if target=='SUCCESS' and (type(tx) is not str or not tx.isdigit() or not 1<=len(tx)<=64):raise ValueError('PROVIDER_TRANSACTION_REQUIRED')
    body_hash=observation.get('body_sha256')
    if type(body_hash) is not str or len(body_hash)!=64:raise ValueError('SIGNED_BODY_HASH_REQUIRED')
    event='wp_'+hashlib.sha256(canonical([expected['sp_mchid'],expected['sub_mchid'],expected['out_trade_no'],target,tx])).hexdigest()[:48]
    evidence=dict(source='WECHAT_SIGNED_ORDER_QUERY',body_sha256=body_hash,transaction_id=tx,provider_state=provider_state,observed_at=at)
    if db.in_transaction:raise ValueError('EXTERNAL_ORDER_TRANSACTION_DENIED')
    db.execute('BEGIN IMMEDIATE')
    try:
        order=state(db,identity,reference)
        if order['amount_minor']!=expected['amount_minor'] or order['currency']!='CNY':raise PermissionError('ORIGINAL_ORDER_AMOUNT_CHANGED')
        prior=db.execute('SELECT tenant_id,merchant_id,store_id,reference,to_state FROM order_events WHERE event_id=?',(event,)).fetchone()
        if prior:
            if prior!=(t,m,s,reference,target) or order['state']!=target or order['provider_transaction_id']!=tx:raise ValueError('PROVIDER_EVENT_COLLISION')
            db.commit();return dict(changed=False,provider_state=provider_state)
        if order['state']=='REFUNDED' and provider_state=='REFUND' and provider_evidence(db,identity,reference) is not None:
            db.commit();return dict(changed=False,provider_state=provider_state)
        if order['state']!='PENDING':raise PermissionError('ORDER_STATE_REQUIRES_RECONCILIATION')
        changed=db.execute('UPDATE orders SET state=?,provider_transaction_id=? WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? AND state=\'PENDING\'',(target,tx,t,m,s,reference))
        if changed.rowcount!=1:raise ValueError('ORDER_PROJECTION_CONFLICT')
        db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',(event,t,m,s,reference,'PENDING',target,canonical(evidence).decode()))
        db.commit()
    except BaseException:db.rollback();raise
    return dict(changed=True,provider_state=provider_state)


def project_verified_refund(db,identity,reference,out_refund_no,amount_minor,total_minor,body_sha256,at):
    """Internal caller supplies an already RSA-verified SUCCESS refund result."""
    t,m,s=scope(identity)
    if (not valid_id(reference) or not valid_id(out_refund_no) or type(amount_minor) is not int
            or type(total_minor) is not int or not 1<=amount_minor<=total_minor
            or type(body_sha256) is not str or len(body_sha256)!=64 or type(at) is not int or at<0):raise ValueError('INVALID_VERIFIED_REFUND_PROJECTION')
    event='wr_'+hashlib.sha256(canonical([identity,reference,out_refund_no])).hexdigest()[:48]
    if db.in_transaction:raise ValueError('EXTERNAL_ORDER_TRANSACTION_DENIED')
    db.execute('BEGIN IMMEDIATE')
    try:
        order=state(db,identity,reference)
        if order['amount_minor']!=total_minor or order['state'] not in ('SUCCESS','REFUNDED') or provider_evidence(db,identity,reference) is None:raise PermissionError('VERIFIED_PAID_ORDER_REQUIRED')
        prior=db.execute('SELECT tenant_id,merchant_id,store_id,reference,evidence_source FROM order_events WHERE event_id=?',(event,)).fetchone()
        if prior:
            evidence=json.loads(prior[4])
            if prior[:4]!=(t,m,s,reference) or evidence.get('out_refund_no')!=out_refund_no or evidence.get('refund_minor')!=amount_minor:raise ValueError('VERIFIED_REFUND_EVENT_COLLISION')
            db.commit();return dict(changed=False,order_state=order['state'])
        refunded=0
        for raw, in db.execute('SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,reference)):
            try:value=json.loads(raw)
            except (ValueError,TypeError):continue
            if type(value) is dict and value.get('source')=='WECHAT_SIGNED_REFUND_RESULT':
                amount=value.get('refund_minor')
                if type(amount) is not int or amount<=0:raise ValueError('INVALID_REFUND_EVENT_HISTORY')
                refunded+=amount
        if refunded+amount_minor>total_minor:raise ValueError('VERIFIED_REFUND_TOTAL_CONFLICT')
        target='REFUNDED' if refunded+amount_minor==total_minor else 'SUCCESS'
        evidence=dict(source='WECHAT_SIGNED_REFUND_RESULT',body_sha256=body_sha256,transaction_id=order['provider_transaction_id'],out_refund_no=out_refund_no,refund_minor=amount_minor,observed_at=at)
        db.execute('UPDATE orders SET state=? WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(target,t,m,s,reference))
        db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',(event,t,m,s,reference,order['state'],target,canonical(evidence).decode()))
        db.commit()
    except BaseException:db.rollback();raise
    return dict(changed=True,order_state=target)
