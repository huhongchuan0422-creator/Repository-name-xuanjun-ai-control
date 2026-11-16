"""Default-off recovery of an already persisted, zero-cost TEST_ONLY result.

No Writer revival, model call, approval generation or native development bypass.
Real revocation is an external prerequisite; only factual checkpoint production
and the existing independent candidate review/acceptance chain are extended.
"""
import hashlib
import json
from task_supervisor import canonical, UNKNOWN

ACTIONS={'task_result_recovery_status':None,'task_prepare_result_recovery':'CONTROLLER',
         'task_review_result_recovery':'REVIEWER','task_accept_result_recovery':'ACCEPTOR'}


def source_snapshot(c,b,require_revoked=True):
    c.gateway.assert_task_context(c.context,b['task_id']);c._assert_expected_project(b['task_id'],b['project_id'])
    return source_snapshot_from_db(c.db,c.gateway.supervisor,c.tenant_id,b,require_revoked)


def source_snapshot_from_db(db,supervisor,tenant_id,b,require_revoked=True):
    t=supervisor._task(b['task_id']);tid=t['task_id'];attempt=b['attempt_id']
    meta=db.execute('SELECT tenant_id,project_id FROM gateway_task_metadata WHERE task_id=?',(tid,)).fetchone()
    if meta is None or (meta['tenant_id'],meta['project_id'])!=(tenant_id,b['project_id']):raise ValueError('RECOVERY_TENANT_PROJECT_REQUIRED')
    if t['attempt_id']!=attempt or t['state'] not in ('STARTED','RUNNING','HOLD','SUCCESS'):
        raise ValueError('RECOVERY_CURRENT_ORIGINAL_ATTEMPT_REQUIRED')
    if t['state']=='HOLD' and t['next_action']!='RECONCILE_BEFORE_CONTROLLED_REASSIGN':raise ValueError('RECOVERY_UNRELATED_HOLD_NOT_BYPASSED')
    resources=json.loads(t['resource_scope_json'])
    if (t['stage'] not in ('TEST_ONLY','TEST_ONLY_EXECUTION') or resources!=['fake:'+tid]
        or json.loads(t['completion_json'])!=['model_result_persisted']
        or db.execute("SELECT 1 FROM events WHERE task_id=? AND kind='DEVELOPMENT_CONTRACT'",(tid,)).fetchone()):
        raise ValueError('RECOVERY_FIXED_PERSISTED_RESULT_CONTRACT_REQUIRED')
    if require_revoked and (t['authority_state']!='REVOKED' or t['coverage_digest'] in ('',UNKNOWN)):
        raise ValueError('RECOVERY_ORIGINAL_REVOCATION_REQUIRED')
    if supervisor.unresolved_operations(tid):raise ValueError('RECOVERY_UNKNOWN_EFFECTS_FORBIDDEN')
    spec=db.execute('SELECT goal,deliverables_json,acceptance_json FROM task_work_specs WHERE tenant_id=? AND task_id=?',(tenant_id,tid)).fetchone()
    if spec is None or json.loads(spec['acceptance_json'])!=['model_result_persisted']:
        raise ValueError('RECOVERY_ORIGINAL_ACCEPTANCE_REQUIRED')
    binding=db.execute('SELECT * FROM mcp_task_bindings WHERE tenant_id=? AND task_id=?',(tenant_id,tid)).fetchone()
    if binding is None or binding['request_id']!=b['request_id'] or binding['project_id']!=b['project_id']:
        raise ValueError('RECOVERY_ORIGINAL_MCP_BINDING_REQUIRED')
    rows=list(db.execute('SELECT * FROM model_requests WHERE tenant_id=? AND task_id=? AND attempt_id=?',(tenant_id,tid,attempt)))
    if len(rows)!=1:raise ValueError('RECOVERY_UNIQUE_REQUEST_REQUIRED')
    r=rows[0]
    if (r['request_id']!=b['request_id'] or r['state']!='SUCCEEDED' or r['attempts']!=1 or r['cancel_requested']
        or not isinstance(r['result_json'],str) or len(r['result_json'].encode())>8192):
        raise ValueError('RECOVERY_SETTLED_RESULT_REQUIRED')
    if not isinstance(json.loads(r['result_json']),dict):raise ValueError('RECOVERY_STRUCTURED_RESULT_REQUIRED')
    sha=hashlib.sha256(r['result_json'].encode()).hexdigest()
    if sha!=b['result_sha256']:raise ValueError('RECOVERY_RESULT_DIGEST_MISMATCH')
    usage=db.execute('SELECT * FROM model_usage_events WHERE tenant_id=? AND request_id=?',(tenant_id,r['request_id'])).fetchone()
    reserve=db.execute('SELECT * FROM model_call_reservations WHERE tenant_id=? AND request_id=?',(tenant_id,r['request_id'])).fetchone()
    rb=db.execute('SELECT * FROM model_request_bindings WHERE tenant_id=? AND request_id=?',(tenant_id,r['request_id'])).fetchone()
    if (usage is None or usage['outcome']!='SUCCEEDED' or usage['cost_state']!='KNOWN_ZERO' or usage['cost_value']!=0
        or reserve is None or reserve['state']!='SETTLED' or reserve['cost_state']!='KNOWN_ZERO' or reserve['settled_at'] is None or reserve['reserved_cost']!=0
        or rb is None or rb['allow_paid'] or rb['writer_fence']!=t['fence'] or rb['writer_epoch']!=t['epoch']):
        raise ValueError('RECOVERY_ORIGINAL_SETTLEMENT_AND_FENCE_REQUIRED')
    # Bind the recovered result to the work spec frozen at request admission,
    # never to a changed goal/deliverable observed only during recovery.
    executed_spec_sha=rb['work_spec_sha256']
    current_spec_sha=hashlib.sha256(canonical(dict(spec)).encode()).hexdigest()
    if not executed_spec_sha or executed_spec_sha!=current_spec_sha:
        raise ValueError('RECOVERY_EXECUTED_WORK_SPEC_CHANGED_OR_MISSING')
    assignment=db.execute('SELECT principal_id,role_version FROM model_assignments WHERE tenant_id=? AND task_id=? AND attempt_id=? AND role_id=?',(tenant_id,tid,attempt,r['role_id'])).fetchone()
    if assignment is None:raise ValueError('RECOVERY_ORIGINAL_EXECUTOR_REQUIRED')
    return {'tenant_id':tenant_id,'project_id':b['project_id'],'task_id':tid,'attempt_id':attempt,
        'request_id':r['request_id'],'result_sha256':sha,'spec_sha256':t['spec_sha256'],
        'checkpoint_sha256':t['checkpoint_sha256'],'task_spec_sha256':executed_spec_sha,
        'scope_digest':t['resource_scope_digest'],'fence':t['fence'],'epoch':t['epoch'],
        'request_attempts':1,'request_updated_at':r['updated_at'],'settled_at':reserve['settled_at'],
        'input_tokens':usage['input_tokens'],'output_tokens':usage['output_tokens'],'cost_state':'KNOWN_ZERO','binding_principal':binding['principal_id'],
        'executor_principal':assignment['principal_id'],'executor_role_id':r['role_id'],'executor_role_version':assignment['role_version']}


