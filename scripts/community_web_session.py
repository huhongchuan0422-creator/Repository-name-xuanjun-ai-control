"""HTTPS cookie transport for this community's existing Center staff accounts.

No registration, account mapping, grant creation or alternate identity store.
Consumers retain the original WeChat registration/login path.
"""
import hashlib
import re
from pathlib import Path
from scripts.pr122_customer_core import Center

COOKIE='__Host-xj_customer'
PIN='cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0'

def token(headers):
    if (len(headers.get_all('Cookie',[]))>1 or
        any(headers.get_all(k,[]) for k in ('X-Center-Session','X-Community-Session','Authorization'))):
        raise PermissionError('COOKIE_SESSION_REQUIRED')
    values=[p.strip().partition('=')[2] for p in headers.get('Cookie','').split(';')
            if p.strip().partition('=')[0]==COOKIE]
    if len(values)!=1 or not re.fullmatch('[A-Za-z0-9_-]{32,128}',values[0]):
        raise PermissionError('COOKIE_SESSION_REQUIRED')
    return values[0]

class WebSession:
    def __init__(self,center,operations=None,communities=None,onboarding=None,*,provider_actions=None,merchant_bills=None):
        if type(center) is not Center or hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest()!=PIN:
            raise PermissionError('PINNED_ORIGINAL_CENTER_REQUIRED')
        self.center=center
        self.operations,self.communities,self.onboarding=operations,communities,onboarding
        if any(service is not None and service.center is not center for service in (operations,communities,onboarding)):
            raise PermissionError("SAME_CENTER_REQUIRED")
        self.provider_actions,self.merchant_bills=provider_actions,merchant_bills
        if provider_actions is not None:
            from scripts.community_wechat_sp_actions import ProviderActions
            if type(provider_actions) is not ProviderActions or provider_actions.center is not center or provider_actions.operations is not operations:
                raise ValueError('SAME_ORIGINAL_PROVIDER_ACTIONS_REQUIRED')
        if merchant_bills is not None:
            from scripts.community_merchant_bills import MerchantBills
            if type(merchant_bills) is not MerchantBills or merchant_bills.center is not center or merchant_bills.actions is not provider_actions:
                raise ValueError('SAME_ORIGINAL_MERCHANT_BILLS_REQUIRED')
    def finance_options(self,session,csrf,selected):
        # Read authorization only; never dispatch provider/bill operations here.
        options={'provider':[],'merchant_bill':[]}
        def matches(grant):
            return all(grant[k]==selected[k] for k in ('user_id','project','tenant','scope'))
        if self.provider_actions is not None:
            for workspace in sorted(self.operations.grants):
                try:grant,_=self.provider_actions._authorize(session,csrf,workspace)
                except PermissionError:continue
                if matches(grant):options['provider'].append({'workspace':workspace})
        if self.merchant_bills is not None:
            for workspace in sorted(self.merchant_bills.grants):
                try:context=self.merchant_bills._context(session,csrf,workspace)
                except PermissionError:continue
                if matches(context['anchor']):options['merchant_bill'].append({'workspace':workspace})
        return options
    def dispatch(self,path,headers,body,source):
        if type(body) is not dict:raise ValueError('EXACT_SESSION_BODY_REQUIRED')
        if path=='/community/session/login':
            if set(body)!={'email','password'} or type(body['password']) is not str or not 1<=len(body['password'])<=1024:
                raise ValueError('EXISTING_ACCOUNT_CREDENTIALS_REQUIRED')
            if type(source) is not str or not 1<=len(source)<=128:raise PermissionError('TRUSTED_SOURCE_REQUIRED')
            with self.center.tx():self.center.limit('community-web-source:'+self.center.idx(source),40,300)
            result=self.center.login(body['email'],body['password'])
            cookie=COOKIE+'='+result['token']+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600'
            return {'csrf':result['csrf'],'user_id':result['user_id']},cookie
        if body!={}:raise ValueError('EMPTY_SESSION_BODY_REQUIRED')
        session=token(headers)
        values=headers.get_all('X-CSRF-Token',[])
        if len(values)!=1 or not values[0]:raise PermissionError('CSRF_REQUIRED')
        uid=self.center.session(session,values[0])
        if path=='/community/session/check':
            # This list is navigation only; every original business dispatch
            # still rechecks live project, role, principal and store bindings.
            workspaces=[]
            if self.operations is not None:
                for name,grant in self.operations.grants.items():
                    if grant['user_id']!=uid:continue
                    try:
                        project,_,_=self.center.project(uid,grant['project'],grant['project_roles'])
                        principal=grant['principal']
                        if project['tenant']!=grant['tenant'] or principal not in self.operations.runtime.bindings or self.operations.runtime.bindings[principal]!=grant['scope']:continue
                        if grant['onboarding_required']:
                            from scripts.community_merchant_opening import authorize_workspace
                            authorize_workspace(self.onboarding,self.operations,name,uid)
                    except PermissionError:continue
                    workspaces.append({'kind':'MERCHANT','workspace':name,'finance_options':self.finance_options(session,values[0],grant)})
            if self.communities is not None:
                for name in self.communities.grants:
                    try:grant=self.communities.authorize(session,values[0],name)
                    except PermissionError:continue
                    role=grant.get('role')
                    if role not in ('CUSTOMER','COMMUNITY_ADMIN','MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER'):continue
                    workspaces.append({'kind':'COMMUNITY','workspace':name,'role':role})
            reviewer=False
            if self.onboarding is not None:
                try:self.onboarding._reviewer(uid);reviewer=True
                except PermissionError:pass
            return {'user_id':uid,'workspaces':workspaces,'reviewer':reviewer},None
        if path!='/community/session/logout':raise ValueError('UNKNOWN_SESSION_ACTION')
        self.center.logout(session)
        return {'logged_out':True},COOKIE+'=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0'
