"""Single-use, Owner-root admitted repair of the installed offline Phase-B unit.

No provider import, credentials, business DB, service start or runtime replacement.
The Python API accepts a disposable model adapter; the CLI exposes no test bypass.
"""
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
import sys
import tarfile
import tempfile
import time

HOST = "iZmj7a5kwr75qc1tul4kf9Z"
ACTION = "PR99_PHASE_B_OFFLINE_UNIT_REPAIR_V1"
OLD_TX = "c79182446ab8c2e447cb6942061710fb4a864addb4b9718f967402ef8c30cfe2"
OLD_MANIFEST = "f887b085508e3ed4831dbed22152e35af5e8aba95b85b899b4697c61449917de"
OLD_UNIT = "f725c84e321065a3a14d0680abef96e654f3a482d6fe807bfe01998e07672bdb"
RELEASE = "/opt/xuanjun-binance/releases/f887b085508e3ed4"
UNIT = "/etc/systemd/system/xuanjun-binance-shadow.service"
TX = "/etc/xuanjun-binance/install-transaction.json"
CURRENT = "/opt/xuanjun-binance/current"
WORK = "/var/lib/xuanjun-pr99-offline-repair-v1"
PIN = "/etc/xuanjun-pr99-release/offline-repair-admission.json"
SHARED = ("morelogin-socks5-permanent.service", "xuanjun-novel-factory.service",
          "postgresql.service", "redis.service", "yibi-api.service", "yibi-scheduler.service")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}


class Hold(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Context:
    """Production context uses only fixed absolute programs and root paths."""
    uid = 0
    old_tx_sha = OLD_TX
    trust_root = Path("/")

    def path(self, value):
        return Path(value)

    def run(self, args):
        return subprocess.run(args, capture_output=True, text=True, timeout=30, env=ENV)

    def boundary(self):
        parent = os.stat("/proc/self/ns/net").st_ino
        code = ('import os,socket,json;print(json.dumps({'
                '"ns":os.stat("/proc/self/ns/net").st_ino,'
                '"interfaces":socket.if_nameindex()}))')
        r = self.run(["/usr/bin/unshare", "--net", "--", "/usr/bin/python3.11", "-I", "-c", code])
        require(r.returncode == 0, "NETNS_UNAVAILABLE")
        v = json.loads(r.stdout)
        require(v["ns"] != parent and [x[1] for x in v["interfaces"]] == ["lo"], "NETNS_NOT_ISOLATED")

    def checkpoint(self, name):
        pass


def trusted(path, ctx, directory=False, private=False):
    """Reject links and writable intermediate directories before reading bytes."""
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "PATH_INVALID")
    require(path == ctx.trust_root or ctx.trust_root in path.parents, "OUTSIDE_TRUST_ROOT")
    for parent in reversed(path.parents):
        if parent != ctx.trust_root and ctx.trust_root not in parent.parents:
            continue
        s = parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == ctx.uid and not s.st_mode & 0o022,
                "UNTRUSTED_PARENT")
    s = path.lstat()
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode), "UNTRUSTED_TYPE")
    require(s.st_uid == ctx.uid and not s.st_mode & 0o022, "UNTRUSTED_OWNER_MODE")
    if private:
        require(stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600), "PRIVATE_MODE_REQUIRED")
    require(directory or s.st_size <= 10000000, "FILE_TOO_LARGE")
    return s


def read(path, ctx, private=False):
    trusted(path, ctx, private=private)
    return Path(path).read_bytes()


def absent(path):
    return not os.path.lexists(path)


def atomic(path, data, mode, ctx, expected=None):
    path = Path(path)
    trusted(path.parent, ctx, directory=True)
    if expected is not None:
        require(read(path, ctx) == expected, "ATOMIC_TARGET_CHANGED")
    else:
        require(absent(path), "ATOMIC_TARGET_EXISTS")
    fd, temp = tempfile.mkstemp(prefix=".pr99-offline-", dir=str(path.parent))
    # A failure preserves the temporary file too; no broad cleanup is allowed.
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fchmod(f.fileno(), mode)
        os.fsync(f.fileno())
    if expected is not None:
        require(read(path, ctx) == expected, "ATOMIC_TARGET_CHANGED")
    else:
        require(absent(path), "ATOMIC_TARGET_EXISTS")
    os.replace(temp, path)
    sync_directory(path.parent)


