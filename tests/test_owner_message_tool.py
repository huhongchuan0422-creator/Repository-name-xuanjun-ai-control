"""Host-injected simulated tool: no outbound message or live identity."""
from test_handoff_alert_original_delivery import OriginalAlertDelivery
from task_center_owner_message_tool import make_owner_message_adapter,parse_message_result

class OwnerMessageTool(OriginalAlertDelivery):
    def adapter(self,result):
        calls=[]
        def tool(**kwargs):calls.append(kwargs);return result
        def authorized(tenant,task,attempt):return (tenant,task,attempt)==('tenant-1','demo-b','attempt-1')
        def binding(tenant,task,attempt):return 'user:fixture-owner'
        return make_owner_message_adapter('user:fixture-owner',authorized,binding,tool,message_mode='sync'),calls

    def test_actual_observed_send_shape_settled_and_receipt(self):
        raw={'ok':True,'channel':'feishu','action':'send','messageId':'fixture-platform-id',
             'receipt':{'primaryPlatformMessageId':'fixture-platform-id','sentAt':'fixture-time'},
             'messageDelivery':{'status':'settled'},'sourceReplyDelivered':True}
        adapter,calls=self.adapter(raw)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'SENT_ACK_UNKNOWN')
        self.assertEqual(len(calls),1);self.assertEqual(set(calls[0]),{'action','target','message'})
        self.assertEqual(calls[0]['action'],'send');self.assertEqual(calls[0]['target'],'user:fixture-owner')
        self.assertEqual(self.s.db.execute('SELECT phase,evidence_ref FROM gateway_delivery_receipts').fetchone()[:],('SENT','fixture-platform-id'))
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)

    def test_ok_sent_at_without_settled_is_unknown_no_blind_repeat(self):
        raw={'ok':True,'channel':'feishu','action':'send','messageId':'fixture-platform-id',
             'receipt':{'primaryPlatformMessageId':'fixture-platform-id','sentAt':'fixture-time'}}
        adapter,calls=self.adapter(raw)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.reconcile_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(len(calls),1);self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_delivery_receipts').fetchone()[0],0)

    def test_parser_requires_terminal_target_receipt_and_matching_ids(self):
        base={'ok':True,'channel':'feishu','action':'send','messageId':'id-1','receipt':{'primaryPlatformMessageId':'id-1'},'messageDelivery':{'status':'settled'}}
        self.assertEqual(parse_message_result(base),{'state':'SENT','settled':True,'message_id':'id-1'})
        for bad in (dict(base,ok=False),dict(base,channel='other'),dict(base,action='other'),dict(base,messageId='id-2'),dict(base,messageDelivery={}),dict(base,messageId=None,receipt={}),dict(base,messageDelivery=None,sourceReplyDelivered=True)):
            self.assertIsNone(parse_message_result(bad))
        receipt_only=dict(base);receipt_only.pop('messageId')
        self.assertEqual(parse_message_result(receipt_only)['message_id'],'id-1')

    def test_confirmed_destination_never_grants_task_authority(self):
        calls=[]
        adapter=make_owner_message_adapter('user:fixture-owner',lambda *args:False,lambda *args:'user:fixture-owner',lambda **kwargs:calls.append(kwargs),message_mode='sync')
        self.assertEqual(self.g.due_handoff_alerts(self.context,now=1000,host_adapter=adapter),[])
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'DESTINATION_UNAVAILABLE')
        self.assertEqual(calls,[]);self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)
