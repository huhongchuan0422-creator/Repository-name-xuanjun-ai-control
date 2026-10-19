"""Isolated Linux process runtime with durable ownership, recovery and bounded logs."""
import argparse, fcntl, hashlib, json, os, re, signal, socket, subprocess, sys, time
from pathlib import Path

MAX_LOG = 1024 * 1024
MAX_ENV = 64
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
SECRET_KEYS = ("TOKEN", "SECRET", "PASSWORD", "PRIVATE", "KEY")

class Fault(Exception):
    def __init__(self, code, reference=None):
        self.code, self.reference = code, reference
        super().__init__(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def durable(path, value, replace=True):
    payload = canonical(value)
    if not replace and path.exists():
        raise Fault("IMMUTABLE_RECEIPT_EXISTS", str(path))
    temp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload); out.flush(); os.fsync(out.fileno())
        if not replace and path.exists():
            raise Fault("IMMUTABLE_RECEIPT_EXISTS", str(path))
        os.replace(str(temp), str(path))
        dfd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        try: temp.unlink()
        except FileNotFoundError: pass

def load(path):
    if not path.exists(): return None
    if path.is_symlink() or not path.is_file(): raise Fault("UNSAFE_STATE", str(path))
    return json.loads(path.read_text())

def check_request(req):
    if not isinstance(req, dict) or req.get("schema") != 1 or req.get("scope") != "ISOLATED_TEST_ONLY":
        raise Fault("INVALID_SCOPE")
    for key in ("installation_id", "batch_id", "attempt_id"):
        if not isinstance(req.get(key), str) or not ID.fullmatch(req[key]): raise Fault("INVALID_ID")
    root = req.get("root")
    if not isinstance(root, str) or not os.path.isabs(root) or os.path.normpath(root) != root or root == "/":
        raise Fault("INVALID_ROOT")
    if not isinstance(req.get("inputs"), dict): raise Fault("INVALID_INPUT")
    return Path(root)

def safe_root(path):
    cur = Path("/")
    for part in path.parts[1:]:
        cur /= part
        if cur.is_symlink(): raise Fault("SYMLINK_ROOT")
    st = path.stat()
    if not path.is_dir() or st.st_uid != os.geteuid(): raise Fault("ROOT_UNAVAILABLE")
    if st.st_mode & 0o077: raise Fault("ROOT_NOT_PRIVATE")

def proc(pid):
    try:
        raw = Path("/proc/%d/stat" % pid).read_text()
        f = raw.rsplit(")", 1)[1].split()
        return {"pid": pid, "state": f[0], "ppid": int(f[1]), "pgrp": int(f[2]), "session": int(f[3]), "start": f[19]}
    except (OSError, ValueError, IndexError):
        return None

def process_match(identity):
    now = proc(identity["pid"])
    if now is None or now["state"] == "Z": return "GONE"
    if now["start"] != identity["start"] or now["session"] != identity["session"]: return "MISMATCH"
    return "LIVE"

def scan_group(pgid):
    try: names = list(Path("/proc").iterdir())
    except OSError: return None
    found = []
    for item in names:
        if not item.name.isdigit(): continue
        p = proc(int(item.name))
        if p and p["state"] != "Z" and p["pgrp"] == pgid: found.append(p)
    return sorted(found, key=lambda x: x["pid"])

def workload_state(entry):
    leader = proc(entry.get("pid", -1))
    if leader and leader["state"] != "Z":
        if leader["start"] != entry.get("start") or leader["pgrp"] != entry.get("pgid") or leader["session"] != entry.get("session"):
            return "MISMATCH", []
    group = scan_group(entry.get("pgid", -1))
    if group is None: return "UNKNOWN", []
    if group and any(p["session"] != entry.get("session") for p in group): return "MISMATCH", group
    return ("LIVE", group) if group else ("GONE", [])

def process_set(entry):
    workload, group = workload_state(entry) if "pid" in entry else ("GONE", [])
    collector = process_match(entry["collector"]) if entry.get("collector") else "GONE"
    if workload == "MISMATCH" or collector == "MISMATCH": return "MISMATCH", group, collector
    if workload == "UNKNOWN": return "UNKNOWN", group, collector
    if workload == "GONE" and collector == "GONE": return "GONE", group, collector
    return "LIVE", group, collector

