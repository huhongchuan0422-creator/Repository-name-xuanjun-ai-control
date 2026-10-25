"""Fixed in-process entry admission tests. No UK host, no B/C."""
import unittest
from unittest.mock import patch
from scripts import community_preview_carrier_handoff_admission as h
from scripts import community_preview_carrier_handoff_entry as entry

class FixedEntry(unittest.TestCase):
    def test_unknown_action_holds_before_identity_or_io(self):
        with patch.object(entry,'identify_admin') as identity:
            with self.assertRaisesRegex(h.Hold,'HANDOFF_OPERATION_DENIED'):
                entry.run('owner-bc',lambda *args:True,b'old',b'new')
            identity.assert_not_called()

    def test_absent_authority_holds_before_archive_read(self):
        with patch.object(entry,'identify_admin',return_value=1008),patch.object(h,'members') as members:
            with self.assertRaisesRegex(h.Hold,'CURRENT_INSTALL_WRITER_APPROVAL_REQUIRED'):
                entry.run('execute',lambda *args:False,b'old',b'new')
            members.assert_not_called()

    def test_authority_called_once_and_rejected_from_original_host(self):
        seen=[]
        def approve(*args):
            seen.append(args)
            return False
        with patch.object(entry,'identify_admin',return_value=1008):
            with self.assertRaisesRegex(h.Hold,'CURRENT_INSTALL_WRITER_APPROVAL_REQUIRED'):
                entry.run('rollback',approve,b'old',b'new')
        self.assertEqual(seen,[('rollback',h.HOST,entry.ATTEMPT)])

    def test_host_identity_denied(self):
        with patch.object(entry.os,'geteuid',return_value=0),patch.object(entry.os,'uname') as u:
            u.return_value.nodename='NOT_THE_FIXED_HOST'
            with self.assertRaisesRegex(h.Hold,'FIXED_UK_HOST_AND_ROOT_REQUIRED'):
                entry.identify_admin()

    def test_exact_archive_pins_checked_before_parent_open(self):
        with patch.object(entry,'identify_admin',return_value=1008):
            with patch.object(entry,'_protected_path_directory') as open_parent:
                with self.assertRaisesRegex(h.Hold,'CANDIDATE_ARCHIVE_SHA'):
                    entry.run('status',lambda *args:True,b'not-the-old-archive',b'not-the-new-archive')
                open_parent.assert_not_called()

if __name__=='__main__':unittest.main()
