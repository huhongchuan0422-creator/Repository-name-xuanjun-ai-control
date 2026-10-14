from __future__ import print_function

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from gate_common import GateError, canonical_bytes, sha256_value
from final_snapshot import REQUIRED_SURFACES, RECONCILED_STATE_CLASSES, SURFACE_REQUESTS
from readonly_reconciliation_adapter import (SYMBOLS, TABLE_SPECS,
                                              AuthenticatedGetOnlyPager,
                                              FixtureGetOnlyPager, ReadOnlyBusinessDatabase,
                                              collect_fixture_evidence)
import restricted_executor as executor
from restricted_executor import (TransactionLedger, cgroup_candidate_spec,
                                  execute_candidate, load_verified_policy)
from writer_isolation import coverage_assessment, evaluate_launch, validate_manifest
from build_writer_coverage import build as build_coverage
from korea import get_only_policy
from korea.get_only_policy import ControlledHttpsTransport, PolicyDenied, validate_request


NOW_MS = 1791975600000


def runner_ok(request):
    return {"schema_version": 1, "action": request["action"], "outcome": "SUCCEEDED",
            "side_effects_attempted": True,
            "side_effects": [{"effect_id": "e1", "kind": "CANDIDATE_TEST",
                              "target_sha256": "a" * 64, "claimed_state": "COMPLETE"}],
            "effect_verification": [{"effect_id": "e1", "verified": True,
                                     "evidence_sha256": "e" * 64}],
            "postcondition_verified": True, "completed_at_epoch": 1900000000,
            "evidence_sha256": "f" * 64}


def verifier_ok(request, runner_result):
    observations = []
    for expected in request["expected_postconditions"]:
        observations.append({
            "postcondition_id": expected["postcondition_id"],
            "kind": expected["kind"],
            "target_sha256": expected["target_sha256"],
            "observed_state": expected["required_state"],
            "source_class": "SYSTEMD_READBACK",
            "verified": True,
            "evidence_sha256": "9" * 64})
    value = {"schema_version": 1, "tx_id": request["tx_id"],
             "host": request["host"], "action": request["action"],
             "candidate_sha256": request["candidate_sha256"],
             "verifier_sha256": request["independent_verifier_sha256"],
             "runner_result_sha256": sha256_value(runner_result),
             "observed_at_epoch": 1900000001, "observations": observations,
             "all_postconditions_verified": True}
    value["evidence_sha256"] = sha256_value(value)
    return value


def runner_unknown(request):
    value = runner_ok(request); value["outcome"] = "UNKNOWN"
    value["postcondition_verified"] = False
    return value


def runner_slow(unused):
    time.sleep(5)
    return {}


class ReadOnlyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        business = os.path.join(self.temp.name, "business")
        evidence = os.path.join(self.temp.name, "evidence")
        os.mkdir(business); os.mkdir(evidence)
        self.db_path, self.evidence = os.path.join(business, "trading.db"), evidence
        connection = sqlite3.connect(self.db_path)
        created = set()
        for unused, (table, columns) in TABLE_SPECS.items():
            if table in created:
                continue
            created.add(table)
            definitions = ['"{0}" {1}'.format(
                column, "INTEGER PRIMARY KEY" if column == "id" else "TEXT")
                for column in columns]
            connection.execute("CREATE TABLE {0} ({1})".format(table, ",".join(definitions)))
        payload = json.dumps({"raw": {"assets": []}}, sort_keys=True)
        connection.execute("INSERT INTO account_snapshots VALUES(1,?,?,?,?)",
                           ("snap-a", "account-a", str(NOW_MS), payload))
        connection.execute("INSERT INTO account_capabilities VALUES(1,?,?,?,?,?)",
                           ("account-a", "PRODUCTION", "HEDGE", "ACTIVE", str(NOW_MS)))
        connection.execute("INSERT INTO kill_switch_state VALUES(1,'global','1','test')")
        connection.commit(); connection.close()
        self.fixture = self.make_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def make_fixture(self):
        value = {}
        for surface in REQUIRED_SURFACES:
            if surface == "server_time":
                items, symbols = {"serverTime": NOW_MS}, []
            elif surface == "account":
                items, symbols = {"assets": []}, []
            elif surface == "balances":
                items, symbols = [], []
            elif surface == "position_mode":
                items, symbols = {"dualSidePosition": True}, []
            elif surface in RECONCILED_STATE_CLASSES:
                items, symbols = [], list(SYMBOLS)
            else:
                items, symbols = {}, []
            value[surface] = [{"cursor": None, "next_cursor": None, "items": items,
                               "observed_at_ms": NOW_MS, "symbols": symbols,
                               "account_id": "account-a", "snapshot_id": "snap-a"}]
        return value

    def collect(self, run_id, fixture=None, **kwargs):
        return collect_fixture_evidence(
            self.db_path, self.evidence, run_id, fixture or self.fixture,
            "account-a", "snap-a", current_time_ms=NOW_MS, **kwargs)

    def test_wal_aware_backup_and_fixture_label_are_explicit(self):
        result = self.collect("run-1")
        self.assertEqual(result["status"], "PASS_FIXTURE_ONLY")
        self.assertTrue(result["fixture_only"])
        self.assertFalse(result["production_authorized"])
        with open(os.path.join(result["run_dir"], "reconciliation.json")) as stream:
            receipt = json.load(stream)
        self.assertEqual(receipt["database_capture_mode"], "WAL_AWARE_SQLITE_BACKUP_COPY")
        self.assertFalse(receipt["authenticated_get_receipts_verified"])
        self.assertFalse(receipt["final_snapshot_live_admissible"])
        self.assertTrue(all(call["evidence_level"] == "SIMULATED_FIXTURE_ONLY"
                            for call in receipt["calls"]))

    def test_concurrent_wal_commit_is_not_hidden_by_immutable_live_reader(self):
        writer = sqlite3.connect(self.db_path)
        writer.execute("PRAGMA journal_mode=WAL")
        row = {"symbol": "BTCUSDT", "positionSide": "LONG", "positionAmt": "1"}
        def commit_after_read_connection_opens():
            writer.execute("INSERT INTO position_snapshots VALUES(1,?,?,?,?,?,?,?)",
                           ("snap-a", "account-a", "BTCUSDT", "LONG", "1",
                            str(NOW_MS), json.dumps(row)))
            writer.commit()
        run_dir = os.path.join(self.evidence, "wal-counterexample")
        os.mkdir(run_dir, 0o700)
        database = ReadOnlyBusinessDatabase(self.db_path, run_dir, "account-a", "snap-a",
                                            NOW_MS, before_backup_hook=commit_after_read_connection_opens)
        try:
            self.assertEqual(database.exchange_rows("positions"), [row])
            self.assertFalse(database.capture["source_stable_during_capture"])
        finally:
            database.close_and_verify(); writer.close()

    def test_account_snapshot_and_freshness_binding_rejects_mixed_old_or_omitted(self):
        connection = sqlite3.connect(self.db_path)
        other = json.dumps({"raw": {"assets": [{"asset": "MIXED"}]}}, sort_keys=True)
        connection.execute("INSERT INTO account_snapshots VALUES(2,?,?,?,?)",
                           ("snap-b", "account-b", str(NOW_MS + 1), other))
        position = {"symbol": "ETHUSDT", "positionSide": "SHORT", "positionAmt": "2"}
        connection.execute("INSERT INTO position_snapshots VALUES(1,?,?,?,?,?,?,?)",
                           ("snap-a", "account-a", "ETHUSDT", "SHORT", "2",
                            str(NOW_MS), json.dumps(position)))
        connection.execute("INSERT INTO account_snapshots VALUES(3,?,?,?,?)",
                           ("old-snap", "account-a", str(NOW_MS - 60000),
                            json.dumps({"raw": {"assets": []}})))
        connection.commit(); connection.close()
        result = self.collect("omitted")
        self.assertEqual(result["status"], "HOLD")
        with self.assertRaises(GateError):
            collect_fixture_evidence(self.db_path, self.evidence, "old", self.fixture,
                                     "account-a", "old-snap", current_time_ms=NOW_MS,
                                     max_age_ms=1000)

    def test_algo_and_protection_require_independent_tables(self):
        ordinary = {"symbol": "SOLUSDT", "type": "STOP_MARKET", "status": "NEW"}
        algo = {"symbol": "SOLUSDT", "type": "TRAILING_STOP_MARKET", "status": "NEW"}
        connection = sqlite3.connect(self.db_path)
        connection.execute("INSERT INTO order_snapshots VALUES(1,?,?,?,?,?,?,?)",
                           ("snap-a", "account-a", "SOLUSDT", "o1", "NEW",
                            str(NOW_MS), json.dumps(ordinary)))
        connection.execute("INSERT INTO algo_order_snapshots VALUES(1,?,?,?,?,?,?,?)",
                           ("snap-a", "account-a", "SOLUSDT", "a1", "NEW",
                            str(NOW_MS), json.dumps(algo)))
        connection.commit(); connection.close()
        run_dir = os.path.join(self.evidence, "dedicated"); os.mkdir(run_dir, 0o700)
        database = ReadOnlyBusinessDatabase(self.db_path, run_dir, "account-a", "snap-a", NOW_MS)
        try:
            self.assertEqual(database.exchange_rows("algo_orders"), [algo])
            self.assertNotEqual(database.exchange_rows("open_orders"), [algo])
            self.assertEqual(database.exchange_rows("protective_orders"), [])
        finally:
            database.close_and_verify()

    def test_pagination_and_independent_clock_negative_cases(self):
        fixture = self.make_fixture()
        fixture["trades"] = [
            {"cursor": None, "next_cursor": "p2", "items": [], "observed_at_ms": NOW_MS,
             "symbols": ["BTCUSDT"], "account_id": "account-a", "snapshot_id": "snap-a"},
            {"cursor": "p2", "next_cursor": None, "items": [], "observed_at_ms": NOW_MS,
             "symbols": ["ETHUSDT", "SOLUSDT"], "account_id": "account-a",
             "snapshot_id": "snap-a"}]
        self.assertTrue(FixtureGetOnlyPager(fixture).collect(
            "trades", SYMBOLS, NOW_MS, "account-a", "snap-a")["pagination_complete"])
        fixture["trades"][1]["cursor"] = "gap"
        with self.assertRaises(GateError):
            FixtureGetOnlyPager(fixture).collect("trades", SYMBOLS, NOW_MS,
                                                 "account-a", "snap-a")
        stale = self.make_fixture(); stale["server_time"][0]["items"]["serverTime"] -= 20000
        self.assertEqual(self.collect("stale-clock", stale)["status"], "HOLD")
        mixed = self.make_fixture(); mixed["positions"][0]["account_id"] = "account-b"
        with self.assertRaises(GateError):
            self.collect("mixed-page", mixed)
        with mock.patch("readonly_reconciliation_adapter.time.time",
                        side_effect=(1.0, 3.0)):
            with self.assertRaises(GateError):
                self.collect("deadline", max_capture_ms=1000)

    def test_authenticated_pager_binds_clock_role_account_hash_and_verifier(self):
        timeline = iter((1000, 1001, 1002, 1003, 1004, 1005))
        def clock(): return next(timeline)
        def transport(surface, symbol, cursor, account_id, snapshot_id):
            item = [] if symbol is None else [{"symbol": symbol}]
            response = {"items": item, "next_cursor": None, "observed_at_ms": NOW_MS}
            receipt = {"method": "GET", "endpoint": dict(SURFACE_REQUESTS)[surface],
                "request_id": surface + str(symbol),
                "credential_role": "BINANCE_ACCOUNT_READONLY", "account_id": account_id,
                "request_started_ms": 1000 if symbol in (None, "BTCUSDT") else
                    (1002 if symbol == "ETHUSDT" else 1004),
                "request_finished_ms": 1001 if symbol in (None, "BTCUSDT") else
                    (1003 if symbol == "ETHUSDT" else 1005),
                "response_sha256": sha256_value(response), "auth_evidence_sha256": "a" * 64}
            return response, receipt
        pager = AuthenticatedGetOnlyPager(transport, lambda receipt, response: True,
                                         clock, 2000)
        value = pager.collect("positions", SYMBOLS, "account-a", "snap-a")
        self.assertTrue(value["authenticated_get_receipts_verified"])
        self.assertEqual(len(pager.calls), 3)


