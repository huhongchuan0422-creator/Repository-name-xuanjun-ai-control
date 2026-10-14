"""WAL-aware SQLite / fixture reconciliation candidate.

The live business DB is opened normally in read-only mode and copied with the
SQLite backup API.  Only the closed evidence copy uses ``immutable=1``.  Main,
WAL and SHM identities are bound around capture and collection.  Fixture GET
receipts remain explicitly simulated and can never authorize production.
"""
from __future__ import print_function

import datetime
import hashlib
import json
import os
import sqlite3
import stat
import time

from gate_common import GateError, canonical_bytes, require, sha256_value
from final_snapshot import (REQUIRED_SURFACES, RECONCILED_STATE_CLASSES,
                            SIDE_CAR_CLASSES, SURFACE_REQUESTS)


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
MAX_PAGE_COUNT = 1000
DEFAULT_MAX_AGE_MS = 30000
DEFAULT_MAX_CAPTURE_MS = 30000
DEFAULT_MAX_CLOCK_SKEW_MS = 10000
EVIDENCE_FILES = ("exchange-pages.json", "local-state.json", "reconciliation.json")
LOCAL_COMPARE_SURFACES = ("account", "balances", "position_mode") + tuple(RECONCILED_STATE_CLASSES)

# Algo/protective state has independent authoritative tables.  Ordinary order
# rows are not silently reclassified as endpoint evidence.
TABLE_SPECS = {
    "account": ("account_snapshots", ("id", "snapshot_id", "account_id", "created_time", "payload_json")),
    "balances": ("account_snapshots", ("id", "snapshot_id", "account_id", "created_time", "payload_json")),
    "position_mode": ("account_capabilities", ("id", "account_id", "environment", "position_mode", "status", "verified_time")),
    "positions": ("position_snapshots", ("id", "snapshot_id", "account_id", "symbol", "side", "quantity", "created_time", "payload_json")),
    "open_orders": ("order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "order_id", "status", "created_time", "payload_json")),
    "algo_orders": ("algo_order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "algo_id", "status", "created_time", "payload_json")),
    "protective_orders": ("protective_order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "algo_id", "status", "created_time", "payload_json")),
    "recent_orders": ("order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "order_id", "status", "created_time", "payload_json")),
    "trades": ("trade_snapshots", ("id", "snapshot_id", "account_id", "symbol", "trade_id", "order_id", "created_time", "payload_json")),
    "pending_queue": ("execution_requests", ("id", "request_id", "account_id", "status", "intent")),
    "recovery_queue": ("recovery_items", ("id", "recovery_id", "account_id", "state", "action")),
    "unknown_execution": ("execution_attempts", ("id", "attempt_id", "status", "error_type", "http_method")),
    "inflight_requests": ("execution_requests", ("id", "request_id", "account_id", "status", "intent")),
    "guard_state": ("kill_switch_state", ("id", "switch_name", "enabled", "reason")),
    "watch_state": ("health_checks", ("id", "check_id", "component", "status")),
    "ownership_ledger": ("audit_events", ("id", "event_id", "entity_type", "entity_id", "account_id")),
    "scheduler_state": ("sync_runs", ("id", "sync_run_id", "account_id", "symbol", "status")),
    "ownership_conflicts": ("account_anomaly_events", ("id", "event_id", "account_id", "anomaly_type", "state", "new_positions_locked")),
}


def _real(path):
    return os.path.realpath(os.path.abspath(path))


def _is_below(path, root):
    candidate, parent = _real(path), _real(root)
    return candidate == parent or candidate.startswith(parent + os.sep)


def _valid_identifier(value, code):
    require(isinstance(value, str) and value and len(value) <= 160 and
            all(character.isalnum() or character in "-_.:" for character in value), code)
    return value


def _file_identity(path, logical_name):
    if not os.path.exists(path):
        return {"logical_name": logical_name, "exists": False}
    require(os.path.isfile(path) and not os.path.islink(path),
            "G4_SQLITE_SIDECAR_INVALID:" + logical_name)
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    value = os.stat(path)
    return {"logical_name": logical_name, "exists": True, "size": value.st_size,
            "mtime_ns": int(value.st_mtime * 1000000000), "sha256": digest.hexdigest()}


def sqlite_file_set_identity(path):
    return [_file_identity(path, "main"), _file_identity(path + "-wal", "wal"),
            _file_identity(path + "-shm", "shm")]


def _epoch_ms(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, str):
        try:
            parsed = datetime.datetime.strptime(value.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            return int((parsed - datetime.datetime(1970, 1, 1)).total_seconds() * 1000)
        except ValueError:
            pass
    raise GateError("G4_SNAPSHOT_TIME_INVALID")


class EvidenceDirectory(object):
    def __init__(self, root, business_db):
        require(os.path.isdir(root) and not os.path.islink(root), "G4_EVIDENCE_ROOT_REQUIRED")
        require(not _is_below(root, os.path.dirname(business_db)), "G4_EVIDENCE_MUST_BE_SEPARATE")
        self.root = _real(root)

    def create_run(self, run_id):
        _valid_identifier(run_id, "G4_RUN_ID_INVALID")
        path = os.path.join(self.root, run_id)
        os.mkdir(path, 0o700)
        require(stat.S_IMODE(os.stat(path).st_mode) == 0o700, "G4_EVIDENCE_MODE_INVALID")
        return path

    @staticmethod
    def write_once(run_dir, name, value):
        require(name in EVIDENCE_FILES, "G4_EVIDENCE_NAME_NOT_ALLOWLISTED")
        target = os.path.join(run_dir, name)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
            stream.flush(); os.fsync(stream.fileno())
        return _file_identity(target, name)


def capture_consistent_sqlite_snapshot(source_path, run_dir, before_backup_hook=None):
    """Capture a coherent SQLite image with the read-only backup API."""
    require(os.path.isfile(source_path) and not os.path.islink(source_path),
            "G4_DB_REGULAR_FILE_REQUIRED")
    source_path = _real(source_path)
    target = os.path.join(run_dir, "business-snapshot.sqlite")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)
    before = sqlite_file_set_identity(source_path)
    source = sqlite3.connect("file:{0}?mode=ro".format(source_path), uri=True, timeout=10)
    destination = sqlite3.connect(target)
    try:
        source.execute("PRAGMA query_only=ON")
        if before_backup_hook is not None:
            require(callable(before_backup_hook), "G4_BACKUP_HOOK_INVALID")
            before_backup_hook()
        source.backup(destination)
        destination.commit()
    finally:
        destination.close(); source.close()
    after = sqlite_file_set_identity(source_path)
    return {"source_path": source_path, "snapshot_path": target,
            "source_identity_before": before, "source_identity_after_capture": after,
            "source_stable_during_capture": before == after,
            "snapshot_identity": _file_identity(target, "captured_snapshot"),
            "capture_semantics": "SQLITE_BACKUP_API_FROM_MODE_RO_WAL_AWARE",
            "freeze_claimed": False}


class ReadOnlyBusinessDatabase(object):
    def __init__(self, path, run_dir, account_id, snapshot_id, captured_at_ms,
                 max_age_ms=DEFAULT_MAX_AGE_MS, before_backup_hook=None):
        self.path = _real(path)
        self.account_id = _valid_identifier(account_id, "G4_ACCOUNT_ID_INVALID")
        self.snapshot_id = _valid_identifier(snapshot_id, "G4_SNAPSHOT_ID_INVALID")
        require(type(captured_at_ms) is int and captured_at_ms > 0, "G4_CAPTURE_TIME_INVALID")
        require(type(max_age_ms) is int and 0 < max_age_ms <= 300000, "G4_MAX_AGE_INVALID")
        self.captured_at_ms, self.max_age_ms = captured_at_ms, max_age_ms
        self.capture = capture_consistent_sqlite_snapshot(path, run_dir, before_backup_hook)
        uri = "file:{0}?mode=ro&immutable=1".format(self.capture["snapshot_path"])
        self.connection = sqlite3.connect(uri, uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only=ON")

    def _tables(self):
        return set(row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))

    def rows(self, logical_name):
        require(logical_name in TABLE_SPECS, "G4_DB_LOGICAL_TABLE_UNKNOWN")
        table, columns = TABLE_SPECS[logical_name]
        require(table in self._tables(), "G4_DB_TABLE_MISSING:" + table)
        actual = set(row[1] for row in self.connection.execute(
            "PRAGMA table_info({0})".format(table)))
        require(set(columns).issubset(actual), "G4_DB_COLUMNS_MISSING:" + table)
        clauses, parameters = [], []
        if "account_id" in columns:
            clauses.append('"account_id"=?'); parameters.append(self.account_id)
        if "snapshot_id" in columns:
            clauses.append('"snapshot_id"=?'); parameters.append(self.snapshot_id)
        sql = "SELECT {0} FROM {1}".format(
            ",".join('"{0}"'.format(column) for column in columns), table)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"
        return [dict(row) for row in self.connection.execute(sql, tuple(parameters))]

    def _require_fresh(self, rows, field):
        for row in rows:
            observed = _epoch_ms(row.get(field))
            require(observed <= self.captured_at_ms + DEFAULT_MAX_CLOCK_SKEW_MS,
                    "G4_SNAPSHOT_FROM_FUTURE")
            require(self.captured_at_ms - observed <= self.max_age_ms, "G4_SNAPSHOT_STALE")

    def _payload_rows(self, logical_name):
        rows = self.rows(logical_name)
        self._require_fresh(rows, "created_time")
        values = []
        for row in rows:
            try:
                value = json.loads(row.get("payload_json"))
            except (TypeError, ValueError):
                raise GateError("G4_DB_PAYLOAD_INVALID")
            require(isinstance(value, dict), "G4_DB_PAYLOAD_OBJECT_REQUIRED")
            if logical_name in RECONCILED_STATE_CLASSES:
                require(row.get("symbol") in SYMBOLS and value.get("symbol") == row.get("symbol"),
                        "G4_SYMBOL_BINDING_INVALID:" + logical_name)
            values.append(value)
        return values

    def exchange_rows(self, logical_name):
        if logical_name == "position_mode":
            rows = self.rows(logical_name)
            require(len(rows) == 1, "G4_POSITION_MODE_EXACT_ACCOUNT_ROW_REQUIRED")
            self._require_fresh(rows, "verified_time")
            mode = str(rows[0].get("position_mode") or "").upper()
            require(mode in ("HEDGE", "ONE_WAY", "ONEWAY"), "G4_POSITION_MODE_UNKNOWN")
            return {"dualSidePosition": mode == "HEDGE"}
        values = self._payload_rows(logical_name)
        if logical_name in ("account", "balances"):
            require(len(values) == 1, "G4_ACCOUNT_SNAPSHOT_EXACT_ROW_REQUIRED")
            raw = values[0].get("raw")
            require(isinstance(raw, dict), "G4_ACCOUNT_RAW_REQUIRED")
            if logical_name == "balances":
                require(isinstance(raw.get("assets"), list), "G4_ACCOUNT_ASSETS_REQUIRED")
                return raw["assets"]
            return raw
        if logical_name in ("open_orders", "algo_orders", "protective_orders"):
            return [row for row in values if row.get("status") in ("NEW", "PARTIALLY_FILLED")]
        return values

    def snapshot(self):
        exchange = dict((name, self.exchange_rows(name)) for name in LOCAL_COMPARE_SURFACES)
        sidecars = dict((name, self.rows(name)) for name in SIDE_CAR_CLASSES)
        unknown = [row for row in sidecars["unknown_execution"]
                   if row.get("status") in ("UNKNOWN", "TIMEOUT", "PARTIAL") or row.get("error_type")]
        inflight = [row for row in sidecars["inflight_requests"]
                    if row.get("status") in ("PENDING", "STARTED", "INFLIGHT", "UNKNOWN")]
        conflicts = [row for row in self.rows("ownership_conflicts")
                     if row.get("state") not in ("RESOLVED", "CLOSED") and
                     str(row.get("new_positions_locked")) in ("1", "true", "True")]
        return {"expected_symbols": list(SYMBOLS), "account_id": self.account_id,
                "snapshot_id": self.snapshot_id, "captured_at_ms": self.captured_at_ms,
                "exchange_mirror": exchange,
                "db_external_state": dict((name, {"sha256": sha256_value(rows)})
                                          for name, rows in sidecars.items()),
                "unknown_orders": unknown, "inflight_requests": inflight,
                "ownership_conflicts": conflicts,
                "sidecar_counts": dict((name, len(rows)) for name, rows in sidecars.items()),
                "sqlite_capture": self.capture}

    def close_and_verify(self):
        self.connection.close()
        source_after = sqlite_file_set_identity(self.path)
        return {"captured_snapshot_identity_after":
                    _file_identity(self.capture["snapshot_path"], "captured_snapshot"),
                "source_identity_after_read": source_after,
                "source_stable_through_read":
                    source_after == self.capture["source_identity_after_capture"]}


class FixtureGetOnlyPager(object):
    """Simulation pager; not an authenticated exchange transport."""
    def __init__(self, fixture, page_limit=100):
        require(isinstance(fixture, dict), "G4_FIXTURE_REQUIRED")
        require(type(page_limit) is int and 0 < page_limit <= 1000, "G4_PAGE_LIMIT_INVALID")
        self.fixture, self.page_limit, self.calls = fixture, page_limit, []

    def collect(self, surface, symbols, request_clock_ms, account_id, snapshot_id):
        require(surface in REQUIRED_SURFACES, "G4_SURFACE_NOT_ALLOWLISTED")
        require(set(symbols) == set(SYMBOLS), "G4_SYMBOL_SET_INVALID")
        pages = self.fixture.get(surface)
        require(isinstance(pages, list) and pages, "G4_FIXTURE_SURFACE_MISSING:" + surface)
        require(len(pages) <= MAX_PAGE_COUNT, "G4_PAGE_COUNT_EXCEEDED:" + surface)
        items, expected_cursor, covered, observed = [], None, set(), None
        for index, page in enumerate(pages):
            require(isinstance(page, dict), "G4_PAGE_INVALID:" + surface)
            require(set(page) == set(("cursor", "next_cursor", "items", "observed_at_ms",
                                      "symbols", "account_id", "snapshot_id")),
                    "G4_PAGE_FIELDS_INVALID:" + surface)
            require(page["account_id"] == account_id, "G4_PAGE_ACCOUNT_BINDING_INVALID:" + surface)
            require(page["snapshot_id"] == snapshot_id,
                    "G4_PAGE_SNAPSHOT_BINDING_INVALID:" + surface)
            require(page["cursor"] == expected_cursor, "G4_PAGE_CURSOR_GAP:" + surface)
            require(isinstance(page["items"], (list, dict)), "G4_PAGE_ITEMS_INVALID:" + surface)
            require(type(page["observed_at_ms"]) is int, "G4_PAGE_TIME_INVALID:" + surface)
            require(isinstance(page["symbols"], list), "G4_PAGE_SYMBOLS_INVALID:" + surface)
            if isinstance(page["items"], list):
                require(len(page["items"]) <= self.page_limit,
                        "G4_PAGE_LIMIT_EXCEEDED:" + surface)
                items.extend(page["items"])
            else:
                require(len(pages) == 1, "G4_OBJECT_SURFACE_MULTIPAGE:" + surface)
                items = page["items"]
            covered.update(page["symbols"])
            observed = page["observed_at_ms"] if observed is None else max(
                observed, page["observed_at_ms"])
            expected_cursor = page["next_cursor"]
            self.calls.append({"method": "GET", "surface": surface, "page": index,
                               "cursor_sha256": sha256_value(page["cursor"]),
                               "request_started_ms": request_clock_ms,
                               "request_finished_ms": request_clock_ms,
                               "authenticated_get_receipt": False,
                               "evidence_level": "SIMULATED_FIXTURE_ONLY"})
        require(expected_cursor is None, "G4_PAGINATION_NOT_TERMINATED:" + surface)
        if surface in RECONCILED_STATE_CLASSES:
            require(covered == set(SYMBOLS), "G4_SYMBOL_COVERAGE_INCOMPLETE:" + surface)
            require(all(isinstance(item, dict) and item.get("symbol") in SYMBOLS
                        for item in items), "G4_ITEM_SYMBOL_BINDING_INVALID:" + surface)
        return {"observed_at_ms": observed, "data": items, "pagination_complete": True,
                "symbols_covered": sorted(covered)}


class AuthenticatedGetOnlyPager(object):
    """Production-shaped pager requiring an independent receipt verifier.

    The transport and verifier are separate capabilities.  This task exercises
    them only with local fakes; no Binance connection is made.
    """
    RECEIPT_FIELDS = frozenset((
        "method", "endpoint", "request_id", "credential_role", "account_id",
        "request_started_ms", "request_finished_ms", "response_sha256",
        "auth_evidence_sha256"))

    def __init__(self, transport, receipt_verifier, clock_ms, capture_deadline_ms):
        require(callable(transport) and callable(receipt_verifier) and callable(clock_ms),
                "G4_AUTHENTICATED_TRANSPORT_VERIFIER_CLOCK_REQUIRED")
        require(type(capture_deadline_ms) is int and capture_deadline_ms > 0,
                "G4_AUTHENTICATED_CAPTURE_DEADLINE_INVALID")
        self.transport, self.receipt_verifier = transport, receipt_verifier
        self.clock_ms, self.capture_deadline_ms, self.calls = clock_ms, capture_deadline_ms, []
        self.paths = dict(SURFACE_REQUESTS)

    def _verified_page(self, surface, symbol, cursor, account_id, snapshot_id):
        before = self.clock_ms()
        require(type(before) is int and before <= self.capture_deadline_ms,
                "G4_AUTHENTICATED_CAPTURE_DEADLINE_EXCEEDED")
        response, receipt = self.transport(surface, symbol, cursor, account_id, snapshot_id)
        after = self.clock_ms()
        require(type(after) is int and before <= after <= self.capture_deadline_ms,
                "G4_AUTHENTICATED_CAPTURE_DEADLINE_EXCEEDED")
        require(isinstance(response, dict) and set(response) ==
                set(("items", "next_cursor", "observed_at_ms")),
                "G4_AUTHENTICATED_PAGE_INVALID")
        require(isinstance(receipt, dict) and set(receipt) == self.RECEIPT_FIELDS,
                "G4_AUTHENTICATED_RECEIPT_FIELDS_INVALID")
        require(receipt["method"] == "GET" and receipt["endpoint"] == self.paths[surface],
                "G4_AUTHENTICATED_RECEIPT_METHOD_ENDPOINT_INVALID")
        require(receipt["credential_role"] == "BINANCE_ACCOUNT_READONLY" and
                receipt["account_id"] == account_id,
                "G4_AUTHENTICATED_RECEIPT_ACCOUNT_ROLE_INVALID")
        require(type(receipt["request_started_ms"]) is int and
                type(receipt["request_finished_ms"]) is int and
                before <= receipt["request_started_ms"] <=
                receipt["request_finished_ms"] <= after,
                "G4_AUTHENTICATED_RECEIPT_TIME_INVALID")
        for field in ("response_sha256", "auth_evidence_sha256"):
            require(isinstance(receipt[field], str) and len(receipt[field]) == 64 and
                    all(character in "0123456789abcdef" for character in receipt[field]),
                    "G4_AUTHENTICATED_RECEIPT_HASH_INVALID")
        require(receipt["response_sha256"] == sha256_value(response),
                "G4_AUTHENTICATED_RESPONSE_HASH_MISMATCH")
        require(self.receipt_verifier(receipt, response) is True,
                "G4_AUTHENTICATED_RECEIPT_INDEPENDENT_VERIFICATION_FAILED")
        self.calls.append(receipt)
        return response

    def collect(self, surface, symbols, account_id, snapshot_id):
        require(surface in REQUIRED_SURFACES and set(symbols) == set(SYMBOLS),
                "G4_AUTHENTICATED_SURFACE_OR_SYMBOL_SET_INVALID")
        requested_symbols = list(symbols) if surface in RECONCILED_STATE_CLASSES else [None]
        collected, observed, covered = [], None, set()
        for symbol in requested_symbols:
            cursor, page_count = None, 0
            while True:
                page = self._verified_page(surface, symbol, cursor, account_id, snapshot_id)
                page_count += 1
                require(page_count <= MAX_PAGE_COUNT, "G4_AUTHENTICATED_PAGE_COUNT_EXCEEDED")
                items = page["items"]
                require(isinstance(items, (list, dict)), "G4_AUTHENTICATED_ITEMS_INVALID")
                if isinstance(items, list):
                    require(len(items) <= 1000, "G4_AUTHENTICATED_PAGE_LIMIT_EXCEEDED")
                    if symbol is not None:
                        require(all(isinstance(item, dict) and item.get("symbol") == symbol
                                    for item in items), "G4_AUTHENTICATED_SYMBOL_BINDING_INVALID")
                    collected.extend(items)
                else:
                    require(symbol is None and page_count == 1,
                            "G4_AUTHENTICATED_OBJECT_PAGINATION_INVALID")
                    collected = items
                observed = page["observed_at_ms"] if observed is None else max(
                    observed, page["observed_at_ms"])
                if symbol is not None: covered.add(symbol)
                cursor = page["next_cursor"]
                if cursor is None: break
                require(isinstance(cursor, str) and cursor, "G4_AUTHENTICATED_CURSOR_INVALID")
        if surface in RECONCILED_STATE_CLASSES:
            require(covered == set(SYMBOLS), "G4_AUTHENTICATED_SYMBOL_COVERAGE_INCOMPLETE")
        return {"observed_at_ms": observed, "data": collected,
                "pagination_complete": True, "symbols_covered": sorted(covered),
                "authenticated_get_receipts_verified": True}


def collect_fixture_evidence(database_path, evidence_root, run_id, fixture,
                             account_id, snapshot_id, current_time_ms=None,
                             max_age_ms=DEFAULT_MAX_AGE_MS,
                             max_capture_ms=DEFAULT_MAX_CAPTURE_MS,
                             before_backup_hook=None):
    """Run WAL-aware DB capture against network-free simulated pages."""
    clock_now = int(time.time() * 1000) if current_time_ms is None else current_time_ms
    require(type(clock_now) is int and clock_now > 0, "G4_INDEPENDENT_CURRENT_TIME_INVALID")
    require(type(max_capture_ms) is int and 0 < max_capture_ms <= 300000,
            "G4_CAPTURE_DEADLINE_INVALID")
    directory = EvidenceDirectory(evidence_root, database_path)
    run_dir = directory.create_run(run_id)
    started_ms = int(time.time() * 1000)
    database = ReadOnlyBusinessDatabase(database_path, run_dir, account_id, snapshot_id,
                                        clock_now, max_age_ms, before_backup_hook)
    try:
        local = database.snapshot()
        pager = FixtureGetOnlyPager(fixture)
        surfaces = dict((surface, pager.collect(surface, SYMBOLS, clock_now,
                                                account_id, snapshot_id))
                        for surface in REQUIRED_SURFACES)
        server = surfaces["server_time"]["data"]
        require(isinstance(server, dict) and type(server.get("serverTime")) is int,
                "G4_SERVER_TIME_INVALID")
        finished_ms = int(time.time() * 1000)
        require(finished_ms - started_ms <= max_capture_ms, "G4_CAPTURE_DEADLINE_EXCEEDED")
        blockers = []
        if abs(server["serverTime"] - clock_now) > DEFAULT_MAX_CLOCK_SKEW_MS:
            blockers.append("EXCHANGE_CLOCK_NOT_BOUND_TO_INDEPENDENT_CURRENT_TIME")
        for name in LOCAL_COMPARE_SURFACES:
            if sha256_value(local["exchange_mirror"][name]) != sha256_value(surfaces[name]["data"]):
                blockers.append("STATE_MISMATCH:" + name)
        for name, value in surfaces.items():
            if abs(value["observed_at_ms"] - server["serverTime"]) > DEFAULT_MAX_CLOCK_SKEW_MS:
                blockers.append("SURFACE_SKEW:" + name)
        require(len(pager.calls) >= len(REQUIRED_SURFACES) and
                all(call["method"] == "GET" for call in pager.calls),
                "G4_GET_EVIDENCE_INCOMPLETE")
        if local["unknown_orders"]: blockers.append("UNKNOWN_EXECUTION")
        if local["inflight_requests"]: blockers.append("INFLIGHT_REQUESTS")
        if local["ownership_conflicts"]: blockers.append("OWNERSHIP_CONFLICTS")
        if not local["sqlite_capture"]["source_stable_during_capture"]:
            blockers.append("SQLITE_SOURCE_CHANGED_DURING_CAPTURE")
        verification = database.close_and_verify()
        if not verification["source_stable_through_read"]:
            blockers.append("SQLITE_SOURCE_CHANGED_AFTER_CAPTURE")
        result = {"schema_version": 2, "adapter_mode": "SIMULATED_FIXTURE_ONLY",
                  "database_capture_mode": "WAL_AWARE_SQLITE_BACKUP_COPY",
                  "account_id": account_id, "snapshot_id": snapshot_id,
                  "independent_current_time_ms": clock_now,
                  "capture_started_wall_ms": started_ms,
                  "capture_finished_wall_ms": finished_ms,
                  "max_capture_ms": max_capture_ms, "surfaces": surfaces,
                  "calls": pager.calls, "blockers": blockers,
                  "status": "PASS_FIXTURE_ONLY" if not blockers else "HOLD",
                  "fixture_only": True, "authenticated_get_receipts_verified": False,
                  "binance_called": False, "business_db_write": False,
                  "final_snapshot_live_admissible": False,
                  "production_authorized": False, "source_verification": verification}
        manifests = [directory.write_once(run_dir, "exchange-pages.json", surfaces),
                     directory.write_once(run_dir, "local-state.json", local),
                     directory.write_once(run_dir, "reconciliation.json", result)]
        return {"status": result["status"], "run_dir": run_dir, "files": manifests,
                "source_verification": verification, "fixture_only": True,
                "production_authorized": False}
    except Exception:
        try:
            database.connection.close()
        except Exception:
            pass
        raise
