"""Synthetic callables only: never invoke an actual message tool."""
from test_handoff_alert_original_delivery import OriginalAlertDelivery
from task_center_owner_alert_adapter import OwnerAlertAdapter

class OwnerAdapterTests(OriginalAlertDelivery):
    def adapter(self,scope=True,target='owner-direct',state='SENT',settled=True):
        calls=[]
        def authorized(tenant,task,attempt):return scope and (tenant,task,attempt)==('tenant-1','demo-b','attempt-1')
        def binding(tenant,task,attempt):return target
        def invoke(destination,text,key,attempt):
            calls.append((destination,text,key,attempt))
            return {'fixture_state':state,'fixture_settled':settled,'fixture_message_id':'platform-fixture-id'}
        def parse(raw):
            return {'state':raw['fixture_state'],'settled':raw['fixture_settled'],
                    'message_id':raw['fixture_message_id'],'receipt_ref':'fixture-failure-ref'}
        return OwnerAlertAdapter('owner-direct',authorized,binding,invoke,parse),calls

    def test_owner_authorized_original_alert_sent_with_settled_receipt(self):
        adapter,calls=self.adapter()
        self.assertEqual([x['outbox_id'] for x in self.g.due_handoff_alerts(self.context,now=1000,host_adapter=adapter)],[self.oid])
        result=self.g.deliver_handoff_alert(self.context,self.oid,adapter)
        self.assertEqual(result['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],'owner-direct');self.assertEqual(calls[0][2:],(self.oid,1))
        self.assertEqual(self.s.db.execute('SELECT phase,evidence_ref FROM gateway_delivery_receipts').fetchone()[:],('SENT','platform-fixture-id'))
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)

    def test_destination_does_not_grant_task_scope_or_other_recipient(self):
        for scope,target in ((False,'owner-direct'),(True,'different-recipient')):
            adapter,calls=self.adapter(scope=scope,target=target)
            self.assertEqual(self.g.due_handoff_alerts(self.context,now=1000,host_adapter=adapter),[])
            self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'DESTINATION_UNAVAILABLE')
            self.assertEqual(calls,[])
        self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)

    def test_unsettled_result_is_unknown_and_reconcile_unsupported(self):
        adapter,calls=self.adapter(settled=False)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(len(calls),1);self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_delivery_receipts').fetchone()[0],0)

    def test_missing_receipt_or_parser_failure_does_not_fabricate_sent(self):
        adapter,calls=self.adapter()
        adapter._parse=lambda raw:{'state':'SENT','settled':True,'message_id':''}
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_delivery_receipts').fetchone()[0],0)
