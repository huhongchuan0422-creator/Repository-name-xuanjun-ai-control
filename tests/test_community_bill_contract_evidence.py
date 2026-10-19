"""Offline, non-authorizing checks for the unresolved community bill evidence index."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/development/COMMUNITY_BILL_CONTRACT_EVIDENCE.json"
REQUIRED = {
    "BILL_TIMEZONE",
    "BILL_DATE_MEMBERSHIP_RULE",
    "SUMMARY_AMOUNT_SEMANTICS",
    "RETURN_DETAIL_JOIN_UNVERIFIED",
    "UNFREEZE_DETAIL_JOIN_UNVERIFIED",
    "PROVIDER_POPULATION_COMPLETENESS",
    "LOCAL_SIGNED_DETAIL_EVIDENCE_COMPLETENESS",
}
FIELDS = {
    "id", "domain", "status", "code_references",
    "proven_by_current_evidence", "not_proven_by_current_evidence",
    "required_provider_fields_or_rules", "owner_role",
    "test_references", "closure_conditions",
}


class CommunityBillContractEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(INDEX.read_text(encoding="utf-8"))

    def test_unique_ids_and_complete_missing_contract_coverage(self):
        entries = self.doc["evidence"]
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), REQUIRED)
        self.assertEqual(self.doc["schema_version"], 1)
        for entry in entries:
            self.assertEqual(set(entry), FIELDS)
            self.assertEqual(entry["status"], "OPEN_UNVERIFIED")
            self.assertIn(entry["domain"], {"PROVIDER", "LOCAL"})
            self.assertTrue(entry["proven_by_current_evidence"])
            self.assertTrue(entry["not_proven_by_current_evidence"])
            self.assertTrue(entry["owner_role"])
            for field in ("required_provider_fields_or_rules", "closure_conditions",
                          "code_references", "test_references"):
                self.assertTrue(entry[field], (entry["id"], field))
                self.assertTrue(all(bool(value) for value in entry[field]))

    def test_referenced_paths_symbols_markers_and_test_names_exist(self):
        trees = {}
        for entry in self.doc["evidence"]:
            for ref in entry["code_references"]:
                self.assertEqual(set(ref), {"path", "symbol", "marker"})
                path = ROOT / ref["path"]
                self.assertTrue(path.is_file(), ref)
                source = path.read_text(encoding="utf-8")
                self.assertIn(ref["marker"], source, ref)
                if path not in trees:
                    trees[path] = ast.parse(source, filename=str(path))
                symbol = ref["symbol"].split(".")
                nodes = trees[path].body
                for part in symbol:
                    candidates = [node for node in nodes
                                  if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                                       ast.AsyncFunctionDef))
                                  and node.name == part]
                    self.assertEqual(len(candidates), 1, ref)
                    nodes = candidates[0].body
            test_files = [
                ROOT / "tests/test_community_provider_bills.py",
                ROOT / "tests/test_community_merchant_bills.py",
            ]
            known = set()
            for path in test_files:
                self.assertTrue(path.is_file(), path)
                tree = ast.parse(path.read_text(encoding="utf-8"))
                known.update(n.name for n in ast.walk(tree)
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and n.name.startswith("test_"))
            for name in entry["test_references"]:
                self.assertIn(name, known, entry["id"])

    def test_provider_and_local_evidence_remain_distinct(self):
        provider = {item["id"] for item in self.doc["evidence"]
                    if item["domain"] == "PROVIDER"}
        local = {item["id"] for item in self.doc["evidence"]
                 if item["domain"] == "LOCAL"}
        self.assertEqual(local, {"LOCAL_SIGNED_DETAIL_EVIDENCE_COMPLETENESS"})
        self.assertEqual(provider, REQUIRED - local)
        self.assertFalse(self.doc["enforced_boundaries"]
                         ["local_configured_stores_are_provider_population"])
        self.assertFalse(self.doc["enforced_boundaries"]
                         ["files_or_links_establish_verification"])
        self.assertIn("cannot prove provider population",
                      self.doc["source_separation"]["local"])

    def test_no_finance_or_funds_promotion(self):
        boundary = self.doc["enforced_boundaries"]
        self.assertEqual(self.doc["overall_state"], "OPEN_UNVERIFIED")
        self.assertIs(boundary["complete_reconciliation_available"], False)
        self.assertEqual(boundary["finance_status"], "UNCONFIRMED")
        self.assertIs(boundary["funds_retry_authorized"], False)
        provider = (ROOT / "scripts/community_provider_bills.py").read_text()
        merchant = (ROOT / "scripts/community_merchant_bills.py").read_text()
        for marker in ("COMPLETE_SPLIT_BILL_RECONCILIATION_UNAVAILABLE",
                       "funds_retry_authorized=False",
                       "finance_status='UNCONFIRMED'"):
            self.assertIn(marker, provider)
        for marker in ("COMPLETE_MERCHANT_BILL_RECONCILIATION_UNAVAILABLE",
                       "provider_population_completeness='NOT_ESTABLISHED'",
                       "funds_retry_authorized=False"):
            self.assertIn(marker, merchant)


if __name__ == "__main__":
    unittest.main()
