"""Actual source-only backup readback at REVOKING; never asserts COMPLETE."""
import json,unittest
from unittest.mock import patch
import backup_component_hostcycle as component
import test_mcp_acceptance_backup_preflight_delta as fixture
from reusable_task_gateway import TestOnlyExecutor
from task_writer_fence import Fence

class RevokingBackupReadback(unittest.TestCase):
    def setUp(self):
        self.f=fixture.TerminalPreflightDelta();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.h=self.f.f.h;task=self.h.supervisor._task('demo-b')
        artifact=self.f.db.execute('SELECT artifact_sha256 FROM delivery_candidates WHERE candidate_id=?',(self.f.candidate,)).fetchone()[0]
        with patch.object(Fence,'invalidate_source_resources',side_effect=RuntimeError('stop')):
            with self.assertRaisesRegex(RuntimeError,'stop'):
                TestOnlyExecutor(self.h.gateway,self.h.fence,self.h.context).complete_success('demo-b','attempt-b',artifact,json.loads(task['completion_json']))
        self.assertEqual(self.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
    def test_real_source_readback_outside_transaction_but_accept_still_held(self):
        original=component.BackupComponent._readback;seen=[]
        def readback(obj,*args):
            self.assertFalse(self.f.db.in_transaction);seen.append(True);return original(obj,*args)
        with patch.object(component.BackupComponent,'_readback',new=readback):
            with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE_ATTEMPT_REQUIRED'):self.f.f.call(self.f.candidate)
        self.assertEqual(seen,[True]);self.assertEqual(self.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(self.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
    def assert_no_readback(self):
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaises(ValueError):self.f.f.call(self.f.candidate)
            self.assertFalse(readback.called)
        self.assertEqual(self.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(self.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
    def test_missing_drain_blocks_readback(self):
        self.f.db.execute("DELETE FROM revocation_drains WHERE task_id='demo-b'");self.f.db.commit();self.assert_no_readback()
    def test_changed_checkpoint_blocks_readback(self):
        self.f.db.execute("UPDATE gateway_checkpoints SET effects_state='UNKNOWN' WHERE task_id='demo-b'");self.f.db.commit();self.assert_no_readback()
    def test_unknown_writer_effect_blocks_readback(self):
        self.f.db.execute("INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",('fixture-unknown','demo-b','attempt-b','fixture-event','fake:demo-b','a'*64,'b'*64,'{}','UNKNOWN',1,1));self.f.db.commit();self.assert_no_readback()
        self.assertEqual(self.f.db.execute("SELECT state FROM writer_operations WHERE operation_id='fixture-unknown'").fetchone()[0],'UNKNOWN')
    def test_changed_existing_invalidation_receipt_blocks_readback(self):
        self.h.fence.invalidate_source_resources('demo-b','terminal-release')
        self.f.db.execute("UPDATE resource_invalidation_receipts SET receipt_json='{}' WHERE task_id='demo-b'");self.f.db.commit();self.assert_no_readback()
    def test_revoked_acceptor_blocks_readback(self):
        self.f.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");self.f.db.commit();self.assert_no_readback()
    def test_role_change_during_readback_does_not_complete(self):
        original=component.BackupComponent._readback;seen=[]
        def revoke(obj,*args):
            value=original(obj,*args)
            self.f.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");self.f.db.commit();seen.append(True)
            return value
        with patch.object(component.BackupComponent,'_readback',new=revoke):
            with self.assertRaisesRegex(ValueError,'CURRENT_HOST_LIFECYCLE_ROLE_REQUIRED'):self.f.f.call(self.f.candidate)
        self.assertEqual(seen,[True]);self.assertEqual(self.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(self.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
    def test_valid_original_receipt_is_reused_without_mutation(self):
        self.h.fence.invalidate_source_resources('demo-b','terminal-release')
        before=self.f.db.execute("SELECT receipt_json,receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()
        original=component.BackupComponent._readback;seen=[]
        def readback(obj,*args):seen.append(True);return original(obj,*args)
        with patch.object(component.BackupComponent,'_readback',new=readback):
            with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE_ATTEMPT_REQUIRED'):self.f.f.call(self.f.candidate)
        after=self.f.db.execute("SELECT receipt_json,receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()
        self.assertEqual(seen,[True]);self.assertEqual(tuple(before),tuple(after))
        self.assertEqual(self.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
