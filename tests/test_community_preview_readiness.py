import io,json,os,time,unittest
from unittest.mock import patch
from email.message import Message
from scripts.community_preview_readiness import check,URL

class HealthGate(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,GITHUB_SHA='a'*40);self.env.start();self.addCleanup(self.env.stop)

 def response(self,status=200,body=None,content_type='application/json',url=URL):
  response=io.BytesIO(json.dumps(body if body is not None else dict(
      status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
      runtime_source_sha='a'*40,version_source='IMAGE_BUILD_STAMP',observed_at=int(time.time()))).encode())
  response.status=status;response.headers=Message();response.headers['Content-Type']=content_type
  response.geturl=lambda:url
  return response
 def test_fixed_health_ready_is_connectivity_only(self):
  def open_url(request,timeout):
   self.assertEqual(request.full_url,URL);self.assertEqual(timeout,10)
   return self.response()
  report=check(open_url)
  self.assertEqual(report['status'],'BACKEND_HEALTH_VERIFIED')
  self.assertFalse(report['login_verified']);self.assertFalse(report['customer_acceptance'])
 def test_unavailable_maintenance_html_redirect_and_false_acceptance_fail_closed(self):
  variants=[dict(status=503),dict(body={'status':'MAINTENANCE'}),
      dict(content_type='text/html'),dict(url='https://other.invalid/'),
      dict(body={'status':'READY','scope':'PROCESS_AND_DATABASE_CONNECTIVITY','production_acceptance':True})]
  for variant in variants:
   with self.subTest(variant=variant):
    self.assertEqual(check(lambda *a,**k:self.response(**variant))['status'],'BACKEND_NOT_READY')
 def test_remote_version_is_required_not_local_sha_and_never_assumes_compatibility(self):
  good=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
      runtime_source_sha='a'*40,version_source='IMAGE_BUILD_STAMP',observed_at=int(time.time()))
  for key,value in [('runtime_source_sha',None),('runtime_source_sha','b'*40),('runtime_source_sha','bad'),
                    ('version_source','CLIENT_ENV'),('observed_at',0),('observed_at',True),
                    ('observed_at',int(time.time())+601)]:
   with self.subTest(key=key,value=value):
    report=check(lambda *a,**k:self.response(body=dict(good,**{key:value})))
    self.assertEqual(report['status'],'BACKEND_NOT_READY')
    self.assertEqual(report['compatibility'],'UNVERIFIED')
  report=check(lambda *a,**k:self.response(body=good))
  self.assertEqual(report['frontend_source_sha'],'a'*40)
  self.assertEqual(report['backend_source_sha'],'a'*40)
  self.assertEqual(report['compatibility'],'EXACT_SOURCE_MATCH')
  self.assertNotIn('source_sha',report)
 def test_missing_frontend_sha_stops_before_io(self):
  with patch.dict(os.environ,GITHUB_SHA=''):
   self.assertEqual(check(lambda *a,**k:self.fail('must not connect'))['status'],'BACKEND_NOT_READY')
 def test_clock_is_checked_after_remote_read(self):
  # A valid-looking response becomes stale while the request is being read.
  good=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
      runtime_source_sha='a'*40,version_source='IMAGE_BUILD_STAMP',observed_at=100)
  with patch('scripts.community_preview_readiness.time.time',return_value=701):
   self.assertEqual(check(lambda *a,**k:self.response(body=good))['status'],'BACKEND_NOT_READY')
 def test_network_failure_is_sanitized(self):
  def fail(*a,**k):raise TimeoutError('sensitive fixture detail')
  report=check(fail)
  self.assertEqual(report['status'],'BACKEND_NOT_READY')
  self.assertNotIn('sensitive',json.dumps(report))

 def test_current_d8b_product_accepts_only_ready_d8b_backend(self):
  frontend='d8b65bf3aa022c5f184b6307fb40a84acfcd2b11';backend='d8b65bf3aa022c5f184b6307fb40a84acfcd2b11'
  identity=dict(product_source_sha=frontend,control_source_sha='c'*40,fixed_product=True,
      backend_source_sha=backend,compatibility='EXACT_SOURCE_MATCH')
  health=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
      runtime_source_sha=backend,version_source='IMAGE_BUILD_STAMP',observed_at=int(time.time()))
  url='https://uk.wenwenwenyiyiyi.work/community-preview/community/health'
  ready=check(lambda *a,**k:self.response(body=health,url=url),profile='uk-path-candidate',product_identity=identity)
  self.assertEqual((ready['status'],ready['frontend_source_sha'],ready['backend_source_sha'],ready['compatibility']),
      ('BACKEND_HEALTH_VERIFIED',frontend,backend,'EXACT_SOURCE_MATCH'))
  wrong=check(lambda *a,**k:self.response(body=dict(health,runtime_source_sha='b'*40),url=url),
      profile='uk-path-candidate',product_identity=identity)
  self.assertEqual(wrong['status'],'BACKEND_NOT_READY')
  oldpair=check(lambda *a,**k:self.response(body=dict(health,runtime_source_sha='48df407f30f512b1456270c8faba22f095404b9f'),url=url),profile='uk-path-candidate',product_identity=dict(identity,product_source_sha='44e7344b9a0b00b3999e64eaf90c243d98f7c001',backend_source_sha='48df407f30f512b1456270c8faba22f095404b9f'))
  self.assertEqual(oldpair['status'],'BACKEND_NOT_READY')
  stale=check(lambda *a,**k:self.response(body=health,url=url),profile='uk-path-candidate',
      product_identity=dict(identity,product_source_sha='28ca2f0c66305a2bca4fa6e27cf27427f36aaefd'))
  self.assertEqual(stale['status'],'BACKEND_NOT_READY')

if __name__=='__main__':unittest.main()
