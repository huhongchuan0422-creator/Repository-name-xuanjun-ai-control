"""Synthetic local host tool: no actual message, recipient or provider."""
import json, os, tempfile, unittest
from test_handoff_host_delta import HostDelta, CONFIG
from task_center_handoff_host import HandoffHost
from task_center_role_contract import RoleContractResolver
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from reusable_scheduler_cli import demo_graph

class FixtureTransport:
    def __init__(self,state='SENT'):self.state=state;self.calls=0;self.expected=None
    def resolve_destination(self,packet):
        if packet['task_id']!='demo-b':return None
        self.expected=packet['outbox_id'];return 'synthetic-existing-destination'
    def send(self,destination,packet):
        self.calls+=1
        if self.state=='THROW':raise RuntimeError('synthetic unknown effect')
        return {'platform_state':self.state,'message_id':'synthetic-platform-receipt','key':packet['outbox_id']}
    def interpret_result(self,destination,packet,raw):
        if raw.get('key')!=self.expected or raw.get('message_id')!='synthetic-platform-receipt':return None
        return {'state':raw['platform_state'],'receipt_ref':'synthetic-platform-receipt'}

class OriginalAlertDelivery(HostDelta):
    def setUp(self):
        super().setUp();self.tmp2=tempfile.TemporaryDirectory();self.s=Supervisor(os.path.join(self.tmp2.name,'supervisor.sqlite'),clock=lambda:1000)
        self.authority=TestTenantAuthority(b'0'*32);self.context=self.authority.issue('tenant-1','seed');self.g=GatewayKernel(self.s,self.authority)
        self.g.register_graph(self.context,demo_graph('tenant-1'))
        caller={'caller_id':'caller','run_id':'run','session_id':'session','gateway_id':'gateway'}
        self.s.claim_writer('demo-b','attempt-1','owner','entry',caller,'lease','provider',['fake:demo-b'],2000)
        self.s.db.execute('CREATE TABLE model_assignments(tenant_id TEXT,task_id TEXT,attempt_id TEXT,role_id TEXT,role_version TEXT,principal_id TEXT,provider_id TEXT,model_id TEXT,state TEXT)')
        self.s.db.execute("INSERT INTO model_assignments VALUES('tenant-1','demo-b','attempt-1','role-agent','v1','agent','fixture-only','fixture-model','ASSIGNED')")
        self.s.db.execute('CREATE TABLE role_templates(tenant_id TEXT,role_id TEXT,version TEXT,capabilities_json TEXT,enabled INTEGER)')
        self.s.db.execute('INSERT INTO role_templates VALUES(?,?,?,?,?)',('tenant-1','role-agent','v1',json.dumps(['code']),1));self.s.db.commit()
        policy=dict(self.policy,task_id='demo-b',task_spec_sha256=self.s.db.execute("SELECT spec_sha256 FROM tasks WHERE task_id='demo-b'").fetchone()[0])
        host=HandoffHost(self.s.db,'tenant-1','formal-fixture',self.auth,clock=lambda:1000,mcp_config=CONFIG,role_contract=RoleContractResolver(self.s.db,[policy]))
        req=self.req();req.update(host.issue_reference('alice','demo-b','attempt-1',1));req['task_id']='demo-b'
        self.auth.backup={'state':'INCOMPLETE','missing':['RESTORE'],'cycle_at':990}
        self.assertEqual(host.record('alice',req)['alert_delivery'],'UNKNOWN')
        self.oid=self.s.db.execute("SELECT outbox_id FROM outbox WHERE task_id='demo-b'").fetchone()[0]
    def tearDown(self):self.s.close();self.tmp2.cleanup();super().tearDown()
    def test_original_alert_sent_once_with_platform_receipt_not_ack(self):
        with self.assertRaisesRegex(ValueError,'HANDOFF_ALERT_REQUIRES_TRUSTED_TRANSPORT_RECEIPT'):
            self.g.mark_outbox_sent(self.context,self.oid,'caller-claimed-receipt')
        a=FixtureTransport();result=self.g.deliver_handoff_alert(self.context,self.oid,a)
        self.assertEqual(result['state'],'SENT_ACK_UNKNOWN');self.assertTrue(result['dispatch_performed'])
        self.assertEqual(self.s.db.execute('SELECT phase,evidence_ref FROM gateway_delivery_receipts').fetchone()[:],('SENT','synthetic-platform-receipt'))
        self.assertEqual(self.s.db.execute('SELECT delivered_at FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],1000)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN');self.assertEqual(a.calls,1)
        with self.assertRaises(ValueError):self.g.mark_outbox_sent(self.context,self.oid,'caller-claimed-receipt')
    def test_unknown_effects_are_never_automatically_replayed(self):
        a=FixtureTransport('THROW');self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY');self.assertEqual(a.calls,1)
        self.assertIsNone(self.s.db.execute('SELECT delivered_at FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0])
        self.assertFalse(any(x['outbox_id']==self.oid for x in self.s.due_outbox(now=9999)))
        with self.assertRaises(ValueError):self.s.outbox_result(self.oid,True)
    def test_unavailable_or_denied_destination_never_consumes_outbox(self):
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid)['state'],'HOST_TRANSPORT_UNAVAILABLE')
        a=FixtureTransport();a.resolve_destination=lambda packet:None
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'DESTINATION_UNAVAILABLE')
        self.assertEqual(a.calls,0);self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)
        with self.assertRaises(ValueError):self.g.deliver_handoff_alert(self.authority.issue('other','seed'),self.oid,a)
    def test_definitive_failure_is_distinct_and_never_fabricates_sent(self):
        a=FixtureTransport('FAILED');self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'FAILED_NO_RETRY')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_delivery_receipts').fetchone()[0],0)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'FAILED_NO_RETRY');self.assertEqual(a.calls,1)
    def test_crash_after_durable_intent_does_not_resend(self):
        a=FixtureTransport()
        def crash(destination,packet):
            a.calls+=1
            raise KeyboardInterrupt('synthetic process interruption')
        a.send=crash
        with self.assertRaises(KeyboardInterrupt):self.g.deliver_handoff_alert(self.context,self.oid,a)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(a.calls,1)
        self.assertFalse(any(x['outbox_id']==self.oid for x in self.s.due_outbox(now=9999)))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_delivery_receipts').fetchone()[0],0)
