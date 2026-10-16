"""One private service-contract capture; never install or activate a service."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import tarfile
import time
import urllib.request

ACTION = "PR99_S06_PRIVATE_RUNTIME_CONTRACT_V1"
REPO = "huhongchuan0422-creator/Repository-name-xuanjun-ai-control"
TOKYO = "iZ6wee8q9z4t03hvqumwfhZ"
KOREA = "iZmj7a5kwr75qc1tul4kf9Z"
SOURCE = Path("/root/pr99-s06-runtime-contract-v1")
TARGET = Path("/root/pr99-s06-runtime-received-v1")
R2 = Path("/root/pr99-current-point-received-v2")
DB_SHA = "6d451dfdc4714ca9bc704d719dcb47b02ec1e2ce243f886bfb2578a27fbca232"
CIPHER_SHA = "2ac42b9e69c69260c99387b2e1ae339dd2e80b3f01c1984858e458e6c8872d32"
PUBLIC_KEY = "47.245.53.152 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBMfngQ3DTnuC8aP0TZ0fBhcq+8p7Yw0c7VEYKWSpFrtpqWf+shoFTiyrAWj1OlrnoeOlsZq1SS1zOavODbJOnzs=\n"
UNITS = (
    "secure-secrets-portal.service", "xuanjun-wecom-customer-contact.service",
    "xuanjun-wecom-customer-service.service", "xuanjun-wecom-novel-ingress.service",
    "domestic-model-rpc-tunnel.service", "korea-novel-model-rpc-tunnel.service",
    "provider-neutral-tokyo-tunnel.service", "restricted-rpc-openai-shim.service",
    "tokyo-restricted-model-executor.service", "xj-tokyo-vpn.service",
)
FILES = tuple("/etc/systemd/system/" + n for n in UNITS) + (
    "/etc/systemd/system/tokyo-restricted-model-executor.service.d/provider-health-alert.conf",)
PROPS = ("Id", "Names", "LoadState", "ActiveState", "SubState", "MainPID", "User",
         "Group", "WorkingDirectory", "FragmentPath", "DropInPaths", "Requires", "Wants",
         "After", "ReadWritePaths", "EnvironmentFiles", "ControlGroup")
MAX_FILE = 262144
MAX_TOTAL = 4 * 1024 * 1024


class Hold(RuntimeError):
    pass


def need(value, reason):
    if not value:
        raise Hold(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_directory(path):
    s = path.lstat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o700,
         "PRIVATE_DIRECTORY_IDENTITY")


def stable_file(path, limit=MAX_FILE, owner=0, private=False):
    for p in reversed(path.parents):
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             "UNTRUSTED_PARENT")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        s = os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid == owner and s.st_nlink == 1
             and not s.st_mode & 0o022 and s.st_size <= limit, "FILE_IDENTITY_OR_SIZE")
        if private:
            need(stat.S_IMODE(s.st_mode) in (0o400, 0o600), "PRIVATE_FILE_MODE")
        data = f.read(limit + 1)
        after = os.fstat(f.fileno())
    current = path.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    need(len(data) == s.st_size and all(getattr(s, k) == getattr(after, k)
         == getattr(current, k) for k in fields), "FILE_CHANGED")
    return data


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def command(args, timeout=15):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})


def verify_approval(record, args, now):
    need(args.confirm_independent_auditor, "INDEPENDENT_REVIEW_CONFIRMATION_REQUIRED")
    need(record.get("id") == args.approval_id and record.get("issue_url") ==
         "https://api.github.com/repos/" + REPO + "/issues/99", "APPROVAL_ID_OR_PR")
    u = record.get("user", {})
    need(u.get("id") == 332398908 and u.get("login") == "huhongchuan0422-creator"
         and u.get("type") == "User", "APPROVAL_AUTHOR")
    body = record["body"]
    need(sha(body.encode()) == args.approval_sha256, "APPROVAL_BODY")
    start, end = "<!-- PR99_S06_RUNTIME_APPROVAL_V1\n", "\nPR99_S06_RUNTIME_APPROVAL_V1 -->"
    need(body.count(start) == body.count(end) == 1, "APPROVAL_MARKER")
    a = json.loads(body.split(start)[1].split(end)[0])
    need(a["decision"] == "APPROVED_WITH_EXACT_PRECONDITIONS" and a["action"] == ACTION
         and type(a["max_attempts"]) is int and a["max_attempts"] == 1, "APPROVAL_ACTION")
    need(re.fullmatch("[0-9a-f]{40}", args.source_commit)
         and a["source_commit"] == args.source_commit and a["script_sha256"] == args.script_sha256
         and a["source_host"] == TOKYO and a["target_host"] == KOREA, "APPROVAL_BINDING")
    need(type(a["issued_at"]) is int and type(a["expires_at"]) is int
         and a["issued_at"] <= now < a["expires_at"]
         and 0 < a["expires_at"] - a["issued_at"] <= 43200, "APPROVAL_TIME")
    return a


def approval(args):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("https://api.github.com/repos/" + REPO + "/issues/comments/" +
                     str(args.approval_id), timeout=20) as r:
        raw = r.read(200001)
    need(len(raw) <= 200000, "APPROVAL_SIZE")
    record = json.loads(raw)
    return record, verify_approval(record, args, int(time.time()))


def unit_metadata():
    result = {}
    for name in UNITS + ("provider-neutral-tunnel.service",):
        r = command(["/usr/bin/systemctl", "show", name, "--no-pager"] +
                    [v for k in PROPS for v in ("-p", k)])
        props = dict(line.split("=", 1) for line in r.stdout.decode().splitlines() if "=" in line)
        need(r.returncode == 0 or props.get("LoadState") == "not-found", "UNIT_QUERY_FAILED")
        result[name] = props
    for name in UNITS:
        p = result[name]
        need(p.get("LoadState") == "loaded" and p.get("FragmentPath") ==
             "/etc/systemd/system/" + name, "UNIT_PATH_OR_LOAD_DRIFT")
        expected = FILES[-1] if name == "tokyo-restricted-model-executor.service" else ""
        need(p.get("DropInPaths", "") == expected, "UNIT_DROPIN_SET_DRIFT")
    return result


def listener_metadata():
    r = command(["/usr/sbin/ss", "-H", "-lntp"])
    need(r.returncode == 0, "LISTENER_QUERY_FAILED")
    rows = []
    for line in r.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            port = int(parts[3].rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if port not in (443, 18080, 18443, 18761, 18770, 18780, 18781, 19443, 19444):
            continue
        pids = sorted(set(re.findall(r"pid=(\d+)", line)))
        processes = []
        for pid in pids:
            details = {"pid": pid}
            for name in ("exe", "cwd"):
                try:
                    details[name] = os.readlink("/proc/" + pid + "/" + name)
                except OSError as e:
                    details[name] = {"status": "UNKNOWN", "error_type": type(e).__name__}
            try:
                details["uid"] = Path("/proc/" + pid).stat().st_uid
                details["systemd_units"] = sorted(set(re.findall(r"([^/\n]+\.service)",
                    Path("/proc/" + pid + "/cgroup").read_text())))
            except OSError as e:
                details["identity"] = {"status": "UNKNOWN", "error_type": type(e).__name__}
            processes.append(details)
        rows.append({"endpoint": parts[3], "port": port, "pids": pids,
                     "visible_process_metadata": processes, "owner_observed": bool(pids)})
    return rows


def make_tar(files):
    need(set(files) == {"units/" + Path(p).name for p in FILES[:-1]} |
         {"dropins/provider-health-alert.conf", "private-runtime.json"}, "CAPTURE_FILE_SET")
    need(sum(map(len, files.values())) <= MAX_TOTAL, "CAPTURE_TOTAL")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as t:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.uid, info.gid, info.mtime = len(data), 0o600, 0, 0, 0
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def capture(expires):
    need(os.geteuid() == 0 and os.uname().nodename == TOKYO and time.time() < expires,
         "SOURCE_ROOT_HOST_OR_TIME")
    os.umask(0o077)
    SOURCE.mkdir(mode=0o700)
    try:
        write_new(SOURCE / "capture.started", b"one private config capture; preserve; no retry\n")
        before = unit_metadata()
        data, identities = {}, {}
        for path in FILES:
            name = "dropins/provider-health-alert.conf" if path == FILES[-1] else "units/" + Path(path).name
            raw = stable_file(Path(path))
            data[name], identities[path] = raw, sha(raw)
        private = {"epoch": int(time.time()), "units": before, "listeners": listener_metadata(),
                   "environment_files_opened": False, "argv_read": False,
                   "database_opened": False, "unit_body_may_contain_inline_authentication": True}
        data["private-runtime.json"] = encoded(private)
        need(unit_metadata() == before, "MANAGER_CHANGED_DURING_CAPTURE")
        for path in FILES:
            need(sha(stable_file(Path(path))) == identities[path], "UNIT_BYTES_CHANGED")
        archive = make_tar(data)
        write_new(SOURCE / "payload.tar.gz", archive)
        write_new(SOURCE / "payload.key", (os.urandom(32).hex() + "\n").encode())
        with (SOURCE / "openssl-private.log").open("xb") as log, (SOURCE / "payload.enc").open("xb") as out:
            r = subprocess.run(["/usr/bin/openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2",
                "-iter", "200000", "-md", "sha256", "-in", str(SOURCE / "payload.tar.gz"),
                "-pass", "file:" + str(SOURCE / "payload.key")], stdout=out, stderr=log, timeout=40)
            out.flush(); os.fsync(out.fileno())
        need(r.returncode == 0, "ENCRYPTION_FAILED")
        cipher = stable_file(SOURCE / "payload.enc", MAX_TOTAL + 65536, private=True)
        receipt = {"status": "S06_PRIVATE_CONTRACT_PREPARED", "host": TOKYO,
                   "cipher_sha256": sha(cipher), "cipher_bytes": len(cipher),
                   "archive_sha256": sha(archive), "files": {p: sha(b) for p, b in data.items()},
                   "file_count": len(data), "unit_count": len(UNITS), "service_actions": 0,
                   "business_api_requests": 0, "environment_files_opened": False,
                   "database_opened": False, "production_deployed": False}
        write_new(SOURCE / "receipt.json", encoded(receipt))
    except BaseException as e:
        write_new(SOURCE / "failure.json", encoded({"status": "HOLD_PRESERVE_EVIDENCE",
                  "reason": str(e) if isinstance(e, Hold) else type(e).__name__, "retry_allowed": False}))
        raise


def signal_hold(number, unused_frame):
    raise Hold("SIGNAL_" + str(number))


def ssh_step(common, remote, cmd, out, work, step, data=None):
    with (work / ("ssh-step-%03d.stderr.log" % step)).open("xb") as err:
        os.fchmod(err.fileno(), 0o600)
        r = subprocess.run(common + ["-o", "BatchMode=yes", remote, cmd], input=data,
                           stdout=out, stderr=err, timeout=120)
        err.flush(); os.fsync(err.fileno())
    need(r.returncode == 0, "SSH_STEP_%03d_EXIT_%s" % (step, r.returncode))


def verify_archive(raw, expected):
    need(sha(raw) == expected["archive_sha256"], "ARCHIVE_DIGEST")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
        for m in t:
            p = PurePosixPath(m.name)
            need(m.isfile() and not p.is_absolute() and ".." not in p.parts
                 and m.name not in files and m.name in expected["files"]
                 and 0 <= m.size <= (MAX_TOTAL if m.name == "private-runtime.json" else MAX_FILE), "ARCHIVE_MEMBER")
            need(sum(map(len, files.values())) + m.size <= MAX_TOTAL, "ARCHIVE_LIMIT")
            f = t.extractfile(m)
            with f:
                b = f.read(m.size + 1)
            need(len(b) == m.size and sha(b) == expected["files"][m.name], "ARCHIVE_FILE_HASH")
            files[m.name] = b
    need(set(files) == set(expected["files"]), "ARCHIVE_SET")
    make_tar(files)  # Enforce the independently fixed capture member allowlist as well.
    return files


def main():
    parser = argparse.ArgumentParser()
    for key in ("approval-id", "approval-sha256", "source-commit", "script-sha256"):
        parser.add_argument("--" + key, required=True, type=int if key == "approval-id" else str)
    parser.add_argument("--confirm-independent-auditor", action="store_true")
    args = parser.parse_args()
    need(os.geteuid() == 0 and os.uname().nodename == KOREA, "KOREA_ROOT_REQUIRED")
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, signal_hold)
    os.umask(0o077)
    source = stable_file(Path(__file__).absolute(), private=True)
    need(sha(source) == args.script_sha256, "EXECUTABLE_DIGEST")
    record, admitted = approval(args)
    private_directory(R2)
    point = json.loads(stable_file(R2 / "final-receipt.json", private=True))
    need(point["status"] == "CURRENT_OFFLINE_POINT_RECEIVED_PASS"
         and point["approval_comment_id"] == 6217030577 and point["source_files"] == 1363
         and point["database_sha256"] == DB_SHA and point["cipher_sha256"] == CIPHER_SHA,
         "ACCEPTED_R2_POINT_CHANGED")
    local_ports = listener_metadata()
    TARGET.mkdir(mode=0o700)  # One attempt consumes this new action, never the R2 approval.
    ssh = ["/usr/bin/ssh", "-T", "-S", str(TARGET / "ssh.sock"), "-o", "ControlMaster=auto",
           "-o", "ControlPersist=60", "-o", "UserKnownHostsFile=" + str(TARGET / "known_hosts"),
           "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
           "-o", "HostKeyAlgorithms=ecdsa-sha2-nistp256", "-o", "UpdateHostKeys=no",
           "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no", "-o", "ForwardX11=no",
           "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1"]
    remote = "root@47.245.53.152"
    step = 0
    def run_remote(cmd, out, data=None):
        nonlocal step
        step += 1
        ssh_step(ssh, remote, cmd, out, TARGET, step, data)
    def fetch(name, limit):
        need(name in ("receipt.json", "payload.enc", "payload.key"), "FETCH_NAME")
        code = "import json; ns={'__name__':'s06_private_capture'}; exec(" + repr(source.decode()) + ",ns); import sys; sys.stdout.buffer.write(ns['stable_file'](ns['SOURCE']/" + repr(name) + "," + str(limit) + ",private=True))"
        with (TARGET / name).open("xb") as out:
            run_remote("/usr/bin/python3.11 -I -B -", out, code.encode())
            out.flush(); os.fsync(out.fileno())
    try:
        write_new(TARGET / "approval.json", encoded(record))
        write_new(TARGET / "known_hosts", PUBLIC_KEY.encode())
        print("请输入东京root密码；本批只采集固定服务配置，不启动服务。", flush=True)
        subprocess.run(ssh + ["-n", "-o", "BatchMode=no", "-o", "NumberOfPasswordPrompts=1",
            remote, 'test "$(hostname -s)" = ' + TOKYO + ' && test "$(id -u)" = 0'], check=True, timeout=120)
        approval(args)
        code = ("ns={'__name__':'s06_private_capture'};exec(" + repr(source.decode())
                + ",ns);ns['signal'].signal(ns['signal'].SIGTERM,ns['signal_hold']);"
                  "ns['signal'].signal(ns['signal'].SIGHUP,ns['signal_hold']);ns['capture']("
                + str(admitted["expires_at"]) + ")")
        with (TARGET / "capture-private.log").open("xb") as log:
            run_remote("/usr/bin/python3.11 -I -B -", log, code.encode())
        fetch("receipt.json", 20000)
        expected = json.loads(stable_file(TARGET / "receipt.json", 20000, private=True))
        need(expected["status"] == "S06_PRIVATE_CONTRACT_PREPARED" and expected["host"] == TOKYO
             and expected["file_count"] == 12 and expected["unit_count"] == 10
             and 0 < expected["cipher_bytes"] <= MAX_TOTAL + 65536, "SOURCE_RECEIPT")
        fetch("payload.enc", MAX_TOTAL + 65536)
        fetch("payload.key", 65)
        need(re.fullmatch(b"[0-9a-f]{64}\n", stable_file(TARGET / "payload.key", 65, private=True)), "KEY_FORMAT")
        cipher = stable_file(TARGET / "payload.enc", MAX_TOTAL + 65536, private=True)
        need(len(cipher) == expected["cipher_bytes"] and sha(cipher) == expected["cipher_sha256"], "CIPHER_DIGEST")
        with (TARGET / "decrypt-private.log").open("xb") as log, (TARGET / "payload.tar.gz").open("xb") as out:
            r = subprocess.run(["/usr/bin/openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                "-iter", "200000", "-md", "sha256", "-in", str(TARGET / "payload.enc"),
                "-pass", "file:" + str(TARGET / "payload.key")], stdout=out, stderr=log, timeout=40)
            out.flush(); os.fsync(out.fileno())
        need(r.returncode == 0, "DECRYPT_FAILED")
        verify_archive(stable_file(TARGET / "payload.tar.gz", MAX_TOTAL + 65536, private=True), expected)
        # Leave verified material private. No extraction into /etc, no install, no subprocess from contents.
        result = {"status": "S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS", "approval_comment_id": args.approval_id,
                  "host": KOREA, "unit_files": 10, "dropin_files": 1, "private_metadata_files": 1,
                  "cipher_sha256": expected["cipher_sha256"], "archive_sha256": expected["archive_sha256"],
                  "korea_listener_metadata": local_ports, "service_actions": 0, "business_api_requests": 0,
                  "database_opened": False, "environment_files_opened": False, "credentials_used": False,
                  "unit_bytes_may_contain_inline_authentication": True,
                  "private_credentials_absence_proven": False, "production_deployed": False,
                  "runtime_secrets_transferred_from_environment_files": False, "retry_allowed": False,
                  "complete_service_config_closure": False, "tokyo_retirement": "HOLD"}
        write_new(TARGET / "final-receipt.json", encoded(result))
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as e:
        write_new(TARGET / "failure.json", encoded({"status": "HOLD_PRESERVE_EVIDENCE",
            "reason": str(e) if isinstance(e, Hold) else type(e).__name__, "retry_allowed": False}))
        print("HOLD_PRESERVE_EVIDENCE; PRIVATE_LOGS=" + str(TARGET), flush=True)
        raise
    finally:
        try:
            subprocess.run(ssh + ["-o", "BatchMode=yes", "-O", "exit", remote],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass


if __name__ == "__main__":
    main()
