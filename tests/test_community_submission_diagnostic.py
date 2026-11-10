"""Synthetic diagnostic privacy, isolation, bounded sink and real HTTP mapping."""
import io,json,queue,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
from scripts import community_submission_diagnostic as d
from scripts.pr122_customer_core import Denied
from scripts.community_license_region import RegionValidationError
from test_community_applicant_applyment import ApplicantApplyment

class Diagnostics(unittest.TestCase):
 def trace(self,fn,op='wechat_apply'):
  @d.request_scope
  def go():
   d.select({'operation':'onboarding','params':{'operation':op,'secret':'NEVER_LOG_ID_ADDRESS_TOKEN'}})
   return fn()
  return go()
 def test_exact_fields_and_secret_absence(self):
  def fn():
   d.mark('PROFILE');d.failure(ValueError('NEVER_LOG_ID_ADDRESS_TOKEN'))
   return d.response(400,{'error':'INVALID_REQUEST'})['submission_diagnostic']
  value=self.trace(fn)
  self.assertEqual(set(value),{'operation','stage','correlation_id','timestamp','status','code'})
  self.assertEqual(value['code'],'PROFILE_CHECK_FAILED');self.assertNotIn('NEVER_LOG',json.dumps(value))
  self.assertRegex(value['correlation_id'],r'^[a-f0-9]{32}$');self.assertIsNone(d._CONTEXT.get())
 def test_request_ids_distinct_and_context_reset_on_exception(self):
  a=self.trace(lambda:d.snapshot('STARTED'));b=self.trace(lambda:d.snapshot('STARTED'))
  self.assertNotEqual(a['correlation_id'],b['correlation_id'])
  with self.assertRaises(ValueError):self.trace(lambda:(_ for _ in ()).throw(ValueError('secret')))
  self.assertIsNone(d._CONTEXT.get())
 def test_full_sink_cannot_block_request(self):
  full=queue.Queue(1);full.put('occupied')
  with patch.object(d,'_EVENTS',full):
   value=self.trace(lambda:d.response(200,{'result':'ok'}))
  self.assertEqual(value['result'],'ok')
 def test_nonselected_operations_emit_nothing(self):
  with patch.object(d,'_EVENTS') as sink:
   self.trace(lambda:d.response(200,{'result':'ok'}),op='upload')
   sink.put_nowait.assert_not_called()
 def test_unknown_stage_and_error_are_not_echoed(self):
  def fn():
   d.mark('SECRET_ADDRESS');d.failure(RuntimeError('SECRET_ADDRESS'));return d.response(503,{})
  v=self.trace(fn)['submission_diagnostic'];self.assertEqual(v['stage'],'DISPATCH');self.assertEqual(v['code'],'SERVICE_UNAVAILABLE')
 def test_parallel_request_context_ids_do_not_mix(self):
  barrier=threading.Barrier(2);values=[]
  def worker(op):
   def fn():barrier.wait(timeout=3);values.append(d.response(200,{})['submission_diagnostic'])
   self.trace(fn,op)
  threads=[threading.Thread(target=worker,args=(op,)) for op in ('read','wechat_status')]
  for t in threads:t.start()
  for t in threads:t.join(4);self.assertFalse(t.is_alive())
  self.assertEqual({v['operation'] for v in values},{'read','wechat_status'});self.assertEqual(len({v['correlation_id'] for v in values}),2)

 def test_authentication_before_body_has_unknown_operation_not_guessed(self):
  @d.request_scope
  def go():
   d.begin();d.mark('AUTHENTICATION');d.failure(PermissionError('PRIVATE_TOKEN'))
   return d.response(403,{'error':'ACCESS_DENIED'})['submission_diagnostic']
  result=go();self.assertEqual(result['operation'],'UNKNOWN');self.assertEqual(result['stage'],'AUTHENTICATION');self.assertEqual(result['code'],'ACCESS_DENIED');self.assertNotIn('PRIVATE',json.dumps(result))
 def test_parse_selection_keeps_request_random_id(self):
  @d.request_scope
  def go():
   d.begin();before=d.snapshot('STARTED')['correlation_id']
   d.select({'operation':'onboarding','params':{'operation':'submit'}})
   self.assertEqual(d.snapshot('STARTED')['correlation_id'],before)
  go()

class HttpDiagnostics(unittest.TestCase):
 def test_original_http_error_mapping_and_public_whitelist(self):
  from test_community_mini_center_identity import ExistingCenterComposition
  from scripts.community_merchant_onboarding import MerchantOnboarding
  from scripts.community_mini_http import serve
  from scripts.community_mini_merchant import MiniMerchant
  fx=ExistingCenterComposition();fx.setUp();self.addCleanup(fx.tearDown)
  onboarding=MerchantOnboarding(fx.center,{fx.uid2:'project1'})
  server=serve(fx.gateway,onboarding=onboarding);self.addCleanup(server.server_close);server.timeout=2
  errors=[(Denied('RATE_LIMIT'),429,'RATE_LIMIT'),(ValueError('WECHAT_APPLYMENT_VERSION_CONFLICT'),400,'VERSION_CONFLICT'),(ValueError('SECRET_ADDRESS_TOKEN'),400,'INVALID_REQUEST')]
  # Original RegionValidationError constructor takes a resolver result.
  from scripts.community_license_region import validate
  try:validate('',None)
  except RegionValidationError as e:errors.append((e,400,'MINI_LICENSE_REGION_INVALID'))
  for error,status,code in errors:
   result=[]
   def client():
    req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/mini/merchant',data=json.dumps({'operation':'onboarding','params':{'operation':'wechat_apply','params':{}}}).encode(),headers={'Content-Type':'application/json','X-Community-Scene':'shop1','X-Community-Session':'synthetic'})
    try:
     with urllib.request.urlopen(req,timeout=3) as r:result.append((r.status,json.load(r)))
    except urllib.error.HTTPError as e:result.append((e.code,json.load(e)))
   with patch.object(MiniMerchant,'context',return_value=None),patch.object(MiniMerchant,'dispatch',side_effect=error):
    t=threading.Thread(target=client);t.start();server.handle_request();t.join(4)
   self.assertEqual(result[0][0],status);diag=result[0][1]['submission_diagnostic'];self.assertEqual(diag['code'],code);self.assertNotIn('SECRET',json.dumps(diag))


  # Real original authentication rejects the synthetic invalid session before
  # reading/dispatching the operation. This does not mock the auth context.
  result=[]
  with patch.object(MiniMerchant,'dispatch') as dispatch:
   t=threading.Thread(target=client);t.start();server.handle_request();t.join(4)
   dispatch.assert_not_called()
  self.assertEqual(result[0][0],403)
  auth=result[0][1]['submission_diagnostic']
  self.assertEqual((auth['operation'],auth['stage'],auth['code']),('UNKNOWN','AUTHENTICATION','ACCESS_DENIED'))

class ApplyDiagnostic(ApplicantApplyment):
 def test_diagnostic_unknown_is_still_one_intent_no_repost(self):
  @d.request_scope
  def go():
   d.select({'operation':'onboarding','params':{'operation':'wechat_apply'}})
   with self.response(error=TimeoutError('SECRET')):
    try:self.apply()
    except TimeoutError as e:d.failure(e)
   return d.response(408,{})['submission_diagnostic']
  diag=go();self.assertEqual(diag['stage'],'PROVIDER_POST');self.assertEqual(diag['code'],'PROVIDER_RESULT_UNKNOWN')
  self.assertEqual(len(self.attempts()),1);self.provider.reset_mock()
  with self.assertRaises(PermissionError):self.apply()
  self.provider.assert_not_called()