def bounded_number(value, low, high, code):
    try: value = float(value)
    except (TypeError, ValueError): raise Fault(code)
    if value < low or value > high: raise Fault(code)
    return value

def validate_health(health, root):
    if not isinstance(health, dict): raise Fault("INVALID_HEALTH")
    kind = health.get("type")
    if kind == "process":
        return {"type": "process"}
    if kind != "unix_socket": raise Fault("INVALID_HEALTH")
    path = health.get("path")
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
        raise Fault("INVALID_HEALTH_SOCKET")
    try:
        Path(path).relative_to(root)
    except ValueError:
        raise Fault("HEALTH_SOCKET_OUTSIDE_ROOT")
    request = health.get("request", "")
    expect = health.get("expect")
    if not isinstance(request, str) or not isinstance(expect, str) or not expect:
        raise Fault("INVALID_HEALTH_PROTOCOL")
    try:
        request_bytes = request.encode("utf-8")
        expect_bytes = expect.encode("utf-8")
    except UnicodeError:
        raise Fault("INVALID_HEALTH_PROTOCOL")
    if len(request_bytes) > 4096 or len(expect_bytes) > 4096:
        raise Fault("INVALID_HEALTH_PROTOCOL")
    connect_timeout = bounded_number(health.get("connect_timeout", .2), .01, 5.0, "INVALID_HEALTH_TIMEOUT")
    read_timeout = bounded_number(health.get("read_timeout", .2), .01, 5.0, "INVALID_HEALTH_TIMEOUT")
    total_timeout = bounded_number(health.get("total_timeout", 2.0), .02, 30.0, "INVALID_HEALTH_TIMEOUT")
    max_response = health.get("max_response", 4096)
    if not isinstance(max_response, int) or isinstance(max_response, bool) or max_response < len(expect_bytes) or max_response > 65536:
        raise Fault("INVALID_HEALTH_RESPONSE_LIMIT")
    return {"type":"unix_socket","path":path,"request":request,"expect":expect,
            "connect_timeout":connect_timeout,"read_timeout":read_timeout,
            "total_timeout":total_timeout,"max_response":max_response}

def config_payload(inputs, root):
    argv = inputs.get("argv")
    if not isinstance(argv, list) or not argv or len(argv) > 64 or any(not isinstance(x, str) or not x or "\x00" in x for x in argv):
        raise Fault("INVALID_ARGV")
    if argv[0] in ("/bin/sh", "/bin/bash", "sh", "bash"): raise Fault("SHELL_FORBIDDEN")
    if not os.path.isabs(argv[0]) or not Path(argv[0]).is_file() or not os.access(argv[0], os.X_OK):
        raise Fault("INVALID_EXECUTABLE")
    cwd = inputs.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not Path(cwd).is_dir(): raise Fault("INVALID_CWD")
    env = inputs.get("env", {})
    if not isinstance(env, dict) or len(env) > MAX_ENV: raise Fault("INVALID_ENV")
    for k, v in env.items():
        if not isinstance(k, str) or not ID.fullmatch(k) or not isinstance(v, str) or "\x00" in v: raise Fault("INVALID_ENV")
        if any(mark in k.upper() for mark in SECRET_KEYS): raise Fault("SECRET_ENV_FORBIDDEN")
    health = validate_health(inputs.get("health", {"type": "process"}), root)
    timeout = bounded_number(inputs.get("timeout", 2), .05, 10.0, "INVALID_TIMEOUT")
    return {"argv": argv, "cwd": cwd, "env": env, "health": health, "timeout": timeout}

def stable_identity(req, entry=None):
    cfg = entry.get("config_sha256") if entry else None
    op = entry.get("operation_id") if entry else None
    commit = entry.get("commit_receipt") if entry else None
    return cfg, op, commit

def base(req, status, error=None, receipt=None, entry=None):
    cfg, op, commit = stable_identity(req, entry)
    out = {k: req[k] for k in ("schema", "scope", "installation_id", "batch_id", "attempt_id")}
    out.update({"status": status, "receipt": receipt, "error": error,
                "config_sha256": cfg, "operation_id": op, "commit_receipt": commit})
    return out

