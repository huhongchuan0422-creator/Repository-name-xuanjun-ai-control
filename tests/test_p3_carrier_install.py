from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from install import p3_carrier_install as installer


def write_json(path, value, mode=0o600):
    with open(path, "w") as output:
        json.dump(value, output, sort_keys=True, separators=(",", ":"))
        output.write("\n")
    os.chmod(path, mode)


class CarrierInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="p3-installer-"))
        self.root = os.path.join(self.tmp, "carrier")
        self.releases = os.path.join(self.tmp, "releases")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(os.path.join(self.root, "src"))
        self.member = os.path.join(self.root, "src", "module.py")
        with open(self.member, "wb") as output:
            output.write(b"default_off = True\n")
        member_sha = installer._digest(self.member)
        self.manifest = {
            "schema": 1,
            "kind": "P3_IMMUTABLE_DEFAULT_OFF_INSTALL_CARRIER",
            "source_commit": "1" * 40,
            "source_tree": "2" * 40,
            "default_off": True,
            "execution_enabled": False,
            "notifications_enabled": False,
            "files": {"src/module.py": member_sha},
            "release_files": ["src/module.py"],
            "base_reviews": {"qa": "PASS", "security": "PASS"},
        }
        self.manifest_path = os.path.join(self.root, "CARRIER_MANIFEST.json")
        write_json(self.manifest_path, self.manifest)
        self.manifest_sha = installer._digest(self.manifest_path)
        self.archive_sha = "3" * 64

    def _install_receipt_path(self):
        return os.path.join(
            self.releases, "p3-" + self.archive_sha[:20],
            "INSTALL_RECEIPT.json")

    def _rewrite_install_receipt(self, path, value):
        os.chmod(path, 0o600)
        write_json(path, value)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_install_is_default_off_idempotent_and_recoverable(self):
        first = installer.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        self.assertEqual("INSTALLED_DEFAULT_OFF_NOT_BOUND", first["state"])
        second = installer.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        self.assertTrue(second["idempotent"])
        recovered = installer.recover(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state,
            "install-attempt-01")
        self.assertEqual("INSTALLED_EFFECT_RECOVERED_NO_REPLAY",
                         recovered["recovery"])

    def test_bound_or_executed_receipt_never_reads_back_idempotent_or_recovered(self):
        mutations = (
            {"host_bound": True},
            {"real_task_executed": True},
            {"host_bound": True, "real_task_executed": True},
        )
        for number, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                if number:
                    shutil.rmtree(self.releases)
                    shutil.rmtree(self.state)
                installer.install(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases, self.state,
                    "install-attempt-01", lambda: True,
                    enforce_root=False)
                receipt_path = self._install_receipt_path()
                with open(receipt_path) as source:
                    receipt = json.load(source)
                receipt.update(mutation)
                self._rewrite_install_receipt(receipt_path, receipt)

                observed = installer.readback(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases)
                self.assertEqual("CONFLICT", observed["state"])
                self.assertIn(observed["field"], mutation)

                with self.assertRaisesRegex(
                        ValueError, "EXISTING_RELEASE_CONFLICT"):
                    installer.install(
                        self.root, self.manifest_path, self.manifest_sha,
                        self.archive_sha, self.releases, self.state,
                        "install-attempt-01", lambda: True,
                        enforce_root=False)

                recovered = installer.recover(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases, self.state,
                    "install-attempt-01")
                self.assertEqual("CONFLICT", recovered["state"])
                self.assertEqual("RESULT_MISSING_HOLD_NO_REPLAY",
                                 recovered["recovery"])

    def test_install_receipt_requires_exact_keys_and_valid_attempt(self):
        installer.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state,
            "install-attempt-01", lambda: True, enforce_root=False)
        receipt_path = self._install_receipt_path()
        with open(receipt_path) as source:
            receipt = json.load(source)
        receipt["unexpected"] = True
        self._rewrite_install_receipt(receipt_path, receipt)
        observed = installer.readback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases)
        self.assertEqual("receipt_keys", observed["field"])

        del receipt["unexpected"]
        receipt["attempt_id"] = "invalid attempt"
        self._rewrite_install_receipt(receipt_path, receipt)
        observed = installer.readback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases)
        self.assertEqual("attempt_id", observed["field"])

    def test_missing_current_controlled_authority_fails_before_effect(self):
        with self.assertRaisesRegex(PermissionError,
                                    "CURRENT_CONTROLLED_ENTRY_AUTHORITY_REQUIRED"):
            installer.install(
                self.root, self.manifest_path, self.manifest_sha,
                self.archive_sha, self.releases, self.state,
                "install-attempt-01", lambda: False, enforce_root=False)
        self.assertFalse(os.path.exists(self.releases))
        self.assertFalse(os.path.exists(self.state))

    def test_rollback_only_quarantines_unbound_default_off_release(self):
        installer.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        result = installer.rollback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "rollback-attempt-01",
            lambda: True, enforce_root=False)
        self.assertEqual("ROLLED_BACK_DEFAULT_OFF_QUARANTINED", result["state"])
        self.assertTrue(os.path.isfile(
            os.path.join(result["destination"], "ROLLBACK_RECEIPT.json")))
        self.assertEqual("ABSENT", installer.readback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases)["state"])

    def test_interrupted_rollback_recovers_receipt_without_rename_replay(self):
        installer.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        original = installer._atomic_json

        def interrupt(path, value, mode=0o440):
            if path.endswith("ROLLBACK_RECEIPT.json"):
                raise RuntimeError("SIMULATED_INTERRUPT_AFTER_ROLLBACK_RENAME")
            return original(path, value, mode)

        installer._atomic_json = interrupt
        try:
            with self.assertRaisesRegex(
                    RuntimeError, "SIMULATED_INTERRUPT_AFTER_ROLLBACK_RENAME"):
                installer.rollback(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases, self.state,
                    "rollback-attempt-01", lambda: True,
                    enforce_root=False)
        finally:
            installer._atomic_json = original
        result = installer.rollback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state,
            "rollback-attempt-01", lambda: True, enforce_root=False)
        self.assertEqual("ROLLBACK_EFFECT_RECOVERED_NO_REPLAY",
                         result["recovery"])
        self.assertTrue(os.path.isfile(
            os.path.join(result["destination"], "ROLLBACK_RECEIPT.json")))

    def test_interrupted_rollback_rejects_changed_quarantine_checkpoint(self):
        installer.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        original = installer._atomic_json

        def interrupt(path, value, mode=0o440):
            if path.endswith("ROLLBACK_RECEIPT.json"):
                raise RuntimeError("SIMULATED_INTERRUPT_AFTER_ROLLBACK_RENAME")
            return original(path, value, mode)

        installer._atomic_json = interrupt
        try:
            with self.assertRaises(RuntimeError):
                installer.rollback(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases, self.state,
                    "rollback-attempt-01", lambda: True,
                    enforce_root=False)
        finally:
            installer._atomic_json = original
        destination_member = os.path.join(
            self.state, "rolled-back", "rollback-attempt-01",
            "src", "module.py")
        os.chmod(destination_member, 0o600)
        with open(destination_member, "ab") as output:
            output.write(b"changed")
        with self.assertRaisesRegex(
                ValueError, "ROLLBACK_DESTINATION_CHECKPOINT_MISMATCH_HOLD"):
            installer.rollback(
                self.root, self.manifest_path, self.manifest_sha,
                self.archive_sha, self.releases, self.state,
                "rollback-attempt-01", lambda: True,
                enforce_root=False)

    def test_changed_member_is_rejected(self):
        with open(self.member, "ab") as output:
            output.write(b"changed")
        with self.assertRaisesRegex(ValueError,
                                    "CARRIER_MEMBER_MISMATCH:src/module.py"):
            installer.verify_carrier(
                self.root, self.manifest_path, self.manifest_sha)


if __name__ == "__main__":
    unittest.main()
