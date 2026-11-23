"""Read original SOURCE backup before original release; no COMPLETE fixture."""
import json,unittest
from unittest.mock import patch
import backup_component_hostcycle as component
import test_mcp_acceptance_backup_preflight_delta as fixture
from reusable_task_gateway import GatewayKernel,TestOnlyExecutor
from task_center_backup_bridge_v2 import PreparedBackupAssessment

class RevokedUnreleasedBackup(unittest.TestCase):
    def setUp(self):
        self.f=fixture.TerminalPreflightDelta();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.h=self.f.f.h;task=self.h.supervisor._task('demo-b')
        artifact=self.f.db.execute('SELECT artifact_sha256 FROM delivery_candidates WHERE candidate_id=?',(self.f.candidate,)).fetchone()[0]
        with patch.object(GatewayKernel,'release_revoked_resources',side_effect=RuntimeError('stop')):
            with self.assertRaisesRegex(RuntimeError,'stop'):
                TestOnlyExecutor(self.h.gateway,self.h.fence,self.h.context).complete_success('demo-b','attempt-b',artifact,json.loads(task['completion_json']))
        self.assertEqual(self.h.supervisor._task('demo-b')['authority_state'],'REVOKED')
    def assert_not_released(self):
        self.assertEqual(self.f.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],0)
        self.assertEqual(self.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
    def test_real_prepared_source_checked_in_release_transaction_and_held(self):
        readback=component.BackupComponent._readback;assess=PreparedBackupAssessment.__call__;reads=[];checks=[]
        def read(obj,*args):
            self.assertFalse(self.f.db.in_transaction);reads.append(True);return readback(obj,*args)
        def check(obj,binding):
            result=assess(obj,binding);checks.append((obj.db.in_transaction,result['state']));return result
        with patch.object(component.BackupComponent,'_readback',new=read),patch.object(PreparedBackupAssessment,'__call__',new=check):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.f.call(self.f.candidate)
        self.assertEqual(reads,[True]);self.assertEqual(checks,[(True,'INCOMPLETE')]);self.assert_not_released()
    def test_missing_checkpoint_blocks_readback_and_release(self):
        self.f.db.execute("DELETE FROM gateway_checkpoints WHERE task_id='demo-b'");self.f.db.commit()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('no read')) as read:
            with self.assertRaises(ValueError):self.f.f.call(self.f.candidate)
            self.assertFalse(read.called)
        self.assert_not_released()
    def test_receipt_changed_during_readback_rolls_back_release(self):
        original=component.BackupComponent._readback;seen=[]
        def change(obj,*args):
            result=original(obj,*args)
            self.f.db.execute("UPDATE resource_invalidation_receipts SET receipt_json='{}' WHERE task_id='demo-b'");self.f.db.commit();seen.append(True);return result
        with patch.object(component.BackupComponent,'_readback',new=change):
            with self.assertRaisesRegex(ValueError,'HOLD_RESOURCE_RELEASE_RECONCILIATION'):self.f.f.call(self.f.candidate)
        self.assertEqual(seen,[True]);self.assert_not_released()
    def test_unknown_writer_effect_blocks_readback_and_release(self):
        self.f.db.execute("INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",('fixture-unknown','demo-b','attempt-b','fixture-event','fake:demo-b','a'*64,'b'*64,'{}','UNKNOWN',1,1));self.f.db.commit()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('no read')) as read:
            with self.assertRaises(ValueError):self.f.f.call(self.f.candidate)
            self.assertFalse(read.called)
        self.assertEqual(self.f.db.execute("SELECT state FROM writer_operations WHERE operation_id='fixture-unknown'").fetchone()[0],'UNKNOWN');self.assert_not_released()
    def test_changed_revoked_claim_blocks_readback_and_release(self):
        self.f.db.execute("UPDATE resource_claims SET fence=fence+1 WHERE task_id='demo-b'");self.f.db.commit()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('no read')) as read:
            with self.assertRaises(ValueError):self.f.f.call(self.f.candidate)
            self.assertFalse(read.called)
        self.assert_not_released()
