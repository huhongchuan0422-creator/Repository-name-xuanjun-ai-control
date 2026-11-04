import hashlib,json,time,unittest
import test_model_orchestration as fixtures
from model_orchestration import ModelControl,ModelScheduler
from task_center_mcp_service import ensure_schema
from task_center_mcp_result_recovery import ResultRecoveryMCP
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ModelOrchestrationTests();self.f.setUp();f=self.f;f.assigned()
  f.supervisor.db.execute("UPDATE task_work_specs SET goal=?,deliverables_json=?,acceptance_json=? WHERE task_id='demo-b'",('Persist one result',json.dumps(['structured_model_result']),json.dumps(['model_result_persisted'])))
  f.supervisor.db.execute("UPDATE tasks SET completion_json=? WHERE task_id='demo-b'",(json.dumps(['model_result_persisted']),));f.supervisor.db.commit()
  for role,phase,kind in [('qa','REVIEWER','QA'),('security','REVIEWER','SECURITY'),('acceptor','ACCEPTOR',None)]:
   f.role(role,phase,['code'],False,kind);f.control.assign('demo-b',role,'v1',role)
  q=f.control.queue_request('demo-b','developer',[],'one-existing-fixture',16);self.rid=q['request_id']
  class LocalFixture:
   def invoke(self,*args):return {'content':'persisted fixture','usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},'provider_request_id':'local-fixture'}
  self.assertEqual('SUCCEEDED',ModelScheduler(f.control,{'openai-compatible':LocalFixture()}).run_once()['state'])
  raw=f.supervisor.db.execute('SELECT result_json FROM model_requests WHERE request_id=?',(self.rid,)).fetchone()[0];self.sha=hashlib.sha256(raw.encode()).hexdigest()
  ensure_schema(f.supervisor.db)
  f.supervisor.db.execute('INSERT INTO mcp_task_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('tenant-a','admin:owner','demo-project','fixture','demo-b',self.rid,'a'*64,'b'*64,'fixture-connection','free','ok',16,'QUEUED',1,1));f.supervisor.db.commit()
  self.now=time.time()+1000;f.supervisor.clock=lambda:self.now;f.control.clock=lambda:self.now
 def tearDown(self):self.f.tearDown()
 def facade(self,who='admin:owner'):
  phase='CONTROLLER' if who=='admin:owner' else 'ACCEPTOR' if who=='acceptor' else 'REVIEWER'
  c=ModelControl(self.f.gateway,self.f.authority.issue('tenant-a',who),self.f.master,clock=lambda:self.now)
  b=dict(tenant_id='tenant-a',principal_id=who,project_id='demo-project',task_id='demo-b',attempt_id='attempt-b',request_id=self.rid,result_sha256=self.sha,phase=phase,role_id='developer' if phase=='CONTROLLER' else who,role_version='v1',review_kind=who.upper() if phase=='REVIEWER' else None,actions=['task_result_recovery_status']+(['task_prepare_result_recovery'] if phase=='CONTROLLER' else ['task_accept_result_recovery'] if phase=='ACCEPTOR' else ['task_review_result_recovery']))
  return ResultRecoveryMCP(c,b)
 def args(self,**kw):return dict(task_id='demo-b',attempt_id='attempt-b',**kw)
 def revoke(self):
  f=self.f;controller={'role':'REVOCATION_CONTROLLER','caller_id':'fixture-existing-controller'}
  f.fence.begin_revocation('demo-b',controller);f.fence.drain('demo-b',controller,1);f.fence.invalidate_source_resources('demo-b','fixture-original-revocation');f.supervisor.complete_revocation('demo-b')
 def test_expired_result_not_automatically_success_or_replayed(self):
  v=self.facade().call('task_result_recovery_status',self.args())
  self.assertEqual('RESULT_VERIFIED_REVOKE_AND_REVIEW_REQUIRED',v['state'])
  with self.assertRaisesRegex(ValueError,'ORIGINAL_REVOCATION'):self.facade().call('task_prepare_result_recovery',self.args())
  self.assertEqual('STARTED',self.f.supervisor._task('demo-b')['state'])
 def test_original_result_recovery_independent_reviews_then_accept(self):
  self.revoke();v=self.facade().call('task_prepare_result_recovery',self.args());cid=v['candidate_id']
  self.assertEqual('REVIEW_REQUIRED',v['recovery_state'])
  with self.assertRaisesRegex(ValueError,'REVIEW_PASS'):self.facade('acceptor').call('task_accept_result_recovery',self.args(candidate_id=cid))
  for who in ('qa','security'):self.facade(who).call('task_review_result_recovery',self.args(candidate_id=cid,findings=[],passed=True))
  result=self.facade('acceptor').call('task_accept_result_recovery',self.args(candidate_id=cid))
  self.assertEqual('ACCEPTED',result['state']);self.assertEqual('SUCCESS',self.f.supervisor._task('demo-b')['state'])
  row=self.f.supervisor.db.execute('SELECT state,attempts FROM model_requests WHERE request_id=?',(self.rid,)).fetchone();self.assertEqual(('SUCCEEDED',1),tuple(row))
  self.assertEqual('REVOKED',self.f.supervisor._task('demo-b')['authority_state'])

 def prepared(self):
  self.revoke();return self.facade().call('task_prepare_result_recovery',self.args())['candidate_id']
 def reviewed(self):
  cid=self.prepared()
  for who in ('qa','security'):self.facade(who).call('task_review_result_recovery',self.args(candidate_id=cid,findings=[],passed=True))
  return cid
 def test_wrong_digest_or_caller_is_denied_without_ledger_write(self):
  a=self.facade();a.b['result_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'DIGEST'):a.call('task_result_recovery_status',self.args())
  a=self.facade();a.b['principal_id']='other'
  with self.assertRaisesRegex(ValueError,'IDENTITY'):a.call('task_result_recovery_status',self.args())
  self.assertEqual(0,self.f.supervisor.db.execute('SELECT count(*) FROM delivery_candidates').fetchone()[0])
 def test_unknown_settlement_is_not_recovered(self):
  self.f.supervisor.db.execute("UPDATE model_usage_events SET cost_state='UNKNOWN' WHERE request_id=?",(self.rid,));self.f.supervisor.db.commit()
  with self.assertRaisesRegex(ValueError,'SETTLEMENT'):self.facade().call('task_result_recovery_status',self.args())
 def test_request_attempt_count_must_remain_one(self):
  self.f.supervisor.db.execute('UPDATE model_requests SET attempts=2 WHERE request_id=?',(self.rid,));self.f.supervisor.db.commit()
  with self.assertRaisesRegex(ValueError,'SETTLED_RESULT'):self.facade().call('task_result_recovery_status',self.args())
 def assert_no_recovery_effects(self):
  db=self.f.supervisor.db
  for table in ('delivery_candidates','gateway_checkpoints'):
   self.assertEqual(0,db.execute('SELECT count(*) FROM '+table+" WHERE task_id='demo-b'").fetchone()[0])
  self.assertEqual(0,db.execute("SELECT count(*) FROM events WHERE task_id='demo-b' AND kind IN ('RESULT_RECOVERY_SOURCE','TERMINAL')").fetchone()[0])
  self.assertEqual('STARTED',self.f.supervisor._task('demo-b')['state'])
  self.assertEqual(('SUCCEEDED',1),tuple(db.execute('SELECT state,attempts FROM model_requests WHERE request_id=?',(self.rid,)).fetchone()))
 def test_work_spec_changed_before_prepare_is_not_rebased(self):
  from task_supervisor import canonical
  db=self.f.supervisor.db
  executed=db.execute('SELECT work_spec_sha256 FROM model_request_bindings WHERE request_id=?',(self.rid,)).fetchone()[0]
  db.execute("UPDATE task_work_specs SET goal=?,deliverables_json=? WHERE task_id='demo-b'",('different goal',json.dumps(['different deliverable'])));db.commit()
  spec=db.execute("SELECT goal,deliverables_json,acceptance_json FROM task_work_specs WHERE task_id='demo-b'").fetchone()
  self.assertNotEqual(executed,hashlib.sha256(canonical(dict(spec)).encode()).hexdigest())
  self.revoke()
  with self.assertRaisesRegex(ValueError,'EXECUTED_WORK_SPEC_CHANGED_OR_MISSING'):
   self.facade().call('task_prepare_result_recovery',self.args())
  self.assert_no_recovery_effects()
 def test_missing_executed_work_spec_hash_is_not_rebased(self):
  self.revoke();db=self.f.supervisor.db
  for missing in (None,''):
   with self.subTest(hash=missing):
    db.execute('UPDATE model_request_bindings SET work_spec_sha256=? WHERE request_id=?',(missing,self.rid));db.commit()
    with self.assertRaisesRegex(ValueError,'EXECUTED_WORK_SPEC_CHANGED_OR_MISSING'):
     self.facade().call('task_prepare_result_recovery',self.args())
    self.assert_no_recovery_effects()
 def test_prepare_is_idempotent_and_does_not_issue_authority(self):
  cid=self.prepared();again=self.facade().call('task_prepare_result_recovery',self.args())
  self.assertEqual(cid,again['candidate_id']);self.assertTrue(again['duplicate'])
  self.assertEqual(1,self.f.supervisor.db.execute('SELECT count(*) FROM delivery_candidates').fetchone()[0])
  self.assertEqual('REVOKED',self.f.supervisor._task('demo-b')['authority_state'])
 def test_changed_result_cannot_be_accepted_after_review(self):
  cid=self.reviewed();self.f.supervisor.db.execute("UPDATE model_requests SET result_json='{}' WHERE request_id=?",(self.rid,));self.f.supervisor.db.commit()
  with self.assertRaisesRegex(ValueError,'DIGEST'):self.facade('acceptor').call('task_accept_result_recovery',self.args(candidate_id=cid))
  self.assertEqual('STARTED',self.f.supervisor._task('demo-b')['state'])
 def test_revoked_review_role_cannot_be_used_at_canonical_finish(self):
  cid=self.reviewed();self.f.supervisor.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='qa'");self.f.supervisor.db.commit()
  with self.assertRaisesRegex(ValueError,'CURRENT_REVIEW_AUTHORITY'):self.facade('acceptor').call('task_accept_result_recovery',self.args(candidate_id=cid))
  self.assertEqual('STARTED',self.f.supervisor._task('demo-b')['state'])
 def test_direct_canonical_callback_cannot_invent_reviews(self):
  cid=self.prepared();s=self.f.supervisor;s.db.execute('BEGIN IMMEDIATE')
  try:
   with self.assertRaisesRegex(ValueError,'PERSISTED_INDEPENDENT'):
    s.record_reconciled_result_terminal('demo-b','attempt-b',self.sha,'acceptor',lambda:{'candidate_id':cid,'task_id':'demo-b','attempt_id':'attempt-b','artifact_sha256':self.sha})
  finally:s.db.rollback()
  self.assertEqual('STARTED',s._task('demo-b')['state'])
 def test_accept_repeat_requires_real_audit_and_keeps_request_attempt(self):
  cid=self.reviewed();a=self.facade('acceptor');a.call('task_accept_result_recovery',self.args(candidate_id=cid))
  self.assertTrue(a.call('task_accept_result_recovery',self.args(candidate_id=cid))['duplicate'])
  self.assertEqual('ACCEPTED',self.facade().call('task_result_recovery_status',self.args())['state'])
  self.assertEqual(1,self.f.supervisor.db.execute('SELECT attempts FROM model_requests WHERE request_id=?',(self.rid,)).fetchone()[0])
 def test_native_development_cannot_enter_result_recovery(self):
  self.f.supervisor.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('demo-b','attempt-b','contract','DEVELOPMENT_CONTRACT',1,'PHASE_EXECUTION','fixture:contract','{}'));self.f.supervisor.db.commit()
  with self.assertRaisesRegex(ValueError,'FIXED_PERSISTED_RESULT_CONTRACT'):self.facade().call('task_result_recovery_status',self.args())
 def test_host_config_and_mcp_tools_default_off(self):
  from task_center_mcp_dispatch_host import validate_config,dispatch_rpc
  from task_center_mcp_service import MCPTaskService
  service=MCPTaskService(self.f.db,fixtures.KEY,'tenant-a',self.f.master,'admin:owner','demo-project')
  identity={'tenant_id':'tenant-a','principal_id':'admin:owner','project_id':'demo-project','scopes':['task:read','task:submit']}
  rpc={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}}
  off=dispatch_rpc(service,identity,validate_config(None),rpc,False)
  self.assertNotIn('task_prepare_result_recovery',[x['name'] for x in off['result']['tools']])
  config=validate_config({'schema_version':1,'enabled':True,'bindings':[],'recovery_bindings':[self.facade().b]})
  on=dispatch_rpc(service,identity,config,rpc,False)
  self.assertIn('task_prepare_result_recovery',[x['name'] for x in on['result']['tools']])
  result=dispatch_rpc(service,identity,config,{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'task_result_recovery_status','arguments':self.args()}},False)
  self.assertFalse(json.loads(result['result']['content'][0]['text'])['model_invoked'])


 def test_existing_session_csrf_role_route_closes_recovery_without_oauth_admin_expansion(self):
  import sqlite3,threading,http.cookiejar
  from urllib.request import Request,build_opener,HTTPCookieProcessor
  from urllib.error import HTTPError
  from task_center_app import make_server
  from task_center_session_auth import SessionStore
  self.f.supervisor.clock=time.time;self.f.control.clock=time.time
  self.f.supervisor.db.execute("UPDATE tasks SET authority_valid_until=? WHERE task_id='demo-b'",(time.time()-1,));self.f.supervisor.db.commit();self.revoke()
  roles={'admin:owner':['TASK_CENTER_ADMIN'],'qa':['TASK_REVIEWER'],'security':['TASK_REVIEWER'],'acceptor':['TASK_ACCEPTOR']}
  class FixtureIdentity:
   def verify(this,user,password):
    return {'tenant_id':'tenant-a','principal_id':user,'roles':roles[user]} if user in roles and password=='fixture-only' else None
  def connect():
   db=sqlite3.connect(self.f.db);db.row_factory=sqlite3.Row;return db
  sessions=SessionStore(connect,'tenant-a')
  config={'schema_version':1,'enabled':True,'bindings':[],'recovery_bindings':[self.facade(who).b for who in roles]}
  server=make_server(self.f.db,fixtures.KEY,'tenant-a','admin:owner','127.0.0.1',0,self.f.master,identity_provider=FixtureIdentity(),session_store=sessions,external_origin='https://fixture.invalid',mcp_enabled=True,mcp_dispatch_config=config)
  thread=threading.Thread(target=server.serve_forever);thread.daemon=True;thread.start();base='http://127.0.0.1:'+str(server.server_port)
  def login(who):
   client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
   req=Request(base+'/api/session/login',data=json.dumps({'username':who,'password':'fixture-only'}).encode(),headers={'Content-Type':'application/json','Host':'fixture.invalid','Origin':'https://fixture.invalid'})
   response=client.open(req)
   from http.cookies import SimpleCookie
   jar=SimpleCookie()
   for item in response.headers.get_all('Set-Cookie',[]):jar.load(item)
   cookie='; '.join(k+'='+v.value for k,v in jar.items())
   return client,json.loads(response.read())['csrf_token'],cookie
  def post(auth,action,**kw):
   client,csrf,cookie=auth
   req=Request(base+'/api/admin/model-control',data=json.dumps(dict(self.args(**kw),action=action)).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':csrf,'Cookie':cookie,'Host':'fixture.invalid','Origin':'https://fixture.invalid'})
   try:return json.loads(client.open(req).read())
   except HTTPError as e:raise AssertionError(e.read().decode())
  try:
   owner=login('admin:owner')
   with self.assertRaisesRegex(AssertionError,'CSRF_REQUIRED'):post((owner[0],'wrong',owner[2]),'PREPARE_RESULT_RECOVERY')
   cid=post(owner,'PREPARE_RESULT_RECOVERY')['candidate_id']
   with self.assertRaisesRegex(AssertionError,'ROLE_REQUIRED'):post(owner,'REVIEW_RESULT_RECOVERY',candidate_id=cid,findings=[],passed=True)
   for who in ('qa','security'):post(login(who),'REVIEW_RESULT_RECOVERY',candidate_id=cid,findings=[],passed=True)
   self.assertEqual('ACCEPTED',post(login('acceptor'),'ACCEPT_RESULT_RECOVERY',candidate_id=cid)['state'])
   self.assertEqual('SUCCESS',self.f.supervisor._task('demo-b')['state'])
  finally:server.shutdown();server.server_close();thread.join(2)


 def test_direct_canonical_callback_cannot_hide_changed_result(self):
  cid=self.reviewed();s=self.f.supervisor
  s.db.execute("UPDATE model_requests SET result_json='{}' WHERE request_id=?",(self.rid,));s.db.commit();s.db.execute('BEGIN IMMEDIATE')
  try:
   with self.assertRaisesRegex(ValueError,'DIGEST'):
    s.record_reconciled_result_terminal('demo-b','attempt-b',self.sha,'acceptor',lambda:{'candidate_id':cid,'task_id':'demo-b','attempt_id':'attempt-b','artifact_sha256':self.sha})
  finally:s.db.rollback()
  self.assertEqual('STARTED',s._task('demo-b')['state'])

if __name__=='__main__':unittest.main()
