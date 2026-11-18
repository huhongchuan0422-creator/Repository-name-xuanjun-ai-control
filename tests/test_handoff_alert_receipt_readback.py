"""Original outbox -> gateway settled receipt -> protected GET; all fixtures."""
import hashlib, http.client, json, os, threading
from test_handoff_alert_original_delivery import OriginalAlertDelivery, FixtureTransport
from test_handoff_host_delta import CONFIG
from task_center_handoff_host import HandoffHost, FormalHandoffIdentityProvider, REQUIRED_CONTEXT
from task_center_role_contract import RoleContractResolver
from task_center_handoff_ledger import HandoffLedgerBridge
from task_center_owner_message_tool import make_owner_message_adapter
from task_center_app import make_server

class AlertReceiptReadback(OriginalAlertDelivery):
    def setUp(self):
        super().setUp()
        policy=dict(self.policy,task_id='demo-b',task_spec_sha256=self.s.db.execute("SELECT spec_sha256 FROM tasks WHERE task_id='demo-b'").fetchone()[0])
        self.read_host=HandoffHost(self.s.db,'tenant-1','formal-fixture',self.auth,clock=lambda:1000,mcp_config=CONFIG,role_contract=RoleContractResolver(self.s.db,[policy]))
        self.reference=json.loads(self.s.db.execute("SELECT payload_json FROM events WHERE task_id='demo-b' AND kind='HANDOFF_REFERENCE_ISSUED'").fetchone()[0])
    def request(self):
        ref={k:self.reference[k] for k in ('event_id','handoff_id','handoff_version','backup_cycle_id')}
        return dict(ref,task_id='demo-b',attempt_id='attempt-1',action='PROPOSE',causation='NONE',snapshot_digest='a'*64,backup_manifest_sha256='b'*64,checked=sorted(REQUIRED_CONTEXT),provider_ref='fixture-only')
    def adapter(self):
        def tool(**kwargs):return {'ok':True,'channel':'feishu','action':'send','messageId':'fixture-msg-1','chatId':'fixture-owner','receipt':{'primaryPlatformMessageId':'fixture-msg-1'},'messageDelivery':{'status':'settled','deliveredTargets':['fixture-owner']}}
        return make_owner_message_adapter('user:fixture-owner',lambda t,k,a:(t,k,a)==('tenant-1','demo-b','attempt-1'),lambda *args:'user:fixture-owner',tool,message_mode='sync')
    def read_http(self,session='good'):
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(this,token):return 'alice' if token=='good' else None
            def verify_csrf(this,session,token):return token=='csrf'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(this,session):return session=='alice'
        bridge=HandoffLedgerBridge(self.read_host,os.path.join(self.tmp2.name,'observer'),'test-ledger','writer')
        server=make_server(self.s.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,identity_provider=Identity(),session_store=Sessions(),outbound_enabled=False,handoff_host=self.read_host,ledger_bridge=bridge)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                c.request('GET','/api/admin/handoff-event?task_id=demo-b&attempt_id=attempt-1&event_id='+self.reference['event_id'],headers={'Host':'localhost:%s'%server.server_port,'Cookie':'session='+session})
                r=c.getresponse();return r.status,json.loads(r.read().decode())
            finally:c.close()
        finally:server.shutdown();thread.join(3);server.server_close()
    def snapshot(self):return hashlib.sha256('\n'.join(self.s.db.iterdump()).encode()).hexdigest()
    def test_settled_original_send_then_new_alert_history_and_read_only(self):
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.adapter())['state'],'SENT_ACK_UNKNOWN')
        self.auth.backup={'state':'INCOMPLETE','missing':['INSTALL_ENTRY'],'cycle_at':990}
        self.assertEqual(self.read_host.record('alice',self.request())['alert_delivery'],'UNKNOWN')
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200)
        self.assertEqual(body['alert_delivery'],'UNKNOWN')
        self.assertEqual([r['alert_delivery'] for r in body['history']],['SENT_ACK_UNKNOWN','UNKNOWN'])
        self.assertNotIn('fixture-msg-1',json.dumps(body));self.assertEqual(before,self.snapshot())
        self.auth.enabled=False;self.assertEqual(self.read_http()[0],404);self.auth.enabled=True
        other=HandoffHost(self.s.db,'other-tenant','formal-fixture',self.auth,clock=lambda:1000,mcp_config=CONFIG)
        with self.assertRaises(ValueError):other.read_receipt('alice','demo-b','attempt-1',self.reference['event_id'])
        self.assertEqual(before,self.snapshot())
    def test_single_sent_without_settled_provenance_stays_unknown(self):
        a=FixtureTransport();self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN')
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN')
        self.assertEqual(before,self.snapshot());self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN');self.assertEqual(a.calls,1)
    def test_unknown_effect_not_replayed_and_wrong_receipt_is_unknown(self):
        a=FixtureTransport('THROW');self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN')
        self.assertEqual(before,self.snapshot());self.assertEqual(a.calls,1)
    def test_current_settled_receipt_reads_sent_without_platform_id(self):
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.adapter())['state'],'SENT_ACK_UNKNOWN')
        before=self.snapshot();status,body=self.read_http()
        self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'SENT_ACK_UNKNOWN')
        self.assertEqual(body['history'][0]['alert_delivery'],'SENT_ACK_UNKNOWN')
        self.assertNotIn('fixture-msg-1',json.dumps(body));self.assertEqual(before,self.snapshot())
    def test_reconciled_settled_platform_proof_is_bound_to_exact_attempt(self):
        class ReconcileTransport(FixtureTransport):
            def __init__(this):super().__init__('THROW')
            def resolve_destination(this,packet):return 'user:fixture-owner'
            def reconcile(this,packet):
                return {'state':'SENT','receipt_ref':'fixture-msg-1','dispatch_settled':True,
                        'platform_result':{'ok':True,'channel':'feishu','action':'send','messageId':'fixture-msg-1','chatId':'fixture-owner','messageDelivery':{'status':'settled','deliveredTargets':['fixture-owner']}}}
        a=ReconcileTransport()
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN')
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'SENT_ACK_UNKNOWN')
        self.assertEqual(a.calls,1);self.assertNotIn('fixture-msg-1',json.dumps(body));self.assertEqual(before,self.snapshot())
    def test_corrupt_receipt_and_missing_table_fail_closed_without_write(self):
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.adapter())['state'],'SENT_ACK_UNKNOWN')
        self.s.db.execute("UPDATE gateway_delivery_receipts SET evidence_ref='different-id'");self.s.db.commit()
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN');self.assertEqual(before,self.snapshot())
        self.s.db.execute('DROP TABLE gateway_delivery_receipts');self.s.db.commit()
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN');self.assertEqual(before,self.snapshot())
    def test_wrong_attempt_and_conflicting_proof_do_not_become_sent(self):
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.adapter())['state'],'SENT_ACK_UNKNOWN')
        key='handoff-alert-intent:'+self.oid
        row=self.s.db.execute('SELECT payload_json FROM events WHERE event_id=?',(key,)).fetchone()
        original=row[0];value=json.loads(original);value['delivery_attempt']=2
        self.s.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(value),key));self.s.db.commit()
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN');self.assertEqual(before,self.snapshot())
        self.s.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(original,key));self.s.db.commit()
        key='handoff-alert-result:'+self.oid;row=self.s.db.execute('SELECT payload_json FROM events WHERE event_id=?',(key,)).fetchone()
        value=json.loads(row[0]);value['platform_proof']['settled']=False
        self.s.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(value),key));self.s.db.commit()
        before=self.snapshot();status,body=self.read_http();self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN');self.assertEqual(before,self.snapshot())
    def test_conflicting_result_and_reconciliation_do_not_report_sent(self):
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.adapter())['state'],'SENT_ACK_UNKNOWN')
        key='handoff-alert-result:'+self.oid
        row=self.s.db.execute('SELECT * FROM events WHERE event_id=?',(key,)).fetchone()
        data=json.loads(row['payload_json']);data['state']='CONFLICTING_STATE'
        self.s.db.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(data),key))
        data['state']='SENT_ACK_UNKNOWN';data['delivery_attempt']=1
        self.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('demo-b','attempt-1','handoff-alert-reconcile:'+self.oid+':1','HANDOFF_ALERT_RECONCILED',row['observed_at'],'PHASE_EXECUTION',row['evidence_ref'],json.dumps(data)))
        self.s.db.commit();before=self.snapshot();status,body=self.read_http()
        self.assertEqual(status,200);self.assertEqual(body['alert_delivery'],'UNKNOWN');self.assertEqual(before,self.snapshot())