def _test_sign(seed, message):
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8; scalar |= 1 << 254
    public_key = executor._encodepoint(executor._scalarmult(executor._B, scalar))
    nonce = int.from_bytes(hashlib.sha512(digest[32:] + message).digest(), "little") % executor._L
    encoded_r = executor._encodepoint(executor._scalarmult(executor._B, nonce))
    challenge = int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(),
                               "little") % executor._L
    signature = encoded_r + ((nonce + challenge * scalar) % executor._L).to_bytes(32, "little")
    return public_key, signature


class RestrictedExecutorTests(unittest.TestCase):
    def setUp(self):
        module_dir = os.path.dirname(__file__)
        self.temp = tempfile.TemporaryDirectory(dir=module_dir)
        self.uid = os.getuid()
        self.allowed_path = os.path.join(self.temp.name, "allowed")
        os.mkdir(self.allowed_path, 0o700)
        self.ledger = os.path.join(self.temp.name, "ledger.sqlite")
        self.request_value = {
            "tx_id": "tx-1", "host": "iZmj7a5kwr75qc1tul4kf9Z", "action": "KOREA_DEPLOY",
            "paths": [self.allowed_path], "units": ["xuanjun-binance-shadow.service"],
            "candidate_sha256": "a" * 64, "authority_id": "independent-authority-1",
            "one_time_nonce_sha256": "b" * 64, "timeout_seconds": 2,
            "independent_verifier_sha256": "c" * 64,
            "expected_postconditions": [{
                "postcondition_id": "e1", "kind": "CANDIDATE_TEST",
                "target_sha256": "a" * 64, "required_state": "COMPLETE",
                "is_effect": True}]}
        self.anchor = {"schema_version": 1, "algorithm": "Ed25519",
                       "authority_id": "independent-authority-1", "public_key_hex": "0" * 64}
        self.policy = {"schema_version": 3, "policy_id": "policy-1",
                       "candidate_sha256": "a" * 64, "expires_at_epoch": 2000000000,
                       "one_time_authority_id": "independent-authority-1",
                       "authorized_request_sha256": sha256_value(self.request_value),
                       "execution_identity": "xuanjun_binance",
                       "independent_verifier_sha256": "c" * 64,
                       "trust_anchor_sha256": "0" * 64,
                       "hosts": {"iZmj7a5kwr75qc1tul4kf9Z": {
                           "paths": [self.allowed_path],
                           "units": ["xuanjun-binance-shadow.service"],
                           "actions": ["KOREA_DEPLOY"]}}}

    def tearDown(self):
        self.temp.cleanup()

    def signed_policy(self, policy=None, tamper_signature=False):
        policy = dict(policy or self.policy)
        anchor = dict(self.anchor)
        seed = bytes(range(32))
        provisional = canonical_bytes(policy)
        public_key, unused = _test_sign(seed, provisional)
        anchor["public_key_hex"] = public_key.hex()
        policy["trust_anchor_sha256"] = sha256_value(anchor)
        payload = canonical_bytes(policy)
        public_key, signature = _test_sign(seed, payload)
        self.assertEqual(public_key.hex(), anchor["public_key_hex"])
        if tamper_signature:
            signature = bytes([signature[0] ^ 1]) + signature[1:]
        paths = [os.path.join(self.temp.name, name)
                 for name in ("policy.json", "policy.sig", "anchor.json")]
        for path, content in ((paths[0], payload), (paths[1], signature.hex().encode("ascii")),
                              (paths[2], canonical_bytes(anchor))):
            with open(path, "wb") as stream:
                stream.write(content)
            os.chmod(path, 0o600)
        return load_verified_policy(paths[0], paths[1], paths[2], self.uid)

    def execute(self, request=None, runner=runner_ok, verifier=verifier_ok,
                tx="tx-1", nonce=None):
        request = dict(request or self.request_value)
        request["tx_id"] = tx
        if nonce is not None:
            request["one_time_nonce_sha256"] = nonce
        policy = dict(self.policy)
        policy["authorized_request_sha256"] = sha256_value(request)
        verified = self.signed_policy(policy)
        with mock.patch("restricted_executor.runtime_identity", return_value={
                "host": request["host"], "os_identity": "xuanjun_binance"}):
            return execute_candidate(request, verified, self.ledger, runner, verifier,
                                     now_epoch=1900000000)

    def test_independent_signature_exact_hash_and_strict_success(self):
        result = self.execute()
        self.assertEqual(result["status"], "SUCCEEDED")
        ledger = TransactionLedger(self.ledger)
        try:
            self.assertEqual(ledger.read("tx-1")["state"], "SUCCEEDED")
        finally:
            ledger.close()
        bad = dict(self.policy); bad["candidate_sha256"] = "G" * 64
        with self.assertRaises(GateError):
            self.signed_policy(bad)
        with self.assertRaises(GateError):
            self.signed_policy(tamper_signature=True)

    def test_caller_dict_or_wrong_runtime_identity_cannot_gain_execution(self):
        with self.assertRaises(GateError):
            execute_candidate(self.request_value, self.policy, self.ledger, runner_ok,
                              now_epoch=1900000000)
        verified = self.signed_policy()
        with mock.patch("restricted_executor.runtime_identity",
                        return_value={"host": "wrong", "os_identity": "xuanjun_binance"}):
            with self.assertRaises(GateError):
                execute_candidate(self.request_value, verified, self.ledger, runner_ok,
                                  now_epoch=1900000000)

    def test_path_normalization_ownership_and_symlink_fail_closed(self):
        link = os.path.join(self.temp.name, "link")
        os.symlink(self.allowed_path, link)
        bad = dict(self.policy); bad["hosts"] = {"iZmj7a5kwr75qc1tul4kf9Z": {
            "paths": [link], "units": ["xuanjun-binance-shadow.service"],
            "actions": ["KOREA_DEPLOY"]}}
        with self.assertRaises(GateError):
            self.signed_policy(bad)
        verified = self.signed_policy()
        moved = self.allowed_path + ".moved"
        os.rename(self.allowed_path, moved)
        os.symlink(moved, self.allowed_path)
        with mock.patch("restricted_executor.runtime_identity", return_value={
                "host": self.request_value["host"], "os_identity": "xuanjun_binance"}):
            with self.assertRaises(GateError):
                execute_candidate(self.request_value, verified, self.ledger, runner_ok,
                                  now_epoch=1900000000)

    def test_missing_wrong_type_unverified_effect_and_timeout_are_unknown(self):
        cases = []
        missing = runner_ok(self.request_value); missing.pop("postcondition_verified")
        cases.append(lambda unused: missing)
        wrong_type = runner_ok(self.request_value); wrong_type["postcondition_verified"] = 1
        cases.append(lambda unused: wrong_type)
        unverified = runner_ok(self.request_value); unverified["effect_verification"][0]["verified"] = False
        cases.append(lambda unused: unverified)
        cases.append(runner_unknown)
        for index, runner in enumerate(cases):
            result = self.execute(runner=runner, tx="unknown-{0}".format(index),
                                  nonce=("{0:064x}".format(index + 2)))
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertFalse(result["blind_retry_allowed"])
        result = self.execute(runner=runner_slow, tx="timeout", nonce="d" * 64)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("NO_CGROUP_PROOF", result["containment"])

    def test_independent_verifier_and_zero_effect_policy_fail_closed(self):
        def unverified(request, runner_result):
            value = verifier_ok(request, runner_result)
            value["all_postconditions_verified"] = False
            unsigned = dict(value); unsigned.pop("evidence_sha256")
            value["evidence_sha256"] = sha256_value(unsigned)
            return value
        result = self.execute(verifier=unverified, tx="bad-verifier", nonce="8" * 64)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["blind_retry_allowed"])

        request = dict(self.request_value)
        request["action"] = "READONLY_INSPECT"
        request["expected_postconditions"] = [{
            "postcondition_id": "readonly-no-mutation", "kind": "PRODUCTION_MUTATION",
            "target_sha256": "1" * 64, "required_state": "NO", "is_effect": False}]
        request["units"] = []
        def readonly_runner(value):
            result = runner_ok(value)
            result["side_effects_attempted"] = False
            result["side_effects"] = []
            result["effect_verification"] = []
            return result
        policy = dict(self.policy)
        policy["hosts"] = {request["host"]: {"paths": [self.allowed_path],
                            "units": [], "actions": ["READONLY_INSPECT"]}}
        request["tx_id"] = "readonly"
        request["one_time_nonce_sha256"] = "7" * 64
        policy["authorized_request_sha256"] = sha256_value(request)
        verified = self.signed_policy(policy)
        with mock.patch("restricted_executor.runtime_identity", return_value={
                "host": request["host"], "os_identity": "xuanjun_binance"}):
            result = execute_candidate(request, verified, self.ledger, readonly_runner,
                                       verifier_ok, now_epoch=1900000000)
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_replay_and_cgroup_boundary_are_explicit(self):
        self.execute()
        with self.assertRaises(GateError):
            self.execute()
        value = cgroup_candidate_spec("tx-cgroup")
        self.assertFalse(value["invoked"])
        self.assertFalse(value["actual_cgroup_boundary_proven"])
        self.assertEqual(value["containment_level"], "CANDIDATE_DATA_ONLY_NOT_INVOKED")


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

    def test_all_95_remain_unknown_and_deny(self):
        manifest = build_coverage(self.private_map())
        self.assertTrue(validate_manifest(manifest))
        result = coverage_assessment(manifest)
        self.assertEqual((result["checked"], result["status"], len(result["unknown"])),
                         (95, "HOLD", 95))
        record = manifest["records"][0]
        evaluated = evaluate_launch(record, "/private/path/0.py", record["source_sha256"],
                                    "PROTECTIVE_CREATE", {})
        self.assertEqual(evaluated["decision"], "DENY")


