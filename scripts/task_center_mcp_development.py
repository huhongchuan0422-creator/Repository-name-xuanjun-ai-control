"""Original controlled development workflow, explicit host integration only.

No synthetic GitHub event, key generation, shell tool, task/DB creation, or model
call. A host supplies original registered bindings and existing custody adapters.
"""
import copy
import hashlib
import json
import re
from model_orchestration import ModelControl
from task_supervisor import canonical
from task_writer_fence import Fence
from local_development_executor import LocalDevelopmentExecutor
from entry_review_gate import complete_reviewed_candidate,finalize_reviewed_candidate
from development_entry_intake import _controlled_candidate_files, validate_event

ACTIONS={'task_development_apply':'EXECUTOR','task_development_review':'REVIEWER',
         'task_development_finalize':'ACCEPTOR','task_development_status':None}
EXTRA={'task_development_apply':('request_id',),
       'task_development_review':('candidate_event_id','reviewed_event_id','reviews'),
       'task_development_finalize':('reviewed_event_id','completion_event_id'),
       'task_development_status':()}

def tools():
    out=[]
    for name,extra in EXTRA.items():
        p={k:{'type':'string','minLength':1,'maxLength':200} for k in ('task_id','attempt_id')+extra}
        if 'reviews' in p:p['reviews']={'type':'array','maxItems':2,'items':{'type':'object'}}
        out.append({'name':name,'description':'Original host-bound development workflow; signed reviews required; LOCAL_ONLY runtime execution remains HOLD.',
            'inputSchema':{'type':'object','properties':p,'required':list(p),'additionalProperties':False}})
    return out

