"""End-to-end isolated host contract test; simulated subject and backup only."""
import copy, json, unittest
import test_handoff_host_delta as fixtures
from task_center_handoff_host import HandoffHost
from task_center_role_contract import RoleContractResolver

class RoleHostDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.HostDelta();self.f.setUp();self.db=self.f.db;self.auth=self.f.auth
        self.db.execute("INSERT INTO tasks SELECT 'task-2',attempt_id,authority_state,authority_valid_until,fence,epoch,resource_scope_json,resource_scope_digest,last_trusted_time,? FROM tasks WHERE task_id='task-1'",('b'*64,))
        self.db.execute("INSERT INTO gateway_task_metadata VALUES('task-2','tenant-1','demo-project')")
        self.db.execute("INSERT INTO resource_claims SELECT 'task-2',resource_key,attempt_id,fence,epoch,state FROM resource_claims WHERE task_id='task-1'")
        self.db.execute("INSERT INTO model_assignments VALUES('tenant-1','task-2','attempt-1','role-designer','v1','designer','fixture-ui','ui-model','ASSIGNED')")
        self.db.execute('INSERT INTO role_templates VALUES(?,?,?,?,?)',('tenant-1','role-designer','v1',json.dumps(['design']),1));self.db.commit()
        self.config=copy.deepcopy(fixtures.CONFIG)
        self.config['bindings'][0]['roles']['role-designer']={'role_version':'v1','principal_id':'designer','provider_id':'fixture-ui','model_id':'ui-model','connection_id':'fixture-ui-connection'}
        self.auth.assess_provider=lambda binding:'CONNECTED'
        def contract(task,role,provider,scope,spec,required,na):
            return dict(contract_id='contract-'+task,contract_version=1,tenant_id='tenant-1',project_id='demo-project',task_id=task,attempt_id='attempt-1',task_spec_sha256=spec*64,role_id=role,role_version='v1',role_scope=[scope],provider_id=provider,required_categories=required,not_applicable=na)
        self.dev=contract('task-1','role-agent','fixture-only','code','a',['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT','INSTALL','SOURCE'],{})
        self.ui=contract('task-2','role-designer','fixture-ui','design','b',['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT'],{'SOURCE':'NON_SOURCE_WORK_PRODUCT','INSTALL':'NO_INSTALLATION_SCOPE'})
        self.resolver=RoleContractResolver(self.db,[self.dev,self.ui])
        self.host=HandoffHost(self.db,'tenant-1','formal-fixture',self.auth,clock=lambda:1000,mcp_config=self.config,role_contract=self.resolver)
    def tearDown(self):self.f.tearDown()
    def req(self,task,provider):
        ref=self.host.issue_reference('alice',task,'attempt-1',1)
        policy=self.resolver.resolve('tenant-1',task,'attempt-1',provider)
        return dict(ref,task_id=task,attempt_id='attempt-1',action='PROPOSE',causation='NONE',snapshot_digest='c'*64,backup_manifest_sha256='d'*64,checked=list(policy['required_checks']),provider_ref=provider)
    def test_two_professions_end_to_end_alert_and_applicability_readback(self):
        for task,provider in (('task-1','fixture-only'),('task-2','fixture-ui')):
            req=self.req(task,provider);self.auth.backup={'state':'INCOMPLETE','missing':['ARTIFACT'],'cycle_at':990}
            result=self.host.record('alice',req);self.assertEqual(result['alert_delivery'],'UNKNOWN')
            self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE task_id=? AND kind='AUTHENTICATED_HANDOFF_PROPOSE'",(task,)).fetchone()[0],0)
            self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990};self.assertEqual(self.host.record('alice',req)['state'],'RECORDED')
            receipt=self.host.read_receipt('bob',task,'attempt-1',req['event_id']);self.assertIn('ARTIFACT',receipt['contract']['required_checks'])
            self.assertEqual(receipt['history'][0]['missing'],['ARTIFACT'])
            self.assertEqual('SOURCE' in receipt['checked'],task=='task-1')
            self.assertEqual('INSTALL_ENTRY' in receipt['checked'],task=='task-1')
            self.assertEqual(bool(receipt['contract']['not_applicable']),task=='task-2')
    def test_missing_contract_never_success_and_wrong_scope_rejected(self):
        req=self.req('task-2','fixture-ui');self.host.role_contract=None
        self.assertEqual(self.host.record('alice',req)['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind='AUTHENTICATED_HANDOFF_PROPOSE'").fetchone()[0],0)
        self.host.role_contract=self.resolver;self.db.execute("UPDATE role_templates SET capabilities_json='[]' WHERE role_id='role-designer'");self.db.commit()
        self.assertEqual(self.host.record('alice',req)['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
    def test_recorded_contract_digest_and_scope_are_revalidated(self):
        req=self.req('task-2','fixture-ui');self.host.record('alice',req)
        key='handoff-host:'+req['event_id'];row=self.db.execute('SELECT payload_json FROM events WHERE event_id=?',(key,)).fetchone();payload=json.loads(row[0]);payload['contract_sha256']='e'*64
        self.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(payload),key));self.db.commit()
        with self.assertRaises(ValueError):self.host.read_receipt('bob','task-2','attempt-1',req['event_id'])
    def test_backup_receives_contract_binding_not_caller_waiver(self):
        req=self.req('task-2','fixture-ui');seen=[]
        def assess(binding):
            seen.append(copy.deepcopy(binding));return {'state':'INCOMPLETE','missing':['CREDENTIAL_RECOVERY'],'cycle_at':990}
        self.auth.assess_backup=assess
        self.assertEqual(self.host.record('alice',req)['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(seen[0]['contract_id'],self.ui['contract_id'])
        self.assertEqual(seen[0]['applicability']['not_applicable'],self.ui['not_applicable'])
        self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind='AUTHENTICATED_HANDOFF_PROPOSE'").fetchone()[0],0)

    def test_caller_cannot_claim_na_or_omit_required_artifact(self):
        req=self.req('task-2','fixture-ui');req['not_applicable']={'SOURCE':'anything'}
        with self.assertRaises(ValueError):self.host.record('alice',req)
        del req['not_applicable'];req['checked'].remove('ARTIFACT')
        self.assertEqual(self.host.record('alice',req)['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        receipt=self.host.read_receipt('bob','task-2','attempt-1',req['event_id']);self.assertIn('ARTIFACT',receipt['missing'])

if __name__=='__main__':unittest.main()