def package_files(folder, archive, ctx):
    trusted(folder, ctx, directory=True, private=True)
    raw = read(archive, ctx, private=True)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
        for m in t.getmembers():
            p = PurePosixPath(m.name)
            require(m.isfile() and p.as_posix() == m.name and not p.is_absolute()
                    and ".." not in p.parts and m.name not in files and m.size <= 2000000,
                    "ARCHIVE_MEMBER_INVALID")
            files[m.name] = t.extractfile(m).read()
    binding = json.loads(files["REPAIR_BINDING.json"])
    require(binding["schema_version"] == 1 and re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"]),
            "BINDING_INVALID")
    require(set(files) == set(binding["files"]) | {"REPAIR_BINDING.json"}, "PACKAGE_FILE_SET")
    require(set(x.name for x in folder.iterdir()) == set(files), "EXTRACTED_FILE_SET")
    for name, digest in binding["files"].items():
        require("/" not in name and sha(files[name]) == digest, "PACKAGE_HASH_MISMATCH")
    for name, data in files.items():
        require(read(folder / name, ctx) == data, "EXTRACTED_BYTES_MISMATCH")
    require(sha(files["installed-runtime-manifest.json"]) == OLD_MANIFEST, "OLD_MANIFEST_BINDING")
    return binding, files, sha(raw)


def admission(ctx, binding, files, archive_sha):
    pin_path = ctx.path(PIN)
    trusted(pin_path.parent, ctx, directory=True, private=True)
    pin = json.loads(read(pin_path, ctx, private=True))
    body = pin["approval_body"]
    require(sha(body.encode()) == pin["approval_body_sha256"], "APPROVAL_BODY_HASH")
    start, end = "<!-- PR99_OFFLINE_REPAIR_APPROVAL_V1\n", "\nPR99_OFFLINE_REPAIR_APPROVAL_V1 -->"
    require(body.count(start) == 1 and body.count(end) == 1, "APPROVAL_MARKER")
    a = json.loads(body.split(start)[1].split(end)[0])
    expected = {"schema_version": 1, "action": ACTION, "host": HOST, "max_attempts": 1,
                "source_commit": binding["source_commit"], "artifact_sha256": archive_sha,
                "helper_sha256": sha(files["controlled_repair.py"]),
                "unit_sha256": sha(files["offline.service"]), "old_transaction_sha256": ctx.old_tx_sha,
                "service_start_allowed": False, "phase_c_allowed": False}
    require(set(a) == set(expected) | {"approval_comment_id", "issued_at", "expires_at"}, "APPROVAL_FIELDS")
    for key, value in expected.items():
        require(type(a[key]) is type(value) and a[key] == value, "APPROVAL_SCOPE_MISMATCH")
    require(type(a["approval_comment_id"]) is int and a["approval_comment_id"] == pin["approval_comment_id"]
            and a["approval_comment_id"] not in (6207630392, 6207782855), "OLD_OR_WRONG_APPROVAL")
    require(type(a["issued_at"]) is int and type(a["expires_at"]) is int
            and a["issued_at"] <= time.time() < a["expires_at"]
            and 0 < a["expires_at"] - a["issued_at"] <= 43200, "APPROVAL_EXPIRED")
    return a


def service(ctx, repaired):
    r = ctx.run(["/usr/bin/systemctl", "is-enabled", "xuanjun-binance-shadow.service"])
    require(r.returncode == 1 and r.stdout.strip() == "disabled", "SERVICE_NOT_DISABLED")
    r = ctx.run(["/usr/bin/systemctl", "show", "xuanjun-binance-shadow.service",
                 "-p", "ActiveState", "-p", "SubState", "-p", "MainPID", "-p", "FragmentPath",
                 "-p", "DropInPaths", "-p", "User", "-p", "Group", "-p", "PrivateNetwork",
                 "-p", "RestrictAddressFamilies", "--no-pager"])
    require(r.returncode == 0, "SERVICE_SHOW_FAILED")
    v = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    for k, val in {"ActiveState": "inactive", "SubState": "dead", "MainPID": "0",
                   "FragmentPath": str(ctx.path(UNIT)), "DropInPaths": "",
                   "User": "xuanjun_binance", "Group": "xuanjun_binance"}.items():
        require(v.get(k) == val, "SERVICE_IDENTITY_OR_STATE")
    if repaired:
        require(v.get("PrivateNetwork") == "yes" and v.get("RestrictAddressFamilies") == "AF_UNIX",
                "MANAGER_NETWORK_PROFILE_NOT_LOADED")


def shared(ctx):
    r = ctx.run(["/usr/bin/systemctl", "show", *SHARED, "-p", "Id", "-p", "LoadState",
                 "-p", "ActiveState", "-p", "SubState", "-p", "MainPID", "--no-pager"])
    require(r.returncode in (0, 1) and all("Id=" + name in r.stdout for name in SHARED), "SHARED_METADATA_UNAVAILABLE")
    return encoded({"exit": r.returncode, "metadata": r.stdout})


