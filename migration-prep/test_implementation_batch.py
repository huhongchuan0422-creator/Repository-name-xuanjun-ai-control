from __future__ import print_function

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unittest

from gate_common import GateError, sha256_value
from final_snapshot import REQUIRED_SURFACES, RECONCILED_STATE_CLASSES
from readonly_reconciliation_adapter import (SYMBOLS, TABLE_SPECS, EvidenceDirectory,
                                              FixtureGetOnlyPager, ReadOnlyBusinessDatabase,
                                              collect_fixture_evidence)
from restricted_executor import (TransactionLedger, cgroup_candidate_spec,
                                  execute_candidate, validate_policy)
from writer_isolation import coverage_assessment, evaluate_launch, validate_manifest
from build_writer_coverage import build as build_coverage
from korea.get_only_policy import PolicyDenied, validate_request


def runner_ok(request):
    return {"partial_success": False, "outcome_unknown": False, "phase": request["action"]}


def runner_partial(unused):
    return {"partial_success": True, "outcome_unknown": False}


def runner_slow(unused):
    time.sleep(5)
    return {"partial_success": False, "outcome_unknown": False}


class ReadOnlyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        business = os.path.join(self.temp.name, "business")
        evidence = os.path.join(self.temp.name, "evidence")
        os.mkdir(business); os.mkdir(evidence)
        self.db_path = os.path.join(business, "trading.db")
        self.evidence = evidence
        connection = sqlite3.connect(self.db_path)
        created = set()
        for unused, (table, columns) in TABLE_SPECS.items():
            if table in created:
                continue
            created.add(table)
            definitions = []
            for column in columns:
                definitions.append('"{0}" {1}'.format(
                    column, "INTEGER PRIMARY KEY" if column == "id" else "TEXT"))
            connection.execute("CREATE TABLE {0} ({1})".format(table, ",".join(definitions)))
        connection.execute("INSERT INTO kill_switch_state(id,switch_name,enabled,reason) VALUES(1,'global','1','test')")
        connection.commit(); connection.close()
        self.fixture = self.make_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def make_fixture(self):
        value = {}
        now = 1791975600000
        for surface in REQUIRED_SURFACES:
            if surface == "server_time":
                items, symbols = {"serverTime": now}, []
            elif surface == "balances":
                items, symbols = [], []
            elif surface in RECONCILED_STATE_CLASSES:
                items, symbols = [], list(SYMBOLS)
            else:
                items, symbols = {}, []
            value[surface] = [{"cursor": None, "next_cursor": None, "items": items,
                               "observed_at_ms": now, "symbols": symbols}]
        return value

    def test_real_sqlite_reader_is_immutable_and_evidence_separate(self):
        with open(self.db_path, "rb") as stream:
            before = stream.read()
        result = collect_fixture_evidence(self.db_path, self.evidence, "run-1", self.fixture)
        self.assertEqual(result["status"], "PASS_CANDIDATE")
        with open(self.db_path, "rb") as stream:
            self.assertEqual(stream.read(), before)
        self.assertEqual(sorted(item["name"] for item in result["files"]),
                         ["exchange-pages.json", "local-state.json", "reconciliation.json"])
        self.assertFalse(result["production_authorized"])

    def test_sqlite_write_and_reused_evidence_run_fail(self):
        database = ReadOnlyBusinessDatabase(self.db_path)
        with self.assertRaises(sqlite3.OperationalError):
            database.connection.execute("DELETE FROM kill_switch_state")
        database.close_and_verify_unchanged()
        collect_fixture_evidence(self.db_path, self.evidence, "run-1", self.fixture)
        with self.assertRaises(OSError):
            collect_fixture_evidence(self.db_path, self.evidence, "run-1", self.fixture)

    def test_pagination_cursor_symbol_and_method_contract(self):
        fixture = self.make_fixture()
        fixture["trades"] = [
            {"cursor": None, "next_cursor": "page-2", "items": [],
             "observed_at_ms": 1791975600000, "symbols": ["BTCUSDT"]},
            {"cursor": "page-2", "next_cursor": None, "items": [],
             "observed_at_ms": 1791975600001, "symbols": ["ETHUSDT", "SOLUSDT"]}]
        pager = FixtureGetOnlyPager(fixture)
        self.assertTrue(pager.collect("trades", SYMBOLS)["pagination_complete"])
        self.assertTrue(all(call["method"] == "GET" for call in pager.calls))
        fixture["trades"][1]["cursor"] = "gap"
        with self.assertRaises(GateError):
            FixtureGetOnlyPager(fixture).collect("trades", SYMBOLS)

    def test_mismatch_unknown_and_inflight_hold(self):
        fixture = self.make_fixture()
        fixture["positions"][0]["items"] = [{"symbol": "BTCUSDT"}]
        result = collect_fixture_evidence(self.db_path, self.evidence, "mismatch", fixture)
        self.assertEqual(result["status"], "HOLD")
        connection = sqlite3.connect(self.db_path)
        connection.execute("INSERT INTO execution_requests(id,request_id,account_id,status,intent) VALUES(1,'r','a','INFLIGHT','OPEN')")
        connection.commit(); connection.close()
        result = collect_fixture_evidence(self.db_path, self.evidence, "inflight", self.make_fixture())
        self.assertEqual(result["status"], "HOLD")


class RestrictedExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.temp.name, "ledger.sqlite")
        self.policy = {
            "schema_version": 1, "candidate_sha256": "a" * 64,
            "expires_at_epoch": 2000000000, "one_time_authority_id": "owner-gate-1",
            "authorized_request_sha256": "0" * 64,
            "hosts": {"iZmj7a5kwr75qc1tul4kf9Z": {
                "paths": ["/opt/xuanjun-binance"],
                "units": ["xuanjun-binance-shadow.service"],
                "actions": ["KOREA_DEPLOY", "KOREA_LOCK_WRITER"]}}}

    def tearDown(self):
        self.temp.cleanup()

    def request(self, tx="tx-1", timeout=2):
        return {"tx_id": tx, "host": "iZmj7a5kwr75qc1tul4kf9Z", "action": "KOREA_DEPLOY",
                "paths": ["/opt/xuanjun-binance"], "units": ["xuanjun-binance-shadow.service"],
                "candidate_sha256": "a" * 64, "authority_id": "owner-gate-1",
                "one_time_nonce_sha256": "b" * 64, "timeout_seconds": timeout}

    def bound(self, request):
        policy = dict(self.policy)
        policy["authorized_request_sha256"] = sha256_value(request)
        return policy

    def test_exact_allowlists_version_authority_and_success_receipt(self):
        request = self.request()
        result = execute_candidate(request, self.bound(request), self.ledger, runner_ok,
                                   now_epoch=1900000000)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertFalse(result["production_authorized"])
        self.assertEqual(TransactionLedger(self.ledger).read("tx-1")["state"], "SUCCEEDED")

    def test_replay_version_host_path_unit_action_and_expiry_rejected(self):
        request = self.request()
        policy = self.bound(request)
        execute_candidate(request, policy, self.ledger, runner_ok, now_epoch=1900000000)
        with self.assertRaises(GateError):
            execute_candidate(request, policy, self.ledger, runner_ok, now_epoch=1900000000)
        for key, value in (("candidate_sha256", "c" * 64), ("host", "wrong-host"),
                           ("paths", ["/tmp"]), ("units", ["ssh.service"]),
                           ("action", "READONLY_INSPECT")):
            request = self.request("tx-" + key)
            request[key] = value
            with self.assertRaises(GateError):
                execute_candidate(request, self.bound(request), self.ledger, runner_ok,
                                  now_epoch=1900000000)
        with self.assertRaises(GateError):
            request = self.request("expired")
            execute_candidate(request, self.bound(request), self.ledger, runner_ok,
                              now_epoch=2000000000)

    def test_same_one_time_nonce_cannot_bind_a_second_transaction(self):
        first = self.request("nonce-first")
        execute_candidate(first, self.bound(first), self.ledger, runner_ok, now_epoch=1900000000)
        second = self.request("nonce-second")
        with self.assertRaises(GateError):
            execute_candidate(second, self.bound(second), self.ledger, runner_ok,
                              now_epoch=1900000000)

    def test_partial_and_timeout_are_unknown_without_blind_retry(self):
        partial_request = self.request("partial")
        partial = execute_candidate(partial_request, self.bound(partial_request), self.ledger,
                                    runner_partial, now_epoch=1900000000)
        self.assertEqual(partial["status"], "UNKNOWN")
        self.assertFalse(partial["blind_retry_allowed"])
        timeout_request = self.request("timeout", 1)
        timeout_request["one_time_nonce_sha256"] = "c" * 64
        timeout = execute_candidate(timeout_request, self.bound(timeout_request), self.ledger,
                                    runner_slow, now_epoch=1900000000)
        self.assertEqual(timeout["status"], "UNKNOWN")
        self.assertTrue(timeout["inspection_required"])

    def test_cgroup_spec_is_data_only_and_no_root(self):
        value = cgroup_candidate_spec("tx-1")
        self.assertFalse(value["invoked"])
        self.assertFalse(value["root_capability"])
        self.assertIn("KillMode=control-group", value["properties"])


