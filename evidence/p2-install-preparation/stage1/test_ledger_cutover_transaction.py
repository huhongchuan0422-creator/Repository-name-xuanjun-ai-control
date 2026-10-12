import json
import fcntl
import os
import tempfile
import unittest
from ledger_cutover_transaction import LedgerCutoverTransaction
from ledger_install_stage import PROOF_KEYS


class Adapter(object):
    def __init__(self): self.calls = []; self.fail = False
    def preflight(self, plan): self.calls.append('preflight'); return True
    def stop_and_inhibit(self, bindings): self.calls.append('stop')
    def measure_quiescence(self, bindings):
        self.calls.append('measure')
        if self.fail: raise RuntimeError('private diagnostic must not be saved')
        return {'proof': {key: True for key in PROOF_KEYS}, 'units': {}}


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = os.path.realpath(self.temp.name)
        self.path = self.root + '/receipt.json'
        self.plan = {'schema':1, 'transaction_id':'p2-once',
                     'source':self.root+'/old.sqlite',
                     'rollback_snapshot':self.root+'/backup.sqlite',
                     'staged_generation':self.root+'/next.sqlite',
                     'repository':'owner/repo', 'legacy_bindings':{}}
        self.adapter = Adapter()

    def read(self):
        with open(self.path) as f: return json.load(f)

    def test_intent_is_durable_before_migration_and_no_replay(self):
        def stage(*args):
            self.assertEqual(self.read()['stage'], 'STAGE_REQUESTED')
            self.assertEqual(self.adapter.calls, ['preflight','stop','measure'])
            return {'status':'STAGED_NOT_ACTIVE'}
        tx = LedgerCutoverTransaction(self.path, self.adapter, stage)
        self.assertEqual(tx.execute(self.plan)['stage'], 'STAGED')
        self.assertFalse(self.read()['activation_executed'])
        with self.assertRaisesRegex(ValueError, 'RECONCILIATION'):
            tx.execute(self.plan)
        self.assertEqual(self.adapter.calls, ['preflight','stop','measure'])

    def test_failed_stop_measurement_never_migrates_or_restarts(self):
        self.adapter.fail = True
        def stage(*args): self.fail('migration after failed proof')
        with self.assertRaises(RuntimeError):
            LedgerCutoverTransaction(self.path,self.adapter,stage).execute(self.plan)
        receipt = self.read()
        self.assertEqual(receipt['stage'], 'HOLD')
        self.assertEqual(receipt['failed_stage'], 'STOP_REQUESTED')
        self.assertNotIn('private', json.dumps(receipt))

    def test_migration_failure_preserves_reconciliation_boundary(self):
        def stage(*args): raise OSError('partial backup')
        with self.assertRaises(OSError):
            LedgerCutoverTransaction(self.path,self.adapter,stage).execute(self.plan)
        self.assertEqual(self.read()['failed_stage'], 'STAGE_REQUESTED')
        self.assertFalse(self.read()['source_replaced'])

    def test_preflight_failure_has_no_stop_or_journal(self):
        self.adapter.preflight = lambda plan: False
        with self.assertRaises(ValueError):
            LedgerCutoverTransaction(self.path,self.adapter).execute(self.plan)
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(self.adapter.calls, [])

    def test_second_writer_cannot_stop_services(self):
        fd = os.open(self.path+'.lock', os.O_RDWR|os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'WRITER_EXISTS'):
                LedgerCutoverTransaction(self.path,self.adapter).execute(self.plan)
            self.assertEqual(self.adapter.calls, [])
        finally: os.close(fd)


if __name__ == '__main__': unittest.main()
