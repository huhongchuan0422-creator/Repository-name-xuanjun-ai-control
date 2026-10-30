import shutil
import tempfile
import unittest
from pathlib import Path
from scripts.pr122_delivery_host import integrate

ROOT=Path(__file__).resolve().parents[1]
class DeliveryHostTests(unittest.TestCase):
    def setup_tree(self, td):
        root=Path(td)/'repo';public=Path(td)/'public';public.mkdir()
        shutil.copytree(ROOT/'demos/pr122-delivery-review',root/'demos/pr122-delivery-review')
        (public/'index.html').write_text('<html lang="zh-CN"><nav id="primary-nav"><a href="/custom-ai">定制与交付</a><button></button><div class="nav-panel"></div></nav></html>')
        return root,public
    def test_frozen_drift_rejects_before_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root,public=self.setup_tree(td)
            (root/'demos/pr122-delivery-review/community-next/suite.js').write_text('changed')
            before=(public/'index.html').read_bytes()
            with self.assertRaisesRegex(ValueError,'FROZEN_REVIEW_TEMPLATE_DRIFT'):integrate(root,public)
            self.assertFalse((public/'delivery').exists());self.assertEqual(before,(public/'index.html').read_bytes())
    def test_unknown_existing_directory_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root,public=self.setup_tree(td);(public/'delivery').mkdir();(public/'delivery/draft').write_text('unknown')
            with self.assertRaisesRegex(ValueError,'DELIVERY_HOST_COLLISION'):integrate(root,public)
            self.assertEqual((public/'delivery/draft').read_text(),'unknown')
    def test_navigation_drift_rejects_without_partial_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root,public=self.setup_tree(td);(public/'later.html').write_text('<nav id="primary-nav">unknown draft</nav>')
            before=(public/'index.html').read_bytes()
            with self.assertRaisesRegex(ValueError,'DELIVERY_NAV_STRUCTURE'):integrate(root,public)
            self.assertFalse((public/'delivery').exists());self.assertEqual(before,(public/'index.html').read_bytes())
