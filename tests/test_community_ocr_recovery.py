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


class SafeReadDiagnostics(unittest.TestCase):
 def test_payload_and_log_are_allowlisted_and_share_random_id(self):
  import json
  from scripts.community_ocr_host import _RequestDiagnostic,_attach_failure,OcrPublicError
  context=_RequestDiagnostic('read');context.phase('RESULT_READ')
  with self.assertLogs('community.ocr.diagnostic',level='WARNING') as logs:
   error=_attach_failure(RuntimeError('SYNTHETIC_SECRET_AND_CUSTOMER_DATA'),context)
   payload=OcrPublicError('OCR_UNAVAILABLE',error.ocr_diagnostic).public_payload()
   _attach_failure(PermissionError('OCR_OWNER_TIMEOUT'),context)
  diagnostic=payload['ocr_diagnostic']
  self.assertEqual(len(logs.output),1)
  self.assertEqual(diagnostic['reason'],'RESULT_READ_FAILED')
  self.assertRegex(diagnostic['diagnostic_id'],'^[a-f0-9]{32}$')
  self.assertIn(diagnostic['diagnostic_id'],logs.output[0])
  self.assertNotIn('SYNTHETIC_SECRET',str(payload)+str(logs.output))
  self.assertEqual(set(diagnostic),{'version','diagnostic_id','stage','reason','retryable','request_retained'})
  self.assertNotEqual(diagnostic['diagnostic_id'],_RequestDiagnostic('read').diagnostic_id)
 def test_invalid_external_metadata_never_echoed(self):
  from scripts.community_ocr_host import safe_diagnostic,OcrPublicError
  self.assertIsNone(safe_diagnostic({'version':1,'reason':'SYNTHETIC_SECRET'}))
  diagnostic=OcrPublicError('OCR_UNAVAILABLE').ocr_diagnostic
  self.assertNotIn('secret',safe_diagnostic(dict(diagnostic,secret='must-not-return')))
  self.assertIsNone(safe_diagnostic(dict(diagnostic,diagnostic_id='private-value')))
  self.assertEqual(OcrPublicError('PRIVATE_ERROR_BODY',diagnostic).code,'OCR_UNAVAILABLE')
 def test_pending_distinguishes_retained_request_and_other_busy_request(self):
  from scripts.community_ocr_host import _RequestDiagnostic,_pending
  ctx=_RequestDiagnostic('read');ctx.phase('RESULT_READ')
  same=_pending(ctx,retained=True).ocr_diagnostic
  other=_pending(_RequestDiagnostic('submit'),retained=False,reason='ANOTHER_REQUEST_IN_PROGRESS').ocr_diagnostic
  self.assertTrue(same['retryable']);self.assertTrue(same['request_retained'])
  self.assertFalse(other['request_retained']);self.assertNotEqual(same['diagnostic_id'],other['diagnostic_id'])
 def test_idle_pump_preserves_original_worker_context_and_owner_thread(self):
  from scripts.community_ocr_host import _RequestDiagnostic,_CURRENT_DIAGNOSTIC,current_diagnostic
  from scripts.community_ocr_bridge import on_owner
  owner=OwnerCalls(timeout=1);expected=_RequestDiagnostic('read');seen=[]
  class Bridge:
   owner_thread=threading.get_ident();owner_call=owner
   @on_owner
   def authenticate(self, token):
    seen.append((threading.get_ident(),current_diagnostic().diagnostic_id,current_diagnostic().stage))
    raise ValueError('SYNTHETIC_SECRET')
  def work():
   reset=_CURRENT_DIAGNOSTIC.set(expected)
   try:return Bridge().authenticate('SYNTHETIC_TOKEN')
   finally:_CURRENT_DIAGNOSTIC.reset(reset)
  with concurrent.futures.ThreadPoolExecutor(1) as pool:
   f=pool.submit(work)
   deadline=time.monotonic()+2
   while owner.pending.empty() and time.monotonic()<deadline:time.sleep(.001)
   self.assertFalse(owner.pending.empty());owner.pump()
   with self.assertRaises(ValueError) as caught:f.result()
  self.assertEqual(seen,[(threading.get_ident(),expected.diagnostic_id,'AUTHENTICATION')])
  self.assertEqual(caught.exception.ocr_diagnostic['reason'],'AUTHENTICATION_FAILED')
  self.assertEqual(caught.exception.ocr_diagnostic['diagnostic_id'],expected.diagnostic_id)
  self.assertIsNone(current_diagnostic());owner.close()
 def test_queued_owner_timeout_is_bounded_and_never_executes_late(self):
  from scripts.community_ocr_host import _RequestDiagnostic
  owner=OwnerCalls(timeout=.03);called=[];ctx=_RequestDiagnostic('read')
  def operation():called.append(1)
  operation.ocr_context=ctx;operation.ocr_stage='SOURCE_BINDING'
  with concurrent.futures.ThreadPoolExecutor(1) as pool:
   f=pool.submit(owner,operation)
   with self.assertRaisesRegex(PermissionError,'OCR_OWNER_TIMEOUT') as caught:f.result(timeout=1)
  self.assertEqual(caught.exception.ocr_diagnostic['reason'],'OWNER_WAIT_TIMEOUT')
  self.assertEqual(caught.exception.ocr_diagnostic['stage'],'SOURCE_BINDING')
  owner.pump();owner.close();self.assertEqual(called,[])
 def test_running_owner_callback_keeps_original_timeout_without_unbounded_wait(self):
  owner=OwnerCalls(timeout=.03);returned=[]
  def operation():time.sleep(.07);returned.append(True)
  with concurrent.futures.ThreadPoolExecutor(1) as pool:
   f=pool.submit(owner,operation)
   while owner.pending.empty():time.sleep(.001)
   owner.pump()
   with self.assertRaisesRegex(PermissionError,'OCR_OWNER_TIMEOUT'):f.result()
  self.assertEqual(returned,[True]);owner.close()
 def test_public_gateway_preserves_infrastructure_reason_swallowed_by_api(self):
  from scripts.community_ocr_host import _RequestDiagnostic,OcrPublicError
  from scripts.community_mini_merchant import MiniMerchant
  h=HostOcr.__new__(HostOcr);identity=object();onboarding=object()
  h.merchant=SimpleNamespace(identity=identity,onboarding=onboarding)
  context=_RequestDiagnostic('read');context.phase('SOURCE_BINDING')
  error=PermissionError('ATTACHMENT_AUTHORIZATION_REVOKED')
  error.ocr_diagnostic=context.fail(reason='OWNER_WAIT_TIMEOUT')
  def dispatch(*args):raise error
  h.dispatch=dispatch
  gateway=SimpleNamespace(ocr=h,identity=identity,onboarding=onboarding)
  with self.assertRaises(OcrPublicError) as caught:MiniMerchant._dispatch_ocr(gateway,'synthetic','',{})
  self.assertEqual(caught.exception.code,'OCR_UNAVAILABLE')
  self.assertEqual(caught.exception.ocr_diagnostic['diagnostic_id'],context.diagnostic_id)
  self.assertEqual(caught.exception.ocr_diagnostic['reason'],'OWNER_WAIT_TIMEOUT')
 def test_serial_platform_serve_composes_existing_housekeeping_and_owner_pump(self):
  from scripts.community_platform_host import PlatformHost
  calls=[];owner_thread=threading.get_ident()
  class Server:
   def service_actions(self):calls.append(('original',threading.get_ident()))
   def serve_forever(self,*,poll_interval):
    self.poll_interval=poll_interval
    self.service_actions()
  server=Server();h=PlatformHost.__new__(PlatformHost)
  h.application=SimpleNamespace(listen_proxy=lambda *a:server)
  h.plan=dict(socket_path='synthetic',https_origin='synthetic',nginx_uid=1,nginx_gid=1)
  h.ocr=SimpleNamespace(service_actions=lambda:calls.append(('ocr',threading.get_ident())))
  h.close=lambda:calls.append(('close',threading.get_ident()))
  h.serve()
  self.assertEqual(server.poll_interval,.25)
  self.assertEqual(calls,[('original',owner_thread),('ocr',owner_thread),('close',owner_thread)])


