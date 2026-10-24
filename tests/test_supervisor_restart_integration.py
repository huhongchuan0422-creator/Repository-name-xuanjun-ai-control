import unittest
from five_support import load_dependencies, CanonicalFixture


class SupervisorRestartTests(unittest.TestCase):
    def setUp(self):
        self.inventory=load_dependencies()['task_supervisor_runtime'].canonical_inventory_page
        self.f=CanonicalFixture(self)
    def scan(self,db,now=100,limit=2):
        rows=[];cursor=None
        while True:
            value=self.inventory(db,now,cursor,limit)
            self.assertFalse(value['dispatch_performed'])
            rows.extend(value['tasks'])
            if value['complete']:return rows
            cursor=value['next_cursor']
    def test_all_unsupervised_tasks_survive_real_db_reopen(self):
        for n in range(11):self.f.task('T%02d'%n)
        before=self.scan(self.f.reader(self));self.f.reopen_producer()
        after=self.scan(self.f.reader(self))
        self.assertEqual([r['id'] for r in before],[r['id'] for r in after])
        self.assertEqual(len(after),11)
        self.assertTrue(all('SUPERVISION_RECORD_MISSING' in r['attention'] for r in after))
        self.assertEqual([r['decision_key'] for r in before],[r['decision_key'] for r in after])
    def test_actual_dispatch_record_remains_after_reopen(self):
        self.f.task('T1','RUNNING')
        self.f.producer.dispatch('T1','a'*64,'DOTS','fixture-run','fixture-session','/fixture','b'*64,110,120,130,{},'fixture-budget')
        self.f.reopen_producer();rows=self.scan(self.f.reader(self),now=300)
        self.assertNotIn('SUPERVISION_RECORD_MISSING',rows[0]['attention'])
        self.assertIn('PROGRESS_DEADLINE_EXCEEDED',rows[0]['attention'])
        self.assertEqual(rows[0]['execution_authority'],'NOT_GRANTED')
    def test_wal_pagination_does_not_omit_existing_tasks(self):
        for n in ('A','C','E'):self.f.task(n)
        db=self.f.reader(self);first=self.inventory(db,100,None,1)
        self.f.task('B')
        tail=[];cursor=first['next_cursor']
        while cursor is not None:
            value=self.inventory(db,100,cursor,1);tail.extend(value['tasks']);cursor=value['next_cursor']
        self.assertEqual([r['id'] for r in first['tasks']+tail],['A','C','E'])
        self.assertEqual([r['id'] for r in self.scan(self.f.reader(self))],['A','B','C','E'])
    def test_pending_delivery_durable_without_false_ack(self):
        self.f.task('T1');self.f.event('T1');self.f.reopen_producer()
        row=self.scan(self.f.reader(self))[0]
        self.assertEqual(len(row['deliveries']),2)
        self.assertTrue(all(x['state']=='PENDING' for x in row['deliveries']))
        self.assertEqual(row['execution_authority'],'NOT_GRANTED')
    def test_real_outbox_stale_fence_visible(self):
        self.f.task('T1');self.f.event('T1')
        self.f.db.execute('UPDATE tasks SET fence=5');self.f.reopen_producer()
        row=self.scan(self.f.reader(self))[0]
        self.assertIn('STALE_DELIVERY_RECONCILE_ONLY',row['attention'])
    def test_scans_leave_real_schema_and_rows_unchanged(self):
        self.f.task('T1');self.f.event('T1')
        before='\n'.join(self.f.db.iterdump());self.scan(self.f.reader(self))
        self.assertEqual(before,'\n'.join(self.f.db.iterdump()))
