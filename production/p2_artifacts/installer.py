"""Isolated, journaled artifact installer. Never authorizes production use."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import uuid

IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
HEX = re.compile(r"^[0-9a-f]{64}$")

class Stop(Exception):
    def __init__(self, code):
        self.code = code

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def durable_write(path, data):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    finally:
        pass
    fsync_dir(path.parent)

def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def safe_root(raw):
    if not isinstance(raw, str) or not os.path.isabs(raw) or os.path.normpath(raw) != raw:
        raise Stop("INVALID_ROOT")
    path = Path(raw)
    if path == Path("/") or path.is_symlink():
        raise Stop("INVALID_ROOT")
    current = Path("/")
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise Stop("ROOT_SYMLINK")
    if not path.is_dir():
        raise Stop("ROOT_UNAVAILABLE")
    return path

def request_check(req):
    if not isinstance(req, dict) or req.get("schema") != 1 or req.get("scope") != "ISOLATED_TEST_ONLY":
        raise Stop("INVALID_SCOPE")
    for field in ("installation_id", "batch_id", "attempt_id"):
        if not isinstance(req.get(field), str) or not IDENT.fullmatch(req[field]) or req[field] in (".", ".."):
            raise Stop("INVALID_ID")
    root = safe_root(req.get("root"))
    if not isinstance(req.get("inputs"), dict):
        raise Stop("INVALID_INPUTS")
    return root

def subdir(root, name):
    p = root / name
    if not p.exists():
        p.mkdir(mode=0o700)
        fsync_dir(root)
    if p.is_symlink() or not p.is_dir():
        raise Stop("UNSAFE_STATE")
    return p

def identity(req):
    return {k: req[k] for k in ("schema", "scope", "installation_id", "batch_id", "attempt_id")}

def result(req, status, receipt=None, error=None):
    return dict(identity(req), status=status, receipt=receipt, error=error)

def failure(req, code, log=None):
    return result(req, "HOLD", error={"code": code, "log": log})

def valid_member(name):
    if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name:
        raise Stop("UNSAFE_ARCHIVE")
    parts = name.split("/")
    if any(x in ("", ".", "..") for x in parts) or len(name) > 512:
        raise Stop("UNSAFE_ARCHIVE")

def manifest(req):
    ins = req["inputs"]
    if ins.get("operation") != "install" or not isinstance(ins.get("archive"), str):
        raise Stop("INVALID_INPUTS")
    if not HEX.fullmatch(ins.get("archive_sha256", "")):
        raise Stop("INVALID_DIGEST")
    files = ins.get("files")
    if not isinstance(files, dict) or not files or len(files) > 2048:
        raise Stop("INVALID_MANIFEST")
    for name, sha in files.items():
        valid_member(name)
        if not HEX.fullmatch(sha):
            raise Stop("INVALID_MANIFEST")
    return files

def validate_archive(archive, expected_sha, files):
    if not os.path.isabs(archive) or not os.path.isfile(archive) or os.path.islink(archive):
        raise Stop("ARCHIVE_UNAVAILABLE")
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    if h.hexdigest() != expected_sha:
        raise Stop("ARCHIVE_DIGEST_MISMATCH")
    with tarfile.open(archive, "r:*") as t:
        members = t.getmembers()
        found = {}
        for m in members:
            valid_member(m.name)
            if not m.isfile() or m.name in found or m.name not in files:
                raise Stop("UNSAFE_ARCHIVE")
            if m.size > 256 * 1024 * 1024:
                raise Stop("SIZE_LIMIT")
            data = t.extractfile(m)
            if data is None:
                raise Stop("UNSAFE_ARCHIVE")
            h = hashlib.sha256()
            while True:
                b = data.read(1024 * 1024)
                if not b:
                    break
                h.update(b)
            if h.hexdigest() != files[m.name]:
                raise Stop("FILE_DIGEST_MISMATCH")
            found[m.name] = m
        if set(found) != set(files):
            raise Stop("MANIFEST_MISMATCH")
    return sorted(files)

def verify_tree(destination, files):
    if not destination.is_dir() or destination.is_symlink():
        return False
    actual = {}
    for parent, dirs, filenames in os.walk(destination, followlinks=False):
        for d in dirs:
            if (Path(parent) / d).is_symlink():
                return False
        for filename in filenames:
            f = Path(parent) / filename
            if not f.is_file() or f.is_symlink():
                return False
            actual[str(f.relative_to(destination))] = digest(f.read_bytes())
    return actual == files

def receipt_of(path):
    if not path.is_file() or path.is_symlink():
        return None
    return {"path": str(path), "sha256": digest(path.read_bytes())}

def paths(root, req):
    state = subdir(root, ".p2_artifacts")
    journals = subdir(state, "journals")
    receipts = subdir(state, "receipts")
    versions = subdir(root, "versions")
    key = req["installation_id"] + "--" + req["batch_id"]
    return journals / (key + ".json"), receipts / (key + ".json"), versions / key

def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise Stop("UNSAFE_STATE")
    try:
        return json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise Stop("CORRUPT_JOURNAL")

def inspect_locked(req, root):
    journal, receipt, dest = paths(root, req)
    if not journal.exists() and not receipt.exists() and not dest.exists():
        return result(req, "NO_EFFECT")
    if not journal.exists():
        return failure(req, "UNJOURNALED_EFFECT")
    j = read_json(journal)
    if j.get("request_digest") != digest(encode(req)) or j.get("attempt_id") != req["attempt_id"]:
        return failure(req, "REQUEST_CONFLICT", str(journal))
    if receipt.exists():
        r = read_json(receipt)
        if r.get("journal_sha256") != digest(journal.read_bytes()) or not verify_tree(dest, j["files"]):
            return failure(req, "COMMITTED_STATE_MISMATCH", str(journal))
        return result(req, "COMMITTED", receipt_of(receipt))
    return failure(req, "INCOMPLETE_BATCH", str(journal))

def locked(req, action):
    root = request_check(req)
    state = subdir(root, ".p2_artifacts")
    fd = os.open(str(state / ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if action != "execute":
            return inspect_locked(req, root)
        prior = inspect_locked(req, root)
        if prior["status"] != "NO_EFFECT":
            return prior
        files = manifest(req)
        ins = req["inputs"]
        names = validate_archive(ins["archive"], ins["archive_sha256"], files)
        journal, receipt, dest = paths(root, req)
        j = {"schema": 1, "request_digest": digest(encode(req)), "attempt_id": req["attempt_id"],
             "files": files, "archive_sha256": ins["archive_sha256"], "phase": "PREPARED"}
        durable_write(journal, encode(j))
        # Destination is unique per batch and never replaces an earlier committed version.
        dest.mkdir(mode=0o700)
        fsync_dir(dest.parent)
        with tarfile.open(ins["archive"], "r:*") as tar:
            for name in names:
                member = tar.getmember(name)
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.exists():
                    raise Stop("DESTINATION_CONFLICT")
                data = tar.extractfile(member)
                if data is None:
                    raise Stop("UNSAFE_ARCHIVE")
                durable_write(target, data.read())
        if not verify_tree(dest, files):
            raise Stop("POST_INSTALL_MISMATCH")
        fsync_dir(dest)
        durable_write(receipt, encode({"schema": 1, "journal_sha256": digest(journal.read_bytes()),
                                      "version": str(dest), "files": files}))
        return inspect_locked(req, root)
    finally:
        os.close(fd)

def dispatch(req, action):
    try:
        return locked(req, action)
    except Stop as e:
        return failure(req, e.code)
    except (OSError, tarfile.TarError, ValueError, KeyError, TypeError):
        return failure(req, "IO_OR_FORMAT_ERROR")

def execute(request):
    return dispatch(request, "execute")

def inspect(request):
    return dispatch(request, "inspect")

def recover(request):
    return dispatch(request, "recover")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("execute", "inspect", "recover"))
    args = parser.parse_args()
    try:
        req = json.load(sys.stdin)
        out = globals()[args.action](req)
    except (ValueError, TypeError):
        out = {"status": "HOLD", "error": {"code": "INVALID_JSON", "log": None}}
    print(json.dumps(out, sort_keys=True))
    return 0 if out["status"] in ("COMMITTED", "NO_EFFECT") else 2

if __name__ == "__main__":
    sys.exit(main())
