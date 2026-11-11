import argparse
import copy
import hashlib
import io
import json
import os
import multiprocessing
from pathlib import Path
import subprocess
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import runtime_contract as c


class Admission(unittest.TestCase):
    def setUp(self):
        self.value = {"decision": "APPROVED_WITH_EXACT_PRECONDITIONS", "action": c.ACTION,
                      "max_attempts": 1, "source_commit": "a" * 40, "script_sha256": "b" * 64,
                      "source_host": c.TOKYO, "target_host": c.KOREA, "issued_at": 100, "expires_at": 200}
        self.record = {"id": 123, "issue_url": "https://api.github.com/repos/" + c.REPO + "/issues/99",
                       "user": {"id": 332398908, "login": "huhongchuan0422-creator", "type": "User"}}
        self.args = argparse.Namespace(approval_id=123, approval_sha256="", source_commit="a" * 40,
                                       script_sha256="b" * 64, confirm_independent_auditor=True)

    def bind(self):
        self.record["body"] = "<!-- PR99_S06_RUNTIME_APPROVAL_V1\n" + json.dumps(self.value) + "\nPR99_S06_RUNTIME_APPROVAL_V1 -->"
        self.args.approval_sha256 = c.sha(self.record["body"].encode())

    def test_valid_new_action(self):
        self.bind()
        self.assertEqual(c.verify_approval(self.record, self.args, 150), self.value)

    def test_old_copy_permission_rejected(self):
        self.value["action"] = "PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1"
        self.bind()
        with self.assertRaisesRegex(c.Hold, "APPROVAL_ACTION"):
            c.verify_approval(self.record, self.args, 150)

    def test_forged_author_or_pr(self):
        for field, value in (("id", 1), ("login", "someone"), ("type", "Bot")):
            with self.subTest(field=field):
                r = copy.deepcopy(self.record)
                self.bind(); r["body"] = self.record["body"]
                r["user"][field] = value
                with self.assertRaisesRegex(c.Hold, "APPROVAL_AUTHOR"):
                    c.verify_approval(r, self.args, 150)
        self.record["issue_url"] = self.record["issue_url"].replace("/99", "/122")
        with self.assertRaisesRegex(c.Hold, "APPROVAL_ID_OR_PR"):
            c.verify_approval(self.record, self.args, 150)

    def test_exact_source_and_script(self):
        for field in ("source_commit", "script_sha256", "source_host", "target_host"):
            with self.subTest(field=field):
                old = self.value[field]; self.value[field] = "wrong"; self.bind()
                with self.assertRaisesRegex(c.Hold, "APPROVAL_BINDING"):
                    c.verify_approval(self.record, self.args, 150)
                self.value[field] = old

    def test_time_bool_attempts_and_owner_confirmation(self):
        self.bind()
        for now in (99, 200):
            with self.assertRaisesRegex(c.Hold, "APPROVAL_TIME"):
                c.verify_approval(self.record, self.args, now)
        self.value["max_attempts"] = True; self.bind()
        with self.assertRaisesRegex(c.Hold, "APPROVAL_ACTION"):
            c.verify_approval(self.record, self.args, 150)
        self.args.confirm_independent_auditor = False
        with self.assertRaisesRegex(c.Hold, "INDEPENDENT"):
            c.verify_approval(self.record, self.args, 150)

    def test_body_change(self):
        self.bind(); self.record["body"] += " "
        with self.assertRaisesRegex(c.Hold, "APPROVAL_BODY"):
            c.verify_approval(self.record, self.args, 150)