class LateReadBinding(unittest.TestCase):
 def service(self, action, change=None):
  import httpx
  from scripts.community_ocr_host import _RequestDiagnostic
  h=HostOcr.__new__(HostOcr);h.owner=OwnerCalls();h.scene='';h.applicant_mode=True;h.busy=False
  job=dict(job_id='11111111-1111-1111-1111-111111111111',subject='synthetic-owner',tenant_id='synthetic-tenant',onboarding_application_id='synthetic-application',document_type='business_license',application_revision='1',provider_version=1,attachment_id='synthetic-attachment',document_sha256='a'*64,status='needs_review')
  source=dict(data=b'SYNTHETIC',mime='image/png',document_type=job['document_type'],application_revision='1',wechat_version=1,attachment_id=job['attachment_id'],document_sha256=job['document_sha256'])
  if change:source.update(change)
  h.bridge=SimpleNamespace(authenticate=lambda token:SimpleNamespace(subject=job['subject'],tenant_id=job['tenant_id']),authorize_application=lambda *a:True,source=lambda *a:dict(source),store=SimpleNamespace(get=lambda *a:dict(job)))
  params=dict(action=action,application=job['onboarding_application_id'],job_id=job['job_id'])
  if action=='confirm':params.update(revision=1,fields={'company_name':'SYNTHETIC CONFIRMED'},idempotency_key='synthetic-confirm-001',application_revision='1',provider_version=1)
  h.inflight=concurrent.futures.Future();h.inflight.set_result(httpx.Response(200,json={'job_id':job['job_id'],'status':job['status'],'fields':{'company_name':{'value':'SYNTHETIC OLD VALUE'}}}))
  h.inflight_key=('synthetic-token','',repr(sorted(params.items())));h.inflight_source=None;h.inflight_diagnostic=_RequestDiagnostic(action)
  # No worker/app exists: dispatch must consume only the original completed future.
  return h,params,job
 def assert_changed(self, change, reason):
  for action in ('read','confirm'):
   with self.subTest(action=action):
    h,params,before=self.service(action,change)
    with self.assertRaisesRegex(PermissionError,'OCR_SOURCE_CHANGED') as caught:h.dispatch('synthetic-token','',params)
    diagnostic=caught.exception.ocr_diagnostic
    self.assertEqual(diagnostic['stage'],'SOURCE_BINDING');self.assertEqual(diagnostic['reason'],reason)
    self.assertTrue(diagnostic['request_retained'])
    self.assertEqual(h.bridge.store.get(before['job_id'],before['tenant_id']),before)
    h.owner.close()
 def test_completed_read_and_confirm_recheck_revision(self):
  self.assert_changed({'application_revision':'2'},'APPLICATION_REVISION_CHANGED')
 def test_completed_read_and_confirm_recheck_attachment_and_content(self):
  for change in ({'attachment_id':'synthetic-replacement'},{'document_sha256':'b'*64}):self.assert_changed(change,'ATTACHMENT_CHANGED')
 def test_completed_read_and_confirm_recheck_provider_value_and_type(self):
  for value in (2,True,None):self.assert_changed({'wechat_version':value},'PROVIDER_VERSION_CHANGED')
 def test_unchanged_completed_read_and_confirm_release_same_future_without_worker(self):
  for action in ('read','confirm'):
   h,params,before=self.service(action)
   result=h.dispatch('synthetic-token','',params)
   self.assertEqual(result['status_code'],200);self.assertEqual(result['result']['job_id'],before['job_id'])
   self.assertIsNone(h.inflight);h.owner.close()

if __name__=='__main__':unittest.main()
