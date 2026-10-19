"""Fail-closed five-attempt operator receipts. Synthetic test, not UK activation."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'production' / 'p2_recovery'))
import attempt_receipt as ar

class Flags:
    isolated = 1
    no_site = 1
    dont_write_bytecode = 1

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, 'receipts')
        os.mkdir(self.root, 0o700)
        self.argv = ['attempt_receipt.py','--root',self.root,'--slot','1',
                     '--attempt-id','p2-real-001','--status','FAILED_RECONCILED',
                     '--command-sha256','a'*64,'--evidence-sha256','b'*64]
    def run_slot(self, slot, status='FAILED_RECONCILED'):
        args = list(self.argv)
        args[args.index('--slot')+1] = str(slot)
        args[args.index('--status')+1] = status
        # TemporaryDirectory ancestry belongs to the invoking user; simulate
        # the owner-only protected tree in this isolated non-production test.
        original_stat = ar.os.fstat
        def stat_as_root(fd):
            value = original_stat(fd)
            fields = list(value)
            fields[stat.ST_UID] = 0
            return os.stat_result(fields)
        with mock.patch.object(ar.os,'getuid',return_value=0), (
             mock.patch.object(ar.os,'geteuid',return_value=0)), (
             mock.patch.object(ar.os,'uname',return_value=(ar.HOST,)*5)), (
             mock.patch.object(ar.os,'fstat',side_effect=stat_as_root)), (
             mock.patch.object(ar.sys,'flags',Flags())), (
             mock.patch.object(ar.sys,'argv',args)):
            ar.main()
    def test_first_and_next_reconciled(self):
        self.run_slot(1)
        self.run_slot(2)
        self.assertTrue(os.path.isfile(os.path.join(self.root,'attempt-2.json')))
    def test_skip_slot_rejected(self):
        with self.assertRaises(FileNotFoundError): self.run_slot(2)
    def test_duplicate_rejected(self):
        self.run_slot(1)
        with self.assertRaises(FileExistsError): self.run_slot(1)
    def test_unknown_prior_blocks_new_attempt(self):
        self.run_slot(1,'UNKNOWN_HOLD')
        with self.assertRaisesRegex(RuntimeError,'PRIOR_ATTEMPT_NOT_RECONCILED'):
            self.run_slot(2)
    def test_success_prior_blocks_new_attempt(self):
        self.run_slot(1,'SUCCEEDED_VERIFIED')
        with self.assertRaisesRegex(RuntimeError,'PRIOR_ATTEMPT_NOT_RECONCILED'):
            self.run_slot(2)
    def test_sixth_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'INVALID_ATTEMPT'):self.run_slot(6)

if __name__=='__main__':
    unittest.main()
