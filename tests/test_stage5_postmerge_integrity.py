"""Post-merge source tree canary for Stage5 PR110 integration.

This test executes on a branch created directly from the exact verified
main merge commit 9a022ada842c579e8bc943720a5d6e751c3e006e.
It tests the combined Python boundary only; full aggregate and Chromium CI
are independently triggered by changes to this test path.
"""
import unittest
from scripts.community_demo_api import READ_TIMEOUT_SECONDS, handler, DemoService
from scripts.community_checkout_refund_preview_read import checkout_with_refund_preview

class PostMergeCanary(unittest.TestCase):
    def test_hardened_backend_and_merged_business_helpers_import(self):
        self.assertEqual(READ_TIMEOUT_SECONDS, 1.0)
        self.assertTrue(callable(handler))
        self.assertTrue(callable(DemoService))
        self.assertTrue(callable(checkout_with_refund_preview))
    def test_three_page_static_allowlist_and_real_uuid_contract(self):
        from pathlib import Path
        root=Path(__file__).resolve().parent.parent
        source=(root/"scripts"/"community_demo_api.py").read_text("utf-8")
        js=(root/"demos"/"community-local-e2e"/"app.js").read_text("utf-8")
        for path in ("/demo/merchant/","/demo/platform/","/demo/"):
            self.assertIn(path,source)
        self.assertIn("crypto.randomUUID()",js)
        self.assertIn("HEADER_DEADLINE_EXPIRED",source)

if __name__=="__main__": unittest.main()
