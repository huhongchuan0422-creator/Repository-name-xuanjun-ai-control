"""Phase sequencing tests use only synthetic in-memory state."""
import copy
import json
import unittest
import epoch7_delta as d
import epoch7_injected_recovery as r
import epoch7_additive_identity as a
from test_epoch7_injected_recovery import prepared
from test_epoch7_additive_identity import additive_fixture
from test_epoch7_delta import h


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.s, self.c, self.ops, self.verifier, self.gate, self.payloads = prepared()
        self.attempt = r.BoundJournal(r.ATTEMPT, self.gate, self.ops)
        self.attempt.create({'stage': 'ADMITTED'})
        r.RetainedTargetDelta(self.gate, self.attempt, self.ops).apply(self.payloads)
        self.step = r.GenerationAccessStep(self.gate, self.attempt, self.ops)
        self.calls = 0
        def chmod(before, after):
            self.calls += 1
            state = json.loads(self.ops.journals[self.step.journal.name]['data'].decode())['state']
            self.assertEqual(state['stage'], 'GENERATION_ACCESS_INTENT')
            self.assertEqual(self.attempt.state['stage'], 'GENERATION_ACCESS_INTENT')
            self.assertEqual(before, self.ops.snapshot['generation'])
            self.ops.snapshot['generation'] = copy.deepcopy(after)
            if self.ops.fail == 'chmod_uncertain': raise OSError('CHMOD_UNCERTAIN')
            if self.ops.fail == 'wrong_inode': self.ops.snapshot['generation']['ino'] += 1
            return copy.deepcopy(self.ops.snapshot['generation'])
        self.ops.chmod_generation_exact = chmod

    def test_generation_exact_receipt_then_gate_accepts_new_mode(self):
        preserved = copy.deepcopy(self.ops.preserved)
        result = self.step.apply(); self.gate.check()
        self.assertEqual(result['generation_mode'], 0o700)
        self.assertEqual(self.attempt.state['stage'], 'GENERATION_ACCESS_COMPLETE')
        self.assertEqual(self.ops.preserved, preserved)
        self.assertEqual(self.calls, 1)

    def test_generation_cannot_run_twice(self):
        self.step.apply()
        with self.assertRaisesRegex(ValueError, 'EXACT_PHASE'): self.step.apply()
        self.assertEqual(self.calls, 1)

    def test_uncertain_chmod_keeps_intent_and_cannot_retry(self):
        self.ops.fail = 'chmod_uncertain'
        with self.assertRaises(OSError): self.step.apply()
        self.assertEqual(self.step.journal.state['stage'], 'GENERATION_ACCESS_INTENT')
        with self.assertRaisesRegex(ValueError, 'EXACT_PHASE'): self.step.apply()
        self.assertEqual(self.calls, 1)

    def test_wrong_post_inode_never_done(self):
        self.ops.fail = 'wrong_inode'
        with self.assertRaises(ValueError): self.step.apply()
        self.assertEqual(self.step.journal.state['stage'], 'GENERATION_ACCESS_INTENT')

    def test_denied_review_prevents_chmod(self):
        self.verifier.reject = True
        with self.assertRaisesRegex(ValueError, 'REVIEW_DENIED'): self.step.apply()
        self.assertEqual(self.calls, 0)

    def test_existing_generation_journal_not_reset(self):
        self.ops.journals[self.step.journal.name] = self.ops.record(b'old intent')
        with self.assertRaisesRegex(ValueError, 'ALREADY_ATTEMPTED'): self.step.apply()
        self.assertEqual(self.calls, 0)


class IdentityPhaseTests(unittest.TestCase):
    def setUp(self):
        config, manifest, unit, interpreter, absence = additive_fixture()
        self.raw = d.canonical(config) + b'\n'
        addition = a.compile_addition(self.raw, a.raw_sha(self.raw), manifest, a.raw_sha(manifest),
                                     unit, interpreter, absence)
        s, c, self.ops, self.verifier, unused, payloads = prepared()
        c['manifest_sha256'] = a.raw_sha(manifest); c['activation']['release_sha256'] = a.raw_sha(manifest)
        c['targets'][a.UNIT]['sha256'] = a.raw_sha(unit); payloads[a.UNIT] = unit
        self.observed = None; self.calls = 0
        self.ops.read_additive_absence = lambda path: copy.deepcopy(absence)
        self.ops.read_additive_target = lambda path: copy.deepcopy(self.observed)
        self.gate = r.RecoveryGate(s, c, d.digest(s), h('kit'), h('security'), 7000000000,
            self.verifier, self.ops, self.ops.prior_provision_bytes, additive_delta=addition)
        self.ops.preserved = copy.deepcopy(self.gate.preserved)
        self.attempt = r.BoundJournal(r.ATTEMPT, self.gate, self.ops)
        self.attempt.create({'stage': 'ADMITTED'})
        r.RetainedTargetDelta(self.gate, self.attempt, self.ops).apply(payloads)
        self.step = r.OwnerIdentityPublication(self.gate, self.attempt, self.ops)
        def publish(before, raw, after):
            self.calls += 1
            self.assertEqual(self.step.journal.state['stage'], 'ADDITIVE_PUBLICATION_INTENT')
            self.assertEqual(self.attempt.state['stage'], 'ADDITIVE_PUBLICATION_INTENT')
            self.observed = dict(after, dev=1, ino=999, nlink=1)
            if self.ops.fail == 'publication_uncertain': raise OSError('PUBLICATION_UNCERTAIN')
            if self.ops.fail == 'wrong_links': self.observed['nlink'] = 2
            return copy.deepcopy(self.observed)
        self.ops.publish_additive_exact = publish

    def test_exact_reviewed_owner_publication_updates_live_gate(self):
        self.step.apply(self.raw); self.gate.check()
        self.assertEqual(self.attempt.state['stage'], 'IDENTITY_PUBLISHED')
        self.assertIn(a.PATH, self.attempt.state['identity_receipts'])
        self.assertEqual(self.calls, 1)

    def test_wrong_bytes_rejected_before_publication_intent(self):
        with self.assertRaisesRegex(ValueError, 'APPROVED_BYTES'): self.step.apply(self.raw + b' ')
        self.assertEqual(self.calls, 0)
        self.assertNotIn(self.step.journal.name, self.ops.journals)

    def test_uncertain_publication_cannot_retry(self):
        self.ops.fail = 'publication_uncertain'
        with self.assertRaises(OSError): self.step.apply(self.raw)
        self.assertEqual(self.step.journal.state['stage'], 'ADDITIVE_PUBLICATION_INTENT')
        with self.assertRaisesRegex(ValueError, 'EXACT_PHASE'): self.step.apply(self.raw)
        self.assertEqual(self.calls, 1)

    def test_two_link_result_never_done(self):
        self.ops.fail = 'wrong_links'
        with self.assertRaises(ValueError): self.step.apply(self.raw)
        self.assertEqual(self.step.journal.state['stage'], 'ADDITIVE_PUBLICATION_INTENT')

    def test_published_pin_drift_denies_gate(self):
        self.step.apply(self.raw); self.observed['sha256'] = h('changed')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_TARGET_DRIFT'): self.gate.check()

    def test_new_wrapper_cannot_repeat_publication(self):
        self.step.apply(self.raw)
        with self.assertRaisesRegex(ValueError, 'ALREADY_PUBLISHED'):
            r.OwnerIdentityPublication(self.gate, self.attempt, self.ops).apply(self.raw)
