"""Existing Center sessions authorize registered community operation grants.

Grants are protected host configuration referencing original account/project
IDs, not another IAM database. No project member automatically becomes staff,
merchant administrator, moderator or platform owner. No money API is added.
"""
import hashlib
import re
from pathlib import Path
from scripts.pr122_customer_core import Center,canonical
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_phase2 import Principal


class CenterOperations:
    def __init__(self,center,runtime,grants,*,onboarding=None):
        if (type(center) is not Center or type(runtime) is not StageRuntime
                or type(grants) is not dict or not grants):
            raise ValueError('EXISTING_CENTER_AND_REGISTERED_GRANTS_REQUIRED')
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest()!=\
                'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0':
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        self.center,self.runtime=center,runtime
        self.onboarding=onboarding
        if onboarding is not None:
            from scripts.community_merchant_onboarding import MerchantOnboarding
            if type(onboarding) is not MerchantOnboarding or onboarding.center is not center:
                raise ValueError('SAME_CENTER_ONBOARDING_REQUIRED')
        self.grants={}
        for name,grant in grants.items():
            if (type(name) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',name)
                    or type(grant) is not dict or set(grant) not in (
                        {'user_id','project','project_roles','principal'},
                        {'user_id','project','project_roles','principal','onboarding_required'})
                    or any(type(grant[k]) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',grant[k]) for k in ('user_id','project'))
                    or type(grant['project_roles']) not in (list,tuple) or not grant['project_roles']
                    or any(r not in ('OWNER','EDITOR','REVIEWER') for r in grant['project_roles'])):
                raise ValueError('INVALID_PROTECTED_OPERATION_GRANT')
            p=grant['principal']
            if (type(p) is not Principal or p not in runtime.bindings or p.role not in
                    ('MERCHANT_ADMIN','STORE_STAFF','PLATFORM_REVIEWER','FINANCE_APPROVER','PLATFORM_OWNER')):
                raise PermissionError('REGISTERED_OPERATOR_REQUIRED')
            required=grant.get('onboarding_required',False)
            if type(required) is not bool or required and (onboarding is None or p.role!='MERCHANT_ADMIN'):
                raise ValueError('PROTECTED_MERCHANT_ONBOARDING_GATE_REQUIRED')
            self.grants[name]={**grant,'project_roles':tuple(grant['project_roles']),
                'onboarding_required':required,'role':p.role,'tenant':p.tenant_id,'scope':dict(runtime.bindings[p])}

    def dispatch(self,session,csrf,body):
        if (type(body) is not dict or set(body)!={'workspace','operation','params'}
                or type(body['workspace']) is not str or type(body['operation']) is not str
                or type(body['params']) is not dict):
            raise ValueError('INVALID_OPERATION_FIELDS')
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf)
        from scripts.community_staff import Staff
        if body['operation'] in ('community.stores','community.store_save'):
            from scripts.community_stores import Stores
            return Stores(self).dispatch(session,csrf,body['workspace'],body['operation'],body['params'])
        if body['operation'].startswith('community.staff_'):
            return Staff(self).dispatch(session,csrf,body['workspace'],body['operation'],body['params'])
        grant=self.grants.get(body['workspace'])
        if grant is None:grant=Staff(self).resolve(body['workspace'],uid)
        if grant is None or grant['user_id']!=uid:raise PermissionError('OPERATION_GRANT_REQUIRED')
        if 'allowed_operations' in grant and body['operation'] not in grant['allowed_operations']:
            raise PermissionError('STAFF_OPERATION_DENIED')
        p=grant['principal']
        if (p not in self.runtime.bindings or p.role!=grant['role'] or p.tenant_id!=grant['tenant']
                or self.runtime.bindings[p]!=grant['scope']):
            raise PermissionError('OPERATION_GRANT_CHANGED')
        project,_,_=c.project(uid,grant['project'],grant['project_roles'])
        if project['tenant']!=grant['tenant']:raise PermissionError('PROJECT_TENANT_MISMATCH')
        if grant['onboarding_required']:
            from scripts.community_merchant_opening import authorize_workspace
            authorize_workspace(self.onboarding,self,body['workspace'],uid)
        # This seam only exposes the existing community workbench operations.
        # SaaS and Finance administration retain their original owner boundary.
        if not body['operation'].startswith('community.'):
            raise PermissionError('COMMUNITY_OPERATION_REQUIRED')
        request_hash=hashlib.sha256(canonical(body)).hexdigest()
        with c.tx():
            c.limit('community-operations:'+uid,60,60)
            c.audit(grant['project'],uid,'COMMUNITY_OPERATION_ATTEMPT',request_hash)
        if body['operation'] in ('community.profile','community.item','community.ad_create','community.ad_state','community.ad_review'):
            from scripts.community_registered_admin import dispatch
            result=dispatch(self.runtime.demo,grant['scope'],grant['role'],uid,body['operation'],body['params'],self.center.now())
        else:result=self.runtime.dispatch(p,body['operation'],body['params'],None)
        # Separate original databases are not an atomic transaction. An audit
        # failure after the business operation is UNKNOWN, never auto-retried.
        with c.tx():
            c.audit(grant['project'],uid,'COMMUNITY_OPERATION_COMPLETED',request_hash)
        return result
