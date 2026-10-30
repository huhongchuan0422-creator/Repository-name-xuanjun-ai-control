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

    def test_changed_member_is_rejected(self):
        with open(self.member, "ab") as output:
            output.write(b"changed")
        with self.assertRaisesRegex(ValueError,
                                    "CARRIER_MEMBER_MISMATCH:src/module.py"):
            installer.verify_carrier(
                self.root, self.manifest_path, self.manifest_sha)


if __name__ == "__main__":
    unittest.main()