class WriterIsolationTests(unittest.TestCase):
    def private_map(self):
        records = []
        for index in range(95):
            path_class = "PROTECTION" if index < 8 else ("FORMAL" if index < 20 else "MANUAL_SCRIPT")
            records.append({"path_id": "WP{0:03d}".format(index + 1),
                            "source_path": "/private/path/{0}.py".format(index),
                            "source_sha256": hashlib.sha256(str(index).encode()).hexdigest(),
                            "path_class": path_class, "static_role": "DIRECT_WRITE_CAPABLE_SOURCE",
                            "current_runtime_reachability": "NOT_OBSERVED_GLOBAL_SCHEDULER_STILL_UNKNOWN",
                            "gateway_global_openclaw_inventory": "UNKNOWN_RESTRICTED_SCOPE",
                            "root_yibi_githubrunner_cron_inventory": "UNKNOWN_PERMISSION_BLOCKED",
                            "runtime_credential_access": "NOT_OBSERVED"})
        return {"records": records, "frozen_discovery_count": 95,
                "frozen_discovery_sha256": "c" * 64, "mapping_sha256": "d" * 64}

    def test_all_95_have_dynamic_manual_and_protection_policy(self):
        manifest = build_coverage(self.private_map())
        self.assertTrue(validate_manifest(manifest))
        result = coverage_assessment(manifest)
        self.assertEqual(result["checked"], 95)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(len(result["unknown"]), 95)

    def test_unknown_denies_and_valid_fence_never_authorizes_production(self):
        record = build_coverage(self.private_map())["records"][0]
        path = "/private/path/0.py"
        result = evaluate_launch(record, path, record["source_sha256"], "PROTECTIVE_CREATE", {})
        self.assertEqual(result["decision"], "DENY")
        record = dict(record); record["disposition"] = "FENCE_REQUIRED"
        result = evaluate_launch(record, path, record["source_sha256"], "PROTECTIVE_CREATE",
                                 {"external_epoch_valid": True, "credential_scope_valid": True,
                                  "scheduler_gate_valid": True})
        self.assertEqual(result["decision"], "CONTRACT_VALID_NOT_AUTHORIZED")
        self.assertFalse(result["production_authorized"])

    def test_source_hash_path_hash_and_protection_open_fail(self):
        record = build_coverage(self.private_map())["records"][0]
        record = dict(record); record["disposition"] = "FENCE_REQUIRED"
        context = {"external_epoch_valid": True, "credential_scope_valid": True,
                   "scheduler_gate_valid": True}
        with self.assertRaises(GateError):
            evaluate_launch(record, "/wrong", record["source_sha256"], "PROTECTIVE_CREATE", context)
        with self.assertRaises(GateError):
            evaluate_launch(record, "/private/path/0.py", "0" * 64, "PROTECTIVE_CREATE", context)
        result = evaluate_launch(record, "/private/path/0.py", record["source_sha256"],
                                 "CREATE_ORDER", context)
        self.assertEqual(result["reason"], "PROTECTION_OPEN_FORBIDDEN")


