"""Resolve role applicability from trusted host policy and existing DB facts.

An applicability plan is not proof of artifact readback or backup recovery.
Host-supplied policies are not accepted from an MCP or handoff request body.
"""
import copy, hashlib, json, re, sqlite3

ARTIFACT_CATEGORIES=frozenset(('SOURCE','ARTIFACT','CONTEXT','INSTALL','CONFIG_REFERENCE','AUTH_ENTRY'))
COMMON_CATEGORIES=frozenset(('ARTIFACT','CONTEXT','CONFIG_REFERENCE','AUTH_ENTRY'))
OPTIONAL_CATEGORIES=ARTIFACT_CATEGORIES-COMMON_CATEGORIES
COMMON_CHECKS=frozenset(('ORIGIN_SCOPE','DIRTY_SCOPE','AUTH_ENTRY','PERMISSION_SCOPE','CREDENTIAL_REFERENCE','CREDENTIAL_RECOVERY','CONFIG_REFERENCE','RESTORE','ACCEPTANCE','EFFECTS','WRITER_CUSTODY','ARTIFACT'))
ROLE_CHECKS={'SOURCE':frozenset(('SOURCE',)),'INSTALL':frozenset(('INSTALLED_VERSION','INSTALL_ENTRY'))}
ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}$')
HEX=re.compile(r'^[0-9a-f]{64}$')
FIELDS={'contract_id','contract_version','tenant_id','project_id','task_id','attempt_id','task_spec_sha256','role_id','role_version','role_scope','provider_id','required_categories','not_applicable'}

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')

def validate(value):
    if not isinstance(value,dict) or set(value)!=FIELDS:raise ValueError('TASK_CONTRACT_INVALID')
    if any(not isinstance(value[k],str) or not ID.fullmatch(value[k]) for k in ('contract_id','tenant_id','project_id','task_id','attempt_id','role_id','role_version','provider_id')):raise ValueError('TASK_CONTRACT_INVALID')
    if type(value['contract_version']) is not int or value['contract_version']<1 or not isinstance(value['task_spec_sha256'],str) or not HEX.fullmatch(value['task_spec_sha256']):raise ValueError('TASK_CONTRACT_INVALID')
    scope=value['role_scope'];required=value['required_categories'];na=value['not_applicable']
    if (not isinstance(scope,list) or not scope or any(not isinstance(x,str) or not ID.fullmatch(x) for x in scope) or scope!=sorted(set(scope)) or
        not isinstance(required,list) or any(not isinstance(x,str) or x not in ARTIFACT_CATEGORIES for x in required) or required!=sorted(set(required)) or
        not COMMON_CATEGORIES.issubset(required) or not isinstance(na,dict) or set(na)!=OPTIONAL_CATEGORIES-set(required) or
        any((k=='SOURCE' and v!='NON_SOURCE_WORK_PRODUCT') or (k=='INSTALL' and v!='NO_INSTALLATION_SCOPE') for k,v in na.items())):raise ValueError('TASK_CONTRACT_INVALID')
    return value

class RoleContractResolver:
    """Read trusted host contracts; require actual current assignment and scope."""
    def __init__(self,db,contracts):
        if not isinstance(contracts,(list,tuple)):raise ValueError('TRUSTED_CONTRACTS_REQUIRED')
        self.db=db;self.contracts=tuple(copy.deepcopy(validate(c)) for c in contracts)
        keys=[tuple(c[k] for k in ('tenant_id','task_id','attempt_id','provider_id')) for c in self.contracts]
        if len(set(keys))!=len(keys):raise ValueError('TASK_CONTRACT_AMBIGUOUS')
    def resolve(self,tenant_id,task_id,attempt_id,provider_id):
        matches=[c for c in self.contracts if all(c[k]==v for k,v in zip(('tenant_id','task_id','attempt_id','provider_id'),(tenant_id,task_id,attempt_id,provider_id)))]
        if len(matches)!=1:raise ValueError('TASK_CONTRACT_UNKNOWN')
        c=matches[0]
        try:
            rows=self.db.execute('''SELECT t.attempt_id,t.spec_sha256,m.tenant_id,m.project_id,
                a.role_id,a.role_version,a.provider_id,a.state,r.capabilities_json,r.enabled
              FROM tasks t JOIN gateway_task_metadata m ON m.task_id=t.task_id
              JOIN model_assignments a ON a.tenant_id=m.tenant_id AND a.task_id=t.task_id AND a.attempt_id=t.attempt_id
              JOIN role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
              WHERE t.task_id=? AND m.tenant_id=? AND a.provider_id=?''',(task_id,tenant_id,provider_id)).fetchall()
            if len(rows)!=1:raise ValueError('TASK_CONTRACT_UNKNOWN')
            attempt,spec,tenant,project,role,version,provider,state,scope,enabled=tuple(rows[0]);scope=json.loads(scope)
        except (sqlite3.Error,TypeError,ValueError):raise ValueError('TASK_CONTRACT_UNKNOWN')
        if (attempt!=attempt_id or spec!=c['task_spec_sha256'] or tenant!=tenant_id or project!=c['project_id'] or role!=c['role_id'] or
            version!=c['role_version'] or provider!=provider_id or state!='ASSIGNED' or enabled!=1 or scope!=c['role_scope']):raise ValueError('TASK_CONTRACT_UNKNOWN')
        checks=set(COMMON_CHECKS)
        for category in c['required_categories']:checks.update(ROLE_CHECKS.get(category,()))
        return {'contract_id':c['contract_id'],'contract_version':c['contract_version'],'contract_sha256':hashlib.sha256(canonical(c)).hexdigest(),
                'role_id':role,'role_version':version,'role_scope':copy.deepcopy(scope),'provider_id':provider,
                'required_categories':list(c['required_categories']),'not_applicable':dict(c['not_applicable']),'required_checks':sorted(checks)}
