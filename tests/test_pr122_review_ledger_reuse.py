"""Original encrypted ledger integration; synthetic identities, never production."""
import unittest
from scripts.pr122_customer_core import Center,Denied,Conflict
from scripts.pr122_customer_changes import Changes
from tests.test_pr122_customer_center import CustomerTests as Fixture
from tests.pr122_customer_change_fixture import seed,PAGE_SHA

class ReviewLedgerReuseTests(unittest.TestCase):
    imported=Fixture.imported
    def setUp(self):
        Fixture.setUp(self);seed(self);self.service=Changes(self.c)
    def submit(self,text='真实隔离意见',page='/project/consumer/',version=PAGE_SHA,key='review-logical-key-0001'):
        return self.service.submit(self.owner,'project-a',page,version,text,'RECTIFICATION',key)
    def test_retry_returns_original_receipt_and_single_row(self):
        a=self.submit();b=self.submit();self.assertEqual(a['event_id'],b['event_id'])
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM change_events WHERE kind='REQUEST'").fetchone()[0],1)
        with self.assertRaises(Conflict):self.submit(text='改变文本却复用同一键')
    def test_restart_recovers_actual_encrypted_history(self):
        saved=self.submit();self.c.db.close()
        self.c=Center(self.root,{'v1':self.key},'v1',clock=lambda:self.now,mail_ready=True,scanner=lambda raw:True)
        self.service=Changes(self.c)
        rows=self.service.list(self.owner,'project-a')['cases']
        self.assertEqual(rows[0]['id'],saved['id']);self.assertEqual(rows[0]['events'][0]['payload']['request'],'真实隔离意见')
    def test_authority_and_exact_asset_version_required(self):
        with self.assertRaises(Denied):self.submit(version='b'*64)
        with self.assertRaises(Denied):self.submit(page='/unregistered/page/')
        with self.assertRaises(Denied):self.service.submit(self.other,'project-a','/project/consumer/',PAGE_SHA,'越权','RECTIFICATION','review-logical-key-0002')
    def test_revocation_preserves_history_but_rejects_current_access(self):
        self.submit();self.imported(2,[])
        with self.assertRaises(Denied):self.service.list(self.owner,'project-a')
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM change_events WHERE kind='REQUEST'").fetchone()[0],1)

if __name__=='__main__':unittest.main()
