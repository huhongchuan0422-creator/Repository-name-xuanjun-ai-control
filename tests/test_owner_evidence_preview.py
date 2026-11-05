import importlib.util
import pathlib
import tempfile
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "owner_evidence_preview.py"
SPEC = importlib.util.spec_from_file_location("preview", PATH)
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)

class EvidencePreviewTests(unittest.TestCase):
    def test_project_state_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "state"
            p.write_text("STATUS=IN_PROGRESS\nSECRET_KEY=dont-render\nCURRENT_STAGE=0\n")
            result = preview.read_canonical(p)
            self.assertNotIn("SECRET_KEY", result)
            self.assertEqual(result["STATUS"], "IN_PROGRESS")
    def test_escape_html(self):
        s = preview.render({"STATUS": "<script>alert(1)</script>"}, [{"node_id":"A","title":"<img src=x>","status":"UNKNOWN"}])
        self.assertNotIn("<script>alert(1)</script>", s)
        self.assertNotIn("<img src=x>", s)
        self.assertIn("&lt;script&gt;", s)
        self.assertIn("UNKNOWN", s)
    def test_unknown_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "cards.json"
            p.write_text('[{"node_id":"1.8","title":"Gateway","status":"PASS"}]')
            self.assertEqual(preview.cards(p)[0]["status"], "UNKNOWN")
    def test_sensitive_field_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "cards.json"
            p.write_text('[{"node_id":"TOKEN","title":"bad"}]')
            with self.assertRaises(ValueError):
                preview.cards(p)

if __name__ == "__main__":
    unittest.main()
