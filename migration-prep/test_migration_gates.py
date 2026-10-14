from __future__ import print_function

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from archive_binding import key_fingerprint, sign, subject, verify
from cutover_gate import advance as cutover_advance, evaluate_isolation, evaluate_shadow, rollback_verdict, uncertain_outcome
from final_snapshot import GetOnlyTransport, SIDE_CAR_CLASSES, build_exchange_reconciliation, build_final_checkpoint, verify_checkpoint
from gate_common import GateError, IdempotentLedger, bounded_call, load_json
from runner_retirement import command_plan, enforce_order as runner_order, evaluate as evaluate_runner
from writer_fence import authorize_write, bind_discovery_to_coverage, discover_writer_paths, evaluate_path_coverage, reboot_verdict, validate_lease
from yibi_retirement import enforce_order as yibi_order, evaluate as evaluate_yibi, failure_recovery, retirement_plan


HERE = os.path.dirname(__file__)
INVENTORY = load_json(os.path.join(HERE, "gate_inventory.json"))


class RunnerGateTests(unittest.TestCase):
    def complete(self):
        runner = INVENTORY["hosts"]["tokyo"]["runner"]
        return {
            "hostname": INVENTORY["hosts"]["tokyo"]["hostname"],
            "runner_agent_id": runner["agent_id"], "runner_name": runner["name"],
            "runner_pool": "Default", "phase": "VERIFIED", "unit_active": False,
            "unit_enabled": False, "listener_processes": 0, "autostart_entries": 0,
            "github_registration_present": False, "helper_present": False,
            "sudoers_dropin_present": False, "ssh_openclaw_canary": True,
            "production_services_unchanged": True, "timed_out": False, "partial_success": False
        }

    def test_exact_runner_plan_keeps_ssh_openclaw(self):
        host = INVENTORY["hosts"]["tokyo"]
        plan = command_plan(host, host["runner"], INVENTORY["runner_privilege_residue"])
        self.assertTrue(any(step.get("check") == "ssh_openclaw_canary_preserved" for step in plan))
        self.assertFalse(any("ssh" in " ".join(step.get("command", [])) and "unlink" in step.get("command", []) for step in plan))

    def test_complete_runner_evidence(self):
        self.assertEqual(evaluate_runner(INVENTORY["hosts"]["tokyo"], self.complete())["status"], "PASS_CANDIDATE_EVIDENCE")

    def test_partial_or_timeout_holds(self):
        value = self.complete()
        value["partial_success"] = True
        self.assertEqual(evaluate_runner(INVENTORY["hosts"]["tokyo"], value)["status"], "HOLD")
        value["partial_success"] = False
        value["timed_out"] = True
        self.assertEqual(evaluate_runner(INVENTORY["hosts"]["tokyo"], value)["next"], "INSPECT_ONLY_NO_BLIND_RETRY")

    def test_runner_repeat_and_order(self):
        self.assertEqual(runner_order(["BASELINED"], "BASELINED"), "REPLAY_NOOP")
        self.assertEqual(runner_order(["BASELINED"], "STOPPED"), "EXECUTE_ONCE")
        with self.assertRaises(GateError):
            runner_order(["BASELINED"], "DEREGISTERED")


