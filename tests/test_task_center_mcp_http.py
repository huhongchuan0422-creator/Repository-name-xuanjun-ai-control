from __future__ import print_function

import base64
import hashlib
import http.cookies
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import socketserver
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import parse_qs,urlsplit,urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from connection_management import ConnectionManager
from model_orchestration import ModelControl
from provider_onboarding import ensure_schema as ensure_onboarding_schema
from task_center_app import make_server
import task_center_app as task_center_app_module
from task_center_mcp_auth import MCPAuthorizationStore
from task_center_mcp_service import MCPTaskService
from task_center_session_auth import FileTestIdentityProvider,SessionStore,password_hash
from task_supervisor import Supervisor
from task_writer_fence import Fence

KEY=b'0123456789abcdef0123456789abcdef'
HOST='mcp.example.com'

class ThreadServer(socketserver.ThreadingMixIn,HTTPServer):daemon_threads=True
class ModelFixture(BaseHTTPRequestHandler):
    calls=0
    def log_message(self,*_args):pass
    def do_POST(self):
        type(self).calls+=1
        length=int(self.headers.get('Content-Length','0'));self.rfile.read(length)
        body=json.dumps({'id':'remote-mcp-result','choices':[{'message':{
          'content':'{"label":"safe","reason":"remote-fixture"}'}}],
          'usage':{'prompt_tokens':5,'completion_tokens':3,
          'total_tokens':8}}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)


