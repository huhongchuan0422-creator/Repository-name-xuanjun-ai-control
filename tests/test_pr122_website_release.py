import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts/pr122_website_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        (self.bundle / "overlay/public/assets").mkdir(parents=True)
        self.original = b"old\n"
        self.updated = b"new\n"
        (self.bundle / "overlay/public/assets/tiktok-integration.js").write_bytes(self.updated)
        self.source = self.root / "source.tar.gz"
        with tarfile.open(self.source, "w:gz") as archive:
            directory = tarfile.TarInfo("package/public/assets")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
            item = tarfile.TarInfo("package/public/assets/tiktok-integration.js")
            item.size = len(self.original)
            archive.addfile(item, io.BytesIO(self.original))
        pin = {
            "source_archive_size": self.source.stat().st_size,
            "source_archive_sha256": release.digest(self.source),
            "overlay_baselines": {"assets/tiktok-integration.js": sha(self.original)},
        }
        manifest = {"files": [{"path": "assets/tiktok-integration.js", "size": len(self.updated), "sha256": sha(self.updated)}]}
        (self.bundle / "source-pin.json").write_text(json.dumps(pin))
        (self.bundle / "candidate-manifest.json").write_text(json.dumps(manifest))
        self.base = self.root / "webroot"

    def tearDown(self):
        self.temp.cleanup()

    def args(self, **updates):
        values = dict(bundle=self.bundle, source_archive=self.source, webroot_base=self.base,
                      transaction_id="tx-1", release_id="release-1", deadline_seconds=5)
        values.update(updates)
        return SimpleNamespace(**values)

    def test_prepare_activate_check_and_rollback(self):
        prepared = release.prepare(self.args())
        self.assertEqual(prepared["state"], "PREPARED")
        activated = release.activate(self.args())
        self.assertEqual(activated["state"], "ACTIVATED")
        self.assertEqual(release.check(self.args())["state"], "PASS")
        rolled = release.rollback(self.args())
        self.assertEqual(rolled["state"], "ROLLED_BACK")
        self.assertFalse((self.base / "current").exists())

    def test_baseline_drift_is_partial_hold(self):
        pin = json.loads((self.bundle / "source-pin.json").read_text())
        pin["overlay_baselines"]["assets/tiktok-integration.js"] = "0" * 64
        (self.bundle / "source-pin.json").write_text(json.dumps(pin))
        with self.assertRaisesRegex(release.Hold, "OVERLAY_BASELINE_DRIFT"):
            release.prepare(self.args())
        receipt = json.loads((self.base / "transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"], "HOLD_PARTIAL")

    def test_unknown_current_blocks_rollback_without_write(self):
        release.prepare(self.args())
        release.activate(self.args())
        other = self.base / "releases/other"
        other.mkdir()
        current = self.base / "current"
        current.unlink()
        current.symlink_to(other)
        with self.assertRaisesRegex(release.Hold, "CURRENT_IDENTITY_UNKNOWN"):
            release.rollback(self.args())
        self.assertEqual(current.resolve(), other.resolve())

    def test_post_activation_content_failure_is_receipted_and_rollback_works(self):
        release.prepare(self.args())
        release.activate(self.args())
        target = self.base / "current/public/assets/tiktok-integration.js"
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(release.Hold, "RELEASE_CONTENT_MISMATCH"):
            release.check(self.args())
        receipt = json.loads((self.base / "transactions/tx-1.json").read_text())
        self.assertEqual(receipt["state"], "CHECK_FAILED")
        self.assertEqual(release.rollback(self.args())["state"], "ROLLED_BACK")

    def test_lock_timeout_is_hold(self):
        self.base.mkdir()
        lock_path = self.base / ".release.lock"
        code = "import fcntl,sys,time; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('READY',flush=True); time.sleep(10)"
        process = subprocess.Popen([sys.executable, "-c", code, str(lock_path)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "READY")
            with self.assertRaisesRegex(release.Hold, "LOCK_TIMEOUT"):
                with release.lock(self.base, 0):
                    pass
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()

    def test_verify_timeout_is_hold(self):
        public = self.root / "public"
        public.mkdir()
        with self.assertRaisesRegex(release.Hold, "VERIFY_TIMEOUT"):
            release.verify_tree(public, {"files": []}, time.monotonic() - 1)

    def test_unsafe_archive_member_is_rejected(self):
        with tarfile.open(self.source, "w:gz") as archive:
            item = tarfile.TarInfo("package/public/../../escape")
            item.size = 1
            archive.addfile(item, io.BytesIO(b"x"))
        pin = json.loads((self.bundle / "source-pin.json").read_text())
        pin.update({"source_archive_size": self.source.stat().st_size, "source_archive_sha256": release.digest(self.source)})
        (self.bundle / "source-pin.json").write_text(json.dumps(pin))
        with self.assertRaisesRegex(release.Hold, "UNSAFE_ARCHIVE_MEMBER_PATH"):
            release.prepare(self.args())


class CandidateConfigTest(unittest.TestCase):
    def test_existing_winctl_is_not_a_candidate_mutation_target(self):
        base = ROOT / "deploy/pr122-domestic-website"
        for path in list((base / "nginx").glob("*")) + list((base / "tls").glob("*")):
            self.assertNotIn("winctl.wenwenwenyiyiyi.work", path.read_text())

    def test_private_home_is_not_an_nginx_root(self):
        text = (ROOT / "deploy/pr122-domestic-website/nginx/xuanjun-apex-https.conf").read_text()
        self.assertIn("root /var/www/wenwenwenyiyiyi.work/current/public;", text)
        self.assertNotIn("/home/openclaw_ops", text)

    def test_package_manifest_covers_release_tool_and_delta_files(self):
        base = ROOT / "deploy/pr122-domestic-website"
        manifest = json.loads((base / "PACKAGE_MANIFEST.json").read_text())
        paths = {item["path"] for item in manifest["files"]}
        self.assertIn("bin/pr122_website_release.py", paths)
        self.assertIn("candidate-manifest.json", paths)
        self.assertIn("overlay/public/assets/tiktok-integration.js", paths)
        for item in manifest["files"]:
            path = ROOT / "scripts/pr122_website_release.py" if item["path"] == "bin/pr122_website_release.py" else base / item["path"]
            self.assertEqual(path.stat().st_size, item["size"])
            self.assertEqual(release.digest(path), item["sha256"])


if __name__ == "__main__":
    unittest.main()
