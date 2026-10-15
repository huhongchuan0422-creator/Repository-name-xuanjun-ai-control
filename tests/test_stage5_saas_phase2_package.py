import hashlib
import io
import json
import zipfile
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
 def mutated(self,blob,change):
    with zipfile.ZipFile(io.BytesIO(blob)) as source:
        items=[(x,source.read(x.filename)) for x in source.infolist()]
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w",compression=zipfile.ZIP_DEFLATED) as target:
        for info,data in items:
            target.writestr(info,change(data) if info.filename=="manifest.json" else data)
    return result.getvalue()
 def test_09_reject_false_live_provider_flags(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        blob=build(d)["archive_bytes"]
        def change(raw):
            m=json.loads(raw);m["wechat_payment_connected"]=True
            return json.dumps(m).encode()
        with self.assertRaisesRegex(ValueError,"INVALID_OFFLINE_SCOPE"):
            inspect(self.mutated(blob,change))
 def test_10_reject_duplicate_manifest_keys(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        blob=build(d)["archive_bytes"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MANIFEST_KEY"):
            inspect(self.mutated(blob,lambda raw:raw[:-1]+b',"production_install_authorized":false}'))
 def test_12_reject_invalid_hex_digest(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        blob=build(d)["archive_bytes"]
        def change(raw):
            m=json.loads(raw);m["assets_sha256"][ASSETS[0]]="z"*64
            return json.dumps(m).encode()
        with self.assertRaisesRegex(ValueError,"INVALID_ASSET_DIGEST"):
            inspect(self.mutated(blob,change))
 def test_13_reject_large_manifest_member(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        blob=build(d)["archive_bytes"]
        with self.assertRaisesRegex(ValueError,"PACKAGE_MEMBER_UNSAFE"):
            inspect(self.mutated(blob,lambda raw:raw+b" "*70000))
 def test_11_reject_undeclared_manifest_fields(self):
    with tempfile.TemporaryDirectory() as d:
        self.source(d)
        blob=build(d)["archive_bytes"]
        def change(raw):
            m=json.loads(raw);m["extra_approved"]=True
            return json.dumps(m).encode()
        with self.assertRaisesRegex(ValueError,"INVALID_MANIFEST_FIELDS"):
            inspect(self.mutated(blob,change))
if __name__=="__main__":unittest.main()
