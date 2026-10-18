"""Fail-closed boundary tests for the new versioned native coordinator."""
import unittest
import epoch7_attempt5_native as native

class LedgerForTest(object):
    def __init__(self):
        self.grant = {'grant_id': 'g'}
        self.attempts = []
    def claim(self):
        self.attempts.append({'id':'a', 'state':'CLAIMED'})
        return 'a'
    def intent(self, aid, sha):
        self.attempts[-1]['state'] = 'INTENT_RECORDED'
    def snapshot(self):
        return {'attempts':self.attempts, 'completed':[]}

class TestNative(unittest.TestCase):
    def test_no_trust_provider(self):
        # The original Ledger is required; no test duck type may bypass it.
        with self.assertRaises(native.Hold):
            native.NativeAttemptCoordinator(LedgerForTest(),
                 tuple('p%02d' % n for n in range(16))).claim('a'*64)
    def test_phase_order(self):
        self.assertRaises(native.Hold, native.check, False, 'PHASE_ORDER')
    def test_unknown_denied(self):
        self.assertRaises(native.Hold, native.check, None, 'UNKNOWN')
    def test_missing_fence_denied(self):
        self.assertRaises(native.Hold, native.check, False, 'FENCE_UNKNOWN')

if __name__ == '__main__':
    unittest.main()
