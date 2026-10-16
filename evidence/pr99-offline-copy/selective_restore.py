#!/usr/bin/python3.11
"""Fixed historical-baseline recovery to one new private directory, never deployment."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import subprocess
import time
import tarfile

BASE = Path("/root/xuanjun-offline-baseline-20261016")
WORK = Path("/root/xuanjun-offline-selected-20261016")
CIPHER_SHA = "ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093"
PLAIN_SHA = "1784372b17b3466ad4de946e03fc1a1866abccdab791fc871db08b827757154a"
DB_SHA = "d0bb23c5cede3a66567373b92221b058aa18e07aa510daf0bc02f8f4770bd0a5"
EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__",
            ".pytest_cache", "site-packages", "runtime", "logs", "backups",
            "secrets", "credentials", "config", "state", "data"}

def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()

def private_json(path, value):
    with path.open("x") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(value, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())

def source_parts(name):
    need("\x00" not in name and "\\" not in name, "UNSAFE_ARCHIVE_NAME")
    p = PurePosixPath(name)
    need(not p.is_absolute() and ".." not in p.parts, "UNSAFE_ARCHIVE_PATH")
    return tuple(x for x in p.parts if x not in (".", ""))

def choose(parts):
    if parts[:2] == ("opt", "trading-system") and len(parts) > 2:
        rel = parts[2:]
        if any(x.lower() in EXCLUDED or x.startswith(".") for x in rel):
            return None
        leaf = rel[-1]
        dependency = (leaf in {"pyproject.toml", "setup.cfg", "Pipfile", "Pipfile.lock",
                              "poetry.lock", "uv.lock"}
                      or (leaf.endswith(".txt") and leaf.startswith(("requirements", "constraints"))))
        if dependency or leaf.endswith((".py", ".pyi", ".sql", ".sh")):
            return ("code", Path(*rel), dependency)
    if parts[:2] == ("root", "xj-db-backup.cea2af8k") and len(parts) > 2:
        leaf = parts[-1].lower()
        if "trading" in leaf and leaf.endswith((".db", ".sqlite", ".sqlite3", ".backup")):
            return ("database", Path(*parts[2:]), False)
    return None

def copy_member(archive, member, target):
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    h = hashlib.sha256()
    count = 0
    stream = archive.extractfile(member)
    need(stream is not None, "MEMBER_STREAM_MISSING")
    with stream, target.open("xb") as out:
        os.fchmod(out.fileno(), 0o600)
        for block in iter(lambda: stream.read(1048576), b""):
            count += len(block)
            need(count <= member.size, "MEMBER_SIZE_CHANGED")
            out.write(block)
            h.update(block)
        need(count == member.size, "MEMBER_TRUNCATED")
        out.flush()
        os.fsync(out.fileno())
    return h.hexdigest(), count

class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.hash = hashlib.sha256()
    def read(self, size=-1):
        value = self.stream.read(size)
        self.hash.update(value)
        return value

def recover_stream(stream, work, expected_plain_sha, expected_db_sha):
    # Caller supplies an exclusive private directory. No tar extraction API or imports.
    reader = HashingReader(stream)
    rows, seen, total, dependencies, matched_db = [], set(), 0, 0, []
    started = time.monotonic()
    with tarfile.open(fileobj=reader, mode="r|gz") as archive:
        count = 0
        for member in archive:
            count += 1
            need(count <= 200000 and time.monotonic() - started < 900, "ARCHIVE_BUDGET")
            parts = source_parts(member.name)
            selected = choose(parts)
            if selected is None or member.isdir():
                continue
            need(member.isfile(), "SELECTED_MEMBER_LINK_OR_SPECIAL_REJECTED")
            kind, rel, dependency = selected
            identity = "/".join(parts)
            need(identity not in seen, "DUPLICATE_SELECTED_MEMBER")
            seen.add(identity)
            limit = 512 * 1024 * 1024 if kind == "database" else 64 * 1024 * 1024
            need(0 <= member.size <= limit, "SELECTED_MEMBER_SIZE_LIMIT")
            total += member.size
            need(total <= 1024 * 1024 * 1024, "RECOVERY_SIZE_LIMIT")
            target = work / ("code" if kind == "code" else "database-candidates") / rel
            sha, size = copy_member(archive, member, target)
            rows.append({"source": identity, "path": str(target.relative_to(work)),
                         "sha256": sha, "bytes": size, "kind": kind})
            dependencies += int(dependency)
            if kind == "database" and sha == expected_db_sha:
                matched_db.append(target)
    # tarfile may finish before the encrypted stream: include all trailing bytes.
    for block in iter(lambda: reader.read(1048576), b""):
        need(time.monotonic() - started < 900, "DRAIN_DEADLINE")
    need(reader.hash.hexdigest() == expected_plain_sha, "PLAINTEXT_ARCHIVE_HASH_MISMATCH")
    code_count = sum(r["kind"] == "code" for r in rows)
    need(code_count > 0 and dependencies > 0, "SOURCE_OR_DEPENDENCIES_MISSING")
    need(len(matched_db) == 1, "EXACT_HISTORICAL_TRADING_BACKUP_NOT_UNIQUE")
    need(sum(r["kind"] == "database" for r in rows) == 1, "UNEXPECTED_TRADING_BACKUP_CANDIDATE")
    db = matched_db[0]
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        need(connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
             "SQLITE_INTEGRITY_FAILED")
    finally:
        connection.close()
    need(digest_file(db) == expected_db_sha, "DATABASE_CHANGED_DURING_CHECK")
    for row in rows:
        target = work / row["path"]
        need(digest_file(target) == row["sha256"], "RESTORED_FILE_CHANGED")
        target.chmod(0o400)
    private_json(work / "private-file-manifest.json", {"schema_version": 1, "files": rows})
    return {"files": len(rows), "source_files": code_count,
            "dependency_manifests": dependencies, "selected_bytes": total,
            "database_sha256": expected_db_sha,
            "private_manifest_sha256": digest_file(work / "private-file-manifest.json")}

def trusted_file(path, size=None):
    s = path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1
         and stat.S_IMODE(s.st_mode) == 0o600, "PRIVATE_INPUT_IDENTITY")
    need(size is None or s.st_size == size, "PRIVATE_INPUT_SIZE")

def main():
    need(os.geteuid() == 0 and os.uname().nodename == "iZmj7a5kwr75qc1tul4kf9Z",
         "KOREA_ROOT_REQUIRED")
    os.umask(0o077)
    for p in (Path("/"), Path("/root"), BASE):
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             "UNTRUSTED_PARENT")
    need(stat.S_IMODE(BASE.lstat().st_mode) == 0o700, "PRIVATE_BASE_REQUIRED")
    cipher, key = BASE / "recovery-baseline.tar.gz.enc", BASE / "baseline.key"
    trusted_file(cipher, 1320571760)
    trusted_file(key, 65)
    trusted_file(BASE / "key-custody-receipt.json")
    receipt = json.loads((BASE / "key-custody-receipt.json").read_text())
    need(receipt["status"] == "BASELINE_KEY_CUSTODY_AND_DECRYPT_STREAM_PASS"
         and receipt["cipher_sha256"] == CIPHER_SHA
         and receipt["plaintext_tar_sha256"] == PLAIN_SHA, "CUSTODY_RECEIPT_MISMATCH")
    need(digest_file(cipher) == CIPHER_SHA, "CIPHER_HASH_MISMATCH")
    need(not os.path.lexists(WORK), "PRIOR_RECOVERY_EXISTS_DO_NOT_RERUN")
    need(shutil.disk_usage(BASE).free >= 1536 * 1024 * 1024, "FREE_DISK_UNDER_1_5_GIB")
    WORK.mkdir(mode=0o700)
    print("SELECTIVE_RECOVERY_STARTED; source/dependency files and exact historical DB only.", flush=True)
    proc = None
    try:
        with (WORK / "decrypt-private.log").open("xb") as log:
            proc = subprocess.Popen(
                ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                 "-md", "sha256", "-in", str(cipher), "-pass", "file:" + str(key)],
                stdout=subprocess.PIPE, stderr=log)
            result = recover_stream(proc.stdout, WORK, PLAIN_SHA, DB_SHA)
            need(proc.wait(timeout=30) == 0, "DECRYPT_PROCESS_FAILED")
        result.update({"schema_version": 1, "status": "SELECTED_HISTORICAL_RECOVERY_PASS",
                       "host": os.uname().nodename, "epoch": int(time.time()),
                       "workdir": str(WORK), "service_actions": 0, "production_deployed": False,
                       "api_configuration_deployed": False, "production_module_imported": False,
                       "environment_status": "DEPENDENCY_MANIFESTS_ONLY_NOT_INSTALLED",
                       "current_final_snapshot": False, "tokyo_retirement": "HOLD"})
        private_json(WORK / "receipt.json", result)
        fd = os.open(WORK, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as error:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        failure = {"status": "HOLD_PRESERVE_EVIDENCE", "error_type": type(error).__name__,
                   "reason": str(error) if isinstance(error, RuntimeError) else "SEE_PRIVATE_TRACE",
                   "retry_allowed": False, "service_actions": 0, "workdir": str(WORK)}
        private_json(WORK / "failure-receipt.json", failure)
        print(json.dumps(failure, sort_keys=True), flush=True)
        raise

if __name__ == "__main__":
    main()
