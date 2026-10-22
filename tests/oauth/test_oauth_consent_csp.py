"""Synthetic in-memory consent boundary tests; all socket connections forbidden."""
import sqlite3,json,unittest,uuid,socket,re,urllib.parse
from unittest.mock import patch
from production.cloud_connection import oauth_authority as candidate
ISSUER='https://authority.example.test'
CALLBACK='https://client.example.test/callback'
def args():return [('client_id','offline-status-client'),('redirect_uri',CALLBACK),('resource',ISSUER+'/mcp'),('scope','connection.status'),('response_type','code'),('code_challenge_method','S256'),('code_challenge','A'*43),('state','B'*40)]
BASE="default-src 'none'; form-action 'self'; frame-ancestors 'none'"
class Fixture(unittest.TestCase):
 def setUp(self):
  self.net=patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK_FORBIDDEN'));self.netmock=self.net.start()
  self.dburi='file:local_ui_test_'+uuid.uuid4().hex+'?mode=memory&cache=shared'
  self.keeper=sqlite3.connect(self.dburi,uri=True);candidate.initialize_new_database(self.keeper)
 def tearDown(self):
  self.keeper.close();self.net.stop();self.assertEqual(self.netmock.call_count,0)
 def client(self,mod=candidate):
  config=dict(issuer=ISSUER,audience=ISSUER+'/mcp',github_client_id='offline-test-client',subjects=['github:332398908'],clients={'offline-status-client':dict(redirect_uris=[CALLBACK],auth_method='none',secret_hash='0'*64,resource_client=False)})
  app=mod.create_app(config,lambda:sqlite3.connect(self.dburi,uri=True),b'LOCAL-TEST-ONLY-NOT-A-SECRET'*2,'LOCAL-TEST-ONLY-NOT-A-GITHUB-SECRET',enabled=True)
  app.config['TESTING']=True
  return app.test_client()
