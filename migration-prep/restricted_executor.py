"""Non-privileged restricted-executor candidate for later root integration."""
from __future__ import print_function

import json
import os
import sqlite3
import time

from gate_common import GateError, bounded_call, canonical_bytes, require, sha256_value


ALLOWED_HOSTS = frozenset(("iZ6wee8q9z4t03hvqumwfhZ", "iZmj7a5kwr75qc1tul4kf9Z"))
ALLOWED_ACTIONS = frozenset(("READONLY_INSPECT", "RUNNER_RETIRE", "YIBI_RETIRE",
                             "WRITER_FENCE", "KOREA_DEPLOY", "KOREA_LOCK_WRITER"))


class TransactionLedger(object):
    def __init__(self, path):
        self.path = path
        self.connection = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS transactions ("
                                "tx_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, "
                                "nonce_sha256 TEXT NOT NULL UNIQUE, "
                                "state TEXT NOT NULL, intent_json TEXT NOT NULL, "
                                "result_json TEXT, updated_at INTEGER NOT NULL)")

    def intent(self, tx_id, request):
        digest, payload = sha256_value(request), canonical_bytes(request).decode("ascii")
        self.connection.execute("BEGIN IMMEDIATE")
        row = self.connection.execute("SELECT request_sha256,state FROM transactions WHERE tx_id=?",
                                      (tx_id,)).fetchone()
        if row:
            self.connection.rollback()
            require(row[0] == digest, "EXECUTOR_TRANSACTION_CONFLICT")
            raise GateError("EXECUTOR_NO_BLIND_RETRY_EXISTING_STATE:" + row[1])
        try:
            self.connection.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?,?)",
                                    (tx_id, digest, request["one_time_nonce_sha256"],
                                     "INTENT", payload, None, int(time.time())))
        except sqlite3.IntegrityError:
            self.connection.rollback()
            raise GateError("EXECUTOR_ONE_TIME_NONCE_REPLAY")
        self.connection.commit()
        return digest

    def finish(self, tx_id, state, result):
        require(state in ("SUCCEEDED", "FAILED", "UNKNOWN"), "EXECUTOR_RESULT_STATE_INVALID")
        self.connection.execute("BEGIN IMMEDIATE")
        row = self.connection.execute("SELECT state FROM transactions WHERE tx_id=?", (tx_id,)).fetchone()
        require(row and row[0] == "INTENT", "EXECUTOR_INTENT_STATE_REQUIRED")
        self.connection.execute("UPDATE transactions SET state=?,result_json=?,updated_at=? WHERE tx_id=?",
                                (state, canonical_bytes(result).decode("ascii"), int(time.time()), tx_id))
        self.connection.commit()

    def read(self, tx_id):
        row = self.connection.execute("SELECT request_sha256,state,intent_json,result_json FROM transactions WHERE tx_id=?",
                                      (tx_id,)).fetchone()
        return None if not row else {"request_sha256": row[0], "state": row[1],
                                     "intent": json.loads(row[2]),
                                     "result": json.loads(row[3]) if row[3] else None}


def validate_policy(policy):
    required = ("schema_version", "candidate_sha256", "expires_at_epoch", "hosts",
                "one_time_authority_id", "authorized_request_sha256")
    require(isinstance(policy, dict) and set(policy) == set(required), "EXECUTOR_POLICY_FIELDS_INVALID")
    require(policy["schema_version"] == 1, "EXECUTOR_POLICY_SCHEMA_INVALID")
    require(isinstance(policy["candidate_sha256"], str) and len(policy["candidate_sha256"]) == 64,
            "EXECUTOR_VERSION_HASH_INVALID")
    require(type(policy["expires_at_epoch"]) is int, "EXECUTOR_EXPIRY_INVALID")
    require(isinstance(policy["one_time_authority_id"], str) and policy["one_time_authority_id"],
            "EXECUTOR_AUTHORITY_ID_REQUIRED")
    require(isinstance(policy["authorized_request_sha256"], str) and
            len(policy["authorized_request_sha256"]) == 64,
            "EXECUTOR_AUTHORIZED_REQUEST_HASH_INVALID")
    require(isinstance(policy["hosts"], dict) and set(policy["hosts"]).issubset(ALLOWED_HOSTS),
            "EXECUTOR_HOSTS_INVALID")
    for host, value in policy["hosts"].items():
        require(isinstance(value, dict) and set(value) == set(("paths", "units", "actions")),
                "EXECUTOR_HOST_POLICY_INVALID")
        require(all(isinstance(path, str) and path.startswith("/") and ".." not in path
                    for path in value["paths"]), "EXECUTOR_PATH_INVALID")
        require(all(isinstance(unit, str) and unit.endswith((".service", ".timer"))
                    for unit in value["units"]), "EXECUTOR_UNIT_INVALID")
        require(set(value["actions"]).issubset(ALLOWED_ACTIONS), "EXECUTOR_ACTION_INVALID")
    return True


