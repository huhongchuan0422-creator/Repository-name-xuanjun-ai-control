"""Strictly text/plain contract-preview regressions."""
import importlib.util
import pathlib
import sys
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from single_contract_preview import render
from single_contract_freeze import ContractHold, freeze
spec = importlib.util.spec_from_file_location("samples", str(ROOT / "tests/test_single_contract_freeze.py"))
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)

class PreviewTests(unittest.TestCase):
    def build(self, value=None):
        data=samples.sample()
        if value is not None:
            data["features"][0]["description"]=value
        return render(freeze(data))

    def test_payment_and_content_type(self):
        result=self.build()
        self.assertEqual(result["content_type"],"text/plain; charset=utf-8")
        self.assertEqual(result["status"],"DRAFT_NOT_FOR_SIGNATURE")
        self.assertFalse(result["signable"])
        self.assertIn("4150.00",result["text"])
        self.assertIn("3000.00",result["text"])
        self.assertIn("CONTRACT_SIGN=HOLD",result["text"])
        self.assertEqual(result,self.build())

    def test_tampered_hash(self):
        x=freeze(samples.sample())
        x["frozen"]["payment_cny"]["first_total"]="1.00"
        with self.assertRaisesRegex(ContractHold,"FROZEN_HASH_MISMATCH"):
            render(x)

    def test_gate_tamper(self):
        x=freeze(samples.sample())
        x["contract_sign"]="READY"
        with self.assertRaisesRegex(ContractHold,"GATE_TAMPERED"):
            render(x)

    def test_entities_and_multiline(self):
        t=self.build("Example\n# FAKE SIGNED HEADING <script> &lt;safe&gt;")["text"]
        self.assertIn("<script> &lt;safe&gt;",t)
        self.assertNotIn("&lt;script\\&gt;",t)
        self.assertNotIn("\n# FAKE SIGNED HEADING",t)

    def test_invalid_candidate(self):
        with self.assertRaises(ContractHold):
            render(None)
        with self.assertRaises(ContractHold):
            render({"status":"SIGNED"})

    def test_explicit_links_and_emphasis_are_literally_text(self):
        p=self.build("[click](https://attacker.invalid/)\nFAKE LEGAL SECTION\n"
                     "------------------\n**PAYMENT APPROVED**")
        self.assertEqual(p["content_type"],"text/plain; charset=utf-8")
        self.assertIn("**PAYMENT APPROVED**",p["text"])
        self.assertIn("https\u2060://attacker.invalid/",p["text"])
        self.assertNotIn("https://attacker.invalid/",p["text"])
        self.assertNotIn("\n------------------\n",p["text"])

    def test_bare_url_numeric_ip_and_html(self):
        p=self.build("https://2130706433/ http://localhost/ www.example.com <script>")
        self.assertEqual(p["content_type"],"text/plain; charset=utf-8")
        self.assertIn("https\u2060://2130706433/",p["text"])
        self.assertIn("http\u2060://localhost/",p["text"])
        self.assertIn("www\u2060.example.com",p["text"])
        self.assertIn("<script>",p["text"])
        self.assertNotIn("https://2130706433/",p["text"])

    def test_image_setext_and_fence(self):
        p=self.build("![image](http://img.invalid/)\n~~~\n# title\n"
                     "Setext\n----------\n- list")
        self.assertIn("http\u2060://img.invalid/",p["text"])
        self.assertNotIn("\n----------\n",p["text"])
        self.assertEqual(p["content_type"],"text/plain; charset=utf-8")
        self.assertIn("CONTRACT_SIGN=HOLD",p["text"])

if __name__=="__main__":
    unittest.main()