class MCPHTTPTests(unittest.TestCase):
    def setUp(self):
        ModelFixture.calls=0
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.model=ThreadServer(('127.0.0.1',0),ModelFixture)
        self.model_thread=threading.Thread(target=self.model.serve_forever)
        self.model_thread.daemon=True;self.model_thread.start()
        self.master=Fernet.generate_key();supervisor=Supervisor(self.db)
        authority=TestTenantAuthority(KEY);gateway=GatewayKernel(supervisor,authority)
        context=authority.issue('tenant-mcp','admin:fixture')
        control=ModelControl(gateway,context,self.master)
        provider={'provider_id':'fixture','display_name':'Fixture',
          'adapter_type':'openai-compatible','base_url':'http://127.0.0.1:%d'%
          self.model.server_port,'enabled':True,'price_state':'KNOWN_FREE',
          'rate_limit_per_min':10,'concurrency_limit':1,'timeout_seconds':1,
          'retry_limit':0}
        control.upsert_provider(provider,'fixture-secret')
        control.set_quota_status('fixture','AVAILABLE','TEST_ONLY_LOCAL_FIXTURE',
          time.time(),None)
        control.upsert_model({'provider_id':'fixture','model_id':'fixture-chat',
          'capabilities':['general'],'enabled':True,'price_state':'KNOWN_FREE',
          'input_unit_cost':0,'output_unit_cost':0})
        ConnectionManager(gateway,context,self.master).upsert({
          'connection_id':'fixture-connection','provider_id':'fixture',
          'purpose':'MODEL_INFERENCE','auth_type':'API_KEY',
          'destination_origin':provider['base_url'],'issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},'fixture-secret')
        control.register_benchmark_suite('mcp-v1',[{'case_id':'general-1',
          'capability':'general','messages':[{'role':'user','content':'classify'}],
          'expected_contains':'label'}])
        control.run_benchmark('fixture','fixture-chat','mcp-v1')
        ensure_onboarding_schema(supervisor.db)
        supervisor.db.execute('''INSERT INTO provider_onboarding_configs VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?)''',('tenant-mcp','fixture-platform',
          'fixture-connection','fixture','fixture-chat','SUCCEEDED','RETRIEVED',
          'TESTED_SUCCEEDED','fixture-chat',json.dumps(['fixture-chat']),
          '••••cret',time.time()))
        supervisor.db.commit();supervisor.close()
        identity_path=os.path.join(self.root,'identities.json')
        with open(identity_path,'w') as stream:json.dump({'users':{'owner':{
          'enabled':True,'password_hash':password_hash('test-password-12'),
          'tenant_id':'tenant-mcp','principal_id':'owner-1',
          'roles':['TASK_CENTER_ADMIN']}}},stream)
        os.chmod(identity_path,0o600)
        self.identity=FileTestIdentityProvider(identity_path)
        def connect():
            import sqlite3
            db=sqlite3.connect(self.db);db.row_factory=sqlite3.Row;return db
        self.sessions=SessionStore(connect,'tenant-mcp')
        self.server=make_server(self.db,KEY,'tenant-mcp','owner',port=0,
          model_master_key=self.master,identity_provider=self.identity,
          session_store=self.sessions,outbound_enabled=False,
          external_origin='https://'+HOST,base_path='/task-center-test/',
          mcp_enabled=True,mcp_model_worker_enabled=True)
        self.thread=threading.Thread(target=self.server.serve_forever)
        self.thread.daemon=True;self.thread.start()
        self.base='http://127.0.0.1:%d/task-center-test'%self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.model.shutdown();self.model.server_close();self.model_thread.join(2)
        shutil.rmtree(self.root)

    def request(self,path,method='GET',body=None,headers=None):
        values={'Host':HOST};values.update(headers or {})
        req=Request(self.base+path,method=method,data=body,headers=values)
        return urlopen(req,timeout=3)

    def raw_chunked(self,path,value,headers=None):
        body=json.dumps(value,separators=(',',':')).encode()
        values={'Host':HOST,'Content-Type':'application/json',
          'Transfer-Encoding':'chunked','Connection':'close'}
        values.update(headers or {})
        request=('POST /task-center-test%s HTTP/1.1\r\n'%path)
        for name,value in values.items():request+='%s: %s\r\n'%(name,value)
        request+='\r\n'
        client=socket.create_connection(('127.0.0.1',self.server.server_port),3)
        try:
            client.sendall(request.encode()+('%x\r\n'%len(body)).encode()+
              body+b'\r\n0\r\n\r\n')
            response=b''
            while True:
                part=client.recv(65536)
                if not part:break
                response+=part
        finally:client.close()
        head,payload=response.split(b'\r\n\r\n',1)
        status=int(head.split(b' ',2)[1])
        parsed={}
        for line in head.split(b'\r\n')[1:]:
            name,value=line.split(b':',1)
            parsed[name.decode().lower()]=value.decode().strip()
        return status,parsed,payload

    def raw_request(self,path,headers,body=b''):
        request=('POST /task-center-test%s HTTP/1.1\r\n'%path)
        values={'Host':HOST,'Connection':'close'};values.update(headers)
        for name,value in values.items():request+='%s: %s\r\n'%(name,value)
        client=socket.create_connection(('127.0.0.1',self.server.server_port),3)
        try:
            client.sendall((request+'\r\n').encode()+body)
            response=b''
            while True:
                part=client.recv(65536)
                if not part:break
                response+=part
        finally:client.close()
        head,payload=response.split(b'\r\n\r\n',1)
        return int(head.split(b' ',2)[1]),json.loads(payload)

    def oauth_record_counts(self):
        import sqlite3
        db=sqlite3.connect(self.db)
        try:return tuple(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
          for table in ('mcp_oauth_clients','mcp_oauth_codes','mcp_oauth_tokens'))
        finally:db.close()

    def refresh_record_count(self):
        import sqlite3
        db=sqlite3.connect(self.db)
        try:return db.execute(
          'SELECT COUNT(*) FROM mcp_oauth_refresh_tokens').fetchone()[0]
        finally:db.close()

    def oauth_store(self):
        def connect():
            import sqlite3
            db=sqlite3.connect(self.db,timeout=5);db.row_factory=sqlite3.Row
            return db
        return MCPAuthorizationStore(connect,'tenant-mcp',
          'https://'+HOST+'/task-center-test',
          'https://'+HOST+'/task-center-test/mcp')

    def test_health_reports_actual_worker_thread_state(self):
        value=json.loads(self.request('/healthz').read().decode())
        self.assertEqual(value['mcp_model_worker'],'RUNNING')
        self.server.mcp_worker.stop()
        value=json.loads(self.request('/healthz').read().decode())
        self.assertEqual(value['mcp_model_worker'],'STOPPED')

    def issue_refresh(self,store,client_id,marker):
        verifier=marker*64
        challenge=base64.urlsafe_b64encode(hashlib.sha256(
          verifier.encode()).digest()).decode().rstrip('=')
        redirect_uri='https://chatgpt.com/connector_platform_oauth_redirect'
        location=store.authorize({'principal_id':'owner-1'},
          {'response_type':'code','client_id':client_id,
           'redirect_uri':redirect_uri,'code_challenge':challenge,
           'code_challenge_method':'S256','state':marker,
           'resource':'https://'+HOST+'/task-center-test/mcp',
           'scope':'task:read'})
        code=parse_qs(urlsplit(location).query)['code'][0]
        return store.exchange({'grant_type':'authorization_code','code':code,
          'client_id':client_id,'redirect_uri':redirect_uri,
          'code_verifier':verifier,
          'resource':'https://'+HOST+'/task-center-test/mcp'})

    def test_chunked_mcp_probe_challenges_and_dcr_registers(self):
        rpc={'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}
        status,headers,body=self.raw_chunked('/mcp',rpc)
        self.assertEqual(status,401)
        self.assertIn('resource_metadata=',headers['www-authenticate'])
        self.assertEqual(json.loads(body)['error'],'MCP_AUTH_REQUIRED')
        self.assertEqual(headers['connection'],'close')
        status,headers,body=self.raw_chunked('/mcp',rpc)
        self.assertEqual(status,401)
        self.assertEqual(self.oauth_record_counts(),(0,0,0))
        status,headers,body=self.raw_chunked('/mcp',rpc,{
          'Authorization':'Bearer invalid'})
        self.assertEqual(status,401)
        dcr={'redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect'],
          'grant_types':['authorization_code','refresh_token'],
          'response_types':['code'],
          'token_endpoint_auth_method':'none','client_name':'Synthetic ChatGPT'}
        status,headers,body=self.raw_chunked('/oauth/register',dcr)
        self.assertEqual(status,201)
        self.assertEqual(json.loads(body)['token_endpoint_auth_method'],'none')
        self.assertEqual(json.loads(body)['grant_types'],
          ['authorization_code','refresh_token'])
        self.assertEqual(self.oauth_record_counts(),(1,0,0))

    def test_dcr_rejections_are_bounded_and_create_no_records(self):
        cases=(({},'invalid_redirect_uri','DCR_REDIRECT_URIS_REQUIRED'),
          ({'redirect_uris':['https://evil.example/callback']},
           'invalid_redirect_uri','CHATGPT_REDIRECT_URI_REQUIRED'),
          ({'redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect'],
            'token_endpoint_auth_method':'client_secret_post'},
           'invalid_client_metadata','PUBLIC_PKCE_CLIENT_REQUIRED'),
          ({'redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect'],
            'grant_types':['client_credentials']},
           'invalid_client_metadata','DCR_GRANT_TYPES_REJECTED'))
        for value,error,expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(HTTPError) as rejected:
                    self.request('/oauth/register','POST',json.dumps(value).encode(),
                      {'Content-Type':'application/json'})
                self.assertEqual(rejected.exception.code,400)
                result=json.loads(rejected.exception.read())
                self.assertEqual(result,{'error':error,
                  'error_description':expected})
                self.assertEqual(rejected.exception.headers['Connection'],'close')
        value={'redirect_uris':[
          'https://chatgpt.com/connector_platform_oauth_redirect'],
          'grant_types':['client_credentials']}
        for unused in range(2):
            with self.assertRaises(HTTPError) as repeated:
                self.request('/oauth/register','POST',json.dumps(value).encode(),
                  {'Content-Type':'application/json'})
            self.assertEqual(repeated.exception.code,400)
        self.assertEqual(self.oauth_record_counts(),(0,0,0))

    def test_dcr_body_framing_and_json_rejections_are_explicit(self):
        status,result=self.raw_request('/oauth/register',{
          'Content-Type':'application/json'},b'{}')
        self.assertEqual((status,result['error_description']),
                         (400,'BODY_LENGTH_REQUIRED'))
        status,result=self.raw_request('/oauth/register',{
          'Content-Type':'application/json','Content-Length':'1'},b'{')
        self.assertEqual((status,result['error_description']),
                         (400,'JSON_INVALID'))
        status,result=self.raw_request('/oauth/register',{
          'Content-Type':'application/json','Content-Length':'65537'},b'')
        self.assertEqual((status,result['error_description']),(400,'BODY_LIMIT'))
        status,result=self.raw_request('/oauth/register',{
          'Content-Type':'application/json','Content-Length':'2',
          'Transfer-Encoding':'chunked'},b'{}')
        self.assertEqual((status,result['error_description']),
                         (400,'BODY_FRAMING_CONFLICT'))
        status,result=self.raw_request('/oauth/register',{
          'Content-Type':'application/json','Content-Length':'10'},b'{}')
        self.assertEqual((status,result['error_description']),(400,'BODY_TIMEOUT'))
        for value in ('+2','0_2','0x2'):
            status,result=self.raw_request('/oauth/register',{
              'Content-Type':'application/json','Content-Length':value},b'{}')
            self.assertEqual((status,result['error_description']),
                             (400,'BODY_LENGTH_REJECTED'))
        for value in (b'+2',b'0_2',b'0x2'):
            status,result=self.raw_request('/oauth/register',{
              'Content-Type':'application/json','Transfer-Encoding':'chunked'},
              value+b'\r\n{}\r\n0\r\n\r\n')
            self.assertEqual((status,result['error_description']),
                             (400,'CHUNK_HEADER_REJECTED'))
        self.assertEqual(self.oauth_record_counts(),(0,0,0))

    def test_body_read_uses_one_total_deadline_for_slow_fragments(self):
        old=task_center_app_module.MCP_BODY_READ_TIMEOUT_SECONDS
        task_center_app_module.MCP_BODY_READ_TIMEOUT_SECONDS=.2
        client=socket.create_connection(('127.0.0.1',self.server.server_port),3)
        started=time.monotonic()
        try:
            client.sendall(('POST /task-center-test/oauth/register HTTP/1.1\r\n'
              'Host: %s\r\nContent-Type: application/json\r\n'
              'Content-Length: 3\r\nConnection: close\r\n\r\n{'%HOST).encode())
            time.sleep(.12)
            client.sendall(b'}')
            response=b''
            while True:
                part=client.recv(65536)
                if not part:break
                response+=part
        finally:
            client.close()
            task_center_app_module.MCP_BODY_READ_TIMEOUT_SECONDS=old
        elapsed=time.monotonic()-started
        head,payload=response.split(b'\r\n\r\n',1)
        self.assertEqual(int(head.split(b' ',2)[1]),400)
        self.assertEqual(json.loads(payload)['error_description'],'BODY_TIMEOUT')
        self.assertLess(elapsed,.30)

    def test_refresh_replay_revokes_only_its_family_under_concurrency(self):
        store=self.oauth_store()
        client=store.register({'redirect_uris':[
          'https://chatgpt.com/connector_platform_oauth_redirect'],
          'grant_types':['authorization_code','refresh_token'],
          'response_types':['code'],'token_endpoint_auth_method':'none'})
        family_a=self.issue_refresh(store,client['client_id'],'a')
        family_b=self.issue_refresh(store,client['client_id'],'b')
        params={'grant_type':'refresh_token',
          'refresh_token':family_a['refresh_token'],
          'client_id':client['client_id'],
          'resource':'https://'+HOST+'/task-center-test/mcp'}
        barrier=threading.Barrier(3);results=[];lock=threading.Lock()
        def rotate():
            barrier.wait()
            try:value=('SUCCESS',store.exchange(dict(params)))
            except ValueError as exc:value=('REJECTED',str(exc))
            with lock:results.append(value)
        workers=[threading.Thread(target=rotate) for unused in range(2)]
        for worker in workers:worker.start()
        barrier.wait()
        for worker in workers:worker.join(5)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual([item[0] for item in results].count('SUCCESS'),1)
        self.assertEqual([item[1] for item in results if item[0]=='REJECTED'],
          ['OAUTH_REFRESH_REPLAY_REJECTED'])
        successor=[item[1]['refresh_token'] for item in results
          if item[0]=='SUCCESS'][0]
        with self.assertRaisesRegex(ValueError,'OAUTH_REFRESH_REJECTED'):
            store.exchange(dict(params,refresh_token=successor))
        unaffected=store.exchange(dict(params,
          refresh_token=family_b['refresh_token']))
        self.assertIn('refresh_token',unaffected)
        import sqlite3
        db=sqlite3.connect(self.db);db.row_factory=sqlite3.Row
        try:
            rows=db.execute('''SELECT family_id,revoked_at FROM
              mcp_oauth_refresh_tokens WHERE tenant_id=?''',(
              'tenant-mcp',)).fetchall()
        finally:db.close()
        families={}
        for row in rows:families.setdefault(row['family_id'],[]).append(
          row['revoked_at'])
        self.assertEqual(len(families),2)
        self.assertEqual(sorted(all(value is not None for value in values)
          for values in families.values()),[False,True])

    def test_oauth_pkce_and_streamable_http_discovery(self):
        metadata=json.loads(self.request('/.well-known/oauth-protected-resource').read())
        self.assertEqual(metadata['resource'],'https://'+HOST+'/task-center-test/mcp')
        standard=Request('http://127.0.0.1:%d/.well-known/'%
          self.server.server_port+'oauth-authorization-server/task-center-test',
          headers={'Host':HOST})
        authorization_server=json.loads(urlopen(standard,timeout=3).read())
        self.assertEqual(authorization_server['issuer'],
          'https://'+HOST+'/task-center-test')
        self.assertEqual(authorization_server['grant_types_supported'],
          ['authorization_code','refresh_token'])
        dcr={'redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect'],
          'grant_types':['authorization_code'],'response_types':['code'],
          'token_endpoint_auth_method':'none','client_name':'ChatGPT test'}
        client=json.loads(self.request('/oauth/register','POST',
          json.dumps(dcr).encode(),{'Content-Type':'application/json'}).read())
        login=self.request('/api/session/login','POST',json.dumps({
          'username':'owner','password':'test-password-12'}).encode(),{
          'Content-Type':'application/json','Origin':'https://'+HOST})
        cookies=login.headers.get_all('Set-Cookie');session_cookie=cookies[0].split(';',1)[0]
        verifier='v'*64
        challenge=base64.urlsafe_b64encode(hashlib.sha256(
          verifier.encode()).digest()).decode().rstrip('=')
        self.assertTrue(session_cookie.startswith('xuanjun_task_center_session='))
        self.assertEqual(client['token_endpoint_auth_method'],'none')

    def test_live_service_blocks_competing_startup_recovery(self):
        def stop(phase):
            if phase=='CONTRACT_PERSISTED':raise RuntimeError('STOP_AFTER_CONTRACT')
        service=MCPTaskService(self.db,KEY,'tenant-mcp',self.master,'owner-1',
          'project-mcp',phase_hook=stop)
        value={'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION',
          'input_text':'Classify: lease safety','idempotency_key':'lease-safety',
          'connection_id':'fixture-connection','max_output_tokens':32}
        with self.assertRaisesRegex(RuntimeError,'STOP_AFTER_CONTRACT'):
            service.submit(value)
        supervisor=Supervisor(self.db);authority=TestTenantAuthority(KEY)
        gateway=GatewayKernel(supervisor,authority)
        binding=supervisor.db.execute('''SELECT task_id FROM mcp_task_bindings
          WHERE tenant_id=? AND idempotency_key=?''',('tenant-mcp',
          'lease-safety')).fetchone();task_id=binding['task_id']
        attempt_id='attempt-'+task_id[4:]
        fence=Fence(supervisor,self.db+'.test-only-locks')
        try:
            fence.claim(task_id,attempt_id,'mcp-worker','model-scheduler-runtime',{
              'caller_id':'test-writer-'+attempt_id,
              'run_id':'test-run-'+attempt_id,
              'session_id':'test-session-'+attempt_id,
              'gateway_id':'test-gateway'},'lease-'+attempt_id,
              gateway.canonical_resources(task_id),time.time()+600)
        finally:fence.close();supervisor.close()
        with self.assertRaisesRegex(ValueError,'MCP_SERVICE_ALREADY_RUNNING'):
            make_server(self.db,KEY,'tenant-mcp','owner',port=0,
              model_master_key=self.master,identity_provider=self.identity,
              session_store=self.sessions,outbound_enabled=False,
              external_origin='https://'+HOST,
              base_path='/task-center-test/',mcp_enabled=True)
        supervisor=Supervisor(self.db)
        try:
            task=supervisor._task(task_id)
            self.assertEqual((task['state'],task['authority_state']),
                             ('RECEIVED','VALID'))
            claim=supervisor.db.execute('''SELECT state FROM resource_claims
              WHERE task_id=?''',(task_id,)).fetchone()
            self.assertEqual(claim['state'],'VALID')
        finally:supervisor.close()

    def test_full_oauth_without_following_external_redirect(self):
        class NoRedirect(__import__('urllib.request').request.HTTPRedirectHandler):
            def redirect_request(self,*_args,**_kwargs):return None
        opener=__import__('urllib.request').request.build_opener(NoRedirect)
        def raw(path,method='GET',body=None,headers=None):
            h={'Host':HOST};h.update(headers or {})
            req=Request(self.base+path,method=method,data=body,headers=h)
            try:return opener.open(req,timeout=3)
            except HTTPError as exc:
                if exc.code in (301,302,303,307,308):return exc
                raise
        dcr={'redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect'],
          'grant_types':['authorization_code','refresh_token'],
          'response_types':['code'],
          'token_endpoint_auth_method':'none'}
        client=json.loads(raw('/oauth/register','POST',json.dumps(dcr).encode(),
          {'Content-Type':'application/json'}).read())
        login=raw('/api/session/login','POST',json.dumps({'username':'owner',
          'password':'test-password-12'}).encode(),{'Content-Type':'application/json',
          'Origin':'https://'+HOST})
        cookie=login.headers.get_all('Set-Cookie')[0].split(';',1)[0]
        verifier='z'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(
          verifier.encode()).digest()).decode().rstrip('=')
        resource='https://'+HOST+'/task-center-test/mcp'
        params={'response_type':'code','client_id':client['client_id'],
          'redirect_uri':dcr['redirect_uris'][0],'code_challenge':challenge,
          'code_challenge_method':'S256','state':'s','resource':resource,
          'scope':'task:read task:submit'}
        redirect=raw('/oauth/authorize?'+urlencode(params),headers={'Cookie':cookie})
        location=redirect.headers['Location'];query=parse_qs(urlsplit(location).query)
        self.assertEqual(query['state'],['s']);self.assertIn('iss',query)
        exchange={'grant_type':'authorization_code','code':query['code'][0],
          'client_id':client['client_id'],'redirect_uri':dcr['redirect_uris'][0],
          'code_verifier':verifier,'resource':resource}
        token=json.loads(raw('/oauth/token','POST',urlencode(exchange).encode(),{
          'Content-Type':'application/x-www-form-urlencoded'}).read())
        self.assertIn('refresh_token',token)
        with self.assertRaises(HTTPError) as replay:
            raw('/oauth/token','POST',urlencode(exchange).encode(),{
              'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(replay.exception.code,400)
        replay_error=json.loads(replay.exception.read())
        self.assertEqual(replay_error,{'error':'invalid_grant',
          'error_description':'OAUTH_CODE_REPLAY_REJECTED'})
        refresh={'grant_type':'refresh_token','refresh_token':token['refresh_token'],
          'client_id':client['client_id'],'resource':resource}
        rotated=json.loads(raw('/oauth/token','POST',urlencode(refresh).encode(),{
          'Content-Type':'application/x-www-form-urlencoded'}).read())
        self.assertNotEqual(rotated['refresh_token'],token['refresh_token'])
        with self.assertRaises(HTTPError) as refresh_replay:
            raw('/oauth/token','POST',urlencode(refresh).encode(),{
              'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(refresh_replay.exception.code,400)
        refresh_error=json.loads(refresh_replay.exception.read())
        self.assertEqual(refresh_error,{'error':'invalid_grant',
          'error_description':'OAUTH_REFRESH_REPLAY_REJECTED'})
        with self.assertRaises(HTTPError) as revoked_successor:
            raw('/oauth/token','POST',urlencode(dict(refresh,
              refresh_token=rotated['refresh_token'])).encode(),{
              'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(json.loads(revoked_successor.exception.read()),{
          'error':'invalid_grant','error_description':'OAUTH_REFRESH_REJECTED'})
        self.assertEqual(self.refresh_record_count(),2)
        token['access_token']=rotated['access_token']
        rpc={'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}
        initialized=json.loads(raw('/mcp','POST',json.dumps(rpc).encode(),{
          'Content-Type':'application/json','Authorization':'Bearer '+
          token['access_token']}).read())
        self.assertEqual(initialized['result']['serverInfo']['name'],
                         'xuanjun-task-center')
        listed=json.loads(raw('/mcp','POST',json.dumps({'jsonrpc':'2.0','id':2,
          'method':'tools/list','params':{}}).encode(),{'Content-Type':
          'application/json','Authorization':'Bearer '+token['access_token']}).read())
        self.assertEqual([x['name'] for x in listed['result']['tools']],
          ['task_capabilities','task_submit','task_get','task_query_result'])
        authorization={'Content-Type':'application/json','Authorization':'Bearer '+
          token['access_token']}
        capabilities=json.loads(raw('/mcp','POST',json.dumps({'jsonrpc':'2.0',
          'id':3,'method':'tools/call','params':{'name':'task_capabilities',
          'arguments':{}}}).encode(),authorization).read())
        self.assertIn('fixture-connection',capabilities['result']['content'][0]['text'])
        rejected_rpc={'jsonrpc':'2.0','id':'scope-reject','method':'tools/call',
          'params':{'name':'task_submit','arguments':{
          'project_id':'other-project','task_type':'TEXT_CLASSIFICATION',
          'input_text':'Classify: hello','idempotency_key':'rejected-idem',
          'connection_id':'fixture-connection','max_output_tokens':32}}}
        with self.assertRaises(HTTPError) as scoped:
            raw('/mcp','POST',json.dumps(rejected_rpc).encode(),authorization)
        self.assertEqual(scoped.exception.code,400)
        self.assertEqual(json.loads(scoped.exception.read()),{
          'error':'invalid_request',
          'error_description':'MCP_PROJECT_SCOPE_REJECTED'})
        submitted=json.loads(raw('/mcp','POST',json.dumps({'jsonrpc':'2.0',
          'id':4,'method':'tools/call','params':{'name':'task_submit','arguments':{
          'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION',
          'input_text':'Classify: hello','idempotency_key':'remote-idem-1',
          'connection_id':'fixture-connection','max_output_tokens':32}}}).encode(),
          authorization).read())
        task_id=json.loads(submitted['result']['content'][0]['text'])['task_id']
        deadline=time.time()+3;result=None
        while time.time()<deadline:
            response=json.loads(raw('/mcp','POST',json.dumps({'jsonrpc':'2.0',
              'id':5,'method':'tools/call','params':{'name':'task_query_result',
              'arguments':{'task_id':task_id}}}).encode(),authorization).read())
            result=json.loads(response['result']['content'][0]['text'])
            if result['state']=='SUCCEEDED':break
            time.sleep(.05)
        self.assertEqual(result['state'],'SUCCEEDED')
        self.assertIn('remote-fixture',result['result']['content'])
        # Same idempotency key returns the same task and does not call again.
        duplicate=json.loads(raw('/mcp','POST',json.dumps({'jsonrpc':'2.0',
          'id':6,'method':'tools/call','params':{'name':'task_submit','arguments':{
          'project_id':'project-mcp','task_type':'TEXT_CLASSIFICATION',
          'input_text':'Classify: hello','idempotency_key':'remote-idem-1',
          'connection_id':'fixture-connection','max_output_tokens':32}}}).encode(),
          authorization).read())
        self.assertEqual(json.loads(duplicate['result']['content'][0]['text'])['task_id'],task_id)
        self.assertEqual(ModelFixture.calls,2) # one benchmark + one task
        with self.assertRaises(HTTPError) as denied:
            raw('/mcp','POST',json.dumps(rpc).encode(),{
              'Content-Type':'application/json'})
        self.assertEqual(denied.exception.code,401)


if __name__=='__main__':unittest.main()
