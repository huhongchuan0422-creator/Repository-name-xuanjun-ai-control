"""Source-only admission negatives. Not production/host acceptance."""
import unittest
from scripts import community_preview_carrier_handoff_admission as h

class HandoffAdmission(unittest.TestCase):
    def test_wrong_installed_old_manifest_holds(self):
        with self.assertRaisesRegex(h.Hold,'OLD_INSTALLED_MANIFEST_UNPROVEN'):
            h.verify_inputs(b'BAD',b'NEW',b'{}')

    def test_live_switch_unqualified_holds(self):
        with self.assertRaisesRegex(h.Hold,'ISOLATED_EXECUTION_IDENTITY_REQUIRED'):
            h.execute(None,None,None,None,None)

    def test_rollback_always_holds(self):
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_OWNERSHIP_NOT_PROVEN'):
            h.rollback()

    def test_status_without_journal_is_not_success(self):
        import os,tempfile
        with tempfile.TemporaryDirectory() as root:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:self.assertEqual(h.status(fd)['state'],'NO_HANDOFF_JOURNAL')
            finally:os.close(fd)

    def test_execute_refuses_unverified_identity_without_writing(self):
        import os,tempfile
        with tempfile.TemporaryDirectory() as root:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:
                with self.assertRaisesRegex(h.Hold,'PARENT_IDENTITY_CHANGED'):
                    h.execute(fd,b'bad',b'bad',[],[],root_uid=os.getuid())
                self.assertFalse(os.listdir(root))
            finally:os.close(fd)

    def test_recovery_missing_or_unknown_journal_holds(self):
        import os,tempfile
        with tempfile.TemporaryDirectory() as root:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:
                with open(os.path.join(root,h.STATE),'wb') as out:out.write(b'{}')
                with self.assertRaisesRegex(h.Hold,'JOURNAL_BINDING_UNKNOWN'):
                    h.status(fd)
            finally:os.close(fd)

    def test_fixed_old_and_new_pins_are_distinct(self):
        self.assertEqual(len(h.OLD_MANIFEST),64)
        self.assertEqual(len(h.NEW_MANIFEST),64)
        self.assertNotEqual(h.OLD_MANIFEST,h.NEW_MANIFEST)
        self.assertNotEqual(h.OLD_ARCHIVE,h.NEW_ARCHIVE)

if __name__=='__main__':
    unittest.main()