class DevelopmentHost:
    """Factory injection by original host, not an MCP-supplied authority object.

    writer_context_provider(task,attempt) must return an EXISTING verified
    {ticket,caller,lock_root}; review_keys_provider(task,key_ids) supplies existing keys.
    None is permitted and fails closed only the dependent operation.
    """
    def __init__(self,bindings,review_keys_provider=None,writer_context_provider=None,contract_provider=None,execution_provider=None,native_source_provider=None,native_executor=None):
        if not isinstance(bindings,list) or len(bindings)>128:raise ValueError('BOUNDED_DEVELOPMENT_BINDINGS_REQUIRED')
        required={'tenant_id','principal_id','project_id','task_id','spec_sha256','checkpoint_sha256','contract_sha256',
                  'role_id','role_version','phase','review_kind','authority_identity','actions','candidate_root','executor_profile'}
        seen=set()
        for b in bindings:
            if not isinstance(b,dict) or set(b)!=required:raise ValueError('EXACT_DEVELOPMENT_HOST_BINDING_REQUIRED')
            for k in ('tenant_id','principal_id','project_id','task_id','role_id','role_version'):
                if not isinstance(b[k],str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',b[k]):raise ValueError('EXACT_HOST_ID_REQUIRED')
            for k in ('spec_sha256','checkpoint_sha256','contract_sha256'):
                if not isinstance(b[k],str) or not re.fullmatch('[0-9a-f]{64}',b[k]):raise ValueError('PINNED_DEVELOPMENT_SCOPE_REQUIRED')
            if (b['phase'] not in ('EXECUTOR','REVIEWER','ACCEPTOR') or b['review_kind'] not in (None,'QA','SECURITY')
                or (b['phase']=='REVIEWER')!=(b['review_kind'] is not None)
                or not isinstance(b['authority_identity'],dict) or set(b['authority_identity'])!={'issuer','subject'}
                or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',v) for v in b['authority_identity'].values())
                or not isinstance(b['actions'],list) or not b['actions'] or any(not isinstance(x,str) for x in b['actions']) or len(set(b['actions']))!=len(b['actions'])
                or any(x not in ACTIONS or ACTIONS[x] not in (None,b['phase']) for x in b['actions'])):
                raise ValueError('EXACT_DEVELOPMENT_HOST_ROLE_REQUIRED')
            if b['candidate_root'] is not None and not isinstance(b['candidate_root'],str):raise ValueError('HOST_CANDIDATE_ROOT_REQUIRED')
            if b['executor_profile'] is not None:
                profile=b['executor_profile']
                expected={'project_id','role_id','role_version','principal_id','repository','branch','repository_root','resource_key','allowed_file','max_source_bytes'}
                if (not isinstance(profile,dict) or set(profile) not in (expected, expected | {'producer_snapshot_sha256'}) or b['phase']!='EXECUTOR'
                    or any(profile[k]!=b[k] for k in ('project_id','role_id','role_version','principal_id'))):
                    raise ValueError('HOST_EXECUTOR_PROFILE_REQUIRED')
            key=tuple(b[k] for k in ('tenant_id','principal_id','project_id','task_id'))
            if key in seen:raise ValueError('DUPLICATE_DEVELOPMENT_HOST_BINDING')
            seen.add(key)
        for fn in (review_keys_provider,writer_context_provider,contract_provider,execution_provider,native_source_provider):
            if fn is not None and not callable(fn):raise ValueError('TRUSTED_HOST_PROVIDER_REQUIRED')
        self.bindings=copy.deepcopy(bindings);self.review_keys_provider=review_keys_provider;self.writer_context_provider=writer_context_provider;self.contract_provider=contract_provider;self.execution_provider=execution_provider
        self.native_source_provider=native_source_provider
        from native_development_executor import NativeDevelopmentExecutor
        if native_executor is not None and not isinstance(native_executor,NativeDevelopmentExecutor):
            raise ValueError('TRUSTED_NATIVE_EXECUTOR_REQUIRED')
        self.native_executor=native_executor
    def register_contract(self,control,task_id):
        """Admit only an existing host-custodied contract pinned by bindings."""
        if self.contract_provider is None:raise ValueError('HOLD_TRUSTED_DEVELOPMENT_CONTRACT_UNAVAILABLE')
        control._admin()
        control.gateway.assert_task_context(control.context,task_id)
        contract=self.pinned_contract(task_id,control.tenant_id,
            lambda project:control._assert_expected_project(task_id,project))
        return control.gateway.supervisor.register_development_contract(task_id,contract)

    def pinned_contract(self,task_id,tenant_id,assert_project):
        """Shared content validation, not authentication or registration."""
        if self.contract_provider is None:raise ValueError('HOLD_TRUSTED_DEVELOPMENT_CONTRACT_UNAVAILABLE')
        contract=self.contract_provider(task_id)
        from task_supervisor import Supervisor
        Supervisor._development_contract_shape(contract)
        rows=[b for b in self.bindings if b['tenant_id']==tenant_id and b['task_id']==task_id]
        if not rows:raise ValueError('DEVELOPMENT_HOST_ACTION_REQUIRED')
        sha=hashlib.sha256(canonical(contract).encode()).hexdigest()
        if any(b['contract_sha256']!=sha or b['spec_sha256']!=contract['spec_sha256'] or b['checkpoint_sha256']!=contract['checkpoint_sha256'] for b in rows):
            raise ValueError('CURRENT_PINNED_DEVELOPMENT_SCOPE_REQUIRED')
        for b in rows:assert_project(b['project_id'])
        executors=[b for b in rows if b['phase']=='EXECUTOR']
        reviewers=[b for b in rows if b['phase']=='REVIEWER']
        from entry_review_gate import identity
        developer=identity(contract['developer'])
        policies=contract['trusted_reviewers']
        identities=[identity(p,True) for p in policies]
        if (len(executors)!=1 or executors[0]['authority_identity']!=contract['developer'] or
            len(reviewers)!=2 or set(p['role'] for p in policies)!={'QA','SECURITY'} or
            len(set(identities))!=2 or developer in identities or
            len(set(p['key_id'] for p in policies))!=2 or
            any(not any(b['review_kind']==p['role'] and b['authority_identity']=={'issuer':p['issuer'],'subject':p['subject']} for b in reviewers) for p in policies)):
            raise ValueError('CANONICAL_DEVELOPMENT_IDENTITY_REQUIRED')
        profile=executors[0]['executor_profile']
        if profile is None:
            # Native apply already consumes the host's exact source provider;
            # registering its pinned contract must not require a local writer.
            if self.native_source_provider is None:
                raise ValueError('HOST_EXECUTOR_PROFILE_REQUIRED')
        elif profile['repository']!=contract['target_repository'] or contract['allowed_files']!=[profile['allowed_file']]:
            raise ValueError('HOST_EXECUTOR_PROFILE_REQUIRED')
        return contract

    def visible(self,identity):
        allowed=set()
        for b in self.bindings:
            if all(b[k]==identity.get(k) for k in ('tenant_id','principal_id','project_id')):allowed.update(b['actions'])
        return [t for t in tools() if t['name'] in allowed]
    def rpc(self,service,identity,value):
        if not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or value.get('method')!='tools/call':raise ValueError('EXACT_DEVELOPMENT_RPC_REQUIRED')
        p=value.get('params')
        if not isinstance(p,dict) or set(p)!={'name','arguments'} or p['name'] not in ACTIONS:raise ValueError('EXACT_DEVELOPMENT_RPC_REQUIRED')
        name=p['name'];a=p['arguments']
        if not isinstance(a,dict) or set(a)!=set(('task_id','attempt_id')+EXTRA[name]):raise ValueError('EXACT_DEVELOPMENT_ARGUMENTS_REQUIRED')
        if len(json.dumps(a).encode())>65536:raise ValueError('BOUNDED_DEVELOPMENT_ARGUMENTS_REQUIRED')
        for k,v in a.items():
            if k!='reviews' and (not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}',v)):raise ValueError('EXACT_DEVELOPMENT_EVENT_ID_REQUIRED')
        b=next((x for x in self.bindings if x['task_id']==a['task_id'] and all(x[k]==identity.get(k) for k in ('tenant_id','principal_id','project_id'))),None)
        if b is None or name not in b['actions']:raise ValueError('DEVELOPMENT_HOST_ACTION_REQUIRED')
        scope='task:read' if name=='task_development_status' else 'task:submit'
        if scope not in identity.get('scopes',[]):raise ValueError('DEVELOPMENT_OAUTH_SCOPE_REQUIRED')
        if any(getattr(service,k)!=identity[k] for k in ('tenant_id','principal_id','project_id')):raise ValueError('DEVELOPMENT_OAUTH_IDENTITY_MISMATCH')
        s,g,_,_=service._open()
        try:
            c=ModelControl(g,g.tenants.issue(service.tenant_id,identity['principal_id']),service.master_key)
            plan=self.native_executor.plan if self.native_executor is not None else None
            def check(audit=False):
                g.assert_task_context(c.context,a['task_id']);c._assert_expected_project(a['task_id'],b['project_id'])
                task=s._task(a['task_id']);contract=s.development_contract(a['task_id'])
                if (task['attempt_id']!=a['attempt_id'] or task['spec_sha256']!=b['spec_sha256'] or task['checkpoint_sha256']!=b['checkpoint_sha256']
                    or hashlib.sha256(canonical(contract).encode()).hexdigest()!=b['contract_sha256']):raise ValueError('CURRENT_PINNED_DEVELOPMENT_SCOPE_REQUIRED')
                row=s.db.execute('''SELECT r.phase,r.review_kind,r.enabled,a.principal_id,a.role_version,r.writer_allowed FROM model_assignments a JOIN role_templates r
                    ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
                    WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.role_id=? AND a.state='ASSIGNED' ''',
                    (service.tenant_id,a['task_id'],a['attempt_id'],b['role_id'])).fetchone()
                if row is None or tuple(row)!=(b['phase'],b['review_kind'],1,b['principal_id'],b['role_version'],1 if b['phase']=='EXECUTOR' else 0):raise ValueError('CURRENT_DEVELOPMENT_ROLE_REQUIRED')
                who=b['authority_identity'];reviewers=[{k:r[k] for k in ('issuer','subject')} for r in contract['trusted_reviewers']]
                if ((b['phase']=='EXECUTOR' and who!=contract['developer']) or
                    (b['phase']=='REVIEWER' and not any(all(r[k]==who[k] for k in who) and r['role']==b['review_kind'] for r in contract['trusted_reviewers'])) or
                    (b['phase']=='ACCEPTOR' and (who==contract['developer'] or who in reviewers))):raise ValueError('CANONICAL_DEVELOPMENT_IDENTITY_REQUIRED')
                if audit and s.db.in_transaction:c._audit(b['principal_id'],'AUTHENTICATED_MCP_DEVELOPMENT',a['task_id'],
                    {'source_kind':'AUTHENTICATED_MCP','action':name,'attempt_id':a['attempt_id']},s.clock())
                if name!='task_development_status' and service.write_admission is not None:
                    service.write_admission()
                return task,contract
            task,contract=check()
            if name=='task_development_apply' and b['executor_profile'] is None:
                # Reuse apply for host-supplied native source; no regeneration.
                if self.native_source_provider is None:
                    raise ValueError('HOLD_TRUSTED_NATIVE_SOURCE_UNAVAILABLE')
                source=self.native_source_provider(a['task_id'],a['attempt_id'],a['request_id'])
                if (not isinstance(source,dict) or set(source)!=
                        {'event','control_repository','trusted_owner','destination'}):
                    raise ValueError('EXACT_HOST_NATIVE_SOURCE_REQUIRED')
                if (not isinstance(source['destination'],dict)
                        or source['destination'].get('task_id')!=a['task_id']):
                    raise ValueError('HOST_NATIVE_DESTINATION_MISMATCH')
                receipt=validate_event(source['event'],source['control_repository'],
                                       source['trusted_owner'],source['destination'])
                if receipt['event']!='CODE_READY':
                    raise ValueError('NATIVE_CODE_READY_REQUIRED')
                receipt['execution_required']=True
                files=_controlled_candidate_files(s,receipt,b['candidate_root'])
                result=s._bind_development_candidate(receipt,
                    {path:hashlib.sha256(raw).hexdigest() for path,raw in files.items()},
                    admission_check=lambda:check(True))
                result.update(execution_state='HOLD_TRUSTED_NATIVE_EXECUTION_UNAVAILABLE',
                    generated_code_executed=False,source_kind='AUTHENTICATED_NATIVE_IMPORT',
                    next_action='RUN_SAME_COMMIT_WITH_ORIGINAL_TRUSTED_EXECUTOR')
                if self.native_executor is not None:
                    execution=self.native_executor.run(s,result['candidate'],files,lambda:check(True))
                    result.update(execution_state='TRUSTED_NATIVE_TESTS_PASSED',
                        execution_receipt=execution,generated_code_executed=True,
                        next_action='INDEPENDENT_SIGNED_REVIEW')
            elif name=='task_development_apply':
                if self.writer_context_provider is None:raise ValueError('HOLD_EXISTING_WRITER_CONTEXT_UNAVAILABLE')
                profile=b['executor_profile']
                if profile is None or any(profile[k]!=b[k] for k in ('project_id','role_id','role_version','principal_id')):raise ValueError('HOST_EXECUTOR_PROFILE_REQUIRED')
                context=self.writer_context_provider(a['task_id'],a['attempt_id'])
                if (not isinstance(context,dict) or set(context)!={'ticket','caller','lock_root'}
                    or not isinstance(context['lock_root'],str) or not context['lock_root'].startswith('/')):raise ValueError('EXISTING_WRITER_CONTEXT_REQUIRED')
                fence=Fence(s,context['lock_root'])
                try:result=LocalDevelopmentExecutor(c,fence,profile,admission_check=lambda:check(True),execution_provider=self.execution_provider).apply_proposal(
                    a['task_id'],a['attempt_id'],a['request_id'],context['ticket'],context['caller'])
                finally:fence.close()
            elif name=='task_development_review':
                candidate=s.development_candidate(a['task_id'],a['candidate_event_id'])
                s._require_development_execution_ready(candidate,plan)
                if self.review_keys_provider is None:raise ValueError('HOLD_TRUSTED_REVIEW_KEYS_UNAVAILABLE')
                keys=self.review_keys_provider(a['task_id'],tuple(x['key_id'] for x in contract['trusted_reviewers']))
                files=_controlled_candidate_files(s,{'task_id':a['task_id'],'target_repository':contract['target_repository'],'code_commit':candidate['code_commit']},b['candidate_root'])
                result=complete_reviewed_candidate(s,a['task_id'],a['candidate_event_id'],files,a['reviews'],keys,a['reviewed_event_id'],admission_check=lambda:check(True),native_test_plan_sha256=plan)
            elif name=='task_development_finalize':
                result=finalize_reviewed_candidate(s,a['task_id'],a['reviewed_event_id'],a['completion_event_id'],admission_check=lambda:check(True),native_test_plan_sha256=plan)
            else:
                candidates=list(s.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND kind='DEVELOPMENT_CANDIDATE'",(a['task_id'],a['attempt_id'])))
                local=any(json.loads(x[0]).get('source_kind')=='LOCAL_ONLY_CONFIRMED_OPERATION' for x in candidates)
                result={'task_id':a['task_id'],'attempt_id':a['attempt_id'],'canonical_task_state':task['state'],'authority_state':task['authority_state'],
                    'execution_state':'HOLD_SANDBOX_UNAVAILABLE' if local else 'REFER_TO_CANONICAL_SIGNED_REVIEW',
                    'source_kind':'AUTHENTICATED_MCP','observation_only':True}
            return {'jsonrpc':'2.0','id':value.get('id'),'result':{'content':[{'type':'text','text':json.dumps(result,sort_keys=True)}],'isError':False}}
        finally:s.close()


def _read_host_json(path,code):
    from secure_file_input import read_owned_secret_file
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('DUPLICATE_DEVELOPMENT_CONFIG_KEY')
            out[k]=v
        return out
    try:return json.loads(read_owned_secret_file(path,code),object_pairs_hook=unique)
    except (OSError,ValueError,TypeError):raise ValueError(code+'_UNAVAILABLE_OR_INVALID') from None


def load_host(path, *, execution_provider=None,native_executor=None,db_path=None):
    """Read-only original-host custody references; never generates/saves keys.

    Files are owned0600 regular single-link and bounded by secure_file_input.
    The host must supply already-authorized custody material; this loader is
    not a producer of authority and does not copy canonical Writer fields.
    execution_provider is an already-constructed trusted host instance, not config.
    """
    cfg=_read_host_json(path,'DEVELOPMENT_HOST_CONFIG')
    required={'schema_version','enabled','bindings','review_keyring_file','writer_context_file'}
    if (not isinstance(cfg,dict) or not required.issubset(cfg) or set(cfg)-required-{'native_source_file','claim_registration','contract_file','native_sandbox'}
            or type(cfg['schema_version']) is not int or cfg['schema_version']!=1 or type(cfg['enabled']) is not bool):
        raise ValueError('EXACT_DEVELOPMENT_HOST_CONFIG_REQUIRED')
    for k in ('review_keyring_file','writer_context_file','native_source_file','contract_file'):
        if cfg.get(k) is not None and (not isinstance(cfg[k],str) or not cfg[k].startswith('/')):
            raise ValueError('EXISTING_PROTECTED_HOST_REFERENCE_REQUIRED')
    registration=cfg.get('claim_registration')
    if registration is not None:
        if (not isinstance(registration,dict) or set(registration)!={'owner_public_key_file','custody_file'}
                or any(not isinstance(v,str) or not v.startswith('/') for v in registration.values())):
            raise ValueError('EXISTING_CLAIM_REGISTRATION_REFERENCES_REQUIRED')
    sandbox=cfg.get('native_sandbox')
    if sandbox is not None:
        if (not isinstance(sandbox,dict) or set(sandbox)!={'repository_root','base_commit','test_plan_sha256'}
                or not isinstance(sandbox['repository_root'],str) or not sandbox['repository_root'].startswith('/')
                or not isinstance(sandbox['base_commit'],str) or re.fullmatch('[0-9a-f]{40}',sandbox['base_commit']) is None
                or not isinstance(sandbox['test_plan_sha256'],str) or re.fullmatch('[0-9a-f]{64}',sandbox['test_plan_sha256']) is None):
            raise ValueError('FIXED_NATIVE_SANDBOX_REFERENCES_REQUIRED')
    if not cfg['enabled']:
        if cfg['bindings'] or cfg['review_keyring_file'] is not None or cfg['writer_context_file'] is not None or cfg.get('native_source_file') is not None or cfg.get('contract_file') is not None or registration is not None or sandbox is not None:
            raise ValueError('DISABLED_DEVELOPMENT_CONFIG_MUST_BE_EMPTY')
        return None
    if sandbox is not None:
        if native_executor is not None:raise ValueError('ONE_TRUSTED_NATIVE_EXECUTOR_REQUIRED')
        from native_sandbox_runner import BubblewrapNativeRunner
        from native_development_executor import NativeDevelopmentExecutor
        runner=BubblewrapNativeRunner(db_path,sandbox['repository_root'],sandbox['base_commit'],sandbox['test_plan_sha256'])
        native_executor=NativeDevelopmentExecutor(runner,runner.plan)
    def keys(task,ids):
        raw=_read_host_json(cfg['review_keyring_file'],'TRUSTED_REVIEW_KEYRING')
        if not isinstance(raw,dict) or any(k not in raw or not isinstance(raw[k],str) or not re.fullmatch('[0-9a-f]{64,256}',raw[k]) or len(raw[k])%2 for k in ids):
            raise ValueError('EXISTING_REVIEW_KEYS_REQUIRED')
        return {k:bytes.fromhex(raw[k]) for k in ids}
    def writer(task,attempt):
        raw=_read_host_json(cfg['writer_context_file'],'EXISTING_WRITER_CUSTODY')
        value=raw.get(task) if isinstance(raw,dict) else None
        if not isinstance(value,dict) or set(value)!={'attempt_id','ticket','caller','lock_root'} or value['attempt_id']!=attempt:
            raise ValueError('EXISTING_EXACT_WRITER_CONTEXT_REQUIRED')
        return {k:value[k] for k in ('ticket','caller','lock_root')}
    def contract(task):
        raw=_read_host_json(cfg['contract_file'],'TRUSTED_DEVELOPMENT_CONTRACT')
        if not isinstance(raw,dict) or task not in raw:raise ValueError('HOLD_TRUSTED_DEVELOPMENT_CONTRACT_UNAVAILABLE')
        return raw[task]
    def native_source(task,attempt,request):
        raw=_read_host_json(cfg['native_source_file'],'TRUSTED_NATIVE_SOURCE')
        try:value=raw[task][attempt][request]
        except (KeyError,TypeError):
            raise ValueError('HOLD_TRUSTED_NATIVE_SOURCE_UNAVAILABLE') from None
        return value
    host=DevelopmentHost(cfg['bindings'],keys if cfg['review_keyring_file'] else None,
                            writer if cfg['writer_context_file'] else None,
                            contract_provider=contract if cfg.get('contract_file') else None,
                            execution_provider=execution_provider,
                            native_source_provider=native_source if cfg.get('native_source_file') else None,native_executor=native_executor)
    if registration is not None:
        from task_center_mcp_claim import load_claim_host
        host.claim_host=load_claim_host(host,registration['owner_public_key_file'],registration['custody_file'])
    return host
