"""Synthetic-only worker drain seam: after a crash between the registration
transaction and the inline delivery, the original bound channel (deliver_outbox/
MailDelivery) must drain the PENDING outbox row; the legacy SMTP drain must not
be used for those rows. No network, no production binding, no outbound mail.
"""
import json,os,sqlite3,tempfile,unittest
from unittest.mock import patch
from scripts.pr122_customer_core import Center
from scripts.pr122_customer_providers import Providers,drain_mail
from scripts.community_mail_delivery import install,drain_outbox,ProviderBinding
_original_connect=sqlite3.connect
sqlite3.connect=lambda path,*a,**k:_original_connect(os.fspath(path),*a,**k)
KEY={'testkey':b'k'*32}
class Transport:
    idempotent_submission=True
    def __init__(self):self.calls=[]
    def authenticated(self,b):return True
    def submit(self,b,message,aid,key):
        self.calls.append((aid,key))
        return {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'synthetic-'+aid}
class WorkerDrain(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=1800000000
        self.c=Center(self.tmp.name,KEY,'testkey',clock=lambda:self.now)
        self.addCleanup(self.c.db.close)
        self.transport=Transport()
        self.delivery=install(self.c,[ProviderBinding('Resend','synthetic','HTTP','https://api.resend.com',{'daily':100,'monthly':3000},True)],{'Resend':self.transport})
    def crash_simulated_pending_row(self,address='drain@example.invalid'):
        # Registration commits the VERIFY outbox row, then the process dies before
        # the inline deliver_outbox call: the row stays PENDING on disk.
        with patch.object(self.c,'deliver_outbox',lambda oid:None):
            self.assertEqual(self.c.register(address,'SyntheticPassword123!')['status'],'CHECK_VERIFICATION_CHANNEL')
        return self.c.db.execute("SELECT * FROM outbox WHERE kind='VERIFY' ORDER BY at DESC,rowid DESC LIMIT 1").fetchone()
    def row_state(self,oid):return self.c.db.execute('SELECT status FROM outbox WHERE id=?',(oid,)).fetchone()['status']
    def test_legacy_smtp_drain_strands_bound_channel_row_without_send(self):
        # Reproduction of the wiring defect this delta fixes: with no SMTP config
        # the legacy drain claims the PENDING row to UNKNOWN without any provider
        # IO, so the bound Resend transport is never used and the mail is stranded.
        row=self.crash_simulated_pending_row()
        result=drain_mail(self.c,Providers({}),'https://synthetic.invalid')
        self.assertEqual(result,{'status':'UNKNOWN'})
        self.assertEqual(self.transport.calls,[])
        self.assertEqual(self.row_state(row['id']),'UNKNOWN')
    def test_worker_drain_delivers_pending_row_via_bound_channel(self):
        row=self.crash_simulated_pending_row()
        result=drain_outbox(self.c)
        self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(result['outbox_id'],row['id'])
        self.assertEqual(self.transport.calls.__len__(),1)
        self.assertEqual(self.row_state(row['id']),'ACCEPTED')
    def test_double_drain_is_idempotent_without_second_send(self):
        row=self.crash_simulated_pending_row()
        first=drain_outbox(self.c)
        self.assertEqual(first['state'],'ACCEPTED')
        # Re-entering the original entry for the same row must not repeat provider IO,
        # and a drained row is no longer PENDING for the next worker tick.
        replay=self.c.deliver_outbox(row['id'])
        self.assertEqual(replay['state'],'ACCEPTED')
        self.assertEqual(self.transport.calls.__len__(),1)
        self.assertEqual(drain_outbox(self.c),{'pending':False})
    def test_unbound_channel_keeps_row_pending_for_retry(self):
        # Same state the ops worker branch reaches when the channel config is not
        # yet usable: no send, no UNKNOWN claim, the row is retried next tick.
        row=self.crash_simulated_pending_row()
        with patch.object(self.delivery,'bindings',[]):
            result=drain_outbox(self.c)
        self.assertEqual(result['state'],'UNAVAILABLE')
        self.assertEqual(self.transport.calls,[])
        self.assertEqual(self.row_state(row['id']),'PENDING')
    def test_empty_outbox_reports_no_pending(self):
        self.assertEqual(drain_outbox(self.c),{'pending':False})
        self.assertEqual(self.transport.calls,[])
if __name__=='__main__':unittest.main()
