from __future__ import print_function

import datetime
import json
import multiprocessing
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from archive_binding import key_fingerprint, sign, subject, verify
from cutover_gate import (FORWARD_PHASES, ROLLBACK_PHASES, advance as cutover_advance,
                          evaluate_isolation, evaluate_shadow, rollback_verdict,
                          uncertain_outcome)
from final_snapshot import (GetOnlyTransport, RECONCILED_STATE_CLASSES, SIDE_CAR_CLASSES,
                            build_exchange_reconciliation, build_final_checkpoint,
                            verify_checkpoint)
from gate_common import GateError, IdempotentLedger, bounded_call, load_json, sha256_value
from runner_retirement import PHASES as RUNNER_PHASES, command_plan
from runner_retirement import enforce_order as runner_order, evaluate as evaluate_runner
from writer_fence import (authorize_write, bind_discovery_to_coverage,
                          discover_writer_paths, evaluate_path_coverage,
                          reboot_verdict, validate_lease)
from yibi_retirement import PHASES as YIBI_PHASES
from yibi_retirement import (enforce_order as yibi_order, evaluate as evaluate_yibi,
                             failure_recovery, retirement_plan)


HERE = os.path.dirname(__file__)
INVENTORY = load_json(os.path.join(HERE, "gate_inventory.json"))


def receipts(phases):
    return [{"phase": phase, "status": "SUCCEEDED", "execution_id": "exec-" + str(index),
             "result_sha256": sha256_value({"phase": phase, "index": index})}
            for index, phase in enumerate(phases)]


def ledger_worker(path, output):
    output.put(IdempotentLedger(path).record("same", {"value": 1}))


def crash_ledger_worker(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS events (idempotency_key TEXT PRIMARY KEY, digest TEXT NOT NULL, recorded_at INTEGER NOT NULL)")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO events VALUES ('crash','x',1)")
    os._exit(7)


def partial_side_effect(path):
    with open(path, "w") as stream:
        stream.write("started")
    time.sleep(10)


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
            "production_services_unchanged": True, "timed_out": False,
            "partial_success": False
        }

    def test_exact_runner_plan_keeps_ssh_openclaw(self):
        host = INVENTORY["hosts"]["tokyo"]
        plan = command_plan(host, host["runner"], INVENTORY["runner_privilege_residue"])
        self.assertTrue(any(step.get("check") == "ssh_openclaw_canary_preserved" for step in plan))

    def test_complete_runner_evidence(self):
        self.assertEqual(evaluate_runner(INVENTORY["hosts"]["tokyo"], self.complete())["status"],
                         "PASS_CANDIDATE_EVIDENCE")

    def test_partial_or_timeout_holds(self):
        value = self.complete(); value["partial_success"] = True
        self.assertEqual(evaluate_runner(INVENTORY["hosts"]["tokyo"], value)["status"], "HOLD")
        value["partial_success"] = False; value["timed_out"] = True
        self.assertEqual(evaluate_runner(INVENTORY["hosts"]["tokyo"], value)["next"],
                         "INSPECT_ONLY_NO_BLIND_RETRY")

    def test_runner_history_requires_bound_contiguous_receipts(self):
        history = receipts(RUNNER_PHASES[:1])
        self.assertEqual(runner_order(history, "BASELINED"), "REPLAY_NOOP")
        self.assertEqual(runner_order(history, "STOPPED"), "EXECUTE_ONCE")
        for invalid in (["BASELINED"], receipts(("STOPPED",)),
                        receipts(RUNNER_PHASES[:1]) * 2):
            with self.assertRaises(GateError):
                runner_order(invalid, "STOPPED")


