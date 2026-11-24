"""Original lifecycle + original authenticated handoff; isolated fake host only."""
import copy,hashlib,json,sys,threading,time,types,unittest
from unittest.mock import patch
import test_mcp_completion as fixtures
from task_center_handoff_host import HandoffHost,HostAuthAdapter
from task_center_role_contract import RoleContractResolver
from task_center_mcp_dispatch_host import dispatch_rpc,validate_config
from task_center_mcp_service import MCPTaskService

# Since the reviewed preflight interface change, HandoffHost.record and
# _accept_with_prepared_backup refuse the legacy in-transaction assess_backup
# callback and require a host-prepared two-phase assessment bound to this DB.
# This simulated provider mirrors the already-reviewed pattern in
# test_mcp_acceptance_backup_preflight_delta: it reasserts the SAME fixture
# facts inside the serialized transaction only, and grants no real backup,
# identity or production evidence.
class SimulatedPrepared:
    def __init__(self,host,adapter):self.db=host.db;self.adapter=adapter;self._guard=threading.Lock();self.expected=None
    def execute(self,host,session,value,binding):
        self.expected=copy.deepcopy(binding)
        try:return host.record(session,value)
        finally:self.expected=None
    def __call__(self,binding):
        if not self.db.in_transaction or binding!=self.expected:return None
        return self.adapter.assess_backup(binding)

_V2_FAKE=types.ModuleType('task_center_backup_bridge_v2')
_V2_FAKE.PreparedBackupAssessment=SimulatedPrepared

class SimulatedHost(HostAuthAdapter):
    def __init__(self):
        self.cycle=time.time();self.content=b'isolated-candidate-bundle';self.event=None;self.backup=True
    def authenticate_and_authorize(self,session,action,binding):
        roles={'alice':'developer','bob':'qa','carol':'acceptor'}
        return {'issuer':'formal-fixture','tenant_id':'tenant-mcp','principal_id':session,
          'session_id':'session-'+session,'role_id':roles[session],'scope':'handoff:'+action,'expires_at':time.time()+300}
    def assess_provider(self,binding):return 'CONNECTED'
    def assess_backup(self,binding):return {'state':'COMPLETE' if self.backup else 'INCOMPLETE','missing':[] if self.backup else ['RESTORE'],'cycle_at':self.cycle}
    def prepare_backup_assessment(self,host):return SimulatedPrepared(host,self)
    def assess_candidate_bundle(self,binding):
        if hashlib.sha256(self.content).hexdigest()!=binding['artifact_sha256']:return None
        return {'candidate_id':binding['candidate_id'],'artifact_sha256':binding['artifact_sha256'],
          'snapshot_sha256':binding['snapshot_sha256'],'read_location_ref':'isolated-bundle-location',
          'handoff_event_id':self.event}