def write_receipt(req, root, kind, status, error=None, entry=None):
    path = root / ("%s-%s-%s-%d.json" % (kind, req["batch_id"], req["attempt_id"], time.time_ns()))
    durable(path, base(req, status, error, None, entry), replace=False)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

def finish(req, root, status, code=None, reference=None, kind="observe", entry=None):
    err = None if code is None else {"code": code, "log": reference}
    rec = write_receipt(req, root, kind, status, err, entry)
    return base(req, status, err, rec, entry)

def marker_path(root, batch):
    return root / ("limit-" + batch + ".json")

def marker_error(entry):
    mark = load(Path(entry["limit_marker"]))
    if not mark: return None
    return mark.get("code", "LOG_LIMIT")

def safe_kill_group(identity, sig):
    leader = proc(identity["pid"])
    group = scan_group(identity["pgid"])
    if group is None: return "PROCESS_SET_UNKNOWN"
    if leader and leader["state"] != "Z":
        if leader["start"] != identity["start"] or leader["session"] != identity["session"] or leader["pgrp"] != identity["pgid"]:
            return "PID_IDENTITY_MISMATCH"
    if group and any(p["session"] != identity["session"] for p in group): return "PID_IDENTITY_MISMATCH"
    if not group: return None
    try: os.killpg(identity["pgid"], sig)
    except ProcessLookupError: return None
    return None

def terminate_owned(entry, timeout):
    state, _, collector = process_set(entry)
    if state == "MISMATCH": return "PID_IDENTITY_MISMATCH"
    if state == "UNKNOWN": return "PROCESS_SET_UNKNOWN"
    if workload_state(entry)[0] == "LIVE":
        err = safe_kill_group(entry, signal.SIGTERM)
        if err: return err
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        ws, _ = workload_state(entry)
        if ws == "MISMATCH": return "PID_IDENTITY_MISMATCH"
        if ws == "UNKNOWN": return "PROCESS_SET_UNKNOWN"
        if ws == "GONE": break
        time.sleep(.03)
    if workload_state(entry)[0] != "GONE": return "STOP_TIMEOUT"
    if entry.get("collector") and process_match(entry["collector"]) == "LIVE":
        try: os.kill(entry["collector"]["pid"], signal.SIGTERM)
        except ProcessLookupError: pass
        until = time.monotonic() + min(timeout, 1.0)
        while time.monotonic() < until and process_match(entry["collector"]) == "LIVE": time.sleep(.03)
    c = process_match(entry["collector"]) if entry.get("collector") else "GONE"
    if c == "MISMATCH": return "COLLECTOR_IDENTITY_MISMATCH"
    if c == "LIVE": return "COLLECTOR_STOP_TIMEOUT"
    return None

def probe_health(entry):
    health = entry.get("health", {"type":"process"})
    if health.get("type") == "process":
        return None
    deadline = time.monotonic() + health["total_timeout"]
    last = "APP_NOT_READY"
    while time.monotonic() < deadline:
        ws, _ = workload_state(entry)
        if ws == "GONE": return "APPLICATION_EXITED"
        if ws == "MISMATCH": return "PID_IDENTITY_MISMATCH"
        if ws == "UNKNOWN": return "PROCESS_SET_UNKNOWN"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            remaining = max(.001, deadline - time.monotonic())
            sock.settimeout(min(health["connect_timeout"], remaining))
            sock.connect(health["path"])
            if health["request"]:
                sock.sendall(health["request"].encode("utf-8"))
            remaining = max(.001, deadline - time.monotonic())
            sock.settimeout(min(health["read_timeout"], remaining))
            data = bytearray()
            while len(data) <= health["max_response"]:
                remaining = max(.001, deadline - time.monotonic())
                sock.settimeout(min(health["read_timeout"], remaining))
                chunk = sock.recv(min(4096, health["max_response"] + 1 - len(data)))
                if not chunk: break
                data.extend(chunk)
                expected = health["expect"].encode("utf-8")
                if data == expected: return None
                if not expected.startswith(data) and data != expected:
                    last = "HEALTH_BAD_RESPONSE"; break
            if len(data) > health["max_response"]:
                return "HEALTH_RESPONSE_TOO_LARGE"
            if bytes(data) != health["expect"].encode("utf-8") and last != "HEALTH_BAD_RESPONSE":
                last = "HEALTH_BAD_RESPONSE"
        except socket.timeout:
            last = "HEALTH_TIMEOUT"
        except (FileNotFoundError, ConnectionRefusedError):
            last = "APP_NOT_READY"
        except OSError:
            last = "HEALTH_IO_ERROR"
        finally:
            sock.close()
        if time.monotonic() < deadline: time.sleep(.02)
    return last

