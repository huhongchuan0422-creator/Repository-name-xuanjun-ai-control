"""Per-HandoffHost lifecycle root with a reusable authentication adapter."""
import os,tempfile,unittest
from unittest.mock import patch
import test_mcp_acceptance_evidence_delta as fixture
from test_candidate_host_wiring_delta import DelegateHost
from task_center_handoff_host import HandoffHost
from development_authority_release import lifecycle
from task_center_candidate_readback import LifecycleCandidateReadback

class RootIsolation(fixture.AcceptanceEvidence):
    def make_host(self,adapter,root=None):
        return HandoffHost(self.h.supervisor.db,'tenant-mcp','formal-fixture',adapter,
            mcp_config=self.config,role_contract=self.contract,candidate_lifecycle_root=root)
    def prepare(self,root):
        path=os.path.join(root,'bundle')
        with open(path,'wb') as stream:stream.write(self.adapter.content)
        lifecycle(root,'apply',path,{'verified':True})
    def test_a_survives_b_empty_and_unconfigured_in_any_order(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.prepare(a);adapter=DelegateHost(self.adapter)
            blank_before=self.make_host(adapter);first=self.make_host(adapter,a)
            blank_after=self.make_host(adapter);second=self.make_host(adapter,b)
            self.assertIsNone(blank_before.assess_candidate_bundle({}))
            self.assertIsNone(blank_after.assess_candidate_bundle({}))
            self.assertNotIn('_lifecycle_candidate_readback',adapter.__dict__)
            self.host=first;cid=self.make_candidate();self.handoff(cid)
            self.assertEqual(self.call(cid)['state'],'ACCEPTED')
            self.assertTrue(self.call(cid)['duplicate'])
            self.assertEqual(first._lifecycle_candidate_readback.artifacts,os.path.join(a,'artifacts'))
            self.assertEqual(second._lifecycle_candidate_readback.artifacts,os.path.join(b,'artifacts'))
    def test_same_digest_reads_each_own_root_in_reverse_construction_order(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.prepare(a);self.prepare(b);adapter=DelegateHost(self.adapter)
            second=self.make_host(adapter,b);first=self.make_host(adapter,a)
            self.host=first;cid=self.make_candidate();self.handoff(cid)
            roots=[];bindings=[];original=LifecycleCandidateReadback._read
            def trace(reader,db,binding):
                roots.append(reader.artifacts);bindings.append(dict(binding))
                return original(reader,db,binding)
            with patch.object(LifecycleCandidateReadback,'_read',trace):
                self.assertEqual(self.call(cid)['state'],'ACCEPTED')
                self.assertTrue(roots);self.assertEqual(set(roots),{os.path.join(a,'artifacts')})
                result=second.assess_candidate_bundle(bindings[0])
                self.assertEqual(result['candidate_id'],cid)
                self.assertEqual(roots[-1],os.path.join(b,'artifacts'))
            self.assertEqual(second._lifecycle_candidate_readback.artifacts,os.path.join(b,'artifacts'))
    def test_no_root_preserves_original_adapter_callback(self):
        adapter=self.adapter;host=self.make_host(adapter)
        cid=self.make_candidate();self.handoff(cid);self.host=host
        self.assertEqual(self.call(cid)['state'],'ACCEPTED')
