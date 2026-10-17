"""Offline tests for one-document unsigned customer preview."""
import copy
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from single_contract_preview import render
from single_contract_freeze import ContractHold, freeze
spec = importlib.util.spec_from_file_location(
    "freeze_samples", str(ROOT / "tests" / "test_single_contract_freeze.py"))
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)

class PreviewTests(unittest.TestCase):
    def test_one_document_and_payment(self):
        preview=render(freeze(samples.sample()))
        self.assertEqual(preview["status"], "DRAFT_NOT_FOR_SIGNATURE")
        self.assertFalse(preview["signable"])
        self.assertIn("4150.00",preview["text"])
        self.assertIn("3000.00",preview["text"])
        self.assertIn("CONTRACT_SIGN=HOLD",preview["text"])
        self.assertEqual(preview,render(freeze(samples.sample())))

    def test_tampered_hash_rejected(self):
        candidate=freeze(samples.sample())
        candidate["frozen"]["payment_cny"]["first_total"]="1.00"
        with self.assertRaisesRegex(ContractHold,"FROZEN_HASH_MISMATCH"):
            render(candidate)

    def test_marked_signable_rejected(self):
        candidate=freeze(samples.sample())
        candidate["contract_sign"]="READY"
        with self.assertRaisesRegex(ContractHold,"GATE_TAMPERED"):
            render(candidate)

    def test_customer_markdown_cannot_forge_sections(self):
        data=samples.sample()
        data["features"][0]["description"]="Example\n# FAKE SIGNED HEADING <script>"
        result=render(freeze(data))["text"]
        self.assertNotIn("\n# FAKE SIGNED HEADING <script>",result)
        self.assertIn("&lt;script&gt;",result)

    def test_reject_bad_candidate(self):
        with self.assertRaises(ContractHold):
            render({"status":"SIGNED"})
        with self.assertRaises(ContractHold):
            render(None)

if __name__=="__main__":
    unittest.main()
