"""Actual HostOcr dispatch/ASGI with synthetic bridge only; no production auth claim."""
import concurrent.futures, threading, unittest, time
from types import SimpleNamespace
from fastapi import FastAPI
from scripts.community_ocr_host import HostOcr, OwnerCalls
class Recovery(unittest.TestCase):
 def service(self):
  h=HostOcr.__new__(HostOcr);h.owner=OwnerCalls(timeout=.03);h.scene='';h.applicant_mode=True;h.busy=False;h.inflight=None;h.inflight_key=None;h.inflight_source=None
  self.release=threading.Event();self.calls=0;self.rev=1;self.allowed=True
  h.bridge=SimpleNamespace(authenticate=lambda t:SimpleNamespace(subject='owner',tenant_id='tenant'),authorize_application=lambda p,a:self.allowed,source=lambda *a:dict(data=b'synthetic',mime='image/png',attachment_id='synthetic',document_type='business_license',application_revision=str(self.rev)),store=SimpleNamespace(get=lambda *a:None))
  app=FastAPI()
  @app.post('/api/v1/ocr/jobs')
  async def run():
   self.calls+=1;self.release.wait(1);return {'job_id':'synthetic-job','status':'needs_review'}
  h.app=app;h.worker=concurrent.futures.ThreadPoolExecutor(1);self.addCleanup(self.release.set);self.addCleanup(h.close)
  return h
 def params(self,key='synthetic-key-00001'):return dict(action='submit',application='a',document_type='business_license',idempotency_key=key)
 def test_timeout_retains_future_retry_no_duplicate_and_host_open(self):
  h=self.service()
  with self.assertRaisesRegex(PermissionError,'OCR_REQUEST_PENDING'):h.dispatch('token','',self.params())
  original=h.inflight;self.assertFalse(h.owner.closed)
  with self.assertRaisesRegex(PermissionError,'OCR_REQUEST_PENDING'):h.dispatch('token','',self.params('different-key-00001'))
  self.assertIs(h.inflight,original);self.release.set();h.owner.timeout=1
  self.assertEqual(h.dispatch('token','',self.params())['result']['job_id'],'synthetic-job');self.assertEqual(self.calls,1);self.assertIsNone(h.inflight)
 def test_source_change_after_timeout_denied(self):
  h=self.service()
  with self.assertRaisesRegex(PermissionError,'PENDING'):h.dispatch('token','',self.params())
  self.rev=2
  with self.assertRaisesRegex(PermissionError,'SOURCE_CHANGED'):h.dispatch('token','',self.params())
  self.assertEqual(self.calls,1);self.release.set()
 def test_revoked_application_cannot_resume(self):
  h=self.service()
  with self.assertRaisesRegex(PermissionError,'PENDING'):h.dispatch('token','',self.params())
  self.allowed=False
  with self.assertRaisesRegex(PermissionError,'APPLICATION_DENIED'):h.dispatch('token','',self.params())
  self.release.set()
 def test_close_rejects_pending_owner_callbacks(self):
  owner=OwnerCalls(timeout=.2);called=[]
  with concurrent.futures.ThreadPoolExecutor(1) as pool:
   f=pool.submit(owner,lambda:called.append(1))
   while owner.pending.empty():time.sleep(.001)
   owner.close()
   with self.assertRaisesRegex(PermissionError,'STOPPED'):f.result()
  self.assertEqual(called,[])

