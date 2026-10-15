from __future__ import print_function

import contextlib
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import tarfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest import mock

from gate_common import sha256_value
from korea.build_runtime_candidate import build_candidate
from korea.get_only_policy import ControlledHttpsTransport
from korea.migration_shadow_entry import main, run_once
from korea.shadow_acceptance import run_continuous, validate_acceptance_config
from korea.validate_runtime_candidate import validate
from readonly_reconciliation_adapter import TABLE_SPECS


class FakeExchangeTransport(ControlledHttpsTransport):
    def __init__(self, host, allowed_ip_addresses, server_offset_ms=0):
        self.host = host
        self.timeout_seconds = 10
        self.server_offset_ms = server_offset_ms
        self.calls = []

    def get(self, url, headers=None, timeout_seconds=None):
        path = urlsplit(url).path
        now = int(time.time() * 1000)
        if path == "/fapi/v1/time": payload = {"serverTime": now + self.server_offset_ms}
        elif path == "/fapi/v3/account": payload = {"assets": []}
        elif path == "/fapi/v3/balance": payload = []
        elif path == "/fapi/v1/positionSide/dual": payload = {"dualSidePosition": True}
        else: payload = []
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        receipt = {"method": "GET", "host": self.host, "path": path, "status": 200,
                   "resolved_ip_sha256": "1" * 64, "resolved_set_sha256": "2" * 64,
                   "tls_peer_certificate_sha256": "3" * 64,
                   "proxy_used": False, "redirect_followed": False,
                   "root_egress_isolation_proven": False,
                   "request_timeout_seconds": timeout_seconds, "elapsed_ms": 0,
                   "body_sha256": hashlib.sha256(body).hexdigest()}
        self.calls.append(receipt)
        return body, receipt


class AlwaysBoundVerifier(object):
    def __init__(self, unused_command, unused_sha): pass
    def __call__(self, receipt, response): return True
    def verify_snapshot_handoff(self, receipt): return True


class RejectingVerifier(AlwaysBoundVerifier):
    def __call__(self, receipt, response): return False


