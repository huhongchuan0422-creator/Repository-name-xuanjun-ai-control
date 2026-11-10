"""Synthetic original HTTP/body and platform-submit boundary regression."""
import json,socket,threading,unittest
from unittest.mock import patch
from scripts import community_submission_diagnostic as d
from scripts.community_mini_http import serve
from scripts.community_mini_merchant import MiniMerchant
from test_community_merchant_onboarding import MerchantAdmissionJourney

class DiagnosticBoundaries(unittest.TestCase):
 def setUp(self):
  self.fx=MerchantAdmissionJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
 def test_authenticated_original_http_bad_body_is_not_authentication_failure(self):
  token=self.fx.fx.token();server=serve(self.fx.fx.gateway,onboarding=self.fx.service);server.timeout=3;self.addCleanup(server.server_close)
  for mode,raw,length,expected_status,stage in [('bad_json',b'{',1,400,'BODY_PARSE'),('truncated',b'{',2,400,'REQUEST_BODY'),('timeout',b'',1,408,'REQUEST_BODY'),('empty',b'',0,400,'REQUEST_BODY')]:
   with self.subTest(mode=mode):
    output=[]
    def client():
     with socket.create_connection(('127.0.0.1',server.server_port),timeout=4) as conn:
      head='POST /mini/merchant HTTP/1.1\r\nHost: 127.0.0.1:'+str(server.server_port)+'\r\nContent-Type: application/json\r\nX-Community-Session: '+token+'\r\nX-Community-Scene: shop1\r\nContent-Length: '+str(length)+'\r\n\r\n'
      conn.sendall(head.encode()+raw)
      if mode=='truncated':conn.shutdown(socket.SHUT_WR)
      chunks=[]
      while True:
       chunk=conn.recv(65536)
       if not chunk:break
       chunks.append(chunk)
      output.append(b''.join(chunks))
    with patch.object(MiniMerchant,'dispatch') as dispatch,patch('scripts.community_wechat_applyment.request') as provider:
     thread=threading.Thread(target=client);thread.start();server.handle_request();thread.join(5)
     self.assertFalse(thread.is_alive());dispatch.assert_not_called();provider.assert_not_called()
    head,body=output[0].split(b'\r\n\r\n',1);self.assertEqual(int(head.split()[1]),expected_status)
    diagnostic=json.loads(body)['submission_diagnostic'];self.assertEqual(diagnostic['operation'],'UNKNOWN');self.assertEqual(diagnostic['stage'],stage)
    self.assertNotIn(token,json.dumps(diagnostic));self.assertEqual(set(diagnostic),{'operation','stage','correlation_id','timestamp','status','code'})
 def test_original_platform_submit_missing_material_has_material_stage(self):
  self.check_platform(self.fx.draft(),'MATERIALS')
 def test_original_platform_submit_unconfirmed_declarations_has_declaration_stage(self):
  self.check_platform(self.fx.draft(declarations={'scene':'unknown','ubos':'unknown'}),'DECLARATIONS')
 def check_platform(self,app,stage):
  @d.request_scope
  def attempt():
   d.select({'operation':'onboarding','params':{'operation':'submit'}})
   try:self.fx.call('submit',{'application':app['application'],'revision':app['revision']})
   except (ValueError,PermissionError) as error:d.failure(error)
   else:self.fail('expected existing gate to reject')
   return d.response(400,{'error':'INVALID_REQUEST'})['submission_diagnostic']
  with patch('scripts.community_wechat_applyment.request') as provider:diag=attempt();provider.assert_not_called()
  self.assertEqual(diag['stage'],stage);self.assertEqual(diag['operation'],'submit')
  for private in (app['application'],'Fixture Address','Fixture Contact'):self.assertNotIn(private,json.dumps(diag))
  result=self.fx.call('read',{'application':app['application']});self.assertEqual(result['status'],'DRAFT');self.assertEqual(result['revision'],app['revision'])
