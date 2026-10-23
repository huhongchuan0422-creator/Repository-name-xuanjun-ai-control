"""Real Flask entry with synthetic GitHub adapter; no network or live credentials."""
import unittest
from unittest.mock import patch,Mock
from tests.oauth import test_oauth_consent_csp as t
from production.cloud_connection import oauth_authority as m
class Tests(unittest.TestCase):
 def setUp(self):
  self.b=t.Fixture();self.b.setUp();self.c=self.b.client(m);self.db=self.b.keeper
  self.gh=self.c.application.extensions['authlib.integrations.flask_client'].create_client('github')
  self.token=patch.object(self.gh,'authorize_access_token',return_value={'access_token':'SYNTHETIC_NEVER_TRANSMITTED'}).start()
  self.response=Mock(status_code=200);self.response.json.return_value={'id':332398908}
  self.get=patch.object(self.gh,'get',return_value=self.response).start()
 def tearDown(self):patch.stopall();self.b.tearDown()
 def start(self):self.assertEqual(self.c.get('/authorize',query_string=t.args(),base_url=t.ISSUER).status_code,302)
 def call(self):return self.c.get('/github/callback',base_url=t.ISSUER,follow_redirects=False)
 def failed(self,label):
  r=self.call();self.assertEqual(r.status_code,401);self.assertEqual(r.headers['X-Xuanjun-OAuth-Stage'],label);self.assertIn('<p>OAuth stage: '+label+'</p>',r.get_data(as_text=True));self.assertEqual(int(r.headers['Content-Length']),len(r.get_data()))
  self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertEqual(r.headers['Referrer-Policy'],'no-referrer')
  self.assertNotIn('SYNTHETIC',str(r.headers)+r.get_data(as_text=True));self.assertNotIn('sensitive_exception',str(r.headers)+r.get_data(as_text=True))
  self.assertEqual(self.db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0],0)
 def test_missing_flow(self):self.failed('FLOW_VALID');self.token.assert_not_called()
 def test_expired_flow(self):self.start();self.db.execute('UPDATE oauth_flows SET expires=0');self.db.commit();self.failed('FLOW_VALID')
 def test_used_flow(self):self.start();self.db.execute('UPDATE oauth_flows SET used=1');self.db.commit();self.failed('FLOW_VALID')
 def test_token_exception(self):self.start();self.token.side_effect=ValueError('sensitive_exception');self.failed('TOKEN_EXCHANGE')
 def test_user_transport(self):self.start();self.get.side_effect=ValueError('sensitive_exception');self.failed('USER_HTTP')
 def test_user_status(self):self.start();self.response.status_code=403;self.failed('USER_HTTP')
 def test_user_json(self):self.start();self.response.json.side_effect=ValueError('sensitive_exception');self.failed('USER_SHAPE')
 def test_user_shape(self):self.start();self.response.json.return_value={'id':True};self.failed('USER_SHAPE')
 def test_subject(self):self.start();self.response.json.return_value={'id':1};self.failed('SUBJECT_ALLOWED')
 def test_deadline(self):
  self.start()
  with patch.object(m.time,'monotonic',side_effect=[10,16]):self.failed('DEADLINE')
 def test_bind_conflict(self):
  self.start();self.db.execute("UPDATE oauth_flows SET sub='github:332398908'");self.db.commit();self.failed('FLOW_BIND')
 def test_success_unchanged(self):
  self.start();r=self.call();self.assertEqual((r.status_code,r.headers['Location']),(302,'/consent'));self.assertNotIn('X-Xuanjun-OAuth-Stage',r.headers)
 def test_other_route_no_header(self):self.assertNotIn('X-Xuanjun-OAuth-Stage',self.c.get('/consent',base_url=t.ISSUER).headers)
 def test_boundary_400_no_header(self):
  self.start();r=self.c.get('/github/callback',base_url='http://authority.example.test');self.assertEqual(r.status_code,400);self.assertNotIn('X-Xuanjun-OAuth-Stage',r.headers)
if __name__=='__main__':unittest.main()
