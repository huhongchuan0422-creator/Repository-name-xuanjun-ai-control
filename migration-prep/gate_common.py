"""Fail-closed helpers shared by Tokyo -> Korea migration gate candidates."""
from __future__ import print_function

import hashlib
import json
import os
import tempfile
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


def atomic_write_json(path, value):
    directory = os.path.dirname(os.path.abspath(path))
    descriptor, temporary = tempfile.mkstemp(prefix=".gate-", dir=directory)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class IdempotentLedger(object):
    """Small durable ledger for candidate tests and later privileged wrappers."""

    def __init__(self, path):
        self.path = path

    def _read(self):
        if not os.path.exists(self.path):
            return {"version": 1, "events": {}}
        value = load_json(self.path)
        require(value.get("version") == 1 and isinstance(value.get("events"), dict), "LEDGER_INVALID")
        return value

    def record(self, key, payload):
        require(isinstance(key, str) and key, "IDEMPOTENCY_KEY_REQUIRED")
        digest = sha256_value(payload)
        current = self._read()
        prior = current["events"].get(key)
        if prior is not None:
            require(prior["digest"] == digest, "IDEMPOTENCY_CONFLICT")
            return {"replayed": True, "digest": digest}
        current["events"][key] = {"digest": digest, "recorded_at": int(time.time())}
        atomic_write_json(self.path, current)
        return {"replayed": False, "digest": digest}


def bounded_call(callable_, timeout_seconds, clock=time.monotonic):
    """Reject a completed call that exceeded its declared evidence window."""
    require(timeout_seconds > 0, "TIMEOUT_REQUIRED")
    started = clock()
    result = callable_()
    elapsed = clock() - started
    require(elapsed <= timeout_seconds, "OPERATION_TIMEOUT")
    return result
