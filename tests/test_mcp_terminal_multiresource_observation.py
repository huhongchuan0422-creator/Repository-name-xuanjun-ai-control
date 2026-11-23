"""Observe an interrupted two-resource original fence, never production."""
import unittest
from unittest.mock import patch
import test_mcp_completion as fixture
import test_model_orchestration as models
from reusable_task_gateway import TestOnlyExecutor
from task_supervisor import Supervisor

class MultiResourceObservation(unittest.TestCase):
    def test_partial_invalidation_preserves_existing_receipt_and_recovers(self):
        graph=models.demo_graph;start=TestOnlyExecutor.start
        def two_graph(tenant):
            value=graph(tenant);next(t for t in value['tasks'] if t['task_id']=='demo-b')['resources']=['fake:demo-b','fake:extra'];return value
        def two_start(executor,task_id,attempt_id,resources,*args,**kwargs):
            return start(executor,task_id,attempt_id,['fake:demo-b','fake:extra'] if task_id=='demo-b' else resources,*args,**kwargs)
        f=fixture.CompletionTests()
        with patch.object(models,'demo_graph',new=two_graph),patch.object(TestOnlyExecutor,'start',new=two_start):f.setUp()
        self.addCleanup(f.tearDown);cid=f.reviewed();a=f.facade('acceptor');args=f.args(candidate_id=cid)
        original=Supervisor.record_resource_invalidation;calls=[]
        def interrupted(supervisor,task_id,receipt):
            if calls:raise RuntimeError('second-receipt-stop')
            result=original(supervisor,task_id,receipt);calls.append(receipt['resource_key']);return result
        with patch.object(Supervisor,'record_resource_invalidation',new=interrupted):
            with self.assertRaisesRegex(RuntimeError,'second-receipt-stop'):a.call('task_accept_candidate',args)
        db=f.f.supervisor.db;task=f.f.supervisor._task('demo-b')
        rows=db.execute("SELECT resource_key,receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b' ORDER BY resource_key").fetchall()
        self.assertEqual(task['authority_state'],'REVOKING');self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['resource_key'],calls[0]);self.assertFalse(f.f.supervisor.unresolved_operations('demo-b'))
        self.assertEqual(a.call('task_accept_candidate',args)['state'],'ACCEPTED')
        after=db.execute("SELECT resource_key,receipt_sha256 FROM resource_invalidation_receipts WHERE task_id='demo-b' ORDER BY resource_key").fetchall()
        self.assertEqual(len(after),2);self.assertEqual(tuple(after[0]),tuple(rows[0]))
        self.assertEqual(db.execute("SELECT state FROM delivery_candidates WHERE candidate_id=?",(cid,)).fetchone()[0],'ACCEPTED')
        self.assertEqual(f.f.supervisor._task('demo-b')['authority_state'],'REVOKED')
        self.assertTrue(a.call('task_accept_candidate',args)['duplicate'])