class ConsentTests(unittest.TestCase):
 def setUp(self):
  self.b=Fixture();self.b.setUp();self.c=self.b.client(candidate);self.db=self.b.keeper
 def tearDown(self):self.b.tearDown()
 def start(self,owner=True):
  r=self.c.get('/authorize',query_string=args()+[('ui_locales','en-US')],base_url=ISSUER,follow_redirects=False);self.assertEqual(r.status_code,302)
  if owner:self.db.execute("UPDATE oauth_flows SET sub='github:332398908'");self.db.commit()
 def get(self,path='/consent'):return self.c.get(path,base_url=ISSUER,follow_redirects=False)
 def form(self):
  r=self.get();self.assertEqual(r.status_code,200)
  return re.search(r'name="csrf" value="([^"]+)"',r.get_data(as_text=True)).group(1),r
 def post(self,data):return self.c.post('/consent',base_url=ISSUER,data=data,follow_redirects=False)
 def codes(self):return self.db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0]
 def test_exact_get_header_and_other_security_headers(self):
  self.start();csrf,r=self.form()
  self.assertEqual(r.headers['Content-Security-Policy'],"default-src 'none'; form-action 'self' "+CALLBACK+"; frame-ancestors 'none'")
  for k,v in [('Cache-Control','no-store'),('Pragma','no-cache'),('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff')]:self.assertEqual(r.headers[k],v)
  self.assertIn('<form method="post">',r.get_data(as_text=True));self.assertEqual(self.codes(),0)
 def test_real_post_once_exact_callback_and_state(self):
  self.start();csrf,r=self.form();out=self.post({'csrf':csrf,'approve':'yes'})
  self.assertEqual(out.status_code,302);u=urllib.parse.urlsplit(out.headers['Location']);expected=urllib.parse.urlsplit(CALLBACK)
  self.assertEqual((u.scheme,u.netloc,u.path),(expected.scheme,expected.netloc,expected.path));self.assertEqual(urllib.parse.parse_qs(u.query)['state'],['B'*40]);self.assertEqual(self.codes(),1)
  self.assertEqual(out.headers['Content-Security-Policy'],BASE);self.assertEqual(self.db.execute('SELECT used FROM oauth_flows').fetchone()[0],1)
  again=self.post({'csrf':csrf,'approve':'yes'});self.assertEqual(again.status_code,401);self.assertEqual(self.codes(),1);self.assertEqual(again.headers['Content-Security-Policy'],BASE)
 def test_missing_and_wrong_form_values(self):
  self.start();csrf,r=self.form()
  for data in ({'approve':'yes'},{'csrf':'wrong','approve':'yes'},{'csrf':csrf,'approve':'no'},{'csrf':csrf,'approve':'yes','extra':'x'}):
   self.assertEqual(self.post(data).status_code,403);self.assertEqual(self.codes(),0)
 def test_duplicate_csrf_and_approve(self):
  from werkzeug.datastructures import MultiDict
  self.start();csrf,r=self.form()
  for key in ('csrf','approve'):
   data=MultiDict([('csrf',csrf),('approve','yes'),(key,csrf if key=='csrf' else 'yes')]);out=self.post(data);self.assertEqual(out.status_code,400);self.assertEqual(out.headers['Content-Security-Policy'],BASE);self.assertEqual(self.codes(),0)
 def test_missing_flow_has_old_policy(self):
  out=self.get();self.assertEqual(out.status_code,401);self.assertEqual(out.headers['Content-Security-Policy'],BASE)
 def test_unbound_owner_has_old_policy(self):
  self.start(False);out=self.get();self.assertEqual(out.status_code,401);self.assertEqual(out.headers['Content-Security-Policy'],BASE)
 def test_expired_or_used_flow_has_old_policy(self):
  for statement in ('UPDATE oauth_flows SET expires=0','UPDATE oauth_flows SET used=1'):
   self.start();self.db.execute(statement);self.db.commit();out=self.get();self.assertEqual(out.status_code,401);self.assertEqual(out.headers['Content-Security-Policy'],BASE)
 def test_current_registration_rechecked(self):
  self.start();params=json.loads(self.db.execute('SELECT params FROM oauth_flows').fetchone()[0]);params['redirect_uri']='https://unregistered.invalid/callback';self.db.execute('UPDATE oauth_flows SET params=?',(json.dumps(params),));self.db.commit();out=self.get();self.assertEqual(out.status_code,403);self.assertEqual(out.headers['Content-Security-Policy'],BASE)
 def test_other_client_cannot_be_selected_by_query(self):
  self.start();out=self.get('/consent?redirect_uri=https://unregistered.invalid/callback&client_id=foreign');self.assertEqual(out.status_code,200);self.assertNotIn('unregistered',out.headers['Content-Security-Policy']);self.assertIn(CALLBACK,out.headers['Content-Security-Policy'])
 def test_other_route_keeps_old_policy(self):
  self.start();self.form();r=self.get('/.well-known/oauth-authorization-server');self.assertEqual(r.headers['Content-Security-Policy'],BASE)
 def make_config_client(self,callback):
  import sqlite3
  entry=dict(redirect_uris=[callback,'https://other.example.test/unused'],auth_method='none',secret_hash='0'*64,resource_client=False)
  config=dict(issuer=ISSUER,audience=ISSUER+'/mcp',github_client_id='offline-test-client',subjects=['github:332398908'],clients={'offline-status-client':entry,'other-client':dict(entry,redirect_uris=['https://another.example.test/unused'])})
  app=candidate.create_app(config,lambda:sqlite3.connect(self.b.dburi,uri=True),b'LOCAL-TEST-ONLY-NOT-A-SECRET'*2,'LOCAL-TEST-ONLY-NOT-A-GITHUB-SECRET',enabled=True)
  app.config['TESTING']=True;self.c=app.test_client()
 def test_only_selected_callback_not_other_registered_uris(self):
  self.make_config_client(CALLBACK);self.start();csrf,r=self.form();policy=r.headers['Content-Security-Policy']
  self.assertIn(CALLBACK,policy);self.assertNotIn('other.example',policy);self.assertNotIn('another.example',policy)
 def test_registered_but_unrepresentable_source_fails_closed(self):
  callback=CALLBACK+'?display=example';self.make_config_client(callback)
  r=self.c.get('/authorize',query_string=[(k,callback if k=='redirect_uri' else v) for k,v in args()],base_url=ISSUER,follow_redirects=False);self.assertEqual(r.status_code,302)
  self.db.execute("UPDATE oauth_flows SET sub='github:332398908'");self.db.commit();out=self.get();self.assertEqual(out.status_code,503);self.assertEqual(out.headers['Content-Security-Policy'],BASE);self.assertEqual(self.codes(),0)
 def test_missing_current_client_fails_closed(self):
  self.start();params=json.loads(self.db.execute('SELECT params FROM oauth_flows').fetchone()[0]);params['client_id']='unregistered-client';self.db.execute('UPDATE oauth_flows SET params=?',(json.dumps(params),));self.db.commit();out=self.get();self.assertEqual(out.status_code,403);self.assertEqual(out.headers['Content-Security-Policy'],BASE)
 def test_safe_source_helper(self):
  for value in (CALLBACK,'https://authority.example.test:8443/oauth/callback','https://authority.example.test/a%20b'):
   self.assertEqual(candidate.consent_form_source(value),value)
 def test_unsafe_source_helper(self):
  for value in ('http://example.test/cb','https://*.example.test/cb','https://example.test/cb;form-action *','https://example.test/cb,https://bad.test/','https://user@example.test/cb','https://example.test\\bad/cb','https://example.test/cb?x=1','https://example.test/cb#f','https://example.test:0/cb','https://example.test:65536/cb','https://bad..test/cb','https://-bad.test/cb','https://example.test/cb\n',' https://example.test/cb','https://example.test/%zz','https://example.test/中文','https://example.test/'+'a'*2048):
   with self.subTest(value_type='synthetic_invalid_uri'):
    with self.assertRaises(candidate.Hold):candidate.consent_form_source(value)
if __name__=='__main__':unittest.main()
