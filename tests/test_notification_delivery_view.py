import sqlite3
import json
import hashlib
import unittest
from scripts.notification_delivery_view import delivery_page


AUTH = {'generation': 1, 'epoch': 2}


# Exact _event method snapshot from P2 artifact11783079460 (77 hashes verified).
# Test-only producer, no operational database or runtime constructor is used.
# Source method SHA256: 625d79ddcc64f761cda1856e453711258b2cc6a60054404ad23c5ed8597cc662

def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class RealEventProducerFixture:
    def __init__(self):
        self.clock = lambda: 100
        self.activation_binding = {'generation': 1, 'epoch': 2}

    def _event(self, db, task_id, kind, details,
               destinations=('GITHUB_PR17', 'OWNER'), canonical=False, dedupe_key=None):
        key = ('%s:terminal:%s' % (task_id, kind)) if canonical else None
        if dedupe_key is not None:
            if (not isinstance(dedupe_key, str) or len(dedupe_key) != 64
                    or any(c not in '0123456789abcdef' for c in dedupe_key)):
                raise ValueError('INVALID_INVENTORY_EVENT_KEY')
            key = '%s:inventory:%s' % (task_id, dedupe_key)
            previous = db.execute('SELECT kind,details FROM supervision_events WHERE event_key=?',
                                  (key,)).fetchone()
            if previous is not None:
                if previous['kind'] != kind or previous['details'] != _dump(details):
                    raise ValueError('INVENTORY_EVENT_KEY_COLLISION')
                return key
        if key is not None and db.execute(
                'SELECT 1 FROM supervision_events WHERE event_key=?',
                (key,)).fetchone():
            return key
        sequence = db.execute('SELECT COUNT(*) FROM supervision_events WHERE task_id=?',
                              (task_id,)).fetchone()[0] + 1
        key = key or '%s:%s:%d' % (task_id, kind, sequence)
        now = float(self.clock())
        db.execute('INSERT INTO supervision_events VALUES(?,?,?,?,?,?)',
                   (key, task_id, sequence, kind, now, _dump(details)))
        task_fence = db.execute('SELECT fence FROM tasks WHERE id=?',
                                (task_id,)).fetchone()[0]
        authority_epoch = (self.activation_binding or {}).get('epoch', 0)
        for destination in destinations:
            db.execute("""INSERT INTO supervision_delivery
              (event_key,destination,state,attempts,next_attempt_at,claim_owner,
               claim_until,claim_epoch,authority_fence,authority_epoch,
               receipt_id,last_error,send_attempts,sent_at,
               reconciliation_owner,reconciliation_until,reconciliation_epoch)
              VALUES(?,?,'PENDING',0,?,NULL,NULL,0,?,?,NULL,NULL,0,NULL,NULL,NULL,0)""",
                       (key, destination, now, task_fence, authority_epoch))
        return key


