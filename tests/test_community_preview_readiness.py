import io,json,unittest
from email.message import Message
from scripts.community_preview_readiness import check,URL

class HealthGate(unittest.TestCase):
 def response(self,status=200,body=None,content_type='application/json',url=URL):
  response=io.BytesIO(json.dumps(body if body is not None else dict(
      status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False)).encode())
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
 def test_network_failure_is_sanitized(self):
  def fail(*a,**k):raise TimeoutError('sensitive fixture detail')
  report=check(fail)
  self.assertEqual(report['status'],'BACKEND_NOT_READY')
  self.assertNotIn('sensitive',json.dumps(report))

if __name__=='__main__':unittest.main()
