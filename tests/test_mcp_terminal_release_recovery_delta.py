"""Original TEST_ONLY recovery after revocation; never asserts backup COMPLETE."""
import unittest
from unittest.mock import patch
import test_mcp_completion as fixture
from reusable_task_gateway import GatewayKernel

class ReleaseRecovery(unittest.TestCase):
    def setUp(self):
        self.f=fixture.CompletionTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.cid=self.f.reviewed();self.a=self.f.facade('acceptor');self.args=self.f.args(candidate_id=self.cid)
        with patch.object(GatewayKernel,'release_revoked_resources',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):self.a.call('task_accept_candidate',self.args)
        self.db=self.f.f.supervisor.db
    def test_interrupted_release_reconciles_then_accepts(self):
        self.assertEqual(self.f.f.supervisor._task('demo-b')['authority_state'],'REVOKED')
        self.assertEqual(self.a.call('task_accept_candidate',self.args)['state'],'ACCEPTED')
        self.assertEqual(self.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],1)
        self.assertTrue(self.a.call('task_accept_candidate',self.args)['duplicate'])
    def test_changed_receipt_rejects_without_release(self):
        self.db.execute("UPDATE resource_invalidation_receipts SET receipt_json='{}' WHERE task_id='demo-b'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_RESOURCE_RELEASE_RECONCILIATION'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],0)
    def test_disabled_role_rejects_without_release(self):
        self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='acceptor'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'CURRENT_HOST_LIFECYCLE_ROLE_REQUIRED'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],0)
    def test_repeated_interruption_preserves_receipts_and_can_resume(self):
        before=self.db.execute("SELECT receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchall()
        with patch.object(GatewayKernel,'release_revoked_resources',side_effect=RuntimeError('again')):
            with self.assertRaisesRegex(RuntimeError,'again'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b'").fetchall(),before)
        self.assertEqual(self.a.call('task_accept_candidate',self.args)['state'],'ACCEPTED')
    def test_changed_checkpoint_rejects_without_release(self):
        self.db.execute("UPDATE gateway_checkpoints SET effects_state='UNKNOWN' WHERE task_id='demo-b'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_RESOURCE_RELEASE_RECONCILIATION'):self.a.call('task_accept_candidate',self.args)
        self.assertEqual(self.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],0)