class YibiGateTests(unittest.TestCase):
    def complete(self):
        yibi = INVENTORY["yibi"]
        return {
            "phase": "VERIFIED", "archive_identity_verified": True,
            "active_units": [], "enabled_units": [],
            "masked_units": yibi["services"] + yibi["timers"], "processes": 0,
            "listeners": 0, "timer_triggers": 0, "cron_triggers": 0,
            "openclaw_triggers": 0, "openclaw_inventory_complete": True,
            "protected_units_pre": {"novel": "active", "postgres": "active", "redis": "active"},
            "protected_units_post": {"novel": "active", "postgres": "active", "redis": "active"},
            "postgres_data_identity_unchanged": True, "redis_identity_unchanged": True,
            "novel_identity_unchanged": True, "timed_out": False, "partial_success": False
        }

    def test_plan_never_stops_protected_units(self):
        yibi = INVENTORY["yibi"]
        flattened = [item for step in retirement_plan(yibi) for item in step.get("command", [])]
        for protected in yibi["protected_units"]:
            self.assertNotIn(protected, flattened)

    def test_complete_retirement_candidate(self):
        self.assertEqual(evaluate_yibi(INVENTORY["yibi"], self.complete())["status"],
                         "PASS_CANDIDATE_EVIDENCE")

    def test_incomplete_inventory_and_partial_hold(self):
        value = self.complete(); value["openclaw_inventory_complete"] = False
        self.assertEqual(evaluate_yibi(INVENTORY["yibi"], value)["status"], "HOLD")
        value = self.complete(); value["partial_success"] = True
        self.assertFalse(evaluate_yibi(INVENTORY["yibi"], value)["re_enable_yibi"])
        self.assertIn("start_yibi", failure_recovery()["forbidden"])

    def test_yibi_history_rejects_string_skip_and_failed_receipt(self):
        history = receipts(YIBI_PHASES[:1])
        self.assertEqual(yibi_order(history, "TRIGGERS_FROZEN"), "EXECUTE_ONCE")
        for invalid in (["ARCHIVE_VERIFIED"], receipts(("TRIGGERS_FROZEN",))):
            with self.assertRaises(GateError):
                yibi_order(invalid, "SERVICES_STOPPED")
        failed = receipts(YIBI_PHASES[:1]); failed[0]["status"] = "FAILED"
        with self.assertRaises(GateError):
            yibi_order(failed, "TRIGGERS_FROZEN")


class WriterFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime.datetime(2026, 10, 14, 11, 0, 0, tzinfo=datetime.timezone.utc)
        self.private = os.path.join(self.temp.name, "private.pem")
        self.public = os.path.join(self.temp.name, "public.pem")
        subprocess.check_call(["openssl", "genpkey", "-algorithm", "ED25519", "-out", self.private],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call(["openssl", "pkey", "-in", self.private, "-pubout", "-out", self.public],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.lease = {
            "schema_version": 2, "lease_id": "lease-korea-42", "epoch": 42,
            "external_current_epoch": 42, "writer_host": "korea",
            "issued_at": "2026-10-14T10:50:00Z", "expires_at": "2026-10-14T11:10:00Z",
            "authority_id": "offline-control-v1", "authoritative_store": "CONTROL_PLANE_QUORUM",
            "credential_fingerprint": "a" * 64, "credential_state_verified": True,
            "ip_allowlist_fingerprint": "b" * 64, "ip_allowlist_verified": True,
            "previous_epoch_revoked": True, "old_host_credential_revoked": True,
            "old_host_ip_removed": True, "production_release_gate_id": "RG-42"
        }
        self.trust = {"offline-control-v1": {
            "authoritative_store": "CONTROL_PLANE_QUORUM", "public_key_path": self.public,
            "pinned_public_key_sha256": key_fingerprint(self.public)}}

    def tearDown(self):
        self.temp.cleanup()

    def binding(self, lease=None):
        return sign(lease or self.lease, self.private, "offline-control-v1")

    def test_signed_contract_is_deduplicated_but_never_authorizes_production(self):
        path = os.path.join(self.temp.name, "ledger.sqlite")
        args = (self.lease, "korea", 42, "PROTECTIVE_CREATE", "req-1", "PROTECTION",
                path, self.now, self.binding(), self.trust)
        first, second = authorize_write(*args), authorize_write(*args)
        self.assertTrue(first["contract_accepted"])
        self.assertFalse(first["execution_authorized"])
        self.assertTrue(second["replayed"])

    def test_strings_empty_authority_and_unsigned_changes_fail(self):
        value = dict(self.lease)
        for key in ("credential_state_verified", "ip_allowlist_verified", "previous_epoch_revoked",
                    "old_host_credential_revoked", "old_host_ip_removed"):
            value[key] = "false"
        with self.assertRaises(GateError):
            validate_lease(value, "korea", 42, "CREATE_ORDER", self.now,
                           self.binding(value), self.trust)
        value = dict(self.lease); value["authoritative_store"] = ""
        with self.assertRaises(GateError):
            validate_lease(value, "korea", 42, "CREATE_ORDER", self.now,
                           self.binding(value), self.trust)
        value = dict(self.lease); value["external_current_epoch"] = 43
        with self.assertRaises(GateError):
            validate_lease(value, "korea", 42, "CREATE_ORDER", self.now,
                           self.binding(), self.trust)

    def test_stale_epoch_old_host_and_reboot_denied(self):
        with self.assertRaises(GateError):
            validate_lease(self.lease, "korea", 41, "CREATE_ORDER", self.now,
                           self.binding(), self.trust)
        self.assertEqual(reboot_verdict(self.lease, "tokyo", 42, self.now,
                                       self.binding(), self.trust), "DENY")

    def test_path_coverage_and_discovery_fail_closed(self):
        records = [
            {"path_id": "formal", "path_class": "FORMAL", "source_path": "/opt/formal.py",
             "reachable": True, "fence_call": True, "credential_access": True, "scheduler_access": True},
            {"path_id": "manual", "path_class": "MANUAL_SCRIPT", "source_path": "/legacy/manual.py",
             "reachable": False, "fence_call": False, "credential_access": False, "scheduler_access": False}
        ]
        self.assertEqual(evaluate_path_coverage(records)["status"], "PASS")
        records[1]["credential_access"] = True
        self.assertEqual(evaluate_path_coverage(records)["status"], "HOLD")
        root = os.path.join(self.temp.name, "legacy"); os.mkdir(root)
        path = os.path.join(root, "manual_order.py")
        with open(path, "w") as stream: stream.write("client.create_order(symbol='BTCUSDT')\n")
        findings = discover_writer_paths([root])
        self.assertEqual(bind_discovery_to_coverage(findings, [])["status"], "HOLD")


class SnapshotTests(unittest.TestCase):
    now = 1791975600000

    def local(self):
        mirror = {name: [{"symbol": "BTCUSDT", "id": name}] for name in RECONCILED_STATE_CLASSES}
        return {"unknown_orders": [], "inflight_requests": [], "ownership_conflicts": [],
                "expected_symbols": ["BTCUSDT"], "exchange_mirror": mirror,
                "db_external_state": {name: {"sha256": "0" * 64} for name in SIDE_CAR_CLASSES}}

    def transport(self, local=None, observed=None, incomplete=None):
        state = local or self.local(); timestamp = self.now if observed is None else observed
        def delegate(method, path, params):
            name = params["surface"]
            data = ({"serverTime": timestamp} if name == "server_time" else
                    state["exchange_mirror"].get(name, []))
            return {"observed_at_ms": timestamp, "data": data,
                    "pagination_complete": name != incomplete,
                    "symbols_covered": ["BTCUSDT"] if name in RECONCILED_STATE_CLASSES else []}
        return GetOnlyTransport(delegate)

    def reconcile(self, local=None, observed=None):
        state = local or self.local()
        return build_exchange_reconciliation(self.transport(state, observed), state,
                                             now_ms=self.now)

    def test_transport_and_actual_get_evidence(self):
        transport = self.transport()
        result = build_exchange_reconciliation(transport, self.local(), now_ms=self.now)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["request_method_policy"], "ENFORCED_GET_ONLY")
        self.assertTrue(all(call["method"] == "GET" for call in result["call_evidence"]))
        with self.assertRaises(GateError):
            transport.request("POST", "/fapi/v1/order")

    def test_old_receipts_pagination_symbol_and_state_mismatch_fail(self):
        old = self.reconcile(observed=1000000)
        self.assertIn("STALE_EXCHANGE_SERVER_TIME", old["blockers"])
        with self.assertRaises(GateError):
            build_exchange_reconciliation(self.transport(incomplete="trades"), self.local(), now_ms=self.now)
        state = self.local(); state["expected_symbols"] = ["BTCUSDT", "ETHUSDT"]
        with self.assertRaises(GateError):
            build_exchange_reconciliation(self.transport(state), state, now_ms=self.now)
        state = self.local(); state["exchange_mirror"]["positions"] = [{"symbol": "BTCUSDT", "id": "wrong"}]
        exchange_state = self.local()
        result = build_exchange_reconciliation(self.transport(exchange_state), state, now_ms=self.now)
        self.assertIn("STATE_MISMATCH:positions", result["blockers"])

    def test_capture_duration_and_unknown_hold(self):
        ticks = iter([self.now, self.now + 30001])
        with self.assertRaises(GateError):
            build_exchange_reconciliation(self.transport(), self.local(), now_ms=self.now,
                                          clock_ms=lambda: next(ticks))
        state = self.local(); state["unknown_orders"] = ["unknown-redacted"]
        self.assertEqual(build_exchange_reconciliation(self.transport(state), state,
                                                       now_ms=self.now)["status"], "HOLD")

    def test_final_checkpoint_semantics_survive_hash_recalculation_attack(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "trading.db")
            with open(database, "wb") as stream: stream.write(b"fixture")
            sidecars = {name: {"content_sha256": "c" * 64,
                               "captured_at_ms": self.now, "frozen": True}
                        for name in SIDE_CAR_CLASSES}
            maintenance = {"freeze_started_ms": self.now - 1, "freeze_deadline_ms": self.now + 1000,
                           "max_freeze_ms": 2000, "new_entries_frozen": True,
                           "inflight_drained": True,
                           "expected_authoritative_files": ["trading.db"]}
            checkpoint = build_final_checkpoint(self.reconcile(), [database], sidecars,
                                                maintenance, captured_at_ms=self.now)
            self.assertTrue(verify_checkpoint(checkpoint))
            checkpoint["sidecars"]["pending_queue"]["frozen"] = False
            unsigned = dict(checkpoint); unsigned.pop("checkpoint_sha256")
            checkpoint["checkpoint_sha256"] = sha256_value(unsigned)
            with self.assertRaises(GateError):
                verify_checkpoint(checkpoint)


class CutoverTests(unittest.TestCase):
    def isolation(self):
        return {"dedicated_user": True, "dedicated_directories": True,
                "dedicated_secret_namespace": True, "ports_non_overlapping": True,
                "runtime_versions_match": True, "dependencies_verified": True,
                "permissions_verified": True, "network_get_only_verified": True,
                "novel_unchanged": True, "postgres_unchanged": True,
                "redis_unchanged": True, "writer_enabled": False,
                "scheduler_enabled": False, "trade_credentials_present": False}

    def shadow(self):
        return {"no_order_write": True, "same_inputs": True, "decision_match": True,
                "position_match": True, "order_match": True, "protective_match": True,
                "unknown_count": 0, "inflight_count": 0, "restart_recovered": True,
                "duration_met": True, "timed_out": False, "partial_success": False}

    def test_every_positive_isolation_field_fails_individually(self):
        self.assertEqual(evaluate_isolation(self.isolation())["status"], "PASS_ISOLATED_CANDIDATE")
        for key in ("dedicated_user", "dedicated_directories", "dedicated_secret_namespace",
                    "ports_non_overlapping", "runtime_versions_match", "dependencies_verified",
                    "permissions_verified", "network_get_only_verified", "novel_unchanged",
                    "postgres_unchanged", "redis_unchanged"):
            value = self.isolation(); value[key] = False
            with self.assertRaises(GateError, msg=key): evaluate_isolation(value)

    def test_shadow_timeout_holds(self):
        value = self.shadow(); value["timed_out"] = True
        self.assertEqual(evaluate_shadow(value)["status"], "HOLD")

    def test_cutover_history_rejects_forged_string_and_skip(self):
        history = receipts(FORWARD_PHASES[:1])
        self.assertEqual(cutover_advance(history, "KOREA_ISOLATED_DEPLOYED"), "REPLAY_NOOP")
        with self.assertRaises(GateError): cutover_advance(["OBSERVATION_PASS"], "RUNTIME_VERIFIED")
        with self.assertRaises(GateError): cutover_advance(receipts(("OBSERVATION_PASS",)), "RUNTIME_VERIFIED")

    def test_rollback_fences_korea_before_tokyo(self):
        self.assertEqual(rollback_verdict(receipts(ROLLBACK_PHASES[:1]))["status"], "HOLD")
        self.assertEqual(rollback_verdict(receipts(ROLLBACK_PHASES[:3]))["status"],
                         "READY_TO_RESTORE_TOKYO")
        self.assertFalse(uncertain_outcome("timeout")["double_writer_allowed"])


class ArchiveBindingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("openssl"), "openssl unavailable")
    def test_detached_ed25519_binding_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            private, public = os.path.join(directory, "private.pem"), os.path.join(directory, "public.pem")
            subprocess.check_call(["openssl", "genpkey", "-algorithm", "ED25519", "-out", private],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["openssl", "pkey", "-in", private, "-pubout", "-out", public],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            statement = subject("artifact", "a" * 64, 123, "korea", "tokyo", ["PR99:6166635563"])
            binding = sign(statement, private, "offline-owner-key-v1")
            self.assertEqual(verify(statement, binding, public, key_fingerprint(public))["status"],
                             "AUTHENTICATED_BINDING_PASS")
            tampered = dict(statement); tampered["size_bytes"] = 124
            with self.assertRaises(GateError): verify(tampered, binding, public, key_fingerprint(public))


class CommonFailureTests(unittest.TestCase):
    def test_idempotency_conflict_and_two_process_serialization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.sqlite")
            output = multiprocessing.Queue()
            workers = [multiprocessing.Process(target=ledger_worker, args=(path, output)) for unused in range(2)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(10)
            results = [output.get(timeout=2), output.get(timeout=2)]
            self.assertEqual(sorted(result["replayed"] for result in results), [False, True])
            with self.assertRaises(GateError): IdempotentLedger(path).record("same", {"value": 2})

    def test_ledger_recovers_after_process_dies_mid_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.sqlite")
            worker = multiprocessing.Process(target=crash_ledger_worker, args=(path,))
            worker.start(); worker.join(10)
            self.assertNotEqual(worker.exitcode, 0)
            self.assertFalse(IdempotentLedger(path).record("after-crash", {"ok": True})["replayed"])

    def test_deadline_terminates_nonreturning_child_and_marks_side_effect_uncertain(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "partial")
            with self.assertRaisesRegex(GateError, "UNCERTAIN_SIDE_EFFECTS"):
                bounded_call(lambda: partial_side_effect(marker), 0.2)
            self.assertTrue(os.path.exists(marker))

    def test_safe_cli_renders_plans_without_execution(self):
        cli = os.path.join(HERE, "migration_gate_cli.py")
        runner = json.loads(subprocess.check_output([sys.executable, cli, "runner-plan", "--host", "tokyo"]).decode("utf-8"))
        yibi = json.loads(subprocess.check_output([sys.executable, cli, "yibi-plan"]).decode("utf-8"))
        self.assertFalse(runner["execution_authorized"])
        self.assertFalse(yibi["execution_authorized"])

    def test_safe_cli_writer_discovery_defaults_hold(self):
        cli = os.path.join(HERE, "migration_gate_cli.py")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "manual_writer.py")
            with open(path, "w") as stream: stream.write("client.create_order(symbol='SOLUSDT')\n")
            result = json.loads(subprocess.check_output([sys.executable, cli, "writer-discover", "--root", directory]).decode("utf-8"))
            self.assertEqual(result["coverage"]["status"], "HOLD")
            self.assertFalse(result["production_mutation"])


if __name__ == "__main__":
    unittest.main()
