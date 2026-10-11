import json
import multiprocessing
import os
import sqlite3
import tempfile
import threading
import unittest
from execution_ledger import ExecutionLedger, InvalidDAG, LeaseLost, SchemaMismatch

SCHEMA = '''
CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,
lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL);
CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,requested_at REAL,decided_at REAL);
CREATE TABLE events(id INTEGER PRIMARY KEY,task_id TEXT,event TEXT,created REAL,details TEXT);
'''


def process_claim(path, identity, output):
    ledger = ExecutionLedger(path, ['owner/repo'])
    output.put(ledger.claim(identity, ttl=60))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = self.temp.name + '/existing.db'
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)
        self.now = 1000.0
        self.ledger = ExecutionLedger(self.path, ['owner/repo'], clock=lambda: self.now)

    def add(self, task_id, kind='CODEX_EXEC', state='PENDING', depends=None):
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                         (task_id, kind, state, json.dumps(depends or []),
                          None, None, 0, '{}', 0.0))

    def spec(self, heavy=True):
        return {'repo': 'owner/repo', 'type': 'CODEX_EXEC', 'heavy': heavy,
                'prompt': 'Implement a tested change in the isolated checkout.',
                'timeout_seconds': 300, 'base_sha': 'a' * 40}

    def register(self, task_id, heavy=True):
        return self.ledger.register_spec(task_id, self.spec(heavy), 'owner', True)

    def token(self, claim):
        return (claim['task_id'], claim['worker_id'], claim['fence'])

    def row(self, table, task_id):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            key = 'id' if table == 'tasks' else 'task_id'
            return dict(conn.execute('SELECT * FROM %s WHERE %s=?' % (table, key),
                                     (task_id,)).fetchone())

    def test_missing_schema_never_creates_registry(self):
        path = self.temp.name + '/missing.db'
        with self.assertRaises(SchemaMismatch):
            ExecutionLedger(path, ['owner/repo'])
        self.assertFalse(os.path.exists(path))

    def test_schema_mismatch_fails_before_side_tables(self):
        path = self.temp.name + '/wrong.db'
        with sqlite3.connect(path) as conn:
            conn.executescript(SCHEMA.replace('fence INTEGER', 'fence TEXT'))
        with self.assertRaises(SchemaMismatch):
            ExecutionLedger(path, ['owner/repo'])
        with sqlite3.connect(path) as conn:
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='execution_specs'").fetchone())

    def test_register_requires_author_attestation(self):
        self.add('a')
        for author, authorized in [('', True), ('owner', False), ('owner', 'true')]:
            with self.assertRaises(PermissionError):
                self.ledger.register_spec('a', self.spec(), author, authorized)

    def test_rejects_issue_shell_and_untrusted_repo_or_type(self):
        self.add('a')
        variants = [dict(self.spec(), shell='rm -rf /'),
                    dict(self.spec(), issue_body='shell'),
                    dict(self.spec(), repo='attacker/repo'),
                    dict(self.spec(), type='SHELL')]
        for spec in variants:
            with self.assertRaises(ValueError):
                self.ledger.register_spec('a', spec, 'owner', True)

    def test_base_sha_requires_exact_hex_commit(self):
        self.add('a')
        for base_sha in ['', 'main', 'a' * 39, 'a' * 41, 'z' * 40, 42]:
            with self.assertRaises(ValueError):
                self.ledger.register_spec('a', dict(self.spec(), base_sha=base_sha), 'owner', True)

    def test_spec_revision_resets_existing_human_approval(self):
        self.add('a', state='WAITING_HUMAN')
        first = self.register('a')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE approvals SET decision='APPROVE',decided_at=1 WHERE task_id='a'")
        second = self.ledger.register_spec('a', dict(self.spec(), prompt='Changed owner requirement'), 'owner', True)
        self.assertEqual(second['revision'], first['revision'] + 1)
        self.assertEqual(self.row('approvals', 'a')['decision'], 'PENDING')
        with self.assertRaises(PermissionError):
            self.ledger.resume_human('a', 'owner')

    def test_same_spec_registration_is_idempotent(self):
        self.add('a', state='WAITING_HUMAN')
        first = self.register('a')
        before = self.row('tasks', 'a')['fence']
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE approvals SET decision='APPROVE',decided_at=1 WHERE task_id='a'")
        second = self.register('a')
        self.assertEqual(second, first)
        self.assertEqual(self.row('tasks', 'a')['fence'], before)
        self.assertEqual(self.row('approvals', 'a')['decision'], 'APPROVE')

    def test_changed_human_spec_invalidates_old_request_fence(self):
        self.add('a', state='WAITING_HUMAN')
        self.register('a')
        before = self.row('tasks', 'a')['fence']
        self.ledger.register_spec('a', dict(self.spec(), prompt='New requirement'), 'owner', True)
        self.assertGreater(self.row('tasks', 'a')['fence'], before)
        self.assertEqual(self.row('approvals', 'a')['decision'], 'PENDING')

    def test_bad_dag_quarantined_independent_tasks_continue(self):
        for task in ['bad', 'child', 'good']:
            self.add(task, depends=['bad'] if task == 'child' else [])
            self.register(task)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE tasks SET depends='[\"missing\"]' WHERE id='bad'")
        self.assertEqual(self.ledger.claim('w')['task_id'], 'good')
        for task in ['bad', 'child']:
            self.assertEqual(self.row('tasks', task)['state'], 'WAITING_HUMAN')
            self.assertEqual(self.row('approvals', task)['decision'], 'PENDING')

    def test_unrelated_historical_cycle_does_not_block_registration(self):
        self.add('old1', kind='MARKER', depends=['old2'])
        self.add('old2', kind='MARKER', depends=['old1'])
        self.add('good')
        self.register('good')
        self.assertEqual(self.ledger.claim('w')['task_id'], 'good')
        self.assertEqual(self.row('tasks', 'old1')['state'], 'PENDING')

    def test_bad_spec_quarantined_independent_task_continues(self):
        for task in ['bad', 'good']:
            self.add(task)
            self.register(task)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE execution_specs SET spec='invalid' WHERE task_id='bad'")
        self.assertEqual(self.ledger.claim('w')['task_id'], 'good')
        self.assertEqual(self.row('tasks', 'bad')['state'], 'WAITING_HUMAN')

    def test_bad_checkpoint_quarantined_independent_task_continues(self):
        for task in ['bad', 'good']:
            self.add(task)
            self.register(task)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE tasks SET checkpoint='[1]' WHERE id='bad'")
        self.assertEqual(self.ledger.claim('w')['task_id'], 'good')
        self.assertEqual(self.row('tasks', 'bad')['state'], 'WAITING_HUMAN')

    def test_heartbeat_phase_and_dashboard_columns(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w')
        self.ledger.heartbeat(*self.token(claim), phase='TESTING')
        row = self.row('worker_heartbeats', 'a')
        self.assertEqual(row['phase'], 'TESTING')
        self.assertEqual(row['seen_at'], self.now)
        for phase in ['bad text', '', 'EXECUTING;DROP', 'X' * 33]:
            with self.assertRaises(ValueError):
                self.ledger.heartbeat(*self.token(claim), phase=phase)

    def test_marker_human_and_kind_mismatch_not_claimed(self):
        self.add('marker', 'MARKER')
        self.add('human', 'HUMAN_GATE', 'WAITING_HUMAN')
        with self.assertRaises(ValueError):
            self.register('marker')
        self.assertIsNone(self.ledger.claim('worker'))
        self.assertEqual(self.row('tasks', 'marker')['state'], 'PENDING')
        self.assertEqual(self.row('tasks', 'human')['state'], 'WAITING_HUMAN')

    def test_unknown_dependency_rejected(self):
        self.add('a', depends=['missing'])
        with self.assertRaises(InvalidDAG):
            self.register('a')
        self.assertIsNone(self.ledger.claim('worker'))

    def test_cycle_rejected(self):
        self.add('a', depends=['b'])
        self.add('b', depends=['a'])
        with self.assertRaises(InvalidDAG):
            self.register('a')

    def test_dependencies_and_approved_human_must_be_done(self):
        self.add('human', 'HUMAN_GATE', 'WAITING_HUMAN')
        self.add('a', depends=['human'])
        self.register('a')
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT INTO approvals VALUES(?,?,?,?)', ('human', 'APPROVE', 1, 2))
        self.assertIsNone(self.ledger.claim('worker'))
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE tasks SET state='DONE' WHERE id='human'")
        self.assertEqual(self.ledger.claim('worker')['task_id'], 'a')

    def test_heavy_limit_skips_to_light(self):
        for task in ['a', 'b', 'c', 'd']:
            self.add(task)
            self.register(task, heavy=task != 'd')
        self.assertEqual(self.ledger.claim('w1')['task_id'], 'a')
        self.assertEqual(self.ledger.claim('w2')['task_id'], 'b')
        self.assertEqual(self.ledger.claim('w3')['task_id'], 'd')
        self.assertIsNone(self.ledger.claim('w4'))

    def test_skips_human_and_resource_to_continue_queue(self):
        self.add('a', state='WAITING_HUMAN')
        self.register('a')
        self.add('b', state='PAUSED_RESOURCE')
        self.register('b')
        self.add('c')
        self.register('c')
        self.assertEqual(self.ledger.claim('w')['task_id'], 'c')

    def test_heartbeat_checkpoint_finish_are_fenced(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w', ttl=10)
        token = self.token(claim)
        self.now += 5
        self.assertEqual(self.ledger.heartbeat(*token, ttl=20), 1025)
        self.ledger.checkpoint(*token, value={'stage': 'tests'})
        self.assertEqual(json.loads(self.row('tasks', 'a')['checkpoint']), {'stage': 'tests'})
        self.assertTrue(self.ledger.assert_live(*token))
        self.assertEqual(self.ledger.finish(*token, state='DONE'), 'DONE')
        with self.assertRaises(LeaseLost):
            self.ledger.checkpoint(*token, value={'stage': 'stale'})
        with self.assertRaises(LeaseLost):
            self.ledger.finish(*token, state='FAILED')

    def test_wrong_owner_or_fence_cannot_mutate(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w')
        for identity, fence in [('attacker', claim['fence']), ('w', claim['fence'] - 1)]:
            with self.assertRaises(LeaseLost):
                self.ledger.heartbeat('a', identity, fence)
            with self.assertRaises(LeaseLost):
                self.ledger.finish('a', identity, fence, 'DONE')

    def test_expiration_requires_review_preserves_checkpoint_resets_approval(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w', ttl=10)
        self.ledger.checkpoint(*self.token(claim), value={'effects': 'uncertain'})
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT INTO approvals VALUES(?,?,?,?)', ('a', 'APPROVE', 1, 2))
        self.now += 10
        with self.assertRaises(LeaseLost):
            self.ledger.assert_live(*self.token(claim))
        self.assertEqual(self.ledger.recover_expired(), ['a'])
        task = self.row('tasks', 'a')
        self.assertEqual(task['state'], 'WAITING_HUMAN')
        self.assertEqual(task['fence'], claim['fence'] + 1)
        self.assertEqual(json.loads(task['checkpoint']), {'effects': 'uncertain'})
        self.assertEqual(self.row('approvals', 'a')['decision'], 'PENDING')
        self.assertIsNone(self.ledger.claim('w2'))
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM events WHERE event='LEASE_EXPIRED_UNCERTAIN_EFFECTS'").fetchone()[0], 1)
        self.assertEqual(self.ledger.recover_expired(), [])

    def test_resume_human_requires_approval_and_new_fence(self):
        self.add('a')
        self.register('a')
        old = self.ledger.claim('w', ttl=1)
        self.now += 2
        self.ledger.recover_expired()
        with self.assertRaises(PermissionError):
            self.ledger.resume_human('a', 'owner')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE approvals SET decision='APPROVE',decided_at=1002 WHERE task_id='a'")
        self.ledger.resume_human('a', 'owner')
        new = self.ledger.claim('w2')
        self.assertGreater(new['fence'], old['fence'])
        with self.assertRaises(LeaseLost):
            self.ledger.finish(*self.token(old), state='DONE')

    def test_known_no_effect_resource_resume_authorized_auto(self):
        self.add('a')
        self.register('a')
        old = self.ledger.claim('w')
        self.assertEqual(self.ledger.finish(*self.token(old), state='PAUSED_RESOURCE', effects='none'), 'PAUSED_RESOURCE')
        with self.assertRaises(PermissionError):
            self.ledger.resume_resource('a', 'scheduler', False, automatic=True)
        self.ledger.resume_resource('a', 'scheduler', True, automatic=True)
        self.assertEqual(self.ledger.claim('w2')['task_id'], 'a')

    def test_unknown_resource_effects_routes_to_human(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w')
        self.assertEqual(self.ledger.finish(*self.token(claim), state='PAUSED_RESOURCE'), 'WAITING_HUMAN')
        with self.assertRaises(ValueError):
            self.ledger.resume_resource('a', 'owner', True)
        self.assertEqual(self.row('approvals', 'a')['decision'], 'PENDING')

    def test_running_spec_immutable_and_integrity_checked(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w')
        with self.assertRaises(ValueError):
            self.register('a')
        self.ledger.finish(*self.token(claim), state='PAUSED_RESOURCE', effects='none')
        self.ledger.resume_resource('a', 'owner', True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE execution_specs SET hash='invalid' WHERE task_id='a'")
        self.assertIsNone(self.ledger.claim('w2'))
        self.assertEqual(self.row('tasks', 'a')['state'], 'WAITING_HUMAN')

    def test_waiting_for_db_lock_cannot_renew_expired_lease(self):
        self.add('a')
        self.register('a')
        claim = self.ledger.claim('w', ttl=1)
        clock_seen = threading.Event()
        started = threading.Event()
        errors = []
        def clock():
            clock_seen.set()
            return self.now
        blocked = ExecutionLedger(self.path, ['owner/repo'], clock=clock)
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute('BEGIN IMMEDIATE')
        def renew():
            started.set()
            try:
                blocked.heartbeat(*self.token(claim), ttl=60)
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=renew)
        thread.start()
        self.assertTrue(started.wait(timeout=1))
        try:
            self.assertFalse(clock_seen.wait(timeout=0.05))
            self.now += 2
        finally:
            conn.rollback()
            conn.close()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], LeaseLost)
        self.assertEqual(self.row('tasks', 'a')['lease_until'], claim['lease_until'])

    def test_thread_claim_only_one_owner(self):
        self.add('a')
        self.register('a')
        results = []
        errors = []
        barrier = threading.Barrier(8)
        def run(identity):
            try:
                ledger = ExecutionLedger(self.path, ['owner/repo'], clock=lambda: self.now)
                barrier.wait(timeout=5)
                results.append(ledger.claim(identity))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=run, args=('w%d' % i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_process_claim_atomic_limit_and_restart_recovery(self):
        for task in ['a', 'b', 'c']:
            self.add(task)
            self.register(task)
        output = multiprocessing.Queue()
        processes = [multiprocessing.Process(target=process_claim,
                      args=(self.path, 'p%d' % i, output)) for i in range(4)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
        claims = [output.get(timeout=2) for unused in processes]
        winners = [claim for claim in claims if claim]
        self.assertEqual(len(winners), 2)
        self.assertEqual(len(set(c['task_id'] for c in winners)), 2)
        latest = max(c['lease_until'] for c in winners) + 1
        restarted = ExecutionLedger(self.path, ['owner/repo'], clock=lambda: latest)
        self.assertEqual(set(restarted.recover_expired()), set(c['task_id'] for c in winners))
        for claim in winners:
            self.assertEqual(self.row('tasks', claim['task_id'])['state'], 'WAITING_HUMAN')
            with self.assertRaises(LeaseLost):
                restarted.assert_live(*self.token(claim))
        self.assertEqual(restarted.claim('new')['task_id'], 'c')
        output.close()
        output.join_thread()

    def test_schema_survives_restart_no_new_registry(self):
        self.add('a')
        first = self.register('a')
        restarted = ExecutionLedger(self.path, ['owner/repo'], clock=lambda: self.now)
        self.assertEqual(restarted.claim('w')['spec_hash'], first['hash'])
        with sqlite3.connect(self.path) as conn:
            names = set(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        self.assertEqual(names, {'tasks', 'approvals', 'events', 'execution_specs', 'worker_heartbeats'})


if __name__ == '__main__':
    unittest.main()
