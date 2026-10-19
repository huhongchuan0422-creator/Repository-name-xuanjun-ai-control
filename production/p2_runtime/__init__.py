"""Isolated Linux process manager; never grants production access."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

MAX_LOG = 1024 * 1024
MAX_ENV = 64
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")

class Fault(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def durable(path, value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    temp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(temp), str(path))
        d = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(d)
        finally:
            os.close(d)
    finally:
        if temp.exists():
            temp.unlink()

def proc_identity(pid):
    try:
        raw = Path("/proc/%d/stat" % pid).read_text()
        suffix = raw.rsplit(")", 1)[1].split()
        start = suffix[19]
        state = suffix[0]
        pgrp = int(suffix[2])
        return {"pid": pid, "start": start, "state": state, "pgrp": pgrp}
    except (OSError, ValueError, IndexError):
        return None

def owned(entry):
    identity = proc_identity(entry["pid"])
    if identity is None or identity["state"] == "Z":
        return "GONE"
    if identity["start"] != entry["start"] or identity["pgrp"] != entry["pid"]:
        return "MISMATCH"
    return "LIVE"

def check_request(request):
    if not isinstance(request, dict) or request.get("schema") != 1 or request.get("scope") != "ISOLATED_TEST_ONLY":
        raise Fault("INVALID_SCOPE")
    for key in ("installation_id", "batch_id", "attempt_id"):
        if not isinstance(request.get(key), str) or not ID.fullmatch(request[key]):
            raise Fault("INVALID_ID")
    root = request.get("root")
    if not isinstance(root, str) or not os.path.isabs(root) or os.path.normpath(root) != root:
        raise Fault("INVALID_ROOT")
    if root == "/" or not isinstance(request.get("inputs"), dict):
        raise Fault("INVALID_INPUT")
    return Path(root)

def safe_root(path):
    # No symlinks in any path component. The component owns its root.
    current = Path("/")
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise Fault("SYMLINK_ROOT")
    if not path.exists() or not path.is_dir() or path.stat().st_uid != os.geteuid():
        raise Fault("ROOT_UNAVAILABLE")
    if path.stat().st_mode & 0o077:
        raise Fault("ROOT_NOT_PRIVATE")

def load(path):
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise Fault("UNSAFE_STATE")
    return json.loads(path.read_text())

def result(req, status, root, code=None, reference=None):
    base = {k: req[k] for k in ("schema", "scope", "installation_id", "batch_id", "attempt_id")}
    base["status"] = status
    base["error"] = None if code is None else {"code": code, "log": reference}
    receipt_path = root / ("receipt-" + req["batch_id"] + ".json")
    body = dict(base)
    durable(receipt_path, body)
    base["receipt"] = {"path": str(receipt_path), "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
    return base

def execute(request):
    return _operate(request, "execute")

def inspect(request):
    return _operate(request, "inspect")

def recover(request):
    return _operate(request, "recover")

def _operate(req, method):
    root = check_request(req)
    safe_root(root)
    lock = root / ".runtime.lock"
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return _locked(req, root, method)
    finally:
        os.close(fd)

def _locked(req, root, method):
    batch = req["batch_id"]
    journal = root / ("batch-" + batch + ".json")
    entry = load(journal)
    inputs = req["inputs"]
    operation = inputs.get("operation", "start")
    if entry and entry["installation_id"] != req["installation_id"]:
        return result(req, "HOLD", root, "BATCH_CONFLICT")
    if entry and entry["attempt_id"] != req["attempt_id"]:
        return result(req, "HOLD", root, "ATTEMPT_CONFLICT")
    if method != "execute":
        if entry is None:
            return result(req, "NO_EFFECT", root)
        if entry["phase"] == "PREPARED":
            return result(req, "HOLD", root, "START_OUTCOME_UNKNOWN", entry.get("log"))
        if entry["phase"] == "STOPPING":
            return result(req, "HOLD", root, "STOP_OUTCOME_UNKNOWN", entry.get("log"))
        state = owned(entry) if "pid" in entry else "GONE"
        if state == "MISMATCH":
            return result(req, "HOLD", root, "PID_IDENTITY_MISMATCH", entry.get("log"))
        if state == "LIVE":
            return result(req, "COMMITTED", root) if entry["phase"] == "RUNNING" else result(req, "HOLD", root, "UNEXPECTED_LIVE_PROCESS", entry.get("log"))
        return result(req, "NO_EFFECT", root)
    if operation not in ("start", "stop"):
        raise Fault("INVALID_OPERATION")
    if operation == "stop":
        if entry is None:
            return result(req, "NO_EFFECT", root)
        if entry["phase"] != "RUNNING":
            return result(req, "HOLD", root, "UNCERTAIN_JOURNAL", entry.get("log"))
        state = owned(entry)
        if state == "GONE":
            entry["phase"] = "STOPPED"
            durable(journal, entry)
            return result(req, "NO_EFFECT", root)
        if state != "LIVE":
            return result(req, "HOLD", root, "PID_IDENTITY_MISMATCH", entry.get("log"))
        entry["phase"] = "STOPPING"
        durable(journal, entry)
        # Only signal a verifiably owned process; no host/container management calls.
        os.kill(entry["pid"], signal.SIGTERM)
        until = time.monotonic() + min(10, max(0.1, float(inputs.get("timeout", 3))))
        while time.monotonic() < until and owned(entry) == "LIVE":
            time.sleep(0.05)
        state = owned(entry)
        if state != "GONE":
            return result(req, "HOLD", root, "STOP_UNCONFIRMED", entry.get("log"))
        entry["phase"] = "STOPPED"
        durable(journal, entry)
        return result(req, "COMMITTED", root)
    if entry:
        state = owned(entry) if "pid" in entry else "GONE"
        if entry["phase"] == "RUNNING" and state == "LIVE":
            return result(req, "COMMITTED", root)
        if entry["phase"] == "STOPPED" and state == "GONE":
            return result(req, "HOLD", root, "ATTEMPT_ALREADY_USED", entry.get("log"))
        return result(req, "HOLD", root, "UNCERTAIN_PRIOR_START", entry.get("log"))
    argv = inputs.get("argv")
    if not isinstance(argv, list) or not argv or len(argv) > 64 or any(not isinstance(x, str) or not x or "\x00" in x for x in argv):
        raise Fault("INVALID_ARGV")
    if argv[0] in ("/bin/sh", "/bin/bash", "sh", "bash"):
        raise Fault("SHELL_FORBIDDEN")
    if not os.path.isabs(argv[0]) or not Path(argv[0]).is_file() or not os.access(argv[0], os.X_OK):
        raise Fault("INVALID_EXECUTABLE")
    cwd = inputs.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not Path(cwd).is_dir():
        raise Fault("INVALID_CWD")
    env = inputs.get("env", {})
    if not isinstance(env, dict) or len(env) > MAX_ENV or any(not isinstance(k, str) or not ID.fullmatch(k) or not isinstance(v, str) or "\x00" in v for k, v in env.items()):
        raise Fault("INVALID_ENV")
    health = inputs.get("health", {"type": "process"})
    if not isinstance(health, dict) or health.get("type") != "process":
        raise Fault("INVALID_HEALTH")
    logfile = root / ("run-" + batch + ".log")
    entry = {"installation_id": req["installation_id"], "attempt_id": req["attempt_id"], "batch_id": batch,
             "phase": "PREPARED", "argv": argv, "cwd": cwd, "env_keys": sorted(env), "log": str(logfile)}
    durable(journal, entry)
    logfile.touch(mode=0o600, exist_ok=False)
    try:
        with logfile.open("wb") as out:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        identity = proc_identity(process.pid)
        if identity is None:
            return result(req, "HOLD", root, "PROCESS_IDENTITY_UNKNOWN", str(logfile))
        entry.update({"pid": process.pid, "start": identity["start"], "phase": "RUNNING"})
        durable(journal, entry)
        until = time.monotonic() + min(10, max(0.05, float(inputs.get("timeout", 2))))
        while time.monotonic() < until:
            if owned(entry) != "LIVE":
                return result(req, "HOLD", root, "HEALTH_FAILED", str(logfile))
            if logfile.stat().st_size > MAX_LOG:
                return result(req, "HOLD", root, "LOG_LIMIT", str(logfile))
            time.sleep(0.05)
        if owned(entry) != "LIVE":
            return result(req, "HOLD", root, "HEALTH_FAILED", str(logfile))
        return result(req, "COMMITTED", root)
    except (OSError, ValueError, subprocess.SubprocessError):
        return result(req, "HOLD", root, "LAUNCH_UNKNOWN", str(logfile))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=("execute", "inspect", "recover"))
    parser.add_argument("--request", help="JSON file; defaults to stdin")
    args = parser.parse_args()
    request = json.load(open(args.request)) if args.request else json.load(sys.stdin)
    try:
        value = globals()[args.method](request)
    except (Fault, OSError, ValueError, KeyError, json.JSONDecodeError) as err:
        value = {"status": "HOLD", "error": {"code": err.code if isinstance(err, Fault) else "INVALID_OR_UNAVAILABLE", "log": None}}
    print(json.dumps(value, sort_keys=True))
    return 0 if value["status"] != "HOLD" else 2

if __name__ == "__main__":
    sys.exit(main())
