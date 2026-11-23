"""Local-only multi-resource recovery checks; never real backup/fence evidence."""
import unittest
from unittest.mock import patch
import test_mcp_completion as fixture
import test_model_orchestration as models
from reusable_task_gateway import TestOnlyExecutor
from task_supervisor import Supervisor
from task_writer_fence import SourceResourceAdapter

class RevokingRecovery(unittest.TestCase):
    def setUp(self):
        graph=models.demo_graph;start=TestOnlyExecutor.start
        def two_graph(tenant):
            v=graph(tenant);next(t for t in v['tasks'] if t['task_id']=='demo-b')['resources']=['fake:demo-b','fake:extra'];return v
        def two_start(executor,task_id,attempt_id,resources,*args,**kw):
            return start(executor,task_id,attempt_id,['fake:demo-b','fake:extra'] if task_id=='demo-b' else resources,*args,**kw)
        self.f=fixture.CompletionTests()
        with patch.object(models,'demo_graph',new=two_graph),patch.object(TestOnlyExecutor,'start',new=two_start):self.f.setUp()
        self.addCleanup(self.f.tearDown);self.cid=self.f.reviewed();self.a=self.f.facade('acceptor');self.args=self.f.args(candidate_id=self.cid)
        original=Supervisor.record_resource_invalidation;calls=[]
        def stop_second(supervisor,task_id,receipt):
            if calls:raise RuntimeError('stop-second')
            result=original(supervisor,task_id,receipt);calls.append(receipt['resource_key']);return result
        with patch.object(Supervisor,'record_resource_invalidation',new=stop_second):
            with self.assertRaisesRegex(RuntimeError,'stop-second'):self.a.call('task_accept_candidate',self.args)
        self.db=self.f.f.supervisor.db
        self.original=self.db.execute("SELECT resource_key,receipt_json,receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()
    def test_only_missing_source_fixture_receipt_is_generated(self):
        original=SourceResourceAdapter.invalidation_receipt;seen=[]
        def capture(adapter,supervisor,task_id,key,*args):
            seen.append(key);return original(adapter,supervisor,task_id,key,*args)
        with patch.object(SourceResourceAdapter,'invalidation_receipt',new=capture):
            self.assertEqual(self.a.call('task_accept_candidate',self.args)['state'],'ACCEPTED')
        self.assertEqual(seen,['fake:extra'])
        row=self.db.execute("SELECT resource_key,receipt_json,receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b' AND resource_key=?",(self.original['resource_key'],)).fetchone()
        self.assertEqual(tuple(row),tuple(self.original))
    def test_reinterruption_after_missing_receipt_reuses_both(self):
        with patch.object(Supervisor,'complete_revocation',side_effect=RuntimeError('stop-again')):
            with self.assertRaisesRegex(RuntimeError,'stop-again'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],2)
        with patch.object(SourceResourceAdapter,'invalidation_receipt',side_effect=AssertionError('no receipt replay')):
            self.assertEqual(self.a.call('task_accept_candidate',self.args)['state'],'ACCEPTED')
    def test_changed_prior_receipt_holds_without_new_receipt(self):
        self.db.execute("UPDATE resource_invalidation_receipts SET receipt_json='{}' WHERE task_id='demo-b'");self.db.commit()
        with patch.object(SourceResourceAdapter,'invalidation_receipt',side_effect=AssertionError('no call')):
            with self.assertRaisesRegex(ValueError,'TERMINAL_RECOVERY_RECEIPT_CONFLICT'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],1)
    def test_missing_drain_holds_without_new_receipt(self):
        self.db.execute("DELETE FROM revocation_drains WHERE task_id='demo-b'");self.db.commit()
        with patch.object(SourceResourceAdapter,'invalidation_receipt',side_effect=AssertionError('no call')):
            with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE_ATTEMPT_REQUIRED'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],1)
    def test_disabled_acceptor_holds_without_new_receipt(self):
        self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");self.db.commit()
        with patch.object(SourceResourceAdapter,'invalidation_receipt',side_effect=AssertionError('no call')):
            with self.assertRaisesRegex(ValueError,'CURRENT_HOST_LIFECYCLE_ROLE_REQUIRED'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],1)
    def test_unknown_writer_effect_holds_without_new_receipt(self):
        self.db.execute("INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",('fixture-unknown','demo-b','attempt-b','fixture-event','fake:extra','a'*64,'b'*64,'{}','UNKNOWN',1,1));self.db.commit()
        with patch.object(SourceResourceAdapter,'invalidation_receipt',side_effect=AssertionError('no call')):
            with self.assertRaisesRegex(ValueError,'TERMINAL_RECOVERY_EVIDENCE_REQUIRED'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT state FROM writer_operations WHERE operation_id='fixture-unknown'").fetchone()[0],'UNKNOWN')
        self.assertEqual(self.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],1)

    def test_role_change_during_receipt_generation_rolls_back(self):
        original=SourceResourceAdapter.invalidation_receipt
        def revoke(adapter,supervisor,task_id,key,*args):
            result=original(adapter,supervisor,task_id,key,*args)
            self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");self.db.commit()
            return result
        with patch.object(SourceResourceAdapter,'invalidation_receipt',new=revoke):
            with self.assertRaisesRegex(ValueError,'CURRENT_HOST_LIFECYCLE_ROLE_REQUIRED'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],1)
        self.assertEqual(self.f.f.supervisor._task('demo-b')['authority_state'],'REVOKING')

class EnforcedRecoveryBoundary(unittest.TestCase):
    def test_revoking_does_not_run_source_receipt_recovery(self):
        import json
        import test_mcp_acceptance_backup_preflight_delta as backup_fixture
        from task_writer_fence import Fence
        f=backup_fixture.TerminalPreflightDelta();f.setUp();self.addCleanup(f.doCleanups)
        h=f.f.h;task=h.supervisor._task('demo-b')
        artifact=f.db.execute('SELECT artifact_sha256 FROM delivery_candidates WHERE candidate_id=?',(f.candidate,)).fetchone()[0]
        with patch.object(Fence,'invalidate_source_resources',side_effect=RuntimeError('stop')):
            with self.assertRaisesRegex(RuntimeError,'stop'):
                TestOnlyExecutor(h.gateway,h.fence,h.context).complete_success('demo-b','attempt-b',artifact,json.loads(task['completion_json']))
        with patch.object(SourceResourceAdapter,'invalidation_receipt',side_effect=AssertionError('no recovery')):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):f.f.call(f.candidate)
        self.assertEqual(h.supervisor._task('demo-b')['authority_state'],'REVOKING')
        self.assertEqual(f.db.execute("SELECT count(*) FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchone()[0],0)
        self.assertEqual(f.db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(f.candidate,)).fetchone()[0],'REVIEW_PASSED')
