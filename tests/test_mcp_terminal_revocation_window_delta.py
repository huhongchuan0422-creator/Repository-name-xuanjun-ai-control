"""Reproduce live-writer resolver invalidation; no COMPLETE evidence fabricated."""
import json
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
