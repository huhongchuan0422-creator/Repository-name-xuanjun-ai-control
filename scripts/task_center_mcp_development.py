"""Original controlled development workflow, explicit host integration only.

No synthetic GitHub event, key generation, shell tool, task/DB creation, or model
call. A host supplies original registered bindings and existing custody adapters.
"""
import copy
import hashlib
import hmac
import json
import re
from model_orchestration import ModelControl
from task_supervisor import canonical
from task_writer_fence import Fence
from local_development_executor import LocalDevelopmentExecutor
from entry_review_gate import complete_reviewed_candidate,finalize_reviewed_candidate
from development_entry_intake import _controlled_candidate_files

ACTIONS={'task_development_gateway_candidate':'EXECUTOR','task_development_gateway_test_event':'EXECUTOR','task_development_gateway_readback':'EXECUTOR','task_development_gateway':'EXECUTOR','task_development_continue_review':'EXECUTOR','task_development_verify_tests':'EXECUTOR','task_development_apply':'EXECUTOR','task_development_review':'REVIEWER',
         'task_development_finalize':'ACCEPTOR','task_development_status':None}
EXTRA={'task_development_gateway_candidate':('request_id',),'task_development_gateway_test_event':('candidate_event_id','run_id'),'task_development_gateway_readback':('request_id',),'task_development_gateway':('request_id',),'task_development_continue_review':('ci_event_id',),'task_development_verify_tests':('candidate_event_id','run_id'),'task_development_apply':('request_id',),
       'task_development_review':('candidate_event_id','reviewed_event_id','reviews'),
       'task_development_finalize':('reviewed_event_id','completion_event_id'),
       'task_development_status':()}

def tools():
    out=[]
    for name,extra in EXTRA.items():
        p={k:{'type':'string','minLength':1,'maxLength':200} for k in ('task_id','attempt_id')+extra}
        if 'reviews' in p:p['reviews']={'type':'array','maxItems':2,'items':{'type':'object'}}
        out.append({'name':name,'description':'Original host-bound development workflow; signed reviews required; local execution stays HOLD unless the fixed original CI exact-tree evidence is verified.',
            'inputSchema':{'type':'object','properties':p,'required':list(p),'additionalProperties':False}})
    return out

