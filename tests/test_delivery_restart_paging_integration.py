import unittest
from five_support import load_dependencies, CanonicalFixture


class DeliveryRestartPagingTests(unittest.TestCase):
    def setUp(self):
        self.page=load_dependencies()['notification_delivery_view'].delivery_page
        self.f=CanonicalFixture(self);self.f.task('A');self.f.event('A')
    def view(self,db,**kwargs):
        return self.page(db,100,dict(generation=1,epoch=2),read_authority=lambda:dict(generation=self.f.binding['generation'],epoch=self.f.binding['epoch']),**kwargs)
    def test_wal_pages_remain_one_snapshot_during_new_events(self):
        db=self.f.reader(self);first=self.view(db,limit=1)
        self.f.task('B');self.f.event('B')
        second=self.view(db,limit=1,after=first['next_cursor'])
        self.assertFalse(second['has_more'])
        self.assertEqual([x['task_id'] for x in first['items']+second['items']],['A','A'])
        fresh=self.f.reader(self);self.assertEqual(len(self.view(fresh)['items']),4)
    def test_new_read_after_close_observes_fence_change(self):
        db=self.f.reader(self);self.assertTrue(all(x['status']=='OBSERVED' for x in self.view(db)['items']))
        db.close();self.f.db.execute("UPDATE tasks SET fence=5 WHERE id='A'")
        fresh=self.f.reader(self);self.assertTrue(all(x['status']=='HOLD' for x in self.view(fresh)['items']))
    def test_restart_does_not_erase_uncertain_send_state(self):
        self.f.db.execute("UPDATE supervision_delivery SET state='SENDING',send_attempts=1")
        self.f.reopen_producer();db=self.f.reader(self)
        rows=self.view(db)['items']
        self.assertTrue(all(not x['external_delivery_verified'] for x in rows))
        self.assertEqual(self.f.db.execute('SELECT COUNT(*) FROM supervision_delivery WHERE send_attempts=1').fetchone()[0],2)
    def test_reopening_does_not_invent_ack(self):
        self.f.reopen_producer();rows=self.view(self.f.reader(self))['items']
        self.assertTrue(all(not x['external_delivery_verified'] for x in rows))
        self.assertEqual(self.f.db.execute('SELECT COUNT(*) FROM supervision_delivery WHERE receipt_id IS NOT NULL').fetchone()[0],0)
    def test_activation_changes_between_pages_abort(self):
        db=self.f.reader(self);first=self.view(db,limit=1)
        self.f.binding['generation']=2
        with self.assertRaisesRegex(ValueError,'ACTIVATION_CHANGED'):self.view(db,limit=1,after=first['next_cursor'])
    def test_no_event_payload_leak_after_restart(self):
        self.f.reopen_producer();self.assertNotIn('NEVER_EXPORTED',repr(self.view(self.f.reader(self))))
