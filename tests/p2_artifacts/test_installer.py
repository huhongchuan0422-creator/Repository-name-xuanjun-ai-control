import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from production.p2_artifacts import execute, inspect, recover

class ArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir()

    def make(self, batch="b1", entries=None, attempt="a1"):
        if entries is None:
            entries = {"app/main.py": b"hello", "plugins/example.py": b"plugin"}
        archive = Path(self.tmp.name) / (batch + ".tar")
        with tarfile.open(archive, "w") as t:
            for name, data in entries.items():
                m = tarfile.TarInfo(name)
                m.size = len(data)
                t.addfile(m, io.BytesIO(data))
        sha = lambda b: hashlib.sha256(b).hexdigest()
        return {"schema": 1, "scope": "ISOLATED_TEST_ONLY", "installation_id": "i1",
                "batch_id": batch, "attempt_id": attempt, "root": str(self.root),
                "inputs": {"operation": "install", "archive": str(archive),
                           "archive_sha256": sha(archive.read_bytes()),
                           "files": {name: sha(data) for name, data in entries.items()}}}

    def test_commit_and_idempotence(self):
        req = self.make()
        one = execute(req)
        self.assertEqual(one["status"], "COMMITTED", one)
        self.assertEqual(execute(req), one)
        self.assertEqual(inspect(req), one)
        self.assertEqual(recover(req), one)
        self.assertEqual((self.root / "versions/i1--b1/app/main.py").read_bytes(), b"hello")

    def test_manifest_reject(self):
        req = self.make()
        req["inputs"]["files"]["app/main.py"] = "0" * 64
        self.assertEqual(execute(req)["status"], "HOLD")
        self.assertEqual(inspect(req)["status"], "NO_EFFECT")

    def test_traversal_reject(self):
        req = self.make(entries={"../escape": b"x"})
        self.assertEqual(execute(req)["status"], "HOLD")
        self.assertFalse((self.root / "escape").exists())

    def test_symlink_reject(self):
        archive = Path(self.tmp.name) / "bad.tar"
        with tarfile.open(archive, "w") as t:
            m = tarfile.TarInfo("link")
            m.type = tarfile.SYMTYPE
            m.linkname = "../../etc/passwd"
            t.addfile(m)
        req = self.make()
        req["inputs"]["archive"] = str(archive)
        req["inputs"]["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.assertEqual(execute(req)["status"], "HOLD")

    def test_interrupted_and_preserve_prior(self):
        good = self.make()
        self.assertEqual(execute(good)["status"], "COMMITTED")
        receipt = good["root"] + "/.p2_artifacts/receipts/i1--b1.json"
        original = Path(receipt).read_bytes()
        second = self.make(batch="b2")
        state = self.root / ".p2_artifacts/journals/i1--b2.json"
        state.write_text(json.dumps({"request_digest": "broken", "attempt_id": "a1"}))
        self.assertEqual(recover(second)["status"], "HOLD")
        self.assertEqual(execute(second)["status"], "HOLD")
        self.assertEqual(Path(receipt).read_bytes(), original)
        self.assertEqual(inspect(good)["status"], "COMMITTED")

    def test_tamper_detected(self):
        req = self.make()
        self.assertEqual(execute(req)["status"], "COMMITTED")
        (self.root / "versions/i1--b1/app/main.py").write_bytes(b"tampered")
        self.assertEqual(recover(req)["status"], "HOLD")

if __name__ == "__main__":
    unittest.main()
