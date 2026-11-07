"""Original events-table multifile candidate handoff; no execution/authority grant.
Reads source through the fixed original readback, never accepts model file SHAs.
"""
import hashlib,json,re
from task_supervisor import canonical,ACTIVE
from original_gateway_transport import BRANCH,WORKSPACE
KIND='ORIGINAL_GATEWAY_MULTIFILE_PENDING_EFFECT'
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def _store(s,task,event_id,kind,payload,reason):
 body=canonical(payload);evidence=digest(payload)
 old=s.db.execute('SELECT kind,payload_json,evidence_ref FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(task['task_id'],task['attempt_id'],event_id)).fetchone()
 if old is not None:
  if tuple(old)!=(kind,body,evidence):raise ValueError('CANONICAL_GATEWAY_EVENT_CONFLICT')
 else:s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(task['task_id'],task['attempt_id'],event_id,kind,s.clock(),reason,evidence,body))
 return {'duplicate':old is not None,'event_id':event_id,'evidence_sha256':evidence}
def bind_candidate(s,task_id,attempt_id,operation_id,ticket,caller,lock_provider_id,admission_check):
 from original_gateway_readback import read_source
 if not callable(admission_check):raise ValueError('ORIGINAL_HOST_ADMISSION_REQUIRED')
 admission_check()
 before=dict(s._task(task_id));contract=s.development_contract(task_id)
 if before['attempt_id']!=attempt_id or ticket.get('task_id')!=task_id or ticket.get('attempt_id')!=attempt_id:raise ValueError('CURRENT_GATEWAY_TASK_ATTEMPT_REQUIRED')
 observed=read_source(s,task_id,attempt_id,operation_id)
 if observed.get('state')!='LOCAL_SOURCE_READ_BACK_NOT_ACCEPTED' or set(observed['files'])!=set(contract['allowed_files']):raise ValueError('EXACT_MULTIFILE_SOURCE_REQUIRED')
 # Real source facts, but not a claim of exclusive authorship or operation CAS.
 candidate={'schema':1,'task_id':task_id,'attempt_id':attempt_id,'lease_id':before['lease_id'],'fence':before['fence'],'epoch':before['epoch'],
  'spec_sha256':before['spec_sha256'],'checkpoint_sha256':before['checkpoint_sha256'],'target_repository':contract['target_repository'],
  'target_base_sha':contract['target_base_sha'],'entry':before['entry'],'code_commit':observed['code_commit'],'tree':observed['tree'],
  'contract_sha256':digest(contract),'files':observed['files'],'source_operation_id':operation_id,'source_kind':KIND,
  'all_changes_attributed_to_task':False,'source_effect_state':'UNKNOWN_RECONCILIATION_REQUIRED'}
 s.db.execute('BEGIN IMMEDIATE')
 with s.db:
  admission_check();task,now=s._validate_writer_locked(ticket,caller,lock_provider_id)
  # Trusted-time update from Writer validation is not a change in task scope.
  keys=('attempt_id','lease_id','fence','epoch','spec_sha256','checkpoint_sha256','state')
  if task['state'] not in ACTIVE or any(task[k]!=before[k] for k in keys) or s.development_contract(task_id)!=contract:raise ValueError('GATEWAY_SOURCE_SCOPE_CHANGED')
  op=s.db.execute('SELECT state FROM writer_operations WHERE operation_id=? AND task_id=? AND attempt_id=?',(operation_id,task_id,attempt_id)).fetchone()
  if op is None or op['state'] not in ('UNKNOWN','DISPATCHING'):raise ValueError('CURRENT_PENDING_GATEWAY_OPERATION_REQUIRED')
  event_id='development-gateway-candidate:'+operation_id+':'+observed['code_commit']
  stored=_store(s,task,event_id,'DEVELOPMENT_CANDIDATE',candidate,'SOURCE_COMMIT')
 return dict(stored,candidate_event_id=event_id,candidate_sha256=digest(candidate),candidate=candidate,execution_state='HOLD_REAL_TEST_AND_EFFECT_RECONCILIATION',development_complete=False)
