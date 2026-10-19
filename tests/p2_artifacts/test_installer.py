import hashlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
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

    def make(self, batch="b1", entries=None, attempt="a1", modes=None):
        if entries is None:
            entries = {"app/main.py": b"hello", "plugins/example.py": b"plugin"}
        archive = Path(self.tmp.name) / (batch + ".tar")
        with tarfile.open(archive, "w") as tar:
            for name, data in entries.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
        sha = lambda b: hashlib.sha256(b).hexdigest()
        inputs = {"operation": "install", "archive": str(archive),
                  "archive_sha256": sha(archive.read_bytes()),
                  "files": {name: sha(data) for name, data in entries.items()}}
        if modes is not None:
            inputs["modes"] = modes
        return {"schema": 1, "scope": "ISOLATED_TEST_ONLY", "installation_id": "i1",
                "batch_id": batch, "attempt_id": attempt, "root": str(self.root),
                "inputs": inputs}

    def cli(self, req, action):
        return subprocess.run([sys.executable, "-m", "production.p2_artifacts", action],
                              input=json.dumps(req), text=True, capture_output=True)

    def start_cli(self, req, action="execute"):
        proc = subprocess.Popen([sys.executable, "-m", "production.p2_artifacts", action],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        proc.stdin.write(json.dumps(req))
        proc.stdin.close()
        return proc

    def wait_for(self, predicate, proc=None, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if proc is not None and proc.poll() is not None:
                out = proc.stdout.read()
                err = proc.stderr.read()
                self.fail("subprocess exited before checkpoint rc=%r stdout=%r stderr=%r" %
                          (proc.returncode, out, err))
            time.sleep(0.001)
        self.fail("checkpoint timeout")

    def kill(self, proc):
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
        self.assertEqual(proc.returncode, -signal.SIGKILL)

    def recover_cli(self, req):
        p = self.cli(req, "recover")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        out = json.loads(p.stdout)
        self.assertEqual(out["status"], "COMMITTED", out)
        return out

    def prior_snapshot(self):
        req = self.make(batch="prior", attempt="prior-a")
        out = execute(req)
        self.assertEqual(out["status"], "COMMITTED", out)
        receipt = Path(out["receipt"]["path"])
        version = self.root / "versions/i1--prior"
        files = {str(p.relative_to(version)): (p.read_bytes(), os.lstat(p).st_ino, os.lstat(p).st_mtime_ns)
                 for p in version.rglob("*") if p.is_file()}
        return req, receipt, receipt.read_bytes(), files

    def assert_prior_unchanged(self, prior):
        req, receipt, receipt_bytes, files = prior
        self.assertEqual(receipt.read_bytes(), receipt_bytes)
        version = self.root / "versions/i1--prior"
        current = {str(p.relative_to(version)): (p.read_bytes(), os.lstat(p).st_ino, os.lstat(p).st_mtime_ns)
                   for p in version.rglob("*") if p.is_file()}
        self.assertEqual(current, files)
        self.assertEqual(inspect(req)["status"], "COMMITTED")

    def test_commit_idempotence_cli_receipt_immutable_and_executable_mode(self):
        req = self.make(modes={"app/main.py": 0o700, "plugins/example.py": 0o600})
        one = execute(req)
        self.assertEqual(one["status"], "COMMITTED", one)
        executable = self.root / "versions/i1--b1/app/main.py"
        self.assertEqual(stat.S_IMODE(os.lstat(executable).st_mode), 0o700)
        receipt = Path(one["receipt"]["path"])
        saved = receipt.read_bytes()
        file_stat = os.lstat(executable)
        self.assertEqual(execute(req), one)
        self.assertEqual(inspect(req), one)
        self.assertEqual(recover(req), one)
        self.assertEqual(receipt.read_bytes(), saved)
        self.assertEqual(os.lstat(executable).st_ino, file_stat.st_ino)
        self.assertEqual(os.lstat(executable).st_mtime_ns, file_stat.st_mtime_ns)
        p = self.cli(req, "inspect")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["status"], "COMMITTED")

    def test_manifest_traversal_link_and_invalid_mode_reject(self):
        req = self.make()
        req["inputs"]["files"]["app/main.py"] = "0" * 64
        self.assertEqual(execute(req)["status"], "HOLD")
        bad = self.make(batch="b2", entries={"../escape": b"x"})
        self.assertEqual(execute(bad)["status"], "HOLD")
        mode = self.make(batch="bmode", modes={"app/main.py": 0o777})
        self.assertEqual(execute(mode)["error"]["code"], "INVALID_MODES")
        archive = Path(self.tmp.name) / "links.tar"
        with tarfile.open(archive, "w") as tar:
            member = tarfile.TarInfo("link")
            member.type = tarfile.SYMTYPE
            member.linkname = "../../etc/passwd"
            tar.addfile(member)
        linkreq = self.make(batch="b3")
        linkreq["inputs"]["archive"] = str(archive)
        linkreq["inputs"]["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        linkreq["inputs"]["files"] = {"link": hashlib.sha256(b"").hexdigest()}
        self.assertEqual(execute(linkreq)["status"], "HOLD")
        self.assertFalse((self.root / "escape").exists())

    def test_changed_during_snapshot_is_deterministically_rejected(self):
        req = self.make(batch="race", attempt="race-a",
                        entries={"payload.bin": b"x" * (16 * 1024 * 1024)})
        source = Path(req["inputs"]["archive"])
        partial = self.root / ".p2_artifacts/snapshots/i1--race--race-a.tar.partial"
        stop = threading.Event()
        ready = threading.Event()

        def mutate():
            self.wait_for(lambda: partial.exists() and partial.stat().st_size > 0, timeout=10)
            ready.set()
            flip = False
            while not stop.is_set():
                with source.open("r+b", buffering=0) as out:
                    out.seek(1024)
                    out.write(b"A" if flip else b"B")
                    out.flush()
                    os.fsync(out.fileno())
                flip = not flip

        original_chunk = impl.CHUNK
        impl.CHUNK = 4096
        thread = threading.Thread(target=mutate)
        thread.start()
        try:
            out = execute(req)
        finally:
            stop.set()
            thread.join(timeout=10)
            impl.CHUNK = original_chunk
        self.assertTrue(ready.is_set())
        self.assertEqual(out["status"], "HOLD", out)
        self.assertIn(out["error"]["code"], ("ARCHIVE_CHANGED_DURING_READ", "ARCHIVE_DIGEST_MISMATCH"))
        self.assertTrue(Path(out["error"]["log"]).is_file())
        self.assertFalse((self.root / ".p2_artifacts/receipts/i1--race.json").exists())
        self.assertFalse((self.root / "versions/i1--race").exists())
        log = json.loads(Path(out["error"]["log"]).read_text())
        self.assertEqual(log["stage"], "EXECUTE")

    def test_sigkill_during_snapshot_recovers_and_preserves_prior(self):
        prior = self.prior_snapshot()
        req = self.make(batch="kill-snap", attempt="a-snap",
                        entries={"payload.bin": b"s" * (32 * 1024 * 1024)})
        partial = self.root / ".p2_artifacts/snapshots/i1--kill-snap--a-snap.tar.partial"
        proc = self.start_cli(req)
        self.wait_for(lambda: partial.exists() and partial.stat().st_size > 0, proc)
        self.kill(proc)
        self.assertTrue(partial.exists())
        out = self.recover_cli(req)
        self.assertEqual(out["status"], "COMMITTED")
        self.assertFalse(partial.exists())
        errors = list((self.root / ".p2_artifacts/errors").glob("i1--kill-snap--*.json"))
        self.assertTrue(any(json.loads(p.read_text())["code"] == "INTERRUPTED_SNAPSHOT" for p in errors))
        self.assert_prior_unchanged(prior)

    def test_sigkill_during_file_write_recovers_without_overwriting_good_file(self):
        prior = self.prior_snapshot()
        req = self.make(batch="kill-file", attempt="a-file",
                        entries={"a-good.bin": b"ok", "z-large.bin": b"f" * (32 * 1024 * 1024)})
        good = self.root / "versions/i1--kill-file/a-good.bin"
        partial = self.root / "versions/i1--kill-file/z-large.bin.p2-part-a-file"
        proc = self.start_cli(req)
        self.wait_for(lambda: good.exists() and partial.exists() and partial.stat().st_size > 0, proc)
        good_before = (good.read_bytes(), os.lstat(good).st_ino, os.lstat(good).st_mtime_ns)
        self.kill(proc)
        self.assertTrue(partial.exists())
        self.recover_cli(req)
        good_after = (good.read_bytes(), os.lstat(good).st_ino, os.lstat(good).st_mtime_ns)
        self.assertEqual(good_after, good_before)
        self.assertFalse(partial.exists())
        errors = list((self.root / ".p2_artifacts/errors").glob("i1--kill-file--*.json"))
        self.assertTrue(any(json.loads(p.read_text())["code"] == "INTERRUPTED_FILE_WRITE" for p in errors))
        self.assert_prior_unchanged(prior)

    def test_sigkill_after_receipt_publish_recovers_as_idempotent_read(self):
        prior = self.prior_snapshot()
        req = self.make(batch="kill-receipt", attempt="a-receipt",
                        entries={"payload.bin": b"r" * (64 * 1024 * 1024)})
        receipt = self.root / ".p2_artifacts/receipts/i1--kill-receipt.json"
        installed = self.root / "versions/i1--kill-receipt/payload.bin"
        proc = self.start_cli(req)
        self.wait_for(lambda: receipt.exists() and installed.exists(), proc)
        receipt_before = receipt.read_bytes()
        stat_before = os.lstat(installed)
        self.kill(proc)
        self.recover_cli(req)
        self.assertEqual(receipt.read_bytes(), receipt_before)
        stat_after = os.lstat(installed)
        self.assertEqual((stat_after.st_ino, stat_after.st_mtime_ns),
                         (stat_before.st_ino, stat_before.st_mtime_ns))
        self.assert_prior_unchanged(prior)

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
