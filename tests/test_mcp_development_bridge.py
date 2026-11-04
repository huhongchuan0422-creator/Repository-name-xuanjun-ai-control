import hashlib
import hmac
import importlib.util
import json
import copy
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT
sys.path.insert(0,str(BASE/'scripts'));sys.path.insert(0,str(ROOT/'scripts'))
from task_center_mcp_development import DevelopmentHost
from task_center_mcp_dispatch_host import dispatch_rpc,validate_config
from task_center_mcp_service import MCPTaskService
from task_supervisor import canonical
import entry_review_gate as gate
spec=importlib.util.spec_from_file_location('local_fixture',ROOT/'tests/test_local_development_executor.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
sys.path.insert(0,str(ROOT/'scripts'))

class DevelopmentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.LocalExecutorTests();self.f.setUp();f=self.f
        self.keys={'TEST-QA':b'Q'*32,'TEST-SECURITY':b'S'*32}
        for rid,phase,kind in [('qa','REVIEWER','QA'),('security','REVIEWER','SECURITY'),('acceptor','ACCEPTOR',None)]:
            f.control.create_role({'role_id':rid,'version':'v1','phase':phase,'capabilities':['code'],'writer_allowed':False,'enabled':True,'review_kind':kind})
            f.control.assign('demo-b',rid,'v1',rid)
        self.bindings=[]
        for rid,principal,phase,kind,subject,action in [('developer','developer-1','EXECUTOR',None,'developer','task_development_apply'),
            ('qa','qa','REVIEWER','QA','qa','task_development_review'),('acceptor','acceptor','ACCEPTOR',None,'acceptor','task_development_finalize')]:
            self.bindings.append({'tenant_id':'tenant-a','principal_id':principal,'project_id':'demo-project','task_id':'demo-b',
                'spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,'contract_sha256':hashlib.sha256(canonical(f.contract).encode()).hexdigest(),
                'role_id':rid,'role_version':'v1','phase':phase,'review_kind':kind,'authority_identity':{'issuer':'fixture','subject':subject},
                'actions':[action,'task_development_status'],'candidate_root':None,'executor_profile':f.profile if phase=='EXECUTOR' else None})
        self.host=self.makehost()
    def tearDown(self):self.f.tearDown()
    def makehost(self):
        f=self.f
        return DevelopmentHost(self.bindings,lambda task,ids:{k:self.keys[k] for k in ids},
            lambda task,attempt:{'ticket':f.ticket,'caller':f.caller,'lock_root':str(f.root/'locks')})
    def call(self,actor,name,**args):
        identity={'tenant_id':'tenant-a','principal_id':actor,'project_id':'demo-project','scopes':['task:read','task:submit']}
        service=MCPTaskService(str(self.f.root/'ledger.sqlite'),fixtures.KEY,'tenant-a',self.master,actor,'demo-project')
        # Service holds the same valid pre-existing master key passed to control.
        service.principal_id=actor;service.master_key=self.master
        value={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':dict(task_id='demo-b',attempt_id='attempt-b',**args)}}
        out=dispatch_rpc(service,identity,validate_config(None),value,False,self.host)
        return json.loads(out['result']['content'][0]['text'])
    @property
    def master(self):
        # Fernet keeps signing+encryption bytes, reconstruct fixture key only.
        import base64
        f=self.f.control.fernet
        return base64.urlsafe_b64encode(f._signing_key+f._encryption_key)
    def native_candidate(self):
        f=self.f;checkout=f.root/'checkout'
        subprocess.check_call(['git','clone','-q','--branch','main',str(f.repo),str(checkout)],stderr=subprocess.DEVNULL)
        subprocess.check_call(['git','-C',str(checkout),'remote','set-url','origin','https://github.com/owner/repo.git'])
        for b in self.bindings:b['candidate_root']=str(checkout)
        self.host=self.makehost()
        receipt=dict(schema=1,entry='CHATGPT',execution_path='CHATGPT_NATIVE',task_id='demo-b',spec_sha256='b'*64,checkpoint_sha256='a'*64,
            target_repository='owner/repo',target_base_sha=f.base,code_commit=f.base,event='CODE_READY',attempt_id='attempt-b',
            lease_id=f.ticket['lease_id'],fence=f.ticket['fence'],epoch=f.ticket['epoch'],lock_provider_id=f.fence.locks.provider_id,
            source_comment_id=1,status='RECEIPT_VALIDATED_NOT_ADMITTED',native_identity='TEST_FIXTURE_NOT_REAL_GITHUB',
            quota_attribution='TEST_ONLY',authority_effect='NONE',required_gate='CANONICAL_TASK_SPEC_CHECKPOINT_TARGET_LEASE_FENCE',**f.caller)
        candidate=f.s.bind_development_candidate(receipt,{'module.py':hashlib.sha256(f.before_raw).hexdigest()})
        contract=dict(f.contract,code_commit=f.base);bundle=gate.review_bundle(contract,{'module.py':f.before_raw},[])['bundle_sha256']
        reviews=[]
        for r in f.contract['trusted_reviewers']:
            payload={'reviewer':{k:r[k] for k in ('issuer','subject')},'role':r['role'],'bundle_sha256':bundle,'decision':'PASS'}
            record={'schema':1,'key_id':r['key_id'],'record_id':gate.digest(gate.canonical(payload)),'payload':payload}
            record['signature']=hmac.new(self.keys[r['key_id']],gate.canonical(record),hashlib.sha256).hexdigest();reviews.append(record)
        return candidate['candidate_event_id'],reviews
    def test_source_apply_uses_original_writer_and_never_executes_code(self):
        rid=self.f.proposal();result=self.call('developer-1','task_development_apply',request_id=rid)
        self.assertEqual(result['execution_state'],'HOLD_SANDBOX_UNAVAILABLE');self.assertFalse(result['generated_code_executed'])
        self.assertEqual(self.f.git('show','refs/heads/main:module.py'),self.f.raw.decode().strip())
        with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX'):
            self.call('qa','task_development_review',candidate_event_id=result['candidate_event_id'],reviewed_event_id='review-local',reviews=[])
    def test_native_signed_review_and_original_revoke_finalize(self):
        candidate,reviews=self.native_candidate()
        result=self.call('qa','task_development_review',candidate_event_id=candidate,reviewed_event_id='review-native',reviews=reviews)
        self.assertEqual(result['state'],'ISOLATED_TEST_ELIGIBLE');self.assertEqual(self.f.s._task('demo-b')['state'],'STARTED')
        with self.assertRaisesRegex(ValueError,'REVOCATION'):
            self.call('acceptor','task_development_finalize',reviewed_event_id='review-native',completion_event_id='complete-native')
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'original-test-owner'}
        self.f.fence.begin_revocation('demo-b',controller);self.f.fence.drain('demo-b',controller,timeout=1)
        self.f.fence.invalidate_source_resources('demo-b','original-test-revocation');self.f.s.complete_revocation('demo-b')
        result=self.call('acceptor','task_development_finalize',reviewed_event_id='review-native',completion_event_id='complete-native')
        self.assertEqual(self.f.s._task('demo-b')['state'],'SUCCESS')
        self.assertGreater(self.f.s.db.execute("SELECT count(*) FROM model_audit WHERE action='AUTHENTICATED_MCP_DEVELOPMENT'").fetchone()[0],0)
    def test_missing_host_key_and_writer_providers_reject(self):
        self.host=DevelopmentHost(self.bindings)
        with self.assertRaisesRegex(ValueError,'WRITER_CONTEXT'):self.call('developer-1','task_development_apply',request_id='none')
        candidate,reviews=self.native_candidate();self.host.review_keys_provider=None
        with self.assertRaisesRegex(ValueError,'TRUSTED_REVIEW_KEYS'):self.call('qa','task_development_review',candidate_event_id=candidate,reviewed_event_id='review-none',reviews=reviews)
    def test_forged_review_and_wrong_host_spec_reject(self):
        candidate,reviews=self.native_candidate();reviews[0]['signature']='0'*64
        with self.assertRaisesRegex(ValueError,'SIGNATURE'):self.call('qa','task_development_review',candidate_event_id=candidate,reviewed_event_id='review-bad',reviews=reviews)
        self.host.bindings[0]['spec_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'PINNED'):self.call('developer-1','task_development_status')
    def test_real_http_oauth_signed_review(self):
        import base64,sqlite3,threading
        from urllib.parse import parse_qs,urlsplit
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from task_center_app import make_server
        from task_center_mcp_auth import MCPAuthorizationStore
        from task_center_session_auth import FileTestIdentityProvider,SessionStore,password_hash
        candidate,reviews=self.native_candidate();f=self.f
        f.s.db.execute("UPDATE gateway_task_metadata SET project_id='project-mcp' WHERE task_id='demo-b'");f.s.db.commit()
        for b in self.bindings:
            b['project_id']='project-mcp'
            if b['executor_profile'] is not None:b['executor_profile']['project_id']='project-mcp'
        self.host=self.makehost()
        path=f.root/'http-identities.json';path.write_text(json.dumps({'users':{'qa':{'enabled':True,
            'password_hash':password_hash('TEST_FIXTURE_PASSWORD_ONLY'),'tenant_id':'tenant-a','principal_id':'qa','roles':['TASK_CENTER_ADMIN']}}}));path.chmod(0o600)
        def connect():
            db=sqlite3.connect(str(f.root/'ledger.sqlite'));db.row_factory=sqlite3.Row;return db
        sessions=SessionStore(connect,'tenant-a');origin='https://development.example.invalid'
        server=make_server(str(f.root/'ledger.sqlite'),fixtures.KEY,'tenant-a','fixture-owner',port=0,
            model_master_key=self.master,identity_provider=FileTestIdentityProvider(str(path)),session_store=sessions,
            outbound_enabled=False,external_origin=origin,mcp_enabled=True,mcp_development_host=self.host)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            store=MCPAuthorizationStore(connect,'tenant-a',origin,origin+'/mcp')
            redirect='https://chatgpt.com/connector_platform_oauth_redirect';verifier='v'*64
            client=store.register({'redirect_uris':[redirect],'grant_types':['authorization_code'],'response_types':['code'],'token_endpoint_auth_method':'none'})
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            location=store.authorize({'principal_id':'qa'},{'response_type':'code','client_id':client['client_id'],
                'redirect_uri':redirect,'code_challenge':challenge,'code_challenge_method':'S256','state':'s','resource':origin+'/mcp','scope':'task:read task:submit'})
            token=store.exchange({'grant_type':'authorization_code','code':parse_qs(urlsplit(location).query)['code'][0],
                'client_id':client['client_id'],'redirect_uri':redirect,'code_verifier':verifier,'resource':origin+'/mcp'})['access_token']
            def rpc(method,params=None):
                value={'jsonrpc':'2.0','id':1,'method':method}
                if params is not None:value['params']=params
                request=Request('http://127.0.0.1:%d/mcp'%server.server_port,data=json.dumps(value).encode(),
                    headers={'Host':'development.example.invalid','Authorization':'Bearer '+token,'Content-Type':'application/json'})
                return json.loads(urlopen(request,timeout=3).read())
            self.assertIn('task_development_review',[x['name'] for x in rpc('tools/list')['result']['tools']])
            result=rpc('tools/call',{'name':'task_development_review','arguments':{'task_id':'demo-b','attempt_id':'attempt-b',
                'candidate_event_id':candidate,'reviewed_event_id':'http-reviewed','reviews':reviews}})
            self.assertFalse(result['result']['isError'])
            self.assertEqual(f.s._task('demo-b')['state'],'STARTED')
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_owned_host_loader_reuses_existing_fixture_keys_and_writer(self):
        from task_center_mcp_development import load_host
        f=self.f;keys=f.root/'existing-test-keys.json';writer=f.root/'existing-test-writer.json';receipts=f.root/'existing-tool-receipts.json';receipt_keys=f.root/'existing-tool-receipt-keys.json';config=f.root/'development-host.json'
        keys.write_text(json.dumps({k:v.hex() for k,v in self.keys.items()}));keys.chmod(0o600)
        writer.write_text(json.dumps({'demo-b':{'attempt_id':'attempt-b','ticket':f.ticket,'caller':f.caller,'lock_root':str(f.root/'locks')}}));writer.chmod(0o600)
        proof={'run_id':'run-1','session_id':'session-1',
            'call':{'id':'call-1','name':'exec_command','arguments':{'cmd':'fixture'}},
            'result':{'toolCallId':'call-1','name':'exec_command','isError':False,
                      'exit_code':0,'output':'fixture'}}
        receipt_key=b'R'*32;signature=hmac.new(receipt_key,canonical(proof).encode(),hashlib.sha256).hexdigest()
        receipts.write_text(json.dumps({'run-1':{'key_id':'fixture-receipt','payload':proof,'signature':signature}}));receipts.chmod(0o600)
        receipt_keys.write_text(json.dumps({'fixture-receipt':receipt_key.hex()}));receipt_keys.chmod(0o600)
        cfg={'schema_version':1,'enabled':True,'bindings':self.bindings,
             'review_keyring_file':str(keys),'writer_context_file':str(writer),
             'tool_receipt_file':str(receipts),'tool_receipt_key_file':str(receipt_keys)}
        config.write_text(json.dumps(cfg));config.chmod(0o600);self.host=load_host(str(config))
        self.assertEqual(self.host.tool_receipt_reader('run-1'),proof)
        bad=json.loads(receipts.read_text());bad['run-1']['signature']='0'*64;receipts.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,'SIGNATURE'):self.host.tool_receipt_reader('run-1')
        receipts.write_text(json.dumps({'run-1':{'key_id':'fixture-receipt','payload':proof,'signature':signature}}))
        with self.assertRaisesRegex(ValueError,'EXISTING_TOOL_RECEIPT'):
            self.host.tool_receipt_reader('run-2')
        result=self.call('developer-1','task_development_apply',request_id=f.proposal())
        self.assertEqual(result['execution_state'],'HOLD_SANDBOX_UNAVAILABLE')
        self.assertNotIn('source_comment_id',result)
        writer.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'WRITER_CUSTODY'):self.host.writer_context_provider('demo-b','attempt-b')

    def test_gateway_tool_observation_does_not_bypass_exact_tree_test_hold(self):
        f=self.f
        result=self.call('developer-1','task_development_apply',request_id=f.proposal())
        local=f.s.development_candidate('demo-b',result['candidate_event_id'])
        candidate=dict(local,source_kind='ORIGINAL_GATEWAY_MULTIFILE_PENDING_EFFECT',
                       tree=f.git('rev-parse',local['code_commit']+'^{tree}'))
        candidate_id='gateway-candidate-fixture'
        body=canonical(candidate);evidence=hashlib.sha256(body.encode()).hexdigest()
        f.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
            ('demo-b','attempt-b',candidate_id,'DEVELOPMENT_CANDIDATE',
             f.s.clock(),'SOURCE_COMMIT',evidence,body))
        observation={'schema':1,'source_kind':'ORIGINAL_HOST_TOOL_EVENT_OBSERVATION',
            'candidate_event_id':candidate_id,'candidate_sha256':evidence,
            'run_id':'123','session_id':'session-1','tool':'exec_command',
            'tool_call_id':'call-1','call_sha256':'c'*64,'output_sha256':'d'*64,
            'state':'TEST_EVENT_OBSERVED_NOT_ACCEPTED','tested_tree_binding':'UNKNOWN',
            'expected_test_plan_binding':'UNKNOWN','development_complete':False}
        obs_body=canonical(observation);obs_id='gateway-observation-fixture'
        f.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
            ('demo-b','attempt-b',obs_id,'DEVELOPMENT_TEST_OBSERVATION',
             f.s.clock(),'TOOL_EVENT',hashlib.sha256(obs_body.encode()).hexdigest(),obs_body))
        f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'FIXED_RUNTIME_LOCAL_CANDIDATE'):
            f.s.record_development_ci('demo-b',candidate_id,123,lambda:None)
        with self.assertRaisesRegex(ValueError,'HOLD_GATEWAY_SOURCE_EFFECT_AND_TEST_BINDING'):
            f.s._require_development_execution_ready(candidate)
    def test_gateway_receipt_binds_tree_plan_reconciles_and_reaches_finalize(self):
        from gateway_multifile_candidate import record_test_event,WORKSPACE
        f=self.f
        applied=self.call('developer-1','task_development_apply',request_id=f.proposal())
        local=f.s.development_candidate('demo-b',applied['candidate_event_id'])
        opid='gateway-source-receipt-fixture'
        operation={'operation_id':opid,'event_id':opid,'operation_kind':'OPENCLAW_DEVELOPMENT_TURN',
            'resource_key':'git:owner/repo/main',
            'expected_before':{'repo':'owner/repo','branch':'feature/mcp-pr17-gateway-successor-20261031','head':f.base},
            'requested_after':{'task_id':'demo-b','attempt_id':'attempt-b','request_id':'request-fixture',
                               'contract_sha256':hashlib.sha256(canonical(f.contract).encode()).hexdigest()},
            'request_sha256':'1'*64,'operation_marker':'xuanjun-op:'+opid}
        f.fence.prepare(f.ticket,f.caller,operation)
        with f.fence.commit_lease(f.ticket,f.caller,opid) as lease:
            lease.unknown({'kind':'OPENCLAW_TURN_SOURCE_EFFECTS_REQUIRE_READBACK','transport_state':'GATEWAY_TURN_RETURNED',
                           'run_id':'123','session_id':'session-1'})
        candidate=dict(local,source_kind='ORIGINAL_GATEWAY_MULTIFILE_PENDING_EFFECT',source_operation_id=opid,
                       tree=f.git('rev-parse',local['code_commit']+'^{tree}'),all_changes_attributed_to_task=False,
                       source_effect_state='UNKNOWN_RECONCILIATION_REQUIRED')
        candidate_id='gateway-candidate-receipt-fixture';body=canonical(candidate)
        f.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('demo-b','attempt-b',candidate_id,
            'DEVELOPMENT_CANDIDATE',f.s.clock(),'SOURCE_COMMIT',hashlib.sha256(body.encode()).hexdigest(),body));f.s.db.commit()
        spec=f.s.db.execute('SELECT goal,deliverables_json,acceptance_json FROM task_work_specs WHERE task_id=?',('demo-b',)).fetchone()
        acceptance=json.loads(spec['acceptance_json']);command='/usr/bin/python3 -m unittest tests.test_fixture'
        plan={'plan_id':'fixture-plan-v1','command':command,'workdir':WORKSPACE,'expected_tree':candidate['tree'],
              'work_spec_sha256':hashlib.sha256(canonical(dict(spec)).encode()).hexdigest(),
              'acceptance_sha256':hashlib.sha256(canonical(acceptance).encode()).hexdigest()}
        receipt={'schema':1,'kind':'ORIGINAL_GATEWAY_FIXED_TEST_RECEIPT','task_id':'demo-b','attempt_id':'attempt-b',
            'operation_id':opid,'candidate_event_id':candidate_id,
            'candidate_sha256':hashlib.sha256(body.encode()).hexdigest(),'run_id':'123','session_id':'session-1',
            'source':{'repository':'owner/repo','branch':'feature/mcp-pr17-gateway-successor-20261031','base_sha':f.base,
                      'code_commit':candidate['code_commit'],'tree':candidate['tree'],'files':candidate['files']},
            'test_plan':plan,'call':{'id':'call-1','name':'exec_command','arguments':{'cmd':command,'workdir':WORKSPACE}},
            'result':{'toolCallId':'call-1','name':'exec_command','isError':False,'exit_code':0,'output':'Ran 1 test\nOK'}}
        failed=copy.deepcopy(receipt);failed['result']['exit_code']=1
        with self.assertRaisesRegex(ValueError,'MATCHED_SUCCESSFUL_TOOL_EVENTS'):
            record_test_event(f.s,'demo-b',candidate_id,'123',lambda run:failed,lambda:True)
        drift=copy.deepcopy(receipt);drift['test_plan']['expected_tree']='0'*40
        with self.assertRaisesRegex(ValueError,'EXACT_TASK_VERSIONED_TEST_PLAN'):
            record_test_event(f.s,'demo-b',candidate_id,'123',lambda run:drift,lambda:True)
        self.assertEqual(f.s.db.execute('SELECT state FROM writer_operations WHERE operation_id=?',(opid,)).fetchone()[0],'UNKNOWN')
        result=record_test_event(f.s,'demo-b',candidate_id,'123',lambda run:receipt,lambda:True)
        self.assertEqual(result['execution_state'],'TESTS_PASSED_EXACT_TREE')
        self.assertEqual(result['source_effect_state'],'CONFIRMED')
        replay=record_test_event(f.s,'demo-b',candidate_id,'123',lambda run:receipt,lambda:True)
        self.assertTrue(replay['duplicate'])
        f.s._require_development_execution_ready(candidate)
        checkout=f.root/'gateway-checkout';subprocess.check_call(['git','clone','-q','--branch','main',str(f.repo),str(checkout)],stderr=subprocess.DEVNULL)
        subprocess.check_call(['git','-C',str(checkout),'remote','set-url','origin','https://github.com/owner/repo.git'])
        for binding in self.bindings:binding['candidate_root']=str(checkout)
        self.host=self.makehost()
        contract=dict(f.contract,code_commit=candidate['code_commit']);files={'module.py':f.raw}
        bundle=gate.review_bundle(contract,files,[])['bundle_sha256'];reviews=[]
        for reviewer in f.contract['trusted_reviewers']:
            payload={'reviewer':{k:reviewer[k] for k in ('issuer','subject')},'role':reviewer['role'],
                     'bundle_sha256':bundle,'decision':'PASS'}
            record={'schema':1,'key_id':reviewer['key_id'],'record_id':gate.digest(gate.canonical(payload)),'payload':payload}
            record['signature']=hmac.new(self.keys[reviewer['key_id']],gate.canonical(record),hashlib.sha256).hexdigest();reviews.append(record)
        reviewed=self.call('qa','task_development_review',candidate_event_id=candidate_id,reviewed_event_id='gateway-reviewed',reviews=reviews)
        self.assertEqual(reviewed['state'],'ISOLATED_TEST_ELIGIBLE')
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'original-test-owner'}
        f.fence.begin_revocation('demo-b',controller);f.fence.drain('demo-b',controller,timeout=1)
        f.fence.invalidate_source_resources('demo-b','gateway-test-revocation');f.s.complete_revocation('demo-b')
        finalized=self.call('acceptor','task_development_finalize',reviewed_event_id='gateway-reviewed',completion_event_id='gateway-complete')
        self.assertEqual(finalized['state'],'SUCCESS')
    def test_host_loader_default_off_and_duplicate_key_rejected(self):
        from task_center_mcp_development import load_host
        p=self.f.root/'host-config.json';p.write_text(json.dumps({'schema_version':1,'enabled':False,'bindings':[],
            'review_keyring_file':None,'writer_context_file':None}));p.chmod(0o600)
        self.assertIsNone(load_host(str(p)))
        p.write_text('{"enabled":false,"enabled":true}')
        with self.assertRaisesRegex(ValueError,'CONFIG'):load_host(str(p))

    def test_default_off_does_not_mount_development_actions(self):
        service=MCPTaskService(str(self.f.root/'ledger.sqlite'),fixtures.KEY,'tenant-a',self.master,'qa','demo-project')
        identity={'tenant_id':'tenant-a','principal_id':'qa','project_id':'demo-project','scopes':['task:read','task:submit']}
        listed=dispatch_rpc(service,identity,validate_config(None),{'jsonrpc':'2.0','id':1,'method':'tools/list'},False)
        self.assertFalse(any(x['name'].startswith('task_development_') for x in listed['result']['tools']))
        with self.assertRaisesRegex(ValueError,'DEVELOPMENT_HOST_UNAVAILABLE'):
            dispatch_rpc(service,identity,validate_config(None),{'jsonrpc':'2.0','id':1,'method':'tools/call',
                'params':{'name':'task_development_status','arguments':{'task_id':'demo-b','attempt_id':'attempt-b'}}},False)
    def test_current_role_revoked_or_cross_project_cannot_review(self):
        candidate,reviews=self.native_candidate()
        self.f.s.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='qa'");self.f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'CURRENT_DEVELOPMENT_ROLE'):
            self.call('qa','task_development_review',candidate_event_id=candidate,reviewed_event_id='denied-review',reviews=reviews)
        self.assertIsNone(self.f.s.db.execute("SELECT 1 FROM events WHERE event_id='denied-review'").fetchone())
    def test_native_signature_bundle_drift_and_dirty_checkout_reject(self):
        candidate,reviews=self.native_candidate()
        root=Path(self.bindings[1]['candidate_root']);(root/'module.py').write_text('changed uncommitted code')
        with self.assertRaisesRegex(ValueError,'DIRTY_CANDIDATE'):
            self.call('qa','task_development_review',candidate_event_id=candidate,reviewed_event_id='dirty-review',reviews=reviews)

    def test_host_current_writer_allowed_revoked_blocks_apply(self):
        rid=self.f.proposal()
        self.f.s.db.execute("UPDATE role_templates SET writer_allowed=0 WHERE role_id='developer'");self.f.s.db.commit()
        with self.assertRaisesRegex(ValueError,'CURRENT_DEVELOPMENT_ROLE'):self.call('developer-1','task_development_apply',request_id=rid)
        self.assertEqual(self.f.git('rev-parse','refs/heads/main'),self.f.base)
        self.assertEqual(self.f.s.db.execute('SELECT count(*) FROM writer_operations').fetchone()[0],0)

    def test_unbound_identity_and_argument_authority_rejected(self):
        with self.assertRaisesRegex(ValueError,'HOST_ACTION'):self.call('unknown','task_development_status')
        with self.assertRaisesRegex(ValueError,'EXACT_DEVELOPMENT_ARGUMENTS'):self.call('developer-1','task_development_apply',request_id='r',source_comment_id=99)

if __name__=='__main__':unittest.main()
