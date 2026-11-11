"""Exact independent approval plus private Owner-root pin; no self-issued permit."""
import time

from gate_common import require
from korea.phase_c.security import digest, strict_json

HOST = "iZmj7a5kwr75qc1tul4kf9Z"
INSTALL_ACTION = "PR99_PHASE_C_OFFLINE_CANDIDATE_INSTALL_V1"
MARKER = "PR99_PHASE_C_ROOT_APPROVAL_V1"


def verify_approval(pin, expected, now=None):
    require(isinstance(pin, dict) and set(pin) == {
        "approval_comment_id", "approval_body_sha256", "approval_body"}, "C_ROOT_PIN_FIELDS")
    require(type(pin["approval_comment_id"]) is int and pin["approval_comment_id"] > 0 and
            type(pin["approval_body"]) is str and 0 < len(pin["approval_body"].encode()) <= 100000 and
            digest(pin["approval_body"].encode()) == pin["approval_body_sha256"], "C_ROOT_PIN_BODY")
    begin, end = "<!-- " + MARKER + "\n", "\n" + MARKER + " -->"
    body = pin["approval_body"]
    require(body.count(begin) == 1 and body.count(end) == 1 and body.index(begin) < body.index(end),
            "C_ROOT_APPROVAL_MARKER")
    approval = strict_json(body.split(begin)[1].split(end)[0])
    fixed = dict(expected, schema_version=1, decision="APPROVED_WITH_EXACT_PRECONDITIONS",
                 host=HOST, max_attempts=1, service_start_allowed=False,
                 network_changes_allowed=False, credentials_allowed=False,
                 database_export_allowed=False, writer_allowed=False)
    require(set(approval) == set(fixed) | {"approval_comment_id", "issued_at", "expires_at"},
            "C_ROOT_APPROVAL_FIELDS")
    for key, value in fixed.items():
        require(type(approval[key]) is type(value) and approval[key] == value, "C_ROOT_APPROVAL_SCOPE:" + key)
    require(approval["approval_comment_id"] == pin["approval_comment_id"] and
            type(approval["approval_comment_id"]) is int, "C_ROOT_APPROVAL_ID")
    current = time.time() if now is None else now
    require(type(approval["issued_at"]) is int and type(approval["expires_at"]) is int and
            approval["issued_at"] <= current < approval["expires_at"] and
            0 < approval["expires_at"] - approval["issued_at"] <= 43200, "C_ROOT_APPROVAL_EXPIRED")
    require(approval["action"] == INSTALL_ACTION, "C_ROOT_ACTION_NOT_IMPLEMENTED")
    return approval
