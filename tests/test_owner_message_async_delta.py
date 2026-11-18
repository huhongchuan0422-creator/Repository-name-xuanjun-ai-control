"""Isolated async host bridge; never sends to a real service."""
import asyncio
from test_handoff_alert_original_delivery import OriginalAlertDelivery
from task_center_owner_message_tool import make_owner_message_adapter,parse_message_result

class AsyncMessageDelta(OriginalAlertDelivery):
    def build(self,tool):
        return make_owner_message_adapter('user:fixture-owner',lambda t,k,a:(t,k,a)==('tenant-1','demo-b','attempt-1'),lambda *args:'user:fixture-owner',tool)
    def run_loop(self,coro):
        loop=asyncio.new_event_loop()
        try:return loop.run_until_complete(coro)
        finally:loop.close()
    def test_async_awaits_same_call_and_sync_rejects_before_intent(self):
        calls=[]
        async def tool(**kwargs):
            await asyncio.sleep(0);calls.append(kwargs)
            return {'ok':True,'channel':'feishu','action':'send','messageId':'m1','chatId':'fixture-owner','messageDelivery':{'status':'settled','deliveredTargets':['fixture-owner']}}
        adapter=self.build(tool)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'ASYNC_HOST_REQUIRED')
        self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)
        result=self.run_loop(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))
        self.assertEqual(result['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)
        self.assertEqual(self.s.db.execute('SELECT evidence_ref FROM gateway_delivery_receipts').fetchone()[0],'m1')
        self.assertEqual(self.run_loop(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)
    def test_async_exception_is_unknown_no_retry(self):
        calls=[]
        async def tool(**kwargs):calls.append(1);await asyncio.sleep(0);raise RuntimeError('unknown')
        adapter=self.build(tool)
        self.assertEqual(self.run_loop(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.run_loop(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))['state'],'UNKNOWN_NO_RETRY');self.assertEqual(len(calls),1)
    def test_cancel_after_intent_never_resends(self):
        calls=[]
        async def tool(**kwargs):calls.append(1);await asyncio.sleep(99)
        adapter=self.build(tool)
        async def run():
            task=asyncio.ensure_future(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))
            await asyncio.sleep(0);task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            return await self.g.deliver_handoff_alert_async(self.context,self.oid,adapter)
        self.assertEqual(self.run_loop(run())['state'],'UNKNOWN_NO_RETRY');self.assertEqual(len(calls),1)
        self.assertIsNone(self.s.db.execute('SELECT delivered_at FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0])
    def test_wrong_explicit_target_refuses_sent_and_absent_is_not_invented(self):
        base={'ok':True,'channel':'feishu','action':'send','messageId':'m1','messageDelivery':{'status':'settled'}}
        self.assertEqual(parse_message_result(base,'user:fixture-owner')['state'],'SENT')
        for bad in (dict(base,chatId='other'),dict(base,messageDelivery={'status':'settled','deliveredTargets':['other']}),dict(base,messageDelivery={'status':'settled','deliveredTargets':[]})):
            self.assertIsNone(parse_message_result(bad,'user:fixture-owner'))
        def tool(**kwargs):return dict(base,chatId='other')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.build(tool))['state'],'UNKNOWN_NO_RETRY')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_delivery_receipts').fetchone()[0],0)
    def test_sync_compat_and_unsupported_callable_preflight(self):
        calls=[]
        class Unsupported:
            def __call__(self,**kwargs):calls.append(kwargs);return None
        bad=self.build(Unsupported())
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,bad)['state'],'ASYNC_HOST_REQUIRED')
        self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)
        def sync(**kwargs):calls.append(kwargs);return {'ok':True,'channel':'feishu','action':'send','messageId':'m1','messageDelivery':{'status':'settled'}}
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.build(sync))['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)
    def test_concurrent_async_duplicate_never_sends_twice(self):
        calls=[]
        async def tool(**kwargs):
            calls.append(1);await asyncio.sleep(0.01)
            return {'ok':True,'channel':'feishu','action':'send','messageId':'m1','messageDelivery':{'status':'settled'}}
        adapter=self.build(tool)
        async def run():
            first=asyncio.ensure_future(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))
            await asyncio.sleep(0)
            second=await self.g.deliver_handoff_alert_async(self.context,self.oid,adapter)
            return await first,second
        first,second=self.run_loop(run())
        self.assertEqual(first['state'],'SENT_ACK_UNKNOWN');self.assertEqual(second['state'],'UNKNOWN_NO_RETRY');self.assertEqual(calls,[1])