class KoreaTransportTests(unittest.TestCase):
    def test_method_host_path_redirect_dns_and_proxy_bypass(self):
        self.assertEqual(validate_request(
            "GET", "https://fapi.binance.com/fapi/v3/account?timestamp=1")["decision"],
            "ALLOW_GET_ONLY")
        for method, url in (("POST", "https://fapi.binance.com/fapi/v3/account"),
                            ("GET", "https://evil.example/fapi/v3/account"),
                            ("GET", "http://fapi.binance.com/fapi/v3/account"),
                            ("GET", "https://fapi.binance.com/fapi/v1/order")):
            with self.assertRaises(PolicyDenied):
                validate_request(method, url)
        transport = ControlledHttpsTransport("fapi.binance.com", ["203.0.113.10"])
        self.assertEqual(transport.proxy_policy, "ENVIRONMENT_PROXY_BYPASSED_RAW_SOCKET")
        with self.assertRaises(PolicyDenied):
            transport._select_pinned_ip(["203.0.113.11"])
        with self.assertRaises(PolicyDenied):
            transport._validate_status(302)

    def test_transport_receipt_binds_dns_tls_and_no_redirect(self):
        class FakeSocket(object):
            def getpeercert(self, binary_form=False):
                return b"certificate" if binary_form else {}
        class FakeResponse(object):
            status = 200
            def read(self, unused): return b"{}"
        class FakeConnection(object):
            def __init__(self, host, ip, port, timeout, context):
                self.sock = FakeSocket(); self.closed = False
            def request(self, method, target, headers=None):
                if method != "GET": raise AssertionError("GET required")
            def getresponse(self): return FakeResponse()
            def close(self): self.closed = True
        transport = ControlledHttpsTransport("fapi.binance.com", ["203.0.113.10"])
        with mock.patch.object(transport, "_resolve",
                               return_value=("203.0.113.10", ["203.0.113.10"])), \
             mock.patch.object(get_only_policy, "PinnedHTTPSConnection", FakeConnection):
            body, receipt = transport.get("https://fapi.binance.com/fapi/v1/time")
        self.assertEqual(body, b"{}")
        self.assertFalse(receipt["proxy_used"])
        self.assertFalse(receipt["redirect_followed"])
        self.assertFalse(receipt["root_egress_isolation_proven"])
        self.assertEqual(receipt["tls_peer_certificate_sha256"],
                         hashlib.sha256(b"certificate").hexdigest())

    def test_transport_refuses_redirect_without_following_location(self):
        class RedirectResponse(object):
            status = 302
        class FakeConnection(object):
            def __init__(self, host, ip, port, timeout, context): self.sock = None
            def request(self, method, target, headers=None): pass
            def getresponse(self): return RedirectResponse()
            def close(self): pass
        transport = ControlledHttpsTransport("fapi.binance.com", ["203.0.113.10"])
        with mock.patch.object(transport, "_resolve",
                               return_value=("203.0.113.10", ["203.0.113.10"])), \
             mock.patch.object(get_only_policy, "PinnedHTTPSConnection", FakeConnection):
            with self.assertRaises(PolicyDenied):
                transport.get("https://fapi.binance.com/fapi/v1/time")
        self.assertEqual(transport.receipts, [])


class PackageIntegrityTests(unittest.TestCase):
    def test_candidate_manifest_recomputes_every_file(self):
        root = os.path.dirname(__file__)
        with open(os.path.join(root, "candidate-manifest.json")) as stream:
            value = json.load(stream)
        self.assertFalse(value["production_authorized"])
        self.assertFalse(value["binance_called"])
        for item in value["files"]:
            path = os.path.join(os.path.dirname(root), item["path"])
            digest = hashlib.sha256()
            with open(path, "rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            self.assertEqual(digest.hexdigest(), item["sha256"])
            self.assertEqual(os.path.getsize(path), item["size"])

    def test_public_writer_manifest_matches_frozen_private_digest(self):
        root = os.path.dirname(__file__)
        with open(os.path.join(root, "writer-coverage-public.json")) as stream:
            value = json.load(stream)
        self.assertEqual(value["source_discovery_count"], 95)
        self.assertEqual(value["private_mapping_sha256"],
                         "8f5ad7df2c63dd1b541ec4d21ab315b9cf0c23f00f77e326b59c82d92053f65b")
        self.assertEqual(set(record["candidate_enforcement"] for record in value["records"]),
                         set(("DENY",)))


if __name__ == "__main__":
    unittest.main()
