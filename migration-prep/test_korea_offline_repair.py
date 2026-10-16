"""Disposable syscall model. Not Korea root/systemd enforcement evidence."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import tarfile
import tempfile
import time
from types import SimpleNamespace
import unittest

FOLDER = Path(__file__).parent / "korea-offline-repair"
if not FOLDER.is_dir():
    FOLDER = Path(__file__).parent
spec = importlib.util.spec_from_file_location("pr99_offline_repair", FOLDER / "controlled_repair.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class Model(repair.Context):
    def __init__(self, root):
        self.trust_root = root
        self.uid = os.getuid()
        self.commands = []
        self.warning = ""
        self.netns_fail = False
        self.checkpoint_action = lambda name: None
        self.loaded = False
        self.active = False
        self.dropin = False
        self.reload_fail = False
        self.loaded_private = "yes"
        self.shared_changed = False

    def path(self, value):
        return self.trust_root / value.lstrip("/")

    def run(self, args):
        self.commands.append(args)
        out, err, code = "", "", 0
        if args[0].endswith("systemd-analyze"):
            err = self.warning
        elif args[1] == "is-enabled":
            out, code = "disabled\n", 1
        elif args[1] == "daemon-reload":
            self.loaded = True
            code = 1 if self.reload_fail else 0
        elif args[1:3] == ["show", "xuanjun-binance-shadow.service"]:
            v = {"ActiveState": "active" if self.active else "inactive", "SubState": "dead",
                 "MainPID": "0", "FragmentPath": str(self.path(repair.UNIT)),
                 "DropInPaths": "drift.conf" if self.dropin else "", "User": "xuanjun_binance",
                 "Group": "xuanjun_binance", "PrivateNetwork": self.loaded_private if self.loaded else "no",
                 "RestrictAddressFamilies": "AF_UNIX"}
            out = "\n".join(k + "=" + v for k, v in v.items())
        else:
            out = "\n".join("Id=" + name + "\nMainPID=1" for name in repair.SHARED)
            if self.loaded and self.shared_changed:
                out += "\nSubState=CHANGED"
        return SimpleNamespace(returncode=code, stdout=out, stderr=err)

    def boundary(self):
        repair.require(not self.netns_fail, "NETNS_UNAVAILABLE")

    def checkpoint(self, name):
        self.checkpoint_action(name)


class KoreaOfflineRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir(mode=0o700)
        self.ctx = Model(self.root)
        for path in ("/opt/xuanjun-binance/releases", "/opt/xuanjun-binance/venv/bin",
                     "/var/lib", "/etc/xuanjun-binance", "/etc/systemd/system", "/run",
                     "/etc/xuanjun-pr99-release", "/root/staging", repair.RELEASE):
            self.ctx.path(path).mkdir(parents=True, mode=0o700, exist_ok=True)
        self.folder = self.ctx.path("/root/staging/package")
        self.folder.mkdir(mode=0o700)
        self.archive = self.ctx.path("/root/staging/review.tar.gz")
        self.files = {name: (FOLDER / name).read_bytes() for name in
                      ("controlled_repair.py", "offline.service", "installed-runtime-manifest.json")}
        self.binding = {"schema_version": 1, "source_commit": "a" * 40,
                        "files": {name: repair.sha(data) for name, data in self.files.items()}}
        self.files["REPAIR_BINDING.json"] = repair.encoded(self.binding)
        self._package()
        fixture = FOLDER / "approved-runtime-632bbe6f.tar.gz"
        self.assertEqual(repair.sha(fixture.read_bytes()),
                         "f7cba56c2c45910901cdbd44056ad7c971a7497ffe67518a4adefb40ef660ba9")
        with tarfile.open(fixture) as t:
            for m in t.getmembers():
                self._write(self.ctx.path(repair.RELEASE) / m.name, t.extractfile(m).read())
        self.ctx.path(repair.CURRENT).symlink_to(repair.RELEASE)
        # Test prefixes do not remap absolute symlinks. readlink is checked,
        # while all explicit runtime reads use ctx.path(RELEASE).
        unit = (self.ctx.path(repair.RELEASE) / "migration-prep/korea/xuanjun-binance-shadow.service.in").read_bytes()
        self._write(self.ctx.path(repair.UNIT), unit)
        self._write(self.ctx.path("/opt/xuanjun-binance/venv/bin/python"), b"MODEL_PYTHON_NOT_EXECUTABLE")
        tx = {"schema_version": 1, "transaction_id": "install-f887b085508e3ed4",
              "manifest_sha256": repair.OLD_MANIFEST, "content_sha256": "d21dad5f79138f7795903ed95108baa5bfead1be4f13f74247c78c336e79f659",
              "release_path": repair.RELEASE, "current_target": repair.RELEASE, "unit_path": repair.UNIT,
              "unit_sha256": repair.OLD_UNIT, "venv_path": "/opt/xuanjun-binance/venv",
              "venv_python_sha256": repair.sha(b"MODEL_PYTHON_NOT_EXECUTABLE"),
              "owned_objects": [], "preserved_on_uninstall": []}
        self.old_tx = repair.encoded(tx)
        self._write(self.ctx.path(repair.TX), self.old_tx)
        self.ctx.old_tx_sha = repair.sha(self.old_tx)
        now = int(time.time())
        self.approval = {"schema_version": 1, "action": repair.ACTION, "host": repair.HOST,
                         "max_attempts": 1, "source_commit": self.binding["source_commit"],
                         "artifact_sha256": repair.sha(self.archive.read_bytes()),
                         "helper_sha256": repair.sha(self.files["controlled_repair.py"]),
                         "unit_sha256": repair.sha(self.files["offline.service"]),
                         "old_transaction_sha256": self.ctx.old_tx_sha, "service_start_allowed": False,
                         "phase_c_allowed": False, "approval_comment_id": 990001,
                         "issued_at": now - 2, "expires_at": now + 600}
        self._pin()

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)

    def _package(self):
        with tarfile.open(self.archive, "w:gz") as t:
            for name, data in self.files.items():
                m = tarfile.TarInfo(name); m.mode = 0o600; m.size = len(data)
                t.addfile(m, io.BytesIO(data))
                self._write(self.folder / name, data)
        self.archive.chmod(0o600)

    def _pin(self):
        body = "<!-- PR99_OFFLINE_REPAIR_APPROVAL_V1\n" + json.dumps(self.approval) + "\nPR99_OFFLINE_REPAIR_APPROVAL_V1 -->"
        self._write(self.ctx.path(repair.PIN), repair.encoded({"approval_comment_id": self.approval["approval_comment_id"],
                    "approval_body": body, "approval_body_sha256": repair.sha(body.encode())}))

    def _apply(self):
        return repair.apply(self.folder, self.archive, self.ctx)

    def _hold(self, reason):
        with self.assertRaisesRegex(repair.Hold, reason):
            self._apply()

    def _unchanged(self):
        self.assertEqual(repair.sha(self.ctx.path(repair.UNIT).read_bytes()), repair.OLD_UNIT)
        self.assertEqual(self.ctx.path(repair.TX).read_bytes(), self.old_tx)

    def test_success_changes_only_unit_hash_in_transaction(self):
        before = {str(p): repair.sha(p.read_bytes()) for p in self.ctx.path(repair.RELEASE).rglob("*") if p.is_file()}
        r = self._apply()
        self.assertEqual(r["status"], "OFFLINE_REPAIR_PASS_WITH_SCOPE_LIMITS")
        after = json.loads(self.ctx.path(repair.TX).read_bytes())
        original = json.loads(self.old_tx)
        self.assertEqual({k for k in after if after[k] != original[k]}, {"unit_sha256"})
        self.assertEqual(before, {str(p): repair.sha(p.read_bytes()) for p in self.ctx.path(repair.RELEASE).rglob("*") if p.is_file()})
        self.assertEqual(os.readlink(self.ctx.path(repair.CURRENT)), repair.RELEASE)
        self.assertFalse(self.ctx.path("/run/xuanjun-binance-install.lock").exists())
        self.assertEqual((self.ctx.path(repair.WORK) / "transaction.before.json").read_bytes(), self.old_tx)
        self.assertFalse(any(any(x in c for x in ("start", "enable", "stop", "restart")) for c in self.ctx.commands))
        self.assertEqual(r["started_service_confinement"], "NOT_EXERCISED")

    def test_replay_is_refused(self):
        self._apply()
        self._hold("ATTEMPT_ALREADY_EXISTS")

    def test_bad_approval_scope_is_rejected_before_lock(self):
        for key, bad in (("action", "install"), ("host", "TOKYO"), ("max_attempts", 2),
                         ("source_commit", "b" * 40), ("artifact_sha256", "0" * 64),
                         ("helper_sha256", "0" * 64), ("unit_sha256", "0" * 64),
                         ("old_transaction_sha256", "0" * 64), ("service_start_allowed", True),
                         ("phase_c_allowed", True), ("approval_comment_id", 6207630392),
                         ("expires_at", int(time.time()) - 1)):
            with self.subTest(key=key):
                old = self.approval[key]; self.approval[key] = bad; self._pin()
                self._hold("APPROVAL|OLD_OR_WRONG")
                self._unchanged()
                self.assertFalse(self.ctx.path("/run/xuanjun-binance-install.lock").exists())
                self.approval[key] = old

    def test_modified_approval_body_rejected(self):
        p = self.ctx.path(repair.PIN); v = json.loads(p.read_bytes()); v["approval_body"] += "x"
        self._write(p, repair.encoded(v)); self._hold("APPROVAL_BODY_HASH"); self._unchanged()

    def test_group_writable_pin_parent_rejected(self):
        self.ctx.path(repair.PIN).parent.chmod(0o770)
        self._hold("UNTRUSTED"); self._unchanged()

    def test_old_transaction_drift_refused(self):
        self._write(self.ctx.path(repair.TX), self.old_tx + b"\n")
        self._hold("OLD_TRANSACTION_CHANGED")

    def test_old_unit_drift_refused(self):
        self._write(self.ctx.path(repair.UNIT), b"changed")
        self._hold("OLD_UNIT_CHANGED")

    def test_runtime_drift_refused(self):
        self._write(self.ctx.path(repair.RELEASE) / "migration-prep/korea/get_only_policy.py", b"changed")
        self._hold("RUNTIME_BYTES_CHANGED"); self._unchanged()

    def test_current_drift_refused(self):
        self.ctx.path(repair.CURRENT).unlink(); self.ctx.path(repair.CURRENT).symlink_to("/unapproved")
        self._hold("CURRENT_CHANGED"); self._unchanged()

    def test_netns_unavailable_refused_before_replacement(self):
        self.ctx.netns_fail = True
        self._hold("NETNS_UNAVAILABLE"); self._unchanged()

    def test_zero_exit_systemd_diagnostic_refused(self):
        self.ctx.warning = "Unknown lvalue 'PrivateNetwork'"
        self._hold("SYSTEMD_VERIFY_DIAGNOSTIC"); self._unchanged()

    def test_active_service_or_dropin_refused(self):
        self.ctx.active = True
        self._hold("SERVICE_IDENTITY_OR_STATE"); self._unchanged()

    def test_dropin_refused(self):
        self.ctx.dropin = True
        self._hold("SERVICE_IDENTITY_OR_STATE"); self._unchanged()

    def test_manager_must_load_private_network(self):
        self.ctx.loaded_private = "no"
        self._hold("MANAGER_NETWORK_PROFILE_NOT_LOADED")

    def test_partial_failure_preserves_old_transaction_and_backup(self):
        def fail(name):
            if name == "after_unit":
                raise repair.Hold("INJECTED_PARTIAL")
        self.ctx.checkpoint_action = fail
        self._hold("INJECTED_PARTIAL")
        self.assertEqual(self.ctx.path(repair.TX).read_bytes(), self.old_tx)
        work = self.ctx.path(repair.WORK)
        self.assertEqual(repair.sha((work / "unit.before").read_bytes()), repair.OLD_UNIT)
        self.assertEqual(json.loads((work / "receipt.json").read_bytes())["status"], "HOLD_PRESERVE_EVIDENCE")
        self.assertTrue(self.ctx.path("/run/xuanjun-binance-install.lock").exists())
        self._hold("ATTEMPT_ALREADY_EXISTS")

    def test_reload_failure_is_not_success(self):
        self.ctx.reload_fail = True
        self._hold("DAEMON_RELOAD_FAILED")
        self.assertTrue(self.ctx.path("/run/xuanjun-binance-install.lock").exists())

    def test_lock_release_failure_prevents_pass(self):
        def change(name):
            if name == "before_unlock":
                (self.ctx.path("/run/xuanjun-binance-install.lock") / "foreign").write_text("hold")
        self.ctx.checkpoint_action = change
        with self.assertRaises(OSError):
            self._apply()
        receipt = json.loads((self.ctx.path(repair.WORK) / "receipt.json").read_bytes())
        self.assertEqual(receipt["status"], "HOLD_PRESERVE_EVIDENCE")

    def test_sigterm_preserves_partial_evidence(self):
        old = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(repair.Hold("SIGTERM")))
        self.ctx.checkpoint_action = lambda name: signal.raise_signal(signal.SIGTERM) if name == "after_unit" else None
        try:
            self._hold("SIGTERM")
        finally:
            signal.signal(signal.SIGTERM, old)
        self.assertEqual(self.ctx.path(repair.TX).read_bytes(), self.old_tx)
        self.assertTrue((self.ctx.path(repair.WORK) / "receipt.json").exists())

    def test_existing_original_lock_blocks_repair(self):
        self.ctx.path("/run/xuanjun-binance-install.lock").mkdir()
        self._hold("ORIGINAL_INSTALL_LOCK_EXISTS"); self._unchanged()

    def test_concurrent_transaction_change_detected(self):
        self.ctx.checkpoint_action = lambda name: self._write(self.ctx.path(repair.TX), b"foreign") if name == "before_replace" else None
        self._hold("TRANSACTION_CONCURRENT_CHANGE")
        self.assertEqual(repair.sha(self.ctx.path(repair.UNIT).read_bytes()), repair.OLD_UNIT)

    def test_shared_service_change_holds_without_rollback(self):
        self.ctx.shared_changed = True
        self._hold("SHARED_NAMED_UNITS_CHANGED")
        self.assertEqual(self.ctx.path(repair.UNIT).read_bytes(), self.files["offline.service"])

    def test_extracted_extra_file_refused(self):
        self._write(self.folder / "extra", b"x")
        self._hold("EXTRACTED_FILE_SET"); self._unchanged()

    def test_archive_symlink_refused(self):
        with tarfile.open(self.archive, "w:gz") as t:
            m = tarfile.TarInfo("link"); m.type = tarfile.SYMTYPE; m.linkname = "/etc/passwd"; t.addfile(m)
        self._hold("ARCHIVE_MEMBER_INVALID"); self._unchanged()

    def test_cross_process_race_allows_only_one_attempt(self):
        read_fd, write_fd = os.pipe()
        children = []
        for _ in range(2):
            pid = os.fork()
            if pid == 0:
                os.close(write_fd)
                os.read(read_fd, 1)
                try:
                    self._apply()
                except BaseException:
                    os._exit(2)
                os._exit(0)
            children.append(pid)
        os.close(read_fd)
        os.write(write_fd, b"xx"); os.close(write_fd)
        statuses = [os.waitpid(pid, 0)[1] for pid in children]
        self.assertEqual(sorted(os.waitstatus_to_exitcode(s) for s in statuses), [0, 2])
        self.assertEqual(json.loads((self.ctx.path(repair.WORK) / "receipt.json").read_bytes())["status"],
                         "OFFLINE_REPAIR_PASS_WITH_SCOPE_LIMITS")

    def test_lock_inode_replacement_prevents_pass(self):
        def replace(name):
            if name == "before_unlock":
                p = self.ctx.path("/run/xuanjun-binance-install.lock")
                p.rename(p.with_name(p.name + ".preserved")); p.mkdir(mode=0o700)
        self.ctx.checkpoint_action = replace
        self._hold("LOCK_IDENTITY_CHANGED")

    def test_transaction_symlink_is_not_read_or_overwritten(self):
        p = self.ctx.path(repair.TX)
        original = p.with_name("preserved.json"); p.rename(original); p.symlink_to(original)
        self._hold("UNTRUSTED_TYPE")
        self.assertTrue(p.is_symlink())
        self.assertEqual(original.read_bytes(), self.old_tx)


if __name__ == "__main__":
    unittest.main()
