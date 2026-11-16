import base64
import hashlib
import json
import multiprocessing
import os
import signal
import socket
import sqlite3
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

# Import the candidate app before the reusable fixture inserts its own scripts.
import task_center_app
from test_execution_intent_delta import fixtures
from task_center_mcp_auth import MCPAuthorizationStore
from task_supervisor import canonical

ORIGIN='https://development.example.invalid'

class SyntheticProvider:
    """Synthetic isolated receipt, NOT a live or authenticated producer."""
    def __init__(self, execute_count, query_count, response):
        self.execute_count=execute_count; self.query_count=query_count; self.response=response; self.receipt=None
    def __call__(self,intent,source):
        self.execute_count.value+=1
        self.receipt={'intent_sha256':hashlib.sha256(canonical(intent).encode()).hexdigest(),
          'result':{'state':'PASS','detail':'HTTP_PUBLIC_CONTRACT'},
          'test_reference_sha256':intent['test_reference_sha256'],
          'source_sha256':intent['source_sha256'],'artifact_sha256':'a'*64}
        raise TimeoutError('synthetic unknown')
    def query(self,intent):
        self.query_count.value+=1
        return self.receipt if self.response.value else None

class ReadyOutput:
    def __init__(self,conn): self.conn=conn
    def write(self,text):
        if '"STARTED"' in text: self.conn.send('ready')
        return len(text)
    def flush(self): pass

def run_main(argv, provider, ready):
    sys.stdout=ReadyOutput(ready)
    try: task_center_app.main(argv,execution_provider=provider)
    except BaseException as exc:
        try: ready.send('error:'+repr(exc))
        except Exception: pass
        raise

class StartupHTTPDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ProducerExecutorTests();self.f.producer_http_test=True;self.f.setUp();f=self.f
        f.s.db.execute("UPDATE gateway_task_metadata SET project_id='project-mcp' WHERE task_id='demo-b'");f.s.db.commit()
        f.profile['project_id']='project-mcp'
        self.rid=f.proposal(); self.proc=None
        self.execute_count=multiprocessing.Value('i',0);self.query_count=multiprocessing.Value('i',0);self.response=multiprocessing.Value('i',0)
    def tearDown(self):
        if self.proc is not None:
            if self.proc.is_alive(): os.kill(self.proc.pid,signal.SIGTERM)
            self.proc.join(8)
            if self.proc.is_alive():
                self.proc.terminate();self.proc.join(3)
                self.fail('test listener failed to terminate')
            self.assertEqual(self.proc.exitcode,0)
            with socket.socket() as check:
                check.settimeout(1)
                self.assertNotEqual(check.connect_ex(('127.0.0.1',self.port)),0)
        self.f.tearDown()
    def file(self,name,value):
        p=self.f.root/name
        p.write_text(value);p.chmod(0o600);return str(p)
    def start(self,connect_provider):
        f=self.f
        binding={'tenant_id':'tenant-a','principal_id':'developer-1','project_id':'project-mcp','task_id':'demo-b',
          'spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,'contract_sha256':hashlib.sha256(canonical(f.contract).encode()).hexdigest(),
          'role_id':'developer','role_version':'v1','phase':'EXECUTOR','review_kind':None,
          'authority_identity':{'issuer':'fixture','subject':'developer'},'actions':['task_development_apply'],
          'candidate_root':None,'executor_profile':f.profile}
        custody=self.file('http-writer.json',json.dumps({'demo-b':{'attempt_id':'attempt-b','ticket':f.ticket,'caller':f.caller,'lock_root':str(f.root/'locks')}}))
        cfg=self.file('http-host.json',json.dumps({'schema_version':1,'enabled':True,'bindings':[binding],
            'review_keyring_file':None,'writer_context_file':custody}))
        identity=self.file('http-identity.json',json.dumps({'users':{}}))
        c=f.control.fernet
        key=self.file('http-master.key',base64.urlsafe_b64encode(c._signing_key+c._encryption_key).decode())
        authority=self.file('http-authority.key',fixtures.KEY.decode())
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); self.port=s.getsockname()[1]
        argv=['--db',str(f.root/'ledger.sqlite'),'--test-authority-key-file',authority,'--tenant','tenant-a',
          '--principal','fixture-owner','--host','127.0.0.1','--port',str(self.port),'--model-master-key-file',key,
          '--test-identity-file',identity,'--external-origin',ORIGIN,'--enable-mcp','--mcp-development-config-file',cfg]
        provider=SyntheticProvider(self.execute_count,self.query_count,self.response) if connect_provider else None
        recv,send=multiprocessing.Pipe(False)
        self.proc=multiprocessing.Process(target=run_main,args=(argv,provider,send));self.proc.start();send.close()
        self.assertTrue(recv.poll(20),'main startup timeout')
        self.assertEqual(recv.recv(),'ready');recv.close()
        def connect():
            db=sqlite3.connect(str(f.root/'ledger.sqlite'));db.row_factory=sqlite3.Row;return db
        store=MCPAuthorizationStore(connect,'tenant-a',ORIGIN,ORIGIN+'/mcp')
        redirect='https://chatgpt.com/connector_platform_oauth_redirect';verifier='v'*64
        client=store.register({'redirect_uris':[redirect],'grant_types':['authorization_code'],'response_types':['code'],'token_endpoint_auth_method':'none'})
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        location=store.authorize({'principal_id':'developer-1'},{'response_type':'code','client_id':client['client_id'],
          'redirect_uri':redirect,'code_challenge':challenge,'code_challenge_method':'S256','state':'s','resource':ORIGIN+'/mcp','scope':'task:read task:submit'})
        self.token=store.exchange({'grant_type':'authorization_code','code':parse_qs(urlsplit(location).query)['code'][0],
          'client_id':client['client_id'],'redirect_uri':redirect,'code_verifier':verifier,'resource':ORIGIN+'/mcp'})['access_token']
    def rpc(self):
        value={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'task_development_apply',
          'arguments':{'task_id':'demo-b','attempt_id':'attempt-b','request_id':self.rid}}}
        req=Request('http://127.0.0.1:%d/mcp'%self.port,data=json.dumps(value).encode(),headers={
          'Host':'development.example.invalid','Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=8) as result: return result.status,json.loads(result.read())
        except HTTPError as e: return e.code,json.loads(e.read())
    def apply(self):
        status,value=self.rpc();self.assertEqual(status,200,repr(value));self.assertFalse(value['result']['isError'],repr(value))
        return json.loads(value['result']['content'][0]['text'])
    def count(self,kind): return self.f.s.db.execute('SELECT count(*) FROM events WHERE kind=?',(kind,)).fetchone()[0]
    def test_main_http_unknown_query_and_idempotence(self):
        self.start(True)
        status,body=self.rpc();self.assertEqual(status,500);self.assertEqual(body['error_description'],'INTERNAL_ERROR')
        self.assertEqual((self.execute_count.value,self.query_count.value),(1,0))
        self.assertEqual(self.apply()['execution_state'],'UNKNOWN')
        self.assertEqual((self.execute_count.value,self.query_count.value),(1,1))
        self.response.value=1; r=self.apply();self.assertEqual(r['execution_state'],'ISOLATED_TEST_ELIGIBLE')
        self.assertEqual(self.apply()['execution_event_id'],r['execution_event_id'])
        self.assertEqual((self.execute_count.value,self.query_count.value),(1,3))
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(1,1))
    def test_main_http_without_provider_not_connected(self):
        self.start(False);self.assertEqual(self.apply()['execution_state'],'NOT_CONNECTED')
        self.assertEqual((self.count('DEVELOPMENT_EXECUTION_INTENT'),self.count('DEVELOPMENT_EXECUTION')),(0,0))
