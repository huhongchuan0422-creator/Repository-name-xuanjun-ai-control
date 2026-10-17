"""Full-length draft rendering stays unsigned and binds exact legal template bytes."""
import importlib.util
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from single_contract_freeze import freeze, ContractHold
from single_contract_full_draft import build_unsigned_document
spec=importlib.util.spec_from_file_location("samples",str(ROOT/"tests/test_single_contract_freeze.py"))
samples=importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)

class FullDraftTests(unittest.TestCase):
    def test_28_chapters_and_quote_present(self):
        out=build_unsigned_document(freeze(samples.sample()),ROOT)
        self.assertFalse(out["signable"])
        self.assertEqual(out["content_type"],"text/plain; charset=utf-8")
        self.assertIn("二十八、单一合同版本与签署证据",out["text"])
        self.assertIn("二十二、项目需求与验收标准",out["text"])
        self.assertIn("4150.00",out["text"])
        self.assertIn("3000.00",out["text"])
        self.assertIn("feature-1",out["text"])
        self.assertIn("server1",out["text"])
        self.assertEqual(out["contract_sign"],"HOLD")
        self.assertEqual(out["payment"],"HOLD")
        self.assertEqual(out["procurement"],"HOLD")
        self.assertEqual(out,build_unsigned_document(freeze(samples.sample()),ROOT))
    def test_corrupt_hash_rejected(self):
        c=freeze(samples.sample())
        c["contract_document_hash"]="0"*64
        with self.assertRaisesRegex(ContractHold,"FROZEN_HASH_MISMATCH"):
            build_unsigned_document(c,ROOT)
    def test_not_a_signing_document(self):
        out=build_unsigned_document(freeze(samples.sample()),ROOT)
        self.assertIn("DRAFT_NOT_FOR_SIGNATURE",out["text"])
        self.assertIn("禁止签约",out["text"])
        self.assertNotIn("SIGNED_AND_PAYABLE",out["text"])

if __name__=="__main__":
    unittest.main()