def recovery_ready(c,task,artifact_sha256=None):
    """Only an authentic persistent reconciliation event enables old core reuse."""
    row=c.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='RESULT_RECOVERY_SOURCE'",(task['task_id'],task['attempt_id'],'result-recovery-source-'+task['attempt_id'])).fetchone()
    if row is None:return False
    saved=json.loads(row['payload_json']);current=source_snapshot(c,saved)
    if current!=saved or (artifact_sha256 is not None and artifact_sha256!=saved['result_sha256']):
        raise ValueError('RECOVERY_FROZEN_SOURCE_CHANGED')
    c.require_host_resource_release(task)
    return True


class ResultRecoveryMCP:
    def __init__(self,control,binding):self.c=control;self.b=dict(binding)
    def authorize(self,name):
        b=self.b;c=self.c
        if name not in b['actions'] or name not in ACTIONS or (ACTIONS[name] and ACTIONS[name]!=b['phase']):
            raise ValueError('RECOVERY_HOST_ACTION_REQUIRED')
        if c._principal()!=b['principal_id'] or c.tenant_id!=b['tenant_id']:
            raise ValueError('RECOVERY_AUTHENTICATED_HOST_IDENTITY_REQUIRED')
        proof=source_snapshot(c,b,require_revoked=name!='task_result_recovery_status')
        if b['phase']=='CONTROLLER':
            if b['principal_id']!=proof['binding_principal']:raise ValueError('RECOVERY_ORIGINAL_SUBMITTER_REQUIRED')
            if (b['role_id'],b['role_version'])!=(proof['executor_role_id'],proof['executor_role_version']):raise ValueError('RECOVERY_ORIGINAL_EXECUTOR_BINDING_REQUIRED')
        else:
            role=c.db.execute('''SELECT r.phase,r.review_kind,r.enabled,r.writer_allowed FROM model_assignments a JOIN role_templates r
              ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
              WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.principal_id=? AND a.role_id=? AND a.role_version=?''',
              (c.tenant_id,b['task_id'],b['attempt_id'],b['principal_id'],b['role_id'],b['role_version'])).fetchone()
            if role is None or role['enabled']!=1 or role['writer_allowed']!=0 or role['phase']!=b['phase'] or role['review_kind']!=b['review_kind']:
                raise ValueError('RECOVERY_CURRENT_INDEPENDENT_ROLE_REQUIRED')
        return proof
    def call(self,name,args):
        if not isinstance(args,dict):raise ValueError('RECOVERY_ARGUMENTS_REQUIRED')
        expected=({'task_id','attempt_id','candidate_id','findings','passed'} if name=='task_review_result_recovery' else
            {'task_id','attempt_id','candidate_id'} if name=='task_accept_result_recovery' else {'task_id','attempt_id'})
        if set(args)!=expected or any(args[k]!=self.b[k] for k in ('task_id','attempt_id')):
            raise ValueError('RECOVERY_EXACT_PINNED_TASK_REQUIRED')
        c=self.c;s=c.gateway.supervisor;b=self.b
        c.db.execute('BEGIN IMMEDIATE')
        try:
            proof=self.authorize(name)
            if name=='task_result_recovery_status':
                t=s._task(b['task_id'])
                state='RESULT_VERIFIED_REVOKE_AND_REVIEW_REQUIRED' if t['authority_state']!='REVOKED' else 'RESULT_VERIFIED_REVIEW_REQUIRED'
                accepted=c.db.execute("SELECT * FROM delivery_candidates WHERE tenant_id=? AND task_id=? AND attempt_id=? AND artifact_sha256=? AND state='ACCEPTED'",(c.tenant_id,b['task_id'],b['attempt_id'],b['result_sha256'])).fetchone()
                if accepted is not None and t['state']=='SUCCESS':
                    c._require_candidate_snapshot(accepted);c._require_terminal_artifact(accepted);c.require_host_resource_release(accepted)
                    if not c.db.execute("SELECT 1 FROM model_audit WHERE tenant_id=? AND principal_id=? AND action='CANDIDATE_ACCEPTED' AND target_id=?",(c.tenant_id,accepted['accepted_by'],accepted['candidate_id'])).fetchone():raise ValueError('RECOVERY_ACCEPTANCE_AUDIT_REQUIRED')
                    state='ACCEPTED'
                return {'state':state,
                    'canonical_state':t['state'],'authority_state':t['authority_state'],'request_state':'SUCCEEDED',
                    'request_attempts':1,'result_sha256':proof['result_sha256'],'model_invoked':False}
        finally:c.db.rollback()
        if name=='task_prepare_result_recovery':return self.prepare(proof)
        c.db.execute('BEGIN IMMEDIATE')
        try:
            self.authorize(name)
            candidate=c.db.execute('SELECT * FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?',(c.tenant_id,args['candidate_id'])).fetchone()
            if candidate is None or candidate['task_id']!=b['task_id'] or candidate['attempt_id']!=b['attempt_id'] or candidate['artifact_sha256']!=b['result_sha256']:
                raise ValueError('RECOVERY_EXACT_CANDIDATE_REQUIRED')
            if not recovery_ready(c,s._task(b['task_id']),candidate['artifact_sha256']):raise ValueError('RECOVERY_SOURCE_REQUIRED')
            if name=='task_review_result_recovery':
                if type(args['passed']) is not bool or not isinstance(args['findings'],list) or len(args['findings'])>32 or any(not isinstance(x,dict) for x in args['findings']) or len(canonical(args['findings']).encode())>8192:
                    raise ValueError('RECOVERY_BOUNDED_REVIEW_REQUIRED')
                result=c.review_candidate(args['candidate_id'],b['principal_id'],args['findings'],args['passed'],b['review_kind'])
            else:
                if candidate['state']=='ACCEPTED':
                    c._require_candidate_snapshot(candidate);c._require_terminal_artifact(candidate)
                    if candidate['accepted_by']!=b['principal_id'] or s._task(b['task_id'])['state']!='SUCCESS':raise ValueError('RECOVERY_ACCEPTED_BINDING_REQUIRED')
                    if not c.db.execute("SELECT 1 FROM model_audit WHERE tenant_id=? AND principal_id=? AND action='CANDIDATE_ACCEPTED' AND target_id=?",(c.tenant_id,b['principal_id'],args['candidate_id'])).fetchone():raise ValueError('RECOVERY_ACCEPTANCE_AUDIT_REQUIRED')
                    return {'state':'ACCEPTED','duplicate':True,'model_invoked':False}
                c.validate_accept_candidate(args['candidate_id'],b['principal_id'])
                # The original candidate/review/release gates were checked in
                # this SAME transaction, not copied from caller assertions.
                s.record_reconciled_result_terminal(b['task_id'],b['attempt_id'],candidate['artifact_sha256'],b['principal_id'],
                    lambda:c.validate_accept_candidate(args['candidate_id'],b['principal_id']))
                result=c.accept_candidate(args['candidate_id'],b['principal_id'])
            c._audit(b['principal_id'],'RESULT_RECOVERY_'+name.upper(),b['task_id'],{'request_id':b['request_id'],'candidate_id':args['candidate_id']},c.clock())
            c.db.commit();return dict(result,model_invoked=False)
        except Exception:c.db.rollback();raise
        finally:
            if c.db.in_transaction:c.db.rollback()
    def prepare(self,proof):
        c=self.c;s=c.gateway.supervisor;b=self.b;tid=b['task_id'];attempt=b['attempt_id']
        cid='reconciled-result-'+hashlib.sha256(canonical(proof).encode()).hexdigest()
        c.db.execute('BEGIN IMMEDIATE')
        try:
            if self.authorize('task_prepare_result_recovery')!=proof:raise ValueError('RECOVERY_SOURCE_CHANGED')
            s.record_reconciled_result_checkpoint(tid,attempt,cid,proof)
            c.db.commit()
        except Exception:c.db.rollback();raise
        release=c.db.execute('SELECT 1 FROM gateway_resource_releases WHERE task_id=? AND attempt_id=?',(tid,attempt)).fetchone()
        if release is None:
            c.gateway.release_revoked_resources(c.context,tid,attempt,cid,'ledger:request/'+b['request_id'],resume_ready=False)
        c.db.execute('BEGIN IMMEDIATE')
        try:
            if self.authorize('task_prepare_result_recovery')!=proof:raise ValueError('RECOVERY_SOURCE_CHANGED')
            c.require_host_resource_release({'task_id':tid,'attempt_id':attempt})
            eid='result-recovery-source-'+attempt;body=canonical(proof)
            existing=c.db.execute('SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(tid,attempt,eid)).fetchone()
            if existing and existing['payload_json']!=body:raise ValueError('RECOVERY_SOURCE_CONFLICT')
            c.db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?)',(tid,attempt,eid,'RESULT_RECOVERY_SOURCE',c.clock(),'TEST_RUN','ledger:request/'+b['request_id'],body))
            if existing is None:c._audit(b['principal_id'],'RESULT_RECOVERY_SOURCE_VERIFIED',tid,proof,c.clock())
            c.db.commit()
        except Exception:c.db.rollback();raise
        # Existing executor is the actual original result producer. This is
        # explicit host service delegation, audited above as the real initiator.
        from model_orchestration import ModelControl
        executor=ModelControl(c.gateway,c.gateway.tenants.issue(c.tenant_id,proof['executor_principal']),c.master_key,clock=c.clock)
        check=executor.register_checklist(tid,[{'id':'model_result_persisted','required':True,'result':'PASS','evidence':'ledger:request/'+b['request_id']+'#sha256='+b['result_sha256']}],proof['executor_principal'])
        c.db.execute('BEGIN IMMEDIATE')
        try:
            self.authorize('task_prepare_result_recovery')
            result=executor.submit_candidate(tid,b['result_sha256'],check['content_sha256'],proof['executor_principal'])
            c.db.commit();return dict(result,recovery_state='ACCEPTED' if result['state']=='ACCEPTED' else 'REVIEW_REQUIRED',model_invoked=False)
        except Exception:c.db.rollback();raise