def record_test_event(s,task_id,candidate_event_id,run_id,receipt_reader,admission_check):
 """Bind one protected original tool receipt to source, plan and result.

 The receipt is read through host custody, never supplied in MCP arguments.
 A successful result is accepted only when its recorded command is the exact
 task-versioned plan and its before/after source snapshot is the candidate
 tree.  The same receipt then reconciles the original Gateway source effect;
 no exit-code-only success path exists.
 """
 if not callable(receipt_reader):raise ValueError('ORIGINAL_TOOL_RECEIPT_READER_UNAVAILABLE')
 if not isinstance(run_id,str) or not run_id:raise ValueError('EXACT_ORIGINAL_RUN_ID_REQUIRED')
 if not callable(admission_check):raise ValueError('ORIGINAL_HOST_ADMISSION_REQUIRED')
 admission_check();candidate=s.development_candidate(task_id,candidate_event_id)
 if candidate.get('source_kind')!=KIND:raise ValueError('ORIGINAL_GATEWAY_MULTIFILE_CANDIDATE_REQUIRED')
 proof=receipt_reader(run_id)
 required={'schema','kind','task_id','attempt_id','operation_id',
  'candidate_event_id','candidate_sha256','run_id','session_id','source',
  'test_plan','call','result'}
 if (not isinstance(proof,dict) or set(proof)!=required or proof.get('schema')!=1
     or proof.get('kind')!='ORIGINAL_GATEWAY_FIXED_TEST_RECEIPT'
     or proof.get('task_id')!=task_id or proof.get('attempt_id')!=candidate['attempt_id']
     or proof.get('operation_id')!=candidate['source_operation_id']
     or proof.get('candidate_event_id')!=candidate_event_id
     or proof.get('candidate_sha256')!=digest(candidate) or proof.get('run_id')!=run_id):
  raise ValueError('ORIGINAL_TOOL_RECEIPT_BINDING_REQUIRED')
 call=proof['call'];result=proof['result']
 if not isinstance(call,dict) or not isinstance(result,dict):raise ValueError('ORIGINAL_TOOL_EVENT_PAIR_REQUIRED')
 if (not isinstance(call.get('id'),str) or not call['id'] or result.get('toolCallId')!=call['id'] or
     call.get('name') not in ('exec_command','bash') or result.get('name')!=call['name'] or result.get('isError') is not False or type(result.get('exit_code')) is not int or result.get('exit_code')!=0 or
     not isinstance(call.get('arguments'),dict) or not isinstance(result.get('output'),str) or len(result['output'].encode())>1048576
     or not isinstance(proof['session_id'],str) or not proof['session_id']):raise ValueError('MATCHED_SUCCESSFUL_TOOL_EVENTS_REQUIRED')
 events=s.db.execute('SELECT evidence_json FROM writer_reconcile_evidence WHERE operation_id=?',(candidate['source_operation_id'],)).fetchall()
 bound=[json.loads(row[0]) for row in events]
 if not any(x.get('kind')=='OPENCLAW_TURN_SOURCE_EFFECTS_REQUIRE_READBACK' and x.get('transport_state')=='GATEWAY_TURN_RETURNED' and x.get('run_id')==run_id and x.get('session_id')==proof['session_id'] for x in bound):raise ValueError('ORIGINAL_OPERATION_RUN_SESSION_BINDING_REQUIRED')
 source=proof['source'];expected_source={'repository','branch','base_sha','code_commit','tree','files'}
 if (not isinstance(source,dict) or set(source)!=expected_source
     or source!={'repository':candidate['target_repository'],'branch':BRANCH,
                 'base_sha':candidate['target_base_sha'],'code_commit':candidate['code_commit'],
                 'tree':candidate['tree'],'files':candidate['files']}):
  raise ValueError('EXACT_TESTED_SOURCE_SNAPSHOT_REQUIRED')
 plan=proof['test_plan'];plan_fields={'plan_id','command','workdir','expected_tree','work_spec_sha256','acceptance_sha256'}
 spec=s.db.execute('''SELECT w.goal,w.deliverables_json,w.acceptance_json
  FROM task_work_specs w JOIN gateway_task_metadata m
  ON m.tenant_id=w.tenant_id AND m.task_id=w.task_id WHERE m.task_id=?''',(task_id,)).fetchone()
 if spec is None:raise ValueError('TASK_WORK_SPEC_REQUIRED')
 spec_value=dict(spec);work_spec_sha=digest(spec_value)
 try:acceptance=json.loads(spec_value['acceptance_json'])
 except (TypeError,ValueError):raise ValueError('CANONICAL_ACCEPTANCE_REQUIRED') from None
 args=call['arguments']
 if (not isinstance(plan,dict) or set(plan)!=plan_fields
     or not isinstance(plan.get('plan_id'),str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',plan['plan_id'])
     or not isinstance(plan.get('command'),str) or not plan['command'].strip() or len(plan['command'].encode())>4096
     or plan.get('workdir')!=WORKSPACE or plan.get('expected_tree')!=candidate['tree']
     or plan.get('work_spec_sha256')!=work_spec_sha or plan.get('acceptance_sha256')!=digest(acceptance)
     or args.get('cmd')!=plan['command'] or args.get('workdir')!=plan['workdir']):
  raise ValueError('EXACT_TASK_VERSIONED_TEST_PLAN_REQUIRED')
 plan_sha=digest(plan)
 # A source readback receipt is valid only for this original operation and the
 # exact candidate/test-plan tuple. It is not a generic FAKE_TXN/GIT_CAS claim.
 operation_row=s.db.execute('SELECT state,payload_json FROM writer_operations WHERE operation_id=?',(candidate['source_operation_id'],)).fetchone()
 operation=operation_row
 if operation is None:raise ValueError('CURRENT_PENDING_GATEWAY_OPERATION_REQUIRED')
 operation=json.loads(operation['payload_json'])
 final_receipt={'schema':1,'outcome':'CONFIRMED','operation_id':candidate['source_operation_id'],
  'resource_key':operation['resource_key'],'operation_marker':operation['operation_marker'],
  'attribution':{'kind':'SOURCE_READBACK','before':operation['expected_before'],'after':operation['requested_after']},
  'source_snapshot':dict(source,candidate_sha256=digest(candidate),test_plan_sha256=plan_sha)}
 reconcile_evidence={'kind':'ORIGINAL_GATEWAY_SOURCE_AND_TEST_READBACK','run_id':run_id,
  'session_id':proof['session_id'],'candidate_sha256':digest(candidate),'tree':candidate['tree'],
  'test_plan_sha256':plan_sha,'tool_call_id':call['id'],'output_sha256':hashlib.sha256(result['output'].encode()).hexdigest()}
 context={'role':'RECONCILER','caller_id':'ORIGINAL_GATEWAY_TOOL_RECEIPT_READER',
  'evidence_id':'gateway-source-test:'+digest(reconcile_evidence)}
 if operation_row['state']=='CONFIRMED':
  prior=s.db.execute('SELECT receipt_json FROM writer_receipts WHERE operation_id=?',(candidate['source_operation_id'],)).fetchone()
  if prior is None or prior[0]!=canonical(final_receipt):raise ValueError('GATEWAY_SOURCE_RECEIPT_CONFLICT')
  reconciled={'state':'CONFIRMED','duplicate':True}
 else:
  reconciled=s.reconcile_operation(candidate['source_operation_id'],context,'CONFIRMED',reconcile_evidence,final_receipt)
 # Do not store raw commands/output which may contain credentials/customer data.
 ci_proof={'schema':1,'source_kind':'ORIGINAL_GATEWAY_TRUSTED_TOOL_RECEIPT',
  'repository':source['repository'],'run_id':run_id,'session_id':proof['session_id'],
  'code_commit':candidate['code_commit'],'tree':candidate['tree'],'files':candidate['files'],
  'work_spec_sha256':work_spec_sha,'acceptance_sha256':digest(acceptance),
  'test_plan_sha256':plan_sha,'tool_call_id':call['id'],'call_sha256':digest(call),
  'output_sha256':hashlib.sha256(result['output'].encode()).hexdigest(),
  'state':'TESTS_PASSED_EXACT_TREE','approval_generated':False,'workflow_dispatched':False}
 observation={'schema':1,'candidate_event_id':candidate_event_id,'candidate_sha256':digest(candidate),
  'source_kind':'ORIGINAL_GATEWAY_TRUSTED_TOOL_RECEIPT','proof':ci_proof}
 s.db.execute('BEGIN IMMEDIATE')
 with s.db:
  admission_check();task=s._task(task_id)
  if s.development_candidate(task_id,candidate_event_id)!=candidate:raise ValueError('CANDIDATE_CHANGED_DURING_TEST_READBACK')
  event_id='development-ci:'+digest(candidate)
  stored=_store(s,task,event_id,'DEVELOPMENT_CI_VERIFIED',observation,'TEST_RUN')
 return dict(stored,observation=observation,execution_state='TESTS_PASSED_EXACT_TREE',
             source_effect_state=reconciled['state'],development_complete=False)
