"""Executable Korea GET-only Shadow entry.

The module has no exchange write method.  It reads a closed/WAL-aware business
snapshot, obtains Binance Futures state through the controlled GET transport,
requires a separately installed receipt verifier, and writes append-only evidence.
"""
from __future__ import print_function

import argparse
import hashlib
import hmac
import json
import os
import signal
import stat
import subprocess
import sys
import time
from urllib.parse import urlencode
from contextlib import contextmanager

from gate_common import GateError, canonical_bytes, require, sha256_value
from final_snapshot import REQUIRED_SURFACES, RECONCILED_STATE_CLASSES, SURFACE_REQUESTS
from korea.get_only_policy import ControlledHttpsTransport
from korea.snapshot_handoff import PROTOCOL as SNAPSHOT_PROTOCOL, admit_snapshot_handoff
from readonly_reconciliation_adapter import (
    AuthenticatedGetOnlyPager,
    EvidenceDirectory,
    LOCAL_COMPARE_SURFACES,
    ReadOnlyBusinessDatabase,
    SYMBOLS,
    evaluate_reconciliation,
)


ROLE = "BINANCE_ACCOUNT_READONLY"
WRITE_WORDS = frozenset(("POST", "PUT", "PATCH", "DELETE", "ORDER", "CANCEL"))
SINGLETON_SURFACES = frozenset(("server_time", "account", "balances", "position_mode"))
PAGED_SURFACES = frozenset(("recent_orders", "trades"))


@contextmanager
def _hard_deadline(seconds):
    """Bound DNS, TLS, body reads and SQLite capture, not only socket calls."""
    require(isinstance(seconds, (int, float)) and seconds > 0,
            "SHADOW_OVERALL_CAPTURE_DEADLINE_EXCEEDED")
    require(hasattr(signal, "setitimer") and hasattr(signal, "ITIMER_REAL"),
            "SHADOW_HARD_DEADLINE_UNAVAILABLE")
    previous_handler = signal.getsignal(signal.SIGALRM)
    def expired(unused_signum, unused_frame):
        raise GateError("SHADOW_OVERALL_CAPTURE_DEADLINE_EXCEEDED")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _read_secure_file(path, label):
    require(isinstance(path, str) and path.startswith("/"), label + "_PATH_REQUIRED")
    require(os.path.isfile(path) and not os.path.islink(path), label + "_REGULAR_FILE_REQUIRED")
    value = os.stat(path)
    require(stat.S_IMODE(value.st_mode) & 0o077 == 0, label + "_MODE_TOO_BROAD")
    with open(path, "rb") as stream:
        raw = stream.read().strip()
    require(raw and len(raw) <= 4096, label + "_VALUE_INVALID")
    return raw


