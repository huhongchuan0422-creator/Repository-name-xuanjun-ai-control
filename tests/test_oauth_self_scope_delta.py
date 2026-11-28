"""Synthetic identities / real local OAuth+MCP seams; not live OAuth evidence."""
import base64
import hashlib
import json
import threading
import unittest
from urllib.parse import urlencode,parse_qs,urlsplit
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import HTTPError
from unittest.mock import patch
from task_center_app import make_server
from task_center_session_auth import FileTestIdentityProvider,SessionStore,password_hash
from task_center_first_claim import main
import test_first_claim_assembly as first

class OAuthSelfScopeTests(unittest.TestCase):
    def setUp(self):
        self.base_fixture=first.FirstClaimAssemblyTests()
        self.base_fixture.setUp();self.addCleanup(self.base_fixture.doCleanups)
        self.f=self.base_fixture.f
        self.base_fixture.run_action('register');self.base_fixture.run_action('claim')
        # Explicit synthetic existing assignment: status keeps its original role guard.
        task=self.f.s._task('demo-b')
        self.f.s.db.execute('''INSERT INTO model_assignments VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
          ('tenant-a','demo-b',task['attempt_id'],'developer','v1','developer',
           'synthetic-provider','synthetic-model','ASSIGNED','SYNTHETIC_EXISTING_ASSIGNMENT',0))
        self.f.s.db.commit()
        self.f.server.shutdown();self.f.server.server_close();self.f.thread.join(2)
        users={name:{'enabled':True,'password_hash':password_hash('SYNTHETIC_PASSWORD'),
          'tenant_id':'tenant-a','principal_id':name,'roles':['TASK_EXECUTOR']}
          for name in ('developer','intruder')}
        path=self.f.root/'self-users.json';path.write_text(json.dumps({'users':users}));path.chmod(0o600)
        self.callback='http://127.0.0.1:33333/synthetic-openclaw-callback'
        self.server=make_server(self.f.path,first.fixture.KEY,'tenant-a','fixture',port=0,
          model_master_key=self.f.master,identity_provider=FileTestIdentityProvider(str(path)),
          session_store=SessionStore(self.f.connect,'tenant-a'),external_origin=self.f.origin,
          mcp_enabled=True,mcp_development_host=self.base_fixture.host,mcp_claim_host=self.f.host,
          mcp_oauth_redirect_uris=[self.callback],outbound_enabled=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*a,**k):return None
        self.opener=build_opener(ProxyHandler({}),NoRedirect)
        self.resource=self.f.origin+'/mcp'

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
    def raw(self,path,method='GET',body=None,cookie=None,token=None):
        headers={'Host':'claim.example.invalid','Origin':self.f.origin}
        if body is not None:headers['Content-Type']='application/x-www-form-urlencoded' if path=='/oauth/token' else 'application/json'
        if cookie:headers['Cookie']=cookie
        if token:headers['Authorization']='Bearer '+token
        req=Request('http://127.0.0.1:%d%s'%(self.server.server_port,path),data=body,method=method,headers=headers)
        try:return self.opener.open(req,timeout=4)
        except HTTPError as e:return e
    def login(self,name):
        response=self.raw('/api/session/login','POST',json.dumps({'username':name,'password':'SYNTHETIC_PASSWORD'}).encode())
        self.assertEqual(response.code,200,response.read())
        return response.headers.get_all('Set-Cookie')[0].split(';',1)[0]
    def authorize(self,name='developer',scope='task:read task:submit'):
        dcr=self.raw('/oauth/register','POST',json.dumps({'redirect_uris':[self.callback]}).encode())
        self.assertEqual(dcr.code,201);client=json.loads(dcr.read())
        verifier='v'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params={'response_type':'code','client_id':client['client_id'],'redirect_uri':self.callback,
          'code_challenge':challenge,'code_challenge_method':'S256','state':'synthetic-state',
          'resource':self.resource,'scope':scope,'principal_id':'cannot-select-this-principal'}
        response=self.raw('/oauth/authorize?'+urlencode(params),cookie=self.login(name))
        return response,client,verifier
    def exchange(self,response,client,verifier,redirect=None):
        code=parse_qs(urlsplit(response.headers['Location']).query)['code'][0]
        return self.raw('/oauth/token','POST',urlencode({'grant_type':'authorization_code',
          'code':code,'client_id':client['client_id'],'redirect_uri':redirect or self.callback,
          'code_verifier':verifier,'resource':self.resource}).encode())
    def rpc(self,token,method='tools/list',params=None):
        value={'jsonrpc':'2.0','id':1,'method':method}
        if params:value['params']=params
        response=self.raw('/mcp','POST',json.dumps(value).encode(),token=token)
        return response.code,json.loads(response.read())

    def test_executor_self_oauth_discover_and_original_status_without_admin(self):
        response,client,verifier=self.authorize();self.assertEqual(response.code,302,response.read())
        token_response=self.exchange(response,client,verifier);self.assertEqual(token_response.code,200,token_response.read())
        # HTTPResponse.read is single-use, do not consume on a successful assertion.

    def test_executor_bearer_remains_self_and_status_is_visible(self):
        response,client,verifier=self.authorize();self.assertEqual(response.code,302)
        issued=self.exchange(response,client,verifier);body=json.loads(issued.read());self.assertEqual(issued.code,200,body)
        token=body['access_token'];code,value=self.rpc(token)
        self.assertEqual(code,200,value)
        self.assertIn('task_development_status',{t['name'] for t in value['result']['tools']})
        task=self.f.s._task('demo-b')
        code,status=self.rpc(token,'tools/call',{'name':'task_development_status','arguments':{'task_id':'demo-b','attempt_id':task['attempt_id']}})
        self.assertEqual(code,200,status)
        self.assertFalse(status.get('result',{}).get('isError',False),status)
        self.assertEqual(self.f.s._task('demo-b')['attempt_id'],task['attempt_id'])
        db=self.f.connect()
        try:
            identities=db.execute('SELECT DISTINCT principal_id,project_id FROM mcp_oauth_tokens').fetchall()
            self.assertTrue(any(tuple(r)==('developer','project-mcp') for r in identities))
            self.assertFalse(any(r['principal_id']=='cannot-select-this-principal' for r in identities))
        finally:db.close()

    def test_other_executor_principal_cannot_inherit_developer_binding(self):
        response,_,_=self.authorize('intruder');self.assertEqual(response.code,400)
        self.assertIn('OAUTH_SELF_DEVELOPMENT_SCOPE_REQUIRED',response.read().decode())

    def test_unregistered_redirect_pkce_and_scope_are_still_rejected(self):
        for uri in (self.callback+'/other',self.callback+'?different=1','https://evil.invalid/callback'):
            response=self.raw('/oauth/register','POST',json.dumps({'redirect_uris':[uri]}).encode())
            self.assertEqual(response.code,400)
        response,client,verifier=self.authorize()
        self.assertEqual(self.exchange(response,client,'wrong-verifier').code,400)
        self.assertEqual(self.exchange(response,client,verifier,self.callback+'/other').code,400)
        self.assertEqual(self.exchange(response,client,verifier).code,200)
        bad,_,_=self.authorize(scope='task:read root:all');self.assertEqual(bad.code,400)

    def test_cli_first_claim_passes_original_db_path_to_host_loader(self):
        key=self.f.root/'authority-key';key.write_bytes(first.fixture.KEY);key.chmod(0o600)
        with patch('task_center_first_claim.load_host',return_value=self.base_fixture.host) as loader:
            self.assertEqual(main(['--db',self.f.path,'--mcp-development-config-file','synthetic-config',
              '--authority-key-file',str(key),'--task-id','demo-b','--action','status']),0)
        loader.assert_called_once_with('synthetic-config',db_path=self.f.path)

if __name__=='__main__':unittest.main()
