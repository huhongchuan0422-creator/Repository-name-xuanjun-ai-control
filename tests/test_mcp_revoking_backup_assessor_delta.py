"""Observe real SOURCE-only prepared assessment; never manufacture COMPLETE."""
import unittest
from unittest.mock import patch
import test_mcp_revoking_backup_readback_delta as fixture
from task_center_backup_bridge_v2 import PreparedBackupAssessment

class RevokingPreparedAssessment(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RevokingBackupReadback();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_original_prepared_assessor_runs_under_transaction_and_holds(self):
        original=PreparedBackupAssessment.__call__;seen=[]
        def observe(assessor,binding):
            result=original(assessor,binding);seen.append((assessor.db.in_transaction,result['state']))
            return result
        with patch.object(PreparedBackupAssessment,'__call__',new=observe):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):
                self.f.f.f.call(self.f.f.candidate)
        self.assertEqual(seen,[(True,'INCOMPLETE')]);self.assertEqual(self.f.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(self.f.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
    def test_checkpoint_removed_during_readback_fails_assessor_without_revocation(self):
        import backup_component_hostcycle as component
        original=component.BackupComponent._readback;seen=[]
        def remove(obj,*args):
            value=original(obj,*args);self.f.f.db.execute("DELETE FROM gateway_checkpoints WHERE task_id='demo-b'");self.f.f.db.commit();seen.append(True);return value
        assessed=[];assessor_original=PreparedBackupAssessment.__call__
        def assess(assessor,binding):
            result=assessor_original(assessor,binding);assessed.append((assessor.db.in_transaction,result['state']));return result
        with patch.object(component.BackupComponent,'_readback',new=remove),patch.object(PreparedBackupAssessment,'__call__',new=assess):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.f.f.call(self.f.f.candidate)
        self.assertEqual(assessed,[(True,'UNKNOWN')]);self.assertEqual(seen,[True]);self.assertEqual(self.f.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(self.f.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
    def test_producer_record_changed_during_readback_fails_assessor(self):
        import json
        import backup_component_hostcycle as component
        original=component.BackupComponent._readback;record=self.f.f.component.cyclepath(self.f.f.ref['backup_cycle_id'])/'record.json';seen=[]
        def change(obj,*args):
            value=original(obj,*args);data=json.loads(record.read_text());data['result']='0'*40;record.write_text(json.dumps(data));seen.append(True);return value
        assessed=[];assessor_original=PreparedBackupAssessment.__call__
        def assess(assessor,binding):
            result=assessor_original(assessor,binding);assessed.append((assessor.db.in_transaction,result['state']));return result
        with patch.object(component.BackupComponent,'_readback',new=change),patch.object(PreparedBackupAssessment,'__call__',new=assess):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.f.f.call(self.f.f.candidate)
        self.assertEqual(assessed,[(True,'UNKNOWN')]);self.assertEqual(seen,[True]);self.assertEqual(self.f.h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(self.f.f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.f.f.candidate,)).fetchone()[0],'REVIEW_PASSED')
