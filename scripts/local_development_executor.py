"""LOCAL_ONLY single-module source adapter; generated code is NEVER executed.

Consumes the existing model queue result, uses original Fence/Git CAS and
canonical candidate/checkpoint records. No queue, credentials, role creation,
review signing, arbitrary command, service, network or production capability.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from task_writer_fence import OfflineGitCAS
from native_syntax_gate import check_bytes

SANDBOX_STATE='HOLD_SANDBOX_UNAVAILABLE'


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
    def __init__(self, control, fence, profile, admission_check=None):
        required={'project_id','role_id','role_version','principal_id','repository',
                  'branch','repository_root','resource_key','allowed_file','max_source_bytes'}
        if not isinstance(profile,dict) or set(profile)!=required:
            raise ValueError('EXACT_HOST_EXECUTOR_PROFILE_REQUIRED')
        if (not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',profile['repository'])
                or not re.fullmatch(r'[A-Za-z0-9_-]+',profile['branch'])
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*\.py',profile['allowed_file'])
                or type(profile['max_source_bytes']) is not int
                or not 1<=profile['max_source_bytes']<=131072):
            raise ValueError('BOUNDED_SINGLE_MODULE_PROFILE_REQUIRED')
        self.admission_check=admission_check
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

    def _git(self,*args,raw=None):
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
        return result.stdout.decode().strip()

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
        if self.admission_check is None:
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
        return dict(payload,task_id=task_id,attempt_id=attempt_id,request_id=request_id,
                    canonical_task_state=current['state'],source_write_confirmed=True,duplicate=prepared['duplicate'])

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
