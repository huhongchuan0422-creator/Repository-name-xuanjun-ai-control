"""Read-only canonical task handoff reconciliation for Issue #19.

Consumes authenticated *projections* from the existing canonical ledger.
Never grants writer rights, mutates a lease or creates a second task queue.
Python 3.6-compatible standard library. No network or model API usage.
"""
from __future__ import unicode_literals
import hashlib
import json
import re

class HandoffHold(ValueError):
    pass

_SHA = re.compile(r"^[a-f0-9]{64}$")
_COMMIT = re.compile(r"^[a-f0-9]{40}$")
_ENTRIES = {"WORK", "CHATGPT", "DOTS"}
_STATES = {"READY", "RUNNING", "STOPPED", "DONE", "HOLD", "UNKNOWN"}
_REQUIRED = {"task_id", "spec_sha256", "checkpoint_sha256", "target_repository",
             "target_base_sha", "entry", "attempt_id", "state", "writer_stopped",
             "lease_expired", "effects_reconciled", "next_owner_ack",
             "last_real_progress_at", "progress_deadline_at", "receipt_id"}

def canonical_bytes(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def _check_id(x):
    if not isinstance(x, str) or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,199}$", x):
        raise HandoffHold("INVALID_ID")

def project(record, now_epoch):
    """Returns a deterministic observation, never an authorization token."""
    if not isinstance(record, dict) or set(record) != _REQUIRED:
        raise HandoffHold("INVALID_PROJECTION_SCHEMA")
    if type(now_epoch) is not int or now_epoch < 0:
        raise HandoffHold("INVALID_CLOCK")
    for k in ("task_id", "target_repository", "attempt_id", "receipt_id"):
        _check_id(record[k])
    for k in ("spec_sha256", "checkpoint_sha256"):
        if not isinstance(record[k], str) or not _SHA.fullmatch(record[k]):
            raise HandoffHold("INVALID_HASH")
    if not isinstance(record["target_base_sha"], str) or not _COMMIT.fullmatch(record["target_base_sha"]):
        raise HandoffHold("INVALID_COMMIT")
    if record["entry"] not in _ENTRIES or record["state"] not in _STATES:
        raise HandoffHold("INVALID_ENTRY_OR_STATE")
    for k in ("writer_stopped", "lease_expired", "effects_reconciled", "next_owner_ack"):
        if record[k] not in (True, False, None):
            raise HandoffHold("INVALID_EVIDENCE_TYPE")
    for k in ("last_real_progress_at", "progress_deadline_at"):
        if record[k] is not None and (type(record[k]) is not int or record[k] < 0):
            raise HandoffHold("INVALID_PROGRESS_TIME")
    blockers = []
    if record["state"] in ("UNKNOWN", "HOLD"):
        blockers.append("CANONICAL_STATE_NOT_READY")
    if record["writer_stopped"] is not True:
        blockers.append("OLD_WRITER_STOP_NOT_PROVEN")
    if record["lease_expired"] is not True:
        blockers.append("LEASE_FENCE_NOT_PROVEN")
    if record["effects_reconciled"] is not True:
        blockers.append("UNKNOWN_EFFECT_NOT_RECONCILED")
    if record["next_owner_ack"] is not True:
        blockers.append("NEW_OWNER_ACK_MISSING")
    deadline = record["progress_deadline_at"]
    last = record["last_real_progress_at"]
    if deadline is None or last is None:
        blockers.append("PROGRESS_DEADLINE_UNKNOWN")
    elif now_epoch > deadline:
        blockers.append("PROGRESS_OVERDUE")
    digest = hashlib.sha256(canonical_bytes(record)).hexdigest()
    return {"task_id": record["task_id"], "attempt_id": record["attempt_id"],
            "entry": record["entry"], "record_sha256": digest,
            "status": "OBSERVATION_ONLY", "candidate_handoff_ready": not blockers,
            "blockers": blockers, "writer_permission": "NOT_GRANTED",
            "side_effects": 0, "next_action": ("REQUEST_CANONICAL_ADMISSION" if not blockers else "HOLD_AND_ESCALATE")}

def observe_many(records, now_epoch):
    if not isinstance(records, list):
        raise HandoffHold("INVALID_COLLECTION")
    seen = set()
    rows = []
    for rec in records:
        row = project(rec, now_epoch)
        key = (row["task_id"], row["attempt_id"])
        if key in seen:
            raise HandoffHold("DUPLICATE_CANONICAL_ATTEMPT")
        seen.add(key)
        rows.append(row)
    return sorted(rows, key=lambda row: (row["task_id"], row["attempt_id"]))
