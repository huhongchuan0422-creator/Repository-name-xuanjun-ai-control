"""Production-DB read-only / fixture-exchange reconciliation adapter candidate.

The adapter deliberately separates three capabilities:

* the production SQLite database is opened with ``mode=ro&immutable=1``;
* exchange pages arrive through an injected GET-only transport (fixtures in this batch);
* output is created only below a dedicated evidence root.

It contains no HTTP client, credential loader, scheduler, freeze action, or database
write path.  Supplying real exchange transport is a later Release-Gate integration.
"""
from __future__ import print_function

import hashlib
import json
import os
import sqlite3
import stat
import tempfile

from gate_common import GateError, canonical_bytes, require, sha256_value
from final_snapshot import REQUIRED_SURFACES, RECONCILED_STATE_CLASSES, SIDE_CAR_CLASSES


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
MAX_PAGE_COUNT = 1000
EVIDENCE_FILES = ("exchange-pages.json", "local-state.json", "reconciliation.json")
LOCAL_COMPARE_SURFACES = ("account", "balances", "position_mode") + tuple(RECONCILED_STATE_CLASSES)

# Exact production tables used to derive the read-only local comparison surface.
# Empty tables remain valid empty state; missing tables fail closed.
TABLE_SPECS = {
    "account": ("account_snapshots", ("id", "snapshot_id", "account_id", "created_time", "payload_json")),
    "balances": ("account_snapshots", ("id", "snapshot_id", "account_id", "created_time", "payload_json")),
    "position_mode": ("account_capabilities", ("id", "account_id", "environment", "position_mode", "status", "verified_time")),
    "positions": ("position_snapshots", ("id", "snapshot_id", "account_id", "symbol", "side", "quantity", "created_time", "payload_json")),
    "open_orders": ("order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "order_id", "status", "created_time", "payload_json")),
    "algo_orders": ("order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "order_id", "status", "created_time", "payload_json")),
    "protective_orders": ("order_snapshots", ("id", "snapshot_id", "account_id", "symbol", "order_id", "status", "created_time", "payload_json")),
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


class ReadOnlyBusinessDatabase(object):
    def __init__(self, path):
        require(os.path.isfile(path) and not os.path.islink(path), "G4_DB_REGULAR_FILE_REQUIRED")
        self.path = _real(path)
        self.before = self.identity()
        uri = "file:{0}?mode=ro&immutable=1".format(self.path)
        self.connection = sqlite3.connect(uri, uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only=ON")

    def identity(self):
        value = os.stat(self.path)
        digest = hashlib.sha256()
        with open(self.path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return {"path": self.path, "size": value.st_size,
                "mtime_ns": int(value.st_mtime * 1000000000), "sha256": digest.hexdigest()}

    def _tables(self):
        return set(row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))

    def rows(self, logical_name):
        require(logical_name in TABLE_SPECS, "G4_DB_LOGICAL_TABLE_UNKNOWN")
        table, columns = TABLE_SPECS[logical_name]
        require(table in self._tables(), "G4_DB_TABLE_MISSING:" + table)
        actual = set(row[1] for row in self.connection.execute("PRAGMA table_info({0})".format(table)))
        require(set(columns).issubset(actual), "G4_DB_COLUMNS_MISSING:" + table)
        sql = "SELECT {0} FROM {1} ORDER BY id".format(
            ",".join('"{0}"'.format(column) for column in columns), table)
        return [dict(row) for row in self.connection.execute(sql)]

    @staticmethod
    def _payload_rows(rows):
        if not rows:
            return []
        newest = max(rows, key=lambda row: (str(row.get("created_time") or ""), row["id"]))
        selected = [row for row in rows if row.get("snapshot_id") == newest.get("snapshot_id")]
        values = []
        for row in selected:
            raw = row.get("payload_json")
            require(isinstance(raw, str), "G4_DB_PAYLOAD_REQUIRED")
            try:
                value = json.loads(raw)
            except (TypeError, ValueError):
                raise GateError("G4_DB_PAYLOAD_INVALID")
            require(isinstance(value, dict), "G4_DB_PAYLOAD_OBJECT_REQUIRED")
            values.append(value)
        return values

    def exchange_rows(self, logical_name):
        if logical_name == "position_mode":
            rows = self.rows(logical_name)
            if not rows:
                return {}
            latest = max(rows, key=lambda row: (str(row.get("verified_time") or ""), row["id"]))
            mode = str(latest.get("position_mode") or "").upper()
            require(mode in ("HEDGE", "ONE_WAY", "ONEWAY"), "G4_POSITION_MODE_UNKNOWN")
            return {"dualSidePosition": mode == "HEDGE"}
        values = self._payload_rows(self.rows(logical_name))
        if logical_name in ("account", "balances"):
            if not values:
                return {} if logical_name == "account" else []
            require(len(values) == 1, "G4_ACCOUNT_SNAPSHOT_AMBIGUOUS")
            raw = values[0].get("raw")
            require(isinstance(raw, dict), "G4_ACCOUNT_RAW_REQUIRED")
            if logical_name == "balances":
                assets = raw.get("assets")
                require(isinstance(assets, list), "G4_ACCOUNT_ASSETS_REQUIRED")
                return assets
            return raw
        if logical_name == "open_orders":
            return [row for row in values if row.get("status") in ("NEW", "PARTIALLY_FILLED")]
        if logical_name in ("algo_orders", "protective_orders"):
            algo = [row for row in values if (row.get("algoId") is not None or
                    row.get("strategyId") is not None or row.get("type") in
                    ("STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET"))]
            if logical_name == "protective_orders":
                return [row for row in algo if row.get("reduceOnly") is True or
                        row.get("closePosition") is True]
            return algo
        return values

    def snapshot(self):
        exchange = {name: self.exchange_rows(name) for name in LOCAL_COMPARE_SURFACES}
        sidecars = {name: self.rows(name) for name in SIDE_CAR_CLASSES}
        unknown = [row for row in sidecars["unknown_execution"]
                   if row.get("status") in ("UNKNOWN", "TIMEOUT", "PARTIAL") or row.get("error_type")]
        inflight = [row for row in sidecars["inflight_requests"]
                    if row.get("status") in ("PENDING", "STARTED", "INFLIGHT", "UNKNOWN")]
        conflicts = [row for row in self.rows("ownership_conflicts")
                     if row.get("state") not in ("RESOLVED", "CLOSED") and
                     str(row.get("new_positions_locked")) in ("1", "true", "True")]
        return {"expected_symbols": list(SYMBOLS), "exchange_mirror": exchange,
                "db_external_state": dict((name, {"sha256": sha256_value(rows)})
                                          for name, rows in sidecars.items()),
                "unknown_orders": unknown, "inflight_requests": inflight,
                "ownership_conflicts": conflicts,
                "sidecar_counts": dict((name, len(rows)) for name, rows in sidecars.items()),
                "database_identity_before": self.before}

    def close_and_verify_unchanged(self):
        self.connection.close()
        after = self.identity()
        require(after == self.before, "G4_PRODUCTION_DB_CHANGED_DURING_READ")
        return after


class FixtureGetOnlyPager(object):
    """Fixture transport with production-equivalent pagination invariants."""
    def __init__(self, fixture, page_limit=100):
        require(isinstance(fixture, dict), "G4_FIXTURE_REQUIRED")
        require(type(page_limit) is int and 0 < page_limit <= 1000, "G4_PAGE_LIMIT_INVALID")
        self.fixture, self.page_limit, self.calls = fixture, page_limit, []

    def collect(self, surface, symbols):
        require(surface in REQUIRED_SURFACES, "G4_SURFACE_NOT_ALLOWLISTED")
        require(set(symbols) == set(SYMBOLS), "G4_SYMBOL_SET_INVALID")
        pages = self.fixture.get(surface)
        require(isinstance(pages, list) and pages, "G4_FIXTURE_SURFACE_MISSING:" + surface)
        require(len(pages) <= MAX_PAGE_COUNT, "G4_PAGE_COUNT_EXCEEDED:" + surface)
        items, expected_cursor, covered = [], None, set()
        observed = None
        for index, page in enumerate(pages):
            require(isinstance(page, dict), "G4_PAGE_INVALID:" + surface)
            require(set(page) == set(("cursor", "next_cursor", "items", "observed_at_ms", "symbols")),
                    "G4_PAGE_FIELDS_INVALID:" + surface)
            require(page["cursor"] == expected_cursor, "G4_PAGE_CURSOR_GAP:" + surface)
            require(isinstance(page["items"], (list, dict)), "G4_PAGE_ITEMS_INVALID:" + surface)
            require(type(page["observed_at_ms"]) is int, "G4_PAGE_TIME_INVALID:" + surface)
            require(isinstance(page["symbols"], list), "G4_PAGE_SYMBOLS_INVALID:" + surface)
            if isinstance(page["items"], list):
                require(len(page["items"]) <= self.page_limit, "G4_PAGE_LIMIT_EXCEEDED:" + surface)
                items.extend(page["items"])
            else:
                require(len(pages) == 1, "G4_OBJECT_SURFACE_MULTIPAGE:" + surface)
                items = page["items"]
            covered.update(page["symbols"])
            observed = page["observed_at_ms"] if observed is None else max(observed, page["observed_at_ms"])
            expected_cursor = page["next_cursor"]
            self.calls.append({"method": "GET", "surface": surface, "page": index,
                               "cursor_sha256": sha256_value(page["cursor"])})
        require(expected_cursor is None, "G4_PAGINATION_NOT_TERMINATED:" + surface)
        if surface in RECONCILED_STATE_CLASSES:
            require(covered == set(SYMBOLS), "G4_SYMBOL_COVERAGE_INCOMPLETE:" + surface)
        return {"observed_at_ms": observed, "data": items, "pagination_complete": True,
                "symbols_covered": sorted(covered)}


class EvidenceDirectory(object):
    def __init__(self, root, business_db):
        require(os.path.isdir(root) and not os.path.islink(root), "G4_EVIDENCE_ROOT_REQUIRED")
        require(not _is_below(root, os.path.dirname(business_db)), "G4_EVIDENCE_MUST_BE_SEPARATE")
        self.root = _real(root)

    def create_run(self, run_id):
        require(isinstance(run_id, str) and run_id and "/" not in run_id and ".." not in run_id,
                "G4_RUN_ID_INVALID")
        path = os.path.join(self.root, run_id)
        os.mkdir(path, 0o700)
        require(stat.S_IMODE(os.stat(path).st_mode) == 0o700, "G4_EVIDENCE_MODE_INVALID")
        return path

    @staticmethod
    def write_once(run_dir, name, value):
        require(name in EVIDENCE_FILES, "G4_EVIDENCE_NAME_NOT_ALLOWLISTED")
        target = os.path.join(run_dir, name)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
            stream.flush(); os.fsync(stream.fileno())
        digest = hashlib.sha256()
        with open(target, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return {"name": name, "sha256": digest.hexdigest(), "size": os.path.getsize(target)}


def collect_fixture_evidence(database_path, evidence_root, run_id, fixture):
    """Exercise the real DB reader against an injected, network-free fixture transport."""
    database = ReadOnlyBusinessDatabase(database_path)
    directory = EvidenceDirectory(evidence_root, database_path)
    run_dir = directory.create_run(run_id)
    try:
        local = database.snapshot()
        pager = FixtureGetOnlyPager(fixture)
        surfaces = dict((surface, pager.collect(surface, SYMBOLS)) for surface in REQUIRED_SURFACES)
        server = surfaces["server_time"]["data"]
        require(isinstance(server, dict) and type(server.get("serverTime")) is int,
                "G4_SERVER_TIME_INVALID")
        blockers = []
        for name in LOCAL_COMPARE_SURFACES:
            if sha256_value(local["exchange_mirror"][name]) != sha256_value(surfaces[name]["data"]):
                blockers.append("STATE_MISMATCH:" + name)
        exchange_ms = server["serverTime"]
        for name, value in surfaces.items():
            if abs(value["observed_at_ms"] - exchange_ms) > 10000:
                blockers.append("SURFACE_SKEW:" + name)
        require(len(pager.calls) >= len(REQUIRED_SURFACES) and
                all(call["method"] == "GET" for call in pager.calls),
                "G4_GET_EVIDENCE_INCOMPLETE")
        if local["unknown_orders"]: blockers.append("UNKNOWN_EXECUTION")
        if local["inflight_requests"]: blockers.append("INFLIGHT_REQUESTS")
        result = {"schema_version": 1, "adapter_mode": "FIXTURE_NO_NETWORK",
                  "database_open_mode": "READ_ONLY_IMMUTABLE", "symbols": list(SYMBOLS),
                  "surfaces": surfaces, "calls": pager.calls, "blockers": blockers,
                  "status": "PASS_CANDIDATE" if not blockers else "HOLD",
                  "binance_called": False, "business_db_write": False,
                  "production_authorized": False}
        manifests = [directory.write_once(run_dir, "exchange-pages.json", surfaces),
                     directory.write_once(run_dir, "local-state.json", local),
                     directory.write_once(run_dir, "reconciliation.json", result)]
        unchanged = database.close_and_verify_unchanged()
        return {"status": result["status"], "run_dir": run_dir, "files": manifests,
                "database_identity_after": unchanged, "production_authorized": False}
    except Exception:
        database.connection.close()
        raise
