"""Source-only admission negatives. Not production/host acceptance."""
import unittest
from scripts import community_preview_carrier_handoff_admission as h

class HandoffAdmission(unittest.TestCase):
    def test_wrong_installed_old_manifest_holds(self):
        with self.assertRaisesRegex(h.Hold,'OLD_INSTALLED_MANIFEST_UNPROVEN'):
            h.verify_inputs(b'BAD',b'NEW',b'{}')

    def test_live_switch_always_holds(self):
        with self.assertRaisesRegex(h.Hold,'LIVE_HANDOFF_NOT_AUTHORIZED_OR_IMPLEMENTED'):
            h.execute()

    def test_rollback_always_holds(self):
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_OWNERSHIP_NOT_PROVEN'):
            h.rollback()

    def test_fixed_old_and_new_pins_are_distinct(self):
        self.assertEqual(len(h.OLD_MANIFEST),64)
        self.assertEqual(len(h.NEW_MANIFEST),64)
        self.assertNotEqual(h.OLD_MANIFEST,h.NEW_MANIFEST)
        self.assertNotEqual(h.OLD_ARCHIVE,h.NEW_ARCHIVE)

if __name__=='__main__':
    unittest.main()
