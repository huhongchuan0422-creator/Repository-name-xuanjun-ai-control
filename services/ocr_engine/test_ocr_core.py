"""No production data, image files or model downloads required."""
import unittest
try:
    from .ocr_core import extract_fields, normalize_lines, run_local_ocr
except ImportError:
    from ocr_core import extract_fields, normalize_lines, run_local_ocr

class OcrCoreTests(unittest.TestCase):
    def test_license_extraction(self):
        lines = [{"text":"统一社会信用代码 91350100M000100Y43","confidence":0.91},
                 {"text":"名称 示例经营主体（合成样本）","confidence":0.97}]
        fields = extract_fields(lines, "business_license")["fields"]
        self.assertEqual(fields["credit_code"]["value"], "91350100M000100Y43")
        self.assertIn("示例经营主体", fields["company_name"]["value"])
    def test_low_confidence_requires_review(self):
        result = extract_fields([{"text":"名称 演示公司","confidence":0.62}], "business_license")
        self.assertTrue(result["fields"]["company_name"]["requires_review"])
        self.assertFalse(result["authenticity_verified"])
    def test_no_hallucinated_fields(self):
        self.assertEqual(extract_fields([{"text":"图像不清楚","confidence":0.99}], "id_front")["fields"], {})
    def test_reject_unsupported_type(self):
        with self.assertRaises(ValueError):
            extract_fields([], "unknown")
    def test_reject_bad_magic_before_model_load(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_IMAGE_MAGIC"):
            run_local_ocr(b"not an image", "business_license")
    def test_normalize_result(self):
        result = normalize_lines({"txts":["名称 演示"], "scores":[0.8]})
        self.assertEqual(result[0]["confidence"],0.8)
if __name__ == "__main__":
    unittest.main()