class YibiGateTests(unittest.TestCase):
    def complete(self):
        yibi = INVENTORY["yibi"]
        return {
            "phase": "VERIFIED", "archive_identity_verified": True,
            "active_units": [], "enabled_units": [],
            "masked_units": yibi["services"] + yibi["timers"], "processes": 0,
            "listeners": 0, "timer_triggers": 0, "cron_triggers": 0, "openclaw_triggers": 0,
            "openclaw_inventory_complete": True,
            "protected_units_pre": {"novel": "active", "postgres": "active", "redis": "active"},
            "protected_units_post": {"novel": "active", "postgres": "active", "redis": "active"},
            "postgres_data_identity_unchanged": True, "redis_identity_unchanged": True,
            "novel_identity_unchanged": True, "timed_out": False, "partial_success": False
        }

    def test_plan_never_stops_protected_units(self):
        yibi = INVENTORY["yibi"]
        commands = retirement_plan(yibi)
        flattened = [item for step in commands for item in step.get("command", [])]
        for protected in yibi["protected_units"]:
            self.assertNotIn(protected, flattened)

    def test_complete_retirement_candidate(self):
        self.assertEqual(evaluate_yibi(INVENTORY["yibi"], self.complete())["status"], "PASS_CANDIDATE_EVIDENCE")

    def test_incomplete_openclaw_inventory_holds(self):
        value = self.complete()
        value["openclaw_inventory_complete"] = False
        self.assertEqual(evaluate_yibi(INVENTORY["yibi"], value)["reason"], "G2_OPENCLAW_TRIGGER_INVENTORY_INCOMPLETE")

    def test_partial_failure_never_reenables(self):
        value = self.complete()
        value["partial_success"] = True
        self.assertFalse(evaluate_yibi(INVENTORY["yibi"], value)["re_enable_yibi"])
        self.assertIn("start_yibi", failure_recovery()["forbidden"])

    def test_yibi_repeat_and_order(self):
        self.assertEqual(yibi_order(["ARCHIVE_VERIFIED"], "ARCHIVE_VERIFIED"), "REPLAY_NOOP")
        with self.assertRaises(GateError):
            yibi_order(["ARCHIVE_VERIFIED"], "SERVICES_STOPPED")


class WriterFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime.datetime(2026, 10, 14, 11, 0, 0, tzinfo=datetime.timezone.utc)
        self.lease = {
            "lease_id": "lease-korea-42", "epoch": 42, "writer_host": "korea",
            "issued_at": "2026-10-14T10:50:00Z", "expires_at": "2026-10-14T11:10:00Z",
            "authoritative_store": "CONTROL_PLANE_QUORUM", "signature_verified": True,
            "credential_fingerprint": "cred:abc", "credential_state_verified": True,
            "ip_allowlist_fingerprint": "ip:def", "ip_allowlist_verified": True,
            "previous_epoch_revoked": True, "old_host_credential_revoked": True,
            "old_host_ip_removed": True, "production_release_gate_id": "RG-42"
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_authorization_and_replay(self):
        path = os.path.join(self.temp.name, "ledger.json")
        first = authorize_write(self.lease, "korea", 42, "PROTECTIVE_CREATE", "req-1", "PROTECTION", path, self.now)
        second = authorize_write(self.lease, "korea", 42, "PROTECTIVE_CREATE", "req-1", "PROTECTION", path, self.now)
        self.assertTrue(first["authorized"])
        self.assertTrue(second["replayed"])

    def test_stale_epoch_old_host_and_reboot_denied(self):
        with self.assertRaises(GateError):
            validate_lease(self.lease, "korea", 41, "CREATE_ORDER", self.now)
        self.assertEqual(reboot_verdict(self.lease, "tokyo", 42, self.now), "DENY")

    def test_local_authority_and_unrevoked_credential_denied(self):
        value = dict(self.lease)
        value["authoritative_store"] = "LOCAL_SQLITE"
        with self.assertRaises(GateError):
            validate_lease(value, "korea", 42, "CREATE_ORDER", self.now)
        value = dict(self.lease)
        value["old_host_credential_revoked"] = False
        with self.assertRaises(GateError):
            validate_lease(value, "korea", 42, "CREATE_ORDER", self.now)

    def test_path_coverage_requires_fence_or_quarantine(self):
        records = [
            {"path_id": "formal", "path_class": "FORMAL", "source_path": "/opt/formal.py", "reachable": True, "fence_call": True, "credential_access": True, "scheduler_access": True},
            {"path_id": "manual", "path_class": "MANUAL_SCRIPT", "source_path": "/legacy/manual.py", "reachable": False, "fence_call": False, "credential_access": False, "scheduler_access": False}
        ]
        self.assertEqual(evaluate_path_coverage(records)["status"], "PASS")
        records[1]["credential_access"] = True
        self.assertEqual(evaluate_path_coverage(records)["status"], "HOLD")

    def test_discovery_fails_closed_on_undeclared_manual_writer(self):
        root = os.path.join(self.temp.name, "legacy")
        os.mkdir(root)
        path = os.path.join(root, "manual_order.py")
        with open(path, "w") as stream:
            stream.write("client.create_order(symbol='BTCUSDT')\n")
        findings = discover_writer_paths([root])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path_class"], "MANUAL_SCRIPT")
        self.assertEqual(bind_discovery_to_coverage(findings, [])["status"], "HOLD")

    def test_discovery_hash_binds_coverage(self):
        root = os.path.join(self.temp.name, "formal")
        os.mkdir(root)
        path = os.path.join(root, "adapter.py")
        with open(path, "w") as stream:
            stream.write("client.cancel_order(order_id='x')\n")
        findings = discover_writer_paths([root])
        coverage = [{"path_id": "adapter", "path_class": "LEGACY", "source_path": path,
                     "source_sha256": findings[0]["sha256"], "reachable": True,
                     "fence_call": True, "credential_access": True, "scheduler_access": True}]
        self.assertEqual(bind_discovery_to_coverage(findings, coverage)["status"], "PASS")


class SnapshotTests(unittest.TestCase):
    class Provider(object):
        def read(self, name):
            data = {"serverTime": 1000000} if name == "server_time" else []
            return {"observed_at_ms": 1000000, "data": data}

    def local(self):
        return {"unknown_orders": [], "inflight_requests": [], "ownership_conflicts": [],
                "db_external_state": {name: {"sha256": "0" * 64} for name in SIDE_CAR_CLASSES}}

    def test_transport_blocks_non_get(self):
        transport = GetOnlyTransport(lambda method, path, params: {})
        transport.request("GET", "/fapi/v1/time")
        with self.assertRaises(GateError):
            transport.request("POST", "/fapi/v1/order")

    def test_exchange_reconciliation_and_unknown_hold(self):
        result = build_exchange_reconciliation(self.Provider(), self.local(), now_ms=1000000)
        self.assertEqual(result["status"], "PASS")
        local = self.local()
        local["unknown_orders"] = ["unknown-redacted"]
        self.assertEqual(build_exchange_reconciliation(self.Provider(), local, now_ms=1000000)["status"], "HOLD")

    def test_final_checkpoint_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "trading.db")
            with open(database, "wb") as stream:
                stream.write(b"fixture")
            exchange = build_exchange_reconciliation(self.Provider(), self.local(), now_ms=1000000)
            checkpoint = build_final_checkpoint(exchange, [database], self.local()["db_external_state"],
                                                {"freeze_started_at": "t0", "freeze_deadline": "t1", "new_entries_frozen": True, "inflight_drained": True})
            self.assertTrue(verify_checkpoint(checkpoint))
            checkpoint["sidecars"]["pending_queue"] = {}
            with self.assertRaises(GateError):
                verify_checkpoint(checkpoint)


