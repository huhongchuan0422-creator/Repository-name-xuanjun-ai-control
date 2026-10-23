"""Check model redistribution notice bundle contents without downloading or upgrading model weights."""
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/"model_manifest.json"
NOTICE=ROOT/"model_distribution"/"NOTICE.md"
LICENSE=ROOT/"model_distribution"/"LICENSE-2.0.txt"
class ModelDistributionBundleTests(unittest.TestCase):
    def test_manifest_license_and_notice_exist(self):
        self.assertTrue(MANIFEST.is_file())
        self.assertTrue(NOTICE.is_file())
        self.assertTrue(LICENSE.is_file())
    def test_manifest_hashes_are_explicit_and_attributed(self):
        manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
        notice=NOTICE.read_text(encoding="utf-8")
        license_text=LICENSE.read_text(encoding="utf-8")
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0", license_text)
        self.assertIn("RapidAI/RapidOCR/blob/4a3070f304467e6d426e78a82afea5cb1181f305/python/MODEL_LICENSES.md", notice)
        for item in manifest["model_set"]["files"].values():
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(item["sha256"], notice)
            self.assertIn(item["filename"], notice)
    def test_source_license_is_verified_but_archive_packaging_not_claimed(self):
        manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
        verification=manifest["verification"]
        self.assertTrue(verification["source_notice_verified"])
        self.assertTrue(verification["section_6_hashes_match_manifest"])
        self.assertFalse(verification["release_archive_packaging_verified"])
if __name__=="__main__": unittest.main()
