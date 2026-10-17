#!/usr/bin/python3 -I
"""Build an exact legacy logging candidate in memory; never install or import it."""
import hashlib

SOURCE_SHA256 = "528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006"

OLD_METHOD = '''    def log_message(self, fmt, *args):
        path = urllib.parse.urlsplit(self.path).path
        sys.stderr.write("%s - - [%s] %s\\n" % (
            self.client_address[0],
            self.log_date_time_string(),
            fmt % args if "%s" not in fmt else fmt % tuple("[REDACTED]" for _ in args),
        ))
        sys.stderr.write("path=%s\\n" % path)
'''

NEW_METHOD = '''    def log_message(self, fmt, *args):
        try:
            path = urllib.parse.urlsplit(self.path).path
        except ValueError:
            path = "[INVALID_PATH]"
        safe_args = tuple(
            arg if type(arg) in (int, float) else "[REDACTED]" for arg in args
        )
        try:
            message = fmt % safe_args
        except (TypeError, ValueError, OverflowError):
            message = "[REDACTED]"
        sys.stderr.write("%s - - [%s] %s\\n" % (
            self.client_address[0],
            self.log_date_time_string(),
            message,
        ))
        sys.stderr.write("path=%s\\n" % path)
'''


def build_candidate(source):
    """Require exact server bytes and replace only the known logging method."""
    if not isinstance(source, bytes):
        raise TypeError("SOURCE_BYTES_REQUIRED")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("SOURCE_SHA256_MISMATCH")
    old, new = OLD_METHOD.encode(), NEW_METHOD.encode()
    if source.count(old) != 1:
        raise ValueError("EXACT_LOG_METHOD_REQUIRED")
    return source.replace(old, new, 1)

# Fixed production capability; main exposes no path, code, unit, or environment arguments.
import ast
import fcntl
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time

HOST = "iZ6wee8q9z4t03hvqumwfhZ"
SOURCE_UID = 1000
STATE_DIR = Path("/var/lib/xuanjun-pr122-portal-logfix-capability")
TARGET = Path("/opt/trading-system/scripts/secure_secrets_portal_server.py")
RULE = Path("/etc/sudoers.d/xuanjun-pr122-portal-logfix")
CANDIDATE_SHA256 = "d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0"
MODES = ("status", "apply", "rollback", "revoke")


def checked_read(path, uid, mode=None):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid:
            raise ValueError("FILE_IDENTITY_MISMATCH")
        if mode is not None and stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("FILE_MODE_MISMATCH")
        data = bytearray()
        while True:
            block = os.read(fd, 1048576)
            if not block:
                return bytes(data), info
            data.extend(block)
            if len(data) > 2000000:
                raise ValueError("FILE_SIZE_LIMIT")
    finally:
        os.close(fd)


def sync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data, uid=0, gid=0, mode=0o600):
    fd, temp = tempfile.mkstemp(prefix=".pr122-", dir=str(path.parent))
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fchown(handle.fileno(), uid, gid)
        os.fchmod(handle.fileno(), mode)
        os.fsync(handle.fileno())
    os.replace(temp, path)
    sync_dir(path.parent)


def restart_portal():
    subprocess.run(
        ["/usr/bin/systemctl", "restart", "secure-secrets-portal.service"],
        check=True, timeout=40, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
    )
    for attempt in range(20):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 18080, timeout=2)
            try:
                conn.request("GET", "/healthz", headers={"Connection": "close"})
                response = conn.getresponse()
                if response.status == 200 and response.read(100) == b"OK\n":
                    return
            finally:
                conn.close()
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.3)
    raise ValueError("PORTAL_STARTUP_HEALTH_FAILED")


def require_running():
    subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", "secure-secrets-portal.service"],
        check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
    )


def verify_live(expected_head):
    checks = []
    for address in ("47.245.53.152", "47.101.152.210"):
        for method, expected in (("GET", 200), ("HEAD", expected_head)):
            raw = socket.create_connection((address, 443), timeout=8)
            tls = ssl.create_default_context().wrap_socket(
                raw, server_hostname="wenwenwenyiyiyi.work")
            conn = http.client.HTTPConnection("wenwenwenyiyiyi.work", timeout=8)
            conn.sock = tls
            try:
                conn.request(method, "/healthz", headers={
                    "Host": "wenwenwenyiyiyi.work", "Connection": "close"})
                response = conn.getresponse()
                body = response.read(4096)
                if response.status != expected or (method == "GET" and body != b"OK\n"):
                    raise ValueError("LIVE_ACCEPTANCE_FAILED")
                checks.append({"address": address, "method": method, "status": response.status})
            finally:
                conn.close()
    return checks


