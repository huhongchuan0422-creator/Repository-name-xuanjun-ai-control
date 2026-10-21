import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from production.cloud_connection.queue import Hold, Queue


PIN = 'a' * 64
ACTOR = 332398908
NOW = 1792592000


def request(name='job-1', project='connection-check'):
    return dict(schema=1, request_id=name, project=project, target='korea',
                operation='probe', executor_sha256=PIN, arguments={}, expires_unix=NOW + 18000)


class ConnectionQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'queue.sqlite')
        self.q = Queue(self.path, PIN, {ACTOR})

    def tearDown(self):
        self.q.close()
        self.tmp.cleanup()

    def submit(self, value=None, queue=None, actor=ACTOR):
        return (queue or self.q).submit(json.dumps(value or request()), actor, NOW)

    def test_submit_and_duplicate_do_not_create_new_job(self):
        self.submit()
        self.submit()
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM connection_jobs').fetchone(), (1,))

    def test_request_rebind_rejected(self):
        self.submit()
        changed = request()
        changed['target'] = 'domestic'
        with self.assertRaisesRegex(Hold, 'REBOUND'):
            self.submit(changed)

    def test_body_actor_claim_not_trusted(self):
        with self.assertRaisesRegex(Hold, 'UNTRUSTED'):
            self.submit(actor=95597695)
        r = request()
        r['actor_id'] = ACTOR
        with self.assertRaisesRegex(Hold, 'FIELDS'):
            self.submit(r)

    def test_arbitrary_execution_denied(self):
        r = request()
        r.update(operation='run', arguments={'command': 'echo unsafe'})
        with self.assertRaisesRegex(Hold, 'NOT_ENROLLED'):
            self.submit(r)

    def test_wrong_target_denied(self):
        r = request()
        r['target'] = 'tokyo'
        with self.assertRaisesRegex(Hold, 'TARGET'):
            self.submit(r)

    def test_wrong_code_pin_denied(self):
        r = request()
        r['executor_sha256'] = 'b' * 64
        with self.assertRaisesRegex(Hold, 'VERSION'):
            self.submit(r)

    def test_expiry_checked_again_before_dispatch(self):
        self.submit()
        with self.assertRaisesRegex(Hold, 'EXPIRY'):
            self.q.begin_dispatch('job-1', NOW + 18000)
        self.assertEqual(self.q.inspect('job-1')['state'], 'READY')

    def test_duplicate_json_keys_denied(self):
        raw = json.dumps(request()).replace('"schema": 1', '"schema": 1,"schema":1')
        with self.assertRaisesRegex(Hold, 'DUPLICATE'):
            self.q.submit(raw, ACTOR, NOW)

    def test_nonfinite_json_denied(self):
        raw = json.dumps(request()).replace(str(NOW + 18000), 'NaN')
        with self.assertRaises(Hold):
            self.q.submit(raw, ACTOR, NOW)

    def test_fetch_path_is_fixed_and_bounded(self):
        r = request()
        r.update(operation='fetch_os_release', arguments={'path': '/etc/os-release', 'max_bytes': 65536})
        self.submit(r)
        r['request_id'] = 'job-2'
        r['arguments']['path'] = '/etc/shadow'
        with self.assertRaisesRegex(Hold, 'ARGUMENTS'):
            self.submit(r)

    def test_same_project_has_one_dispatcher(self):
        self.submit()
        self.submit(request('job-2'))
        self.q.begin_dispatch('job-1', NOW)
        other = Queue(self.path, PIN, {ACTOR})
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                other.begin_dispatch('job-2', NOW)
            self.assertFalse(other.db.in_transaction)
        finally:
            other.close()

    def test_unrelated_projects_can_dispatch(self):
        self.submit()
        self.submit(request('job-2', 'other-project'))
        self.q.begin_dispatch('job-1', NOW)
        self.q.begin_dispatch('job-2', NOW)

    def test_intent_survives_independent_process(self):
        self.submit()
        self.q.begin_dispatch('job-1', NOW)
        code = ('import json;from production.cloud_connection.queue import Queue;'
                'q=Queue(%r,%r,{%r});print(json.dumps(q.inspect("job-1")));q.close()'
                % (self.path, PIN, ACTOR))
        result = subprocess.run([sys.executable, '-c', code], check=True,
                                stdout=subprocess.PIPE, universal_newlines=True)
        value = json.loads(result.stdout)
        self.assertEqual(value['state'], 'DISPATCHING')
        self.assertFalse(value['redispatch_allowed'])

    def test_unknown_blocks_retry_and_next_project_writer(self):
        self.submit()
        self.submit(request('job-2'))
        self.q.begin_dispatch('job-1', NOW)
        self.q.unknown('job-1')
        with self.assertRaisesRegex(Hold, 'QUERY_EXISTING'):
            self.q.begin_dispatch('job-1', NOW)
        with self.assertRaises(sqlite3.IntegrityError):
            self.q.begin_dispatch('job-2', NOW)

    def test_only_existing_invoke_can_finish(self):
        self.submit()
        self.q.begin_dispatch('job-1', NOW)
        self.q.record_invoke('job-1', 't-real-1')
        self.q.unknown('job-1')
        with self.assertRaises(Hold):
            self.q.terminal('job-1', 't-wrong', {'state': 'SUCCESS'})
        self.q.terminal('job-1', 't-real-1', {'state': 'SUCCESS'})
        with self.assertRaises(Hold):
            self.q.terminal('job-1', 't-real-1', {'state': 'FAILED'})

    def test_success_releases_project_without_replaying(self):
        self.submit()
        self.submit(request('job-2'))
        self.q.begin_dispatch('job-1', NOW)
        self.q.record_invoke('job-1', 't-real-1')
        self.q.terminal('job-1', 't-real-1', {'state': 'SUCCESS'})
        self.q.begin_dispatch('job-2', NOW)
        with self.assertRaises(Hold):
            self.q.begin_dispatch('job-1', NOW)

    def test_replace_and_upsert_cannot_rebind_history(self):
        self.submit()
        row = list(self.q.db.execute('SELECT * FROM connection_jobs').fetchone())
        row[1] = 'changed'
        for sql in ('INSERT OR REPLACE INTO connection_jobs VALUES(?,?,?,?,?,?,?,?)',
                    'REPLACE INTO connection_jobs VALUES(?,?,?,?,?,?,?,?)'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.q.db.execute(sql, row)
        with self.assertRaises(sqlite3.IntegrityError):
            self.q.db.execute("UPDATE connection_jobs SET request_id='changed' WHERE request_id='job-1'")
        self.assertEqual(self.q.db.execute('SELECT project FROM connection_jobs').fetchone(), ('connection-check',))

    def test_database_busy_does_not_consume_task(self):
        self.submit()
        other = Queue(self.path, PIN, {ACTOR})
        try:
            other.db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):
                self.q.begin_dispatch('job-1', NOW)
            self.assertFalse(self.q.db.in_transaction)
            other.db.execute('ROLLBACK')
            self.assertEqual(self.q.inspect('job-1')['state'], 'READY')
        finally:
            other.close()


if __name__ == '__main__':
    unittest.main()
