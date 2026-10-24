"""Fail-closed helpers shared by Tokyo -> Korea migration gate candidates."""
from __future__ import print_function

import hashlib
import json
import multiprocessing
import os
import signal
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


def validate_phase_history(phases, history, code_prefix, result_loader=None,
                           authority_verifier=None):
    """Validate ordering and optionally bind receipts to durable results.

    Receipt shape and self-declared digests alone are only format evidence.  A
    caller that wants result binding must provide both an independently backed
    loader and an authority verifier.  Even the bound result is candidate
    evidence; this helper never grants production execution authority.
    """
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
    completed = tuple(receipt["phase"] for receipt in history)
    assessment = {
        "completed": completed,
        "status": "FORMAT_VALID_CANDIDATE",
        "durable_results_bound": False,
        "production_authorized": False
    }
    if result_loader is None and authority_verifier is None:
        return assessment
    require(callable(result_loader) and callable(authority_verifier),
            code_prefix + "_DURABLE_RESULT_AUTHORITY_PAIR_REQUIRED")
    for receipt in history:
        record = result_loader(receipt["execution_id"])
        require(isinstance(record, dict) and set(record) ==
                set(("phase", "execution_id", "result", "authority_binding")),
                code_prefix + "_DURABLE_RESULT_INVALID")
        require(record["phase"] == receipt["phase"] and
                record["execution_id"] == receipt["execution_id"],
                code_prefix + "_DURABLE_RESULT_IDENTITY_MISMATCH")
        require(sha256_value(record["result"]) == receipt["result_sha256"],
                code_prefix + "_DURABLE_RESULT_HASH_MISMATCH")
        require(authority_verifier(receipt, record) is True,
                code_prefix + "_DURABLE_RESULT_AUTHORITY_INVALID")
    assessment.update({
        "status": "AUTHORITY_BOUND_DURABLE_RESULTS_CANDIDATE",
        "durable_results_bound": True
    })
    return assessment


def next_phase_action(phases, history, requested, code_prefix, result_loader=None,
                      authority_verifier=None):
    require(requested in phases, code_prefix + "_PHASE_INVALID")
    assessment = validate_phase_history(phases, history, code_prefix, result_loader,
                                        authority_verifier)
    completed = assessment["completed"]
    if requested in completed:
        action = "REPLAY_NOOP"
    else:
        require(len(completed) < len(phases) and requested == phases[len(completed)],
                code_prefix + "_PHASE_ORDER_VIOLATION")
        action = "EXECUTE_ONCE"
    return {
        "action": action,
        "history_status": assessment["status"],
        "durable_results_bound": assessment["durable_results_bound"],
        "production_authorized": False,
        "scope": "CANDIDATE_ORDERING_ONLY_NOT_PRODUCTION_EXECUTOR"
    }


def _call_worker(callable_, output):
    ready_sent = False
    try:
        if hasattr(os, "setsid"):
            os.setsid()
        output.send(("ready", os.getpid(), os.getpgrp()))
        ready_sent = True
        try:
            value = callable_()
        except BaseException as error:
            output.send(("result", "error", repr(error)))
        else:
            output.send(("result", "ok", value))
    except BaseException as error:
        try:
            if ready_sent:
                output.send(("result", "ipc_error", repr(error)))
            else:
                output.send(("startup_error", repr(error)))
        except BaseException:
            pass
    finally:
        output.close()


def _terminate_process_tree(process, process_group):
    """Best-effort POSIX process-group containment for candidate operations."""
    if process.is_alive():
        if (hasattr(os, "killpg") and process_group == process.pid and
                process_group != os.getpgrp()):
            try:
                os.killpg(process_group, signal.SIGTERM)
            except OSError:
                pass
        else:
            process.terminate()
    process.join(1)
    if process.is_alive():
        if (hasattr(os, "killpg") and process_group == process.pid and
                process_group != os.getpgrp()):
            try:
                os.killpg(process_group, signal.SIGKILL)
            except OSError:
                pass
        elif hasattr(process, "kill"):
            process.kill()
        else:
            process.terminate()
        process.join(1)


def bounded_call(callable_, timeout_seconds):
    """Run an isolated callable with a real deadline.

    A timeout terminates the child and raises an explicit uncertain-side-effect
    error.  Callers must inspect/reconcile; this function never claims rollback.
    """
    require(timeout_seconds > 0, "TIMEOUT_REQUIRED")
    receiver, sender = multiprocessing.Pipe(duplex=False)
    process = multiprocessing.Process(target=_call_worker, args=(callable_, sender))
    started = time.monotonic()
    process.start()
    sender.close()
    process_group = None
    try:
        remaining = max(0, timeout_seconds - (time.monotonic() - started))
        if not receiver.poll(remaining):
            _terminate_process_tree(process, process_group)
            raise GateError("OPERATION_START_TIMEOUT_UNCERTAIN_SIDE_EFFECTS")
        try:
            ready = receiver.recv()
        except (EOFError, OSError):
            process.join(1)
            raise GateError("OPERATION_START_IPC_FAILED_NO_RESULT")
        require(isinstance(ready, tuple) and len(ready) == 3 and ready[0] == "ready",
                "OPERATION_START_ACK_INVALID")
        require(ready[1] == process.pid and type(ready[2]) is int,
                "OPERATION_START_IDENTITY_INVALID")
        process_group = ready[2]
        remaining = max(0, timeout_seconds - (time.monotonic() - started))
        if not receiver.poll(remaining):
            _terminate_process_tree(process, process_group)
            raise GateError("OPERATION_TIMEOUT_UNCERTAIN_SIDE_EFFECTS")
        try:
            message = receiver.recv()
        except (EOFError, OSError):
            _terminate_process_tree(process, process_group)
            raise GateError("OPERATION_RESULT_IPC_FAILED_UNCERTAIN_SIDE_EFFECTS")
        require(isinstance(message, tuple) and len(message) == 3 and
                message[0] == "result", "OPERATION_RESULT_ACK_INVALID")
        status, value = message[1], message[2]
        process.join(1)
        if process.is_alive():
            _terminate_process_tree(process, process_group)
            raise GateError("OPERATION_RESULT_CHILD_LINGERED_UNCERTAIN_SIDE_EFFECTS")
        require(process.exitcode == 0, "OPERATION_CHILD_FAILED_UNCERTAIN_SIDE_EFFECTS")
        require(status != "ipc_error",
                "OPERATION_RESULT_IPC_FAILED_UNCERTAIN_SIDE_EFFECTS:" + str(value))
        require(status == "ok", "OPERATION_CALLABLE_FAILED:" + str(value))
        return value
    finally:
        receiver.close()
        if process.is_alive():
            _terminate_process_tree(process, process_group)
