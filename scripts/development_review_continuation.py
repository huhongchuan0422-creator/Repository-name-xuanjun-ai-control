"""Consume original verified CI events into original checkpoints/model queue.

No CI execution, connector write, scheduler, credentials, signatures or SUCCESS.
Requires original host-bound reviewer identities and source-reader admission.
"""
import hashlib,json,re,math,copy
from task_supervisor import canonical

def sha(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def require(value,reason):
 if not value:raise ValueError(reason)

class DevelopmentReviewContinuation:
 def __init__(self,control,project_id,bindings,source_reader,admission_check):
  self.c=control;self.g=control.gateway;self.s=self.g.supervisor;self.db=control.db;self.project=project_id
  require(callable(source_reader) and callable(admission_check),'EXISTING_HOST_READ_AND_ADMISSION_REQUIRED')
  require(isinstance(bindings,list) and len(bindings)==2,'EXACT_QA_SECURITY_BINDINGS_REQUIRED')
  fields={'role_id','role_version','principal_id','review_kind','provider_id','model_id','connection_id','max_output_tokens','authority_identity'}
  for b in bindings:
   require(isinstance(b,dict) and set(b)==fields and b['review_kind'] in ('QA','SECURITY'),'EXACT_QA_SECURITY_BINDINGS_REQUIRED')
   require(type(b['max_output_tokens'])is int and 1<=b['max_output_tokens']<=128,'ORIGINAL_OUTPUT_BUDGET_REQUIRED')
   require(isinstance(b['authority_identity'],dict) and set(b['authority_identity'])=={'issuer','subject'},'EXISTING_REVIEW_IDENTITY_REQUIRED')
  require({b['review_kind'] for b in bindings}=={'QA','SECURITY'} and len({b['principal_id'] for b in bindings})==2 and len({b['role_id'] for b in bindings})==2,'INDEPENDENT_EXISTING_REVIEW_ROLES_REQUIRED')
  self.bindings=sorted(copy.deepcopy(bindings),key=lambda b:b['review_kind']);self.read=source_reader;self.admit=admission_check

 def _snapshot(self,task_id,attempt_id,event_id):
  self.admit();self.g.assert_task_context(self.c.context,task_id);self.c._assert_expected_project(task_id,self.project)
  task=self.s._task(task_id);now=self.s.clock()
  require(isinstance(now,(int,float)) and math.isfinite(now) and (task['last_trusted_time'] is None or now>=task['last_trusted_time']),'TRUSTED_AUTHORITY_TIME_REQUIRED')
  require(task['attempt_id']==attempt_id and task['state']=='STARTED' and task['authority_state']=='VALID'
   and task['authority_valid_until'] is not None and now<task['authority_valid_until'],'CURRENT_ADMITTED_WRITER_REQUIRED')
  require(not self.s.unresolved_operations(task_id),'UNRESOLVED_EFFECTS_HOLD')
  row=self.db.execute('SELECT * FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(task_id,attempt_id,event_id)).fetchone()
  require(row is not None and row['kind']=='DEVELOPMENT_CI_VERIFIED' and len(row['payload_json'])<=65536,'ORIGINAL_VERIFIED_CI_EVENT_REQUIRED')
  event=json.loads(row['payload_json']);proof=event.get('proof',{})
  require(row['evidence_ref']==sha(event) and event.get('source_kind') in
   ('AUTHENTICATED_MCP_FIXED_PUBLIC_CI_VERIFICATION','ORIGINAL_GATEWAY_TRUSTED_TOOL_RECEIPT')
   and proof.get('state')=='TESTS_PASSED_EXACT_TREE','ORIGINAL_VERIFIED_CI_EVENT_REQUIRED')
  candidate=self.s.development_candidate(task_id,event['candidate_event_id']);contract=self.s.development_contract(task_id)
  require(event['candidate_sha256']==sha(candidate) and event_id=='development-ci:'+sha(candidate),'CI_CANDIDATE_BINDING_REQUIRED')
  require(all(candidate.get(k)==task[k] for k in ('attempt_id','lease_id','fence','epoch','spec_sha256','checkpoint_sha256'))
   and candidate.get('contract_sha256')==sha(contract) and proof.get('files')==candidate['files'],'CURRENT_DEVELOPMENT_SNAPSHOT_REQUIRED')
  # Bind to the executed developer request's work specification, not a new
  # review-time baseline silently substituted after source execution.
  spec=self.db.execute('SELECT goal,deliverables_json,acceptance_json FROM task_work_specs WHERE tenant_id=? AND task_id=?',(self.c.tenant_id,task_id)).fetchone()
  require(spec is not None,'EXECUTED_WORK_SPEC_CHANGED')
  if candidate.get('source_kind')=='ORIGINAL_GATEWAY_MULTIFILE_PENDING_EFFECT':
   require(proof.get('work_spec_sha256')==sha(dict(spec)) and re.fullmatch('[0-9a-f]{64}',proof.get('test_plan_sha256','')) is not None,
    'EXECUTED_WORK_SPEC_CHANGED')
  else:
   checkpoint=self.db.execute('SELECT payload_json FROM gateway_checkpoints WHERE task_id=? AND attempt_id=? AND checkpoint_id=?',
    (task_id,attempt_id,'local-executor-'+candidate.get('source_operation_id',''))).fetchone()
   require(checkpoint is not None and len(checkpoint[0])<=65536,'ORIGINAL_SOURCE_REQUEST_CHECKPOINT_REQUIRED')
   origin=json.loads(checkpoint[0])
   require(origin.get('candidate_event_id')==event['candidate_event_id'],'ORIGINAL_SOURCE_REQUEST_CHECKPOINT_REQUIRED')
   binding=self.db.execute('''SELECT b.work_spec_sha256 FROM model_request_bindings b JOIN model_requests r ON r.tenant_id=b.tenant_id AND r.request_id=b.request_id
    WHERE r.tenant_id=? AND r.task_id=? AND r.attempt_id=? AND r.request_id=? AND r.state='SUCCEEDED' AND r.cancel_requested=0''',
    (self.c.tenant_id,task_id,attempt_id,origin.get('request_id'))).fetchone()
   require(binding is not None and binding[0]==sha(dict(spec)),'EXECUTED_WORK_SPEC_CHANGED')
  remote=self.db.execute('SELECT * FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(task_id,attempt_id,'development-remote:'+sha(candidate))).fetchone()
  commit=candidate['code_commit']
  if remote:
   body=json.loads(remote['payload_json'])
   require(remote['kind']=='DEVELOPMENT_REMOTE_SOURCE' and remote['evidence_ref']==sha(body) and body.get('candidate_sha256')==sha(candidate)
    and body.get('local_commit')==commit and body.get('tree')==proof.get('tree'),'REMOTE_SOURCE_BINDING_REQUIRED')
   commit=body['remote_commit']
  require(proof.get('code_commit')==commit,'CI_EXACT_CODE_COMMIT_REQUIRED')
  for b in self.bindings:
   role=self.db.execute('''SELECT r.phase,r.review_kind,r.writer_allowed,r.enabled,a.role_version,a.principal_id,a.provider_id,a.model_id,a.reason
    FROM model_assignments a JOIN role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
    WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.role_id=?''',(self.c.tenant_id,task_id,attempt_id,b['role_id'])).fetchone()
   require(role is not None and tuple(role)==('REVIEWER',b['review_kind'],0,1,b['role_version'],b['principal_id'],b['provider_id'],b['model_id'],'QUALIFIED_FREE_FINAL_COST'),'CURRENT_HOST_REVIEW_ASSIGNMENT_REQUIRED')
   require(any(x['role']==b['review_kind'] and all(x[k]==b['authority_identity'][k] for k in ('issuer','subject')) for x in contract['trusted_reviewers']),'ORIGINAL_TRUSTED_REVIEWER_REQUIRED')
  return event,candidate

 def _checkpoint(self,task_id,attempt_id,key,payload,check):
  prior=self.db.execute('SELECT payload_json FROM gateway_checkpoints WHERE task_id=? AND attempt_id=? AND checkpoint_id=?',(task_id,attempt_id,key)).fetchone()
  if prior:
   require(prior[0]==canonical(payload),'REVIEW_CHECKPOINT_CONFLICT');return
  self.g.save_checkpoint(self.c.context,task_id,attempt_id,key,payload,[],'RECONCILED',self.g.canonical_resources(task_id),admission_check=check)

 def continue_from_ci(self,task_id,attempt_id,event_id):
  event,candidate=self._snapshot(task_id,attempt_id,event_id);snapshot=sha({'event':event,'candidate':candidate})
  def check():
   a,b=self._snapshot(task_id,attempt_id,event_id)
   require(sha({'event':a,'candidate':b})==snapshot,'CI_CONTINUATION_SNAPSHOT_CHANGED')
  files=self.read(task_id,candidate)
  require(isinstance(files,dict) and set(files)==set(candidate['files']) and all(type(v)is bytes and hashlib.sha256(v).hexdigest()==candidate['files'][k] for k,v in files.items()),'EXACT_REVIEW_SOURCE_REQUIRED')
  source={k:v.decode('utf-8','strict') for k,v in files.items()}
  # Preserve original MCP input cap. No automatic token/budget expansion.
  content=canonical({'instruction':'Review exact code and test evidence; return findings only. Do not sign, execute, approve or mark task complete.',
   'candidate_sha256':sha(candidate),'ci_event_id':event_id,'files':source})
  messages={b['review_kind']:canonical(dict(json.loads(content),review_kind=b['review_kind'])) for b in self.bindings}
  require(all(len(v)<=4000 and len(v.encode())<=16000 for v in messages.values()),'ORIGINAL_REVIEW_INPUT_LIMIT')
  base={'ci_event_id':event_id,'candidate_event_id':event['candidate_event_id'],'candidate_sha256':sha(candidate),
   'execution_state':'TESTS_PASSED_EXACT_TREE','signed_review':False,'canonical_success':False}
  key='ci-review:'+snapshot
  self._checkpoint(task_id,attempt_id,key,dict(base,next_action='REVIEW_REQUIRED'),check)
  requests=[]
  for b in self.bindings:
   check();idem='ci-review-'+sha({'task':task_id,'attempt':attempt_id,'event':event_id,'kind':b['review_kind']})
   queued=self.c.queue_request(task_id,b['role_id'],[{'role':'user','content':messages[b['review_kind']]}],idem,b['max_output_tokens'],b['connection_id'],
    expected_attempt_id=attempt_id,expected_project_id=self.project,expected_assignment_binding=b,admission_check=check)
   row=dict(review_kind=b['review_kind'],**queued);requests.append(row)
   # Queue persistence is not delivery, reviewer ACK or a signed verdict.
   self._checkpoint(task_id,attempt_id,key+':'+b['review_kind'],dict(base,review_kind=b['review_kind'],request_id=queued['request_id'],next_action='WAIT_ORIGINAL_MODEL_REQUEST_RESULT'),check)
   if queued['state']=='SUCCEEDED':
    result_row=self.db.execute('SELECT result_json FROM model_requests WHERE tenant_id=? AND request_id=?',(self.c.tenant_id,queued['request_id'])).fetchone()
    require(result_row is not None and isinstance(result_row[0],str) and 0<len(result_row[0])<=262144,'REVIEW_RESULT_EVIDENCE_REQUIRED')
    row['result_sha256']=hashlib.sha256(result_row[0].encode()).hexdigest()
    self._checkpoint(task_id,attempt_id,key+':'+b['review_kind']+':result',dict(base,review_kind=b['review_kind'],request_id=queued['request_id'],result_sha256=row['result_sha256'],next_action='WAIT_AUTHENTICATED_SIGNED_REVIEW'),check)
   if queued['state'] in ('UNKNOWN','FAILED','CANCELLED'):
    return dict(base,state='HOLD_EXISTING_REVIEW_REQUEST_'+queued['state'],requests=requests,model_calls_by_continuation=0)
  ready=all(x['state']=='SUCCEEDED' for x in requests)
  return dict(base,state='REVIEW_PROPOSALS_READY_UNSIGNED' if ready else 'REVIEW_REQUESTS_REGISTERED',requests=requests,model_calls_by_continuation=0,
   next_action='WAIT_AUTHENTICATED_SIGNED_REVIEW' if ready else 'ORIGINAL_SCHEDULER_THEN_AUTHENTICATED_SIGNED_REVIEW')
