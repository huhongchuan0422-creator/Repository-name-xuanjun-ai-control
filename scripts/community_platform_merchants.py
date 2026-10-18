"""Platform merchant lifecycle over original CRM workspaces and Center audit.

Suspension blocks new purchases and prepay, while queries, cancellation and
refund recovery remain available. It never changes WeChat admission status.
"""
import hashlib
import json
from scripts.pr122_customer_core import canonical

CHANNEL='COMMUNITY_MERCHANT_LIFECYCLE'

def merchant_key(identity):return hashlib.sha256(canonical(identity)).hexdigest()

def assert_trading(center,identity):
    key=merchant_key(identity)
    for raw, in center.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND active=1',(CHANNEL,key)):
        value=json.loads(center.decrypt(raw,'community-merchant-lifecycle:'+key))
        if value['scope']!=identity or value['status']!='ACTIVE':raise PermissionError('PLATFORM_MERCHANT_TRADING_SUSPENDED')

class PlatformMerchants:
    module=dict(id='XJ-PLATFORM-MERCHANT-001',version='1.0.0',author='玄钧AI实验室',dependencies=['original-center','community-commerce'],description='Scoped merchant lifecycle and operations overview')
    def __init__(self,directory):self.directory=directory;self.center=directory.center;self.operations=directory.commerce.operations
    def _targets(self,g,unavailable=None):
        targets={}
        for name,target in sorted(self.operations.grants.items()):
            principal=target['principal']
            if target['project']!=g['project'] or target['tenant']!=g['tenant'] or target['role']!='MERCHANT_ADMIN':continue
            try:
                if principal.role!=target['role'] or principal.tenant_id!=g['tenant'] or self.operations.runtime.bindings.get(principal)!=target['scope']:raise PermissionError('ORIGINAL_MERCHANT_MAPPING_CHANGED')
                self.center.project(target['user_id'],target['project'],target['project_roles'])
            except PermissionError:
                if unavailable is None:raise
                # Only identify the already configured project workspace. Never
                # return its inaccessible user's profile, scope or order data.
                unavailable.append(dict(workspace=name,status='UNAVAILABLE'))
                continue
            targets[name]=target
        return targets
    def _read(self,g,identity):
        key=merchant_key(identity)
        row=self.center.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',(CHANNEL,key,g['project'])).fetchone()
        if row is None:return dict(scope=identity,status='ACTIVE',version=0,reason='',source='ORIGINAL_ADMISSION_DEFAULT')
        value=json.loads(self.center.decrypt(row[0],'community-merchant-lifecycle:'+key))
        if value['scope']!=identity:raise PermissionError('MERCHANT_LIFECYCLE_BINDING_CHANGED')
        return value
    def dispatch(self,session,csrf,body):
        op,p=body['operation'],body['params']
        fields={'platform_merchants':{'after_workspace'},'platform_merchant_state':{'merchant_workspace','status','expected_version','reason'}}
        if op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_PLATFORM_MERCHANT_FIELDS')
        g=self.directory.authorize(session,csrf,body['workspace']);c=self.center
        if g['role'] not in ('PLATFORM_OWNER','PLATFORM_REVIEWER'):raise PermissionError('PLATFORM_MERCHANT_OPERATOR_REQUIRED')
        unavailable=[]
        targets=self._targets(g,unavailable)
        with c.tx():
            c.limit('community-platform-merchants:'+g['user_id'],30,60)
            if op=='platform_merchants':
                if type(p['after_workspace']) is not str or len(p['after_workspace'])>64:raise ValueError('INVALID_MERCHANT_CURSOR')
                unavailable_by_name={item['workspace']:item for item in unavailable}
                names=[name for name in sorted(set(targets)|set(unavailable_by_name)) if name>p['after_workspace']][:51];records=[]
                for name in names[:50]:
                    if name not in targets:continue
                    target=targets[name];identity=target['scope'];t,m,s=(identity[k] for k in ('tenant_id','merchant_id','store_id'))
                    profile=self.operations.runtime.demo.merchant_db.execute('SELECT name,status FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s)).fetchone()
                    counts=dict(self.operations.runtime.demo.db.execute('SELECT state,COUNT(*) FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? GROUP BY state',(t,m,s)))
                    records.append(dict(workspace=name,scope=identity,name=profile[0] if profile else '',store_status=profile[1] if profile else 'NOT_CREATED',lifecycle=self._read(g,identity),order_counts=counts,finance_status='UNCONFIRMED'))
                return dict(records=records,has_more=len(names)>50,next_cursor=names[49] if len(names)>50 else None,
                    coverage='ORIGINAL_PROJECT_ADMITTED_MERCHANTS',coverage_complete=not unavailable,
                    unavailable_mapping_count=len(unavailable),
                    unavailable_mappings=[unavailable_by_name[name] for name in names[:50] if name in unavailable_by_name])
            if g['role']!='PLATFORM_OWNER':raise PermissionError('PLATFORM_OWNER_REQUIRED_FOR_MERCHANT_STATE')
            target=targets.get(p['merchant_workspace']) if type(p['merchant_workspace']) is str else None
            if target is None:raise PermissionError('ORIGINAL_PROJECT_MERCHANT_REQUIRED')
            if p['status'] not in ('ACTIVE','PAUSED','DISABLED') or type(p['reason']) is not str or not 1<=len(p['reason'].strip())<=1000:raise ValueError('INVALID_MERCHANT_STATUS_OR_REASON')
            old=self._read(g,target['scope'])
            if type(p['expected_version']) is not int or p['expected_version']!=old['version']:raise ValueError('MERCHANT_STATE_VERSION_CONFLICT')
            value=dict(scope=target['scope'],status=p['status'],reason=p['reason'].strip(),version=old['version']+1,updated_at=c.now(),actor=g['user_id'])
            key=merchant_key(target['scope']);payload=c.encrypt(canonical(value),'community-merchant-lifecycle:'+key)
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload',(CHANNEL,key,target['user_id'],g['project'],payload))
            event=hashlib.sha256(canonical([key,value])).hexdigest()
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_MERCHANT_LIFECYCLE_HISTORY',?,?,?,?,1)",(event,g['user_id'],g['project'],c.encrypt(canonical(value),'community-merchant-lifecycle-history:'+event)))
            c.audit(g['project'],g['user_id'],'PLATFORM_MERCHANT_'+p['status'],key)
            return value
