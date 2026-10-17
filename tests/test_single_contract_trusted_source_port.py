"""Source-port offline tests; no production connector or authority claims."""
import copy
import importlib.util
import pathlib
import sys
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from single_contract_freeze import ContractHold
from single_contract_trusted_source_port import TrustedContractSource, stage_from_trusted_source
spec=importlib.util.spec_from_file_location("fixture",str(ROOT/"tests/test_single_contract_provenance_adapter.py"))
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

class FakeSource(TrustedContractSource):
    def __init__(self):
        self.scope,self.snapshot,self.evidence=fixture.fixture()
        self.actor="actor-one";self.rev="rev-one";self.allow=True;self.calls=0
    def read_consistent(self, actor, project, contract):
        self.calls+=1
        return {"actor":self.actor,"revision":self.rev,"scope":copy.deepcopy(self.scope),
                "snapshot":copy.deepcopy(self.snapshot),"evidence":copy.deepcopy(self.evidence)}
    def revalidate_revision(self, actor, project, contract, revision):
        self.calls+=1
        return self.allow and revision==self.rev and actor==self.actor

class SourcePortTests(unittest.TestCase):
    def test_staging_holds_and_deterministic_record(self):
        p=FakeSource();out=stage_from_trusted_source(p,"actor-one","prj1","contract1")
        self.assertEqual(out["status"],"OFFLINE_STAGING_HOLD")
        self.assertEqual(out["staging"]["status"],"UNSIGNED_STAGING_ONLY")
        self.assertEqual(out["contract_sign"],"HOLD")
        self.assertEqual(out["payment"],"HOLD")
        self.assertEqual(out["procurement"],"HOLD")
    def test_untrusted_dictionary_not_a_provider(self):
        with self.assertRaisesRegex(ContractHold,"TRUSTED_SOURCE_REQUIRED"):
            stage_from_trusted_source({},"actor-one","prj1","contract1")
    def test_wrong_actor_denied(self):
        with self.assertRaisesRegex(ContractHold,"SOURCE_ACTOR_OR_REVISION_INVALID"):
            stage_from_trusted_source(FakeSource(),"actor-two","prj1","contract1")
    def test_wrong_project_denied(self):
        with self.assertRaisesRegex(ContractHold,"SOURCE_SCOPE_MISMATCH"):
            stage_from_trusted_source(FakeSource(),"actor-one","other","contract1")
    def test_revocation_between_reads_fails(self):
        p=FakeSource();p.allow=False
        with self.assertRaisesRegex(ContractHold,"SOURCE_REVISION_REVOKED"):
            stage_from_trusted_source(p,"actor-one","prj1","contract1")
        self.assertEqual(p.calls,2)
    def test_modified_quote_evidence_rejected(self):
        p=FakeSource();p.evidence["quote"]["version"]="stale"
        with self.assertRaisesRegex(ContractHold,"PROVENANCE_BINDING_MISMATCH"):
            stage_from_trusted_source(p,"actor-one","prj1","contract1")

if __name__=="__main__":
    unittest.main()
