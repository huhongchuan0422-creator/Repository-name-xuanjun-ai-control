#!/usr/bin/python3.11
"""Bounded offline recovery point. No application imports or service operations."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import signal
import sqlite3
import stat
import subprocess
import tarfile
import time

TOKYO = "iZ6wee8q9z4t03hvqumwfhZ"
KOREA = "iZmj7a5kwr75qc1tul4kf9Z"
REMOTE = Path("/root/pr99-current-point-v2")
LOCAL = Path("/root/pr99-current-point-received-v2")
SOURCE = Path("/opt/trading-system")
DATABASE = SOURCE / "database/data/trading.db"
DB_ID = (64771, 1601016, 1000)
ACTION = "PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1"
EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__",
            ".pytest_cache", "site-packages", "runtime", "logs", "backups",
            "secrets", "credentials", "config", "state", "data"}
MAX_TOTAL = 512 * 1024 * 1024
# Explicit source-scope exclusions: these five historical subtrees were not
# enumerated by UID1001. Do not copy their root-only contents or hide other drift.
EXCLUDED_SUBTREES = {
    "backup/WEBSITE_WECOM_AND_DUAL_CHANNEL_REFERRAL_COMPLETION_V1_20261008T003826/tokyo-system",
    "backup/XUANJUN_CUSTOMER_BRAIN_R10_FINAL_AUTHORITY_GAP_REPAIR_V1_20261007T225500",
    "backup/XUANJUN_WECOM_NOVEL_APP_IDENTITY_SECRET_READY_20261007T1818",
    "backup/gpt56_timeout_alignment_20261005T0115+0800",
    "backup/wecom_notification_gate_20261008_pre_audit_fix",
}

class Hold(RuntimeError):
    pass

def need(ok, reason):
    if not ok:
        raise Hold(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def hashfile(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()

def write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as f:
        os.fchmod(f.fileno(), mode)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def json_new(path, value):
    write_new(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())

def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def trusted(path, directory=False, private=False, owners=(0,)):
    info = path.lstat()
    need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
         and info.st_uid in owners and not info.st_mode & 0o022, "UNTRUSTED_PATH")
    need(directory or info.st_nlink == 1, "HARDLINK_REJECTED")
    if private:
        need(stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
             "PRIVATE_MODE")
    return info

def chain(path, owners=(0,)):
    for item in reversed(path.parents):
        trusted(item, directory=True, owners=owners)

def relative(name):
    p = PurePosixPath(name)
    need(bool(name) and not p.is_absolute() and ".." not in p.parts
         and str(p) == name and "\\" not in name and "\x00" not in name,
         "UNSAFE_RELATIVE_PATH")
    return Path(*p.parts)

def selected(rel):
    if any(rel.as_posix() == p or rel.as_posix().startswith(p+"/") for p in EXCLUDED_SUBTREES):
        return False
    if any(x.startswith(".") or x.lower() in EXCLUDED for x in rel.parts):
        return False
    leaf = rel.name
    return (leaf.endswith((".py", ".pyi", ".sql", ".sh"))
            or leaf in {"pyproject.toml", "setup.cfg", "Pipfile", "Pipfile.lock",
                        "poetry.lock", "uv.lock"}
            or leaf.endswith(".txt") and leaf.startswith(("requirements", "constraints")))

def manifest_rows(value):
    rows = value["files"]
    need(isinstance(rows, list) and 0 < len(rows) <= 10000, "SOURCE_COUNT")
    names = [r["path"] for r in rows]
    need(names == sorted(set(names)), "SOURCE_ORDER_OR_DUPLICATE")
    h, total = hashlib.sha256(), 0
    for r in rows:
        need(selected(relative(r["path"])), "UNAPPROVED_SOURCE_PATH")
        need(type(r["bytes"]) is int and 0 <= r["bytes"] <= 64*1024*1024,
             "SOURCE_SIZE")
        need(len(r["sha256"]) == 64 and all(c in "0123456789abcdef" for c in r["sha256"]),
             "SOURCE_DIGEST")
        total += r["bytes"]
        h.update((r["path"]+"\0"+r["sha256"]+"\0"+str(r["bytes"])+"\n").encode())
    need(total <= MAX_TOTAL and h.hexdigest() == value["source_aggregate_sha256"],
         "SOURCE_AGGREGATE")
    return rows

def catalog(root):
    names = []
    def inaccessible(error):
        raise Hold("SOURCE_WALK_INACCESSIBLE") from error
    for current, dirs, files in os.walk(root, followlinks=False, onerror=inaccessible):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                         and d.lower() not in EXCLUDED
                         and (Path(current)/d).relative_to(root).as_posix() not in EXCLUDED_SUBTREES)
        for d in dirs:
            trusted(Path(current)/d, directory=True, owners=(0, 1000))
        for f in files:
            rel = (Path(current)/f).relative_to(root)
            if selected(rel):
                names.append(rel.as_posix())
    return sorted(names)

def stable_bytes(path, expected, limit=64*1024*1024):
    chain(path, owners=(0, 1000))
    info = trusted(path, owners=(0, 1000))
    need(info.st_size == expected["bytes"] <= limit, "SOURCE_SIZE_DRIFT")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        data = f.read(limit+1)
        after = os.fstat(f.fileno())
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(fields(info) == fields(before) == fields(after) == fields(path.lstat()),
         "SOURCE_IDENTITY_DRIFT")
    need(len(data) == expected["bytes"] and sha(data) == expected["sha256"],
         "SOURCE_BYTES_DRIFT")
    return data

def sqlite_check(path, seconds=60):
    deadline = time.monotonic()+seconds
    c = sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)
    try:
        c.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        c.execute("PRAGMA query_only=ON")
        need(c.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
             "COPY_SQLITE_INTEGRITY")
    finally:
        c.close()

def backup_database(source, target, expected_identity, seconds=90):
    chain(source, owners=(0, 1000))
    before = trusted(source, owners=(0, 1000))
    identity = lambda s: (s.st_dev, s.st_ino, s.st_uid)
    need(identity(before) == tuple(expected_identity), "DATABASE_IDENTITY_DRIFT")
    need(0 < before.st_size <= MAX_TOTAL, "DATABASE_SIZE_LIMIT")
    for suffix in ("-wal", "-shm"):
        side = Path(str(source)+suffix)
        if os.path.lexists(side):
            trusted(side, owners=(0, 1000))
    need(not os.path.lexists(target), "BACKUP_EXISTS")
    started, deadline = time.time(), time.monotonic()+seconds
    # mode=ro, not immutable: committed WAL pages must be included by SQLite.
    src = sqlite3.connect(source.resolve().as_uri()+"?mode=ro", uri=True, timeout=3)
    dst = None
    def progress(status, remaining, total):
        need(time.monotonic() < deadline, "BACKUP_DEADLINE")
        need(target.stat().st_size <= MAX_TOTAL, "BACKUP_SIZE_LIMIT")
    try:
        src.execute("PRAGMA query_only=ON")
        write_new(target, b"")
        dst = sqlite3.connect(target, timeout=3)
        src.backup(dst, pages=256, progress=progress, sleep=0.05)
        dst.commit()
        # Only the NEW COPY is normalized. No live checkpoint or journal change.
        need(dst.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",),
             "COPY_JOURNAL_MODE")
    finally:
        if dst is not None:
            dst.close()
        src.close()
    need(identity(source.lstat()) == tuple(expected_identity), "DATABASE_REPLACED")
    need(not any(os.path.lexists(str(target)+s) for s in ("-wal", "-shm", "-journal")),
         "COPY_NOT_CLOSED")
    sqlite_check(target)
    os.chmod(target, 0o400)
    with target.open("rb") as f:
        os.fsync(f.fileno())
    return {"started_epoch": started, "finished_epoch": time.time(),
            "sha256": hashfile(target), "bytes": target.stat().st_size,
            "integrity_check": "PASS", "wal_aware_backup": True,
            "cross_file_atomic": False, "writer_frozen": False,
            "exchange_reconciled": False, "final_trading_checkpoint": False}

def collect_sources(root, payload, value):
    rows = manifest_rows(value)
    names = [r["path"] for r in rows]
    need(catalog(root) == names, "SOURCE_FILE_SET_DRIFT")
    for row in rows:
        target = payload/"code"/relative(row["path"])
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        write_new(target, stable_bytes(root/relative(row["path"]), row), 0o400)
    need(catalog(root) == names, "SOURCE_FILE_SET_DRIFT")
    # Re-read hashes after collecting to reject observed concurrent source drift.
    for row in rows:
        stable_bytes(root/relative(row["path"]), row)
    return rows

def make_archive(payload, rows, database, work):
    records = [{"path": "code/"+r["path"], "bytes": r["bytes"],
                "sha256": r["sha256"]} for r in rows]
    records.append({"path": "database/trading.db", "bytes": database["bytes"],
                    "sha256": database["sha256"]})
    value = {"schema_version": 1, "scope": "CURRENT_OFFLINE_RECOVERY_POINT_NOT_CUTOVER",
             "files": records, "database": database}
    json_new(payload/"manifest.json", value)
    archive = work/"payload.tar.gz"
    with archive.open("xb") as raw:
        os.fchmod(raw.fileno(), 0o600)
        with tarfile.open(fileobj=raw, mode="w:gz") as t:
            for row in records:
                p = payload/relative(row["path"])
                need(hashfile(p) == row["sha256"], "PAYLOAD_DRIFT")
                t.add(p, arcname=row["path"], recursive=False)
            t.add(payload/"manifest.json", arcname="manifest.json", recursive=False)
        raw.flush()
        os.fsync(raw.fileno())
    key = work/"payload.key"
    write_new(key, (os.urandom(32).hex()+"\n").encode())
    write_new(work/"payload.enc", b"")
    with (work/"openssl-private.log").open("xb") as log, (work/"payload.enc").open("wb") as cipher:
        r = subprocess.run(["/usr/bin/openssl", "enc", "-aes-256-cbc", "-salt",
                            "-pbkdf2", "-iter", "200000", "-md", "sha256",
                            "-in", str(archive), "-pass", "file:"+str(key)],
                           stdout=cipher, stderr=log, timeout=120)
        cipher.flush()
        os.fsync(cipher.fileno())
    need(r.returncode == 0, "ENCRYPT_FAILED")
    trusted(work/"payload.enc", private=True)
    return {"cipher_sha256": hashfile(work/"payload.enc"),
            "cipher_bytes": (work/"payload.enc").stat().st_size,
            "plaintext_tar_sha256": hashfile(archive),
            "manifest_sha256": hashfile(payload/"manifest.json"),
            "database": database, "source_files": len(rows)}

def prepare(work, manifest):
    need(os.geteuid() == 0 and os.uname().nodename == TOKYO and work == REMOTE,
         "TOKYO_ROOT_FIXED_PATH_REQUIRED")
    os.umask(0o077)
    trusted(work, directory=True, private=True)
    import shutil
    need(shutil.disk_usage(work).free >= 1536*1024*1024, "TOKYO_FREE_DISK")
    need(not os.path.lexists(work/"prepare.started"), "ATTEMPT_EXISTS_NO_RETRY")
    write_new(work/"prepare.started", b"single action; preserve all failures\n")
    try:
        payload = work/"payload"
        payload.mkdir(mode=0o700)
        rows = collect_sources(SOURCE, payload, manifest)
        (payload/"database").mkdir(mode=0o700)
        db = backup_database(DATABASE, payload/"database/trading.db", DB_ID)
        # Source identities must still match the approved server manifest after DB copy.
        need(catalog(SOURCE) == [r["path"] for r in rows], "SOURCE_FILE_SET_DRIFT")
        for row in rows:
            stable_bytes(SOURCE/relative(row["path"]), row)
        result = make_archive(payload, rows, db, work)
        result.update({"status": "CURRENT_OFFLINE_POINT_PREPARED", "action": ACTION,
                       "host": TOKYO, "source_aggregate_sha256": manifest["source_aggregate_sha256"],
                       "service_actions": 0, "api_requests": 0,
                       "api_configuration_deployed": False, "production_deployed": False,
                       "source_tree_atomic": False, "retry_allowed": False})
        json_new(work/"receipt.json", result)
        fsync_dir(work)
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as e:
        json_new(work/"failure.json", {"status": "HOLD_PRESERVE_EVIDENCE",
                 "reason": str(e) if isinstance(e, Hold) else type(e).__name__,
                 "retry_allowed": False})
        raise

def receive_archive(archive_path, destination, expected, source_manifest):
    need(hashfile(archive_path) == expected["plaintext_tar_sha256"], "PLAINTEXT_HASH")
    rows = manifest_rows(source_manifest)
    approved = {"code/"+r["path"]: r for r in rows}
    approved["database/trading.db"] = expected["database"]
    need(not os.path.lexists(destination), "RECEIVE_EXISTS_NO_RETRY")
    destination.mkdir(mode=0o700)
    seen, manifest_data, total = set(), None, 0
    with tarfile.open(archive_path, "r:gz") as t:
        for m in t:
            relative(m.name)
            need(m.isfile() and m.name not in seen and m.name in set(approved)|{"manifest.json"},
                 "ARCHIVE_MEMBER_REJECTED")
            seen.add(m.name)
            limit = 2*1024*1024 if m.name == "manifest.json" else approved[m.name]["bytes"]
            need(0 <= m.size <= limit, "ARCHIVE_SIZE")
            total += m.size
            need(total <= MAX_TOTAL*2+2*1024*1024, "ARCHIVE_TOTAL")
            f = t.extractfile(m)
            need(f is not None, "ARCHIVE_STREAM")
            target = destination/relative(m.name)
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if m.name == "manifest.json":
                with f:
                    data = f.read(limit+1)
                need(len(data) == m.size, "ARCHIVE_TRUNCATED")
                need(sha(data) == expected["manifest_sha256"], "MANIFEST_HASH")
                manifest_data = json.loads(data)
                write_new(target, data, 0o400)
            else:
                h, size = hashlib.sha256(), 0
                fd = os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o400)
                with f, os.fdopen(fd, "wb") as out:
                    os.fchmod(out.fileno(), 0o400)
                    for data in iter(lambda: f.read(1048576), b""):
                        size += len(data)
                        need(size <= limit, "RECEIVED_SIZE")
                        h.update(data); out.write(data)
                    need(size == m.size == approved[m.name]["bytes"]
                         and h.hexdigest() == approved[m.name]["sha256"], "RECEIVED_BYTES")
                    out.flush(); os.fsync(out.fileno())
    need(seen == set(approved)|{"manifest.json"} and manifest_data is not None,
         "RECEIVED_FILE_SET")
    need({r["path"]: (r["bytes"], r["sha256"]) for r in manifest_data["files"]}
         == {p: (r["bytes"], r["sha256"]) for p, r in approved.items()}, "MANIFEST_FILES")
    sqlite_check(destination/"database/trading.db")
    need(hashfile(destination/"database/trading.db") == expected["database"]["sha256"],
         "RECEIVED_DATABASE_DRIFT")
    fsync_dir(destination)
    return {"status": "CURRENT_OFFLINE_POINT_RECEIVED_PASS", "source_files": len(rows),
            "database_sha256": expected["database"]["sha256"],
            "database_integrity_check": "PASS", "source_manifest_matched": True,
            "production_deployed": False, "service_actions": 0, "api_requests": 0,
            "current_final_trading_snapshot": False, "tokyo_retirement": "HOLD"}