def monitor(entry, timeout):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        mark = marker_error(entry)
        if mark: return mark
        ws, _ = workload_state(entry)
        if ws == "GONE": return "HEALTH_FAILED"
        if ws == "MISMATCH": return "PID_IDENTITY_MISMATCH"
        if ws == "UNKNOWN": return "PROCESS_SET_UNKNOWN"
        col = process_match(entry["collector"])
        if col != "LIVE": return "LOG_COLLECTOR_FAILED" if col == "GONE" else "COLLECTOR_IDENTITY_MISMATCH"
        if entry.get("health", {"type":"process"}).get("type") == "process":
            time.sleep(.03)
            continue
        probe = probe_health(entry)
        if probe is None: return None
        if probe in ("APPLICATION_EXITED","PID_IDENTITY_MISMATCH","PROCESS_SET_UNKNOWN","HEALTH_RESPONSE_TOO_LARGE"):
            return probe
        time.sleep(.02)
    if entry.get("health", {"type":"process"}).get("type") == "process":
        return marker_error(entry)
    return probe_health(entry)

def execute(request): return _operate(request, "execute")
def inspect(request): return _operate(request, "inspect")
def recover(request): return _operate(request, "recover")

def _operate(req, method):
    root = check_request(req); safe_root(root)
    lock = root / ".runtime.lock"
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return _locked(req, root, method)
    except Fault as e:
        return finish(req, root, "HOLD", e.code, e.reference)
    finally:
        os.close(fd)

