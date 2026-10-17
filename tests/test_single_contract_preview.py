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
        self.assertEqual(preview["content_type"], "text/plain; charset=utf-8")
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
        self.assertIn("<script>",result)
        self.assertNotIn("&lt;",result)
        self.assertEqual(render(freeze(data))["content_type"], "text/plain; charset=utf-8")

    def test_reject_bad_candidate(self):
        with self.assertRaises(ContractHold):
            render({"status":"SIGNED"})
        with self.assertRaises(ContractHold):
            render(None)


    def test_markdown_injection_examples_are_literal(self):
        x=samples.sample()
        x["features"][0]["description"]="[click](https://attacker.invalid/)\nFAKE LEGAL SECTION\n------------------\n**PAYMENT APPROVED**"
        text=render(freeze(x))["text"]
        self.assertNotIn("[click](https://attacker.invalid/)",text)
        self.assertNotIn("**PAYMENT APPROVED**",text)
        self.assertNotIn("\n------------------\n",text)
        self.assertIn("CONTRACT_SIGN=HOLD",text)

    def test_sc_r4_bare_urls_and_entities(self):
        x=samples.sample()
        x["features"][0]["description"]=(
            "Untrusted URL https://2130706433/ and www.example.com "
            "<script> &lt;safe&gt; & **literal** `code`")
        result=render(freeze(x))
        self.assertEqual(result["content_type"],"text/plain; charset=utf-8")
        self.assertNotIn("https://2130706433/",result["text"])
        self.assertIn("https\\u2060://2130706433/",result["text"])
        self.assertIn("www\\u2060.example.com",result["text"])
        self.assertIn("<script> &lt;safe&gt; &",result["text"])
        self.assertNotIn("&lt;script\\&gt;",result["text"])

    def test_sc_r4_structural_text_is_not_markup(self):
        x=samples.sample()
        x["features"][0]["description"]=(
            "[click](https://attacker.invalid/) ![image](http://img.invalid/)\\n"
            "FAKE SECTION\\n--------------\\n**PAYMENT APPROVED**\\n"
            "```fake\\n# heading\\n- list item")
        result=render(freeze(x))
        self.assertNotIn("https://attacker.invalid/",result["text"])
        self.assertNotIn("http://img.invalid/",result["text"])
        self.assertNotIn("\\nFAKE SECTION\\n",result["text"])
        self.assertNotIn("## ",result["text"])
        self.assertEqual(result["content_type"],"text/plain; charset=utf-8")
        self.assertIn("CONTRACT_SIGN=HOLD",result["text"])

if __name__=="__main__":
    unittest.main()
