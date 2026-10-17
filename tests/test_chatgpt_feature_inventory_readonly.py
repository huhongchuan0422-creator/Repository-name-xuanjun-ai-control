"""Inventory never treats a registered feature or existing source as PASS."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "features",str(ROOT/"scripts/chatgpt_feature_inventory_readonly.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class InventoryTests(unittest.TestCase):
    def make_root(self,feature):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        (root/"governance").mkdir()
        (root/"governance/features.json").write_text(json.dumps({"features":[feature]}),encoding="utf8")
        self.addCleanup(self.temp.cleanup)
        return root
    def test_unknown_remains_unknown(self):
        root=self.make_root({"feature_id":"X","status":"CANDIDATE",
                             "paths":["missing.py"],"acceptance":{"tests":["tests/a.py"]}})
        out=mod.inventory(root)
        row=out["features"][0]
        self.assertEqual(row["missing_tracked_paths"],["missing.py"])
        self.assertEqual(row["ci_status"],"UNKNOWN")
        self.assertEqual(row["production_acceptance"],"UNKNOWN")
        self.assertEqual(row["registered_status"],"CANDIDATE")
    def test_bad_path_denied(self):
        for path in ("../outside","/tmp/root","a/../../b","a\\b"):
            root=self.make_root({"feature_id":"X","paths":[path]})
            with self.assertRaises(mod.RegistryHold):mod.inventory(root)
    def test_duplicate_feature_denied(self):
        root=self.make_root({"feature_id":"X"})
        (root/"governance/features.json").write_text(json.dumps({"features":[
            {"feature_id":"X"},{"feature_id":"X"}]}))
        with self.assertRaises(mod.RegistryHold):mod.inventory(root)
    def test_real_registry_parse_and_stable(self):
        a=mod.inventory(ROOT)
        b=mod.inventory(ROOT)
        self.assertEqual(a,b)
        self.assertGreater(a["feature_count"],0)
        self.assertEqual(a["feature_count"],len(a["features"]))
        self.assertTrue(all(row["ci_status"]=="UNKNOWN" for row in a["features"]))

if __name__=="__main__":
    unittest.main()