def runtime(ctx, files):
    s = ctx.path(CURRENT).lstat()
    require(stat.S_ISLNK(s.st_mode) and s.st_uid == ctx.uid, "CURRENT_LINK_IDENTITY")
    require(os.readlink(ctx.path(CURRENT)) == RELEASE, "CURRENT_CHANGED")
    trusted(ctx.path(RELEASE), ctx, directory=True)
    require(read(ctx.path(RELEASE) / "minimal-runtime-manifest.json", ctx) == files["installed-runtime-manifest.json"],
            "INSTALLED_MANIFEST_CHANGED")
    manifest = json.loads(files["installed-runtime-manifest.json"])
    expected = {"minimal-runtime-manifest.json"}
    for row in manifest["files"]:
        name = row["path"]
        require(sha(read(ctx.path(RELEASE) / name, ctx)) == row["sha256"], "RUNTIME_BYTES_CHANGED")
        expected.add(name)
    actual = set()
    for p in ctx.path(RELEASE).rglob("*"):
        require(not p.is_symlink(), "RUNTIME_LINK")
        if p.is_file():
            actual.add(p.relative_to(ctx.path(RELEASE)).as_posix())
    require(actual == expected, "RUNTIME_FILE_SET_CHANGED")
    return manifest


def verify(ctx, unit):
    r = ctx.run(["/usr/bin/systemd-analyze", "verify", str(unit)])
    require(r.returncode == 0 and not r.stdout.strip() and not r.stderr.strip(), "SYSTEMD_VERIFY_DIAGNOSTIC")


