"""Bind signed WeChat evidence to original frozen SaaS claims and review tasks.

This is the missing evidence intake seam, not a second Finance ledger. It uses
only original saas_review_tasks; no money state, entitlement or provider call is
changed. Existing Finance must independently reconcile and authorize settlement.
"""
import hashlib
import re
from scripts.community_saas_phase2 import Principal
from scripts.community_saas_offline_handoff import plan_finance_claim,create_review,canonical
from scripts.community_wechat_sp_verification import notification_candidate
from scripts.community_stage_runtime import StageRuntime

class SaasProviderEvidence:
    def __init__(self,runtime,merchant,orders,public_key_pem,public_key_id,api_v3_key):
        if type(runtime) is not StageRuntime:raise ValueError('EXISTING_STAGE_RUNTIME_REQUIRED')
        fields={'sp_mchid','sub_mchid','sp_appid'}
        if (type(merchant) is not dict or set(merchant)!=fields
                or any(type(merchant[k]) is not str or not re.fullmatch('[0-9]{6,32}',merchant[k]) for k in ('sp_mchid','sub_mchid'))
                or type(merchant['sp_appid']) is not str or not re.fullmatch('wx[0-9a-fA-F]{16}',merchant['sp_appid'])):
            raise ValueError('TRUSTED_MERCHANT_BINDING_REQUIRED')
        if type(orders) is not dict or not orders:raise ValueError('SERVER_INVOICE_BINDINGS_REQUIRED')
        self.runtime,self.merchant=runtime,dict(merchant)
        self.orders={}
        provider_refs=set()
        for identity,binding in orders.items():
            if (type(identity) is not tuple or len(identity)!=2 or any(type(v) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',v) for v in identity)
                    or type(binding) is not dict or set(binding)!={'out_trade_no','cycle'}
                    or type(binding['out_trade_no']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,32}',binding['out_trade_no'])
                    or type(binding['cycle']) is not str or binding['out_trade_no'] in provider_refs):
                raise ValueError('INVALID_OR_REUSED_PROVIDER_ORDER_BINDING')
            claim=plan_finance_claim(runtime.saas.orders,identity[1],identity[0])
            if claim['currency']!='CNY' or binding['cycle'] not in claim['amounts_by_cycle_minor']:
                raise ValueError('UNSUPPORTED_INVOICE_CURRENCY_OR_CYCLE')
            amount=claim['amounts_by_cycle_minor'][binding['cycle']]
            if type(amount) is not int or not 1<=amount<=100000000:
                raise ValueError('UNSUPPORTED_PROVIDER_AMOUNT')
            provider_refs.add(binding['out_trade_no']);self.orders[identity]=dict(binding)
        self._public,self._kid,self._api=public_key_pem,public_key_id,api_v3_key

    def receive(self,principal,order_id,headers,raw_body):
        """Protected operator intake; not reachable from customer API dispatch."""
        if (type(principal) is not Principal or principal not in self.runtime.bindings
                or principal.role!='PLATFORM_OWNER'):
            raise PermissionError('REGISTERED_OWNER_REQUIRED')
        tenant=principal.tenant_id
        binding=self.orders.get((tenant,order_id))
        if binding is None:raise PermissionError('INVOICE_BINDING_REQUIRED')
        db=self.runtime.saas.orders
        if db.in_transaction:raise ValueError('EXTERNAL_TRANSACTION_DENIED')
        now=self.runtime.clock()
        if type(now) is not int or now<0:raise ValueError('TRUSTED_CLOCK_REQUIRED')
        # Lock before reading the frozen claim and checking duplicate task state.
        db.execute('BEGIN IMMEDIATE')
        try:
            claim=plan_finance_claim(db,order_id,tenant)
            if claim['currency']!='CNY':raise ValueError('CNY_INVOICE_REQUIRED')
            expected=dict(self.merchant,out_trade_no=binding['out_trade_no'],
                          amount_minor=claim['amounts_by_cycle_minor'][binding['cycle']],currency='CNY')
            candidate=notification_candidate(headers,raw_body,self._public,self._kid,self._api,expected,now)
            task_id=hashlib.sha256(canonical([self.merchant['sp_mchid'],candidate['event_id']])).hexdigest()
            claim_hash=hashlib.sha256(canonical(claim)).hexdigest()
            bound_hash=hashlib.sha256(canonical([expected,binding['cycle']])).hexdigest()
            reason='WECHAT_CANDIDATE body='+candidate['body_sha256']+' claim='+claim_hash+' binding='+bound_hash
            existing=db.execute('SELECT tenant_id,order_id,kind,created_at,reason,state FROM saas_review_tasks WHERE task_id=?',(task_id,)).fetchone()
            if existing:
                if existing[:3]!=(tenant,order_id,'FINANCE_EVIDENCE') or existing[4]!=reason:
                    raise ValueError('PROVIDER_EVENT_COLLISION')
                db.commit();state=existing[5];duplicate=True
            else:
                result=create_review(db,task_id,tenant,order_id,'FINANCE_EVIDENCE',now,reason)
                # create_review owns the same original DB transaction and commit.
                state=result['state'];duplicate=False
            return {'task_id':task_id,'state':state,'duplicate':duplicate,
                    'evidence_body_sha256':candidate['body_sha256'],'quote_sha256':claim['quote_sha256'],
                    'invoice_cycle':binding['cycle'],'provider_transaction_id':candidate['transaction_id'],
                    'reconciliation':'REQUIRED','finance_write':False,'entitlement_granted':False,
                    'payment_settled':False}
        except BaseException:
            db.rollback()
            raise