class DevelopmentHost:
    """Factory injection by original host, not an MCP-supplied authority object.

    writer_context_provider(task,attempt) must return an EXISTING verified
    {ticket,caller,lock_root}; review_keys_provider(task,key_ids) supplies existing keys.
    None is permitted and fails closed only the dependent operation.
    """
    def __init__(self,bindings,review_keys_provider=None,writer_context_provider=None,review_continuations=None,gateway_enabled=False,tool_receipt_reader=None):
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
                if (not isinstance(profile,dict) or set(profile)!=expected or b['phase']!='EXECUTOR'
                    or any(profile[k]!=b[k] for k in ('project_id','role_id','role_version','principal_id'))):
                    raise ValueError('HOST_EXECUTOR_PROFILE_REQUIRED')
            key=tuple(b[k] for k in ('tenant_id','principal_id','project_id','task_id'))
            if key in seen:raise ValueError('DUPLICATE_DEVELOPMENT_HOST_BINDING')
            seen.add(key)
        for fn in (review_keys_provider,writer_context_provider,tool_receipt_reader):
            if fn is not None and not callable(fn):raise ValueError('TRUSTED_HOST_PROVIDER_REQUIRED')
        if review_continuations is None:review_continuations=[]
        if not isinstance(review_continuations,list) or len(review_continuations)>128:raise ValueError('BOUNDED_REVIEW_CONTINUATIONS_REQUIRED')
        continuation_keys=set()
        for row in review_continuations:
            if not isinstance(row,dict) or set(row)!={'tenant_id','principal_id','project_id','task_id','reviewers'}:raise ValueError('EXACT_REVIEW_CONTINUATION_BINDING_REQUIRED')
            if not any(all(row[k]==b[k] for k in ('tenant_id','principal_id','project_id','task_id')) and b['phase']=='EXECUTOR' for b in bindings):raise ValueError('EXISTING_HOST_EXECUTOR_REQUIRED')
            key=tuple(row[k] for k in ('tenant_id','principal_id','project_id','task_id'))
            if key in continuation_keys:raise ValueError('DUPLICATE_REVIEW_CONTINUATION_BINDING')
            continuation_keys.add(key)
        if type(gateway_enabled) is not bool:raise ValueError('EXACT_GATEWAY_ENABLE_FLAG_REQUIRED')
        self.gateway_enabled=gateway_enabled;self.tool_receipt_reader=tool_receipt_reader
        self.review_continuations=copy.deepcopy(review_continuations)
        self.bindings=copy.deepcopy(bindings);self.review_keys_provider=review_keys_provider;self.writer_context_provider=writer_context_provider
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
        scope='task:read' if name in ('task_development_status','task_development_gateway_readback') else 'task:submit'
        if scope not in identity.get('scopes',[]):raise ValueError('DEVELOPMENT_OAUTH_SCOPE_REQUIRED')
        if any(getattr(service,k)!=identity[k] for k in ('tenant_id','principal_id','project_id')):raise ValueError('DEVELOPMENT_OAUTH_IDENTITY_MISMATCH')
        s,g,_,_=service._open()
        try:
            c=ModelControl(g,g.tenants.issue(service.tenant_id,identity['principal_id']),service.master_key)
            def check(audit=False):
                g.assert_task_context(c.context,a['task_id']);c._assert_expected_project(a['task_id'],b['project_id'])
                task=s._task(a['task_id']);contract=s.development_contract(a['task_id'])
                if (task['attempt_id']!=a['attempt_id'] or task['spec_sha256']!=b['spec_sha256'] or task['checkpoint_sha256']!=b['checkpoint_sha256']
                    or hashlib.sha256(canonical(contract).encode()).hexdigest()!=b['contract_sha256']):raise ValueError('CURRENT_PINNED_DEVELOPMENT_SCOPE_REQUIRED')
                row=s.db.execute('''SELECT r.phase,r.review_kind,r.enabled,a.principal_id,a.role_version,r.writer_allowed FROM model_assignments a JOIN role_templates r
                    ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
                    WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.role_id=?''',
                    (service.tenant_id,a['task_id'],a['attempt_id'],b['role_id'])).fetchone()
                if row is None or tuple(row)!=(b['phase'],b['review_kind'],1,b['principal_id'],b['role_version'],1 if b['phase']=='EXECUTOR' else 0):raise ValueError('CURRENT_DEVELOPMENT_ROLE_REQUIRED')
                who=b['authority_identity'];reviewers=[{k:r[k] for k in ('issuer','subject')} for r in contract['trusted_reviewers']]
                if ((b['phase']=='EXECUTOR' and who!=contract['developer']) or
                    (b['phase']=='REVIEWER' and not any(all(r[k]==who[k] for k in who) and r['role']==b['review_kind'] for r in contract['trusted_reviewers'])) or
                    (b['phase']=='ACCEPTOR' and (who==contract['developer'] or who in reviewers))):raise ValueError('CANONICAL_DEVELOPMENT_IDENTITY_REQUIRED')
                if audit and s.db.in_transaction:c._audit(b['principal_id'],'AUTHENTICATED_MCP_DEVELOPMENT',a['task_id'],
                    {'source_kind':'AUTHENTICATED_MCP','action':name,'attempt_id':a['attempt_id']},s.clock())
                return task,contract
            task,contract=check()
            def continue_reviews(ci_event_id):
                config=next((r for r in self.review_continuations if all(r[k]==b[k] for k in ('tenant_id','principal_id','project_id','task_id'))),None)
                if config is None:raise ValueError('REVIEW_CONTINUATION_NOT_CONFIGURED')
                def source_reader(task_id,candidate):
                    qa=next((r for r in config['reviewers'] if r['review_kind']=='QA'),None)
                    registered=next((r for r in self.bindings if qa is not None and r['phase']=='REVIEWER' and r['review_kind']=='QA'
                        and all(r[k]==b[k] for k in ('tenant_id','project_id','task_id'))
                        and all(r[k]==qa[k] for k in ('role_id','role_version','principal_id','authority_identity'))),None)
                    if registered is None:raise ValueError('EXISTING_REVIEW_SOURCE_BINDING_REQUIRED')
                    return _controlled_candidate_files(s,{'task_id':task_id,'target_repository':candidate['target_repository'],'code_commit':candidate['code_commit']},registered['candidate_root'])
                from development_review_continuation import DevelopmentReviewContinuation
                continuation=DevelopmentReviewContinuation(c,b['project_id'],config['reviewers'],source_reader,lambda:check(True))
                return continuation.continue_from_ci(a['task_id'],a['attempt_id'],ci_event_id)
            if name=='task_development_gateway_candidate':
                from gateway_multifile_candidate import bind_candidate
                if self.writer_context_provider is None:raise ValueError('HOLD_EXISTING_WRITER_CONTEXT_UNAVAILABLE')
                context=self.writer_context_provider(a['task_id'],a['attempt_id'])
                if not isinstance(context,dict) or set(context)!={'ticket','caller','lock_root'}:raise ValueError('EXISTING_WRITER_CONTEXT_REQUIRED')
                opid='gateway-source-'+hashlib.sha256((a['task_id']+'\0'+a['attempt_id']+'\0'+a['request_id']).encode()).hexdigest()
                fence=Fence(s,context['lock_root'])
                try:result=bind_candidate(s,a['task_id'],a['attempt_id'],opid,context['ticket'],context['caller'],fence.locks.provider_id,lambda:check(True))
                finally:fence.close()
            elif name=='task_development_gateway_test_event':
                from gateway_multifile_candidate import record_test_event
                result=record_test_event(s,a['task_id'],a['candidate_event_id'],a['run_id'],self.tool_receipt_reader,lambda:check(True))
                if any(all(r[k]==b[k] for k in ('tenant_id','principal_id','project_id','task_id')) for r in self.review_continuations):
                    result['review_continuation']=continue_reviews(result['event_id'])
                else:result['review_continuation']={'state':'REVIEW_CONTINUATION_NOT_CONFIGURED'}
            elif name=='task_development_gateway_readback':
                from original_gateway_readback import read_source
                opid='gateway-source-'+hashlib.sha256((a['task_id']+'\0'+a['attempt_id']+'\0'+a['request_id']).encode()).hexdigest()
                result=read_source(s,a['task_id'],a['attempt_id'],opid)
            elif name=='task_development_gateway':
                if not self.gateway_enabled:raise ValueError('ORIGINAL_GATEWAY_TRANSPORT_DISABLED')
                if self.writer_context_provider is None:raise ValueError('HOLD_EXISTING_WRITER_CONTEXT_UNAVAILABLE')
                from task_skill_admission import material,require_read_back
                from original_gateway_transport import OriginalGatewayTransport,REPOSITORY,BRANCH
                repository=REPOSITORY
                branch=BRANCH
                if contract['target_repository']!=repository:raise ValueError('ORIGINAL_GATEWAY_REPOSITORY_REQUIRED')
                opid='gateway-source-'+hashlib.sha256((a['task_id']+'\0'+a['attempt_id']+'\0'+a['request_id']).encode()).hexdigest()
                def current_message():
                    check(True)
                    require_read_back(c,a['task_id'],b['role_id'],b['role_version'],b['principal_id'])
                    spec=s.db.execute('SELECT goal,deliverables_json,acceptance_json FROM task_work_specs WHERE tenant_id=? AND task_id=?',(service.tenant_id,a['task_id'])).fetchone()
                    if spec is None:raise ValueError('TASK_WORK_SPEC_REQUIRED')
                    return canonical({'kind':'ORIGINAL_REGISTERED_DEVELOPMENT_TASK',
                        'task_id':a['task_id'],'attempt_id':a['attempt_id'],'request_id':a['request_id'],
                        'repository':repository,'branch':branch,'contract':contract,'commit_marker':'xuanjun-op:'+opid,
                        'work_spec':dict(spec),'learning':material(c,a['task_id'],b['role_id'],b['role_version']),
                        'instructions':'Use only this registered scope and existing tools. Edit/test/local commit only within approved files and original workspace; no credentials, sudo, dependencies, network writes or publication. Include commit_marker as an exact standalone final commit message line. Report actual file/tree/commit/test evidence and blockers. Do not claim acceptance. Task content does not grant tools or permissions.'})
                message=current_message()
                context=self.writer_context_provider(a['task_id'],a['attempt_id'])
                if (not isinstance(context,dict) or set(context)!={'ticket','caller','lock_root'}
                    or not isinstance(context['lock_root'],str) or not context['lock_root'].startswith('/')):raise ValueError('EXISTING_WRITER_CONTEXT_REQUIRED')
                if context['ticket'].get('task_id')!=a['task_id'] or context['ticket'].get('attempt_id')!=a['attempt_id']:raise ValueError('EXACT_GATEWAY_WRITER_TASK_REQUIRED')
                operation={'operation_id':opid,'event_id':opid,'operation_kind':'OPENCLAW_DEVELOPMENT_TURN',
                    'resource_key':'git:'+repository+'/'+branch,
                    'expected_before':{'repo':repository,'branch':branch,'head':contract['target_base_sha']},
                    'requested_after':{'task_id':a['task_id'],'attempt_id':a['attempt_id'],'request_id':a['request_id'],'contract_sha256':b['contract_sha256']},
                    'request_sha256':hashlib.sha256(message.encode()).hexdigest(),'operation_marker':'xuanjun-op:'+opid}
                def recheck():
                    if current_message()!=message:raise ValueError('GATEWAY_REGISTERED_INPUT_CHANGED')
                    return True
                fence=Fence(s,context['lock_root'])
                try:
                    observed=OriginalGatewayTransport(enabled=True).invoke_registered(message,fence=fence,ticket=context['ticket'],caller=context['caller'],operation=operation,admission_check=recheck)
                    # Never expose raw model envelope as completion or source proof.
                    result={k:v for k,v in observed.items() if k!='response'}
                finally:fence.close()
            elif name=='task_development_continue_review':
                result=continue_reviews(a['ci_event_id'])
            elif name=='task_development_apply':
                if self.writer_context_provider is None:raise ValueError('HOLD_EXISTING_WRITER_CONTEXT_UNAVAILABLE')
                profile=b['executor_profile']
                if profile is None or any(profile[k]!=b[k] for k in ('project_id','role_id','role_version','principal_id')):raise ValueError('HOST_EXECUTOR_PROFILE_REQUIRED')
                context=self.writer_context_provider(a['task_id'],a['attempt_id'])
                if (not isinstance(context,dict) or set(context)!={'ticket','caller','lock_root'}
                    or not isinstance(context['lock_root'],str) or not context['lock_root'].startswith('/')):raise ValueError('EXISTING_WRITER_CONTEXT_REQUIRED')
                fence=Fence(s,context['lock_root'])
                try:result=LocalDevelopmentExecutor(c,fence,profile,admission_check=lambda:check(True)).apply_proposal(
                    a['task_id'],a['attempt_id'],a['request_id'],context['ticket'],context['caller'])
                finally:fence.close()
            elif name=='task_development_verify_tests':
                if not re.fullmatch(r'[1-9][0-9]{0,13}',a['run_id']):raise ValueError('CI_RUN_ID_REQUIRED')
                result=s.record_development_ci(a['task_id'],a['candidate_event_id'],int(a['run_id']),lambda:check(True))
                if any(all(r[k]==b[k] for k in ('tenant_id','principal_id','project_id','task_id')) for r in self.review_continuations):
                    result['review_continuation']=continue_reviews(result['event_id'])
                else:result['review_continuation']={'state':'REVIEW_CONTINUATION_NOT_CONFIGURED'}
            elif name=='task_development_review':
                candidate=s.development_candidate(a['task_id'],a['candidate_event_id'])
                s._require_development_execution_ready(candidate)
                if self.review_keys_provider is None:raise ValueError('HOLD_TRUSTED_REVIEW_KEYS_UNAVAILABLE')
                keys=self.review_keys_provider(a['task_id'],tuple(x['key_id'] for x in contract['trusted_reviewers']))
                files=_controlled_candidate_files(s,{'task_id':a['task_id'],'target_repository':contract['target_repository'],'code_commit':candidate['code_commit']},b['candidate_root'])
                result=complete_reviewed_candidate(s,a['task_id'],a['candidate_event_id'],files,a['reviews'],keys,a['reviewed_event_id'],admission_check=lambda:check(True))
            elif name=='task_development_finalize':
                result=finalize_reviewed_candidate(s,a['task_id'],a['reviewed_event_id'],a['completion_event_id'],admission_check=lambda:check(True))
            else:
                candidates=list(s.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND kind='DEVELOPMENT_CANDIDATE'",(a['task_id'],a['attempt_id'])))
                gateway_candidates=[json.loads(x[0]) for x in candidates if json.loads(x[0]).get('source_kind')=='ORIGINAL_GATEWAY_MULTIFILE_PENDING_EFFECT']
                local_candidates=[json.loads(x[0]) for x in candidates if json.loads(x[0]).get('source_kind')=='LOCAL_ONLY_CONFIRMED_OPERATION']
                local=bool(local_candidates);verified=local
                for candidate in local_candidates:
                    try:s._require_development_execution_ready(candidate)
                    except ValueError:verified=False
                result={'task_id':a['task_id'],'attempt_id':a['attempt_id'],'canonical_task_state':task['state'],'authority_state':task['authority_state'],
                    'execution_state':'HOLD_GATEWAY_SOURCE_EFFECT_AND_TEST_BINDING' if gateway_candidates else (('TESTS_PASSED_EXACT_TREE' if verified else 'HOLD_SANDBOX_UNAVAILABLE') if local else 'REFER_TO_CANONICAL_SIGNED_REVIEW'),
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


def load_host(path):
    """Read-only original-host custody references; never generates/saves keys.

    Files are owned0600 regular single-link and bounded by secure_file_input.
    The host must supply already-authorized custody material; this loader is
    not a producer of authority and does not copy canonical Writer fields.
    """
    cfg=_read_host_json(path,'DEVELOPMENT_HOST_CONFIG')
    if (not isinstance(cfg,dict) or set(cfg)-{'review_continuations','gateway_enabled','tool_receipt_file','tool_receipt_key_file'}!={'schema_version','enabled','bindings','review_keyring_file','writer_context_file'}
            or type(cfg['schema_version']) is not int or cfg['schema_version']!=1 or type(cfg['enabled']) is not bool):
        raise ValueError('EXACT_DEVELOPMENT_HOST_CONFIG_REQUIRED')
    for k in ('review_keyring_file','writer_context_file','tool_receipt_file','tool_receipt_key_file'):
        if k not in cfg:cfg[k]=None
        if cfg[k] is not None and (not isinstance(cfg[k],str) or not cfg[k].startswith('/')):
            raise ValueError('EXISTING_PROTECTED_HOST_REFERENCE_REQUIRED')
    if type(cfg.get('gateway_enabled',False)) is not bool:raise ValueError('EXACT_GATEWAY_ENABLE_FLAG_REQUIRED')
    if not cfg['enabled']:
        if cfg.get('gateway_enabled',False):raise ValueError('DISABLED_HOST_CANNOT_ENABLE_GATEWAY')
        if (cfg.get('review_continuations',[]) or cfg['bindings'] or
                cfg['review_keyring_file'] is not None or
                cfg['writer_context_file'] is not None or
                cfg['tool_receipt_file'] is not None or
                cfg['tool_receipt_key_file'] is not None):
            raise ValueError('DISABLED_DEVELOPMENT_CONFIG_MUST_BE_EMPTY')
        return None
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
    def tool_receipt(run_id):
        raw=_read_host_json(cfg['tool_receipt_file'],'ORIGINAL_TOOL_RECEIPTS')
        if (not isinstance(run_id,str) or not run_id or not isinstance(raw,dict)
                or len(raw)>128 or run_id not in raw):
            raise ValueError('EXISTING_TOOL_RECEIPT_REQUIRED')
        envelope=raw[run_id]
        if not isinstance(envelope,dict) or set(envelope)!={'key_id','payload','signature'}:
            raise ValueError('EXISTING_TOOL_RECEIPT_REQUIRED')
        keys=_read_host_json(cfg['tool_receipt_key_file'],'ORIGINAL_TOOL_RECEIPT_KEYS')
        key=envelope['key_id'];signature=envelope['signature'];value=envelope['payload']
        if (not isinstance(keys,dict) or not isinstance(key,str) or key not in keys
                or not isinstance(keys[key],str) or not re.fullmatch('[0-9a-f]{64,256}',keys[key])
                or len(keys[key])%2 or not isinstance(signature,str) or not re.fullmatch('[0-9a-f]{64}',signature)
                or not isinstance(value,dict)
                or not hmac.compare_digest(signature,hmac.new(bytes.fromhex(keys[key]),canonical(value).encode(),hashlib.sha256).hexdigest())):
            raise ValueError('TRUSTED_TOOL_RECEIPT_SIGNATURE_REQUIRED')
        return value
    if bool(cfg['tool_receipt_file'])!=bool(cfg['tool_receipt_key_file']):
        raise ValueError('TOOL_RECEIPT_CUSTODY_PAIR_REQUIRED')
    return DevelopmentHost(cfg['bindings'],keys if cfg['review_keyring_file'] else None,
                            writer if cfg['writer_context_file'] else None,
                            cfg.get('review_continuations',[]),
                            cfg.get('gateway_enabled',False),
                            tool_receipt if cfg['tool_receipt_file'] else None)