def _load_config(path):
    raw = _read_secure_file(path, "SHADOW_CONFIG")
    value = json.loads(raw.decode("utf-8"))
    expected = frozenset((
        "schema_version", "feature_id", "account_id", "symbols",
        "business_database", "evidence_root", "pinned_ips", "credential_role",
        "api_key_file", "api_secret_file", "verifier_command",
        "verifier_sha256", "snapshot_max_age_ms", "capture_timeout_ms",
        "runtime_manifest_sha256", "snapshot_handoff_receipt",
        "snapshot_refresh_protocol", "snapshot_publisher_identity_sha256",
        "writer_enabled", "scheduler_enabled",
    ))
    require(isinstance(value, dict) and frozenset(value) == expected,
            "SHADOW_CONFIG_FIELDS_INVALID")
    require(value["schema_version"] == 1, "SHADOW_CONFIG_SCHEMA_INVALID")
    require(value["feature_id"] == "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
            "SHADOW_FEATURE_ID_INVALID")
    require(value["symbols"] == list(SYMBOLS), "SHADOW_SYMBOL_SET_INVALID")
    require(value["credential_role"] == ROLE, "SHADOW_CREDENTIAL_ROLE_INVALID")
    require(value["writer_enabled"] is False and value["scheduler_enabled"] is False,
            "SHADOW_WRITER_OR_SCHEDULER_MUST_BE_FALSE")
    serialized = canonical_bytes(value).upper()
    for forbidden in (b"BINANCE_TRADING", b"TRADING_CREDENTIAL_MASTER_KEY"):
        require(forbidden not in serialized, "SHADOW_FORBIDDEN_CREDENTIAL_REFERENCE")
    require(isinstance(value["pinned_ips"], list) and value["pinned_ips"],
            "SHADOW_PINNED_IPS_REQUIRED")
    require(type(value["snapshot_max_age_ms"]) is int and
            0 < value["snapshot_max_age_ms"] <= 300000,
            "SHADOW_SNAPSHOT_MAX_AGE_INVALID")
    require(type(value["capture_timeout_ms"]) is int and
            0 < value["capture_timeout_ms"] <= 300000,
            "SHADOW_CAPTURE_TIMEOUT_INVALID")
    require(value["snapshot_refresh_protocol"] == SNAPSHOT_PROTOCOL,
            "SHADOW_SNAPSHOT_REFRESH_PROTOCOL_INVALID")
    for name in ("runtime_manifest_sha256", "snapshot_publisher_identity_sha256"):
        require(isinstance(value[name], str) and len(value[name]) == 64 and
                all(character in "0123456789abcdef" for character in value[name]),
                "SHADOW_CONFIG_HASH_INVALID:" + name)
    require(isinstance(value["snapshot_handoff_receipt"], str) and
            value["snapshot_handoff_receipt"].startswith("/"),
            "SHADOW_SNAPSHOT_HANDOFF_PATH_INVALID")
    return value


