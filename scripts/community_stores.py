"""Multi-store business records reuse protected original CRM store bindings."""
from scripts.community_admin_route_gate import community_project, resolve_admin_workspace, admin_workspace_catalog
from scripts.community_merchant_contract import scope
from scripts.community_merchant_store import upsert_profile


class Stores:
    def __init__(self,operations):self.operations=operations;self.center=operations.center
    def dispatch(self,session,csrf,workspace,op,p):
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf);g=resolve_admin_workspace(c,self.operations.grants,workspace,uid)
        if g is None or g['user_id']!=uid or g['role']!='MERCHANT_ADMIN':raise PermissionError('ORIGINAL_MERCHANT_ADMIN_REQUIRED')
        principal=g['principal']
        if principal.tenant_id!=g['tenant'] or principal.role!=g['role'] or self.operations.runtime.bindings.get(principal)!=g['scope']:raise PermissionError('MERCHANT_GRANT_CHANGED')
        project,_,_=community_project(c,uid,g['project'],g['project_roles'])
        if project['tenant']!=g['tenant']:raise PermissionError('MERCHANT_TENANT_DENIED')
        if g['onboarding_required']:
            from scripts.community_merchant_opening import authorize_workspace
            authorize_workspace(self.operations.onboarding,self.operations,workspace,uid)
        fields={'community.stores':set(),'community.store_save':{'store_workspace','record','expected_version'}}
        if op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_STORE_OPERATION')
        admitted={name:target for name,target in admin_workspace_catalog(c,self.operations.grants).items() if target['user_id']==uid and target['project']==g['project'] and target['role']=='MERCHANT_ADMIN' and target['scope']['tenant_id']==g['scope']['tenant_id'] and target['scope']['merchant_id']==g['scope']['merchant_id']}
        def authorize_target(name,target):
            principal=target['principal']
            if principal.role!=target['role'] or principal.tenant_id!=target['tenant'] or self.operations.runtime.bindings.get(principal)!=target['scope']:
                raise PermissionError('ORIGINAL_CRM_ADMITTED_STORE_REQUIRED')
            project,_,_=community_project(c,uid,target['project'],target['project_roles'])
            if project['tenant']!=target['tenant']:
                raise PermissionError('MERCHANT_TENANT_DENIED')
            if target['onboarding_required']:
                from scripts.community_merchant_opening import authorize_workspace
                authorize_workspace(self.operations.onboarding,self.operations,name,uid)
        db=self.operations.runtime.demo.merchant_db
        with c.tx():c.limit('community-stores:'+uid,30,60)
        if op=='community.stores':
            records=[]
            for name,target in sorted(admitted.items()):
                try:authorize_target(name,target)
                except PermissionError:continue
                row=db.execute('SELECT name,description,contact,status,version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',scope(target['scope'])).fetchone()
                records.append(dict(workspace=name,store_id=target['scope']['store_id'],profile=None if row is None else dict(zip(('name','description','contact','status','version'),row))))
            return dict(stores=records)
        target=admitted.get(p['store_workspace']) if type(p['store_workspace']) is str else None
        if target is None:raise PermissionError('ORIGINAL_CRM_ADMITTED_STORE_REQUIRED')
        # The entry workspace is not authority over another store's live role
        # requirement. In particular an EDITOR grant cannot borrow OWNER access.
        authorize_target(p['store_workspace'],target)
        # Creating a business profile does not mint a tenant, merchant, Principal,
        # contract or payment identity. Those stay with original CRM admission.
        actor=dict(authenticated=True,role='MERCHANT_ADMIN',**target['scope'])
        result=upsert_profile(db,target['scope'],actor,p['record'],p['expected_version'])
        with c.tx():c.audit(g['project'],uid,'COMMUNITY_STORE_SAVED',target['scope']['store_id'])
        return dict(result,workspace=p['store_workspace'],store_id=target['scope']['store_id'])
