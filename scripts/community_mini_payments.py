"""Explicitly configured Mini consumer prepay/recovery/signed query composition.

No Finance ledger or simulated SUCCESS mutation. Every call reuses original
Mini identity and original customer-order ownership, including after network IO.
"""
import hashlib
import json
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_wechat_sp_prepay import PartnerPrepay
from scripts.community_order_store import state


class MiniPayments:
    def __init__(self,identity,prepay,merchants=None):
        if type(identity) is not CenterIdentity or type(prepay) is not PartnerPrepay or identity.center is not prepay.center:
            raise ValueError('SAME_ORIGINAL_CENTER_REQUIRED')
        self.identity,self.prepay=identity,prepay
        self.merchants={}
        if merchants is not None:
            if type(merchants) is not dict or not merchants or prepay.bindings:raise ValueError('ONE_PROTECTED_PAYMENT_BINDING_MODE_REQUIRED')
            for scene,record in merchants.items():
                if type(scene) is not str or scene not in identity.scenes or type(record) is not dict or set(record)!={'sp_appid','sub_mchid','description','notify_url','profit_sharing'}:
                    raise ValueError('INVALID_PROTECTED_MERCHANT_PAYMENT_BINDING')
                if record['sp_appid']!=identity.appid:raise ValueError('MINI_APPID_MISMATCH')
                # Reuse the exact provider field validator before accepting host configuration.
                PartnerPrepay(identity.center,prepay.reader,{'validation':dict(record,user_id='validation',project='validation',out_trade_no='validation',amount_minor=1,sp_openid='validation')})
                binding=identity.scenes[scene]
                self.merchants[scene]=dict(record= dict(record),project=binding['project'],scope=dict(identity.runtime.bindings[binding['principal']]))
    def _authorize(self,token,scene,reference):
        i=self.identity;c=i.center
        i.authorize_order_read(token,scene,reference,c.now())
        uid,pid,principal=i._resolve(token,scene)
        scope=i.runtime.bindings[principal]
        order=state(i.runtime.demo.db,scope,reference)
        from scripts.community_order_provider_projection import provider_evidence
        from scripts.community_order_cancellation import local_cancelled
        if order['currency']!='CNY' or order['state']!='PENDING' and provider_evidence(i.runtime.demo.db,scope,reference) is None and not (order['state']=='CANCELLED' and local_cancelled(i.runtime.demo.db,scope,reference)):
            raise PermissionError('ORIGINAL_PENDING_ORDER_BINDING_REQUIRED')
        key=c.idx('wechat-session:'+token)
        meta=c.db.execute("SELECT payload FROM links WHERE channel='WECHAT_MINI_SESSION' AND subject_idx=? AND user_id=? AND project=? AND active=1",(key,uid,pid)).fetchone()
        if meta is None:raise PermissionError('CURRENT_WECHAT_PAYER_REQUIRED')
        session=json.loads(c.decrypt(meta[0],'wechat-mini-session'))
        if self.merchants:
            from scripts.pr122_customer_core import canonical
            merchant=self.merchants.get(scene)
            if merchant is None or merchant['project']!=pid or merchant['scope']!=scope:
                raise PermissionError('PROTECTED_MERCHANT_PAYMENT_BINDING_REQUIRED')
            openid=session.get('openid')
            if type(openid) is not str or i._subject(i.appid,openid)!=session['subject_idx']:
                raise PermissionError('FRESH_VERIFIED_MINI_LOGIN_REQUIRED')
            from scripts.community_provider_reference import provider_order_reference
            b=dict(merchant['record'],user_id=uid,project=pid,out_trade_no=provider_order_reference(self.prepay.reader._mchid,scope,reference),amount_minor=order['amount_minor'],sp_openid=openid)
        else:
            b=self.prepay.bindings.get(reference)
        if b is None or b['user_id']!=uid or b['project']!=pid or b['sp_appid']!=i.appid or order['amount_minor']!=b['amount_minor']:
            raise PermissionError('PROTECTED_PAYMENT_BINDING_REQUIRED')
        if session['subject_idx']!=i._subject(b['sp_appid'],b['sp_openid']):
            raise PermissionError('CURRENT_WECHAT_PAYER_REQUIRED')
        return dict(b)
    def dispatch(self,token,body):
        if (type(body) is not dict or set(body)!={'scene','operation','reference'}
                or any(type(body[k]) is not str for k in body)
                or body['operation'] not in ('prepare','recover','query','cancel')):
            raise ValueError('INVALID_MINI_PAYMENT_REQUEST')
        scene,reference=body['scene'],body['reference']
        b=self._authorize(token,scene,reference)
        authorize=lambda:self._authorize(token,scene,reference)
        c=self.identity.center
        with c.tx():c.limit('community-payment:'+b['user_id'],20,60)
        if body['operation']=='query':
            from scripts.community_order_cancellation import local_cancelled
            _,_,principal=self.identity._resolve(token,scene)
            if local_cancelled(self.identity.runtime.demo.db,self.identity.runtime.bindings[principal],reference):
                return dict(reference=reference,provider_state='NOT_CREATED',order_state='CANCELLED',amount_minor=b['amount_minor'],currency='CNY',provider_signature_verified=False,provider_settlement_verified=False,finance_status='UNCONFIRMED',financial_receipt_issued=False,entitlement_granted=False)
        if body['operation']=='cancel':
            from scripts.community_order_cancellation import OrderCancellation
            return OrderCancellation(self).cancel(token,scene,reference)
        if body['operation'] in ('prepare','recover'):
            _,_,principal=self.identity._resolve(token,scene)
            if state(self.identity.runtime.demo.db,self.identity.runtime.bindings[principal],reference)['state']!='PENDING':raise PermissionError('PAYMENT_ALREADY_TERMINAL_QUERY_ONLY')
        if body['operation']=='prepare':
            from scripts.pr122_customer_core import canonical
            _,_,principal=self.identity._resolve(token,scene)
            original_scope=self.identity.runtime.bindings[principal]
            if b['profit_sharing']:
                actions=getattr(self,'rule_actions',None)
                if actions is None:raise PermissionError('PROFIT_SHARING_RULE_SERVICE_REQUIRED')
                policy=actions.bindings.get(tuple(original_scope[k] for k in ('tenant_id','merchant_id','store_id')))
                grants=[g for g in actions.operations.grants.values() if g['project']==b['project'] and g['scope']==original_scope and g['role'] in ('PLATFORM_OWNER','FINANCE_APPROVER')]
                if policy is None or not grants or actions.reader._mchid!=self.prepay.reader._mchid or policy['sub_mchid']!=b['sub_mchid'] or policy['sp_appid']!=b['sp_appid']:
                    raise PermissionError('SAME_ADMITTED_SPLIT_POLICY_REQUIRED')
                from scripts.community_split_rules import SplitRules
                with c.tx():SplitRules(actions).freeze_original(grants[0],policy,reference)
            expected=dict(sp_mchid=self.prepay.reader._mchid,sp_appid=b['sp_appid'],sub_mchid=b['sub_mchid'],out_trade_no=b['out_trade_no'],amount_minor=b['amount_minor'],currency='CNY')
            callback_key=c.idx('community-payment-notify:'+self.prepay.reader._mchid+':'+b['out_trade_no'])
            callback_binding=dict(user_id=b['user_id'],project=b['project'],scope=original_scope,reference=reference,expected=expected)
            with c.tx():
                old=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PAYMENT_BINDING' AND subject_idx=? AND active=1",(callback_key,)).fetchone()
                if old:
                    if json.loads(c.decrypt(old[0],'community-payment-binding:'+callback_key))!=callback_binding:raise PermissionError('PAYMENT_CALLBACK_BINDING_COLLISION')
                else:c.db.execute("INSERT INTO links VALUES('COMMUNITY_PAYMENT_BINDING',?,?,?,?,1)",(callback_key,b['user_id'],b['project'],c.encrypt(canonical(callback_binding),'community-payment-binding:'+callback_key)))
            result=self.prepay._create_authorized(b,authorize)
        elif body['operation']=='recover':
            result=self.prepay._existing_authorized(b,authorize)
        else:
            reader=self.prepay.reader
            expected=dict(sp_mchid=reader._mchid,**{k:b[k] for k in ('sub_mchid','sp_appid','out_trade_no','amount_minor')},currency='CNY')
            result=reader.read_order(expected)
            if authorize()!=b:raise PermissionError('PAYMENT_BINDING_CHANGED')
            from scripts.community_order_provider_projection import project_verified_query
            _,_,principal=self.identity._resolve(token,scene)
            project_verified_query(self.identity.runtime.demo.db,self.identity.runtime.bindings[principal],reference,expected,result,c.now(),reader._kid)
            with c.tx():c.audit(b['project'],b['user_id'],'COMMUNITY_PAYMENT_QUERIED',hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest())
            # A signed SUCCESS observation is not authoritative Finance settlement.
            result=dict(reference=reference,provider_state=result['provider_state'],amount_minor=b['amount_minor'],currency='CNY',
                        provider_signature_verified=True,provider_settlement_verified=False,finance_status='UNCONFIRMED',
                        financial_receipt_issued=False,entitlement_granted=False)
        return result
