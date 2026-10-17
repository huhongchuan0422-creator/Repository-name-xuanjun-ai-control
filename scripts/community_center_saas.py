"""Original Center customer sessions and ownership for existing SaaS stores.

No new IAM/order/Finance tables. Ownership links remain in the Center backup
and encryption domain. Prepared orders do not confirm payment or grant rights.
"""
import hashlib
import json
import re
import secrets
from scripts.pr122_customer_core import Center,canonical
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_phase2 import Principal


class CenterSaas:
    def __init__(self,center,runtime,grants):
        if type(center) is not Center or type(runtime) is not StageRuntime or type(grants) is not dict or not grants:
            raise ValueError('EXISTING_CENTER_RUNTIME_AND_CUSTOMER_GRANTS_REQUIRED')
        self.center,self.runtime=center,runtime;self.grants={}
        for name,g in grants.items():
            if (type(name) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',name)
                    or type(g) is not dict or set(g)!={'user_id','project','principal'}
                    or any(type(g[k]) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',g[k]) for k in ('user_id','project'))):
                raise ValueError('INVALID_PROTECTED_SAAS_GRANT')
            p=g['principal']
            if type(p) is not Principal or p.role not in ('CUSTOMER','PLATFORM_OWNER') or p not in runtime.bindings:
                raise PermissionError('REGISTERED_CUSTOMER_REQUIRED')
            self.grants[name]=dict(g,role=p.role,tenant=p.tenant_id,scope=dict(runtime.bindings[p]))
    def _authorize(self,session,csrf,workspace):
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        c=self.center;uid=c.session(session,csrf)
        g=self.grants.get(workspace)
        if g is None or g['user_id']!=uid:raise PermissionError('CUSTOMER_WORKSPACE_REQUIRED')
        p=g['principal']
        if p.role!=g['role'] or p.tenant_id!=g['tenant'] or p not in self.runtime.bindings or self.runtime.bindings[p]!=g['scope']:
            raise PermissionError('CUSTOMER_GRANT_CHANGED')
        project,_,_=c.project(uid,g['project'],('OWNER',) if g['role']=='PLATFORM_OWNER' else ('OWNER','EDITOR'))
        if project['tenant']!=g['tenant']:raise PermissionError('PROJECT_TENANT_MISMATCH')
        return g
    def _owned(self,g,kind,reference):
        if type(reference) is not str or not re.fullmatch(('sq_' if kind=='QUOTE' else 'so_')+'[0-9a-f]{32}',reference):
            raise PermissionError('OWNED_REFERENCE_REQUIRED')
        row=self.center.db.execute('SELECT user_id,project,payload FROM links WHERE channel=? AND subject_idx=? AND active=1',('COMMUNITY_SAAS_'+kind,reference)).fetchone()
        if row is None or row['user_id']!=g['user_id'] or row['project']!=g['project']:raise PermissionError('SAAS_CUSTOMER_OWNERSHIP_REQUIRED')
        data=json.loads(self.center.decrypt(row['payload'],'community-saas:'+reference))
        if data['tenant_id']!=g['tenant']:raise PermissionError('SAAS_TENANT_MISMATCH')
        return data
    def _reserve(self,g,kind,reference,data):
        c=self.center
        with c.tx():
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',('COMMUNITY_SAAS_'+kind,reference,g['user_id'],g['project'],c.encrypt(canonical(dict(data,tenant_id=g['tenant'])),'community-saas:'+reference)))
            c.audit(g['project'],g['user_id'],'SAAS_'+kind+'_RESERVED',reference)
    def _fulfillment_view(self,g,order_id):
        key=hashlib.sha256(canonical([g['tenant'],order_id])).hexdigest()
        row=self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_SAAS_FULFILLMENT' AND subject_idx=? AND active=1",(key,)).fetchone()
        if row is None:return None
        saved=json.loads(self.center.decrypt(row[0],'saas-fulfillment:'+key))
        order=self.runtime.saas.dispatch(g['principal'],'order_read',{'order_id':order_id},self.center.now())
        if saved['binding']['tenant']!=g['tenant'] or saved['binding']['order_id']!=order_id or saved['binding']['module']!=order['module_id'] or saved['binding']['quote_sha256']!=order['quote_sha256']:
            raise PermissionError('FULFILLMENT_ORDER_BINDING_MISMATCH')
        from scripts.community_saas_modules import entitled
        return dict(state=saved['state'],entitlement_issued_for_order=saved['state']=='COMPLETED',
                    module_currently_active=entitled(self.runtime.saas.modules,g['tenant'],order['module_id'],self.center.now()),
                    valid_from=saved['start'],valid_until=saved['until'])

    def dispatch(self,session,csrf,body):
        if type(body) is not dict or set(body)!={'workspace','operation','params'} or type(body['workspace']) is not str or type(body['operation']) is not str or type(body['params']) is not dict:
            raise ValueError('INVALID_CUSTOMER_SAAS_REQUEST')
        fields={'owner_offer_read':{'offer_id','version'},'workspace_info':set(),'owner_create_offer':{'offer_id','version','module_id','kind','lines','term_days','tenant_scope','supplier_payment'},'owner_approve_offer':{'offer_id','version','approval_ref','cost_evidence_ref'},'catalog':set(),'offers':{'module_id'},'quote':{'offer_id','version'},'quote_read':{'quote_id'},
                'order_prepare':{'quote_id','currency'},'order_read':{'order_id'},'order_status':{'order_id'},
                'renewal_plan':{'order_id'},'entitlement':{'module_id'},'capability':{'capability'},
                'mine':{'kind','after_id'}}
        from scripts.community_center_saas_admin import FIELDS as ADMIN_FIELDS
        fields.update(ADMIN_FIELDS)
        op,p=body['operation'],body['params']
        if op not in fields or set(p)!=fields[op]:raise ValueError('INVALID_CUSTOMER_SAAS_FIELDS')
        g=self._authorize(session,csrf,body['workspace']);c=self.center;now=c.now()
        with c.tx():
            c.limit('community-saas:'+g['user_id'],60,60)
            c.audit(g['project'],g['user_id'],'SAAS_CUSTOMER_ATTEMPT',hashlib.sha256(canonical(body)).hexdigest())
        def call(operation,params):return self.runtime.dispatch(g['principal'],operation,params,None)
        if op in ADMIN_FIELDS:
            from scripts.community_center_saas_admin import dispatch as admin_dispatch
            result=admin_dispatch(self,g,op,p)
        elif op=='workspace_info':result=dict(role=g['role'],pricing_allowed=g['role']=='PLATFORM_OWNER')
        elif op in ('owner_offer_read','owner_create_offer','owner_approve_offer'):
            if g['role']!='PLATFORM_OWNER':raise PermissionError('ORIGINAL_PLATFORM_OWNER_REQUIRED')
            if op=='owner_offer_read':
                if type(p['version']) is not int or p['version']<1:raise ValueError('INVALID_OFFER_VERSION')
                from scripts.community_saas_offer_catalog import get_offer
                result=get_offer(self.runtime.saas.quotes,p['offer_id'],p['version'])
            else:result=call(op,p)
        elif op=='mine':
            kind=p['kind'];after=p['after_id']
            if type(kind) is not str or kind not in ('QUOTE','ORDER') or type(after) is not str or after and not re.fullmatch(('sq_' if kind=='QUOTE' else 'so_')+'[0-9a-f]{32}',after):raise ValueError('INVALID_SAAS_PAGE')
            rows=c.db.execute('SELECT subject_idx FROM links WHERE channel=? AND user_id=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',('COMMUNITY_SAAS_'+kind,g['user_id'],g['project'],after)).fetchall()
            result=dict(records=[dict(reference=r[0],**self._owned(g,kind,r[0])) for r in rows[:50]],has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None)
        elif op=='quote':
            qid='sq_'+secrets.token_hex(16)
            self._reserve(g,'QUOTE',qid,dict(quote_id=qid,offer_id=p['offer_id'],version=p['version'],created_at=now))
            result=call('quote',dict(p,quote_id=qid,expires_at=now+1800))
        elif op=='quote_read':
            self._owned(g,'QUOTE',p['quote_id']);result=dict(call(op,p),quote_id=p['quote_id'])
        elif op=='order_prepare':
            self._owned(g,'QUOTE',p['quote_id'])
            if p['currency'] not in ('CNY','USD'):raise ValueError('INVALID_CURRENCY')
            oid='so_'+hashlib.sha256(canonical([g['tenant'],p['quote_id'],p['currency']])).hexdigest()[:32]
            old=c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_SAAS_ORDER' AND subject_idx=?",(oid,)).fetchone()
            if old:
                self._owned(g,'ORDER',oid);result=call('order_read',dict(order_id=oid))
            else:
                self._reserve(g,'ORDER',oid,dict(order_id=oid,quote_id=p['quote_id'],currency=p['currency'],created_at=now))
                result=call(op,dict(p,order_id=oid))
        elif op=='renewal_plan':
            self._owned(g,'ORDER',p['order_id'])
            lifecycle=call('order_status',dict(order_id=p['order_id']))
            fulfillment=self._fulfillment_view(g,p['order_id'])
            if fulfillment and fulfillment['state'] in ('REVERSAL_RESERVED','REVERSED'):
                result=dict(order_id=p['order_id'],status=fulfillment['state'],entitlement_granted=False,automatic_renewal_authorized=False)
            elif lifecycle['state']=='CONFIRMED_EXTERNAL':
                order=call('order_read',dict(order_id=p['order_id']))
                row=self.runtime.saas.modules.execute('SELECT valid_until FROM module_entitlements WHERE tenant_id=? AND module_id=?',(g['tenant'],order['module_id'])).fetchone()
                result=call(op,dict(p,valid_until=row[0] if row else None))
            else:result=dict(order_id=p['order_id'],status='AWAITING_FINANCE_CONFIRMATION',payment_confirmed_by_adapter=False,entitlement_granted=False,automatic_renewal_authorized=False)
        elif op in ('order_read','order_status'):
            self._owned(g,'ORDER',p['order_id']);result=call(op,p)
            fulfillment=self._fulfillment_view(g,p['order_id'])
            if fulfillment is not None:result=dict(result,fulfillment=fulfillment)
        else:result=call(op,p)
        self._authorize(session,csrf,body['workspace'])
        with c.tx():c.audit(g['project'],g['user_id'],'SAAS_CUSTOMER_COMPLETED',hashlib.sha256(canonical(body)).hexdigest())
        return result
