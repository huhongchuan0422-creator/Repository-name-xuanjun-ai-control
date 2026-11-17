"""LOCAL_ONLY single-module source adapter; generated code is NEVER executed.

Consumes the existing model queue result, uses original Fence/Git CAS and
canonical candidate/checkpoint records. No queue, credentials, role creation,
review signing, arbitrary command, service, network or production capability.
"""
import hashlib
import json
import os
import re
import secrets
import stat
import threading
import weakref
import subprocess
from pathlib import Path
from task_writer_fence import OfflineGitCAS
from native_syntax_gate import check_bytes
from task_supervisor import canonical
from producer_tree_delta import plan as producer_tree_plan, REPOSITORY as PRODUCER_REPOSITORY, PATH as PRODUCER_PATH

PRODUCER_SNAPSHOT = 'fe9b78539bf92674ca8dcddeb5fb1813ccd032d6b34d5e6e65528444dc63fd35'
PRODUCER_BASE_TREE = '6ce6cc628cc8107c5146e17357844b8aa9d84d42'

SANDBOX_STATE='HOLD_SANDBOX_UNAVAILABLE'

# A query must be issued by the very same host-injected provider instance that
# started an invocation. Random IDs are persisted; the object-to-ID mapping is
# intentionally process-local, so a restart cannot guess old custody.
_PROVIDER_SOURCES={}
_PROVIDER_SOURCES_LOCK=threading.RLock()

def _provider_source(provider):
    if provider is None:
        return {'kind':'FIXED_RUNNER','id':secrets.token_hex(32)}
    key=id(provider)
    with _PROVIDER_SOURCES_LOCK:
        entry=_PROVIDER_SOURCES.get(key)
        if entry is not None and entry[0]() is provider:
            return {'kind':'PROVIDER_INSTANCE','id':entry[1]}
        source_id=secrets.token_hex(32)
        def forget(ref):
            with _PROVIDER_SOURCES_LOCK:
                current=_PROVIDER_SOURCES.get(key)
                if current is not None and current[0] is ref:
                    _PROVIDER_SOURCES.pop(key,None)
        try:ref=weakref.ref(provider,forget)
        except TypeError:
            return {'kind':'UNQUERYABLE_PROVIDER','id':source_id}
        _PROVIDER_SOURCES[key]=(ref,source_id)
        return {'kind':'PROVIDER_INSTANCE','id':source_id}


def capabilities():
    return {'adapter':'LOCAL_ONLY_SINGLE_PYTHON_MODULE','source_write':True,
            'static_syntax_check':True,'generated_code_execution':False,
            'execution_state':SANDBOX_STATE,'review_execution':False,
            'production_ready':False,'model_invocation':False,
            'sandbox_observation':'BWRAP_NETLINK_ROUTE_OPERATION_NOT_PERMITTED',
            'retry_sandbox_or_privilege_escalation':False}


def _git_sha(kind,raw):
    return hashlib.sha1(('%s %d\0'%(kind,len(raw))).encode()+raw).hexdigest()


def _strict_json(raw):
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise ValueError('DUPLICATE_PROPOSAL_KEY')
            out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=unique)