class FilesAndArchive(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s06-synthetic-", dir="/root")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self):
        files = {"units/" + n: b"[Service]\nUser=example\n" for n in c.UNITS}
        files["dropins/provider-health-alert.conf"] = b"[Service]\nRestart=on-failure\n"
        files["private-runtime.json"] = b'{"environment_files_opened": false}\n'
        raw = c.make_tar(files)
        return files, raw, {"archive_sha256": c.sha(raw), "files": {p: c.sha(b) for p, b in files.items()}}

    def test_exact_archive_members_and_byte_check(self):
        files, raw, expected = self.fixture()
        self.assertEqual(c.verify_archive(raw, expected), files)
        expected["files"]["units/secure-secrets-portal.service"] = "0" * 64
        with self.assertRaisesRegex(c.Hold, "ARCHIVE_FILE_HASH"):
            c.verify_archive(raw, expected)

    def test_wrong_or_added_member_rejected_even_self_consistent_manifest(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                           ("units/secure-secrets-portal.service", tarfile.SYMTYPE),
                           ("environment.secret", tarfile.REGTYPE)):
            with self.subTest(name=name, kind=kind):
                b = io.BytesIO()
                with tarfile.open(fileobj=b, mode="w:gz") as t:
                    m = tarfile.TarInfo(name); m.type = kind
                    t.addfile(m, io.BytesIO(b""))
                raw = b.getvalue()
                with self.assertRaises(c.Hold):
                    c.verify_archive(raw, {"archive_sha256": c.sha(raw), "files": {name: c.sha(b"")}})

    def test_stable_private_file_and_replay(self):
        p = self.root / "file"
        c.write_new(p, b"private")
        self.assertEqual(c.stable_file(p, private=True), b"private")
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            c.write_new(p, b"overwrite")
        self.assertEqual(p.read_bytes(), b"private")

    def test_symlink_hardlink_and_writable_input_rejected(self):
        p = self.root / "original"; c.write_new(p, b"x")
        link = self.root / "link"; link.symlink_to(p)
        with self.assertRaises(OSError): c.stable_file(link)
        os.link(p, self.root / "hardlink")
        with self.assertRaises(c.Hold): c.stable_file(p)
        q = self.root / "writable"; c.write_new(q, b"x"); q.chmod(0o666)
        with self.assertRaises(c.Hold): c.stable_file(q)

    def test_read_limit_and_missing_file_fail(self):
        p = self.root / "file"; c.write_new(p, b"abcd")
        with self.assertRaisesRegex(c.Hold, "FILE_IDENTITY_OR_SIZE"):
            c.stable_file(p, 3)
        with self.assertRaises(FileNotFoundError): c.stable_file(self.root / "absent")

    def test_real_synthetic_capture_encrypt_verify_and_duplicate_refusal(self):
        stage = self.root / "capture"
        fixtures = self.root / "units"; fixtures.mkdir(mode=0o700)
        paths = []
        for i, original in enumerate(c.FILES):
            p = fixtures / Path(original).name
            c.write_new(p, ("[Service]\nUser=synthetic\n# test sentinel " + str(i) + "\n").encode())
            paths.append(str(p))
        with patch.object(c, "SOURCE", stage), patch.object(c, "FILES", tuple(paths)), \
             patch.object(c.os, "uname", return_value=argparse.Namespace(nodename=c.TOKYO)), \
             patch.object(c, "unit_metadata", return_value={"synthetic": {"MainPID": "1"}}), \
             patch.object(c, "listener_metadata", return_value=[]):
            c.capture(int(c.time.time()) + 30)
            expected = json.loads((stage / "receipt.json").read_text())
            self.assertEqual(expected["file_count"], 12)
            r = subprocess.run(["/usr/bin/openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-md", "sha256",
                                "-in", str(stage / "payload.enc"), "-pass", "file:" + str(stage / "payload.key")],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(len(c.verify_archive(r.stdout, expected)), 12)
            before = (stage / "receipt.json").read_bytes()
            with self.assertRaises(FileExistsError): c.capture(int(c.time.time()) + 30)
            self.assertEqual((stage / "receipt.json").read_bytes(), before)
            self.assertFalse((stage / "failure.json").exists())

    def test_failure_preserves_attempt_and_does_not_cleanup(self):
        stage = self.root / "capture"
        with patch.object(c, "SOURCE", stage), \
             patch.object(c.os, "uname", return_value=argparse.Namespace(nodename=c.TOKYO)), \
             patch.object(c, "unit_metadata", side_effect=c.Hold("SYNTHETIC_DRIFT")):
            with self.assertRaises(c.Hold): c.capture(int(c.time.time()) + 30)
        self.assertTrue((stage / "capture.started").exists())
        self.assertEqual(json.loads((stage / "failure.json").read_text())["reason"], "SYNTHETIC_DRIFT")
        self.assertFalse((stage / "receipt.json").exists())

    def test_source_expiry_precedes_attempt(self):
        stage = self.root / "capture"
        with patch.object(c, "SOURCE", stage), \
             patch.object(c.os, "uname", return_value=argparse.Namespace(nodename=c.TOKYO)):
            with self.assertRaisesRegex(c.Hold, "SOURCE_ROOT_HOST_OR_TIME"):
                c.capture(0)
        self.assertFalse(stage.exists())

    def test_manager_drift_has_failure_no_success(self):
        stage = self.root / "capture"
        fixtures = []
        for n in c.FILES:
            p = self.root / Path(n).name
            c.write_new(p, b"[Service]\nUser=synthetic\n")
            fixtures.append(str(p))
        with patch.object(c, "SOURCE", stage), patch.object(c, "FILES", tuple(fixtures)), \
             patch.object(c.os, "uname", return_value=argparse.Namespace(nodename=c.TOKYO)), \
             patch.object(c, "unit_metadata", side_effect=[{"pid": "1"}, {"pid": "2"}]), \
             patch.object(c, "listener_metadata", return_value=[]):
            with self.assertRaisesRegex(c.Hold, "MANAGER_CHANGED"):
                c.capture(int(c.time.time()) + 30)
        self.assertTrue((stage / "failure.json").exists())
        self.assertFalse((stage / "receipt.json").exists())

    def test_exact_loaded_unit_and_dropin_contract(self):
        def fake(args):
            name = args[2]
            text = "LoadState=loaded\nFragmentPath=/etc/systemd/system/" + name + "\nDropInPaths=\n"
            return subprocess.CompletedProcess(args, 0, stdout=text.encode(), stderr=b"")
        with patch.object(c, "command", side_effect=fake):
            with self.assertRaisesRegex(c.Hold, "UNIT_DROPIN_SET_DRIFT"):
                c.unit_metadata()

    def test_process_competition_one_attempt(self):
        stage = self.root / "capture"
        ctx = multiprocessing.get_context("fork")
        gate, results = ctx.Event(), ctx.Queue()
        def invoke():
            with patch.object(c, "SOURCE", stage), \
                 patch.object(c.os, "uname", return_value=argparse.Namespace(nodename=c.TOKYO)), \
                 patch.object(c, "unit_metadata", side_effect=c.Hold("SYNTHETIC_STOP")):
                gate.wait(5)
                try: c.capture(int(c.time.time()) + 30)
                except Exception as e: results.put(type(e).__name__)
        children = [ctx.Process(target=invoke) for _ in range(2)]
        for p in children: p.start()
        gate.set()
        for p in children: p.join(10); self.assertFalse(p.is_alive()); self.assertEqual(p.exitcode, 0)
        self.assertCountEqual([results.get(timeout=2) for _ in children], ["Hold", "FileExistsError"])
        self.assertTrue((stage / "capture.started").exists())
        self.assertFalse((stage / "receipt.json").exists())

    def test_actual_sigterm_preserves_unknown_attempt(self):
        stage = self.root / "capture"
        ctx = multiprocessing.get_context("fork")
        def invoke():
            signal.signal(signal.SIGTERM, c.signal_hold)
            with patch.object(c, "SOURCE", stage), \
                 patch.object(c.os, "uname", return_value=argparse.Namespace(nodename=c.TOKYO)), \
                 patch.object(c, "unit_metadata", side_effect=lambda: os.kill(os.getpid(), signal.SIGTERM)):
                try: c.capture(int(c.time.time()) + 30)
                except c.Hold: return
                raise AssertionError("signal was not handled")
        p = ctx.Process(target=invoke); p.start(); p.join(10)
        self.assertFalse(p.is_alive()); self.assertEqual(p.exitcode, 0)
        receipt = json.loads((stage / "failure.json").read_text())
        self.assertEqual(receipt["reason"], "SIGNAL_15")
        self.assertFalse((stage / "receipt.json").exists())

    def test_ssh_failure_persists_stderr_and_forbids_log_overwrite(self):
        # A real local child replaces ssh, never opens a network connection.
        child = [sys.executable, "-I", "-B", "-c", "import sys;sys.stderr.write('synthetic diagnostic');sys.exit(7)"]
        with (self.root / "stdout").open("xb") as out:
            with self.assertRaisesRegex(c.Hold, "SSH_STEP_001_EXIT_7"):
                c.ssh_step(child, "unused", "unused", out, self.root, 1)
            with self.assertRaises(FileExistsError):
                c.ssh_step(child, "unused", "unused", out, self.root, 1)
        log = self.root / "ssh-step-001.stderr.log"
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)
        self.assertEqual(log.read_text(), "synthetic diagnostic")


if __name__ == "__main__":
    unittest.main()
