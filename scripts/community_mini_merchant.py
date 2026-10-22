"""Same-app merchant transport over original Center services, no new authority.

Applicant operations are owner-only. Merchant reads still require original,
live workspace grants and matching scene/store; consumers never inherit them.
"""
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_merchant_onboarding import MerchantOnboarding

APPLICANT={'catalog','mine','read','save','upload','submit','withdraw','history',
           'notices','notice_read','wechat_read','wechat_save','wechat_submit_review','wechat_media'}
WRITES={'community.profile','community.item'}
READS={'community.orders','community.summary','community.orders_page',
       'community.order_detail','community.merchant_settings','community.ads',
       'community.ads_page','community.refund_preview','community.reconciliation'}

class MiniMerchant:
    def __init__(self,identity,onboarding,operations=None,collection_codes=None):
        if (type(identity) is not CenterIdentity or type(onboarding) is not MerchantOnboarding
                or identity.center is not onboarding.center
                or operations is not None and (operations.center is not identity.center or operations.runtime is not identity.runtime)):
            raise PermissionError('ORIGINAL_MINI_MERCHANT_SERVICES_REQUIRED')
        self.identity,self.onboarding,self.operations=identity,onboarding,operations
        self.collection_codes=collection_codes
    def context(self,token,scene):
        return self.identity.merchant_context(token,scene)
    def _grant(self,token,scene,workspace):
        uid,pid,csrf,principal=self.context(token,scene)
        if self.operations is None:raise PermissionError('MERCHANT_OPERATIONS_NOT_CONFIGURED')
        from scripts.community_staff import Staff
        g=self.operations.grants.get(workspace)
        if g is None:g=Staff(self.operations).resolve(workspace,uid)
        if (g is None or g['user_id']!=uid or g['project']!=pid
                or g['role'] not in ('MERCHANT_ADMIN','STORE_STAFF')
                or g['scope']!=self.identity.runtime.bindings[principal]):
            raise PermissionError('MERCHANT_SCENE_GRANT_REQUIRED')
        return g,csrf
    def dispatch(self,token,scene,body):
        uid,pid,csrf,principal=self.context(token,scene)
        if (type(body) is not dict or set(body)!={'operation','params'}
                or type(body['operation']) is not str or type(body['params']) is not dict):
            raise ValueError('INVALID_MINI_MERCHANT_REQUEST')
        op,p=body['operation'],body['params']
        if op=='collection_code':
            if set(p)!={'workspace'} or type(p['workspace']) is not str:raise ValueError('EXACT_COLLECTION_WORKSPACE_REQUIRED')
            from scripts.community_collection_code import CollectionCodes
            if type(self.collection_codes) is not CollectionCodes or self.collection_codes.gateway.identity is not self.identity:
                raise PermissionError('OFFICIAL_COLLECTION_CODE_NOT_CONFIGURED')
            return self.collection_codes.read(token,scene,p['workspace'])
        if op=='workspaces' and p=={}:
            names=[];permissions={}
            candidates=set(self.operations.grants if self.operations is not None else {})
            if self.operations is not None:
                candidates.update(row[0] for row in self.identity.center.db.execute(
                    "SELECT subject_idx FROM links WHERE channel='COMMUNITY_STAFF_GRANT' AND user_id=? AND active=1",(uid,)))
            for name in sorted(candidates):
                try:
                    grant,_=self._grant(token,scene,name)
                    self.operations.dispatch(token,csrf,{'workspace':name,'operation':'community.summary','params':{}})
                except PermissionError:continue
                names.append(name);permissions[name]={'profile_edit':grant['role']=='MERCHANT_ADMIN'}
            return {'workspaces':names,'permissions':permissions}
        if op=='onboarding':
            if set(p)!={'operation','params'} or type(p['operation']) is not str or p['operation'] not in APPLICANT:
                raise PermissionError('APPLICANT_OPERATION_REQUIRED')
            return self.onboarding.dispatch(token,csrf,p)
        if op in ('read','write'):
            if set(p)!={'workspace','operation','params'} or type(p['operation']) is not str or p['operation'] not in (READS if op=='read' else WRITES) or type(p['workspace']) is not str:
                raise PermissionError('MERCHANT_READ_OPERATION_REQUIRED')
            grant,csrf=self._grant(token,scene,p['workspace'])
            if op=='write' and grant['role']!='MERCHANT_ADMIN':raise PermissionError('MERCHANT_ADMIN_REQUIRED')
            return self.operations.dispatch(token,csrf,p)
        raise PermissionError('MINI_MERCHANT_OPERATION_DENIED')
