"""Thin invocation contract tests only; no production FDs or B/C hooks."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from scripts import community_preview_carrier_handoff_admission as h
from scripts import community_preview_carrier_handoff_call as call

class OriginalEntryCall(unittest.TestCase):
    def context(self, authority=True):
        return SimpleNamespace(
            host_id=h.HOST,
            authority_check=lambda: authority,
            parent_fd=11,journal_fd=12,entry_fd=13,lease_fd=14,uid=0,
            parent_identity=[1,2,3,0,0],
            journal_identity=[1,4,3,0,0,2],
            entry_identity=[1,5,0o100600,0,0,1,10,1,1],
            lock_identity=[1,6,0o100600,0,0,1,10,1,1],
            history_refs={'fixture':'not-used'},
            old_archive_bytes=b'fixed-old-fixture',
            new_archive_bytes=b'fixed-new-fixture',
            attempt='isolated-attempt-0001')

    def test_missing_context_is_hold(self):
        with self.assertRaisesRegex(h.Hold,'ORIGINAL_ENTRY_CONTEXT_INCOMPLETE'):
            call.invoke(object(),'status')

    def test_unproven_original_authority_is_hold_before_archive_read(self):
        with patch.object(h,'members') as members:
            with self.assertRaisesRegex(h.Hold,'ORIGINAL_ENTRY_AUTHORITY_NOT_PROVEN'):
                call.invoke(self.context(False),'status')
            members.assert_not_called()

    def test_fixed_status_call_uses_only_passed_original_capabilities(self):
        ctx=self.context()
        old={'manifest.json':b'old'};new={'manifest.json':b'new'}
        with patch.object(h,'members',side_effect=[old,new]),patch.object(h,'status',return_value={'state':'UNKNOWN_INSPECT_ONLY','retry_safe':False}) as status:
            result=call.reconcile_from_original_entry(ctx)
        self.assertEqual(result['state'],'UNKNOWN_INSPECT_ONLY')
        self.assertEqual(status.call_args.args,(11,12,13,14,0,old,new,
            ctx.parent_identity,ctx.journal_identity,ctx.entry_identity,ctx.lock_identity,ctx.history_refs))

    def test_execute_result_unknown_is_not_accepted_or_retried(self):
        ctx=self.context();old={'manifest.json':b'old'};new={'manifest.json':b'new'}
        with patch.object(h,'members',side_effect=[old,new]),patch.object(h,'execute',return_value={'state':'UNKNOWN_INSPECT_ONLY','retry_safe':False}) as execute:
            with self.assertRaisesRegex(h.Hold,'HANDOFF_RESULT_NOT_ACCEPTED_INSPECT_ONLY'):
                call.call_once_from_original_entry(ctx)
            self.assertEqual(execute.call_count,1)

    def test_wrong_host_is_hold(self):
        ctx=self.context();ctx.host_id='other-host'
        with self.assertRaisesRegex(h.Hold,'FIXED_HOST_IDENTITY_MISMATCH'):
            call.invoke(ctx,'status')

if __name__=='__main__':
    unittest.main()
