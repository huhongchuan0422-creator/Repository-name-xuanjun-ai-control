"""Offline provenance adapter cases; no live identity/finance claims."""
import copy
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from single_contract_provenance_adapter import prepare_unsigned
from single_contract_freeze import ContractHold
spec = importlib.util.spec_from_file_location(
    "samples", str(ROOT / "tests/test_single_contract_freeze.py"))
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)
DOMAINS = ("identity", "project", "requirements", "selection", "quote",
           "authorization", "materials", "acceptance", "legal")

def fixture():
    s = samples.sample()
    scope = {key: s[key] for key in ("project_id", "verified_customer_id", "contract_id")}
    e = {}
    for d in DOMAINS:
        version = {"requirements":s["requirements_version"],
                   "quote":s["quote_version"],"acceptance":s["acceptance_version"]}.get(d,"v1")
        digest = {"selection":s["selection_manifest_hash"],
                  "authorization":s["authorization_manifest_hash"],
                  "materials":s["materials_manifest_hash"]}.get(d,"e"*64)
        e[d] = {"scope":copy.deepcopy(scope), "version":version,
                "digest":digest,"source_ref":"trusted-fixture-"+d,
                "verified_by_trusted_adapter":True}
    return scope,s,e

class ProvenanceTests(unittest.TestCase):
    def test_staging_never_signs_or_pays(self):
        scope,s,e=fixture()
        result=prepare_unsigned(scope,s,e)
        self.assertEqual(result["status"],"UNSIGNED_STAGING_ONLY")
        self.assertEqual(result["candidate"]["status"],"UNSIGNED_CANDIDATE_ONLY")
        self.assertEqual(result["contract_sign"],"HOLD")
        self.assertEqual(result["payment"],"HOLD")
        self.assertEqual(result["procurement"],"HOLD")
        self.assertEqual(result["development_start"],"HOLD")
        self.assertEqual(result,prepare_unsigned(scope,s,e))
    def test_missing_evidence_rejected(self):
        scope,s,e=fixture()
        e.pop("quote")
        with self.assertRaises(ContractHold): prepare_unsigned(scope,s,e)
    def test_untrusted_evidence_rejected(self):
        scope,s,e=fixture()
        e["identity"]["verified_by_trusted_adapter"]=False
        with self.assertRaisesRegex(ContractHold,"PROVENANCE_NOT_VERIFIED"):
            prepare_unsigned(scope,s,e)
    def test_cross_tenant_evidence_rejected(self):
        scope,s,e=fixture()
        e["project"]["scope"]["verified_customer_id"]="other"
        with self.assertRaisesRegex(ContractHold,"PROVENANCE_SCOPE"):
            prepare_unsigned(scope,s,e)
    def test_stale_revision_rejected(self):
        scope,s,e=fixture()
        e["requirements"]["version"]="older"
        with self.assertRaisesRegex(ContractHold,"PROVENANCE_BINDING_MISMATCH"):
            prepare_unsigned(scope,s,e)
    def test_selection_change_rejected(self):
        scope,s,e=fixture()
        s["selection_manifest_hash"]="f"*64
        with self.assertRaisesRegex(ContractHold,"PROVENANCE_BINDING_MISMATCH"):
            prepare_unsigned(scope,s,e)
    def test_client_context_spoof_rejected(self):
        scope,s,e=fixture()
        scope["verified_customer_id"]="other"
        with self.assertRaisesRegex(ContractHold,"CONTEXT_SCOPE_MISMATCH"):
            prepare_unsigned(scope,s,e)

if __name__ == "__main__":
    unittest.main()