def execute_candidate(request, policy, ledger_path, runner, now_epoch=None):
    """Execute an injected test runner only; this module owns no sudo/root transport."""
    validate_policy(policy)
    require(callable(runner), "EXECUTOR_INJECTED_RUNNER_REQUIRED")
    required = ("tx_id", "host", "action", "paths", "units", "candidate_sha256",
                "authority_id", "one_time_nonce_sha256", "timeout_seconds")
    require(isinstance(request, dict) and set(request) == set(required), "EXECUTOR_REQUEST_FIELDS_INVALID")
    current = int(time.time()) if now_epoch is None else now_epoch
    require(type(current) is int and current < policy["expires_at_epoch"], "EXECUTOR_AUTHORIZATION_EXPIRED")
    require(request["candidate_sha256"] == policy["candidate_sha256"], "EXECUTOR_VERSION_MISMATCH")
    require(request["authority_id"] == policy["one_time_authority_id"], "EXECUTOR_AUTHORITY_MISMATCH")
    require(isinstance(request["one_time_nonce_sha256"], str) and len(request["one_time_nonce_sha256"]) == 64,
            "EXECUTOR_NONCE_INVALID")
    require(sha256_value(request) == policy["authorized_request_sha256"],
            "EXECUTOR_REQUEST_NOT_BOUND_TO_AUTHORIZATION")
    host = request["host"]
    require(host in policy["hosts"], "EXECUTOR_HOST_NOT_ALLOWLISTED")
    allowed = policy["hosts"][host]
    require(request["action"] in allowed["actions"], "EXECUTOR_ACTION_NOT_ALLOWLISTED")
    require(set(request["paths"]).issubset(set(allowed["paths"])), "EXECUTOR_PATH_NOT_ALLOWLISTED")
    require(set(request["units"]).issubset(set(allowed["units"])), "EXECUTOR_UNIT_NOT_ALLOWLISTED")
    require(type(request["timeout_seconds"]) is int and 0 < request["timeout_seconds"] <= 300,
            "EXECUTOR_TIMEOUT_INVALID")
    ledger = TransactionLedger(ledger_path)
    ledger.intent(request["tx_id"], request)
    try:
        value = bounded_call(lambda: runner(request), request["timeout_seconds"])
        require(isinstance(value, dict), "EXECUTOR_RESULT_INVALID")
        if value.get("partial_success") is True or value.get("outcome_unknown") is True:
            result = {"status": "UNKNOWN", "reason": "PARTIAL_OR_UNKNOWN_SIDE_EFFECTS",
                      "blind_retry_allowed": False, "inspection_required": True}
            ledger.finish(request["tx_id"], "UNKNOWN", result)
            return result
        result = {"status": "SUCCEEDED", "result": value, "production_authorized": False}
        ledger.finish(request["tx_id"], "SUCCEEDED", result)
        return result
    except BaseException as error:
        result = {"status": "UNKNOWN", "reason": repr(error), "blind_retry_allowed": False,
                  "inspection_required": True, "production_authorized": False}
        ledger.finish(request["tx_id"], "UNKNOWN", result)
        return result


def cgroup_candidate_spec(tx_id):
    """Return a future systemd-run confinement spec; never invokes systemd."""
    require(isinstance(tx_id, str) and tx_id and all(c.isalnum() or c in "-_" for c in tx_id),
            "EXECUTOR_TRANSACTION_ID_INVALID")
    return {"unit": "xuanjun-migration-{0}.service".format(tx_id), "properties": [
        "Type=oneshot", "DynamicUser=yes", "PrivateTmp=yes", "NoNewPrivileges=yes",
        "ProtectSystem=strict", "ProtectHome=yes", "PrivateDevices=yes",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", "KillMode=control-group",
        "TimeoutStartSec=300s"], "invoked": False, "root_capability": False}
