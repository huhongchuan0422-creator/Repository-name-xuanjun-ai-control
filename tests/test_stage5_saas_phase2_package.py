import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from scripts.community_saas_phase2_package import ASSETS,build,inspect
class OfflinePackage(unittest.TestCase):
 def source(self,root):
    for name in ASSETS:
        path=Path(root)/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(("safe:"+name).encode())
 def test_01_deterministic_archive(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        x=build(d);y=build(d)
        self.assertEqual(x["sha256"],y["sha256"])
 def test_02_verified_manifest(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        self.assertTrue(inspect(build(d)["archive_bytes"])["verified"])
 def test_03_never_production(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        x=build(d)
        self.assertFalse(x["manifest"]["production_install_authorized"])
        self.assertFalse(x["manifest"]["wechat_payment_connected"])
 def test_04_missing_asset_fails_closed(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        os.unlink(Path(d)/ASSETS[0])
        with self.assertRaises(ValueError):build(d)
 def test_05_key_material_blocked(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        (Path(d)/ASSETS[0]).write_bytes(b"BEGIN PRIVATE KEY")
        with self.assertRaises(ValueError):build(d)
 def test_06_hash_matches_manifest(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        m=build(d)["manifest"]
        self.assertEqual(m["assets_sha256"][ASSETS[0]],hashlib.sha256((Path(d)/ASSETS[0]).read_bytes()).hexdigest())
 def test_07_source_symlink_rejected(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        origin=Path(d)/ASSETS[0]
        real=origin.with_suffix(".real")
        origin.rename(real)
        origin.symlink_to(real)
        with self.assertRaisesRegex(ValueError,"UNSAFE_OR_MISSING_ASSET"):
            build(d)
 def test_08_complete_candidate_contains_recovery_and_finance_contract(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        manifest=build(d)["manifest"]
        self.assertIn("scripts/community_saas_phase2_recovery.py",manifest["assets_sha256"])
        self.assertIn("scripts/community_saas_offline_handoff.py",manifest["assets_sha256"])
        self.assertNotIn("production.env",manifest["assets_sha256"])
if __name__=="__main__":unittest.main()
