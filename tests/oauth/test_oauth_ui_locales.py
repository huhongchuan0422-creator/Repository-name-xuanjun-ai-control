"""Real Flask/Authlib test_client, original pinned source dependencies, offline only.
Uses synthetic client/state/challenge and an isolated in-memory SQLite schema.
Never follows /login or contacts GitHub; no live credentials or server commands.
"""
import sqlite3,json,unittest,uuid,socket
from unittest.mock import patch
from production.cloud_connection import oauth_authority as new

ISSUER='https://authority.example.test'
CALLBACK='https://client.example.test/callback'
def args():return [('client_id','offline-status-client'),('redirect_uri',CALLBACK),('resource',ISSUER+'/mcp'),('scope','connection.status'),('response_type','code'),('code_challenge_method','S256'),('code_challenge','A'*43),('state','B'*40)]
class Tests(unittest.TestCase):
 def setUp(self):
  self.net=patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK_FORBIDDEN'));self.netmock=self.net.start()
  self.dburi='file:local_ui_test_'+uuid.uuid4().hex+'?mode=memory&cache=shared'
  self.keeper=sqlite3.connect(self.dburi,uri=True);new.initialize_new_database(self.keeper)
 def tearDown(self):
  self.keeper.close();self.net.stop();self.assertEqual(self.netmock.call_count,0)
 def client(self,mod=new):
  config=dict(issuer=ISSUER,audience=ISSUER+'/mcp',github_client_id='offline-test-client',subjects=['github:332398908'],clients={'offline-status-client':dict(redirect_uris=[CALLBACK],auth_method='none',secret_hash='0'*64,resource_client=False)})
  app=mod.create_app(config,lambda:sqlite3.connect(self.dburi,uri=True),b'LOCAL-TEST-ONLY-NOT-A-SECRET'*2,'LOCAL-TEST-ONLY-NOT-A-GITHUB-SECRET',enabled=True)
  app.config['TESTING']=True
  return app.test_client()
 def request(self,parameters,mod=new,base_url=ISSUER):return self.client(mod).get('/authorize',query_string=parameters,base_url=base_url,follow_redirects=False)
 def rows(self):return self.keeper.execute('SELECT params FROM oauth_flows').fetchall()
 def test_candidate_real_authlib_next_stage(self):
  r=self.request(args()+[('ui_locales','zh-CN en-US')]);self.assertEqual(r.status_code,302);self.assertEqual(r.headers['Location'],'/login')
  rows=self.rows();self.assertEqual(len(rows),1);stored=json.loads(rows[0][0]);self.assertNotIn('ui_locales',stored);self.assertEqual(stored,dict(args()))
 def test_candidate_no_hint(self):self.assertEqual(self.request(args()).status_code,302)
 def test_valid_hint_bounds(self):
  for hint in ('x'*128,' '.join(['en']*8)):
   with self.subTest(hint_length=len(hint)):
    response=self.request(args()+[('ui_locales',hint)])
    self.assertEqual(response.status_code,302)
    self.assertEqual(response.headers['Location'],'/login')
  self.assertEqual(len(self.rows()),2)
  self.assertTrue(all('ui_locales' not in json.loads(row[0]) for row in self.rows()))
 def test_invalid_hints(self):
  for hint in ('','en_US','en\nUS','中文','x'*129,' '.join(['en']*9)):
   with self.subTest(hint=repr(hint)):self.assertEqual(self.request(args()+[('ui_locales',hint)]).status_code,400)
  self.assertEqual(self.rows(),[])
 def test_duplicate_hint(self):
  self.assertEqual(self.request(args()+[('ui_locales','en'),('ui_locales','zh-CN')]).status_code,400);self.assertEqual(self.rows(),[])
 def test_duplicate_security_fields(self):
  for key in ('client_id','resource','redirect_uri','state','scope','code_challenge'):
   with self.subTest(key=key):self.assertEqual(self.request(args()+[(key,'duplicate'),('ui_locales','en')]).status_code,400)
  self.assertEqual(self.rows(),[])
 def test_unknown_parameter(self):
  self.assertEqual(self.request(args()+[('unknown','x'),('ui_locales','en')]).status_code,400);self.assertEqual(self.rows(),[])
 def test_real_authlib_invalid_client_callback_scope(self):
  for key,value in [('client_id','not-registered'),('redirect_uri',CALLBACK+'/wrong'),('scope','arbitrary.write'),('response_type','token')]:
   with self.subTest(key=key):
    a=[(k,value if k==key else v) for k,v in args()]+[('ui_locales','en')]
    self.assertEqual(self.request(a).status_code,400)
  self.assertEqual(self.rows(),[])
 def test_resource_and_pkce_rejections(self):
  for key,value in [('resource','https://wrong.invalid/mcp'),('code_challenge_method','plain'),('code_challenge','short'),('state','')]:
   with self.subTest(key=key):self.assertEqual(self.request([(k,value if k==key else v) for k,v in args()]+[('ui_locales','en')]).status_code,400)
  self.assertEqual(self.rows(),[])
 def test_host_and_https_boundaries(self):
  for base in ('http://authority.example.test','https://wrong.invalid'):
   with self.subTest(base=base):self.assertEqual(self.request(args()+[('ui_locales','en')],base_url=base).status_code,400)
  self.assertEqual(self.rows(),[])
if __name__=='__main__':unittest.main()
