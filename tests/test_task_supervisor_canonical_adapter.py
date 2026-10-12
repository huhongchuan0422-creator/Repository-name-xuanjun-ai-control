import sqlite3
import unittest
import os,sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from task_supervisor_runtime import canonical_inventory_page as inventory_page, CANONICAL_RUN_COLUMNS as RUN_COLUMNS


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,'
                        'depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,'
                        'checkpoint TEXT,updated REAL)')
        self.db.execute('CREATE TABLE supervised_runs(' + ','.join(RUN_COLUMNS) + ')')

    def tearDown(self):
        self.db.close()

    def task(self, name, state='PENDING', depends='[]'):
        self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                        (name, 'CODEX_EXEC', state, depends, 'writer', 200, 4,
                         'PRIVATE_PROMPT_MUST_NOT_BE_EXPORTED', 999999))

    def begin(self):
        self.db.commit()
        self.db.execute('BEGIN')

    def test_no_transaction_rejected(self):
        with self.assertRaises(ValueError): inventory_page(self.db, 100)

    def test_all_tasks_paginated_no_missing_supervision_omission(self):
        for i in range(7): self.task(str(i))
        self.begin(); seen=[]; cursor=None
        while True:
            result=inventory_page(self.db,100,cursor,2)
            seen.extend(x['id'] for x in result['tasks'])
            self.assertTrue(all('SUPERVISION_RECORD_MISSING' in x['attention'] for x in result['tasks']))
            if result['complete']:break
            cursor=result['next_cursor']
        self.assertEqual(seen,list(map(str,range(7))))

    def test_no_mutation_or_private_checkpoint_export(self):
        self.task('a');self.begin();before=self.db.total_changes
        result=inventory_page(self.db,100)
        self.assertEqual(self.db.total_changes,before)
        self.assertNotIn('PRIVATE_PROMPT',repr(result))
        self.assertFalse(result['dispatch_performed'])

    def test_heartbeat_does_not_hide_deadline_and_unknown_effect(self):
        self.task('a','RUNNING')
        values=dict.fromkeys(RUN_COLUMNS);values.update(task_id='a',executor='DOTS',
            progress_deadline=50,result_deadline=60,effects='UNKNOWN')
        self.db.execute('INSERT INTO supervised_runs VALUES('+','.join('?' for x in RUN_COLUMNS)+')',
                        [values[x] for x in RUN_COLUMNS]);self.begin()
        row=inventory_page(self.db,300)['tasks'][0]
        for flag in ('LEASE_EXPIRED','PROGRESS_DEADLINE_EXCEEDED','RESULT_DEADLINE_EXCEEDED','UNKNOWN_EFFECT_NO_REPLAY'):
            self.assertIn(flag,row['attention'])
        self.assertEqual(row['execution_authority'],'NOT_GRANTED')

    def test_missing_and_failed_dependencies_remain_blocked(self):
        self.task('a','FAILED');self.task('b',depends='["a","missing"]');self.begin()
        self.assertIn('DEPENDENCIES_NOT_DONE',inventory_page(self.db,100)['tasks'][1]['attention'])

    def test_reject_standalone_schema_without_creating_tables(self):
        self.db.execute('DROP TABLE tasks');self.db.execute('CREATE TABLE tasks(task_id TEXT)');self.begin()
        with self.assertRaises(ValueError):inventory_page(self.db,100)

    def test_absent_optional_table_not_created(self):
        self.db.execute('DROP TABLE supervised_runs');self.task('a');self.begin()
        self.assertIn('SUPERVISION_RECORD_MISSING',inventory_page(self.db,100)['tasks'][0]['attention'])
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='supervised_runs'").fetchone())

    def test_unsupervised_expired_writer_is_visible(self):
        self.task('a','RUNNING');self.begin()
        flags=inventory_page(self.db,300)['tasks'][0]['attention']
        self.assertIn('LEASE_EXPIRED',flags)
        self.assertIn('SUPERVISION_RECORD_MISSING',flags)

    def test_restart_duplicate_scan_preserves_decision_identity(self):
        self.task('a');self.begin()
        first=inventory_page(self.db,100)['tasks'][0]
        self.db.rollback();self.db.execute('BEGIN')
        second=inventory_page(self.db,101)['tasks'][0]
        self.assertEqual(first['decision_key'],second['decision_key'])
        self.assertEqual(second['provider'],'CAPABILITY_UNAVAILABLE')

    def test_dead_letter_and_old_fence_are_observed_not_rewritten(self):
        self.task('a');self.db.execute('CREATE TABLE supervision_events(event_key TEXT,task_id TEXT)')
        self.db.execute('CREATE TABLE supervision_delivery(event_key TEXT,destination TEXT,state TEXT,attempts INTEGER,next_attempt_at REAL,authority_fence INTEGER,authority_epoch INTEGER)')
        self.db.execute("INSERT INTO supervision_events VALUES('event1','a')")
        self.db.execute("INSERT INTO supervision_delivery VALUES('event1','PR17','DEAD_LETTER',5,200,3,1)")
        self.begin();before=self.db.total_changes
        row=inventory_page(self.db,100)['tasks'][0]
        self.assertIn('STALE_DELIVERY_RECONCILE_ONLY',row['attention'])
        self.assertEqual(row['deliveries'][0]['state'],'DEAD_LETTER')
        self.assertEqual(self.db.total_changes,before)

    def test_entry_pairs_do_not_grant_execution(self):
        self.task('a')
        for origin in ('WORK','DOTS','CHATGPT'):
            for successor in ('WORK','DOTS','CHATGPT'):
                self.db.execute('DELETE FROM supervised_runs')
                values=dict.fromkeys(RUN_COLUMNS);values.update(task_id='a',executor=successor,
                    run_id=origin+'-old',effects='UNKNOWN',status='RESUMABLE',writer_fence=3)
                self.db.execute('INSERT INTO supervised_runs VALUES('+','.join('?' for x in RUN_COLUMNS)+')',
                                [values[x] for x in RUN_COLUMNS]);self.begin()
                row=inventory_page(self.db,100)['tasks'][0]
                self.assertEqual(row['execution_authority'],'NOT_GRANTED')
                self.assertIn('UNKNOWN_EFFECT_NO_REPLAY',row['attention'])
                self.db.rollback()

    def test_activation_and_exact_task_are_bound(self):
        self.task('a');self.task('b');self.begin()
        activation={'ledger_uuid':'00000000-0000-0000-0000-000000000001',
                    'instance':'00000000-0000-0000-0000-000000000002',
                    'generation':1,'epoch':2,'db_path':'/fixture/canonical.db'}
        result=inventory_page(self.db,100,activation_binding=activation,ledger_identity='1:2',task_id='b')
        self.assertEqual([x['id'] for x in result['tasks']],['b'])
        self.assertEqual(result['tasks'][0]['binding']['activation'],activation)
        self.assertEqual(result['tasks'][0]['binding']['ledger_identity'],'1:2')

    def test_all_entries_deny_delegated_routes_without_fallback(self):
        from task_supervisor_runtime import receiver_continuation_policy
        for entry in ('WORK','CHATGPT','DOTS'):
            for route in ('WORK','CODEX','CODEX_CLI','APP_SERVER','PAID_API','OPENCLAW_AGENT','CHILD_SPAWN','FALLBACK','NATIVE_CHAT_CALL'):
                value=receiver_continuation_policy(entry,route)
                self.assertEqual(value['state'],'CAPABILITY_UNAVAILABLE')
                self.assertFalse(value['dispatch']);self.assertIsNone(value['fallback'])
            value=receiver_continuation_policy(entry,'HASH_SYNTAX_TEST')
            self.assertEqual(value['state'],'MECHANICAL_REVIEW_REQUIRED')
            self.assertFalse(value['dispatch'])

    def test_lineage_rejects_replacement_and_missing_authority(self):
        import copy
        from task_supervisor_runtime import assert_inventory_lineage
        expected={'task_id':'a','fence':4,'spec_sha256':'a'*64,'checkpoint_sha256':'b'*64,
                  'run_id':'r1','session_id':'s1','epoch':2,'attempt_id':'c'*64,
                  'ledger_identity':'1:2','entry':'DOTS','lease_id':'lease1',
                  'activation':{'ledger_uuid':'u1','generation':1,'epoch':2,'instance':'i1','db_path':'/fixture'}}
        for key,value in (('run_id','r2'),('session_id','s2'),('fence',5),('epoch',3),('checkpoint_sha256','d'*64)):
            current=copy.deepcopy(expected);current[key]=value
            with self.assertRaises(ValueError):assert_inventory_lineage(expected,current)
        for key in ('generation','epoch','instance'):
            current=copy.deepcopy(expected);current['activation'][key]='changed'
            with self.assertRaises(ValueError):assert_inventory_lineage(expected,current)
        current=copy.deepcopy(expected);current['attempt_id']='UNKNOWN'
        with self.assertRaises(ValueError):assert_inventory_lineage(expected,current)
        self.assertEqual(assert_inventory_lineage(expected,expected),'MATCHED_OBSERVATION_NOT_AUTHORITY')

    def test_invalid_limits_and_clock(self):
        self.begin()
        for clock,limit in ((float('nan'),1),(100,True),(100,0),(100,101)):
            with self.assertRaises(ValueError):inventory_page(self.db,clock,limit=limit)


if __name__=='__main__': unittest.main()
