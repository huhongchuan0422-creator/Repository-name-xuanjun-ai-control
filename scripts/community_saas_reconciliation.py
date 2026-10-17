"""Cross-check two signed provider observations in the original review store.

Protected operator operation, not a payment endpoint or authoritative Finance
receipt. Unknown queries are never retried here. No new queue or ledger exists.
"""
import hashlib
from scripts.community_saas_provider_evidence import SaasProviderEvidence
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_wechat_sp_verification import notification_candidate
from scripts.community_saas_offline_handoff import canonical,plan_finance_claim,create_review
from scripts.community_saas_phase2 import Principal


def reconcile(inbox,reader,principal,order_id,headers,raw_body):
    if type(inbox) is not SaasProviderEvidence or type(reader) is not PartnerOrderReader:
        raise ValueError('EXISTING_SIGNED_PROVIDER_PORTS_REQUIRED')
    runtime=inbox.runtime
    if (type(principal) is not Principal or principal not in runtime.bindings
            or principal.role!='PLATFORM_OWNER'):
        raise PermissionError('REGISTERED_OWNER_REQUIRED')
    if (reader._mchid!=inbox.merchant['sp_mchid'] or reader._kid!=inbox._kid
            or reader._public!=inbox._public):
        raise PermissionError('SAME_TRUSTED_PROVIDER_CONFIG_REQUIRED')
    tenant=principal.tenant_id
    binding=inbox.orders.get((tenant,order_id))
    if binding is None:raise PermissionError('INVOICE_BINDING_REQUIRED')
    binding=dict(binding);merchant=dict(inbox.merchant)
    db=runtime.saas.orders
    if db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
    claim=plan_finance_claim(db,order_id,tenant)
    if claim['currency']!='CNY':raise ValueError('CNY_INVOICE_REQUIRED')
    expected=dict(merchant,out_trade_no=binding['out_trade_no'],currency='CNY',
                  amount_minor=claim['amounts_by_cycle_minor'][binding['cycle']])
    candidate=notification_candidate(headers,raw_body,inbox._public,inbox._kid,inbox._api,expected,runtime.clock())
    # Never hold a database write lock during network IO. The reader performs
    # exactly one signed GET and verifies its raw response independently.
    query=reader.read_order(expected)
    if query['provider_state']!='SUCCESS' or query['transaction_id']!=candidate['transaction_id']:
        raise ValueError('SIGNED_PROVIDER_OBSERVATIONS_DISAGREE')
    now=runtime.clock()
    # Recheck the original notification window after potentially slow query IO.
    notification_candidate(headers,raw_body,inbox._public,inbox._kid,inbox._api,expected,now)
    def unchanged():
        return (principal in runtime.bindings and principal.role=='PLATFORM_OWNER'
                and principal.tenant_id==tenant and inbox.merchant==merchant
                and inbox.orders.get((tenant,order_id))==binding
                and plan_finance_claim(db,order_id,tenant)==claim)
    if not unchanged():raise PermissionError('INVOICE_BINDING_CHANGED_DURING_QUERY')
    # Preserve the existing event-id collision boundary across notification and
    # query intake. A crash after this commit leaves only pending evidence, and
    # the same explicit retry can finish the match without changing order state.
    original=inbox.receive(principal,order_id,headers,raw_body)
    db.execute('BEGIN IMMEDIATE')
    try:
        if not unchanged():
            raise PermissionError('INVOICE_BINDING_CHANGED_DURING_QUERY')
        binding_hash=hashlib.sha256(canonical([expected,binding['cycle'],claim])).hexdigest()
        task_id=hashlib.sha256(canonical(['WECHAT_QUERY_MATCH',merchant['sp_mchid'],
            candidate['event_id'],candidate['body_sha256'],query['body_sha256'],binding_hash])).hexdigest()
        reason='WECHAT_QUERY_MATCH notify='+candidate['body_sha256']+' query='+query['body_sha256']+' binding='+binding_hash
        row=db.execute('SELECT tenant_id,order_id,kind,created_at,reason,state FROM saas_review_tasks WHERE task_id=?',(task_id,)).fetchone()
        if row:
            if row[:3]!=(tenant,order_id,'FINANCE_EVIDENCE') or row[4]!=reason:
                raise ValueError('RECONCILIATION_EVIDENCE_COLLISION')
            state=row[5];duplicate=True;db.commit()
        else:
            state=create_review(db,task_id,tenant,order_id,'FINANCE_EVIDENCE',now,reason)['state']
            duplicate=False
        return {'task_id':task_id,'notification_task_id':original['task_id'],
                'state':state,'duplicate':duplicate,
                'provider_observations':'SIGNED_SUCCESS_MATCH','provider_transaction_id':candidate['transaction_id'],
                'notification_sha256':candidate['body_sha256'],'query_sha256':query['body_sha256'],
                'finance_confirmation':'REQUIRED','finance_write':False,
                'payment_settled':False,'entitlement_granted':False}
    except BaseException:
        db.rollback();raise
