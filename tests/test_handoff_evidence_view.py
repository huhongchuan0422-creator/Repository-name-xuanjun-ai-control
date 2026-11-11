import unittest
from scripts.handoff_evidence_view import PROOFS, handoff_view


def data():
    e = dict(task_id='T1', spec_sha256='a' * 64, checkpoint_sha256='b' * 64,
             commit='c' * 40, artifact_sha256='d' * 64)
    o = dict(e); o.update(dict.fromkeys(PROOFS, True)); o['evidence_sha256'] = 'e' * 64
    return e, o


class HandoffTests(unittest.TestCase):
    def test_proof_never_transfers(self):
        e, o = data(); r = handoff_view(e, o)
        self.assertEqual(r['status'], 'HANDOFF_PROOFS_REPORTED')
        self.assertFalse(r['execution_granted']); self.assertFalse(r['handoff_performed'])

    def test_every_stop_ack_lease_required(self):
        for field in PROOFS:
            for value in (None, False, 1, 'true'):
                e, o = data(); o[field] = value
                self.assertEqual(handoff_view(e, o)['status'], 'HOLD')

    def test_each_binding_exact(self):
        for field in data()[0]:
            e, o = data(); o[field] = 'wrong'
            self.assertEqual(handoff_view(e, o)['status'], 'HOLD')

    def test_missing_evidence(self):
        e, o = data(); o['evidence_sha256'] = None
        self.assertEqual(handoff_view(e, o)['status'], 'HOLD')

    def test_malformed_input(self):
        for o in (None, {}, []):
            self.assertEqual(handoff_view(data()[0], o)['status'], 'HOLD')

    def test_bad_expected(self):
        e, o = data(); e['commit'] = 'bad'
        with self.assertRaises(ValueError): handoff_view(e, o)

    def test_failures_collected(self):
        e, o = data(); o['old_writer_stopped'] = False; o['successor_ack'] = False
        self.assertEqual(len(handoff_view(e, o)['reasons']), 2)
