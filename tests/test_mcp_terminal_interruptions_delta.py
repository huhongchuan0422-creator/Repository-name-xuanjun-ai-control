"""Original local TEST_ONLY terminal interruption inventory; no backup claims."""
import json,unittest
from unittest.mock import patch
import test_mcp_completion as fixture
from reusable_task_gateway import GatewayKernel
from task_supervisor import Supervisor
from task_writer_fence import Fence

class TerminalInterruptions(unittest.TestCase):
    def test_original_checkpoints_and_retry_inventory(self):
        points=[(GatewayKernel,'save_checkpoint'),(Fence,'begin_revocation'),
                (Fence,'drain'),(Fence,'invalidate_source_resources'),
                (Supervisor,'complete_revocation'),(GatewayKernel,'release_revoked_resources')]
        for cls,name in points:
            with self.subTest(interrupted=name):
                f=fixture.CompletionTests();f.setUp()
                try:
                    cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
                    with patch.object(cls,name,side_effect=RuntimeError('isolated-stop')):
                        with self.assertRaisesRegex(RuntimeError,'isolated-stop'):a.call('task_accept_candidate',args)
                    db=f.f.supervisor.db;task=f.f.supervisor._task('demo-b')
                    counts={table:db.execute('SELECT count(*) FROM '+table+" WHERE task_id='demo-b'").fetchone()[0] for table in ('gateway_checkpoints','revocation_drains','resource_invalidation_receipts','gateway_resource_releases')}
                    self.assertEqual(task['state'],'SUCCESS')
                    expected={
                        'save_checkpoint':('VALID',(0,0,0,0)),
                        'begin_revocation':('VALID',(1,0,0,0)),
                        'drain':('REVOKING',(1,0,0,0)),
                        'invalidate_source_resources':('REVOKING',(1,1,0,0)),
                        'complete_revocation':('REVOKING',(1,1,1,0)),
                        'release_revoked_resources':('REVOKED',(1,1,1,0))}
                    self.assertEqual(task['authority_state'],expected[name][0])
                    self.assertEqual(tuple(counts[k] for k in ('gateway_checkpoints','revocation_drains','resource_invalidation_receipts','gateway_resource_releases')),expected[name][1])
                    try:
                        out=a.call('task_accept_candidate',args);retry='result:'+out['state']
                    except Exception as e:retry=type(e).__name__+':'+str(e)
                    print('INTERRUPTION',name,task['state'],task['authority_state'],json.dumps(counts,sort_keys=True),'retry',retry,flush=True)
                    expected_error=('ValueError:HOLD_RESOURCE_RELEASE_RECONCILIATION' if name=='release_revoked_resources' else 'ValueError:CURRENT_CANDIDATE_ATTEMPT_REQUIRED')
                    self.assertEqual(retry,expected_error)
                    self.assertEqual(db.execute('SELECT state FROM delivery_candidates WHERE candidate_id=?',(cid,)).fetchone()[0],'REVIEW_PASSED')
                finally:f.tearDown()
