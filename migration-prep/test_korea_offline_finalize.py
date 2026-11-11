"""Model-only postflight tests using original approved runtime fixture bytes."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import time
import unittest
from unittest import mock

import test_korea_offline_repair as base

spec = importlib.util.spec_from_file_location("pr99_finalize", base.FOLDER / "finalize_repair.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
c = f.c


class KoreaOfflineFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = base.KoreaOfflineRepairTests("runTest")
        self.fixture.setUp()
        self.ctx = self.fixture.ctx
        # Reproduce the exact predecessor's stopped post-write failure in the
        # disposable model. Never call an installed real helper in these tests.
        self.ctx.loaded_private = "no"
        with self.assertRaises(base.repair.Hold):
            self.fixture._apply()
        self.ctx.loaded_private = "yes"
        self.old_work = self.ctx.path(c.WORK)
        p = self.old_work / "receipt.json"
        v = json.loads(p.read_bytes()); v["approval_comment_id"] = 6208184098
        self.fixture._write(p, c.encoded(v))
        self.old_receipt = p.read_bytes()
        self.ctx.prior_source = v["source_commit"]
        self.ctx.prior_artifact = v["artifact_sha256"]
        self.unit_bytes = self.ctx.path(c.UNIT).read_bytes()
        self.tx_bytes = self.ctx.path(c.TX).read_bytes()
        self.ctx.final_transaction_sha = c.sha(self.tx_bytes)
        self.fixture.folder = self.ctx.path("/root/staging/finalize-package")
        self.fixture.folder.mkdir(mode=0o700)
        self.fixture.archive = self.ctx.path("/root/staging/finalize.tar.gz")
        self.fixture.files["finalize_repair.py"] = (base.FOLDER / "finalize_repair.py").read_bytes()
        self.fixture.binding = {"schema_version": 1, "source_commit": "b" * 40,
                                "files": {k: c.sha(v) for k, v in self.fixture.files.items() if k != "REPAIR_BINDING.json"}}
        self.fixture.files["REPAIR_BINDING.json"] = c.encoded(self.fixture.binding)
        self.fixture._package()
        now = int(time.time())
        self.a = {"schema_version": 1, "action": f.ACTION, "host": c.HOST,
                  "source_commit": "b" * 40, "artifact_sha256": c.sha(self.fixture.archive.read_bytes()),
                  "finalizer_sha256": c.sha(self.fixture.files["finalize_repair.py"]),
                  "checker_sha256": f.CHECKER_SHA, "unit_sha256": f.UNIT_SHA,
                  "transaction_sha256": self.ctx.final_transaction_sha,
                  "prior_repair_approval_comment_id": 6208184098, "max_attempts": 1,
                  "adopt_root_verified_retained_lock": True, "unit_write_allowed": False,
                  "transaction_write_allowed": False, "reload_allowed": False,
                  "service_start_allowed": False, "phase_c_allowed": False,
                  "approval_comment_id": 990002, "issued_at": now - 2, "expires_at": now + 600}
        s = self.ctx.path("/run/xuanjun-binance-install.lock").stat()
        self.pin = {"retained_lock": {"device": s.st_dev, "inode": s.st_ino},
                    "failed_receipt_sha256": c.sha(self.old_receipt)}
        self.pin_write()
        self.ctx.commands = []

    def tearDown(self):
        self.fixture.tearDown()

    def pin_write(self):
        body = "<!-- PR99_OFFLINE_FINALIZE_APPROVAL_V1\n" + json.dumps(self.a) + "\nPR99_OFFLINE_FINALIZE_APPROVAL_V1 -->"
        pin = dict(self.pin, approval_comment_id=self.a["approval_comment_id"],
                   approval_body=body, approval_body_sha256=c.sha(body.encode()))
        self.fixture._write(self.ctx.path(f.PIN), c.encoded(pin))

    def finalize(self):
        return f.finalize(self.fixture.folder, self.fixture.archive, self.ctx)

    def hold(self, reason):
        with self.assertRaisesRegex(c.Hold, reason):
            self.finalize()
        self.assertEqual(self.ctx.path(c.UNIT).read_bytes(), self.unit_bytes)
        self.assertEqual(self.ctx.path(c.TX).read_bytes(), self.tx_bytes)

    def test_success_no_reapply_reload_or_old_receipt_rewrite(self):
        r = self.finalize()
        self.assertEqual(r["status"], "OFFLINE_REPAIR_FINALIZE_PASS_WITH_SCOPE_LIMITS")
        self.assertEqual((self.old_work / "receipt.json").read_bytes(), self.old_receipt)
        self.assertEqual(self.ctx.path(c.UNIT).read_bytes(), self.unit_bytes)
        self.assertEqual(self.ctx.path(c.TX).read_bytes(), self.tx_bytes)
        self.assertFalse(self.ctx.path("/run/xuanjun-binance-install.lock").exists())
        self.assertFalse(any(any(x in cmd for x in ("start", "enable", "stop", "restart", "daemon-reload")) for cmd in self.ctx.commands))

    def test_old_or_wrong_approval_refused_before_attempt(self):
        for key, bad in (("action", c.ACTION), ("approval_comment_id", 6208184098),
                         ("adopt_root_verified_retained_lock", False), ("unit_write_allowed", True),
                         ("reload_allowed", True), ("max_attempts", 2), ("phase_c_allowed", True),
                         ("source_commit", "c" * 40), ("checker_sha256", "0" * 64),
                         ("expires_at", int(time.time()) - 1)):
            with self.subTest(key=key):
                old = self.a[key]; self.a[key] = bad; self.pin_write()
                self.hold("APPROVAL|OLD_OR_WRONG")
                self.assertFalse(self.ctx.path(f.WORK).exists())
                self.a[key] = old

    def test_anchor_must_pin_real_lock_inode(self):
        self.pin["retained_lock"]["inode"] += 1; self.pin_write()
        self.hold("RETAINED_LOCK_IDENTITY_OR_CONTENT")

    def test_nonempty_lock_is_not_cleaned(self):
        p = self.ctx.path("/run/xuanjun-binance-install.lock") / "foreign"
        p.write_bytes(b"preserve")
        self.hold("RETAINED_LOCK_IDENTITY_OR_CONTENT")
        self.assertEqual(p.read_bytes(), b"preserve")

    def test_changed_failed_receipt_refused(self):
        self.fixture._write(self.old_work / "receipt.json", self.old_receipt + b"\n")
        self.hold("FAILED_RECEIPT_CHANGED")

    def test_other_failure_cannot_be_finalized(self):
        v = json.loads(self.old_receipt); v["error"] = "OTHER_FAILURE"
        raw = c.encoded(v); self.fixture._write(self.old_work / "receipt.json", raw)
        self.pin["failed_receipt_sha256"] = c.sha(raw); self.pin_write()
        self.hold("FAILED_RECEIPT_SCOPE_MISMATCH")

    def test_unchanged_shared_units_required(self):
        self.ctx.shared_changed = True
        self.hold("SHARED_NAMED_UNITS_CHANGED")

    def test_typed_blacklist_rejected_even_if_unit_text_is_correct(self):
        self.ctx.dbus_family = '(bas) false 1 "AF_UNIX"'
        self.hold("MANAGER_NETWORK_PROFILE_NOT_LOADED")

    def test_zero_exit_verify_warning_refused(self):
        self.ctx.warning = "unsupported constraint"
        self.hold("SYSTEMD_VERIFY_DIAGNOSTIC")

    def test_runtime_drift_refused(self):
        p = self.ctx.path(c.RELEASE) / "migration-prep/korea/get_only_policy.py"
        p.write_bytes(b"changed")
        self.hold("RUNTIME_BYTES_CHANGED")

    def test_venv_identity_refused(self):
        self.ctx.path("/opt/xuanjun-binance/venv/bin/python").write_bytes(b"changed")
        self.hold("VENV_PYTHON_CHANGED")

    def test_backups_are_verified(self):
        self.fixture._write(self.old_work / "unit.before", b"changed")
        self.hold("OLD_UNIT_BACKUP_CHANGED")

    def test_lock_drift_at_unlock_refused(self):
        def drift(name):
            if name == "finalize_before_unlock":
                p = self.ctx.path("/run/xuanjun-binance-install.lock")
                p.rename(p.with_name(p.name + ".preserved")); p.mkdir(mode=0o700)
        self.ctx.checkpoint_action = drift
        self.hold("RETAINED_LOCK_IDENTITY_OR_CONTENT")

    def test_sigterm_preserves_old_evidence_and_lock(self):
        old = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(c.Hold("SIGTERM")))
        self.ctx.checkpoint_action = lambda _: signal.raise_signal(signal.SIGTERM)
        try:
            self.hold("SIGTERM")
        finally:
            signal.signal(signal.SIGTERM, old)
        self.assertTrue(self.ctx.path("/run/xuanjun-binance-install.lock").exists())
        self.assertEqual((self.old_work / "receipt.json").read_bytes(), self.old_receipt)

    def test_rmdir_failure_cannot_pass(self):
        with mock.patch.object(Path, "rmdir", side_effect=PermissionError("MODEL")):
            with self.assertRaises(PermissionError):
                self.finalize()
        v = json.loads((self.ctx.path(f.WORK) / "receipt.json").read_bytes())
        self.assertEqual(v["status"], "HOLD_PRESERVE_EVIDENCE")

    def test_replay_refused(self):
        self.finalize()
        self.hold("FINALIZE_ALREADY_ATTEMPTED")

    def test_cross_process_finalizers_only_one_consumes(self):
        r, w = os.pipe(); children = []
        for _ in range(2):
            pid = os.fork()
            if pid == 0:
                os.close(w); os.read(r, 1)
                try:
                    self.finalize()
                except BaseException:
                    os._exit(2)
                os._exit(0)
            children.append(pid)
        os.close(r); os.write(w, b"xx"); os.close(w)
        self.assertEqual(sorted(os.waitstatus_to_exitcode(os.waitpid(p, 0)[1]) for p in children), [0, 2])


if __name__ == "__main__":
    unittest.main()
