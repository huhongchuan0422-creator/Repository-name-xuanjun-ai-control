import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from collect_dracut_symlink_supplement import EXPECTED_SUBJECTS, collect
from korea.build_minimal_runtime_manifest import build
from korea.get_only_policy import ControlledHttpsTransport
from korea.migration_shadow_entry import SignedReadonlyTransport, _load_config, self_check


class FakeControlledTransport(ControlledHttpsTransport):
    def __init__(self, payload):
        self.payload = payload
        self.urls = []
        self.timeout_seconds = 10

    def get(self, url, headers=None, timeout_seconds=None):
        self.urls.append((url, dict(headers or {})))
        body = json.dumps(self.payload).encode("utf-8")
        return body, {"method": "GET", "body_sha256": hashlib.sha256(body).hexdigest()}


class CloseoutPackageTests(unittest.TestCase):
    def test_self_check_is_readonly_and_writer_locked(self):
        value = self_check()
        self.assertEqual(value["network_methods"], ["GET"])
        self.assertFalse(value["writer_enabled"])
        self.assertFalse(value["scheduler_enabled"])
        self.assertFalse(value["production_authorized"])

    def test_signed_transport_has_no_write_primitive_or_secret_receipt(self):
        fake = FakeControlledTransport({"serverTime": 123})
        reader = SignedReadonlyTransport(fake, b"read-only-key", b"secret",
                                         "observation-1", 999,
                                         clock_ms=lambda: 123, monotonic=lambda: 1)
        response, receipt = reader("server_time", None, None, "account", "snapshot")
        self.assertEqual(response["items"], {"serverTime": 123})
        self.assertEqual(receipt["method"], "GET")
        self.assertNotIn("secret", json.dumps(receipt).lower())
        self.assertTrue(fake.urls[0][0].startswith("https://fapi.binance.com/fapi/v1/time"))
        self.assertFalse(any(hasattr(reader, name) for name in ("post", "put", "delete", "cancel")))

    def test_config_rejects_writer_and_forbidden_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            value = {
                "schema_version": 1,
                "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
                "account_id": "OWNER-BINANCE-001", "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                "business_database": "/var/lib/xuanjun-binance/input/db",
                "evidence_root": "/var/lib/xuanjun-binance/evidence", "pinned_ips": ["192.0.2.1"],
                "credential_role": "BINANCE_ACCOUNT_READONLY", "api_key_file": "/run/key",
                "api_secret_file": "/run/secret", "verifier_command": "/usr/local/bin/verifier",
                "verifier_sha256": "0" * 64, "snapshot_max_age_ms": 30000,
                "capture_timeout_ms": 30000, "writer_enabled": True, "scheduler_enabled": False,
            }
            path.write_text(json.dumps(value)); path.chmod(0o600)
            with self.assertRaises(Exception): _load_config(str(path))
            value["writer_enabled"] = False
            value["credential_role"] = "BINANCE_TRADING"
            path.write_text(json.dumps(value))
            with self.assertRaises(Exception): _load_config(str(path))

    @mock.patch("collect_dracut_symlink_supplement._rpm_source", return_value={"exit_code": 0, "stdout": "dracut", "stderr": ""})
    @mock.patch("collect_dracut_symlink_supplement._parents", return_value=[])
    @mock.patch("collect_dracut_symlink_supplement._identity", return_value={"uid": 0, "gid": 0, "mode": 0o644, "size": 1, "mtime_ns": 1})
    @mock.patch("collect_dracut_symlink_supplement.open", mock.mock_open(read_data=b"unit"))
    @mock.patch("collect_dracut_symlink_supplement.os.path.realpath")
    @mock.patch("collect_dracut_symlink_supplement.os.path.islink", return_value=True)
    @mock.patch("collect_dracut_symlink_supplement.os.walk")
    def test_dracut_supplement_requires_exact_original_subject_set(self, walk, unused_link, realpath, unused_identity, unused_parents, unused_rpm):
        paths = ["/usr/lib/systemd/system/" + value for value in sorted(EXPECTED_SUBJECTS)]
        # These synthetic names cannot reproduce the frozen subject hashes, so collection must HOLD.
        walk.side_effect = [
            iter([("/etc/systemd/system", [], [])]),
            iter([("/usr/lib/systemd/system", [], [Path(p).name for p in paths])]),
        ]
        realpath.return_value = "/usr/lib/dracut/modules.d/98dracut-systemd/unit.service"
        with mock.patch("collect_dracut_symlink_supplement.os.readlink", return_value="target"):
            result = collect("synthetic")
        self.assertIn("ORIGINAL_FAILED_SUBJECT_SET_MISMATCH", result["blockers"])
        self.assertFalse(result["allowlist_widened"])

    def test_runtime_manifest_is_minimal_and_locked(self):
        value = build()
        self.assertFalse(value["writer_enabled"])
        self.assertEqual(value["allowed_exchange_methods"], ["GET"])
        self.assertEqual(value["persistent_production_launcher"], "NOT_PROVEN_NOT_INCLUDED")
        self.assertGreater(len(value["files"]), 8)

    def test_install_candidate_unit_is_disabled_deny_all(self):
        root = Path(__file__).resolve().parent / "korea"
        unit = (root / "xuanjun-binance-shadow.service.in").read_text()
        install = (root / "install-candidate.sh").read_text()
        check = (root / "check-candidate.sh").read_text()
        self.assertIn("IPAddressDeny=any", unit)
        self.assertNotIn("IPAddressAllow=", unit)
        self.assertNotIn("systemctl start", install)
        self.assertIn("systemctl disable", install)
        self.assertIn("SOURCE_MANIFEST_CONTENT_PASS", install)
        self.assertIn("! grep -Eq '^IPAddressAllow='", check)
        self.assertIn("--continuous", unit)

    def test_production_closure_refuses_to_invent_launcher(self):
        path = Path(__file__).resolve().parent / "production-runtime-closure.json"
        value = json.loads(path.read_text())
        launcher = value["persistent_production_launcher"]
        self.assertEqual(launcher["status"], "NOT_PROVEN_NOT_INSTALLED")
        self.assertFalse(launcher["composition_point_is_launcher"])
        self.assertTrue(launcher["phase_d_e_blocked"])
        self.assertEqual(value["candidate_writer_files"]["decision"], "UNKNOWN_DENY")


if __name__ == "__main__":
    unittest.main()
