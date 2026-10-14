"""G4 candidate: enforced GET-only reconciliation and frozen checkpoint proof."""
from __future__ import print_function

import hashlib
import os
import time

from gate_common import require, sha256_value


SURFACE_REQUESTS = (
    ("server_time", "/fapi/v1/time"),
    ("account", "/fapi/v3/account"),
    ("balances", "/fapi/v3/balance"),
    ("position_mode", "/fapi/v1/positionSide/dual"),
    ("positions", "/fapi/v3/positionRisk"),
    ("open_orders", "/fapi/v1/openOrders"),
    ("algo_orders", "/fapi/v1/openAlgoOrders"),
    ("protective_orders", "/fapi/v1/openAlgoOrders"),
    ("recent_orders", "/fapi/v1/allOrders"),
    ("trades", "/fapi/v1/userTrades")
)
REQUIRED_SURFACES = tuple(name for name, unused in SURFACE_REQUESTS)
RECONCILED_STATE_CLASSES = (
    "positions", "open_orders", "algo_orders", "protective_orders",
    "recent_orders", "trades"
)
SYMBOL_SCOPED_SURFACES = frozenset(RECONCILED_STATE_CLASSES)

SIDE_CAR_CLASSES = (
    "pending_queue", "recovery_queue", "unknown_execution", "inflight_requests",
    "guard_state", "watch_state", "ownership_ledger", "scheduler_state"
)


class GetOnlyTransport(object):
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = []

    def request(self, method, path, params=None):
        require(method == "GET", "G4_NON_GET_FORBIDDEN")
        require(isinstance(path, str) and path.startswith("/"), "G4_PATH_INVALID")
        parameters = params or {}
        require(isinstance(parameters, dict), "G4_PARAMS_INVALID")
        response = self.delegate(method, path, parameters)
        self.calls.append({
            "method": method, "path": path,
            "params_sha256": sha256_value(parameters),
            "response_sha256": sha256_value(response)
        })
        return response


def file_identity(path):
    require(os.path.isfile(path) and not os.path.islink(path), "G4_FILE_REQUIRED")
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    stat_result = os.stat(path)
    return {"logical_name": os.path.basename(path), "size": stat_result.st_size,
            "mtime_ns": int(stat_result.st_mtime * 1000000000), "sha256": digest.hexdigest()}


def _valid_sha256(value):
    return (isinstance(value, str) and len(value) == 64 and
            all(character in "0123456789abcdef" for character in value))