class AcceptanceEvidence(unittest.TestCase):
    def _start_seam(self):
        if not self._seam_started:self._seam.start();self._seam_started=True
    def stop_seam(self):
        if self._seam_started:self._seam.stop();self._seam_started=False
    def setUp(self):
        self._seam=patch.dict(sys.modules,{'task_center_backup_bridge_v2':_V2_FAKE})
        self._seam_started=False;self._start_seam()
        self.fx=fixtures.CompletionHTTPTests();self.fx.setUp();self.h=self.fx.h;h=self.h
        # Real fixture provider/model registrations for independent reviewer roles;
        # no customer data, no provider call for this setup.
        h.control.upsert_provider({'provider_id':'review-fixture','display_name':'Review Fixture',
          'adapter_type':'openai-compatible','base_url':'http://127.0.0.1:%d'%h.f.model.server_port,
          'enabled':True,'price_state':'KNOWN_FREE','rate_limit_per_min':10,'concurrency_limit':1,
          'timeout_seconds':1,'retry_limit':0},'local-fixture-secret')
        h.control.upsert_model({'provider_id':'review-fixture','model_id':'review-chat','capabilities':['general'],
          'enabled':True,'price_state':'KNOWN_FREE','input_unit_cost':0,'output_unit_cost':0})
        h.control.db.execute("UPDATE model_assignments SET provider_id='review-fixture',model_id='review-chat' WHERE task_id='demo-b' AND role_id!='developer'");h.control.db.commit()
        roles={}
        for role,principal in [('developer','developer-1'),('qa','qa'),('acceptor','acceptor')]:
            roles[role]={'role_version':'v1','principal_id':principal,'provider_id':'fixture' if role=='developer' else 'review-fixture',
              'model_id':'fixture-chat' if role=='developer' else 'review-chat','connection_id':'fixture-connection'}
        self.config=validate_config({'schema_version':1,'enabled':True,'bindings':[{'tenant_id':'tenant-mcp','principal_id':'owner-1','project_id':'project-mcp','roles':roles}], 'completion_bindings':self.fx.bindings})
        spec=h.control.db.execute("SELECT spec_sha256 FROM tasks WHERE task_id='demo-b'").fetchone()[0]
        policy={'contract_id':'completion-fixture','contract_version':1,'tenant_id':'tenant-mcp','project_id':'project-mcp',
          'task_id':'demo-b','attempt_id':'attempt-b','task_spec_sha256':spec,'role_id':'developer','role_version':'v1',
          'role_scope':['general'],'provider_id':'fixture','required_categories':['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT'],
          'not_applicable':{'SOURCE':'NON_SOURCE_WORK_PRODUCT','INSTALL':'NO_INSTALLATION_SCOPE'}}
        acceptor_policy=dict(policy,contract_id='completion-acceptor',role_id='acceptor',provider_id='review-fixture')
        self.contract=RoleContractResolver(h.supervisor.db,[policy,acceptor_policy]);self.adapter=SimulatedHost()
        self.host=HandoffHost(h.supervisor.db,'tenant-mcp','formal-fixture',self.adapter,mcp_config=self.config,role_contract=self.contract)
        self.service=MCPTaskService(h.f.db,fx_key(),'tenant-mcp',h.f.master,'acceptor','project-mcp',execution_enabled=False)
        self.identity={'tenant_id':'tenant-mcp','principal_id':'acceptor','project_id':'project-mcp','scopes':['task:submit','task:read']}
    def tearDown(self):self.stop_seam();self.fx.tearDown()
    def make_candidate(self,review=True):
        h=self.h;artifact=hashlib.sha256(self.adapter.content).hexdigest()
        cid=h.rpc(h.token(principal='developer-1'),'task_submit_candidate',self.fx.args(artifact_sha256=artifact,checklist_sha256=self.fx.check))['candidate_id']
        if review:
            for actor in ('qa','security'):
                h.rpc(h.token(principal=actor),'task_review_candidate',self.fx.args(candidate_id=cid,findings=[],passed=True))
        return cid
    def handoff(self,cid):
        db=self.h.control.db;snapshot=db.execute('SELECT snapshot_sha256 FROM candidate_snapshots WHERE candidate_id=?',(cid,)).fetchone()[0]
        plan=self.contract.resolve('tenant-mcp','demo-b','attempt-b','fixture')
        refs={}
        for action,label,actor,parent in [('PROPOSE','p','alice',None),('NOMINATE','n','alice','p'),('RECEIVE','r','bob','p'),('ALIGNED','a','bob','r'),('SUPERVISION_START','s','carol','n'),('VERIFIED','v','carol','s')]:
            refs[label]=self.host.issue_reference(actor,'demo-b','attempt-b',1,refs['p']['event_id'] if refs else None)
            req=dict(refs[label],task_id='demo-b',attempt_id='attempt-b',action=action,
              causation=refs[parent]['event_id'] if parent else 'NONE',snapshot_digest=snapshot,backup_manifest_sha256='b'*64,
              checked=list(plan['required_checks']),provider_ref='fixture')
            if action=='NOMINATE':req['target_ref']='acceptor'
            if action=='VERIFIED':req['alignment_ref']=refs['a']['event_id']
            self.assertEqual(self.host.record(actor,req)['state'],'RECORDED')
        self.adapter.event=refs['v']['event_id']
    def call(self,cid,host=True,attempt='attempt-b'):
        value={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'task_accept_candidate','arguments':{'task_id':'demo-b','attempt_id':attempt,'candidate_id':cid}}}
        result=dispatch_rpc(self.service,self.identity,self.config,value,False,role_contract=self.contract,acceptance_host=self.host if host else None)
        return json.loads(result['result']['content'][0]['text'])
    def test_original_rpc_accept_complete_and_duplicate(self):
        cid=self.make_candidate();self.handoff(cid)
        result=self.call(cid);self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(result['canonical_task_state'],'SUCCESS');self.assertTrue(self.call(cid)['duplicate'])
        self.assertEqual(self.h.control.db.execute("SELECT count(*) FROM model_audit WHERE action='CANDIDATE_EVIDENCE_BOUND' AND target_id=?",(cid,)).fetchone()[0],1)
        identity=dict(self.identity);value={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'task_candidate_status','arguments':{'task_id':'demo-b','attempt_id':'attempt-b','candidate_id':cid}}}
        status=dispatch_rpc(self.service,identity,self.config,value,False,role_contract=self.contract,acceptance_host=self.host)
        self.assertEqual(json.loads(status['result']['content'][0]['text'])['completion_state'],'ACCEPTED')
    def test_acceptor_scope_change_before_accept_is_held(self):
        cid=self.make_candidate();self.handoff(cid)
        self.h.control.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='acceptor'");self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'TASK_CONTRACT_UNKNOWN'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_acceptor_scope_change_blocks_duplicate_claim(self):
        cid=self.make_candidate();self.handoff(cid);self.assertEqual(self.call(cid)['state'],'ACCEPTED')
        self.h.control.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='acceptor'");self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_EVIDENCE_RECONCILIATION_REQUIRED'):self.call(cid)
    def test_lost_original_evidence_anchor_is_not_reported_complete(self):
        cid=self.make_candidate();self.handoff(cid);self.assertEqual(self.call(cid)['state'],'ACCEPTED')
        self.h.control.db.execute("DELETE FROM model_audit WHERE action='CANDIDATE_EVIDENCE_BOUND' AND target_id=?",(cid,));self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_EVIDENCE_RECONCILIATION_REQUIRED'):self.call(cid)
        value={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'task_candidate_status','arguments':{'task_id':'demo-b','attempt_id':'attempt-b','candidate_id':cid}}}
        status=dispatch_rpc(self.service,self.identity,self.config,value,False,role_contract=self.contract,acceptance_host=self.host)
        self.assertEqual(json.loads(status['result']['content'][0]['text'])['completion_state'],'HOLD_HANDOFF_EVIDENCE_RECONCILIATION')
    def test_missing_backup_and_role_scope_leave_task_unfinished(self):
        cid=self.make_candidate();self.handoff(cid);self.adapter.backup=False
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertGreater(self.h.control.db.execute("SELECT count(*) FROM outbox WHERE task_id='demo-b' AND delivered_at IS NULL").fetchone()[0],0)
        self.adapter.backup=True;self.h.control.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='developer'");self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'TASK_CONTRACT_UNKNOWN'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_missing_review_host_and_wrong_attempt(self):
        cid=self.make_candidate(False)
        with self.assertRaisesRegex(ValueError,'REVIEW_PASS_REQUIRED'):self.call(cid)
        with self.assertRaisesRegex(ValueError,'STALE_TASK_ATTEMPT'):self.call(cid,attempt='wrong')
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_review_receipt_tamper_rejected_before_terminal(self):
        cid=self.make_candidate();self.handoff(cid)
        self.h.control.db.execute("DELETE FROM candidate_reviews WHERE candidate_id=? AND review_kind='SECURITY'",(cid,));self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_REVIEW_RECEIPTS_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.h.control.db.execute("SELECT state FROM delivery_candidates WHERE candidate_id=?",(cid,)).fetchone()[0],'REVIEW_PASSED')
    def test_missing_handoff_and_unreadable_artifact_fail_closed(self):
        cid=self.make_candidate();self.handoff(cid)
        self.adapter.content=b'different-bytes'
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BUNDLE_READBACK_REQUIRED'):self.call(cid)
        self.adapter.content=b'isolated-candidate-bundle'
        self.h.control.db.execute("DELETE FROM events WHERE event_id=?",('handoff-contract:'+self.adapter.event,));self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_HANDOFF_RECEIPTS_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_terminal_transaction_rechecks_backup_revocation(self):
        from unittest.mock import patch
        from task_supervisor import Supervisor
        cid=self.make_candidate();self.handoff(cid);original=Supervisor.record;owner=self
        def record(supervisor,*args,**kwargs):
            if kwargs.get('terminal_admission_check') is not None:owner.adapter.backup=False
            return original(supervisor,*args,**kwargs)
        with patch.object(Supervisor,'record',record):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.h.control.db.execute("SELECT state FROM delivery_candidates WHERE candidate_id=?",(cid,)).fetchone()[0],'REVIEW_PASSED')
    def test_unknown_effects_remain_held_without_provider_call(self):
        cid=self.make_candidate();self.handoff(cid)
        self.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'accept-unknown',8,'fixture-connection')
        self.h.control.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='accept-unknown'");self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.h.control.db.execute("SELECT state FROM model_requests WHERE idempotency_key='accept-unknown'").fetchone()[0],'UNKNOWN')
    def test_missing_real_host_fails_closed(self):
        cid=self.make_candidate()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_TRUSTED_HOST_REQUIRED'):self.call(cid,False)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')

def fx_key():return b'0123456789abcdef0123456789abcdef'
if __name__=='__main__':unittest.main()
