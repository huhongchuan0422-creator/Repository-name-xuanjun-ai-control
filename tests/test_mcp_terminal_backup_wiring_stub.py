"""TEST-ONLY stubbed backup gate; this is not complete backup evidence."""
import unittest
from unittest.mock import patch
import test_mcp_revoking_backup_readback_delta as fixture
from task_center_mcp_completion import CandidateAcceptanceEvidence
from task_center_backup_bridge_v2 import PreparedBackupAssessment

class ExplicitStubWiring(unittest.TestCase):
    def test_revoking_fence_release_accept_with_explicit_stubbed_backup_gate(self):
        f=fixture.RevokingBackupReadback();f.setUp();self.addCleanup(f.doCleanups)
        original=CandidateAcceptanceEvidence.check;assess=PreparedBackupAssessment.__call__;observed=[];transactions=[]
        def watch(obj,binding):
            value=assess(obj,binding);transactions.append((obj.db.in_transaction,value['state']));return value
        def stub_gate(obj,binding,prepare_only=False):
            try:return original(obj,binding,prepare_only=prepare_only)
            except ValueError as e:
                if prepare_only or str(e)!='CANDIDATE_BACKUP_COMPLETE_REQUIRED':raise
                observed.append(obj.control.db.in_transaction)
                return {'scope':'TEST_ONLY_STUB_NOT_COMPLETE_OR_OFFICIAL'}
        with patch.object(PreparedBackupAssessment,'__call__',new=watch),patch.object(CandidateAcceptanceEvidence,'check',new=stub_gate):
            result=f.f.f.call(f.f.candidate)
        self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(f.h.supervisor._task('demo-b')['authority_state'],'REVOKED')
        self.assertGreaterEqual(len(observed),4);self.assertTrue(all(observed))
        self.assertTrue(transactions);self.assertTrue(all(in_tx and state=='INCOMPLETE' for in_tx,state in transactions))
        self.assertEqual(f.f.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],1)
        # The stub is not a valid evidence binding. Original status must not
        # present this isolated wiring exercise as an accepted handoff.
        import json
        from task_center_mcp_dispatch_host import dispatch_rpc
        parent=f.f.f
        request={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'task_candidate_status','arguments':{'task_id':'demo-b','attempt_id':'attempt-b','candidate_id':f.f.candidate}}}
        status=dispatch_rpc(parent.service,parent.identity,parent.config,request,False,role_contract=parent.contract,acceptance_host=parent.host)
        self.assertEqual(json.loads(status['result']['content'][0]['text'])['completion_state'],'HOLD_HANDOFF_EVIDENCE_RECONCILIATION')
    def test_stubbed_retry_after_revoked_before_release(self):
        from reusable_task_gateway import GatewayKernel
        f=fixture.RevokingBackupReadback();f.setUp();self.addCleanup(f.doCleanups)
        original=CandidateAcceptanceEvidence.check;assess=PreparedBackupAssessment.__call__;states=[]
        def watch(obj,binding):
            result=assess(obj,binding);states.append((obj.db.in_transaction,result['state']));return result
        def stub_gate(obj,binding,prepare_only=False):
            try:return original(obj,binding,prepare_only=prepare_only)
            except ValueError as e:
                if prepare_only or str(e)!='CANDIDATE_BACKUP_COMPLETE_REQUIRED':raise
                return {'scope':'TEST_ONLY_STUB_NOT_COMPLETE_OR_OFFICIAL'}
        with patch.object(PreparedBackupAssessment,'__call__',new=watch),patch.object(CandidateAcceptanceEvidence,'check',new=stub_gate):
            with patch.object(GatewayKernel,'release_revoked_resources',side_effect=RuntimeError('isolated-stop')):
                with self.assertRaisesRegex(RuntimeError,'isolated-stop'):f.f.f.call(f.f.candidate)
            self.assertEqual(f.h.supervisor._task('demo-b')['authority_state'],'REVOKED')
            self.assertEqual(f.f.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],0)
            result=f.f.f.call(f.f.candidate)
        self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(f.f.db.execute("SELECT count(*) FROM gateway_resource_releases WHERE task_id='demo-b'").fetchone()[0],1)
        self.assertTrue(states);self.assertTrue(all(in_tx and state=='INCOMPLETE' for in_tx,state in states))
