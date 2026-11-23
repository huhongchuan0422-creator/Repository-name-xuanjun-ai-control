"""Checkpoint must survive until the original revocation transaction."""
import unittest
from unittest.mock import patch
import test_mcp_completion as fixture
from reusable_task_gateway import GatewayKernel
from task_writer_fence import Fence

class CheckpointRace(unittest.TestCase):
    def run_race(self,first_checkpoint,mutation):
        f=fixture.CompletionTests();f.setUp();self.addCleanup(f.tearDown)
        cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        cls,method=(Fence,'begin_revocation') if first_checkpoint else (GatewayKernel,'save_checkpoint')
        with patch.object(cls,method,side_effect=RuntimeError('stop')):
            with self.assertRaisesRegex(RuntimeError,'stop'):a.call('task_accept_candidate',args)
        db=f.f.supervisor.db;original=Fence.begin_revocation;seen=[]
        def race(fence,task_id,controller,admission_check=None):
            if mutation=='delete':db.execute("DELETE FROM gateway_checkpoints WHERE task_id=?",(task_id,))
            else:db.execute("UPDATE gateway_checkpoints SET effects_state='UNKNOWN' WHERE task_id=?",(task_id,))
            db.commit();seen.append(True)
            return original(fence,task_id,controller,admission_check=admission_check)
        with patch.object(Fence,'begin_revocation',new=race):
            with self.assertRaisesRegex(ValueError,'TERMINAL_RECOVERY_CHECKPOINT_(MISSING|CONFLICT)'):
                a.call('task_accept_candidate',args)
        self.assertEqual(seen,[True]);self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'VALID')
        self.assertEqual(db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(cid,)).fetchone()[0],'REVIEW_PASSED')
        self.assertEqual(db.execute("SELECT count(*) FROM revocation_drains WHERE task_id='demo-b'").fetchone()[0],0)
    def test_new_checkpoint_deleted(self):self.run_race(False,'delete')
    def test_existing_checkpoint_deleted(self):self.run_race(True,'delete')
    def test_existing_checkpoint_changed(self):self.run_race(True,'change')
