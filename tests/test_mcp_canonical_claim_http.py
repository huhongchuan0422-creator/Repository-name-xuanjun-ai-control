"""Independent HTTP seam test. Keys/identities are synthetic, not live claims."""
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from development_identity_adapter import TrustedRegistrationVerifier
from development_authority import canonical_bytes
from task_supervisor import Supervisor, canonical
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from reusable_scheduler_cli import demo_graph
from model_orchestration import ModelControl
from execution_policy_gateway import ExecutionPolicyGateway
from task_center_mcp_claim import ClaimHost
from task_center_app import make_server
from task_center_mcp_auth import MCPAuthorizationStore
from task_center_session_auth import FileTestIdentityProvider, SessionStore, password_hash

KEY = b'0123456789abcdef0123456789abcdef'

class ClaimHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.path = str(self.root / 'canonical.sqlite'); self.master = Fernet.generate_key()
        self.private = Ed25519PrivateKey.generate()
        self.verifier = TrustedRegistrationVerifier(self.private.public_key())
        self.s = Supervisor(self.path, development_identity_verifier=self.verifier)
        g = GatewayKernel(self.s, TestTenantAuthority(KEY)); ctx = g.tenants.issue('tenant-a', 'admin:fixture')
        graph = demo_graph('tenant-a'); graph['project_id'] = 'project-mcp'
        graph['tasks'][0]['entry'] = 'CHATGPT'
        g.register_graph(ctx, graph)
        self.contract = dict(task_id='demo-b', spec_sha256='b'*64, checkpoint_sha256='a'*64,
            target_repository='owner/repo', target_base_sha='c'*40, entry='CHATGPT',
            developer={'issuer':'native','subject':'developer'}, allowed_files=['module.py'],
            trusted_reviewers=[{'issuer':'native','subject':'qa','key_id':'qa','role':'QA'},
                               {'issuer':'native','subject':'sec','key_id':'sec','role':'SECURITY'}])
        self.s.register_development_contract('demo-b', self.contract)
        control = ModelControl(g,ctx,self.master)
        control.create_role(dict(role_id='developer',version='v1',phase='EXECUTOR',capabilities=['code'],writer_allowed=True,enabled=True,review_kind=None))
        control.record_task_spec('demo-b','deliver patch',['module.py'],['tests'])
        policy = ExecutionPolicyGateway(g,ctx)
        policy.record_unit(dict(task_id='demo-b',delivery_stage='implementation',feature_unit='claim',goal='deliver patch',scope=['WRITE_SOURCE'],acceptance=['tests'],dependencies=['NONE'],asset_version='v1',responsible_party='test-executor'))
        observed={'matches':[]}
        policy.record_asset_query('demo-b','query','CANONICAL_DB','v1',{'lookup':{'asset_key':'claim'},'observed_result':observed,'evidence_ref':'canonical-db://claim@v1'},hashlib.sha256(canonical(observed).encode()).hexdigest())
        policy.record_dispatch_preflight('demo-b','v1',['query'],'NOT_FOUND','fixture source checked')
        digest = hashlib.sha256(canonical(self.contract).encode()).hexdigest()
        self.grant=dict(issuer='owner-auth',subject='test-executor',developer=self.contract['developer'],contract_sha256=digest,valid_until=time.time()+600)
        self.grant['signature']=base64.b64encode(self.private.sign(canonical_bytes(self.grant))).decode()
        self.custody=dict(owner_grant=self.grant,developer_credential={'contract':self.contract,'developer_identity':self.contract['developer']},
            caller={'caller_id':'trusted-host','run_id':'fixture-run','session_id':'fixture-session','gateway_id':'fixture-gateway'},
            lock_root=str(self.root/'locks'),valid_until=time.time()+500)
        binding=dict(tenant_id='tenant-a',principal_id='developer',project_id='project-mcp',task_id='demo-b',spec_sha256='b'*64,checkpoint_sha256='a'*64,contract_sha256=digest,
            role_id='developer',role_version='v1',phase='EXECUTOR',review_kind=None,authority_identity=self.contract['developer'],actions=['task_development_apply','task_development_status'],candidate_root=None,executor_profile=None)
        self.host=ClaimHost([binding],self.verifier,lambda identity,task:self.custody)
        def connect():
            db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
        self.connect=connect; sessions=SessionStore(connect,'tenant-a')
        identities=self.root/'users.json';identities.write_text(json.dumps({'users':{'qa':{'enabled':True,'password_hash':password_hash('TEST_ONLY_PASSWORD'),'tenant_id':'tenant-a','principal_id':'qa','roles':['TASK_CENTER_ADMIN']}}}));identities.chmod(0o600)
        self.origin='https://claim.example.invalid'
        self.server=make_server(self.path,KEY,'tenant-a','fixture',port=0,model_master_key=self.master,
            identity_provider=FileTestIdentityProvider(str(identities)),session_store=sessions,external_origin=self.origin,
            mcp_enabled=True,mcp_claim_host=self.host,outbound_enabled=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.token=self.token_for('developer')
    def token_for(self,principal,scope='task:read task:submit'):
        store=MCPAuthorizationStore(self.connect,'tenant-a',self.origin,self.origin+'/mcp')
        redirect='https://chatgpt.com/connector_platform_oauth_redirect';verifier='v'*64
        client=store.register({'redirect_uris':[redirect],'grant_types':['authorization_code'],'response_types':['code'],'token_endpoint_auth_method':'none'})
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        location=store.authorize({'principal_id':principal},{'response_type':'code','client_id':client['client_id'],'redirect_uri':redirect,'code_challenge':challenge,'code_challenge_method':'S256','state':'s','resource':self.origin+'/mcp','scope':scope})
        return store.exchange({'grant_type':'authorization_code','code':parse_qs(urlsplit(location).query)['code'][0],'client_id':client['client_id'],'redirect_uri':redirect,'code_verifier':verifier,'resource':self.origin+'/mcp'})['access_token']
    def rpc(self,name=None,args=None,token=None):
        value={'jsonrpc':'2.0','id':1,'method':'tools/call' if name else 'tools/list'}
        if name:value['params']={'name':name,'arguments':args if args is not None else {'task_id':'demo-b'}}
        request=Request('http://127.0.0.1:%d/mcp'%self.server.server_port,data=json.dumps(value).encode(),headers={'Host':'claim.example.invalid','Content-Type':'application/json','Authorization':'Bearer '+(token or self.token)})
        try:
            with build_opener(ProxyHandler({})).open(request,timeout=3) as r:return r.status,json.loads(r.read())
        except HTTPError as e:return e.code,json.loads(e.read())
    def payload(self,name):
        status,value=self.rpc(name);self.assertEqual(status,200,value)
        return json.loads(value['result']['content'][0]['text'])
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.s.close();self.temp.cleanup()
    def test_schema_real_claim_and_canonical_readback(self):
        status,value=self.rpc();self.assertEqual(status,200)
        tools={x['name']:x for x in value['result']['tools']}
        self.assertEqual(set(tools['task_claim']['inputSchema']['properties']),{'task_id'})
        status,contract=self.rpc('task_dispatch_contract',{});self.assertEqual(status,200)
        contract=json.loads(contract['result']['content'][0]['text'])
        self.assertTrue(contract['canonical_claim']['host_bound']);self.assertFalse(contract['execution_connected'])
        before=self.payload('task_claim_status');self.assertEqual(before['authority_state'],'NONE')
        claimed=self.payload('task_claim');self.assertEqual(claimed['state'],'RECEIVED');self.assertFalse(claimed['execution_started'])
        self.assertTrue(claimed['attempt_id'].startswith('attempt-'));self.assertTrue(claimed['lease_id'].startswith('lease-'))
        self.assertEqual(claimed,self.payload('task_claim_status'))
        print('SYNTHETIC_IDENTITY_REAL_HTTP_CLAIM_READBACK '+json.dumps({'schema':tools['task_claim']['inputSchema'],'before':before,'claimed':claimed,'readback':self.payload('task_claim_status')},sort_keys=True))
        self.assertNotEqual(self.rpc('task_claim')[0],200)
        self.assertEqual(claimed,self.payload('task_claim_status'))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM resource_claims').fetchone()[0],1)
    def test_no_forged_identity_attempt_or_admin_claim(self):
        for args in ({'task_id':'demo-b','attempt_id':'invented'},{'task_id':'demo-b','principal_id':'admin:fixture'},{'task_id':'demo-c'}):
            self.assertNotEqual(self.rpc('task_claim',args)[0],200)
        self.assertNotEqual(self.rpc('task_claim',token=self.token_for('qa'))[0],200)
        self.assertNotEqual(self.rpc('task_claim',token=self.token_for('developer','task:read'))[0],200)
        self.assertEqual(self.s._task('demo-b')['authority_state'],'NONE')
    def test_role_disabled_during_custody_lookup_cannot_claim(self):
        def disable(identity, task):
            self.s.db.execute('UPDATE role_templates SET enabled=0'); self.s.db.commit()
            return self.custody
        self.host.custody_provider=disable
        self.assertNotEqual(self.rpc('task_claim')[0],200)
        self.assertEqual(self.s._task('demo-b')['authority_state'],'NONE')
    def test_protected_bootstrap_reuses_existing_signed_custody(self):
        from cryptography.hazmat.primitives import serialization
        from task_center_mcp_development import DevelopmentHost
        from task_center_mcp_claim import load_claim_host
        public=self.root/'owner.pem';custody=self.root/'custody.json'
        public.write_bytes(self.private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo));public.chmod(0o600)
        custody.write_text(json.dumps({'demo-b':{'tenant_id':'tenant-a','principal_id':'developer','project_id':'project-mcp','custody':self.custody}}));custody.chmod(0o600)
        loaded=load_claim_host(DevelopmentHost(self.host.bindings),str(public),str(custody))
        self.host.verifier=loaded.verifier;self.host.custody_provider=loaded.custody_provider
        self.assertEqual(self.payload('task_claim')['state'],'RECEIVED')
    def test_project_and_tenant_binding_are_not_inferred_from_connectivity(self):
        self.s.db.execute("UPDATE gateway_task_metadata SET project_id='other' WHERE task_id='demo-b'");self.s.db.commit()
        self.assertNotEqual(self.rpc('task_claim')[0],200)
        self.assertEqual(self.s._task('demo-b')['authority_state'],'NONE')
    def test_bad_grant_missing_admission_and_disabled_role_hold(self):
        self.grant['signature']=base64.b64encode(b'0'*64).decode()
        self.assertNotEqual(self.rpc('task_claim')[0],200)
        self.s.db.execute('DELETE FROM dispatch_preflights');self.s.db.commit()
        self.assertNotEqual(self.rpc('task_claim')[0],200)
        self.s.db.execute('UPDATE role_templates SET enabled=0');self.s.db.commit()
        self.assertNotEqual(self.rpc('task_claim')[0],200)
        self.assertEqual(self.s._task('demo-b')['authority_state'],'NONE')

if __name__=='__main__':unittest.main()
