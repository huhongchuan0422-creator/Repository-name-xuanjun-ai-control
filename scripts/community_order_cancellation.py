"""One consumed close attempt, signed terminal query and recoverable stock release."""
import hashlib
import json
from scripts.pr122_customer_core import canonical
from scripts.community_order_store import state
from scripts.community_order_provider_projection import project_verified_query


def local_cancelled(db,identity,reference):
    t,m,s=(identity[k] for k in ('tenant_id','merchant_id','store_id'))
    for raw, in db.execute("SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? AND to_state='CANCELLED'",(t,m,s,reference)):
        try:evidence=json.loads(raw)
        except (ValueError,TypeError):continue
        if type(evidence) is dict and evidence.get('source')=='LOCAL_CANCEL_BEFORE_PROVIDER':return True
    return False


class OrderCancellation:
    def __init__(self,payments):self.payments=payments;self.center=payments.identity.center
    def cancel(self,token,scene,reference):
        p,c=self.payments,self.center
        b=p._authorize(token,scene,reference)
        uid,project,principal=p.identity._resolve(token,scene)
        identity=p.identity.runtime.bindings[principal];db=p.identity.runtime.demo.db
        key=p.prepay._identity(b);binding_hash=hashlib.sha256(canonical(b)).hexdigest()
        original=state(db,identity,reference)
        if original['state'] not in ('PENDING','CANCELLED'):raise PermissionError('ONLY_UNPAID_ORDER_CAN_BE_CANCELLED')
        with c.tx():
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_ORDER_CLOSE' AND subject_idx=? AND active=1",(key,)).fetchone()
            if row:
                saved=json.loads(c.decrypt(row[0],'community-close:'+key))
                if saved['binding_hash']!=binding_hash:raise PermissionError('CLOSE_BINDING_CHANGED')
                first=False
            else:
                attempted=c.db.execute("SELECT 1 FROM events WHERE channel='COMMUNITY_PREPAY_ATTEMPT' AND event_id=?",(key,)).fetchone() is not None
                saved=dict(binding_hash=binding_hash,provider_attempted=attempted,reference=reference,state='CLOSE_RESERVED')
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_ORDER_CLOSE',?,?,?,?,1)",(key,uid,project,c.encrypt(canonical(saved),'community-close:'+key)))
                c.audit(project,uid,'COMMUNITY_ORDER_CLOSE_RESERVED',key);first=True
        if not saved['provider_attempted']:
            event='lc_'+hashlib.sha256(canonical([identity,reference])).hexdigest()[:48]
            if db.in_transaction:raise ValueError('EXTERNAL_ORDER_TRANSACTION_DENIED')
            db.execute('BEGIN IMMEDIATE')
            try:
                original=state(db,identity,reference)
                if original['state']=='PENDING':
                    t,m,s=(identity[k] for k in ('tenant_id','merchant_id','store_id'))
                    db.execute("UPDATE orders SET state='CANCELLED' WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? AND state='PENDING'",(t,m,s,reference))
                    db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',(event,t,m,s,reference,'PENDING','CANCELLED',canonical(dict(source='LOCAL_CANCEL_BEFORE_PROVIDER',close_intent=key)).decode()))
                elif original['state']!='CANCELLED' or not local_cancelled(db,identity,reference):raise PermissionError('CLOSE_STATE_CONFLICT')
                db.commit()
            except BaseException:db.rollback();raise
            provider_state='NOT_CREATED';verified=False
        else:
            # A close ACK is never treated as payment-state evidence. Even a
            # timeout leads to signed query; an existing intent never POSTs again.
            if first:
                from scripts.community_provider_transport import request
                try:request(p.prepay.reader,'POST','/v3/pay/partner/transactions/out-trade-no/'+b['out_trade_no']+'/close',dict(sp_mchid=p.prepay.reader._mchid,sub_mchid=b['sub_mchid']),empty_response=True)
                except Exception:pass
            reader=p.prepay.reader
            expected=dict(sp_mchid=reader._mchid,sub_mchid=b['sub_mchid'],sp_appid=b['sp_appid'],out_trade_no=b['out_trade_no'],amount_minor=b['amount_minor'],currency='CNY')
            observed=reader.read_order(expected)
            if p._authorize(token,scene,reference)!=b:raise PermissionError('CLOSE_AUTHORIZATION_CHANGED')
            project_verified_query(db,identity,reference,expected,observed,c.now(),reader._kid)
            provider_state=observed['provider_state'];verified=True
        p.identity.authorize_order_read(token,scene,reference,c.now())
        order=state(db,identity,reference)
        if order['state']=='CANCELLED':
            commerce=getattr(p,'commerce',None)
            if commerce is not None:commerce.release_cancelled(identity,project,uid,reference)
            with c.tx():
                saved['state']='CANCELLED_CONFIRMED'
                c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_ORDER_CLOSE' AND subject_idx=? AND active=1",(c.encrypt(canonical(saved),'community-close:'+key),key))
                c.audit(project,uid,'COMMUNITY_ORDER_CANCELLED',key)
        return dict(reference=reference,order_state=order['state'],provider_state=provider_state,
            provider_signature_verified=verified,provider_settlement_verified=False,automatic_close_retry_allowed=False)