class CutoverTests(unittest.TestCase):
    def isolation(self):
        return {"dedicated_user": True, "dedicated_directories": True, "dedicated_secret_namespace": True,
                "ports_non_overlapping": True, "runtime_versions_match": True, "dependencies_verified": True,
                "permissions_verified": True, "network_get_only_verified": True, "novel_unchanged": True,
                "postgres_unchanged": True, "redis_unchanged": True, "writer_enabled": False,
                "scheduler_enabled": False, "trade_credentials_present": False}

    def shadow(self):
        return {"no_order_write": True, "same_inputs": True, "decision_match": True,
                "position_match": True, "order_match": True, "protective_match": True,
                "unknown_count": 0, "inflight_count": 0, "restart_recovered": True,
                "duration_met": True, "timed_out": False, "partial_success": False}

    def test_isolation_and_shadow(self):
        self.assertEqual(evaluate_isolation(self.isolation())["status"], "PASS_ISOLATED_CANDIDATE")
        self.assertEqual(evaluate_shadow(self.shadow())["status"], "PASS_SHADOW_CANDIDATE")

    def test_shadow_timeout_holds(self):
        value = self.shadow()
        value["timed_out"] = True
        self.assertEqual(evaluate_shadow(value)["status"], "HOLD")

    def test_cutover_repeat_and_order(self):
        self.assertEqual(cutover_advance(["KOREA_ISOLATED_DEPLOYED"], "KOREA_ISOLATED_DEPLOYED"), "REPLAY_NOOP")
        with self.assertRaises(GateError):
            cutover_advance([], "TOKYO_FENCED")

    def test_rollback_fences_korea_before_tokyo(self):
        self.assertEqual(rollback_verdict(["KOREA_WRITER_LOCKED"])["status"], "HOLD")
        first = ["KOREA_WRITER_LOCKED", "KOREA_CREDENTIAL_REVOKED", "KOREA_IP_REMOVED"]
        self.assertEqual(rollback_verdict(first)["status"], "READY_TO_RESTORE_TOKYO")
        self.assertFalse(uncertain_outcome("timeout")["double_writer_allowed"])


class ArchiveBindingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("openssl"), "openssl unavailable")
    def test_detached_ed25519_binding_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            private = os.path.join(directory, "private.pem")
            public = os.path.join(directory, "public.pem")
            subprocess.check_call(["openssl", "genpkey", "-algorithm", "ED25519", "-out", private], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["openssl", "pkey", "-in", private, "-pubout", "-out", public], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            statement = subject("artifact", "a" * 64, 123, "korea", "tokyo", ["PR99:6166635563"])
            binding = sign(statement, private, "offline-owner-key-v1")
            result = verify(statement, binding, public, key_fingerprint(public))
            self.assertEqual(result["status"], "AUTHENTICATED_BINDING_PASS")
            tampered = dict(statement)
            tampered["size_bytes"] = 124
            with self.assertRaises(GateError):
                verify(tampered, binding, public, key_fingerprint(public))


class CommonFailureTests(unittest.TestCase):
    def test_idempotency_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = IdempotentLedger(os.path.join(directory, "events.json"))
            ledger.record("same", {"value": 1})
            with self.assertRaises(GateError):
                ledger.record("same", {"value": 2})

    def test_bounded_call_timeout(self):
        ticks = iter([0.0, 2.0])
        with self.assertRaises(GateError):
            bounded_call(lambda: "late", 1.0, clock=lambda: next(ticks))

    def test_safe_cli_renders_plans_without_execution(self):
        cli = os.path.join(HERE, "migration_gate_cli.py")
        runner = json.loads(subprocess.check_output([sys.executable, cli, "runner-plan", "--host", "tokyo"]).decode("utf-8"))
        yibi = json.loads(subprocess.check_output([sys.executable, cli, "yibi-plan"]).decode("utf-8"))
        self.assertFalse(runner["execution_authorized"])
        self.assertFalse(yibi["execution_authorized"])
        self.assertFalse(yibi["re_enable_yibi"])

    def test_safe_cli_writer_discovery_defaults_hold(self):
        cli = os.path.join(HERE, "migration_gate_cli.py")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "manual_writer.py")
            with open(path, "w") as stream:
                stream.write("client.create_order(symbol='SOLUSDT')\n")
            result = json.loads(subprocess.check_output([sys.executable, cli, "writer-discover", "--root", directory]).decode("utf-8"))
            self.assertEqual(result["coverage"]["status"], "HOLD")
            self.assertFalse(result["production_mutation"])


if __name__ == "__main__":
    unittest.main()