class LocalDevelopmentExecutor:
    def __init__(self, control, fence, profile, admission_check=None, execution_provider=None):
        required={'project_id','role_id','role_version','principal_id','repository',
                  'branch','repository_root','resource_key','allowed_file','max_source_bytes'}
        if not isinstance(profile,dict) or set(profile) not in (required, required | {'producer_snapshot_sha256'}):
            raise ValueError('EXACT_HOST_EXECUTOR_PROFILE_REQUIRED')
        nested = 'producer_snapshot_sha256' in profile
        if nested and (profile['producer_snapshot_sha256'] != PRODUCER_SNAPSHOT or profile['repository'] != PRODUCER_REPOSITORY or profile['allowed_file'] != PRODUCER_PATH):
            raise ValueError('EXACT_PRODUCER_PROFILE_REQUIRED')
        if (not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',profile['repository'])
                or not re.fullmatch(r'[A-Za-z0-9_-]+',profile['branch'])
                or (not nested and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*\.py',profile['allowed_file']))
                or type(profile['max_source_bytes']) is not int
                or not 1<=profile['max_source_bytes']<=131072):
            raise ValueError('BOUNDED_SINGLE_MODULE_PROFILE_REQUIRED')
        self.admission_check=admission_check
        self.execution_provider=execution_provider
        self.control=control;self.gateway=control.gateway
        self.supervisor=self.gateway.supervisor;self.fence=fence;self.profile=dict(profile)
        if fence.supervisor is not self.supervisor:
            raise ValueError('SAME_CANONICAL_SUPERVISOR_REQUIRED')
        if profile['resource_key']!='git:'+profile['repository']+'/'+profile['branch']:
            raise ValueError('EXACT_HOST_RESOURCE_BINDING_REQUIRED')
        self.root=Path(profile['repository_root'])
        self._check_root()
        info=self.root.lstat();self.root_identity=(info.st_dev,info.st_ino)

    def _check_root(self):
        p=self.root
        if not p.is_absolute() or str(p.resolve())!=str(p):raise ValueError('CANONICAL_LOCAL_REPO_REQUIRED')
        info=p.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('PRIVATE_HOST_REPO_REQUIRED')
        count=0
        for child in p.rglob('*'):
            count+=1
            if count>10000 or child.is_symlink():raise ValueError('UNSAFE_LOCAL_REPOSITORY')
        if (p/'objects/info/alternates').exists():raise ValueError('GIT_ALTERNATES_FORBIDDEN')
        if self._git('rev-parse','--is-bare-repository')!='true':raise ValueError('BARE_LOCAL_REPOSITORY_REQUIRED')
        if self._git('rev-parse','--show-object-format')!='sha1':raise ValueError('LOCAL_GIT_SHA1_REQUIRED')
        if self._git('remote','get-url','origin')!='https://github.com/'+self.profile['repository']+'.git':
            raise ValueError('HOST_REPOSITORY_ORIGIN_MISMATCH')

    def _git(self,*args,raw=None,raw_output=False):
        if hasattr(self,'root_identity'):
            info=self.root.lstat()
            if (str(self.root.resolve())!=str(self.root) or
                    (info.st_dev,info.st_ino)!=self.root_identity):
                raise ValueError('HOST_REPOSITORY_IDENTITY_CHANGED')
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8',
             'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1',
             'GIT_AUTHOR_NAME':'Local Host Executor','GIT_AUTHOR_EMAIL':'local-only@example.invalid',
             'GIT_COMMITTER_NAME':'Local Host Executor','GIT_COMMITTER_EMAIL':'local-only@example.invalid'}
        command=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
                 '-c','commit.gpgsign=false','--git-dir='+str(self.root)]+list(args)
        result=subprocess.run(command,input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              env=env,timeout=10,check=False)
        if result.returncode:raise ValueError('FIXED_LOCAL_GIT_COMMAND_FAILED')
        if len(result.stdout)>262144:raise ValueError('GIT_OUTPUT_LIMIT')
        return result.stdout if raw_output else result.stdout.decode().strip()

    def _read_proposal(self, task_id, attempt_id, request_id):
        c=self.control;p=self.profile
        self.gateway.assert_task_context(c.context,task_id)
        meta=c.db.execute('SELECT project_id FROM gateway_task_metadata WHERE tenant_id=? AND task_id=?',
                         (c.tenant_id,task_id)).fetchone()
        task=self.supervisor._task(task_id)
        if meta is None or meta['project_id']!=p['project_id']:raise ValueError('PROJECT_TASK_NOT_VISIBLE')
        if task['attempt_id']!=attempt_id:raise ValueError('STALE_TASK_ATTEMPT')
        row=c.db.execute('''SELECT r.result_json,a.role_version,a.principal_id,rt.phase,rt.writer_allowed,
            b.max_output_tokens FROM model_requests r JOIN model_assignments a ON
            a.tenant_id=r.tenant_id AND a.task_id=r.task_id AND a.attempt_id=r.attempt_id
            AND a.role_id=r.role_id JOIN role_templates rt ON rt.tenant_id=a.tenant_id
            AND rt.role_id=a.role_id AND rt.version=a.role_version JOIN model_request_bindings b
            ON b.tenant_id=r.tenant_id AND b.request_id=r.request_id WHERE
            r.tenant_id=? AND r.task_id=? AND r.attempt_id=? AND r.request_id=?
            AND r.role_id=? AND r.state='SUCCEEDED' AND r.cancel_requested=0 AND rt.enabled=1''',
            (c.tenant_id,task_id,attempt_id,request_id,p['role_id'])).fetchone()
        if (row is None or row['role_version']!=p['role_version'] or
                row['principal_id']!=p['principal_id'] or row['phase']!='EXECUTOR' or row['writer_allowed']!=1):
            raise ValueError('EXACT_SUCCESSFUL_DEVELOPER_PROPOSAL_REQUIRED')
        result=json.loads(row['result_json']);text=result.get('content')
        if not isinstance(text,str) or len(text.encode())>p['max_source_bytes']+1024:
            raise ValueError('BOUNDED_MODEL_PROPOSAL_REQUIRED')
        proposal=_strict_json(text)
        if (not isinstance(proposal,dict) or set(proposal)!={'file_path','base_blob','content'}
                or proposal['file_path']!=p['allowed_file']
                or not isinstance(proposal['content'],str)
                or not isinstance(proposal['base_blob'],str)
                or not re.fullmatch('[0-9a-f]{40}',proposal['base_blob'])):
            raise ValueError('EXACT_SOURCE_PROPOSAL_REQUIRED')
        raw=proposal['content'].encode('utf-8')
        if len(raw)>p['max_source_bytes']:raise ValueError('SOURCE_BYTE_LIMIT')
        contract=self.supervisor.development_contract(task_id)
        if (contract['allowed_files']!=[p['allowed_file']] or
                contract['target_repository']!=p['repository']):
            raise ValueError('CANONICAL_HOST_SOURCE_SCOPE_REQUIRED')
        return task,contract,proposal,raw

    def apply_proposal(self,task_id,attempt_id,request_id,ticket,caller):
        if self.admission_check is not None:self.admission_check()
        p=self.profile;task,contract,proposal,raw=self._read_proposal(task_id,attempt_id,request_id)
        syntax=check_bytes(p['allowed_file'],raw)
        if syntax['state']!='PASS_SYNTAX':raise ValueError('SOURCE_SYNTAX_REJECTED')
        self._check_root()
        before=contract['target_base_sha'];ref='refs/heads/'+p['branch']
        before_tree=self._git('rev-parse',before+'^{tree}')
        producer = 'producer_snapshot_sha256' in p
        if producer:
            if before_tree != PRODUCER_BASE_TREE:raise ValueError('EXACT_PRODUCER_BASE_TREE_REQUIRED')
            root_raw=self._git('cat-file','tree',before_tree,raw_output=True)
            scripts_tree=self._git('rev-parse',before+':scripts')
            scripts_raw=self._git('cat-file','tree',scripts_tree,raw_output=True)
            planned=producer_tree_plan(p['repository'],p['allowed_file'],before_tree,root_raw,scripts_raw,proposal['base_blob'],raw)
            blob=planned['blob_oid'];tree=planned['tree_oid']
        else:
            expected_line='100644 blob '+proposal['base_blob']+'\t'+p['allowed_file']
            if self._git('ls-tree',before)!=expected_line:raise ValueError('EXACT_SINGLE_MODULE_BASE_REQUIRED')
            blob=_git_sha('blob',raw)
            tree_raw=b'100644 '+p['allowed_file'].encode()+b'\0'+bytes.fromhex(blob)
            tree=_git_sha('tree',tree_raw)
        opid='local-source-'+hashlib.sha256((task_id+'\0'+attempt_id+'\0'+request_id).encode()).hexdigest()
        operation=OfflineGitCAS.operation(opid,opid,p['resource_key'],p['repository'],p['branch'],
                    before,before_tree,proposal['base_blob'],tree,blob,'xj-'+opid)
        prepared=self.fence.prepare(ticket,caller,operation)
        if prepared['duplicate']:
            if prepared['state']!='CONFIRMED':raise ValueError('EXISTING_OPERATION_HOLD_NO_REPLAY')
            stored=self.control.db.execute('SELECT receipt_json FROM writer_receipts WHERE operation_id=?',(opid,)).fetchone()
            commit=json.loads(stored['receipt_json'])['observed_revision']
            if self._git('rev-parse',ref)!=commit:raise ValueError('CONFIRMED_SOURCE_READBACK_CHANGED')
        else:
            with self.fence.commit_lease(ticket,caller,opid) as lease:
                # Re-read context after the existing writer dispatch gate, not from model authority.
                _,current_contract,_,current_raw=self._read_proposal(task_id,attempt_id,request_id)
                if self.admission_check is not None:self.admission_check()
                if current_raw!=raw or current_contract!=contract:raise ValueError('SOURCE_BINDING_CHANGED')
                if self._git('rev-parse',ref)!=before:raise ValueError('LOCAL_GIT_BASE_CHANGED')
                if self._git('hash-object','-w','--stdin',raw=raw)!=blob:raise ValueError('BLOB_WRITE_MISMATCH')
                if producer:
                    if self._git('hash-object','-w','-t','tree','--stdin',raw=planned['scripts_raw']) != planned['scripts_oid']:
                        raise ValueError('TREE_WRITE_MISMATCH')
                    if self._git('hash-object','-w','-t','tree','--stdin',raw=planned['root_raw']) != tree:
                        raise ValueError('TREE_WRITE_MISMATCH')
                else:
                    line=('100644 blob '+blob+'\t'+p['allowed_file']+'\n').encode()
                    if self._git('mktree',raw=line)!=tree:raise ValueError('TREE_WRITE_MISMATCH')
                commit=self._git('commit-tree',tree,'-p',before,raw=(operation['operation_marker']+'\n').encode())
                self._git('update-ref',ref,commit,before)
                readback={'repo':p['repository'],'branch':p['branch'],'commit':self._git('rev-parse',ref),
                          'parent':self._git('rev-parse',commit+'^'),'tree':self._git('rev-parse',commit+'^{tree}'),
                          'blob':self._git('rev-parse',commit+':'+p['allowed_file']),
                          'marker':self._git('show','-s','--format=%B',commit)}
                receipt=OfflineGitCAS.validate(operation,readback)
                if receipt['outcome']!='CONFIRMED':raise ValueError('LOCAL_GIT_READBACK_CONFLICT')
                lease.confirmed(receipt)
        current=self.supervisor._task(task_id)
        receipt=dict(schema=1,entry=current['entry'],execution_path='LOCAL_ONLY_HOST_EXECUTOR',
            task_id=task_id,spec_sha256=current['spec_sha256'],checkpoint_sha256=current['checkpoint_sha256'],
            target_repository=contract['target_repository'],target_base_sha=before,code_commit=commit,event='CODE_READY',
            attempt_id=attempt_id,lease_id=ticket['lease_id'],fence=ticket['fence'],epoch=ticket['epoch'],
            lock_provider_id=self.fence.locks.provider_id,source_operation_id=opid,
            status='RECEIPT_VALIDATED_NOT_ADMITTED',native_identity='NOT_APPLICABLE_LOCAL_ONLY',
            quota_attribution='NO_MODEL_CALL_BY_EXECUTOR',authority_effect='NONE',
            required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE',**caller)
        if producer:
            candidate=self.supervisor.bind_local_development_candidate(receipt,{p['allowed_file']:raw},
                admission_check=self.admission_check,producer_tree_proof={'root_raw':root_raw,'scripts_raw':scripts_raw})
        elif self.admission_check is None:
            candidate=self.supervisor.bind_local_development_candidate(receipt,{p['allowed_file']:raw})
        else:
            candidate=self.supervisor.bind_local_development_candidate(receipt,{p['allowed_file']:raw},admission_check=self.admission_check)
        checkpoint='local-executor-'+opid
        payload={'execution_state':SANDBOX_STATE,'candidate_event_id':candidate['candidate_event_id'],
                 'request_id':request_id,'source_sha256':hashlib.sha256(raw).hexdigest(),
                 'source_operation_id':opid,'code_commit':commit,'syntax_state':'PASS_SYNTAX',
                 'generated_code_executed':False,'independent_review':'NOT_EXECUTED',
                 'next_action':'WAIT_ORIGINAL_APPROVED_ISOLATED_EXECUTOR'}
        old=self.control.db.execute('SELECT payload_json FROM gateway_checkpoints WHERE task_id=? AND attempt_id=? AND checkpoint_id=?',
                                   (task_id,attempt_id,checkpoint)).fetchone()
        if old is None:self.gateway.save_checkpoint(self.control.context,task_id,attempt_id,checkpoint,
                            payload,[], 'RECONCILED',self.gateway.canonical_resources(task_id))
        elif json.loads(old['payload_json'])!=payload:raise ValueError('CHECKPOINT_BINDING_CONFLICT')
        output=dict(payload,task_id=task_id,attempt_id=attempt_id,request_id=request_id,
                    canonical_task_state=current['state'],source_write_confirmed=True,duplicate=prepared['duplicate'])
        if 'producer_http_test_sha256' in contract:
            output.update(self._run_producer_http_acceptance(task_id,attempt_id,candidate['candidate_event_id'],ticket,caller))
        return output

    def _run_producer_http_acceptance(self,task_id,attempt_id,candidate_event_id,ticket,caller):
        from producer_http_contract import REFERENCE_SHA256,ALLOWED_FILE
        binding=self.prepare_execution_binding(task_id,attempt_id,candidate_event_id)
        contract=self.supervisor.development_contract(task_id)
        if any(ticket.get(k)!=binding[k] for k in ('task_id','attempt_id','lease_id','fence','epoch')):
            raise ValueError('EXECUTION_WRITER_BINDING_MISMATCH')
        if contract.get('producer_http_test_sha256') != REFERENCE_SHA256:
            raise ValueError('PINNED_PRODUCER_TEST_REQUIRED')
        source=_provider_source(self.execution_provider)
        provider=self.execution_provider
        if provider is None:
            # Preserve the installed runner while recording intent before any
            # side effect; without a query capability retries must reconcile.
            from producer_http_runner import run_producer_http
            def provider(intent, source):
                observation=run_producer_http(source)
                if observation['result']!={'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'}:
                    raise ValueError('PRODUCER_HTTP_TEST_NOT_PASSED')
                return dict(observation, intent_sha256=hashlib.sha256(canonical(intent).encode()).hexdigest())
        candidate=self.supervisor.development_candidate(task_id,candidate_event_id)
        if self._git('rev-parse','refs/heads/'+self.profile['branch'])!=binding['code_commit']:
            raise ValueError('CANDIDATE_SOURCE_READBACK_CHANGED')
        raw=self._git('show',binding['code_commit']+':'+ALLOWED_FILE,raw_output=True)
        source_sha256=hashlib.sha256(raw).hexdigest()
        if source_sha256!=candidate['files'][ALLOWED_FILE]:
            raise ValueError('CANDIDATE_SOURCE_DIGEST_MISMATCH')
        intent_base=dict(binding,source_sha256=source_sha256,test_reference_sha256=REFERENCE_SHA256,
                         source_operation_id=candidate['source_operation_id'])
        intent=dict(intent_base,execution_source=source)
        intent_id='producer-http-intent:'+candidate['source_operation_id']
        intent_body=canonical(intent)
        intent_digest=hashlib.sha256(intent_body.encode()).hexdigest()
        self.control.db.execute('BEGIN IMMEDIATE')
        with self.control.db:
            task,now=self.supervisor._validate_writer_locked(ticket,caller,self.fence.locks.provider_id)
            if self.admission_check is not None:self.admission_check()
            if self.prepare_execution_binding(task_id,attempt_id,candidate_event_id)!=binding:
                raise ValueError('CANDIDATE_CHANGED_BEFORE_TEST')
            old=self.control.db.execute('SELECT kind,evidence_ref,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
                (task_id,attempt_id,intent_id)).fetchone()
            if old is not None:
                try:
                    stored=json.loads(old['payload_json'])
                    stored_source=stored.get('execution_source')
                    stored_base={k:v for k,v in stored.items() if k!='execution_source'}
                    source_valid=(stored_source is None or
                        (type(stored_source) is dict and set(stored_source)=={'kind','id'} and
                         stored_source['kind'] in ('FIXED_RUNNER','PROVIDER_INSTANCE','UNQUERYABLE_PROVIDER') and
                         isinstance(stored_source['id'],str) and re.fullmatch('[0-9a-f]{64}',stored_source['id'])))
                    if (old['kind']!='DEVELOPMENT_EXECUTION_INTENT' or stored_base!=intent_base or not source_valid or
                        old['payload_json']!=canonical(stored) or old['evidence_ref']!=hashlib.sha256(old['payload_json'].encode()).hexdigest()):
                        raise ValueError('EXECUTION_INTENT_BINDING_CONFLICT')
                except (TypeError,ValueError,AttributeError):
                    raise ValueError('EXECUTION_INTENT_BINDING_CONFLICT')
                intent=stored
                intent_digest=old['evidence_ref']
                # Reuse only the already-persisted canonical execution, under
                # the same live writer/tenant/source/contract checks above.
                execution_id='producer-http-execution:'+candidate['source_operation_id']
                recorded=self.control.db.execute('SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
                    (task_id,attempt_id,execution_id)).fetchone()
                if recorded is not None:
                    self.supervisor._require_development_execution_ready(candidate)
                    evidence=json.loads(recorded['payload_json'])
                    return {'execution_state':'ISOLATED_TEST_ELIGIBLE','execution_evidence_verified':True,
                            'execution_event_id':execution_id,'execution_artifact_sha256':evidence['artifact_sha256'],
                            'generated_code_executed':True,'next_action':'WAIT_INDEPENDENT_REVIEW'}
            else:
                self.control.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                    (task_id,attempt_id,intent_id,'DEVELOPMENT_EXECUTION_INTENT',now,'TEST_INTENT',intent_digest,intent_body))
        # Only the host-injected provider may query the original invocation.
        # MCP callers cannot supply a receipt, or assert that execution never began.
        if old is not None:
            if (stored_source is None or stored_source.get('kind')!='PROVIDER_INSTANCE' or
                source!=stored_source):
                return {'execution_state':'UNKNOWN','execution_evidence_verified':False,
                        'next_action':'RECONCILE_ORIGINAL_EXECUTION',
                        'reconciliation_state':'ORIGINAL_PROVIDER_UNAVAILABLE_NO_REPLAY'}
            query=getattr(provider,'query',None)
            if not callable(query):
                return {'execution_state':'UNKNOWN','execution_evidence_verified':False,
                        'next_action':'RECONCILE_WITH_TRUSTED_QUERY_PROVIDER',
                        'reconciliation_state':'NO_QUERY_CAPABILITY_NO_REPLAY'}
            observation=query(intent)
            if observation is None:
                return {'execution_state':'UNKNOWN','execution_evidence_verified':False,
                        'next_action':'RECONCILE_ORIGINAL_EXECUTION'}
        else:
            observation=provider(intent,raw)
        if (not isinstance(observation,dict) or set(observation)!={'intent_sha256','result','test_reference_sha256','source_sha256','artifact_sha256'}
            or observation['intent_sha256']!=intent_digest
            or observation['result']!={'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'}
            or observation['test_reference_sha256']!=REFERENCE_SHA256
            or observation['source_sha256']!=source_sha256
            or not isinstance(observation['artifact_sha256'],str)
            or re.fullmatch('[0-9a-f]{64}',observation['artifact_sha256']) is None):
            raise ValueError('PRODUCER_HTTP_TEST_BINDING_MISMATCH')
        self.control.db.execute('BEGIN IMMEDIATE')
        with self.control.db:
            task,now=self.supervisor._validate_writer_locked(ticket,caller,self.fence.locks.provider_id)
            if self.admission_check is not None:self.admission_check()
            if self.prepare_execution_binding(task_id,attempt_id,candidate_event_id)!=binding:
                raise ValueError('CANDIDATE_CHANGED_DURING_TEST')
            if self._git('rev-parse','refs/heads/'+self.profile['branch'])!=binding['code_commit']:
                raise ValueError('CANDIDATE_SOURCE_READBACK_CHANGED')
            evidence={'schema':1,'candidate_event_id':candidate_event_id,'candidate_sha256':binding['candidate_sha256'],
                'task_id':task_id,'attempt_id':attempt_id,'lease_id':binding['lease_id'],'fence':binding['fence'],
                'epoch':binding['epoch'],'contract_sha256':binding['contract_sha256'],'code_commit':binding['code_commit'],
                'source_sha256':observation['source_sha256'],'test_reference_sha256':REFERENCE_SHA256,
                'artifact_sha256':observation['artifact_sha256'],'result':'PASS'}
            body=canonical(evidence);digest=hashlib.sha256(body.encode()).hexdigest()
            eid='producer-http-execution:'+candidate['source_operation_id']
            old=self.control.db.execute('SELECT kind,payload_json,evidence_ref FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(task_id,attempt_id,eid)).fetchone()
            if old is not None:
                if old['kind']!='DEVELOPMENT_EXECUTION' or old['payload_json']!=body or old['evidence_ref']!=digest:
                    raise ValueError('PRODUCER_EXECUTION_EVIDENCE_CONFLICT')
            else:
                self.control.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                    (task_id,attempt_id,eid,'DEVELOPMENT_EXECUTION',now,'TEST_RUN',digest,body))
        return {'execution_state':'ISOLATED_TEST_ELIGIBLE','execution_evidence_verified':True,
                'execution_event_id':eid,'execution_artifact_sha256':observation['artifact_sha256'],
                'generated_code_executed':True,'next_action':'WAIT_INDEPENDENT_REVIEW'}

    def prepare_execution_binding(self,task_id,attempt_id,candidate_event_id):
        """Read-only binding for a future authorized test executor; never admit it.

        This does not validate an active Writer lease, select a command, run
        code, verify execution provenance, or relax the canonical HOLD.
        """
        self.gateway.assert_task_context(self.control.context,task_id)
        task=self.supervisor._task(task_id)
        if task['attempt_id']!=attempt_id:raise ValueError('STALE_TASK_ATTEMPT')
        meta=self.control.db.execute('SELECT project_id FROM gateway_task_metadata WHERE tenant_id=? AND task_id=?',
            (self.control.tenant_id,task_id)).fetchone()
        if meta is None or meta['project_id']!=self.profile['project_id']:
            raise ValueError('PROJECT_TASK_NOT_VISIBLE')
        row=self.control.db.execute('''SELECT kind,payload_json,evidence_ref FROM events
            WHERE task_id=? AND attempt_id=? AND event_id=?''',
            (task_id,attempt_id,candidate_event_id)).fetchone()
        if row is None or row['kind']!='DEVELOPMENT_CANDIDATE':
            raise ValueError('CURRENT_DEVELOPMENT_CANDIDATE_REQUIRED')
        candidate=json.loads(row['payload_json'])
        digest=hashlib.sha256(canonical(candidate).encode('utf-8')).hexdigest()
        if row['evidence_ref']!=digest:raise ValueError('CANDIDATE_DIGEST_MISMATCH')
        if (candidate.get('source_kind')!='LOCAL_ONLY_CONFIRMED_OPERATION' or
            any(candidate.get(k)!=task[k] for k in ('task_id','attempt_id','lease_id','fence','epoch','spec_sha256','checkpoint_sha256'))):
            raise ValueError('CURRENT_LOCAL_CANDIDATE_BINDING_REQUIRED')
        contract=self.supervisor.development_contract(task_id)
        if (candidate.get('contract_sha256')!=hashlib.sha256(canonical(contract).encode('utf-8')).hexdigest()
                or contract['target_repository']!=self.profile['repository']
                or contract['allowed_files']!=[self.profile['allowed_file']]):
            raise ValueError('CURRENT_DEVELOPMENT_CONTRACT_REQUIRED')
        return {'task_id':task_id,'attempt_id':attempt_id,'candidate_event_id':candidate_event_id,
                'candidate_sha256':digest,'code_commit':candidate['code_commit'],
                'contract_sha256':candidate['contract_sha256'],'lease_id':candidate['lease_id'],
                'fence':candidate['fence'],'epoch':candidate['epoch'],
                'execution_state':SANDBOX_STATE,'test_command_state':'NOT_BOUND',
                'writer_lease_validated':False,'execution_evidence_verified':False}

    def status(self,task_id,attempt_id):
        self.gateway.assert_task_context(self.control.context,task_id)
        if self.supervisor._task(task_id)['attempt_id']!=attempt_id:raise ValueError('STALE_TASK_ATTEMPT')
        meta=self.control.db.execute('SELECT project_id FROM gateway_task_metadata WHERE tenant_id=? AND task_id=?',
            (self.control.tenant_id,task_id)).fetchone()
        if meta is None or meta['project_id']!=self.profile['project_id']:raise ValueError('PROJECT_TASK_NOT_VISIBLE')
        rows=self.control.db.execute('''SELECT checkpoint_id,payload_json FROM gateway_checkpoints
             WHERE task_id=? AND attempt_id=? ORDER BY created_at DESC''',(task_id,attempt_id)).fetchall()
        checkpoints=[json.loads(r['payload_json']) for r in rows]
        return {'task_id':task_id,'attempt_id':attempt_id,'execution_state':SANDBOX_STATE,
                'canonical_task_state':self.supervisor._task(task_id)['state'],
                'checkpoints':checkpoints,'generated_code_executed':False}

    def review_or_finalize(self,*args,**kwargs):
        # Even syntactically valid/signed fixture reviews cannot substitute execution evidence.
        raise ValueError(SANDBOX_STATE)
