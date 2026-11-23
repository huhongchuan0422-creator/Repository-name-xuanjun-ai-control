"""Isolated original terminal retry; no real provider or handoff COMPLETE."""
import unittest
from unittest.mock import patch
import test_mcp_completion as fixture
from reusable_task_gateway import GatewayKernel
from task_writer_fence import Fence

class ValidRecovery(unittest.TestCase):
    def run_recovery(self,cls,method):
        f=fixture.CompletionTests();f.setUp();self.addCleanup(f.tearDown)
        cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        with patch.object(cls,method,side_effect=RuntimeError('stop')):
            with self.assertRaisesRegex(RuntimeError,'stop'):a.call('task_accept_candidate',args)
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'VALID')
        result=a.call('task_accept_candidate',args)
        self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'REVOKED')
        self.assertEqual(f.f.supervisor.db.execute("SELECT count(*) FROM events WHERE task_id='demo-b' AND event_id='terminal-attempt-b'").fetchone()[0],1)
        self.assertEqual(f.f.supervisor.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],1)
        self.assertTrue(a.call('task_accept_candidate',args)['duplicate'])
    def test_after_terminal_before_checkpoint(self):self.run_recovery(GatewayKernel,'save_checkpoint')
    def test_after_checkpoint_before_revocation(self):self.run_recovery(Fence,'begin_revocation')
    def test_changed_terminal_payload_blocks_recovery(self):
        f=fixture.CompletionTests();f.setUp();self.addCleanup(f.tearDown)
        cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        with patch.object(GatewayKernel,'save_checkpoint',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):a.call('task_accept_candidate',args)
        db=f.f.supervisor.db;db.execute("UPDATE events SET evidence_ref='unrelated' WHERE task_id='demo-b' AND event_id='terminal-attempt-b'");db.commit()
        with self.assertRaisesRegex(ValueError,'TERMINAL_RECOVERY_EVIDENCE_REQUIRED'):a.call('task_accept_candidate',args)
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'VALID')

    def test_unsettled_model_request_blocks_recovery(self):
        f=fixture.CompletionTests();f.setUp();self.addCleanup(f.tearDown)
        cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        with patch.object(GatewayKernel,'save_checkpoint',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):a.call('task_accept_candidate',args)
        f.f.control.queue_request('demo-b','developer',[{'role':'user','content':'isolated'}],'pending-recovery',16)
        with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):a.call('task_accept_candidate',args)
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'VALID')

    def test_changed_checkpoint_blocks_recovery(self):
        f=fixture.CompletionTests();f.setUp();self.addCleanup(f.tearDown)
        cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        with patch.object(Fence,'begin_revocation',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):a.call('task_accept_candidate',args)
        db=f.f.supervisor.db;db.execute("UPDATE gateway_checkpoints SET effects_state='UNKNOWN' WHERE task_id='demo-b'");db.commit()
        with self.assertRaisesRegex(ValueError,'TERMINAL_RECOVERY_CHECKPOINT_CONFLICT'):a.call('task_accept_candidate',args)
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'VALID')

    def test_role_revoked_after_checkpoint_blocks_revocation(self):
        f=fixture.CompletionTests();f.setUp();self.addCleanup(f.tearDown)
        cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        with patch.object(GatewayKernel,'save_checkpoint',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):a.call('task_accept_candidate',args)
        original=GatewayKernel.save_checkpoint
        def change_role(kernel,*args,**kwargs):
            result=original(kernel,*args,**kwargs)
            kernel.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");kernel.db.commit()
            return result
        with patch.object(GatewayKernel,'save_checkpoint',new=change_role):
            with self.assertRaisesRegex(ValueError,'CURRENT_HOST_LIFECYCLE_ROLE_REQUIRED'):a.call('task_accept_candidate',args)
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'VALID')
        self.assertEqual(f.f.supervisor.db.execute("SELECT state FROM delivery_candidates WHERE candidate_id=?",(cid,)).fetchone()[0],'REVIEW_PASSED')

class SourceOnlyRecovery(unittest.TestCase):
    def test_interrupted_source_only_does_not_revoke_or_accept(self):
        import json
        import test_mcp_acceptance_backup_preflight_delta as fixture_backup
        from reusable_task_gateway import TestOnlyExecutor
        f=fixture_backup.TerminalPreflightDelta();f.setUp();self.addCleanup(f.doCleanups)
        h=f.f.h;task=h.supervisor._task('demo-b')
        artifact=f.db.execute('SELECT artifact_sha256 FROM delivery_candidates WHERE candidate_id=?',(f.candidate,)).fetchone()[0]
        with patch.object(GatewayKernel,'save_checkpoint',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):TestOnlyExecutor(h.gateway,h.fence,h.context).complete_success('demo-b','attempt-b',artifact,json.loads(task['completion_json']))
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):f.f.call(f.candidate)
        self.assertEqual(h.supervisor._task('demo-b')['authority_state'],'VALID')
        self.assertEqual(f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(f.candidate,)).fetchone()[0],'REVIEW_PASSED')