class Capability:
    def __init__(self, root=STATE_DIR, source=TARGET, rule=RULE, restart=restart_portal,
                 verify=verify_live, preflight=require_running):
        self.root, self.source, self.rule = Path(root), Path(source), Path(rule)
        self.restart, self.verify = restart, verify
        self.preflight = preflight

    def load(self):
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("STATE_DIRECTORY_IDENTITY")
        data, _ = checked_read(self.root / "grant.json", 0, 0o600)
        self.grant = json.loads(data)
        self.record = {"status": "READY", "apply_started": False, "rollback_started": False}
        record = self.root / "receipt.json"
        if os.path.lexists(record):
            data, _ = checked_read(record, 0, 0o600)
            self.record = json.loads(data)

    def save(self):
        atomic_write(self.root / "receipt.json",
                     (json.dumps(self.record, sort_keys=True) + "\n").encode())

    def source_bytes(self):
        for parent in (self.source.parent.parent.parent, self.source.parent.parent,
                       self.source.parent):
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, SOURCE_UID) or info.st_mode & 0o022:
                raise ValueError("SOURCE_PARENT_IDENTITY")
        return checked_read(self.source, SOURCE_UID, 0o755)

    def run(self, mode):
        if mode not in MODES:
            raise ValueError("MODE_NOT_ALLOWED")
        self.load()
        if mode == "status":
            return dict(self.record, authority="PERSISTENT_FIXED_ACTIONS",
                        scope=self.grant["scope"], backup=str(self.root / "source.before.py"))
        if mode == "revoke":
            data, _ = checked_read(self.rule, 0, 0o440)
            if hashlib.sha256(data).hexdigest() != self.grant["sudoers_sha256"]:
                raise ValueError("SUDOERS_IDENTITY_MISMATCH")
            backup = self.root / "sudoers.revoked"
            if os.path.lexists(backup):
                raise ValueError("REVOKE_ALREADY_RECORDED")
            atomic_write(backup, data, mode=0o400)
            self.rule.unlink()
            sync_dir(self.rule.parent)
            self.record["authority_revoked"] = True
            self.save()
            return self.record
        source, info = self.source_bytes()
        if mode == "apply":
            if self.record["apply_started"]:
                raise ValueError("NO_BLIND_APPLY_RETRY")
            self.preflight()
            candidate = build_candidate(source)
            if hashlib.sha256(candidate).hexdigest() != CANDIDATE_SHA256:
                raise ValueError("CANDIDATE_HASH_MISMATCH")
            ast.parse(candidate)
            backup = self.root / "source.before.py"
            if os.path.lexists(backup):
                raise ValueError("BACKUP_ALREADY_EXISTS")
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(fd, "wb") as handle:
                handle.write(source)
                handle.flush()
                os.fsync(handle.fileno())
            sync_dir(self.root)
            self.record.update(apply_started=True, status="APPLY_STARTED",
                               original_uid=info.st_uid, original_gid=info.st_gid,
                               source_sha256=SOURCE_SHA256, candidate_sha256=CANDIDATE_SHA256)
            self.save()
            replacement, accepted_head = candidate, 501
        else:
            if not self.record["apply_started"] or self.record["rollback_started"]:
                raise ValueError("ROLLBACK_NOT_ALLOWED")
            if hashlib.sha256(source).hexdigest() != CANDIDATE_SHA256:
                raise ValueError("ROLLBACK_CURRENT_SOURCE_MISMATCH")
            replacement, _ = checked_read(self.root / "source.before.py", 0, 0o400)
            if hashlib.sha256(replacement).hexdigest() != SOURCE_SHA256:
                raise ValueError("ROLLBACK_BACKUP_HASH_MISMATCH")
            self.record.update(rollback_started=True, status="ROLLBACK_STARTED")
            self.save()
            accepted_head = 502  # Original logging defect is deliberately restored.
        try:
            current, current_info = self.source_bytes()
            if current != source or (current_info.st_dev, current_info.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError("CONCURRENT_SOURCE_CHANGE")
            atomic_write(self.source, replacement, info.st_uid, info.st_gid, 0o755)
            self.record["source_replaced_for"] = mode
            self.save()
            self.record["restart_attempted_for"] = mode
            self.save()
            self.restart()
            self.record["checks"] = self.verify(accepted_head)
            self.record["status"] = "LIVE_HEAD_GET_PASS" if mode == "apply" else "ROLLED_BACK"
            self.save()
            return self.record
        except BaseException as error:
            self.record.update(status="UNKNOWN_PRESERVE_EVIDENCE", error=type(error).__name__)
            self.save()
            raise


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        raise SystemExit("MODE_NOT_ALLOWED")
    if os.geteuid() != 0 or os.uname().nodename != HOST:
        raise SystemExit("ROOT_ON_APPROVED_TOKYO_REQUIRED")
    capability = Capability()
    capability.load()
    fd = os.open(STATE_DIR / "execution.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("LOCK_IDENTITY")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(capability.run(sys.argv[1]), sort_keys=True))
    except BaseException as error:
        print(json.dumps({"status": "HOLD", "reason": type(error).__name__,
                          "receipt": str(STATE_DIR / "receipt.json")}, sort_keys=True))
        raise SystemExit(1)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()

