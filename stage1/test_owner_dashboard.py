import json
import os
import sqlite3
import tempfile
import unittest
from owner_dashboard import snapshot, read_token


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name, 'state.sqlite')
        with sqlite3.connect(self.db) as db:
            db.executescript('CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER,updated REAL,lease_owner TEXT,lease_until REAL,checkpoint TEXT);CREATE TABLE worker_heartbeats(worker_id TEXT,task_id TEXT,fence INTEGER,seen_at REAL,phase TEXT);')
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)', ('one','RUNNING',4,100,'dev',200,json.dumps({'phase':'CODE','secret':'never publish'})))
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)', ('human','WAITING_HUMAN',2,99,None,None,'{}'))

    def tearDown(self):
        self.temp.cleanup()

    def test_running_is_not_proof_of_activity(self):
        s = snapshot(self.db, now=110)
        self.assertEqual(s['tasks'][0]['execution_evidence'], 'UNKNOWN')
        self.assertNotIn('secret', s['tasks'][0]['checkpoint'])
        self.assertEqual(len(s['human_queue']), 1)

    def test_pipeline_checkpoint_commit_qa_and_reason_survive(self):
        sha = 'a' * 40
        qa_sha = 'b' * 40
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE tasks SET checkpoint=? WHERE id=?',
                       (json.dumps({'phase': 'QA_READY', 'sha': sha,
                                    'qa_commit': qa_sha, 'reason': 'QA_HEAD_CHANGED',
                                    'prompt': 'private instructions',
                                    'failure_log': 'secret=never publish'}), 'human'))
        s = snapshot(self.db, now=110)
        checkpoint = s['human_queue'][0]['checkpoint']
        self.assertEqual(checkpoint, {'phase': 'QA_READY', 'sha': sha,
                                     'commit': sha, 'qa_commit': qa_sha,
                                     'reason': 'QA_HEAD_CHANGED',
                                     'error_code': 'QA_HEAD_CHANGED'})
        self.assertEqual(checkpoint, next(t for t in s['tasks'] if t['id'] == 'human')['checkpoint'])

    def test_complete_human_queue_is_independent_of_recent_task_limit(self):
        with sqlite3.connect(self.db) as db:
            for n in range(205):
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',
                           ('new-' + str(n), 'DONE', 1, 200 + n, None, None, '{}'))
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',
                       ('older-human', 'WAITING_HUMAN', 3, 50, None, None,
                        json.dumps({'reason': 'RESOURCE_NOT_READY', 'prompt': 'secret'})))
        for limit in (1, 200):
            s = snapshot(self.db, now=500, limit=limit)
            self.assertTrue(s['truncated'])
            self.assertFalse(any(t['state'] == 'WAITING_HUMAN' for t in s['tasks']))
            self.assertEqual([t['id'] for t in s['human_queue']], ['human', 'older-human'])
            self.assertEqual(len(s['human_queue']), s['counts']['WAITING_HUMAN'])
            self.assertEqual(s['human_queue'][1]['checkpoint'],
                             {'reason': 'RESOURCE_NOT_READY', 'error_code': 'RESOURCE_NOT_READY'})

    def test_new_metadata_rejects_freeform_or_invalid_values(self):
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE tasks SET checkpoint=? WHERE id=?',
                       (json.dumps({'sha': 'secret=' + 'a' * 40,
                                    'qa_commit': 'b' * 41,
                                    'reason': 'token=private', 'ci': 'PASS'}), 'human'))
        s = snapshot(self.db, now=110)
        self.assertEqual(s['human_queue'][0]['checkpoint'], {'ci': 'PASS'})

    def test_model_policy_is_not_actual_inference_evidence(self):
        s = snapshot(self.db, now=110)
        self.assertEqual(s['model_policy'],
                         {'primary': 'openai/gpt-6.1-sol',
                          'fallbacks': ['openai/gpt-5.6-sol'],
                          'source': 'OWNER_CONFIGURATION_INTENT'})
        self.assertEqual(s['model'], 'UNKNOWN')
        self.assertIsNone(s['fallbacks'])
        self.assertEqual(s['services']['codex_model_access'], 'UNKNOWN')

    def test_heartbeat_matches_lease_worker_fence_and_age(self):
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO worker_heartbeats VALUES(?,?,?,?,?)', ('dev','one',4,108,'CODE'))
        self.assertEqual(snapshot(self.db, now=110)['tasks'][0]['execution_evidence'], 'FRESH_WORKER_HEARTBEAT')
        self.assertEqual(snapshot(self.db, now=180)['tasks'][0]['execution_evidence'], 'UNKNOWN')
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE worker_heartbeats SET fence=3,seen_at=109')
        self.assertEqual(snapshot(self.db, now=110)['tasks'][0]['execution_evidence'], 'UNKNOWN')

    def test_limit_and_read_only(self):
        self.assertTrue(snapshot(self.db, now=110, limit=1)['truncated'])
        with self.assertRaises(ValueError):
            snapshot(self.db, limit=0)
        missing = os.path.join(self.temp.name,'missing')
        with self.assertRaises(sqlite3.Error):
            snapshot(missing)
        self.assertFalse(os.path.exists(missing))

    def test_non_object_checkpoint_and_sensitive_allowed_key_are_removed(self):
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE tasks SET checkpoint=? WHERE id=?', ('["secret=hidden"]','one'))
        self.assertEqual(snapshot(self.db,now=110)['tasks'][0]['checkpoint'], {})
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE tasks SET checkpoint=? WHERE id=?', (json.dumps({'phase':'secret=hidden','ci':'token-value'}),'one'))
        self.assertEqual(snapshot(self.db,now=110)['tasks'][0]['checkpoint'], {})

    def test_token_rejects_world_readable_and_symlink(self):
        token = os.path.join(self.temp.name,'token')
        with open(token,'w') as stream:
            stream.write('t'*48)
        os.chmod(token,0o644)
        with self.assertRaises(ValueError):
            read_token(token)
        os.chmod(token,0o600)
        self.assertEqual(read_token(token),'t'*48)
        link = os.path.join(self.temp.name,'link')
        os.symlink(token,link)
        with self.assertRaises(ValueError):
            read_token(link)


if __name__ == '__main__':
    unittest.main()
