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
import stat
import subprocess
import sys
import time
from urllib.parse import urlencode

from gate_common import GateError, canonical_bytes, require, sha256_value
from final_snapshot import REQUIRED_SURFACES, RECONCILED_STATE_CLASSES, SURFACE_REQUESTS
from korea.get_only_policy import ControlledHttpsTransport
from readonly_reconciliation_adapter import (
    AuthenticatedGetOnlyPager,
    EvidenceDirectory,
    LOCAL_COMPARE_SURFACES,
    ReadOnlyBusinessDatabase,
    SYMBOLS,
)


ROLE = "BINANCE_ACCOUNT_READONLY"
WRITE_WORDS = frozenset(("POST", "PUT", "PATCH", "DELETE", "ORDER", "CANCEL"))
SINGLETON_SURFACES = frozenset(("server_time", "account", "balances", "position_mode"))
PAGED_SURFACES = frozenset(("recent_orders", "trades"))


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
    return value


class IndependentReceiptVerifier(object):
    def __init__(self, command, expected_sha256):
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

    def __call__(self, receipt, response):
        result = subprocess.run(
            [self.command, "verify-shadow-receipt"],
            input=canonical_bytes({"receipt": receipt, "response": response}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False,
        )
        if result.returncode != 0:
            return False
        try:
            value = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        return value == {"verified": True}


class SignedReadonlyTransport(object):
    """Surface adapter whose only network primitive is ControlledHttpsTransport.get."""
    def __init__(self, transport, api_key, api_secret, clock_ms=None):
        require(isinstance(transport, ControlledHttpsTransport),
                "SHADOW_CONTROLLED_TRANSPORT_REQUIRED")
        self.transport = transport
        self.api_key = api_key.decode("utf-8")
        self.api_secret = api_secret
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.paths = dict(SURFACE_REQUESTS)

    @staticmethod
    def _items(surface, value):
        if surface in SINGLETON_SURFACES:
            require(isinstance(value, (dict, list)), "SHADOW_SINGLETON_RESPONSE_INVALID")
            return value
        require(isinstance(value, list), "SHADOW_LIST_RESPONSE_INVALID")
        return value

    def __call__(self, surface, symbol, cursor, account_id, snapshot_id):
        require(surface in REQUIRED_SURFACES, "SHADOW_SURFACE_NOT_ALLOWLISTED")
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
        body, network_receipt = self.transport.get(
            "https://fapi.binance.com" + path + (("?" + query) if query else ""),
            headers=headers,
        )
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
        receipt = {
            "method": "GET", "endpoint": path,
            "request_id": hashlib.sha256((snapshot_id + surface + str(symbol) +
                                           str(cursor)).encode("utf-8")).hexdigest(),
            "credential_role": ROLE, "account_id": account_id,
            "request_started_ms": started, "request_finished_ms": finished,
            "response_sha256": sha256_value(response),
            "auth_evidence_sha256": hashlib.sha256(canonical_bytes({
                "credential_role": ROLE, "endpoint": path,
                "query_keys": sorted(key for key in parameters if key != "signature"),
                "network_receipt": network_receipt,
            })).hexdigest(),
        }
        return response, receipt


def run_once(config, now_ms=None):
    started = int(time.time() * 1000) if now_ms is None else now_ms
    api_key = _read_secure_file(config["api_key_file"], "READONLY_API_KEY")
    api_secret = _read_secure_file(config["api_secret_file"], "READONLY_API_SECRET")
    verifier = IndependentReceiptVerifier(config["verifier_command"],
                                          config["verifier_sha256"])
    directory = EvidenceDirectory(config["evidence_root"], config["business_database"])
    run_id = "shadow-" + str(started)
    run_dir = directory.create_run(run_id)
    database = ReadOnlyBusinessDatabase(
        config["business_database"], run_dir, config["account_id"], run_id,
        started, config["snapshot_max_age_ms"],
    )
    try:
        local = database.snapshot()
        deadline = started + config["capture_timeout_ms"]
        transport = SignedReadonlyTransport(
            ControlledHttpsTransport("fapi.binance.com", config["pinned_ips"]),
            api_key, api_secret,
        )
        pager = AuthenticatedGetOnlyPager(
            transport, verifier, lambda: int(time.time() * 1000), deadline,
        )
        surfaces = dict((surface, pager.collect(
            surface, SYMBOLS, config["account_id"], run_id
        )) for surface in REQUIRED_SURFACES)
        blockers = []
        for name in LOCAL_COMPARE_SURFACES:
            if sha256_value(local["exchange_mirror"][name]) != sha256_value(surfaces[name]["data"]):
                blockers.append("STATE_MISMATCH:" + name)
        if local["unknown_orders"]:
            blockers.append("UNKNOWN_EXECUTION")
        if local["inflight_requests"]:
            blockers.append("INFLIGHT_REQUESTS")
        if local["ownership_conflicts"]:
            blockers.append("OWNERSHIP_CONFLICTS")
        verification = database.close_and_verify()
        if not verification["source_stable_through_read"]:
            blockers.append("SQLITE_SOURCE_CHANGED_AFTER_CAPTURE")
        result = {
            "schema_version": 1, "feature_id": config["feature_id"],
            "mode": "KOREA_GET_ONLY_SHADOW", "run_id": run_id,
            "status": "PASS_READONLY_SHADOW_CYCLE" if not blockers else "HOLD",
            "blockers": blockers, "surfaces": surfaces, "calls": pager.calls,
            "local_state_sha256": sha256_value(local),
            "source_verification": verification, "binance_methods": ["GET"],
            "writer_enabled": False, "scheduler_enabled": False,
            "production_authorized": False,
        }
        files = [
            directory.write_once(run_dir, "exchange-pages.json", surfaces),
            directory.write_once(run_dir, "local-state.json", local),
            directory.write_once(run_dir, "reconciliation.json", result),
        ]
        return {"status": result["status"], "run_id": run_id, "files": files}
    except Exception:
        try:
            database.connection.close()
        except Exception:
            pass
        raise


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
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        print(json.dumps(self_check(), sort_keys=True))
        return 0
    require(args.once and args.config, "SHADOW_EXPLICIT_ONCE_AND_CONFIG_REQUIRED")
    print(json.dumps(run_once(_load_config(args.config)), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"status": "HOLD", "error_type": type(error).__name__,
                          "production_authorized": False}, sort_keys=True), file=sys.stderr)
        sys.exit(2)
