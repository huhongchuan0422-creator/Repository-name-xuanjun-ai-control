"""Reconcile only trusted platform fixture proof, never send real messages."""
from test_handoff_alert_original_delivery import OriginalAlertDelivery, FixtureTransport

class PlatformFixture(FixtureTransport):
    def __init__(self,state='THROW',proof='NOT_SENT'):
        super().__init__(state);self.proof=proof;self.lookups=0
    def reconcile(self,packet):
        self.lookups+=1
        if packet['task_id']!='demo-b' or packet['delivery_attempt']<1:raise ValueError('wrong binding')
        if self.proof=='UNKNOWN':return None
        return {'state':self.proof,'receipt_ref':'synthetic-verified-platform-record','dispatch_settled':True}

class Reconciliation(OriginalAlertDelivery):
    def test_intent_crash_confirm_not_sent_then_retry_once(self):
        a=PlatformFixture();a.send=lambda destination,packet:(_ for _ in ()).throw(KeyboardInterrupt('before send'))
        with self.assertRaises(KeyboardInterrupt):self.g.deliver_handoff_alert(self.context,self.oid,a)
        self.assertFalse(any(x['outbox_id']==self.oid for x in self.s.due_outbox(now=9999)))
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'RETRY_READY')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'RETRY_READY');self.assertEqual(a.lookups,1)
        self.assertEqual([x['outbox_id'] for x in self.g.due_handoff_alerts(self.context,now=1000,host_adapter=PlatformFixture())],[self.oid])
        a.state='SENT';a.send=FixtureTransport.send.__get__(a,PlatformFixture)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN');self.assertEqual(a.calls,1)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM events WHERE kind='HANDOFF_ALERT_INTENT'").fetchone()[0],2)
    def test_unknown_but_sent_reconciles_without_resend(self):
        a=PlatformFixture(proof='SENT')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN')
        self.assertEqual(a.calls,1);self.assertEqual(a.lookups,1)
        self.assertEqual(self.s.db.execute('SELECT phase,evidence_ref FROM gateway_delivery_receipts').fetchone()[:],('SENT','synthetic-verified-platform-record'))
    def test_definitive_failed_then_confirmed_not_sent(self):
        a=PlatformFixture(state='FAILED');self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'FAILED_NO_RETRY')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'RETRY_READY')
        a.state='SENT';self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'SENT_ACK_UNKNOWN');self.assertEqual(a.calls,2)
    def test_unknown_and_wrong_tenant_remain_no_retry(self):
        a=PlatformFixture(proof='UNKNOWN');self.g.deliver_handoff_alert(self.context,self.oid,a)
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY');self.assertEqual(a.calls,1)
        with self.assertRaises(ValueError):self.g.reconcile_handoff_alert(self.authority.issue('other','seed'),self.oid,a)
        self.assertFalse(self.g.due_handoff_alerts(self.context,now=9999,host_adapter=PlatformFixture()))
    def test_unattempted_not_visible_to_generic_consumer(self):
        self.assertFalse(any(x['outbox_id']==self.oid for x in self.s.due_outbox(now=9999)))
        self.assertEqual([x['outbox_id'] for x in self.g.due_handoff_alerts(self.context,now=1000,host_adapter=PlatformFixture())],[self.oid])
    def test_unsettled_and_wrong_task_never_authorize_retry(self):
        a=PlatformFixture();self.g.deliver_handoff_alert(self.context,self.oid,a)
        a.reconcile=lambda packet:{'state':'NOT_SENT','receipt_ref':'fixture-proof','dispatch_settled':False}
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,a)['state'],'UNKNOWN_NO_RETRY')
        # Another task in the same tenant needs its own binding; the restricted
        # host resolver cannot use demo-b's authorized destination for demo-c.
        import json
        from task_supervisor import canonical
        row=self.s.db.execute('SELECT payload_json FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()
        payload=json.loads(row['payload_json']);payload.update(task_id='demo-c',attempt_id='attempt-c')
        self.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('demo-c','attempt-c','other-alert','SUPERVISION_ACTION',1000,'PHASE_EXECUTION','HANDOFF_CONTEXT_INCOMPLETE',canonical(payload)))
        self.s._enqueue('demo-c','attempt-c','other-alert',payload,1000);self.s.db.commit()
        other=self.s.db.execute("SELECT outbox_id FROM outbox WHERE event_id='other-alert'").fetchone()[0]
        restricted=PlatformFixture(state='SENT')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,other,restricted)['state'],'DESTINATION_UNAVAILABLE')
        self.assertEqual(restricted.calls,0)