class IndependentReceiptVerifier(object):
    def __init__(self, command, expected_sha256, monotonic=None, deadline_monotonic=None):
        require(isinstance(command, str) and command.startswith("/"),
                "SHADOW_VERIFIER_COMMAND_REQUIRED")
        require(os.path.isfile(command) and not os.path.islink(command),
                "SHADOW_VERIFIER_REGULAR_FILE_REQUIRED")
        identity = os.stat(command)
        require(identity.st_uid == 0 and stat.S_IMODE(identity.st_mode) & 0o022 == 0,
                "SHADOW_VERIFIER_ROOT_IMMUTABLE_REQUIRED")
        with open(command, "rb") as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        require(digest == expected_sha256, "SHADOW_VERIFIER_HASH_MISMATCH")
        self.command = command
        self.monotonic = monotonic or time.monotonic
        self.deadline_monotonic = deadline_monotonic

    def __call__(self, receipt, response):
        remaining = 10
        if self.deadline_monotonic is not None:
            remaining = min(remaining, self.deadline_monotonic - self.monotonic())
        if remaining <= 0:
            return False
        result = subprocess.run(
            [self.command, "verify-shadow-receipt"],
            input=canonical_bytes({"receipt": receipt, "response": response}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining, check=False,
        )
        if result.returncode != 0:
            return False
        try:
            value = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        expected = {
            "verified": True,
            "request_id": receipt["request_id"],
            "account_id": receipt["account_id"],
            "credential_role": receipt["credential_role"],
            "response_sha256": receipt["response_sha256"],
            "network_evidence_sha256": sha256_value(receipt["network_evidence"]),
        }
        return value == expected

    def verify_snapshot_handoff(self, receipt):
        remaining = 10
        if self.deadline_monotonic is not None:
            remaining = min(remaining, self.deadline_monotonic - self.monotonic())
        if remaining <= 0:
            return False
        result = subprocess.run(
            [self.command, "verify-snapshot-handoff"], input=canonical_bytes(receipt),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining, check=False,
        )
        if result.returncode != 0:
            return False
        try:
            value = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        return value == {
            "verified": True,
            "snapshot_generation_id": receipt["snapshot_generation_id"],
            "database_sha256": receipt["database_sha256"],
            "runtime_manifest_sha256": receipt["runtime_manifest_sha256"],
            "publisher_identity_sha256": receipt["publisher_identity_sha256"],
        }


class SignedReadonlyTransport(object):
    """Surface adapter whose only network primitive is ControlledHttpsTransport.get."""
    def __init__(self, transport, api_key, api_secret, observation_run_id,
                 deadline_monotonic, clock_ms=None, monotonic=None):
        require(isinstance(transport, ControlledHttpsTransport),
                "SHADOW_CONTROLLED_TRANSPORT_REQUIRED")
        self.transport = transport
        self.api_key = api_key.decode("utf-8")
        self.api_secret = api_secret
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.monotonic = monotonic or time.monotonic
        self.deadline_monotonic = deadline_monotonic
        self.observation_run_id = observation_run_id
        self.paths = dict(SURFACE_REQUESTS)

    @staticmethod
    def _items(surface, value):
        require(not (isinstance(value, dict) and "code" in value and "msg" in value),
                "SHADOW_BINANCE_ERROR_RESPONSE")
        if surface in SINGLETON_SURFACES:
            require(isinstance(value, (dict, list)), "SHADOW_SINGLETON_RESPONSE_INVALID")
            if surface == "server_time":
                require(isinstance(value, dict) and type(value.get("serverTime")) is int,
                        "SHADOW_SERVER_TIME_RESPONSE_INVALID")
            elif surface == "position_mode":
                require(isinstance(value, dict) and type(value.get("dualSidePosition")) is bool,
                        "SHADOW_POSITION_MODE_RESPONSE_INVALID")
            elif surface == "balances":
                require(isinstance(value, list) and all(
                    isinstance(item, dict) and isinstance(item.get("asset"), str)
                    for item in value), "SHADOW_BALANCE_RESPONSE_INVALID")
            elif surface == "account":
                require(isinstance(value, dict) and isinstance(value.get("assets"), list),
                        "SHADOW_ACCOUNT_RESPONSE_INVALID")
            return value
        require(isinstance(value, list), "SHADOW_LIST_RESPONSE_INVALID")
        require(all(isinstance(item, dict) for item in value),
                "SHADOW_LIST_ITEM_RESPONSE_INVALID")
        return value

    def __call__(self, surface, symbol, cursor, account_id, snapshot_id):
        require(surface in REQUIRED_SURFACES, "SHADOW_SURFACE_NOT_ALLOWLISTED")
        remaining = self.deadline_monotonic - self.monotonic()
        require(remaining > 0, "SHADOW_OVERALL_CAPTURE_DEADLINE_EXCEEDED")
        path = self.paths[surface]
        started = self.clock_ms()
        parameters = {}
        if surface != "server_time":
            parameters.update({"timestamp": started, "recvWindow": 5000})
        if symbol is not None:
            parameters["symbol"] = symbol
        if surface in PAGED_SURFACES:
            parameters["limit"] = 1000
            if cursor is not None:
                parameters["orderId" if surface == "recent_orders" else "fromId"] = cursor
        unsigned = urlencode(sorted(parameters.items()))
        if surface != "server_time":
            parameters["signature"] = hmac.new(
                self.api_secret, unsigned.encode("ascii"), hashlib.sha256
            ).hexdigest()
        query = urlencode(sorted(parameters.items()))
        headers = {} if surface == "server_time" else {"X-MBX-APIKEY": self.api_key}
        with _hard_deadline(remaining):
            body, network_receipt = self.transport.get(
                "https://fapi.binance.com" + path + (("?" + query) if query else ""),
                headers=headers, timeout_seconds=min(self.transport.timeout_seconds, remaining),
            )
        require(self.monotonic() <= self.deadline_monotonic,
                "SHADOW_OVERALL_CAPTURE_DEADLINE_EXCEEDED")
        finished = self.clock_ms()
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise GateError("SHADOW_BINANCE_JSON_INVALID")
        items = self._items(surface, decoded)
        next_cursor = None
        if surface in PAGED_SURFACES and isinstance(items, list) and len(items) == 1000:
            field = "orderId" if surface == "recent_orders" else "id"
            last = items[-1].get(field) if isinstance(items[-1], dict) else None
            require(isinstance(last, int), "SHADOW_PAGINATION_CURSOR_INVALID")
            next_cursor = str(last + 1)
        response = {"items": items, "next_cursor": next_cursor,
                    "observed_at_ms": finished}
        network_evidence = dict(network_receipt)
        network_evidence["normalized_response_sha256"] = sha256_value(response)
        receipt = {
            "method": "GET", "endpoint": path,
            "request_id": hashlib.sha256((self.observation_run_id + snapshot_id + surface +
                                           str(symbol) + str(cursor)).encode("utf-8")).hexdigest(),
            "credential_role": ROLE, "account_id": account_id,
            "request_started_ms": started, "request_finished_ms": finished,
            "response_sha256": sha256_value(response),
            "auth_evidence_sha256": hashlib.sha256(canonical_bytes({
                "credential_role": ROLE, "endpoint": path,
                "query_keys": sorted(key for key in parameters if key != "signature"),
                "network_evidence_sha256": sha256_value(network_evidence),
            })).hexdigest(),
            "network_evidence": network_evidence,
        }
        return response, receipt


def run_once(config, now_ms=None, clock_ms=None, monotonic=None,
             transport_factory=None, verifier_factory=None):
    clock = clock_ms or (lambda: int(time.time() * 1000))
    monotonic_clock = monotonic or time.monotonic
    started = clock() if now_ms is None else now_ms
    capture_started_ms = clock()
    capture_started_monotonic = monotonic_clock()
    deadline_monotonic = capture_started_monotonic + (config["capture_timeout_ms"] / 1000.0)
    api_key = _read_secure_file(config["api_key_file"], "READONLY_API_KEY")
    api_secret = _read_secure_file(config["api_secret_file"], "READONLY_API_SECRET")
    if verifier_factory is None:
        verifier = IndependentReceiptVerifier(
            config["verifier_command"], config["verifier_sha256"],
            monotonic=monotonic_clock, deadline_monotonic=deadline_monotonic)
    else:
        verifier = verifier_factory(config["verifier_command"], config["verifier_sha256"])
    directory = EvidenceDirectory(config["evidence_root"], config["business_database"])
    observation_run_id = "shadow-observation-" + str(started)
    run_dir = directory.create_run(observation_run_id)
    database = None; admitted = None
    try:
        with _hard_deadline(deadline_monotonic - monotonic_clock()):
            admitted = admit_snapshot_handoff(config, verifier, started)
            authenticated_generation = admitted.materialize(run_dir)
            database = ReadOnlyBusinessDatabase(
                authenticated_generation["path"], run_dir, config["account_id"], None,
                started, config["snapshot_max_age_ms"],
            )
            local = database.snapshot()
            admitted.close()
        authoritative_snapshot_id = local["snapshot_id"]
        transport = ((transport_factory or ControlledHttpsTransport)(
            "fapi.binance.com", config["pinned_ips"]))
        transport = SignedReadonlyTransport(
            transport, api_key, api_secret, observation_run_id,
            deadline_monotonic, clock_ms=clock, monotonic=monotonic_clock,
        )
        pager = AuthenticatedGetOnlyPager(
            transport, verifier, clock, started + config["capture_timeout_ms"],
        )
        surfaces = {}
        for surface in REQUIRED_SURFACES:
            require(monotonic_clock() <= deadline_monotonic,
                    "SHADOW_OVERALL_CAPTURE_DEADLINE_EXCEEDED")
            surfaces[surface] = pager.collect(
                surface, SYMBOLS, config["account_id"], authoritative_snapshot_id)
        capture_finished_ms = clock()
        blockers = evaluate_reconciliation(
            local, surfaces, pager.calls, started, capture_started_ms,
            capture_finished_ms, max_capture_ms=config["capture_timeout_ms"],
            require_authenticated=True)
        with _hard_deadline(deadline_monotonic - monotonic_clock()):
            verification = database.close_and_verify()
        if not verification["source_stable_through_read"]:
            blockers.append("SQLITE_SOURCE_CHANGED_AFTER_CAPTURE")
        result = {
            "schema_version": 1, "feature_id": config["feature_id"],
            "mode": "KOREA_GET_ONLY_SHADOW",
            "observation_run_id": observation_run_id,
            "authoritative_business_snapshot_id": authoritative_snapshot_id,
            "status": "PASS_READONLY_SHADOW_CYCLE" if not blockers else "HOLD",
            "blockers": blockers, "surfaces": surfaces, "calls": pager.calls,
            "local_state_sha256": sha256_value(local),
            "source_verification": verification, "binance_methods": ["GET"],
            "writer_enabled": False, "scheduler_enabled": False,
            "production_authorized": False,
            "snapshot_generation_id": admitted["snapshot_generation_id"],
            "snapshot_handoff_database_sha256": admitted["database_sha256"],
            "authenticated_generation": authenticated_generation,
        }
        files = [
            directory.write_once(run_dir, "exchange-pages.json", surfaces),
            directory.write_once(run_dir, "local-state.json", local),
            directory.write_once(run_dir, "reconciliation.json", result),
        ]
        return {"status": result["status"], "observation_run_id": observation_run_id,
                "authoritative_business_snapshot_id": authoritative_snapshot_id,
                "snapshot_generation_id": admitted["snapshot_generation_id"],
                "files": files}
    except Exception as error:
        try:
            if database is not None:
                database.connection.close()
        except Exception:
            pass
        try:
            if admitted is not None:
                admitted.close()
        except Exception:
            pass
        failure = {"schema_version": 1, "status": "HOLD",
                   "observation_run_id": observation_run_id,
                   "error_type": type(error).__name__, "production_authorized": False,
                   "writer_enabled": False, "scheduler_enabled": False}
        try:
            directory.write_once(run_dir, "reconciliation.json", failure)
        except Exception:
            pass
        return failure


def self_check():
    return {
        "feature_id": "TOKYO_KOREA_BINANCE_MIGRATION_CANONICAL_V1",
        "entry": "korea.migration_shadow_entry",
        "network_methods": ["GET"],
        "writer_enabled": False,
        "scheduler_enabled": False,
        "credential_role": ROLE,
        "forbidden_credential_references": ["BINANCE_TRADING", "TRADING_CREDENTIAL_MASTER_KEY"],
        "production_authorized": False,
        "status": "SELF_CHECK_PASS_NO_NETWORK",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--acceptance-config")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    require(bool(args.once) != bool(args.continuous) and args.config,
            "SHADOW_EXACTLY_ONE_MODE_AND_CONFIG_REQUIRED")
    if args.continuous:
        require(args.acceptance_config, "SHADOW_ACCEPTANCE_CONFIG_REQUIRED")
        from korea.shadow_acceptance import load_acceptance_config, run_continuous
        result = run_continuous(_load_config(args.config),
                                load_acceptance_config(args.acceptance_config))
    else:
        result = run_once(_load_config(args.config))
    print(json.dumps(result, sort_keys=True))
    if str(result.get("status", "")).startswith("PASS"):
        return 0
    return 3 if result.get("status") == "UNKNOWN" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"status": "HOLD", "error_type": type(error).__name__,
                          "production_authorized": False}, sort_keys=True), file=sys.stderr)
        sys.exit(2)
        sys.exit(2)