class DurableRecovery(unittest.TestCase):
 def test_completed_durable_job_replayed_after_host_recreation_without_inference(self):
  import tempfile,hashlib
  from pathlib import Path
  from cryptography.fernet import Fernet
  import importlib.util,sys,os,json,subprocess
  lock=json.loads(Path('scripts/community_ocr_dependency.json').read_text())
  dep=tempfile.TemporaryDirectory();self.addCleanup(dep.cleanup);root=Path(dep.name)
  for name,digest_expected in lock['files'].items():
   source=os.environ.get('COMMUNITY_TEST_PINNED_OCR_DIR')
   data=(Path(source)/name).read_bytes() if source else subprocess.check_output(['git','show',lock['source_sha']+':services/ocr_engine/'+name])
   self.assertEqual(hashlib.sha256(data).hexdigest(),lock.get('upstream_files',lock['files'])[name])
   successor=lock.get('local_successor',{})
   if name in successor.get('source_files',{}):
    self.assertEqual(hashlib.sha256(Path(successor['patch_path']).read_bytes()).hexdigest(),successor['patch_sha256'])
    data=Path(successor['source_files'][name]).read_bytes()
   self.assertEqual(hashlib.sha256(data).hexdigest(),digest_expected);(root/name).write_bytes(data)
  (root/'__init__.py').write_text('')
  name='ocr_recovery_pinned_'+str(id(self))
  spec=importlib.util.spec_from_file_location(name,root/'__init__.py',submodule_search_locations=[str(root)])
  module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
  api=__import__(name+'.api',fromlist=['api'])
  with tempfile.TemporaryDirectory() as tmp:
   key=Fernet.generate_key();path=str(Path(tmp)/'ocr.sqlite');calls=[];raw=b'SYNTHETIC ONLY';digest=hashlib.sha256(raw).hexdigest()
   def make(store):
    h=HostOcr.__new__(HostOcr);h.owner=OwnerCalls(timeout=1);h.scene='';h.applicant_mode=True;h.busy=False;h.inflight=None;h.inflight_key=None;h.inflight_source=None;h.worker=concurrent.futures.ThreadPoolExecutor(1)
    principal=api.Principal(subject='synthetic-owner',tenant_id='synthetic-tenant',permissions={'ocr:use'})
    source=dict(data=raw,mime='image/png',attachment_id='synthetic-attachment',document_type='business_license',application_revision='1',document_sha256=digest)
    h.bridge=SimpleNamespace(authenticate=lambda t:principal,authorize_application=lambda p,a:True,source=lambda *a:dict(source),store=store)
    def binding(*a):return h.owner(lambda:dict(authorized=True,content_sha256=digest,document_type='business_license',application_revision='1'))
    def infer(*a,**kw):
     calls.append(1)
     if getattr(self,'slow',False):time.sleep(16)
     return {'fields':{}}
    h.app=api.create_app(authenticate=lambda t:h.owner(lambda:principal),store=store,infer=infer,authorize_application=lambda *a:h.owner(lambda:True),authorize_attachment=binding)
    return h
   store=api.SecureSQLiteJobStore(path,key)
   if getattr(self,'interrupted',False):
    job=store.create('synthetic-tenant','synthetic-owner','synthetic-app','business_license',digest,'same-durable-request-0001','synthetic-attachment','1',None)
    self.assertTrue(store.claim(job['job_id']))
    # Test owns this temporary store exclusively and has started no worker.
    store=api.SecureSQLiteJobStore(path,key)
    self.assertEqual(store.get(job['job_id'],'synthetic-tenant')['status'],'processing')
    store.recover_interrupted()
    recovered=store.get(job['job_id'],'synthetic-tenant');self.assertEqual(recovered['job_id'],job['job_id']);self.assertEqual(recovered['error_code'],'OCR_INTERRUPTED')
    self.assertIsNone(store.get(job['job_id'],'other-tenant'))
   h=make(store)
   p=dict(action='submit',application='synthetic-app',document_type='business_license',idempotency_key='same-durable-request-0001')
   try:
    if getattr(self,'slow',False):
     with self.assertRaisesRegex(PermissionError,'PENDING'):h.dispatch('token','',p)
     time.sleep(16.1)
     self.assertTrue(h.inflight.done());self.assertFalse(h.owner.closed)
    first=h.dispatch('token','',p)['result']['job_id']
   finally:h.close();h.worker.shutdown(wait=True)
   # Reopen encrypted journal, simulating a new host with no in-memory future.
   h=make(api.SecureSQLiteJobStore(path,key))
   try:
    self.assertEqual(h.dispatch('token','',p)['result']['job_id'],first)
    read=h.dispatch('token','',dict(action='read',application='synthetic-app',job_id=first))
    self.assertEqual(read['result']['status'],'failed' if getattr(self,'interrupted',False) else 'needs_review');self.assertEqual(calls,[] if getattr(self,'interrupted',False) else [1])
   finally:h.close();h.worker.shutdown(wait=True)

 def test_sixteen_second_inference_survives_no_owner_pump_between_requests(self):
  self.slow=True
  self.test_completed_durable_job_replayed_after_host_recreation_without_inference()

 def test_interrupted_durable_job_returns_failed_without_reinference(self):
  self.interrupted=True
  self.test_completed_durable_job_replayed_after_host_recreation_without_inference()

 def test_host_recovery_occurs_only_after_existing_exclusive_store_lock(self):
  import ast
  from pathlib import Path
  tree=ast.parse(Path('scripts/community_platform_host.py').read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='recover_interrupted']
  self.assertEqual(len(calls),1)
  fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='configure_applicant_ocr')
  source=ast.get_source_segment(Path('scripts/community_platform_host.py').read_text(),fn)
  self.assertLess(source.index('fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)'),source.index('store.recover_interrupted()'))
  self.assertLess(source.index('store.recover_interrupted()'),source.index("self.configure_ocr('',api,store,applicant_mode=True)"))

if __name__=='__main__':unittest.main()