def _locked(req, root, method):
    inputs = req["inputs"]; op = inputs.get("operation", "start")
    journal = root / ("batch-" + req["batch_id"] + ".json")
    entry = load(journal)
    if entry and entry["installation_id"] != req["installation_id"]: return finish(req, root, "HOLD", "BATCH_CONFLICT", entry.get("log"))
    if entry and entry["attempt_id"] != req["attempt_id"]: return finish(req, root, "HOLD", "ATTEMPT_CONFLICT", entry.get("log"))
    if op == "start":
        cfg = config_payload(inputs, root); expected = digest(cfg)
        if entry and entry.get("config_sha256") != expected: return finish(req, root, "HOLD", "CONFIG_CONFLICT", entry.get("log"))

    if method != "execute":
        if entry is None: return finish(req, root, "NO_EFFECT")
        mark = marker_error(entry)
        state, group, collector = process_set(entry) if "pid" in entry else ("GONE", [], "GONE")
        if state == "MISMATCH": return finish(req, root, "HOLD", "PID_IDENTITY_MISMATCH", entry.get("log"))
        if state == "UNKNOWN": return finish(req, root, "HOLD", "PROCESS_SET_UNKNOWN", entry.get("log"))
        if mark:
            if state != "GONE":
                entry["phase"] = "STOPPING"; durable(journal, entry)
                err = terminate_owned(entry, 1.0)
                if err: return finish(req, root, "HOLD", err, entry.get("log"))
            entry["phase"] = "STOPPED"; entry["members"] = []; durable(journal, entry)
            return finish(req, root, "HOLD", mark, entry.get("log"))
        if entry["phase"] == "PREPARED": return finish(req, root, "HOLD", "START_OUTCOME_UNKNOWN", entry.get("log"))
        if entry["phase"] == "STOPPING":
            if state == "GONE":
                entry["phase"] = "STOPPED"; entry["members"] = []; durable(journal, entry)
                return finish(req, root, "COMMITTED", kind="commit")
            if method == "recover":
                err = terminate_owned(entry, min(10.0, max(.05, float(inputs.get("timeout", 3)))))
                if err: return finish(req, root, "HOLD", err, entry.get("log"))
                entry["phase"] = "STOPPED"; entry["members"] = []; durable(journal, entry)
                return finish(req, root, "COMMITTED", kind="commit")
            return finish(req, root, "HOLD", "STOP_OUTCOME_UNKNOWN", entry.get("log"))
        if entry["phase"] == "RUNNING":
            ws, group = workload_state(entry)
            if ws != "LIVE": return finish(req, root, "HOLD", "RUNNING_PROCESS_MISSING", entry.get("log"))
            if collector != "LIVE": return finish(req, root, "HOLD", "LOG_COLLECTOR_FAILED", entry.get("log"))
            entry["members"] = [{"pid": p["pid"], "start": p["start"]} for p in group]; durable(journal, entry)
            return finish(req, root, "COMMITTED")
        if entry["phase"] == "STOPPED":
            ws, _ = workload_state(entry) if "pid" in entry else ("GONE", [])
            if ws == "GONE" and collector == "LIVE":
                err = terminate_owned(entry, 1.0)
                if err: return finish(req, root, "HOLD", err, entry.get("log"))
                state, _, collector = process_set(entry)
            if state == "GONE": return finish(req, root, "NO_EFFECT")
        return finish(req, root, "HOLD", "UNEXPECTED_LIVE_PROCESS", entry.get("log"))

    if op not in ("start", "stop"): raise Fault("INVALID_OPERATION")
    if op == "stop":
        if entry is None: return finish(req, root, "NO_EFFECT")
        if entry["phase"] not in ("RUNNING", "STOPPING"): return finish(req, root, "HOLD", "UNCERTAIN_JOURNAL", entry.get("log"))
        state, _, _ = process_set(entry)
        if state == "MISMATCH": return finish(req, root, "HOLD", "PID_IDENTITY_MISMATCH", entry.get("log"))
        if state == "UNKNOWN": return finish(req, root, "HOLD", "PROCESS_SET_UNKNOWN", entry.get("log"))
        entry["phase"] = "STOPPING"; durable(journal, entry)
        err = terminate_owned(entry, min(10.0, max(.05, float(inputs.get("timeout", 3)))))
        if err: return finish(req, root, "HOLD", err, entry.get("log"))
        entry["phase"] = "STOPPED"; entry["members"] = []; durable(journal, entry)
        return finish(req, root, "COMMITTED", kind="commit")

    if entry:
        mark = marker_error(entry)
        state, _, collector = process_set(entry) if "pid" in entry else ("GONE", [], "GONE")
        if mark:
            if state != "GONE":
                entry["phase"] = "STOPPING"; durable(journal, entry)
                err = terminate_owned(entry, 1.0)
                if err: return finish(req, root, "HOLD", err, entry.get("log"))
            entry["phase"] = "STOPPED"; durable(journal, entry)
            return finish(req, root, "HOLD", mark, entry.get("log"))
        if entry["phase"] == "RUNNING" and workload_state(entry)[0] == "LIVE" and collector == "LIVE":
            return finish(req, root, "COMMITTED")
        if entry["phase"] == "PREPARED": return finish(req, root, "HOLD", "START_OUTCOME_UNKNOWN", entry.get("log"))
        if entry["phase"] == "STOPPED" and state == "GONE": return finish(req, root, "HOLD", "ATTEMPT_ALREADY_USED", entry.get("log"))
        return finish(req, root, "HOLD", "UNCERTAIN_PRIOR_START", entry.get("log"))

    cfg = config_payload(inputs, root)
    logfile = root / ("run-" + req["batch_id"] + ".log")
    limitmark = marker_path(root, req["batch_id"])
    if logfile.exists() or limitmark.exists(): return finish(req, root, "HOLD", "BATCH_FILES_EXIST", str(logfile))
    entry = {"installation_id": req["installation_id"], "batch_id": req["batch_id"], "attempt_id": req["attempt_id"],
             "phase": "PREPARED", "config_sha256": digest(cfg), "argv": cfg["argv"], "cwd": cfg["cwd"],
             "env_sha256": digest(cfg["env"]), "health_sha256": digest(cfg["health"]), "health": cfg["health"],
             "operation_id": digest({"installation_id":req["installation_id"],"batch_id":req["batch_id"],
                                      "attempt_id":req["attempt_id"],"config_sha256":digest(cfg)}),
             "commit_receipt": None, "log": str(logfile), "limit_marker": str(limitmark), "members": []}
    durable(journal, entry)
    try:
        workload = subprocess.Popen(cfg["argv"], cwd=cfg["cwd"], env=cfg["env"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        ident = proc(workload.pid)
        if ident is None or ident["pgrp"] != workload.pid or ident["session"] != workload.pid:
            return finish(req, root, "HOLD", "PROCESS_IDENTITY_UNKNOWN", str(logfile))
        entry.update({"pid": workload.pid, "start": ident["start"], "pgid": ident["pgrp"], "session": ident["session"]})
        collector_args = [sys.executable, str(Path(__file__).resolve()), "_collect", str(logfile), str(limitmark),
                          str(MAX_LOG), str(ident["pid"]), ident["start"], str(ident["pgrp"]), str(ident["session"])]
        collector = subprocess.Popen(collector_args, stdin=workload.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True, close_fds=True)
        workload.stdout.close()
        ci = proc(collector.pid)
        if ci is None:
            entry["phase"] = "STOPPING"; durable(journal, entry); terminate_owned(entry, 1.0)
            return finish(req, root, "HOLD", "COLLECTOR_IDENTITY_UNKNOWN", str(logfile))
        entry["collector"] = {"pid": ci["pid"], "start": ci["start"], "session": ci["session"]}
        entry["phase"] = "RUNNING"; durable(journal, entry)
        err = monitor(entry, cfg["timeout"])
        if err:
            entry["phase"] = "STOPPING"; durable(journal, entry)
            cleanup = terminate_owned(entry, 1.0)
            if cleanup: return finish(req, root, "HOLD", cleanup, str(logfile))
            entry["phase"] = "STOPPED"; entry["members"] = []; durable(journal, entry)
            return finish(req, root, "HOLD", err, str(logfile))
        ws, group = workload_state(entry)
        entry["members"] = [{"pid": p["pid"], "start": p["start"]} for p in group] if ws == "LIVE" else []
        durable(journal, entry)
        return finish(req, root, "COMMITTED", kind="commit")
    except (OSError, ValueError, subprocess.SubprocessError):
        return finish(req, root, "HOLD", "LAUNCH_UNKNOWN", str(logfile))

def collector(logfile, markfile, limit, pid, start, pgid, session):
    identity = {"pid": pid, "start": start, "pgid": pgid, "session": session}
    log = Path(logfile); mark = Path(markfile); limit = int(limit)
    fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    used = 0; overflow = False
    try:
        with os.fdopen(fd, "wb", buffering=0) as out:
            while True:
                chunk = os.read(0, 65536)
                if not chunk: break
                room = max(0, limit - used)
                if room:
                    piece = chunk[:room]; out.write(piece); used += len(piece)
                if len(chunk) > room:
                    overflow = True
                    durable(mark, {"schema": 1, "code": "LOG_LIMIT", "bytes": used}, replace=False)
                    err = safe_kill_group(identity, signal.SIGTERM)
                    if err:
                        durable(mark.with_name(mark.name + ".error"), {"schema": 1, "code": err}, replace=False)
                    break
            try: os.fsync(out.fileno())
            except OSError: pass
    finally:
        if overflow:
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and workload_state(identity)[0] == "LIVE": time.sleep(.03)
            if workload_state(identity)[0] == "LIVE": safe_kill_group(identity, signal.SIGKILL)
    return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_collect":
        return collector(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6], int(sys.argv[7]), int(sys.argv[8]))
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=("execute", "inspect", "recover"))
    parser.add_argument("--request")
    args = parser.parse_args()
    try:
        req = json.load(open(args.request)) if args.request else json.load(sys.stdin)
        value = globals()[args.method](req)
    except (Fault, OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        value = {"schema": 1, "scope": "ISOLATED_TEST_ONLY", "installation_id": None, "batch_id": None, "attempt_id": None,
                 "status": "HOLD", "receipt": None,
                 "error": {"code": getattr(e, "code", "INVALID_OR_UNAVAILABLE"), "log": getattr(e, "reference", None)}}
    print(json.dumps(value, sort_keys=True))
    return 0 if value["status"] != "HOLD" else 2
if __name__ == "__main__": sys.exit(main())
