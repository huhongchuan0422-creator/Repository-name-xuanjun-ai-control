"""Fail-closed helpers shared by Tokyo -> Korea migration gate candidates."""
from __future__ import print_function

import hashlib
import json
import multiprocessing
import os
import sqlite3
import time


class GateError(Exception):
    pass


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_value(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def require(condition, code):
    if not condition:
        raise GateError(code)


def require_exact_keys(value, required, optional=()):
    require(isinstance(value, dict), "OBJECT_REQUIRED")
    missing = sorted(set(required) - set(value))
    extra = sorted(set(value) - set(required) - set(optional))
    require(not missing, "MISSING_FIELDS:" + ",".join(missing))
    require(not extra, "UNEXPECTED_FIELDS:" + ",".join(extra))


def load_json(path):
    with open(path, "r") as stream:
        return json.load(stream)


class IdempotentLedger(object):
    """Transactional cross-process candidate ledger.

    SQLite supplies crash recovery, BEGIN IMMEDIATE serialization and a unique
    key constraint.  This ledger is not an external Writer authority.
    """

    def __init__(self, path):
        self.path = path

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "idempotency_key TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "recorded_at INTEGER NOT NULL)"
        )
        return connection

    def record(self, key, payload):
        require(isinstance(key, str) and key, "IDEMPOTENCY_KEY_REQUIRED")
        digest = sha256_value(payload)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT digest FROM events WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is not None:
                require(row[0] == digest, "IDEMPOTENCY_CONFLICT")
                connection.commit()
                return {"replayed": True, "digest": digest}
            connection.execute(
                "INSERT INTO events(idempotency_key,digest,recorded_at) VALUES(?,?,?)",
                (key, digest, int(time.time()))
            )
            connection.commit()
            return {"replayed": False, "digest": digest}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def validate_phase_history(phases, history, code_prefix):
    """Require a receipt-bound, successful, unique, continuous phase prefix."""
    require(isinstance(history, list), code_prefix + "_HISTORY_REQUIRED")
    require(len(history) <= len(phases), code_prefix + "_HISTORY_TOO_LONG")
    seen_execution_ids = set()
    for index, receipt in enumerate(history):
        require(isinstance(receipt, dict), code_prefix + "_RECEIPT_REQUIRED")
        require(set(receipt) == set(("phase", "status", "execution_id", "result_sha256")),
                code_prefix + "_RECEIPT_FIELDS_INVALID")
        require(receipt["phase"] == phases[index], code_prefix + "_HISTORY_NOT_CONTIGUOUS")
        require(receipt["status"] == "SUCCEEDED", code_prefix + "_PHASE_NOT_SUCCEEDED")
        require(isinstance(receipt["execution_id"], str) and receipt["execution_id"],
                code_prefix + "_EXECUTION_ID_REQUIRED")
        require(receipt["execution_id"] not in seen_execution_ids,
                code_prefix + "_EXECUTION_ID_REUSED")
        seen_execution_ids.add(receipt["execution_id"])
        digest = receipt["result_sha256"]
        require(isinstance(digest, str) and len(digest) == 64 and
                all(character in "0123456789abcdef" for character in digest),
                code_prefix + "_RESULT_DIGEST_INVALID")
    return tuple(receipt["phase"] for receipt in history)


def next_phase_action(phases, history, requested, code_prefix):
    require(requested in phases, code_prefix + "_PHASE_INVALID")
    completed = validate_phase_history(phases, history, code_prefix)
    if requested in completed:
        return "REPLAY_NOOP"
    require(len(completed) < len(phases) and requested == phases[len(completed)],
            code_prefix + "_PHASE_ORDER_VIOLATION")
    return "EXECUTE_ONCE"


def _call_worker(callable_, output):
    try:
        output.put(("ok", callable_()))
    except BaseException as error:
        output.put(("error", repr(error)))


def bounded_call(callable_, timeout_seconds):
    """Run an isolated callable with a real deadline.

    A timeout terminates the child and raises an explicit uncertain-side-effect
    error.  Callers must inspect/reconcile; this function never claims rollback.
    """
    require(timeout_seconds > 0, "TIMEOUT_REQUIRED")
    output = multiprocessing.Queue()
    process = multiprocessing.Process(target=_call_worker, args=(callable_, output))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise GateError("OPERATION_TIMEOUT_UNCERTAIN_SIDE_EFFECTS")
    require(process.exitcode == 0, "OPERATION_CHILD_FAILED")
    require(not output.empty(), "OPERATION_RESULT_MISSING")
    status, value = output.get()
    require(status == "ok", "OPERATION_CALLABLE_FAILED:" + str(value))
    return value