def validate_bindings(rows):
    if not isinstance(rows,list) or len(rows)>128:raise ValueError('RECOVERY_BINDINGS_REQUIRED')
    seen=set()
    expected={'tenant_id','principal_id','project_id','task_id','attempt_id','request_id','result_sha256','phase','role_id','role_version','review_kind','actions'}
    for b in rows:
        if (not isinstance(b,dict) or set(b)!=expected or any(not isinstance(b[k],str) or not 0<len(b[k])<=128 or any(ord(x)<33 or ord(x)>126 for x in b[k]) for k in expected-{'actions','review_kind'})
            or b['phase'] not in ('CONTROLLER','REVIEWER','ACCEPTOR')
            or b['review_kind'] not in ('QA','SECURITY',None)
            or (b['phase']=='REVIEWER')!=(b['review_kind'] is not None)
            or not isinstance(b['actions'],list) or not b['actions'] or len(set(b['actions']))!=len(b['actions'])
            or any(a not in ACTIONS or (ACTIONS[a] is not None and ACTIONS[a]!=b['phase']) for a in b['actions'])
            or len(b['result_sha256'])!=64 or any(x not in '0123456789abcdef' for x in b['result_sha256'])):
            raise ValueError('EXACT_RECOVERY_BINDING_REQUIRED')
        key=(b['tenant_id'],b['principal_id'],b['project_id'])
        if key in seen:raise ValueError('DUPLICATE_RECOVERY_IDENTITY')
        seen.add(key)
    return rows


def tools(binding):
    result=[]
    for name in binding['actions']:
        properties={k:{'type':'string','minLength':1,'maxLength':128} for k in ('task_id','attempt_id')}
        if name in ('task_review_result_recovery','task_accept_result_recovery'):properties['candidate_id']={'type':'string','pattern':'^[a-f0-9]{64}$'}
        if name=='task_review_result_recovery':properties.update(findings={'type':'array','maxItems':32,'items':{'type':'object'}},passed={'type':'boolean'})
        result.append({'name':name,'description':'Explicit host-approved recovery of one already settled TEST_ONLY result. No model request or Writer renewal.',
            'inputSchema':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}})
    return result
