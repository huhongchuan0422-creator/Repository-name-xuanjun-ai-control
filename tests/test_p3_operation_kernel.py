import os
import sqlite3
import tempfile
import threading
import unittest
from src.p3_operation_kernel import MIGRATION, OperationKernel

IDENTITY = dict(task_id='task', spec_hash='a'*64, artifact='artifact', run_id='run', session_id='session', attempt_id='attempt', lease_id='lease', fence=1, epoch=1, generation=1, resume_generation=1)

class Policy:
    def verify_adapter(self, declaration, identity, admission):
        return declaration == 'fixture-only'
    def verify_receipt(self, evidence, declaration, operation_id, digest, identity):
        return isinstance(evidence, dict) and evidence.get('auth') == (operation_id, digest)

class Adapter:
    def __init__(self):
        self.calls = 0
        self.fail = False
    def identity(self):
        return 'fixture-only'
    def invoke(self, operation_id, digest, identity, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError('effect unknown')
        return dict(auth=(operation_id,digest), outcome='SUCCEEDED', correlation='fixture')
    def reconcile(self, operation_id, digest, identity):
        return dict(auth=(operation_id,digest), outcome='SUCCEEDED', correlation='fixture')

class OperationTests(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile(delete=False)
        self.path = f.name
        f.close()
        db = self.connect()
        db.execute(MIGRATION)
        db.commit()
        db.close()
        self.adapter = Adapter()
        self.kernel = OperationKernel(self.connect, self.adapter, Policy(), enabled=True)
    def tearDown(self):
        os.unlink(self.path)
    def connect(self):
        return sqlite3.connect(self.path, timeout=10)
    def test_concurrent_replay_calls_adapter_at_most_once(self):
        barrier = threading.Barrier(12)
        errors = []
        def run():
            try:
                barrier.wait()
                self.kernel.invoke('id', IDENTITY, dict(IDENTITY), {'event':'one'})
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=run) for _ in range(12)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual([], errors)
        self.assertEqual(1, self.adapter.calls)
        self.assertEqual('SUCCEEDED', self.kernel._row('id')['state'])
    def test_unknown_no_redial_and_reconcile_after_reopen(self):
        self.adapter.fail = True
        first = self.kernel.invoke('id', IDENTITY, dict(IDENTITY), {})
        self.assertEqual('UNKNOWN', first['state'])
        new = OperationKernel(self.connect, self.adapter, Policy(), enabled=True)
        self.assertEqual('UNKNOWN', new.invoke('id', IDENTITY, dict(IDENTITY), {})['state'])
        self.assertEqual(1, self.adapter.calls)
        self.assertEqual('SUCCEEDED', new.reconcile('id')['state'])
        self.assertEqual(1, self.adapter.calls)
    def test_crash_after_running_does_not_redial(self):
        created, row = self.kernel.reserve('id', IDENTITY, dict(IDENTITY), {})
        self.assertTrue(created)
        self.assertTrue(self.kernel._transition('id', 'RESERVED', 'RUNNING'))
        self.assertEqual('RUNNING', self.kernel.invoke('id', IDENTITY, dict(IDENTITY), {})['state'])
        self.assertEqual(0, self.adapter.calls)
        self.assertEqual('SUCCEEDED', self.kernel.reconcile('id')['state'])
    def test_conflicts_and_missing_lease_fail_before_adapter(self):
        self.kernel.reserve('id', IDENTITY, dict(IDENTITY), {})
        with self.assertRaises(ValueError): self.kernel.reserve('id', IDENTITY, dict(IDENTITY), {'different': True})
        with self.assertRaises(ValueError): self.kernel.reserve('other', IDENTITY, dict(IDENTITY), {})
        admission = dict(IDENTITY)
        del admission['lease_id']
        with self.assertRaises(PermissionError): self.kernel.invoke('another', IDENTITY, admission, {})
        self.assertEqual(0, self.adapter.calls)
    def test_untrusted_and_default_off(self):
        with self.assertRaises(PermissionError): OperationKernel(self.connect, self.adapter, Policy())
        self.adapter.identity = lambda: 'forged'
        with self.assertRaises(PermissionError): self.kernel.invoke('id', IDENTITY, dict(IDENTITY), {})
        self.assertEqual(0, self.adapter.calls)
        self.assertIsNone(self.kernel._row('id'))
    def test_untrusted_receipt_is_unknown(self):
        self.adapter.invoke = lambda *args: dict(outcome='SUCCEEDED', correlation='fake')
        self.assertEqual('UNKNOWN', self.kernel.invoke('id', IDENTITY, dict(IDENTITY), {})['state'])
        self.adapter.reconcile = lambda *args: dict(outcome='SUCCEEDED', correlation='fake')
        self.assertEqual('UNKNOWN', self.kernel.reconcile('id')['state'])
