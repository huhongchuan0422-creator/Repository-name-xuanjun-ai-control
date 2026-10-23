"""Governance-registered OCR contract tests. Synthetic text only; no identity data or inference claim."""
import unittest
from services.ocr_engine.ocr_core import extract_fields, normalize_lines, run_local_ocr

class OcrContractTests(unittest.TestCase):
    def test_business_license_fields_and_confirmation(self):
        lines = [
            {"text": "统一社会信用代码 91350100M000100Y43", "confidence": 0.91},
            {"text": "名称 示例经营主体（合成样本）", "confidence": 0.97},
        ]
        result = extract_fields(lines, "business_license")
        self.assertEqual(result["fields"]["credit_code"]["value"], "91350100M000100Y43")
        self.assertTrue(result["requires_human_confirmation"])
        self.assertFalse(result["authenticity_verified"])

    def test_low_confidence_flagged(self):
        result = extract_fields([{"text": "名称 演示主体", "confidence": 0.62}], "business_license")
        self.assertTrue(result["fields"]["company_name"]["requires_review"])

    def test_missing_fields_are_not_invented(self):
        self.assertEqual(extract_fields([{"text": "模糊文本", "confidence": 0.99}], "id_front")["fields"], {})

    def test_unsupported_type_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_DOCUMENT_TYPE"):
            extract_fields([], "storefront_photo")

    def test_invalid_magic_rejected_without_model_loading(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_IMAGE_MAGIC"):
            run_local_ocr(b"not an image", "business_license")

    def test_result_normalization(self):
        self.assertEqual(normalize_lines({"txts": ["名称 演示"], "scores": [0.8]})[0]["confidence"], 0.8)

if __name__ == "__main__":
    unittest.main()
