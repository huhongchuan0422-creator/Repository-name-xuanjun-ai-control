"""Host-declared mode; fixtures never send through a real service."""
import asyncio
from test_handoff_alert_original_delivery import OriginalAlertDelivery
from task_center_owner_message_tool import make_owner_message_adapter

class OwnerMode(OriginalAlertDelivery):
    def wrapped(self,calls):
        async def actual(**kwargs):
            await asyncio.sleep(0);calls.append(kwargs)
            return {'ok':True,'channel':'feishu','action':'send','messageId':'fixture-id','messageDelivery':{'status':'settled'}}
        def wrapper(**kwargs):return actual(**kwargs)
        return wrapper
    def adapter(self,tool,mode):
        return make_owner_message_adapter('user:fixture-owner',lambda *x:True,lambda *x:'user:fixture-owner',tool,message_mode=mode)
    def run_loop(self,coro):
        loop=asyncio.new_event_loop()
        try:return loop.run_until_complete(coro)
        finally:loop.close()
    def test_wrapped_async_explicit_mode_rejects_sync_then_awaits_once(self):
        calls=[];adapter=self.adapter(self.wrapped(calls),'async')
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,adapter)['state'],'ASYNC_HOST_REQUIRED')
        self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)
        self.assertEqual(calls,[])
        self.assertEqual(self.run_loop(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))['state'],'SENT_ACK_UNKNOWN')
        self.assertEqual(self.run_loop(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))['state'],'SENT_ACK_UNKNOWN')
        self.assertEqual(len(calls),1)
    def test_explicit_sync_legacy_and_unknown_mode(self):
        calls=[]
        def sync(**kwargs):
            calls.append(kwargs);return {'ok':True,'channel':'feishu','action':'send','messageId':'fixture-id','messageDelivery':{'status':'settled'}}
        for mode in (None,'auto','other',True):
            with self.assertRaisesRegex(ValueError,'HOST_MESSAGE_MODE_REQUIRED'):self.adapter(sync,mode)
        self.assertEqual(calls,[]);self.assertEqual(self.s.db.execute('SELECT attempts FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0],0)
        self.assertEqual(self.g.deliver_handoff_alert(self.context,self.oid,self.adapter(sync,'sync'))['state'],'SENT_ACK_UNKNOWN');self.assertEqual(len(calls),1)
    def test_cancel_wrapped_async_and_duplicate_no_resend(self):
        calls=[]
        async def actual(**kwargs):calls.append(1);await asyncio.sleep(99)
        def wrapper(**kwargs):return actual(**kwargs)
        adapter=self.adapter(wrapper,'async')
        async def run():
            task=asyncio.ensure_future(self.g.deliver_handoff_alert_async(self.context,self.oid,adapter))
            await asyncio.sleep(0);task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            return await self.g.deliver_handoff_alert_async(self.context,self.oid,adapter)
        self.assertEqual(self.run_loop(run())['state'],'UNKNOWN_NO_RETRY');self.assertEqual(calls,[1])
