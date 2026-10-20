"""Offline, non-authorizing checks for the unresolved community bill evidence index."""
import ast
import copy
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
    "id", "category", "status", "source_refs", "existing_evidence",
    "required_delivery", "responsible_role", "dependencies",
    "existing_tests", "closure_conditions",
}


class CommunityBillContractEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(INDEX.read_text(encoding="utf-8"))

    def test_unique_ids_and_complete_missing_contract_coverage(self):
        self.validate_contract(self.doc)
        entries = self.doc["requirements"]
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), REQUIRED)
        self.assertEqual(self.doc["schema_version"], 1)
        for entry in entries:
            self.assertEqual(set(entry), FIELDS)
            self.assertEqual(entry["status"], "OPEN_UNVERIFIED")
            self.assertIn(entry["category"], {"PROVIDER_CONTRACT", "LOCAL_EVIDENCE"})
            self.assertTrue(entry["existing_evidence"]["proves"])
            self.assertTrue(entry["existing_evidence"]["does_not_prove"])
            self.assertTrue(entry["responsible_role"])
            for field in ("required_delivery", "closure_conditions",
                          "source_refs", "existing_tests", "dependencies"):
                self.assertTrue(entry[field], (entry["id"], field))
                self.assertTrue(all(bool(value) for value in entry[field]))

    @staticmethod
    def validate_contract(doc):
        if doc.get("baseline_commit") != "98067fd25154c95e2ea3c63dcc26fe086f180709":
            raise ValueError("INVALID_BASELINE")
        if "evidence" in doc or type(doc.get("requirements")) is not list:
            raise ValueError("INVALID_REQUIREMENTS_KEY")
        entries = doc["requirements"]
        if len(entries) != len(REQUIRED) or {x["id"] for x in entries} != REQUIRED:
            raise ValueError("INVALID_REQUIREMENTS")
        for entry in entries:
            if set(entry) != FIELDS or entry["status"] != "OPEN_UNVERIFIED":
                raise ValueError("INVALID_ENTRY")
            refs = entry["source_refs"]
            sources = entry["existing_evidence"]["sources"]
            if not refs or not sources or { (x["path"], x["symbol"]) for x in sources } != {
                    (x["path"], x["symbol"]) for x in refs}:
                raise ValueError("INVALID_SOURCE_PROVENANCE")
            for ref in refs:
                path = ROOT / ref["path"]
                if (ref["path"] not in {"scripts/community_provider_bills.py",
                                       "scripts/community_merchant_bills.py"}
                        or not path.is_file()
                        or ref["marker"] != ref["reason_code_or_field"]):
                    raise ValueError("INVALID_SOURCE_REFERENCE")
                source = path.read_text(encoding="utf-8")
                nodes = ast.parse(source, filename=str(path)).body
                target = None
                for name in ref["symbol"].split("."):
                    found = [node for node in nodes
                             if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                                  ast.AsyncFunctionDef)) and node.name == name]
                    if len(found) != 1:
                        raise ValueError("INVALID_SYMBOL")
                    target = found[0]
                    nodes = target.body
                lines = source.splitlines(keepends=True)
                segment = "".join(lines[target.lineno - 1: target.end_lineno])
                if ref["marker"] not in segment:
                    raise ValueError("INVALID_SYMBOL_MARKER_BINDING")
            known = set()
            for name in ("test_community_provider_bills.py", "test_community_merchant_bills.py"):
                tree = ast.parse((ROOT / "tests" / name).read_text(encoding="utf-8"))
                known.update(n.name for n in ast.walk(tree)
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and n.name.startswith("test_"))
            if not entry["existing_tests"] or not set(entry["existing_tests"]) <= known:
                raise ValueError("INVALID_EXISTING_TESTS")

    def test_referenced_paths_symbols_markers_and_test_names_exist(self):
        self.validate_contract(self.doc)

    def test_invalid_baseline_provenance_and_marker_bindings_rejected(self):
        def rejected(mutator):
            candidate = copy.deepcopy(self.doc)
            mutator(candidate)
            with self.assertRaises(ValueError):
                self.validate_contract(candidate)

        rejected(lambda d: d.__setitem__("baseline_commit", "0" * 40))
        rejected(lambda d: d["requirements"][0]["existing_evidence"]["sources"][0].__setitem__(
            "path", "scripts/nonexistent.py"))
        rejected(lambda d: d["requirements"][0]["existing_evidence"]["sources"][0].__setitem__(
            "symbol", "nonexistent"))
        rejected(lambda d: d["requirements"][0]["source_refs"][0].__setitem__(
            "symbol", "sample_summary_diagnostic"))
        rejected(lambda d: d["requirements"][0]["source_refs"][0].__setitem__(
            "marker", "PINNED_SAMPLE_ARITHMETIC_ONLY"))

    def test_provider_and_local_evidence_remain_distinct(self):
        provider = {item["id"] for item in self.doc["requirements"]
                    if item["category"] == "PROVIDER_CONTRACT"}
        local = {item["id"] for item in self.doc["requirements"]
                 if item["category"] == "LOCAL_EVIDENCE"}
        self.assertEqual(local, {"LOCAL_SIGNED_DETAIL_EVIDENCE_COMPLETENESS"})
        self.assertEqual(provider, REQUIRED - local)
        self.assertFalse(self.doc["enforced_boundaries"]
                         ["local_configured_stores_are_provider_population"])
        self.assertFalse(self.doc["enforced_boundaries"]
                         ["files_or_links_establish_verification"])
        self.assertFalse(self.doc["enforced_boundaries"]["runtime_order_database_in_local_snapshot"])
        self.assertFalse(self.doc["enforced_boundaries"]["cross_database_atomic"])
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