class Tests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.authority = dict(AUTH)
        self.db.executescript('''
        CREATE TABLE tasks(id TEXT PRIMARY KEY, fence INTEGER);
        CREATE TABLE supervision_events(event_key TEXT PRIMARY KEY, task_id TEXT, sequence INTEGER, kind TEXT, created_at REAL, details TEXT);
        CREATE TABLE supervision_delivery(event_key TEXT, destination TEXT, state TEXT,
          attempts INTEGER, next_attempt_at REAL, authority_fence INTEGER,
          authority_epoch INTEGER, receipt_id TEXT, send_attempts INTEGER,
          claim_until REAL, claim_token TEXT, last_error TEXT, claim_owner TEXT,
          claim_epoch INTEGER, sent_at REAL, reconciliation_owner TEXT,
          reconciliation_until REAL, reconciliation_epoch INTEGER,
          PRIMARY KEY(event_key,destination));
        ''')

    def tearDown(self):
        self.db.close()

    def insert(self, index=1, destination='OWNER', state='PENDING', **changes):
        task_id = 'TASK_' + str(index)
        key = '%s:NOTICE:%d' % (task_id, index)
        self.db.execute('INSERT OR IGNORE INTO tasks VALUES(?,?)', (task_id,4))
        self.db.execute('INSERT OR IGNORE INTO supervision_events VALUES(?,?,?,?,?,?)',
                        (key, task_id, index, 'NOTICE', 100, 'PRIVATE_PAYLOAD'))
        row = dict(event_key=key, destination=destination, state=state, attempts=0,
                   next_attempt_at=100, authority_fence=4, authority_epoch=2,
                   receipt_id=None, send_attempts=0, claim_until=None,
                   claim_token='SECRET', last_error='SECRET')
        row.update(changes)
        self.db.execute('INSERT INTO supervision_delivery('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', list(row.values()))

    def begin(self):
        self.db.commit(); self.db.execute('BEGIN')

    def view(self, **kwargs):
        return delivery_page(self.db, 100, AUTH, read_authority=lambda: dict(self.authority), **kwargs)

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

    def test_stale_task_fence(self):
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
        for cursor in ([], ['<bad>','OWNER'], ['a'*64,"' OR 1=1 --"], True):
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


    def test_actual_event_producer_all_key_forms(self):
        self.db.execute('INSERT INTO tasks VALUES(?,?)', ('T1',4))
        producer=RealEventProducerFixture()
        producer._event(self.db,'T1','INVENTORY_NOTICE',{},dedupe_key='a'*64)
        producer._event(self.db,'T1','SUCCESS',{},canonical=True)
        producer._event(self.db,'T1','PROGRESS',{})
        self.begin();seen=[];cursor=None
        while True:
            page=self.view(limit=1,after=cursor);seen.extend(page['items'])
            if not page['has_more']:break
            cursor=page['next_cursor']
        self.assertEqual(len(seen),6)
        self.assertTrue(all(row['status']=='OBSERVED' for row in seen))
        self.assertTrue(any(row['event_key']=='T1:inventory:'+'a'*64 for row in seen))
        self.assertTrue(any(row['event_key']=='T1:terminal:SUCCESS' for row in seen))
        self.assertTrue(any(row['event_key']=='T1:PROGRESS:3' for row in seen))
        self.assertEqual(self.db.execute('SELECT authority_fence,authority_epoch FROM supervision_delivery LIMIT 1').fetchone(),(4,2))

    def test_actual_producer_task_fence_changes(self):
        self.db.execute('INSERT INTO tasks VALUES(?,?)',('T1',4))
        RealEventProducerFixture()._event(self.db,'T1','PROGRESS',{})
        self.db.execute('UPDATE tasks SET fence=5');self.begin()
        self.assertTrue(all(row['status']=='HOLD' for row in self.view()['items']))

    def test_different_generation_is_explicitly_verified(self):
        self.insert();self.begin()
        current={'generation':9,'epoch':2}
        result=delivery_page(self.db,100,current,read_authority=lambda:dict(current))
        self.assertEqual(result['items'][0]['status'],'OBSERVED')
        # Changing generation never means changing the independent task fence4.
        self.assertEqual(self.db.execute('SELECT authority_fence FROM supervision_delivery').fetchone()[0],4)

    def test_generation_mismatch_rejected(self):
        self.insert();self.begin();self.authority['generation']=2
        with self.assertRaisesRegex(ValueError,'ACTIVATION_CHANGED'):self.view()

    def test_generation_changes_during_read(self):
        self.insert();self.begin();calls=[]
        def reader():
            calls.append(1)
            return {'generation':1 if len(calls)==1 else 2,'epoch':2}
        with self.assertRaisesRegex(ValueError,'ACTIVATION_CHANGED'):
            delivery_page(self.db,100,AUTH,read_authority=reader)
        self.assertEqual(len(calls),2)

    def test_explicit_activation_reader_required(self):
        self.insert();self.begin()
        with self.assertRaisesRegex(ValueError,'ACTIVATION_RECHECK_REQUIRED'):
            delivery_page(self.db,100,AUTH)

    def test_missing_task_visible_hold(self):
        self.insert();self.db.execute('DELETE FROM tasks');self.begin()
        self.assertIn('STALE_OR_UNKNOWN_AUTHORITY',self.view()['items'][0]['warnings'])

    def test_key_must_bind_event_metadata(self):
        self.insert();self.db.execute("UPDATE supervision_events SET kind='DIFFERENT'");self.begin()
        self.assertIn('EVENT_KEY_BINDING_MISMATCH',self.view()['items'][0]['warnings'])


if __name__=='__main__':unittest.main()
