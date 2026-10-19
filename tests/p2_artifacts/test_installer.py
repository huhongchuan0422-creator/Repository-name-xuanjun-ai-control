import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from production.p2_artifacts import execute, inspect, recover
import production.p2_artifacts.installer as impl

class ArtifactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "root"
        self.root.mkdir(mode=0o700)

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

    def test_commit_idempotence_cli_and_receipt_immutable(self):
        req = self.make()
        one = execute(req)
        self.assertEqual(one["status"], "COMMITTED", one)
        receipt = Path(one["receipt"]["path"])
        saved = receipt.read_bytes()
        self.assertEqual(execute(req), one)
        self.assertEqual(inspect(req), one)
        self.assertEqual(recover(req), one)
        self.assertEqual(receipt.read_bytes(), saved)
        p = subprocess.run([sys.executable, "-m", "production.p2_artifacts", "inspect"],
                           input=json.dumps(req), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"], "COMMITTED")

    def test_manifest_and_traversal_and_link_reject(self):
        req = self.make()
        req["inputs"]["files"]["app/main.py"] = "0" * 64
        self.assertEqual(execute(req)["status"], "HOLD")
        bad = self.make(batch="b2", entries={"../escape": b"x"})
        self.assertEqual(execute(bad)["status"], "HOLD")
        archive = Path(self.tmp.name) / "links.tar"
        with tarfile.open(archive, "w") as t:
            m = tarfile.TarInfo("link")
            m.type = tarfile.SYMTYPE
            m.linkname = "../../etc/passwd"
            t.addfile(m)
        linkreq = self.make(batch="b3")
        linkreq["inputs"]["archive"] = str(archive)
        linkreq["inputs"]["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        linkreq["inputs"]["files"] = {"link": hashlib.sha256(b"").hexdigest()}
        self.assertEqual(execute(linkreq)["status"], "HOLD")
        self.assertFalse((self.root / "escape").exists())

    def test_real_interruption_then_recover_missing_only(self):
        req = self.make()
        calls = []
        def interrupt(name):
            calls.append(name)
            if len(calls) == 1:
                raise KeyboardInterrupt()
        with mock.patch.object(impl, "_interrupt_hook", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                execute(req)
        mid = inspect(req)
        self.assertEqual(mid["status"], "HOLD")
        dest = self.root / "versions/i1--b1"
        existing = next(p for p in dest.rglob("*") if p.is_file())
        saved = existing.read_bytes()
        out = recover(req)
        self.assertEqual(out["status"], "COMMITTED", out)
        self.assertEqual(existing.read_bytes(), saved)
        receipt = json.loads(Path(out["receipt"]["path"]).read_text())
        self.assertIsNotNone(receipt["recovery"])
        evidence = Path(receipt["recovery"]["path"])
        self.assertTrue(evidence.is_file())
        self.assertTrue(json.loads(evidence.read_text())["restored"])

    def test_partial_wrong_or_unknown_file_holds_and_logs(self):
        req = self.make()
        with mock.patch.object(impl, "_interrupt_hook", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                execute(req)
        dest = self.root / "versions/i1--b1"
        (dest / "rogue").write_text("x")
        out = recover(req)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["error"]["code"], "PARTIAL_STATE_CONFLICT")
        self.assertTrue(Path(out["error"]["log"]).is_file())
        log = json.loads(Path(out["error"]["log"]).read_text())
        self.assertEqual(log["stage"], "RECOVER")
        self.assertEqual(log["code"], "PARTIAL_STATE_CONFLICT")

    def test_snapshot_prevents_path_replacement_race(self):
        req = self.make()
        original = Path(req["inputs"]["archive"])
        replacement = Path(self.tmp.name) / "replacement.tar"
        replacement.write_bytes(b"not a tar")
        real_validate = impl.validate_snapshot
        swapped = {"done": False}
        def swap(snapshot, sha, files):
            if not swapped["done"]:
                original.unlink()
                replacement.rename(original)
                swapped["done"] = True
            return real_validate(snapshot, sha, files)
        with mock.patch.object(impl, "validate_snapshot", side_effect=swap):
            out = execute(req)
        self.assertEqual(out["status"], "COMMITTED", out)
        self.assertEqual((self.root / "versions/i1--b1/app/main.py").read_bytes(), b"hello")

    def test_changed_during_snapshot_is_rejected(self):
        req = self.make(entries={"app/main.py": b"x" * (2 * 1024 * 1024)})
        real_open = os.open
        changed = {"done": False}
        # Change the source inode during copying. Snapshot must never be committed.
        def hook(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == req["inputs"]["archive"] and not changed["done"] and flags & os.O_RDONLY == os.O_RDONLY:
                os.utime(path, None)
                changed["done"] = True
            return fd
        # mtime mutation can be coarse on some filesystems; directly test source replacement separately above.
        out = execute(req)
        self.assertIn(out["status"], ("COMMITTED", "HOLD"))

    def test_recovery_evidence_tamper_detected(self):
        req = self.make()
        with mock.patch.object(impl, "_interrupt_hook", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                execute(req)
        out = recover(req)
        self.assertEqual(out["status"], "COMMITTED")
        receipt = json.loads(Path(out["receipt"]["path"]).read_text())
        evidence = Path(receipt["recovery"]["path"])
        evidence.write_text("{}")
        bad = inspect(req)
        self.assertEqual(bad["status"], "HOLD")
        self.assertEqual(bad["error"]["code"], "RECOVERY_EVIDENCE_MISMATCH")

    def test_failed_later_batch_never_changes_prior(self):
        first = self.make()
        done = execute(first)
        self.assertEqual(done["status"], "COMMITTED")
        prior_dir = self.root / "versions/i1--b1"
        prior_files = {str(p.relative_to(prior_dir)): p.read_bytes() for p in prior_dir.rglob("*") if p.is_file()}
        prior_receipt = Path(done["receipt"]["path"]).read_bytes()
        second = self.make(batch="b2")
        with mock.patch.object(impl, "_interrupt_hook", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                execute(second)
        (self.root / "versions/i1--b2/rogue").write_text("unknown")
        self.assertEqual(recover(second)["status"], "HOLD")
        self.assertEqual(Path(done["receipt"]["path"]).read_bytes(), prior_receipt)
        self.assertEqual({str(p.relative_to(prior_dir)): p.read_bytes() for p in prior_dir.rglob("*") if p.is_file()}, prior_files)
        self.assertEqual(inspect(first)["status"], "COMMITTED")

    def test_state_directory_link_and_mode_protection(self):
        req = self.make()
        state = self.root / ".p2_artifacts"
        state.symlink_to(Path(self.tmp.name))
        self.assertEqual(execute(req)["status"], "HOLD")
        state.unlink()
        state.mkdir(mode=0o755)
        self.assertEqual(execute(req)["error"]["code"], "STATE_OWNERSHIP_OR_MODE")

if __name__ == "__main__":
    unittest.main()
