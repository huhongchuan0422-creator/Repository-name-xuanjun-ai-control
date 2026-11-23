"""Synthetic host executor receipts; not a real isolation/runtime acceptance."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_mcp_development_bridge as bridge
from native_development_executor import NativeDevelopmentExecutor


class RunnerFixture:
    def __init__(self):self.calls=0;self.receipts={};self.bad=False;self.unknown=False
    def execute(self,request,files):
        self.calls+=1
        assert {p:hashlib.sha256(raw).hexdigest() for p,raw in files.items()}==request['files']
        receipt={k:request[k] for k in ('schema','execution_id','candidate_sha256','code_commit','test_plan_sha256')}
        receipt.update(state='PASSED',isolation='ISOLATED',tests_executed=1,result_sha256='1'*64)
        if self.bad:receipt['code_commit']='0'*40
        self.receipts[request['execution_id']]=receipt
        if self.unknown:raise RuntimeError('FIXTURE_SEND_UNKNOWN')
        return receipt
    def lookup(self,execution_id):return self.receipts.get(execution_id)


class NativeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.b=bridge.DevelopmentBridgeTests();self.b.setUp()
        self.source,self.payload=self.b.native_apply_host()
        self.runner=RunnerFixture()
        self.b.host.native_executor=NativeDevelopmentExecutor(self.runner,'2'*64)
    def tearDown(self):self.b.tearDown()
    def apply(self):return self.b.call('developer-1','task_development_apply',request_id='native-run')
    def test_original_dispatch_runs_same_candidate_and_persists_receipt_once(self):
        result=self.apply();self.assertEqual(result['execution_state'],'TRUSTED_NATIVE_TESTS_PASSED')
        candidate=result['candidate'];self.assertTrue(candidate['execution_required'])
        self.b.f.s._require_development_execution_ready(candidate)
        again=self.apply();self.assertEqual(self.runner.calls,1)
        self.assertEqual(again['execution_receipt'],result['execution_receipt'])
        rows=self.b.f.s.db.execute("SELECT kind FROM events WHERE kind LIKE 'DEVELOPMENT_EXECUTION%'").fetchall()
        self.assertEqual(len(rows),2)
    def test_protected_loader_and_real_http_bootstrap_use_executor(self):
        import base64,sqlite3,threading
        from urllib.parse import parse_qs,urlsplit
        from urllib.request import Request,build_opener,ProxyHandler
        from task_center_app import make_server
        from task_center_mcp_auth import MCPAuthorizationStore
        from task_center_session_auth import FileTestIdentityProvider,SessionStore,password_hash
        from task_center_mcp_development import load_host
        b=self.b;f=b.f
        f.s.db.execute("UPDATE gateway_task_metadata SET project_id='project-mcp' WHERE task_id='demo-b'");f.s.db.commit()
        for binding in b.bindings:binding['project_id']='project-mcp'
        source=f.root/'native.json';config=f.root/'host.json'
        source.write_text(json.dumps({'demo-b':{'attempt-b':{'native-http':self.source}}}));source.chmod(0o600)
        config.write_text(json.dumps({'schema_version':1,'enabled':True,'bindings':b.bindings,
            'writer_context_file':None,'review_keyring_file':None,'native_source_file':str(source)}));config.chmod(0o600)
        host=load_host(str(config),native_executor=b.host.native_executor)
        identities=f.root/'http-identities.json'
        identities.write_text(json.dumps({'users':{'qa':{'enabled':True,
            'password_hash':password_hash('TEST_FIXTURE_PASSWORD_ONLY'),'tenant_id':'tenant-a',
            'principal_id':'qa','roles':['TASK_CENTER_ADMIN']}}}));identities.chmod(0o600)
        def connect():
            db=sqlite3.connect(str(f.root/'ledger.sqlite'));db.row_factory=sqlite3.Row;return db
        sessions=SessionStore(connect,'tenant-a')
        provider=FileTestIdentityProvider(str(identities))
        server=make_server(str(f.root/'ledger.sqlite'),bridge.fixtures.KEY,'tenant-a','fixture-owner',port=0,
            model_master_key=b.master,identity_provider=provider,external_origin='https://native.example.invalid',
            mcp_enabled=True,mcp_development_host=host,outbound_enabled=False,session_store=sessions)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def connect():
                db=sqlite3.connect(str(f.root/'ledger.sqlite'));db.row_factory=sqlite3.Row;return db
            origin='https://native.example.invalid';store=MCPAuthorizationStore(connect,'tenant-a',origin,origin+'/mcp')
            redirect='https://chatgpt.com/connector_platform_oauth_redirect';verifier='v'*64
            client=store.register({'redirect_uris':[redirect],'grant_types':['authorization_code'],
                'response_types':['code'],'token_endpoint_auth_method':'none'})
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            location=store.authorize({'principal_id':'developer-1'},{'response_type':'code','client_id':client['client_id'],
                'redirect_uri':redirect,'code_challenge':challenge,'code_challenge_method':'S256',
                'state':'s','resource':origin+'/mcp','scope':'task:read task:submit'})
            token=store.exchange({'grant_type':'authorization_code','code':parse_qs(urlsplit(location).query)['code'][0],
                'client_id':client['client_id'],'redirect_uri':redirect,'code_verifier':verifier,'resource':origin+'/mcp'})['access_token']
            value={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'task_development_apply',
                'arguments':{'task_id':'demo-b','attempt_id':'attempt-b','request_id':'native-http'}}}
            request=Request('http://127.0.0.1:%d/mcp'%server.server_port,data=json.dumps(value).encode(),
                headers={'Host':'native.example.invalid','Content-Type':'application/json','Authorization':'Bearer '+token})
            with build_opener(ProxyHandler({})).open(request,timeout=3) as response:result=json.loads(response.read())
            self.assertFalse(result['result']['isError'])
            payload=json.loads(result['result']['content'][0]['text'])
            self.assertEqual(payload['execution_state'],'TRUSTED_NATIVE_TESTS_PASSED')
            self.assertEqual(self.runner.calls,1)
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_missing_executor_cannot_review_native_import(self):
        self.b.host.native_executor=None
        result=self.apply()
        with self.assertRaisesRegex(ValueError,'TRUSTED_NATIVE_EXECUTION_REQUIRED'):
            self.b.f.s._require_development_execution_ready(result['candidate'])
    def test_unknown_send_reconciles_without_rerunning(self):
        self.runner.unknown=True
        with self.assertRaisesRegex(RuntimeError,'SEND_UNKNOWN'):self.apply()
        result=self.apply()
        self.assertEqual(self.runner.calls,1)
        self.assertEqual(result['execution_state'],'TRUSTED_NATIVE_TESTS_PASSED')
    def test_unknown_without_receipt_does_not_reexecute(self):
        self.runner.unknown=True
        with self.assertRaises(RuntimeError):self.apply()
        self.runner.receipts.clear()
        with self.assertRaisesRegex(ValueError,'EFFECT_UNKNOWN'):self.apply()
        self.assertEqual(self.runner.calls,1)
    def test_wrong_commit_receipt_never_unlocks_review(self):
        self.runner.bad=True
        with self.assertRaisesRegex(ValueError,'EXACT_TRUSTED_NATIVE_EXECUTION_RECEIPT'):self.apply()
        self.assertEqual(self.b.f.s.db.execute("SELECT count(*) FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone()[0],0)
    def test_execution_cannot_cross_task_attempt_or_commit(self):
        candidate=self.apply()['candidate']
        for field,value in [('task_id','other-task'),('attempt_id','other-attempt'),('code_commit','0'*40)]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'TRUSTED_NATIVE_EXECUTION_REQUIRED'):
                self.b.f.s._require_development_execution_ready(dict(candidate,**{field:value}))

    def test_replayed_receipt_requires_exact_commit_isolation_and_tests(self):
        from native_development_executor import digest,execution_event
        from task_supervisor import canonical
        candidate=self.apply()['candidate'];s=self.b.f.s;eid=execution_event(candidate)
        original=json.loads(s.db.execute('SELECT payload_json FROM events WHERE event_id=?',(eid,)).fetchone()[0])
        for field,value in [('code_commit','0'*40),('isolation','LOCAL'),('tests_executed',0),('execution_id','0'*64),('state','FAILED')]:
            modified=json.loads(json.dumps(original));modified['receipt'][field]=value
            s.db.execute('UPDATE events SET payload_json=?,evidence_ref=? WHERE event_id=?',
                (canonical(modified),digest(modified),eid));s.db.commit()
            with self.subTest(field=field),self.assertRaises(ValueError):
                s._require_development_execution_ready(candidate)

    def test_revoked_role_before_return_rejects_receipt(self):
        original=self.runner.execute
        def revoke(request,files):
            result=original(request,files)
            self.b.f.s.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='developer'");self.b.f.s.db.commit()
            return result
        self.runner.execute=revoke
        with self.assertRaisesRegex(ValueError,'CURRENT_DEVELOPMENT_ROLE'):self.apply()
        self.assertEqual(self.b.f.s.db.execute("SELECT count(*) FROM events WHERE kind='DEVELOPMENT_EXECUTION'").fetchone()[0],0)

if __name__=='__main__':unittest.main()