class R1R6CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.business = root / "business"; self.business.mkdir()
        self.evidence = root / "evidence"; self.evidence.mkdir(mode=0o700)
        self.db = self.business / "trading.db"
        self.now = int(time.time() * 1000)
        connection = sqlite3.connect(str(self.db))
        created = set()
        for unused, (table, columns) in TABLE_SPECS.items():
            if table in created: continue
            created.add(table)
            definitions = ['"{0}" {1}'.format(
                column, "INTEGER PRIMARY KEY" if column == "id" else "TEXT")
                for column in columns]
            connection.execute("CREATE TABLE {0} ({1})".format(table, ",".join(definitions)))
        payload = json.dumps({"raw": {"assets": []}}, sort_keys=True)
        connection.execute("INSERT INTO account_snapshots VALUES(1,?,?,?,?)",
                           ("business-snapshot-7", "account-a", str(self.now), payload))
        connection.execute("INSERT INTO account_capabilities VALUES(1,?,?,?,?,?)",
                           ("account-a", "PRODUCTION", "HEDGE", "ACTIVE", str(self.now)))
        connection.commit(); connection.close()
        self.key = root / "key"; self.key.write_text("key"); self.key.chmod(0o600)
        self.secret = root / "secret"; self.secret.write_text("secret"); self.secret.chmod(0o600)
        self.handoff = root / "handoff.json"
        database_sha = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.handoff.write_text(json.dumps({
            "schema_version": 1,
            "protocol": "XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1",
            "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
            "account_id": "account-a", "database_path": str(self.db.resolve()),
            "database_sha256": database_sha, "snapshot_generation_id": "generation-1",
            "captured_at_ms": self.now, "published_at_ms": self.now,
            "runtime_manifest_sha256": "4" * 64,
            "publisher_identity_sha256": "5" * 64,
        }, sort_keys=True)); self.handoff.chmod(0o600)
        self.config = {
            "schema_version": 1, "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
            "account_id": "account-a", "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "business_database": str(self.db), "evidence_root": str(self.evidence),
            "pinned_ips": ["192.0.2.1"], "credential_role": "BINANCE_ACCOUNT_READONLY",
            "api_key_file": str(self.key), "api_secret_file": str(self.secret),
            "verifier_command": "/not/used/by/factory", "verifier_sha256": "0" * 64,
            "runtime_manifest_sha256": "4" * 64,
            "snapshot_handoff_receipt": str(self.handoff),
            "snapshot_refresh_protocol": "XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1",
            "snapshot_publisher_identity_sha256": "5" * 64,
            "snapshot_max_age_ms": 30000, "capture_timeout_ms": 30000,
            "writer_enabled": False, "scheduler_enabled": False,
        }

    def tearDown(self): self.temp.cleanup()

    def test_clean_extracted_artifact_is_self_contained_and_has_exact_default_import(self):
        output = Path(self.temp.name) / "runtime-candidate"
        manifest = build_candidate(output)
        value = validate(output, hashlib.sha256(manifest.read_bytes()).hexdigest())
        self.assertEqual(value["status"], "RUNTIME_CANDIDATE_INPUT_PASS")
        self.assertEqual(validate(output)["status"], "RUNTIME_CANDIDATE_INPUT_PASS")
        self.assertFalse(value["workspace_fallback_used"])
        for name in ("gate_common.py", "final_snapshot.py", "readonly_reconciliation_adapter.py"):
            self.assertTrue((output / "migration-prep" / name).is_file())
        archive = Path(self.temp.name) / "runtime-candidate.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(output, arcname="runtime-candidate")
        extracted = Path(self.temp.name) / "extracted"; extracted.mkdir()
        with tarfile.open(archive, "r:gz") as stream:
            stream.extractall(extracted)
        clean = extracted / "runtime-candidate"
        self.assertEqual(validate(clean)["status"], "RUNTIME_CANDIDATE_INPUT_PASS")

    def test_partial_copy_and_dangling_symlink_fail_input_validation(self):
        output = Path(self.temp.name) / "partial"
        build_candidate(output)
        target = output / "migration-prep/gate_common.py"
        target.unlink()
        with self.assertRaises(RuntimeError): validate(output)
        target.symlink_to(output / "missing")
        with self.assertRaises(RuntimeError): validate(output)

    def test_real_entry_separates_observation_and_business_snapshot_ids(self):
        result = run_once(self.config,
                          transport_factory=lambda host, ips: FakeExchangeTransport(host, ips),
                          verifier_factory=AlwaysBoundVerifier)
        self.assertEqual(result["status"], "PASS_READONLY_SHADOW_CYCLE")
        self.assertEqual(result["authoritative_business_snapshot_id"], "business-snapshot-7")
        self.assertNotEqual(result["observation_run_id"], "business-snapshot-7")
        receipt = json.loads((self.evidence / result["observation_run_id"] /
                              "reconciliation.json").read_text())
        self.assertEqual(receipt["authoritative_business_snapshot_id"], "business-snapshot-7")

    def test_real_entry_clock_skew_is_hold_and_hold_exit_is_nonzero(self):
        result = run_once(self.config,
                          transport_factory=lambda host, ips: FakeExchangeTransport(host, ips, -20000),
                          verifier_factory=AlwaysBoundVerifier)
        self.assertEqual(result["status"], "HOLD")
        with mock.patch("korea.migration_shadow_entry._load_config", return_value=self.config), \
             mock.patch("korea.migration_shadow_entry.run_once", return_value={"status": "HOLD"}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--once", "--config", "/secure/config"]), 2)
        with mock.patch("korea.migration_shadow_entry._load_config", return_value=self.config), \
             mock.patch("korea.migration_shadow_entry.run_once", return_value={"status": "UNKNOWN"}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--once", "--config", "/secure/config"]), 3)

    def test_real_entry_rejects_slow_response_bad_shape_missing_cursor_and_verifier(self):
        class SlowTransport(FakeExchangeTransport):
            def get(self, url, headers=None, timeout_seconds=None):
                time.sleep(0.03)
                return super().get(url, headers, timeout_seconds)
        tight = dict(self.config); tight["capture_timeout_ms"] = 10
        result = run_once(tight,
                          transport_factory=lambda host, ips: SlowTransport(host, ips),
                          verifier_factory=AlwaysBoundVerifier)
        self.assertEqual(result["status"], "HOLD")

        class BadAccountTransport(FakeExchangeTransport):
            def get(self, url, headers=None, timeout_seconds=None):
                if urlsplit(url).path == "/fapi/v3/account":
                    payload = {"notAssets": []}
                    body = json.dumps(payload).encode("utf-8")
                    return body, {"method": "GET", "host": self.host,
                        "path": "/fapi/v3/account", "status": 200,
                        "body_sha256": hashlib.sha256(body).hexdigest()}
                return super().get(url, headers, timeout_seconds)
        bad_shape = run_once(self.config,
                             transport_factory=lambda host, ips: BadAccountTransport(host, ips),
                             verifier_factory=AlwaysBoundVerifier)
        self.assertEqual(bad_shape["status"], "HOLD")

        class MissingCursorTransport(FakeExchangeTransport):
            def get(self, url, headers=None, timeout_seconds=None):
                if urlsplit(url).path == "/fapi/v1/allOrders":
                    payload = [{"symbol": "BTCUSDT"}] * 1000
                    body = json.dumps(payload).encode("utf-8")
                    return body, {"method": "GET", "host": self.host,
                        "path": "/fapi/v1/allOrders", "status": 200,
                        "body_sha256": hashlib.sha256(body).hexdigest()}
                return super().get(url, headers, timeout_seconds)
        missing_cursor = run_once(
            self.config,
            transport_factory=lambda host, ips: MissingCursorTransport(host, ips),
            verifier_factory=AlwaysBoundVerifier)
        self.assertEqual(missing_cursor["status"], "HOLD")

        rejected = run_once(self.config,
                            transport_factory=lambda host, ips: FakeExchangeTransport(host, ips),
                            verifier_factory=RejectingVerifier)
        self.assertEqual(rejected["status"], "HOLD")

    def test_install_scripts_bind_transaction_reentry_dangling_and_replacement(self):
        root = Path(__file__).resolve().parent / "korea"
        install = (root / "install-candidate.sh").read_text()
        check = (root / "check-candidate.sh").read_text()
        uninstall = (root / "uninstall-candidate.sh").read_text()
        self.assertIn("! -L $path", install)
        self.assertIn("ALREADY_INSTALLED=YES", install)
        self.assertIn("DIFFERENT_VERSION_REQUIRES_SEPARATE_APPROVED_UPGRADE", install)
        self.assertIn("INSTALL_TRANSACTION_BUSY", install)
        self.assertIn("STAGING_VALIDATION_FAILED", install)
        self.assertIn("trap cleanup EXIT", install)
        self.assertIn("UNIT_IDENTITY_MISMATCH", check)
        self.assertIn("UNEXPECTED_DROPIN", check)
        self.assertIn("REPLACED_UNIT_REFUSED", uninstall)
        self.assertIn("TRANSACTION_RECORD_HASH_MISMATCH", uninstall)
        self.assertIn("STATE_CREDENTIALS_EVIDENCE_IDENTITY=PRESERVED", uninstall)

    def test_continuous_window_aggregates_samples_resources_and_restart_state(self):
        acceptance = {
            "schema_version": 1, "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
            "window_id": "owner-window-1", "owner_approval_id": "approval-1",
            "owner_approved": True, "duration_seconds": 60,
            "sample_interval_seconds": 20, "minimum_samples": 3,
            "max_failed_samples": 0, "rss_peak_mib": 512,
            "mem_available_floor_mib": 512, "swap_growth_mib": 128,
            "latency_p95_ms": 2000, "latency_p99_ms": 5000,
            "max_sample_gap_seconds": 40, "max_restart_count": 0,
        }
        validate_acceptance_config(acceptance)
        moment = {"value": 0}
        def clock(): return moment["value"]
        def sleep(seconds): moment["value"] += int(seconds * 1000)
        def cycle(unused_config, now_ms=None):
            moment["value"] += 100
            return {"status": "PASS_READONLY_SHADOW_CYCLE",
                    "observation_run_id": "obs-" + str(now_ms),
                    "authoritative_business_snapshot_id": "business-snapshot-7",
                    "snapshot_generation_id": "generation-" + str(now_ms)}
        resource = lambda: {"rss_mib": 100, "mem_available_mib": 1000,
                            "swap_used_mib": 10}
        value = run_continuous(self.config, acceptance, cycle_runner=cycle,
                               clock_ms=clock, sleep_fn=sleep, resource_sampler=resource)
        self.assertEqual(value["status"], "PASS_SHADOW_WINDOW")
        self.assertGreaterEqual(len(value["samples"]), 3)
        self.assertEqual(value["restart_count"], 0)

    def test_unapproved_shadow_thresholds_fail_closed(self):
        value = {"schema_version": 1,
                 "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
                 "window_id": "draft", "owner_approval_id": "pending",
                 "owner_approved": False, "duration_seconds": 60,
                 "sample_interval_seconds": 20, "minimum_samples": 3,
                 "max_failed_samples": 0, "rss_peak_mib": 512,
                 "mem_available_floor_mib": 512, "swap_growth_mib": 128,
                 "latency_p95_ms": 2000, "latency_p99_ms": 5000}
        value.update({"max_sample_gap_seconds": 40, "max_restart_count": 0})
        with self.assertRaises(Exception): validate_acceptance_config(value)

    def _acceptance(self, window="negative-window", max_restarts=1):
        return {
            "schema_version": 1, "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
            "window_id": window, "owner_approval_id": "approval-negative",
            "owner_approved": True, "duration_seconds": 60,
            "sample_interval_seconds": 20, "minimum_samples": 3,
            "max_failed_samples": 0, "rss_peak_mib": 512,
            "mem_available_floor_mib": 512, "swap_growth_mib": 128,
            "latency_p95_ms": 2000, "latency_p99_ms": 5000,
            "max_sample_gap_seconds": 40, "max_restart_count": max_restarts,
        }

    def test_long_or_expired_restart_and_tested_object_drift_hold(self):
        resource = lambda: {"rss_mib": 100, "mem_available_mib": 1000,
                            "swap_used_mib": 10, "cgroup_memory_peak_mib": 100,
                            "cgroup_oom": 0}
        moment = {"value": 0}
        def interrupted(unused_config, now_ms=None):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            run_continuous(self.config, self._acceptance("gap-window"),
                           cycle_runner=interrupted, clock_ms=lambda: moment["value"],
                           sleep_fn=lambda seconds: None, resource_sampler=resource)
        moment["value"] = 41001
        held = run_continuous(self.config, self._acceptance("gap-window"),
                              cycle_runner=interrupted, clock_ms=lambda: moment["value"],
                              sleep_fn=lambda seconds: None, resource_sampler=resource)
        self.assertEqual(held["status"], "HOLD")
        self.assertIn("SHADOW_CONTINUITY_GAP_EXCEEDED", held["blockers"])

        changes = (
            ("account", "account_id", "different-account"),
            ("database", "business_database", str(Path(self.temp.name) / "different.sqlite")),
            ("artifact", "runtime_manifest_sha256", "6" * 64),
        )
        for suffix, key, replacement in changes:
            moment["value"] = 0; window = "identity-" + suffix
            with self.assertRaises(KeyboardInterrupt):
                run_continuous(self.config, self._acceptance(window),
                               cycle_runner=interrupted, clock_ms=lambda: moment["value"],
                               sleep_fn=lambda seconds: None, resource_sampler=resource)
            changed = dict(self.config); changed[key] = replacement
            with self.assertRaises(Exception):
                run_continuous(changed, self._acceptance(window),
                               cycle_runner=interrupted, clock_ms=lambda: 1000,
                               sleep_fn=lambda seconds: None, resource_sampler=resource)

        moment["value"] = 0
        with self.assertRaises(KeyboardInterrupt):
            run_continuous(self.config, self._acceptance("expired-window"),
                           cycle_runner=interrupted, clock_ms=lambda: moment["value"],
                           sleep_fn=lambda seconds: None, resource_sampler=resource)
        expired = run_continuous(self.config, self._acceptance("expired-window"),
                                 cycle_runner=interrupted, clock_ms=lambda: 60001,
                                 sleep_fn=lambda seconds: None, resource_sampler=resource)
        self.assertEqual(expired["status"], "HOLD")
        self.assertIn("SHADOW_WINDOW_EXPIRED_BEFORE_RESUME", expired["blockers"])

    def test_stale_static_snapshot_handoff_is_hold(self):
        receipt = json.loads(self.handoff.read_text())
        receipt["captured_at_ms"] = self.now - 30001
        receipt["published_at_ms"] = self.now - 30001
        self.handoff.write_text(json.dumps(receipt, sort_keys=True)); self.handoff.chmod(0o600)
        result = run_once(self.config, now_ms=self.now,
                          transport_factory=lambda host, ips: FakeExchangeTransport(host, ips),
                          verifier_factory=AlwaysBoundVerifier)
        self.assertEqual(result["status"], "HOLD")

    def test_resource_threshold_and_nonpass_cycle_hard_stop_immediately(self):
        moment = {"value": 0}
        def clock(): return moment["value"]
        def cycle(unused_config, now_ms=None):
            moment["value"] += 10
            return {"status": "PASS_READONLY_SHADOW_CYCLE",
                    "observation_run_id": "obs", "authoritative_business_snapshot_id": "snap",
                    "snapshot_generation_id": "generation-1"}
        resource = lambda: {"rss_mib": 700, "mem_available_mib": 1000,
                            "swap_used_mib": 10, "cgroup_memory_peak_mib": 700,
                            "cgroup_oom": 0}
        held = run_continuous(self.config, self._acceptance("resource-window"),
                              cycle_runner=cycle, clock_ms=clock,
                              sleep_fn=lambda seconds: None, resource_sampler=resource)
        self.assertEqual(held["status"], "HOLD")
        self.assertEqual(held["hard_stopped_at_sequence"], 1)
        self.assertIn("SHADOW_RSS_THRESHOLD_EXCEEDED", held["blockers"])


if __name__ == "__main__":
    unittest.main()
