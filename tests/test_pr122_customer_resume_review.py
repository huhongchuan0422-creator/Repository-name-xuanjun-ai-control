"""Independent offline regression checks for stale V2 finalization."""
import copy
import json
import os
import unittest
from unittest.mock import patch

from scripts import pr122_customer_release as release
from scripts import pr122_customer_resume as resume
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_attempts as attempt_tests
from tests import test_pr122_customer_resume as resume_tests


def advanced_ledger(data):
    advanced = copy.deepcopy(data)
    previous = advanced['attempts'][-1]
    if previous['state'] == 'STARTED_UNKNOWN':
        previous.update(state='HOLD_UNKNOWN_OR_PARTIAL',
                        ended_unix=previous['started_unix'])
    number = len(advanced['attempts']) + 1
    advanced['attempts'].append({
        'number': number,
        'attempt_id': advanced['binding']['transaction'] + '-%02d' % number,
        'previous_sha256': digest(canonical(previous)),
        'state': 'STARTED_UNKNOWN',
    })
    return advanced


class FinalizationReviewTests(unittest.TestCase):
    def test_stale_attempt_finish_preserves_advanced_durable_ledger(self):
        fixture = attempt_tests.AttemptsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        attempt = fixture.new()
        advanced = advanced_ledger(attempt.data)
        attempt.path.write_bytes(canonical(advanced))
        with self.assertRaisesRegex(Denied, 'ATTEMPT_FENCE_LOST'):
            attempt.finish('HOLD_UNKNOWN_OR_PARTIAL')
        self.assertEqual(json.loads(attempt.path.read_bytes()), advanced)


class ReconciliationReviewTests(unittest.TestCase):
    setUp = resume_tests.ResumeTests.setUp
    fake_run = resume_tests.ResumeTests.fake_run
    inventory = resume_tests.ResumeTests.inventory
    patches = resume_tests.ResumeTests.patches
    receipt = resume_tests.ResumeTests.receipt
    ledger = resume_tests.ResumeTests.ledger

    def test_replaced_shared_lock_cannot_consume_next_attempt(self):
        def fail_smoke(args):
            if args[0] == '/usr/bin/curl':
                return release.CommandFailure(args, 7, b'fixture temporary read failure')
        self.command_failure = fail_smoke
        snapshots = []

        def replace_lock(_seconds):
            snapshots.append((canonical(self.ledger()), canonical(self.receipt())))
            replacement = self.b / 'new-lock'
            replacement.write_bytes(b'')
            os.replace(replacement, release.LOCK)

        with self.patches(), patch.object(resume.time, 'sleep', replace_lock):
            with self.assertRaisesRegex(Denied, 'LOCK_REPLACED'):
                release.apply(self.source, 4)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(canonical(self.ledger()), snapshots[0][0])
        self.assertEqual(canonical(self.receipt()), snapshots[0][1])

    def test_reconcile_proof_cannot_overwrite_newer_durable_attempt(self):
        def fail_smoke(args):
            if args[0] == '/usr/bin/curl':
                return release.CommandFailure(args, 60, b'fixture permanent read failure')
        self.command_failure = fail_smoke
        with self.patches(), self.assertRaises(resume.Stopped):
            release.apply(self.source, 4)
        receipt_path = release.STATE / release.TXN / 'receipt.json'
        ledger_path = release.STATE / (release.TXN + '.attempts.json')
        old_receipt = receipt_path.read_bytes()
        advanced = advanced_ledger(self.ledger())
        original_reconcile = resume.Journal.reconcile
        injected = []

        def replace_ledger_after_proof(journal):
            original_reconcile(journal)
            if not injected:
                injected.append(True)
                ledger_path.write_bytes(canonical(advanced))

        self.command_failure = None
        with self.patches(), patch.object(resume.Journal, 'reconcile',
                                         replace_ledger_after_proof):
            with self.assertRaisesRegex(Denied, 'FENCE|RECONCILE'):
                release.apply(self.source, 4)
        self.assertEqual(injected, [True])
        self.assertEqual(self.ledger(), advanced)
        self.assertEqual(receipt_path.read_bytes(), old_receipt)


if __name__ == '__main__':
    unittest.main()
