import copy,hashlib,json,os,threading,unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import test_task_center_app as app_fixture
KEY=app_fixture.KEY
from task_supervisor import canonical,Supervisor
from task_center_mcp_development import load_host
from task_center_app import build_handler,TaskCenterHTTPServer
from cryptography.fernet import Fernet

class RegistrationDelta(unittest.TestCase):
 def setUp(self):
  self.f=app_fixture.TaskCenterAppTests();self.f.setUp();self.f.server.shutdown();self.f.server.server_close();self.f.thread.join(2)
  self.contract={'task_id':'demo-b','spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,'entry':'TEST_ONLY','target_repository':'owner/repo','target_base_sha':'c'*40,'developer':{'issuer':'fixture','subject':'dev'},'allowed_files':['module.py'],'trusted_reviewers':[{'issuer':'fixture','subject':'qa','role':'QA','key_id':'fixture-qa'},{'issuer':'fixture','subject':'sec','role':'SECURITY','key_id':'fixture-sec'}]}
  digest=hashlib.sha256(canonical(self.contract).encode()).hexdigest();rows=[]
  for role,phase,kind,subject in [('dev','EXECUTOR',None,'dev'),('qa','REVIEWER','QA','qa'),('sec','REVIEWER','SECURITY','sec')]:
   profile={'project_id':'demo-project','role_id':role,'role_version':'v1','principal_id':role,'repository':'owner/repo','branch':'main','repository_root':'/fixture','resource_key':'fake:demo-b','allowed_file':'module.py','max_source_bytes':1000} if phase=='EXECUTOR' else None
   rows.append({'tenant_id':'tenant-ui','principal_id':role,'project_id':'demo-project','task_id':'demo-b','spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,'contract_sha256':digest,'role_id':role,'role_version':'v1','phase':phase,'review_kind':kind,'authority_identity':{'issuer':'fixture','subject':subject},'actions':['task_development_status'],'candidate_root':None,'executor_profile':profile})
  self.contract_path=os.path.join(self.f.root,'contracts.json');self.config_path=os.path.join(self.f.root,'config.json')
  self.write(self.contract_path,{'demo-b':self.contract})
  self.cfg={'schema_version':1,'enabled':True,'bindings':rows,'review_keyring_file':None,'writer_context_file':None,'contract_file':self.contract_path}
  self.write(self.config_path,self.cfg);self.host=load_host(self.config_path)
  handler=build_handler(self.f.db,KEY,'tenant-ui','viewer',Fernet.generate_key(),admin_token='test-admin-token-123456',mcp_development_host=self.host)
  self.f.server=TaskCenterHTTPServer(('127.0.0.1',0),handler);self.f.thread=threading.Thread(target=self.f.server.serve_forever);self.f.thread.daemon=True;self.f.thread.start();self.f.base='http://127.0.0.1:%s'%self.f.server.server_port
 def tearDown(self):self.f.tearDown()
 def write(self,path,value):
  with open(path,'w') as out:json.dump(value,out)
  os.chmod(path,0o600)
 def post(self,body,auth=True):
  h={'Content-Type':'application/json'}
  if auth:h['X-Test-Admin-Token']='test-admin-token-123456'
  r=Request(self.f.base+'/api/admin/model-control',data=json.dumps(body).encode(),headers=h,method='POST')
  try:
   x=urlopen(r,timeout=3);return x.status,json.loads(x.read())
  except HTTPError as x:return x.code,json.loads(x.read())
 def request(self,**extra):return dict(action='REGISTER_DEVELOPMENT_CONTRACT',task_id='demo-b',**extra)
 def test_trusted_file_and_idempotent(self):
  c,r=self.post(self.request());self.assertEqual(c,200,r);self.assertFalse(r['duplicate'])
  c,r=self.post(self.request());self.assertEqual(c,200,r);self.assertTrue(r['duplicate'])
  s=Supervisor(self.f.db)
  try:self.assertEqual(s.development_contract('demo-b'),self.contract)
  finally:s.close()
 def test_unauthorized(self):
  c,r=self.post(self.request(),False);self.assertEqual((c,r['error']),(403,'ADMIN_REQUIRED'))
 def test_body_tamper_rejected(self):
  c,r=self.post(self.request(contract=self.contract));self.assertEqual((c,r['detail']),(400,'EXACT_DEVELOPMENT_REGISTRATION_ARGUMENTS_REQUIRED'))
 def test_wrong_base_rejected_against_pin(self):
  obj=copy.deepcopy(self.contract);obj['target_base_sha']='d'*40;self.write(self.contract_path,{'demo-b':obj})
  c,r=self.post(self.request());self.assertEqual((c,r['detail']),(400,'CURRENT_PINNED_DEVELOPMENT_SCOPE_REQUIRED'))
 def test_wrong_tenant_binding_rejected(self):
  for b in self.host.bindings:b['tenant_id']='another-tenant'
  c,r=self.post(self.request());self.assertEqual((c,r['detail']),(400,'DEVELOPMENT_HOST_ACTION_REQUIRED'))
 def test_no_provider_hold(self):
  self.host.contract_provider=None;c,r=self.post(self.request());self.assertEqual((c,r['detail']),(400,'HOLD_TRUSTED_DEVELOPMENT_CONTRACT_UNAVAILABLE'))
 def test_original_ready_constraint(self):
  s=Supervisor(self.f.db)
  try:
   s.db.execute("UPDATE tasks SET state='STARTED' WHERE task_id='demo-b'");s.db.commit()
  finally:s.close()
  c,r=self.post(self.request());self.assertEqual((c,r['detail']),(400,'CANONICAL_DEVELOPMENT_CONTRACT_MISMATCH'))
 def test_reviewer_key_tamper_rejected(self):
  obj=copy.deepcopy(self.contract);obj['trusted_reviewers'][0]['key_id']='changed';self.write(self.contract_path,{'demo-b':obj})
  c,r=self.post(self.request());self.assertEqual((c,r['detail']),(400,'CURRENT_PINNED_DEVELOPMENT_SCOPE_REQUIRED'))
 def test_reviewer_mapping_rejected(self):
  self.host.bindings[-1]['authority_identity']['subject']='other'
  c,r=self.post(self.request());self.assertEqual((c,r['detail']),(400,'CANONICAL_DEVELOPMENT_IDENTITY_REQUIRED'))
if __name__=='__main__':unittest.main()