def apply(folder, archive, ctx):
    binding, files, archive_sha = package_files(folder, archive, ctx)
    a = admission(ctx, binding, files, archive_sha)  # precedes every persistent change
    require(absent(ctx.path(WORK)), "ATTEMPT_ALREADY_EXISTS_NO_RETRY")
    require(absent(ctx.path("/run/xuanjun-binance-install.lock")), "ORIGINAL_INSTALL_LOCK_EXISTS")
    trusted(ctx.path("/var/lib"), ctx, directory=True)
    # Share the original installer lock name. O_EXCL directory creation prevents
    # both an old installer and a second repair from entering concurrently.
    lock = ctx.path("/run/xuanjun-binance-install.lock")
    trusted(lock.parent, ctx, directory=True)
    lock.mkdir(mode=0o700)
    sync_directory(lock.parent)
    lock_identity = (lock.stat().st_dev, lock.stat().st_ino)
    # Lock stays on any failure. No stale-lock deletion or automatic rollback.
    work = ctx.path(WORK)
    work.mkdir(mode=0o700)
    sync_directory(work.parent)
    receipt = {"schema_version": 1, "action": ACTION, "host": HOST,
               "approval_comment_id": a["approval_comment_id"], "source_commit": binding["source_commit"],
               "artifact_sha256": archive_sha, "status": "STARTED_PRESERVE_EVIDENCE",
               "phase": "preflight", "service_started": False, "runtime_changed": False,
               "credentials_read": False, "binance_called": False, "automatic_retry_allowed": False}
    receipt_path = work / "receipt.json"
    atomic(receipt_path, encoded(receipt), 0o600, ctx)
    try:
        service(ctx, False)
        old_tx = read(ctx.path(TX), ctx, private=True)
        require(sha(old_tx) == ctx.old_tx_sha, "OLD_TRANSACTION_CHANGED")
        tx = json.loads(old_tx)
        for k, val in {"schema_version": 1, "transaction_id": "install-f887b085508e3ed4",
                       "manifest_sha256": OLD_MANIFEST, "release_path": RELEASE, "current_target": RELEASE,
                       "unit_path": UNIT, "venv_path": "/opt/xuanjun-binance/venv", "unit_sha256": OLD_UNIT}.items():
            require(tx.get(k) == val, "OLD_TRANSACTION_FIELDS")
        old_unit = read(ctx.path(UNIT), ctx)
        require(sha(old_unit) == OLD_UNIT, "OLD_UNIT_CHANGED")
        trusted(ctx.path("/opt/xuanjun-binance/venv"), ctx, directory=True)
        python = ctx.path("/opt/xuanjun-binance/venv/bin/python").resolve(strict=True)
        require(sha(read(python, ctx)) == tx["venv_python_sha256"], "VENV_PYTHON_CHANGED")
        runtime(ctx, files)
        before = shared(ctx)
        ctx.boundary()  # only a short unshare child; no service or packet
        # Verify a synthetic copy before changing the real unit. The exact
        # installed copy is verified again before daemon-reload.
        probe = work / "pr99-offline-probe.service"
        new_unit = files["offline.service"]
        require(b"PrivateNetwork=yes\n" in new_unit and b"RestrictAddressFamilies=AF_UNIX\n" in new_unit,
                "OFFLINE_UNIT_INVALID")
        require(not any(x in new_unit for x in (b"LoadCredential", b"IPAddress", b"EnvironmentFile", b"--continuous")),
                "ONLINE_OR_UNSUPPORTED_UNIT")
        synthetic = re.sub(br"(?m)^ExecStart=.*$", b"ExecStart=/bin/true", new_unit)
        atomic(probe, synthetic, 0o600, ctx)
        verify(ctx, probe)
        for name, data in (("unit.before", old_unit), ("transaction.before.json", old_tx), ("shared.before.json", before)):
            atomic(work / name, data, 0o600, ctx)
        ctx.checkpoint("before_replace")
        require(time.time() < a["expires_at"], "APPROVAL_EXPIRED_BEFORE_REPLACE")
        service(ctx, False)
        require(read(ctx.path(TX), ctx, private=True) == old_tx, "TRANSACTION_CONCURRENT_CHANGE")
        receipt["phase"] = "replace_unit"
        atomic(receipt_path, encoded(receipt), 0o600, ctx, receipt_path.read_bytes())
        atomic(ctx.path(UNIT), new_unit, 0o644, ctx, old_unit)
        ctx.checkpoint("after_unit")
        verify(ctx, ctx.path(UNIT))
        new_tx = dict(tx, unit_sha256=sha(new_unit))  # only this field changes
        atomic(ctx.path(TX), encoded(new_tx), 0o600, ctx, old_tx)
        ctx.checkpoint("after_transaction")
        r = ctx.run(["/usr/bin/systemctl", "daemon-reload"])
        require(r.returncode == 0, "DAEMON_RELOAD_FAILED")
        service(ctx, True)
        runtime(ctx, files)
        require(sha(read(python, ctx)) == tx["venv_python_sha256"], "VENV_PYTHON_CHANGED")
        require(read(ctx.path(UNIT), ctx) == new_unit, "FINAL_UNIT_CHANGED")
        require(read(ctx.path(TX), ctx, private=True) == encoded(new_tx), "FINAL_TRANSACTION_CHANGED")
        require(shared(ctx) == before, "SHARED_NAMED_UNITS_CHANGED")
        atomic(work / "transaction.after.json", encoded(new_tx), 0o600, ctx)
        ctx.checkpoint("before_unlock")
        s = lock.lstat()
        require(stat.S_ISDIR(s.st_mode) and (s.st_dev, s.st_ino) == lock_identity, "LOCK_IDENTITY_CHANGED")
        lock.rmdir()  # lock release must succeed before PASS
        sync_directory(lock.parent)
        receipt.update(status="OFFLINE_REPAIR_PASS_WITH_SCOPE_LIMITS", phase="complete",
                       unit_sha256=sha(new_unit), transaction_sha256=sha(encoded(new_tx)),
                       runtime_manifest_sha256=OLD_MANIFEST, lock_released=True,
                       manager_private_network="yes", netns_child="ONLY_LO_PASS",
                       started_service_confinement="NOT_EXERCISED", phase_c="NOT_AUTHORIZED")
        atomic(receipt_path, encoded(receipt), 0o600, ctx, receipt_path.read_bytes())
    except BaseException as e:
        receipt.update(status="HOLD_PRESERVE_EVIDENCE", error=str(e) if isinstance(e, Hold) else type(e).__name__)
        atomic(receipt_path, encoded(receipt), 0o600, ctx, receipt_path.read_bytes())
        raise
    return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True, type=Path)
    p.add_argument("--archive", required=True, type=Path)
    args = p.parse_args()
    try:
        require(os.geteuid() == 0 and os.uname().nodename == HOST, "WRONG_ROOT_OR_HOST")
        require(not any(k.startswith(("KOREA_", "PYTHON")) for k in os.environ), "UNCLEAN_EXECUTION_ENVIRONMENT")
        require(Path(__file__).resolve() == args.package / "controlled_repair.py", "HELPER_PACKAGE_PATH")
        os.umask(0o077)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Hold("SIGTERM")))
        print(json.dumps(apply(args.package, args.archive, Context()), sort_keys=True))
    except BaseException as e:
        print(json.dumps({"status": "HOLD_PRESERVE_EVIDENCE", "reason": str(e) if isinstance(e, Hold) else type(e).__name__,
                          "retry_allowed": False}), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
