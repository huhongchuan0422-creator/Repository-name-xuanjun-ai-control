"""Deterministic offline guard for the single signed custom development contract.
Run: python3 -m unittest discover -s tests -p test_single_contract_consistency.py -v
No API calls, external files or customer material.
"""
import hashlib
import html
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class SingleContractConsistency(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "docs/legal/registry.json").read_bytes())
        self.docs = {x["id"]: x for x in self.registry["documents"]}

    def source(self, ident):
        item = self.docs[ident]
        return (ROOT / item["source"]).read_bytes()

    def test_exact_utf8_sha256(self):
        for ident in ("custom-development", "custom-sow"):
            item = self.docs[ident]
            self.assertEqual(hashlib.sha256(self.source(ident)).hexdigest(), item["source_sha256"])

    def test_exact_html_escaped_full_document(self):
        for ident, preview in (("custom-development", "demos/legal/custom-development.html"),
                               ("custom-sow", "demos/legal/custom-sow.html")):
            data = self.source(ident).decode("utf-8")
            page = (ROOT / preview).read_text(encoding="utf-8")
            self.assertIn("<pre>" + html.escape(data, quote=True) + "</pre>", page)
            self.assertIn("SHA256：" + self.docs[ident]["source_sha256"], page)
            self.assertIn(self.docs[ident]["version"], page)

    def test_single_customer_signing_contract(self):
        policy = self.registry["custom_development_single_document_policy"]
        self.assertEqual(policy["customer_signed_document_id"], "custom-development")
        self.assertEqual(policy["customer_signable_document_count"], 1)
        self.assertEqual(self.docs["custom-sow"]["status"], "INTERNAL_ONLY")
        self.assertIsNone(self.docs["custom-sow"]["planned_route"])
        self.assertIsNone(self.docs["custom-sow"]["preview"])
        self.assertFalse(self.docs["custom-sow"]["signature_enabled"])

    def test_legacy_signing_language_removed(self):
        main = self.source("custom-development").decode("utf-8")
        internal = self.source("custom-sow").decode("utf-8")
        for bad in ("乙方按任务书交付", "在任务书一次说清", "检索已确认任务书", "完整附件、法律审查"):
            self.assertNotIn(bad, main)
        for bad in ("甲方（客户）", "乙方（开发服务方）", "七、双方签署"):
            self.assertNotIn(bad, internal)
        for number in ("二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八"):
            self.assertIn(number + "、", main)

    def test_production_hold(self):
        self.assertFalse(self.registry["production_enabled"])
        self.assertFalse(self.docs["custom-development"]["signature_enabled"])
        self.assertIn("DRAFT_NOT_FOR_SIGNATURE", self.source("custom-development").decode("utf-8"))
        self.assertIn("INTERNAL_SCHEMA_NOT_FOR_CUSTOMER_SIGNATURE", self.source("custom-sow").decode("utf-8"))

if __name__ == "__main__":
    unittest.main()
