import sqlite3
import unittest
from scripts.notification_delivery_view import delivery_page


AUTH = {'generation': 1, 'epoch': 2}


class Tests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
        CREATE TABLE supervision_events(event_key TEXT PRIMARY KEY, task_id TEXT, details TEXT);
        CREATE TABLE supervision_delivery(event_key TEXT, destination TEXT, state TEXT,
          attempts INTEGER, next_attempt_at REAL, authority_fence INTEGER,
          authority_epoch INTEGER, receipt_id TEXT, send_attempts INTEGER,
          claim_until REAL, claim_token TEXT, last_error TEXT,
          PRIMARY KEY(event_key,destination));
        ''')

    def tearDown(self):
        self.db.close()

    def insert(self, index=1, destination='OWNER', state='PENDING', **changes):
        key = '%064x' % index
        self.db.execute('INSERT OR IGNORE INTO supervision_events VALUES(?,?,?)',
                        (key, 'TASK_' + str(index), 'PRIVATE_PAYLOAD'))
        row = dict(event_key=key, destination=destination, state=state, attempts=0,
                   next_attempt_at=100, authority_fence=1, authority_epoch=2,
                   receipt_id=None, send_attempts=0, claim_until=None,
                   claim_token='SECRET', last_error='SECRET')
        row.update(changes)
        self.db.execute('INSERT INTO supervision_delivery('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', list(row.values()))

    def begin(self):
        self.db.commit(); self.db.execute('BEGIN')

    def view(self, **kwargs):
        return delivery_page(self.db, 100, AUTH, **kwargs)

    def test_requires_transaction(self):
        with self.assertRaises(ValueError):self.view()

    def test_empty(self):
        self.begin();self.assertEqual(self.view()['items'], [])

    def test_readonly(self):
        self.insert();self.begin();before=self.db.total_changes
        tables=list(self.db.execute('SELECT name FROM sqlite_master ORDER BY name'))
        result=self.view()
        self.assertEqual(before,self.db.total_changes)
        self.assertEqual(tables,list(self.db.execute('SELECT name FROM sqlite_master ORDER BY name')))
        self.assertFalse(result['canonical_mutation']);self.assertFalse(result['send_performed'])

    def test_does_not_echo_private_columns(self):
        self.insert(receipt_id='SECRET');self.begin();out=repr(self.view())
        self.assertNotIn('SECRET',out);self.assertNotIn('PRIVATE_PAYLOAD',out)

    def test_composite_pagination(self):
        for i in range(1,106):
            for target in ('OWNER','GITHUB_PR17'):self.insert(i,target)
        self.begin();cursor=None;seen=[]
        while True:
            page=self.view(limit=17,after=cursor)
            seen.extend((r['event_key'],r['destination']) for r in page['items'])
            if not page['has_more']:break
            cursor=page['next_cursor']
        self.assertEqual(len(seen),210);self.assertEqual(len(set(seen)),210)
        self.assertEqual(seen,sorted(seen))

    def test_due_vs_waiting(self):
        self.insert(1,next_attempt_at=100);self.insert(2,next_attempt_at=101)
        self.begin();self.assertEqual([r['classification'] for r in self.view()['items']],['RETRY_DUE','WAITING_RETRY'])

    def test_unknown_retry_time(self):
        self.insert(next_attempt_at=None);self.begin()
        self.assertIn('UNKNOWN_RETRY_TIME',self.view()['items'][0]['warnings'])

    def test_ack_requires_receipt(self):
        self.insert(state='ACKED');self.begin();row=self.view()['items'][0]
        self.assertEqual(row['status'],'HOLD');self.assertEqual(row['classification'],'ACK_EVIDENCE_MISSING')

    def test_ack_is_not_verified_external_delivery(self):
        self.insert(state='ACKED',receipt_id='receipt');self.begin();row=self.view()['items'][0]
        self.assertEqual(row['classification'],'ACK_RECORDED')
        self.assertFalse(row['external_delivery_verified'])

    def test_sending_not_ack(self):
        self.insert(1,state='SENDING');self.insert(2,state='SENDING_UNCERTAIN');self.begin()
        self.assertTrue(all(r['classification']=='RECONCILIATION_REQUIRED' for r in self.view()['items']))

    def test_dead_letter_not_retried(self):
        self.insert(state='DEAD_LETTER',attempts=5);self.begin()
        row=self.view()['items'][0];self.assertEqual(row['classification'],'MANUAL_REVIEW_REQUIRED')
        self.assertEqual(self.db.execute('SELECT attempts FROM supervision_delivery').fetchone()[0],5)

    def test_expired_claim(self):
        self.insert(state='CLAIMED',claim_until=99);self.begin()
        self.assertEqual(self.view()['items'][0]['classification'],'CLAIM_EXPIRED')

    def test_active_claim(self):
        self.insert(state='CLAIMED',claim_until=101);self.begin()
        self.assertEqual(self.view()['items'][0]['classification'],'CLAIM_ACTIVE')

    def test_stale_epoch(self):
        self.insert(state='ACKED',receipt_id='r',authority_epoch=1);self.begin()
        self.assertIn('STALE_OR_UNKNOWN_AUTHORITY',self.view()['items'][0]['warnings'])

    def test_stale_generation(self):
        self.insert(authority_fence=3);self.begin()
        self.assertEqual(self.view()['items'][0]['status'],'HOLD')

    def test_orphan_delivery_visible(self):
        self.insert();self.db.execute('DELETE FROM supervision_events');self.begin()
        row=self.view()['items'][0];self.assertIsNone(row['task_id'])
        self.assertIn('MISSING_OR_INVALID_EVENT_TASK',row['warnings'])

    def test_unknown_state_or_counters(self):
        self.insert(state='SECRET',attempts=-1,send_attempts=None);self.begin()
        row=self.view()['items'][0];self.assertEqual(row['state'],'UNKNOWN')
        self.assertIsNone(row['attempts']);self.assertIsNone(row['send_attempts'])

    def test_missing_schema_no_creation(self):
        self.db.execute('DROP TABLE supervision_events');self.begin()
        with self.assertRaises(ValueError):self.view()

    def test_cursor_rejected(self):
        self.begin()
        for cursor in ([], ['bad','OWNER'], ['a'*64,"' OR 1=1 --"], True):
            with self.assertRaises(ValueError):self.view(after=cursor)

    def test_invalid_bounds(self):
        self.begin()
        for limit in (0,101,True):
            with self.assertRaises(ValueError):self.view(limit=limit)

    def test_unknown_authority(self):
        self.begin()
        for auth in ({},None,{'generation':True,'epoch':2},{'generation':0,'epoch':2}):
            with self.assertRaises(ValueError):delivery_page(self.db,100,auth)

    def test_readonly_connection(self):
        self.insert();self.begin();self.db.execute('PRAGMA query_only=ON')
        self.assertEqual(self.view()['returned_count'],1)


if __name__=='__main__':unittest.main()
