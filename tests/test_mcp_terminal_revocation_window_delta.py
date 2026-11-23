"""Reproduce live-writer resolver invalidation; no COMPLETE evidence fabricated."""
import json
from unittest.mock import patch
import backup_component_hostcycle as component
from test_mcp_acceptance_backup_preflight_delta import TerminalPreflightDelta
from reusable_task_gateway import TestOnlyExecutor

class TerminalRevocationWindow(TerminalPreflightDelta):
    def test_original_terminal_revokes_resolver_before_acceptance(self):
        from task_center_mcp_completion import CandidateAcceptanceEvidence
        binding={'project_id':'project-mcp','principal_id':'acceptor','role_id':'acceptor',
                 'role_version':'v1','phase':'ACCEPTOR','review_kind':None,
                 'task_id':'demo-b','attempt_id':'attempt-b','candidate_id':self.candidate}
        plan=CandidateAcceptanceEvidence(self.f.h.control,self.host).check(binding,prepare_only=True)
        backup_binding=plan['backup_binding']
        self.component.plan(backup_binding)
        h=self.f.h; task=h.supervisor._task('demo-b')
        artifact=self.db.execute('SELECT artifact_sha256 FROM delivery_candidates WHERE candidate_id=?',(self.candidate,)).fetchone()[0]
        TestOnlyExecutor(h.gateway,h.fence,h.context).complete_success('demo-b','attempt-b',artifact,json.loads(task['completion_json']))
        task=h.supervisor._task('demo-b')
        self.assertEqual((task['state'],task['authority_state']),('SUCCESS','REVOKED'))
        with self.assertRaisesRegex(ValueError,'CURRENT_FENCED_WRITER_REQUIRED'):
            self.component.plan(backup_binding)
        self.assertEqual(self.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.candidate,)).fetchone()[0],'REVIEW_PASSED')

    def _release(self):
        h=self.f.h;task=h.supervisor._task('demo-b')
        artifact=self.db.execute('SELECT artifact_sha256 FROM delivery_candidates WHERE candidate_id=?',(self.candidate,)).fetchone()[0]
        TestOnlyExecutor(h.gateway,h.fence,h.context).complete_success('demo-b','attempt-b',artifact,json.loads(task['completion_json']))

    def test_released_retry_reads_real_source_and_still_holds_incomplete(self):
        self._release()
        original=component.BackupComponent._readback;seen=[]
        def readback(obj,*args):
            self.assertFalse(self.db.in_transaction);seen.append(True);return original(obj,*args)
        with patch.object(component.BackupComponent,'_readback',new=readback):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):
                self.f.call(self.candidate)
        self.assertEqual(seen,[True])
        self.assertEqual(self.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.candidate,)).fetchone()[0],'REVIEW_PASSED')

    def test_released_retry_rejects_lost_release_receipt_before_readback(self):
        self._release();self.db.execute("DELETE FROM gateway_resource_releases WHERE task_id='demo-b'");self.db.commit()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):
                self.f.call(self.candidate)
            self.assertFalse(readback.called)
        self.assertEqual(self.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.candidate,)).fetchone()[0],'REVIEW_PASSED')

    def test_release_receipt_removed_during_readback_is_rechecked(self):
        self._release();original=component.BackupComponent._readback;seen=[]
        def remove_receipt(obj,*args):
            result=original(obj,*args)
            self.db.execute("DELETE FROM gateway_resource_releases WHERE task_id='demo-b'");self.db.commit()
            seen.append(True);return result
        with patch.object(component.BackupComponent,'_readback',new=remove_receipt):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):
                self.f.call(self.candidate)
        self.assertEqual(seen,[True])
        self.assertEqual(self.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(self.candidate,)).fetchone()[0],'REVIEW_PASSED')
