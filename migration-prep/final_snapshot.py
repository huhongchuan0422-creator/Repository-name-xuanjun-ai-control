"""G4 candidate: GET-only exchange reconciliation and final checkpoint builder."""
from __future__ import print_function

import hashlib
import json
import os
import time

from gate_common import canonical_bytes, require, sha256_value


REQUIRED_SURFACES = (
    "server_time", "account", "balances", "position_mode", "positions",
    "open_orders", "algo_orders", "recent_orders", "trades"
)

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
        self.calls.append({"method": method, "path": path})
        return self.delegate(method, path, params or {})


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


def build_exchange_reconciliation(provider, local_state, now_ms=None, max_skew_ms=10000):
    require(isinstance(local_state, dict), "G4_LOCAL_STATE_REQUIRED")
    for key in ("unknown_orders", "inflight_requests", "ownership_conflicts", "db_external_state"):
        require(key in local_state, "G4_LOCAL_MISSING:" + key)
    started_ms = int(time.time() * 1000) if now_ms is None else now_ms
    surfaces = {}
    for name in REQUIRED_SURFACES:
        value = provider.read(name)
        require(isinstance(value, dict) and "observed_at_ms" in value and "data" in value,
                "G4_SURFACE_INVALID:" + name)
        surfaces[name] = value
    finished_ms = int(time.time() * 1000) if now_ms is None else now_ms
    exchange_ms = int(surfaces["server_time"]["data"]["serverTime"])
    stale = sorted(name for name, value in surfaces.items()
                   if abs(exchange_ms - int(value["observed_at_ms"])) > max_skew_ms)
    blockers = []
    if stale:
        blockers.append("STALE_SURFACES:" + ",".join(stale))
    if local_state["unknown_orders"]:
        blockers.append("UNKNOWN_ORDERS")
    if local_state["inflight_requests"]:
        blockers.append("INFLIGHT_REQUESTS")
    if local_state["ownership_conflicts"]:
        blockers.append("OWNERSHIP_CONFLICTS")
    if not isinstance(local_state["db_external_state"], dict) or not local_state["db_external_state"]:
        blockers.append("DB_EXTERNAL_STATE_MISSING")
    snapshot = {
        "schema_version": 1,
        "request_method_policy": "GET_ONLY",
        "watermark": {"local_started_ms": started_ms, "exchange_server_ms": exchange_ms,
                      "local_finished_ms": finished_ms, "max_skew_ms": max_skew_ms},
        "surfaces": surfaces,
        "local_state": local_state,
        "blockers": blockers,
        "status": "PASS" if not blockers else "HOLD"
    }
    snapshot["content_sha256"] = sha256_value(snapshot)
    return snapshot


def build_final_checkpoint(exchange_snapshot, authoritative_files, sidecars, maintenance):
    require(exchange_snapshot.get("status") == "PASS", "G4_RECONCILIATION_NOT_PASS")
    require(isinstance(authoritative_files, list) and authoritative_files, "G4_DATABASE_FILES_REQUIRED")
    require(isinstance(sidecars, dict), "G4_SIDECARS_REQUIRED")
    require(set(sidecars) == set(SIDE_CAR_CLASSES), "G4_SIDECAR_SET_INCOMPLETE")
    require(isinstance(maintenance, dict), "G4_MAINTENANCE_REQUIRED")
    for key in ("freeze_started_at", "freeze_deadline", "new_entries_frozen", "inflight_drained"):
        require(key in maintenance, "G4_MAINTENANCE_MISSING:" + key)
    require(maintenance["new_entries_frozen"] and maintenance["inflight_drained"], "G4_MAINTENANCE_NOT_QUIESCENT")
    identities = [file_identity(path) for path in authoritative_files]
    checkpoint = {
        "schema_version": 1,
        "exchange_snapshot_sha256": exchange_snapshot["content_sha256"],
        "authoritative_files": identities,
        "sidecars": sidecars,
        "maintenance": maintenance,
        "status": "FINAL_CHECKPOINT_CANDIDATE"
    }
    checkpoint["checkpoint_sha256"] = sha256_value(checkpoint)
    return checkpoint


def verify_checkpoint(checkpoint):
    claimed = checkpoint.get("checkpoint_sha256")
    unsigned = dict(checkpoint)
    unsigned.pop("checkpoint_sha256", None)
    require(claimed == sha256_value(unsigned), "G4_CHECKPOINT_HASH_MISMATCH")
    require(checkpoint.get("status") == "FINAL_CHECKPOINT_CANDIDATE", "G4_CHECKPOINT_STATUS_INVALID")
    return True
