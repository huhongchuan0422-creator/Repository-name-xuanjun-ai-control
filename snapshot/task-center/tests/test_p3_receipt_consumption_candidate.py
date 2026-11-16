import os
import sqlite3
import threading
import unittest
from test_development_authority import DevelopmentAuthorityTests
from p3_receipt_consumption_candidate import install_candidate_schema, consume_verified_receipt_candidate


class P3ConsumptionTests(DevelopmentAuthorityTests):
    def setUp(self):
        super().setUp()
        db=sqlite3.connect(self.path)
        install_candidate_schema(db); db.commit(); db.close()
        self.request={'task_id':'task-1','request_id':'request-1','service_id':'reader-1',
                      'purpose':'AUTHORIZATION_CONSUME','target_sha256':'d'*64}
        self.assignment={k:self.expected[k] for k in ('attempt_id','lease_id','fence','epoch','resource_scope_digest')}

    def consume(self, nonce='nonce', digest='e'*64, assignment=None):
        db=sqlite3.connect(self.path,timeout=5); db.row_factory=sqlite3.Row
        try:
            consume_verified_receipt_candidate(db,nonce=nonce,receipt_sha256=digest,
                request=self.request,trust=self.trust,assignment=assignment or self.assignment,now=1002.0)
        finally: db.close()

    def test_concurrent_real_sqlite_single_winner_and_persistence(self):
        barrier=threading.Barrier(8); results=[]; lock=threading.Lock()
        def run():
            barrier.wait()
            try: self.consume(); outcome='won'
            except ValueError as e: outcome=str(e)
            with lock: results.append(outcome)
        threads=[threading.Thread(target=run) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(results.count('won'),1)
        self.assertEqual(results.count('RECEIPT_ALREADY_CONSUMED'),7)
        with self.assertRaisesRegex(ValueError,'ALREADY_CONSUMED'): self.consume('other')
        with self.assertRaisesRegex(ValueError,'ALREADY_CONSUMED'): self.consume(digest='f'*64)

    def test_fence_and_revocation_fail_without_consuming(self):
        wrong=dict(self.assignment,fence=999)
        with self.assertRaisesRegex(ValueError,'ASSIGNMENT_MISMATCH'): self.consume(assignment=wrong)
        db=sqlite3.connect(self.path)
        db.execute("UPDATE tasks SET authority_state='REVOKED' WHERE task_id='task-1'"); db.commit(); db.close()
        with self.assertRaisesRegex(ValueError,'AUTHORITY_NOT_VALID'): self.consume()
        db=sqlite3.connect(self.path)
        self.assertEqual(db.execute('SELECT count(*) FROM p3_consumed_receipts_candidate').fetchone()[0],0); db.close()


def _process_consume(path, request, trust, assignment, gate, results):
    db=sqlite3.connect(path,timeout=10); db.row_factory=sqlite3.Row
    gate.wait()
    try:
        consume_verified_receipt_candidate(db,nonce='shared',receipt_sha256='e'*64,
            request=request,trust=trust,assignment=assignment,now=1002.0)
        results.put('won')
    except Exception as exc:
        results.put(type(exc).__name__+':'+str(exc))
    finally: db.close()


def _crash_after_insert(path, request, trust, assignment):
    db=sqlite3.connect(path,timeout=10); db.row_factory=sqlite3.Row
    db.create_function('crash_now',0,lambda:os._exit(73))
    consume_verified_receipt_candidate(db,nonce='crash',receipt_sha256='a'*64,
        request=request,trust=trust,assignment=assignment,now=1002.0)
    os._exit(74)


class P3ProcessRecoveryTests(P3ConsumptionTests):
    def test_process_competition_and_digest_across_nonces(self):
        import multiprocessing as mp
        ctx=mp.get_context('fork'); gate=ctx.Event(); results=ctx.Queue()
        procs=[ctx.Process(target=_process_consume,args=(self.path,self.request,self.trust,self.assignment,gate,results)) for _ in range(8)]
        for p in procs:p.start()
        gate.set()
        for p in procs:p.join(15)
        try:
            self.assertTrue(all(not p.is_alive() and p.exitcode==0 for p in procs))
            outcomes=[results.get(timeout=2) for _ in procs]
            self.assertEqual(outcomes.count('won'),1)
            self.assertEqual(outcomes.count('ValueError:RECEIPT_ALREADY_CONSUMED'),7)
            with self.assertRaisesRegex(ValueError,'RECEIPT_ALREADY_CONSUMED'):
                self.consume(nonce='different',digest='e'*64)
            with sqlite3.connect(self.path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM p3_consumed_receipts_candidate').fetchone()[0],1)
        finally:
            for p in procs:
                if p.is_alive():p.terminate();p.join()
            results.close()

    def test_process_crash_mid_transaction_and_recovery(self):
        import multiprocessing as mp
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TRIGGER crash_candidate AFTER INSERT ON p3_consumed_receipts_candidate BEGIN SELECT crash_now(); END')
        p=mp.get_context('fork').Process(target=_crash_after_insert,args=(self.path,self.request,self.trust,self.assignment))
        p.start(); p.join(15)
        if p.is_alive():p.terminate();p.join();self.fail('crash process stuck')
        self.assertEqual(p.exitcode,73)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT count(*) FROM p3_consumed_receipts_candidate').fetchone()[0],0)
            db.execute('DROP TRIGGER crash_candidate')
        self.consume(nonce='crash',digest='a'*64)
        with self.assertRaisesRegex(ValueError,'RECEIPT_ALREADY_CONSUMED'):
            self.consume(nonce='again',digest='a'*64)

    def test_wrong_task_lease_fence_rollback(self):
        original=self.request
        self.request=dict(original,task_id='nonexistent')
        with self.assertRaises(KeyError):self.consume()
        self.request=original
        for field in ('lease_id','fence','attempt_id','epoch','resource_scope_digest'):
            wrong=dict(self.assignment); wrong[field]=999 if field in ('fence','epoch') else 'wrong'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'ASSIGNMENT_MISMATCH'):
                self.consume(assignment=wrong)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM p3_consumed_receipts_candidate').fetchone()[0],0)
        self.consume()