def build_exchange_reconciliation(transport, local_state, now_ms=None,
                                  max_skew_ms=10000, max_capture_ms=30000,
                                  clock_ms=None):
    """Collect every surface through GET-only transport and compare state."""
    require(isinstance(transport, GetOnlyTransport), "G4_GET_ONLY_TRANSPORT_REQUIRED")
    require(isinstance(local_state, dict), "G4_LOCAL_STATE_REQUIRED")
    for key in ("unknown_orders", "inflight_requests", "ownership_conflicts",
                "db_external_state", "expected_symbols", "exchange_mirror"):
        require(key in local_state, "G4_LOCAL_MISSING:" + key)
    expected_symbols = local_state["expected_symbols"]
    require(isinstance(expected_symbols, list) and expected_symbols and
            len(expected_symbols) == len(set(expected_symbols)), "G4_EXPECTED_SYMBOLS_INVALID")
    require(set(local_state["exchange_mirror"]) == set(RECONCILED_STATE_CLASSES),
            "G4_LOCAL_MIRROR_SET_INCOMPLETE")
    require(set(local_state["db_external_state"]) == set(SIDE_CAR_CLASSES),
            "G4_DB_EXTERNAL_STATE_INCOMPLETE")

    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
    require(type(current_ms) is int and current_ms > 0, "G4_NOW_INVALID")
    clock = clock_ms or (lambda: int(time.time() * 1000))
    started_ms = current_ms if now_ms is not None and clock_ms is None else clock()
    surfaces = {}
    for name, path in SURFACE_REQUESTS:
        value = transport.request("GET", path, {"surface": name})
        require(isinstance(value, dict), "G4_SURFACE_INVALID:" + name)
        for field in ("observed_at_ms", "data", "pagination_complete", "symbols_covered"):
            require(field in value, "G4_SURFACE_FIELD_MISSING:" + name + ":" + field)
        require(type(value["observed_at_ms"]) is int, "G4_SURFACE_TIME_INVALID:" + name)
        require(type(value["pagination_complete"]) is bool and value["pagination_complete"],
                "G4_PAGINATION_INCOMPLETE:" + name)
        require(isinstance(value["symbols_covered"], list), "G4_SYMBOL_COVERAGE_INVALID:" + name)
        if name in SYMBOL_SCOPED_SURFACES:
            require(set(value["symbols_covered"]) == set(expected_symbols),
                    "G4_SYMBOL_COVERAGE_INCOMPLETE:" + name)
        surfaces[name] = value
    finished_ms = current_ms if now_ms is not None and clock_ms is None else clock()
    require(type(started_ms) is int and type(finished_ms) is int and
            started_ms <= finished_ms <= started_ms + max_capture_ms,
            "G4_CAPTURE_WINDOW_EXCEEDED")
    require(len(transport.calls) == len(SURFACE_REQUESTS) and
            all(call["method"] == "GET" for call in transport.calls),
            "G4_GET_CALL_EVIDENCE_INCOMPLETE")

    server_data = surfaces["server_time"]["data"]
    require(isinstance(server_data, dict) and type(server_data.get("serverTime")) is int,
            "G4_SERVER_TIME_INVALID")
    exchange_ms = server_data["serverTime"]
    blockers = []
    if abs(current_ms - exchange_ms) > max_skew_ms:
        blockers.append("STALE_EXCHANGE_SERVER_TIME")
    stale = sorted(name for name, value in surfaces.items()
                   if abs(exchange_ms - value["observed_at_ms"]) > max_skew_ms)
    if stale:
        blockers.append("STALE_SURFACES:" + ",".join(stale))
    if local_state["unknown_orders"]:
        blockers.append("UNKNOWN_ORDERS")
    if local_state["inflight_requests"]:
        blockers.append("INFLIGHT_REQUESTS")
    if local_state["ownership_conflicts"]:
        blockers.append("OWNERSHIP_CONFLICTS")
    for name in RECONCILED_STATE_CLASSES:
        if sha256_value(local_state["exchange_mirror"][name]) != sha256_value(surfaces[name]["data"]):
            blockers.append("STATE_MISMATCH:" + name)
    snapshot = {
        "schema_version": 2,
        "request_method_policy": "ENFORCED_GET_ONLY",
        "watermark": {"local_started_ms": started_ms, "request_now_ms": current_ms,
                      "exchange_server_ms": exchange_ms, "local_finished_ms": finished_ms,
                      "max_skew_ms": max_skew_ms, "max_capture_ms": max_capture_ms},
        "call_evidence": list(transport.calls), "surfaces": surfaces,
        "local_state": local_state, "blockers": blockers,
        "status": "PASS" if not blockers else "HOLD"
    }
    snapshot["content_sha256"] = sha256_value(snapshot)
    return snapshot


