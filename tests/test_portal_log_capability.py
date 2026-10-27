import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "capability", ROOT / "deploy/pr122-portal-log-capability/portal_log_capability.py")
CAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAP)


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest("Filesystem ownership tests require isolated root container")
        self.tmp = tempfile.TemporaryDirectory(prefix="pr122-cap-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir(mode=0o700)
        self.source = self.base / "app/scripts/secure_secrets_portal_server.py"
        self.source.parent.mkdir(parents=True)
        if os.environ.get("PR122_CAPABILITY_SYNTHETIC_TEST") == "1":
            # Hosted CI has no production file. Only the test namespace receives
            # synthetic source pins; no production script accepts env overrides.
            self.assertEqual(CAP.SOURCE_SHA256, "528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006")
            self.original = ("class PortalHandler:\n" + CAP.OLD_METHOD).encode()
            pin = mock.patch.object(CAP, "SOURCE_SHA256", hashlib.sha256(self.original).hexdigest())
            pin.start()
            self.addCleanup(pin.stop)
            candidate = CAP.build_candidate(self.original)
            pin2 = mock.patch.object(CAP, "CANDIDATE_SHA256", hashlib.sha256(candidate).hexdigest())
            pin2.start()
            self.addCleanup(pin2.stop)
        else:
            self.original = Path(os.environ["PR122_PORTAL_SOURCE"]).read_bytes()
        self.source.write_bytes(self.original)
        self.source_uid = 1000
        try:
            os.chown(self.source, 1000, 1000)
        except OSError:
            # Root in this test user namespace has no UID1000 mapping. Keep this
            # substitution in the test module only; production SOURCE_UID stays1000.
            self.source_uid = os.getuid()
            patch = mock.patch.object(CAP, "SOURCE_UID", self.source_uid)
            patch.start()
            self.addCleanup(patch.stop)
        self.source.chmod(0o755)
        self.rule = self.base / "sudoers"
        self.rule.write_bytes(b"FIXED_TEST_RULE\n")
        self.rule.chmod(0o440)
        grant = {"scope": "OWNER_LONG_TERM_DOMESTIC_TOKYO_MIGRATION",
                 "sudoers_sha256": hashlib.sha256(self.rule.read_bytes()).hexdigest()}
        (self.root / "grant.json").write_text(json.dumps(grant))
        (self.root / "grant.json").chmod(0o600)
        self.restarts = []
        self.verifications = []
        def verify(head):
            self.verifications.append(head)
            return [{"method": "HEAD", "status": head}]
        self.cap = CAP.Capability(self.root, self.source, self.rule,
                                  restart=lambda: self.restarts.append(True),
                                  verify=verify, preflight=lambda: None)

    def test_status_has_no_expiry_and_no_production_effects(self):
        result = self.cap.run("status")
        self.assertEqual(result["authority"], "PERSISTENT_FIXED_ACTIONS")
        self.assertEqual(self.restarts, [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_apply_preserves_backup_identity_and_candidate_hash(self):
        result = self.cap.run("apply")
        self.assertEqual(result["status"], "LIVE_HEAD_GET_PASS")
        self.assertEqual((self.root / "source.before.py").read_bytes(), self.original)
        self.assertEqual((self.root / "source.before.py").stat().st_mode & 0o777, 0o400)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), CAP.CANDIDATE_SHA256)
        self.assertEqual(self.source.stat().st_uid, self.source_uid)
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o755)
        self.assertEqual(len(self.restarts), 1)
        self.assertEqual(self.verifications, [501])

    def test_apply_cannot_repeat_even_after_success(self):
        self.cap.run("apply")
        with self.assertRaisesRegex(ValueError, "NO_BLIND_APPLY_RETRY"):
            self.cap.run("apply")
        self.assertEqual(len(self.restarts), 1)

    def test_rollback_restores_exact_original_and_is_one_time(self):
        self.cap.run("apply")
        self.assertEqual(self.cap.run("rollback")["status"], "ROLLED_BACK")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.verifications, [501, 502])
        with self.assertRaisesRegex(ValueError, "ROLLBACK_NOT_ALLOWED"):
            self.cap.run("rollback")
        self.assertEqual(len(self.restarts), 2)

    def test_foreign_source_refuses_before_restart(self):
        self.source.write_bytes(b"FOREIGN")
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
            self.cap.run("apply")
        self.assertEqual(self.restarts, [])
        self.assertFalse((self.root / "source.before.py").exists())

    def test_symlink_source_refused(self):
        real = self.base / "real.py"
        real.write_bytes(self.original)
        self.source.unlink()
        self.source.symlink_to(real)
        with self.assertRaises(OSError):
            self.cap.run("apply")
        self.assertEqual(self.restarts, [])

    def test_hardlink_source_refused(self):
        os.link(self.source, self.base / "alias.py")
        with self.assertRaisesRegex(ValueError, "FILE_IDENTITY_MISMATCH"):
            self.cap.run("apply")

    def test_group_writable_source_parent_refused(self):
        self.source.parent.chmod(0o775)
        with self.assertRaisesRegex(ValueError, "SOURCE_PARENT_IDENTITY"):
            self.cap.run("apply")

    def test_untrusted_state_directory_refused(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "STATE_DIRECTORY_IDENTITY"):
            self.cap.run("apply")

    def test_untrusted_grant_mode_refused(self):
        (self.root / "grant.json").chmod(0o644)
        with self.assertRaisesRegex(ValueError, "FILE_MODE_MISMATCH"):
            self.cap.run("apply")

    def test_existing_backup_never_overwritten(self):
        (self.root / "source.before.py").write_bytes(b"PRESERVE")
        with self.assertRaisesRegex(ValueError, "BACKUP_ALREADY_EXISTS"):
            self.cap.run("apply")
        self.assertEqual((self.root / "source.before.py").read_bytes(), b"PRESERVE")

    def test_stopped_service_is_not_started(self):
        def stopped():
            raise subprocess.CalledProcessError(3, "is-active")
        self.cap.preflight = stopped
        with self.assertRaises(subprocess.CalledProcessError):
            self.cap.run("apply")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.restarts, [])

    def test_restart_timeout_preserves_evidence_and_disallows_retry(self):
        def timeout():
            raise subprocess.TimeoutExpired("restart", 40)
        self.cap.restart = timeout
        with self.assertRaises(subprocess.TimeoutExpired):
            self.cap.run("apply")
        self.assertEqual(self.cap.run("status")["status"], "UNKNOWN_PRESERVE_EVIDENCE")
        self.assertTrue((self.root / "source.before.py").exists())
        with self.assertRaisesRegex(ValueError, "NO_BLIND_APPLY_RETRY"):
            self.cap.run("apply")

    def test_tampered_backup_blocks_rollback(self):
        self.cap.run("apply")
        CAP.atomic_write(self.root / "source.before.py", b"TAMPERED", mode=0o400)
        with self.assertRaisesRegex(ValueError, "ROLLBACK_BACKUP_HASH_MISMATCH"):
            self.cap.run("rollback")
        self.assertEqual(len(self.restarts), 1)

    def test_foreign_current_source_blocks_rollback(self):
        self.cap.run("apply")
        self.source.write_bytes(b"OTHER_DEPLOYMENT")
        with self.assertRaisesRegex(ValueError, "ROLLBACK_CURRENT_SOURCE_MISMATCH"):
            self.cap.run("rollback")

    def test_unrecognized_modes_refused(self):
        for mode in ("shell", "python", "restart-nginx", "apply anything", ""):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, "MODE_NOT_ALLOWED"):
                    self.cap.run(mode)

    def test_revoke_only_matching_rule_and_preserves_backup(self):
        self.cap.run("revoke")
        self.assertFalse(self.rule.exists())
        self.assertEqual((self.root / "sudoers.revoked").read_bytes(), b"FIXED_TEST_RULE\n")
        self.assertEqual(self.restarts, [])

    def test_revoke_refuses_foreign_rule(self):
        CAP.atomic_write(self.rule, b"ANOTHER_POLICY", mode=0o440)
        with self.assertRaisesRegex(ValueError, "SUDOERS_IDENTITY_MISMATCH"):
            self.cap.run("revoke")
        self.assertTrue(self.rule.exists())

    def test_cli_rejects_extra_arguments_before_any_filesystem_access(self):
        with mock.patch.object(CAP.sys, "argv", ["cap", "apply", "/other/path"]):
            with self.assertRaisesRegex(SystemExit, "MODE_NOT_ALLOWED"):
                CAP.main()

    def test_cli_rejects_wrong_host(self):
        with mock.patch.object(CAP.sys, "argv", ["cap", "apply"]):
            with mock.patch.object(CAP.os, "uname", return_value=mock.Mock(nodename="other-host")):
                with self.assertRaisesRegex(SystemExit, "ROOT_ON_APPROVED_TOKYO_REQUIRED"):
                    CAP.main()


if __name__ == "__main__":
    unittest.main()
