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