def _validate_checkpoint_semantics(checkpoint):
    require(checkpoint.get("schema_version") == 2, "G4_CHECKPOINT_SCHEMA_INVALID")
    require(checkpoint.get("status") == "FINAL_CHECKPOINT_CANDIDATE",
            "G4_CHECKPOINT_STATUS_INVALID")
    maintenance = checkpoint.get("maintenance")
    require(isinstance(maintenance, dict), "G4_MAINTENANCE_REQUIRED")
    for key in ("freeze_started_ms", "freeze_deadline_ms", "max_freeze_ms",
                "checkpoint_captured_ms", "new_entries_frozen", "inflight_drained",
                "expected_authoritative_files"):
        require(key in maintenance, "G4_MAINTENANCE_MISSING:" + key)
    start, deadline = maintenance["freeze_started_ms"], maintenance["freeze_deadline_ms"]
    captured, maximum = maintenance["checkpoint_captured_ms"], maintenance["max_freeze_ms"]
    require(all(type(value) is int for value in (start, deadline, captured, maximum)),
            "G4_FREEZE_TIME_INVALID")
    require(start <= captured <= deadline and deadline - start <= maximum,
            "G4_FREEZE_WINDOW_INVALID")
    require(maintenance["new_entries_frozen"] is True and maintenance["inflight_drained"] is True,
            "G4_MAINTENANCE_NOT_QUIESCENT")
    identities = checkpoint.get("authoritative_files")
    require(isinstance(identities, list) and identities, "G4_DATABASE_FILES_REQUIRED")
    require(set(item["logical_name"] for item in identities) ==
            set(maintenance["expected_authoritative_files"]), "G4_AUTHORITATIVE_FILE_SET_MISMATCH")
    for item in identities:
        require(_valid_sha256(item.get("sha256")) and type(item.get("size")) is int,
                "G4_AUTHORITATIVE_FILE_IDENTITY_INVALID")
    sidecars = checkpoint.get("sidecars")
    require(isinstance(sidecars, dict) and set(sidecars) == set(SIDE_CAR_CLASSES),
            "G4_SIDECAR_SET_INCOMPLETE")
    for name, receipt in sidecars.items():
        require(isinstance(receipt, dict) and set(receipt) ==
                set(("content_sha256", "captured_at_ms", "frozen")),
                "G4_SIDECAR_RECEIPT_INVALID:" + name)
        require(_valid_sha256(receipt["content_sha256"]), "G4_SIDECAR_HASH_INVALID:" + name)
        require(type(receipt["captured_at_ms"]) is int and receipt["frozen"] is True and
                start <= receipt["captured_at_ms"] <= captured,
                "G4_SIDECAR_OUTSIDE_FREEZE:" + name)
    watermark = checkpoint.get("exchange_watermark")
    require(isinstance(watermark, dict) and
            start <= watermark.get("local_started_ms", -1) <=
            watermark.get("local_finished_ms", -1) <= captured,
            "G4_RECONCILIATION_OUTSIDE_FREEZE")
    return True


def build_final_checkpoint(exchange_snapshot, authoritative_files, sidecars, maintenance,
                           captured_at_ms=None):
    require(exchange_snapshot.get("status") == "PASS", "G4_RECONCILIATION_NOT_PASS")
    require(isinstance(authoritative_files, list) and authoritative_files,
            "G4_DATABASE_FILES_REQUIRED")
    require(isinstance(sidecars, dict), "G4_SIDECARS_REQUIRED")
    require(isinstance(maintenance, dict), "G4_MAINTENANCE_REQUIRED")
    value = dict(maintenance)
    value["checkpoint_captured_ms"] = (int(time.time() * 1000)
                                        if captured_at_ms is None else captured_at_ms)
    checkpoint = {
        "schema_version": 2,
        "exchange_snapshot_sha256": exchange_snapshot["content_sha256"],
        "exchange_watermark": exchange_snapshot["watermark"],
        "authoritative_files": [file_identity(path) for path in authoritative_files],
        "sidecars": sidecars, "maintenance": value,
        "status": "FINAL_CHECKPOINT_CANDIDATE"
    }
    _validate_checkpoint_semantics(checkpoint)
    checkpoint["checkpoint_sha256"] = sha256_value(checkpoint)
    return checkpoint


def verify_checkpoint(checkpoint):
    claimed = checkpoint.get("checkpoint_sha256")
    unsigned = dict(checkpoint)
    unsigned.pop("checkpoint_sha256", None)
    require(claimed == sha256_value(unsigned), "G4_CHECKPOINT_HASH_MISMATCH")
    return _validate_checkpoint_semantics(checkpoint)