class KoreaPackageTests(unittest.TestCase):
    def test_application_layer_get_only_exact_host_and_path(self):
        value = validate_request("GET", "https://fapi.binance.com/fapi/v3/account?timestamp=1")
        self.assertEqual(value["decision"], "ALLOW_GET_ONLY")
        for method, url in (("POST", "https://fapi.binance.com/fapi/v1/order"),
                            ("GET", "https://evil.example/fapi/v3/account"),
                            ("GET", "http://fapi.binance.com/fapi/v3/account"),
                            ("GET", "https://fapi.binance.com/fapi/v1/order")):
            with self.assertRaises(PolicyDenied):
                validate_request(method, url)

    def test_manifest_is_isolated_nonexecuting_and_korea_first_rollback(self):
        path = os.path.join(os.path.dirname(__file__), "korea", "deployment-manifest.json")
        with open(path) as stream:
            value = json.load(stream)
        self.assertFalse(value["production_authorized"])
        self.assertFalse(value["install_executed"])
        self.assertFalse(value["runtime"]["reuse_yibi_venv"])
        self.assertFalse(value["writer_enabled"])
        self.assertFalse(value["scheduler_enabled"])
        self.assertEqual(value["network"]["application_method_allowlist"], ["GET"])
        self.assertEqual(value["rollback_order"][:3],
                         ["KOREA_WRITER_LOCKED", "KOREA_CREDENTIAL_REVOKED", "KOREA_IP_REMOVED"])
        self.assertFalse(value["double_writer_allowed"])


class PackageIntegrityTests(unittest.TestCase):
    def test_candidate_manifest_recomputes_every_file(self):
        root = os.path.dirname(__file__)
        with open(os.path.join(root, "candidate-manifest.json")) as stream:
            value = json.load(stream)
        self.assertFalse(value["production_authorized"])
        self.assertFalse(value["binance_called"])
        self.assertFalse(value["production_deployed"])
        for item in value["files"]:
            path = os.path.join(os.path.dirname(root), item["path"])
            digest = hashlib.sha256()
            with open(path, "rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            self.assertEqual(digest.hexdigest(), item["sha256"])
            self.assertEqual(os.path.getsize(path), item["size"])

    def test_executor_allowlist_is_exact_and_protected_units_forbidden(self):
        root = os.path.dirname(__file__)
        with open(os.path.join(root, "restricted-executor-allowlist.json")) as stream:
            value = json.load(stream)
        self.assertFalse(value["production_authorized"])
        self.assertEqual(value["privileged_transport"], "NONE")
        self.assertEqual(set(value["hosts"]),
                         set(("iZ6wee8q9z4t03hvqumwfhZ", "iZmj7a5kwr75qc1tul4kf9Z")))
        units = set(unit for host in value["hosts"].values() for unit in host["units"])
        self.assertFalse(units.intersection(value["forbidden_units"]))

    def test_public_writer_manifest_matches_frozen_private_digest(self):
        root = os.path.dirname(__file__)
        with open(os.path.join(root, "writer-coverage-public.json")) as stream:
            value = json.load(stream)
        self.assertEqual(value["source_discovery_count"], 95)
        self.assertEqual(value["source_discovery_sha256"],
                         "c80ccec7548264dce4322413d423a9a98869a3cb0f1675d27f91906a64068b65")
        self.assertEqual(value["private_mapping_sha256"],
                         "8f5ad7df2c63dd1b541ec4d21ab315b9cf0c23f00f77e326b59c82d92053f65b")
        self.assertTrue(value["source_paths_redacted"])
        self.assertEqual(set(record["candidate_enforcement"] for record in value["records"]),
                         set(("DENY",)))


if __name__ == "__main__":
    unittest.main()
