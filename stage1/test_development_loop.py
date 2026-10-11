import json
import os
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import Future

from development_loop import DevelopmentLoop
from execution_ledger import ExecutionLedger


SCHEMA = '''CREATE TABLE tasks(id TEXT PRIMARY KEY,kind TEXT,state TEXT,depends TEXT,lease_owner TEXT,lease_until REAL,fence INTEGER,checkpoint TEXT,updated REAL);
CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,requested_at REAL,decided_at REAL);
CREATE TABLE events(id INTEGER PRIMARY KEY,task_id TEXT,event TEXT,created REAL,details TEXT);'''


class InlineExecutor:
    def submit(self, fn, claim):
        result=Future()
        try:result.set_result(fn(claim))
        except Exception as exc:result.set_exception(exc)
        return result
    def shutdown(self, wait=False):
        pass


class PendingExecutor:
    def __init__(self):
        self.futures = []

    def submit(self, fn, claim):
        future = Future()
        future.set_running_or_notify_cancel()
        self.futures.append(future)
        return future

    def shutdown(self, wait=False):
        pass


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.temp.name,'state.sqlite')
        self.now=100
        with sqlite3.connect(self.db) as db:
            db.executescript(SCHEMA)
            for ident,deps in [('one','[]'),('two','["one"]'),('human','[]')]:
                state='WAITING_HUMAN' if ident=='human' else 'PENDING'
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',(ident,'CODEX_EXEC',state,deps,None,None,1,'{}',100))
        self.ledger=ExecutionLedger(self.db,['owner/repo'],clock=lambda:self.now)
        for ident in ('one','two','human'):
            self.ledger.register_spec(ident,{'repo':'owner/repo','type':'CODEX_EXEC','prompt':'approved test task','heavy':True,'timeout_seconds':60,'base_sha':'a'*40},'owner',True)
        self.calls=[]

    def tearDown(self):
        self.temp.cleanup()

    def state(self, ident):
        with sqlite3.connect(self.db) as db:
            return db.execute('SELECT state FROM tasks WHERE id=?',(ident,)).fetchone()[0]

    def test_complete_and_automatically_dispatch_next_dependency(self):
        outer=self
        class Pipeline:
            def run(self, claim):
                outer.calls.append(claim['task_id'])
                outer.ledger.finish(claim['task_id'],claim['worker_id'],claim['fence'],'DONE',effects='known')
                return {'state':'DONE','production_pass':False}
        loop=DevelopmentLoop(self.ledger,lambda _:Pipeline(),'test',max_workers=1,executor=InlineExecutor())
        self.assertEqual(loop.tick()['dispatched'],1)
        self.assertEqual(self.calls,['one'])
        self.assertEqual(loop.tick()['dispatched'],1)
        self.assertEqual(self.calls,['one','two'])
        loop.tick()
        self.assertEqual(self.state('human'),'WAITING_HUMAN')
        self.assertEqual(loop.tick()['active'],0)
        loop.close()

    def test_ci_wait_continues_same_lease_and_checkpoint(self):
        outer=self
        class Pipeline:
            def run(self, claim):
                outer.calls.append(claim)
                if len(outer.calls)==1:
                    cp={'phase':'CI_WAIT'}
                    outer.ledger.checkpoint(claim['task_id'],claim['worker_id'],claim['fence'],cp)
                    return {'state':'RUNNING','checkpoint':cp}
                outer.ledger.finish(claim['task_id'],claim['worker_id'],claim['fence'],'DONE',effects='known')
                return {'state':'DONE'}
        loop=DevelopmentLoop(self.ledger,lambda _:Pipeline(),'test',max_workers=1,clock=lambda:self.now,executor=InlineExecutor())
        loop.tick();loop.tick()
        self.assertEqual(len(self.calls),1)
        self.now+=6;loop.tick()
        self.assertEqual(self.calls[0]['fence'],self.calls[1]['fence'])
        self.assertEqual(self.calls[1]['checkpoint'],{'phase':'CI_WAIT'})
        loop.close()

    def test_exception_quarantines_one_task_and_independent_work_continues(self):
        class Pipeline:
            def run(self, claim):
                raise RuntimeError('sensitive exception must not persist')
        loop=DevelopmentLoop(self.ledger,lambda _:Pipeline(),'test',max_workers=1,executor=InlineExecutor())
        loop.tick();loop.tick()
        self.assertEqual(self.state('one'),'WAITING_HUMAN')
        self.assertEqual(self.state('two'),'PENDING')
        loop.close()

    def test_unpersisted_done_is_quarantined_and_dependency_stays_pending(self):
        class Pipeline:
            def run(self, claim):
                return {'state': 'DONE'}
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                               max_workers=1, executor=InlineExecutor())
        self.addCleanup(loop.close)
        loop.tick()
        loop.tick()
        observed = self.ledger.observation('one')
        self.assertEqual(observed['state'], 'WAITING_HUMAN')
        self.assertEqual(observed['checkpoint']['error_code'], 'PIPELINE_RESULT_UNCONFIRMED')
        self.assertEqual(self.state('two'), 'PENDING')
        self.assertEqual(loop.active, {})

    def test_unpersisted_running_checkpoint_never_becomes_continuation(self):
        outer = self
        class Pipeline:
            def run(self, claim):
                outer.calls.append(claim)
                return {'state': 'RUNNING', 'checkpoint': {'phase': 'CI_WAIT'}}
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                               max_workers=1, clock=lambda: self.now,
                               executor=InlineExecutor())
        self.addCleanup(loop.close)
        loop.tick()
        loop.tick()
        self.now += 20
        loop.tick()
        observed = self.ledger.observation('one')
        self.assertEqual(observed['state'], 'WAITING_HUMAN')
        self.assertNotIn('phase', observed['checkpoint'])
        self.assertEqual(len(self.calls), 1)

    def test_pipeline_error_retains_persisted_external_effect_evidence(self):
        evidence = {'phase': 'IN_FLIGHT_COMMIT', 'workdir': '/isolated/task',
                    'sha': 'a' * 40, 'branch': 'codex/task-a', 'patch_attempts': 2}
        outer = self
        class Pipeline:
            def run(self, claim):
                outer.ledger.checkpoint(claim['task_id'], claim['worker_id'],
                                        claim['fence'], evidence)
                raise RuntimeError('raw diagnostics must not persist')
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                               max_workers=1, executor=InlineExecutor())
        self.addCleanup(loop.close)
        loop.tick()
        loop.tick()
        observed = self.ledger.observation('one')
        self.assertEqual(observed['state'], 'WAITING_HUMAN')
        self.assertEqual(observed['checkpoint'], dict(evidence,
                         error_code='PIPELINE_RESULT_UNCONFIRMED'))
        self.assertNotIn('raw diagnostics', json.dumps(observed))

    def test_factory_failures_have_a_per_tick_attempt_budget(self):
        spec = {'repo': 'owner/repo', 'type': 'CODEX_EXEC', 'prompt': 'approved task',
                'heavy': True, 'timeout_seconds': 60, 'base_sha': 'a' * 40}
        for ident in ('extra1', 'extra2', 'extra3'):
            with sqlite3.connect(self.db) as db:
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                           (ident, 'CODEX_EXEC', 'PENDING', '[]', None, None, 1, '{}', 100))
            self.ledger.register_spec(ident, spec, 'owner', True)
        calls = []
        def factory(claim):
            calls.append(claim['task_id'])
            raise RuntimeError('factory unavailable')
        loop = DevelopmentLoop(self.ledger, factory, 'test', max_workers=2,
                               executor=InlineExecutor())
        self.addCleanup(loop.close)
        self.assertEqual(loop.tick()['dispatched'], 0)
        self.assertEqual(calls, ['extra1', 'extra2'])
        self.assertEqual(self.state('extra1'), 'WAITING_HUMAN')
        self.assertEqual(self.state('extra2'), 'WAITING_HUMAN')
        self.assertEqual(self.state('extra3'), 'PENDING')

    def test_late_future_after_expiry_cannot_finish_or_renew_old_claim(self):
        class Pipeline:
            def run(self, claim):
                raise AssertionError('pending executor must not execute code')
        executor = PendingExecutor()
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                               max_workers=1, clock=lambda: self.now, executor=executor)
        self.addCleanup(loop.close)
        loop.tick()
        old_fence = loop.active['one']['claim']['fence']
        self.now += 181
        self.assertEqual(self.ledger.recover_expired(), ['one'])
        loop.tick()
        executor.futures[0].set_result({'state': 'DONE'})
        loop.tick()
        observed = self.ledger.observation('one')
        self.assertEqual(observed['state'], 'WAITING_HUMAN')
        self.assertEqual(observed['fence'], old_fence + 1)
        self.assertIsNone(observed['lease_until'])
        self.assertNotIn('one', loop.active)
        self.assertEqual(self.state('two'), 'PENDING')

    def test_stop_and_new_loop_do_not_reclaim_live_or_expired_uncertain_work(self):
        class Pipeline:
            def run(self, claim):
                raise AssertionError('pending executor must not execute code')
        first_executor = PendingExecutor()
        first = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                                max_workers=1, clock=lambda: self.now,
                                executor=first_executor)
        self.addCleanup(first.close)
        first.tick()
        fence = first.active['one']['claim']['fence']
        first.stop()
        self.assertTrue(first.tick()['stopping'])
        second_executor = PendingExecutor()
        restarted = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                                    max_workers=1, clock=lambda: self.now,
                                    executor=second_executor)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.tick()['dispatched'], 0)
        self.assertEqual(self.ledger.observation('one')['fence'], fence)
        self.now += 181
        self.assertEqual(restarted.tick()['dispatched'], 0)
        self.assertEqual(self.state('one'), 'WAITING_HUMAN')
        self.assertEqual(second_executor.futures, [])

    def test_protected_checkpoint_is_quarantined_without_blocking_independent_work(self):
        spec = {'repo': 'owner/repo', 'type': 'CODEX_EXEC', 'prompt': 'approved task',
                'heavy': True, 'timeout_seconds': 60, 'base_sha': 'a' * 40}
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                       ('zzready', 'CODEX_EXEC', 'PENDING', '[]', None, None, 1, '{}', 100))
        self.ledger.register_spec('zzready', spec, 'owner', True)
        outer = self
        class Pipeline:
            def run(self, claim):
                ids = (claim['task_id'], claim['worker_id'], claim['fence'])
                if claim['task_id'] == 'one':
                    cp = {'phase': 'CI_WAIT', 'workdir': '/isolated/task',
                          'secret': 'dummy-protected-canary'}
                    outer.ledger.checkpoint(*(ids + (cp,)))
                    return {'state': 'RUNNING', 'checkpoint': cp}
                outer.ledger.finish(*(ids + ('DONE',)), effects='known')
                return {'state': 'DONE'}
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                               max_workers=1, executor=InlineExecutor())
        self.addCleanup(loop.close)
        loop.tick()
        self.assertEqual(loop.tick()['dispatched'], 1)
        self.assertEqual(self.state('one'), 'WAITING_HUMAN')
        self.assertEqual(self.state('zzready'), 'DONE')
        self.assertEqual(self.state('two'), 'PENDING')
        with sqlite3.connect(self.db) as db:
            cp = json.loads(db.execute('SELECT checkpoint FROM tasks WHERE id=?',
                                       ('one',)).fetchone()[0])
        self.assertEqual(cp['workdir'], '/isolated/task')

    def test_nonconforming_phase_cannot_crash_scheduler_heartbeat(self):
        outer = self
        class Pipeline:
            def run(self, claim):
                cp = {'phase': 'CI-WAIT'}
                outer.ledger.checkpoint(claim['task_id'], claim['worker_id'],
                                        claim['fence'], cp)
                return {'state': 'RUNNING', 'checkpoint': cp}
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test',
                               max_workers=1, clock=lambda: self.now,
                               executor=InlineExecutor())
        self.addCleanup(loop.close)
        loop.tick()
        for invalid_phase in ('CI-WAIT', '123', '_CI'):
            with self.subTest(phase=invalid_phase):
                claim = loop.active['one']['claim']
                cp = {'phase': invalid_phase}
                self.ledger.checkpoint(claim['task_id'], claim['worker_id'], claim['fence'], cp)
                future = Future()
                future.set_result({'state': 'RUNNING', 'checkpoint': cp})
                loop.active['one']['future'] = future
                self.assertEqual(loop.tick()['active'], 1)
                self.assertEqual(self.state('one'), 'RUNNING')
                with sqlite3.connect(self.db) as db:
                    phase = db.execute('SELECT phase FROM worker_heartbeats WHERE task_id=?',
                                       ('one',)).fetchone()[0]
                self.assertEqual(phase, 'EXECUTING')

    def test_two_real_threads_dispatch_without_waiting_for_pipeline_turns(self):
        spec = {'repo': 'owner/repo', 'type': 'CODEX_EXEC', 'prompt': 'approved task',
                'heavy': True, 'timeout_seconds': 60, 'base_sha': 'a' * 40}
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                       ('zzready', 'CODEX_EXEC', 'PENDING', '[]', None, None, 1, '{}', 100))
        self.ledger.register_spec('zzready', spec, 'owner', True)
        started = {'one': threading.Event(), 'zzready': threading.Event()}
        release = threading.Event()
        outer = self
        class Pipeline:
            def run(self, claim):
                started[claim['task_id']].set()
                if not release.wait(timeout=5):
                    raise RuntimeError('test synchronization timeout')
                outer.ledger.finish(claim['task_id'], claim['worker_id'],
                                    claim['fence'], 'DONE', effects='known')
                return {'state': 'DONE'}
        loop = DevelopmentLoop(self.ledger, lambda _: Pipeline(), 'test', max_workers=2)
        try:
            self.assertEqual(loop.tick()['dispatched'], 2)
            self.assertTrue(started['one'].wait(timeout=1))
            self.assertTrue(started['zzready'].wait(timeout=1))
            self.assertTrue(all(not entry['future'].done() for entry in loop.active.values()))
            self.assertEqual(self.state('two'), 'PENDING')
        finally:
            release.set()
            loop.close()
            loop.pool.shutdown(wait=True)
        self.assertEqual(self.state('one'), 'DONE')
        self.assertEqual(self.state('zzready'), 'DONE')


if __name__=='__main__':unittest.main()
