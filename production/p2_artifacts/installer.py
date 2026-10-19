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
CHUNK = 1024 * 1024
MAX_MEMBERS = 2048
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 768 * 1024 * 1024

class Stop(Exception):
    def __init__(self, code):
        self.code = code

def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def durable_write(path, data, mode=0o600):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    fsync_dir(path.parent)

def stream_hash_file(path):
    if path.is_symlink() or not path.is_file():
        raise Stop("UNSAFE_STATE")
    h = hashlib.sha256()
    with open(path, "rb") as src:
        while True:
            b = src.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def safe_root(raw):
    if not isinstance(raw, str) or not os.path.isabs(raw) or os.path.normpath(raw) != raw:
        raise Stop("INVALID_ROOT")
    path = Path(raw)
    if path == Path("/") or path.is_symlink() or not path.is_dir():
        raise Stop("INVALID_ROOT")
    current = Path("/")
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise Stop("ROOT_SYMLINK")
    st = path.stat()
    if st.st_uid != os.geteuid() or (stat.S_IMODE(st.st_mode) & 0o022):
        raise Stop("ROOT_OWNERSHIP_OR_MODE")
    return path

def checked_dir(parent, name, create=True):
    p = parent / name
    if not p.exists() and create:
        p.mkdir(mode=0o700)
        fsync_dir(parent)
    try:
        st = os.lstat(p)
    except OSError:
        raise Stop("UNSAFE_STATE")
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise Stop("UNSAFE_STATE")
    if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise Stop("STATE_OWNERSHIP_OR_MODE")
    return p

def request_check(req):
    if not isinstance(req, dict) or req.get("schema") != 1 or req.get("scope") != "ISOLATED_TEST_ONLY":
        raise Stop("INVALID_SCOPE")
    for field in ("installation_id", "batch_id", "attempt_id"):
        if not isinstance(req.get(field), str) or not IDENT.fullmatch(req[field]) or req[field] in (".", ".."):
            raise Stop("INVALID_ID")
    if not isinstance(req.get("inputs"), dict):
        raise Stop("INVALID_INPUTS")
    return safe_root(req.get("root"))

def identity(req):
    try:
        return {k: req[k] for k in ("schema", "scope", "installation_id", "batch_id", "attempt_id")}
    except Exception:
        return {"schema": 1, "scope": "ISOLATED_TEST_ONLY", "installation_id": None,
                "batch_id": None, "attempt_id": None}

def result(req, status, receipt=None, error=None):
    return dict(identity(req), status=status, receipt=receipt, error=error)

def failure(req, code, log=None, stage=None):
    return result(req, "HOLD", error={"code": code, "stage": stage, "log": log})

def valid_member(name):
    if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name or len(name) > 512:
        raise Stop("UNSAFE_ARCHIVE")
    if any(x in ("", ".", "..") for x in name.split("/")):
        raise Stop("UNSAFE_ARCHIVE")

def parse_manifest(req):
    ins = req["inputs"]
    if ins.get("operation") != "install" or not isinstance(ins.get("archive"), str):
        raise Stop("INVALID_INPUTS")
    if not os.path.isabs(ins["archive"]) or not HEX.fullmatch(ins.get("archive_sha256", "")):
        raise Stop("INVALID_INPUTS")
    files = ins.get("files")
    if not isinstance(files, dict) or not files or len(files) > MAX_MEMBERS:
        raise Stop("INVALID_MANIFEST")
    for name, sha in files.items():
        valid_member(name)
        if not HEX.fullmatch(sha):
            raise Stop("INVALID_MANIFEST")
    modes = ins.get("modes", {})
    if not isinstance(modes, dict) or set(modes) - set(files):
        raise Stop("INVALID_MODES")
    normalized = {}
    for name in files:
        mode = modes.get(name, 0o600)
        if mode not in (0o600, 0o700):
            raise Stop("INVALID_MODES")
        normalized[name] = mode
    return files, normalized

def state_paths(root, req):
    state = checked_dir(root, ".p2_artifacts")
    journals = checked_dir(state, "journals")
    receipts = checked_dir(state, "receipts")
    snapshots = checked_dir(state, "snapshots")
    errors = checked_dir(state, "errors")
    recoveries = checked_dir(state, "recoveries")
    versions = checked_dir(root, "versions")
    key = req["installation_id"] + "--" + req["batch_id"]
    snap = snapshots / (key + "--" + req["attempt_id"] + ".tar")
    return state, journals / (key + ".json"), receipts / (key + ".json"), snap, recoveries / (key + ".json"), versions / key, errors

def persist_error(errors, req, code, stage, details=None):
    name = "%s--%s--%s.json" % (req.get("installation_id", "unknown"), req.get("batch_id", "unknown"), uuid.uuid4().hex)
    p = errors / name
    payload = {"schema": 1, "code": code, "stage": stage,
               "installation_id": req.get("installation_id"), "batch_id": req.get("batch_id"),
               "attempt_id": req.get("attempt_id"), "details": details}
    try:
        durable_write(p, encode(payload))
        return str(p)
    except Exception:
        return None

def snapshot_partial(snapshot):
    return Path(str(snapshot) + ".partial")

def snapshot_input(req, snapshot):
    source = req["inputs"]["archive"]
    partial = snapshot_partial(snapshot)
    if partial.exists():
        raise Stop("STALE_PARTIAL_SNAPSHOT")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open(source, flags)
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ARCHIVE_BYTES:
        os.close(fd)
        raise Stop("ARCHIVE_UNAVAILABLE")
    outfd = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    h = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "rb", closefd=True) as src, os.fdopen(outfd, "wb", closefd=True) as out:
            while True:
                b = src.read(CHUNK)
                if not b:
                    break
                total += len(b)
                if total > MAX_ARCHIVE_BYTES:
                    raise Stop("ARCHIVE_SIZE_LIMIT")
                h.update(b)
                out.write(b)
            out.flush()
            os.fsync(out.fileno())
            after = os.fstat(src.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise Stop("ARCHIVE_CHANGED_DURING_READ")
            if h.hexdigest() != req["inputs"]["archive_sha256"]:
                raise Stop("ARCHIVE_DIGEST_MISMATCH")
            os.fchmod(out.fileno(), 0o400)
            os.fsync(out.fileno())
        os.rename(partial, snapshot)
        fsync_dir(snapshot.parent)
    except BaseException:
        try:
            os.unlink(partial)
        except OSError:
            pass
        raise
    return h.hexdigest()

def validate_snapshot(snapshot, expected_sha, files):
    if snapshot.is_symlink() or not snapshot.is_file() or stat.S_IMODE(snapshot.stat().st_mode) != 0o400:
        raise Stop("SNAPSHOT_UNSAFE")
    if stream_hash_file(snapshot) != expected_sha:
        raise Stop("SNAPSHOT_DIGEST_MISMATCH")
    found = {}
    total = 0
    with tarfile.open(snapshot, "r:*") as tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise Stop("MEMBER_LIMIT")
        for m in members:
            valid_member(m.name)
            if not m.isfile() or m.name in found or m.name not in files:
                raise Stop("UNSAFE_ARCHIVE")
            if m.size < 0 or m.size > MAX_MEMBER_BYTES:
                raise Stop("SIZE_LIMIT")
            total += m.size
            if total > MAX_TOTAL_BYTES:
                raise Stop("TOTAL_SIZE_LIMIT")
            src = tar.extractfile(m)
            if src is None:
                raise Stop("UNSAFE_ARCHIVE")
            h = hashlib.sha256()
            count = 0
            while True:
                b = src.read(CHUNK)
                if not b:
                    break
                count += len(b)
                if count > m.size:
                    raise Stop("SIZE_MISMATCH")
                h.update(b)
            if count != m.size or h.hexdigest() != files[m.name]:
                raise Stop("FILE_DIGEST_MISMATCH")
            found[m.name] = m.size
    if set(found) != set(files):
        raise Stop("MANIFEST_MISMATCH")
    return sorted(found)

def read_json(path, corrupt="CORRUPT_STATE"):
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid():
            raise Stop("UNSAFE_STATE")
        return json.loads(path.read_text())
    except Stop:
        raise
    except (OSError, ValueError, UnicodeError):
        raise Stop(corrupt)

def secure_parent(dest, rel):
    cur = dest
    parts = rel.split("/")[:-1]
    for part in parts:
        nxt = cur / part
        if not nxt.exists():
            nxt.mkdir(mode=0o700)
            fsync_dir(cur)
        st = os.lstat(nxt)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid():
            raise Stop("DESTINATION_PARENT_UNSAFE")
        cur = nxt
    return dest / rel

def part_path(target, attempt_id):
    return target.with_name(target.name + ".p2-part-" + attempt_id)

def write_stream(target, src, expected_size, mode, attempt_id):
    partial = part_path(target, attempt_id)
    fd = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    h = hashlib.sha256()
    count = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                b = src.read(CHUNK)
                if not b:
                    break
                count += len(b)
                if count > expected_size or count > MAX_MEMBER_BYTES:
                    raise Stop("SIZE_MISMATCH")
                h.update(b)
                out.write(b)
            if count != expected_size:
                raise Stop("SIZE_MISMATCH")
            os.fchmod(out.fileno(), mode)
            out.flush()
            os.fsync(out.fileno())
        os.link(partial, target, follow_symlinks=False)
        fsync_dir(target.parent)
        os.unlink(partial)
        fsync_dir(target.parent)
    except BaseException:
        raise
    return h.hexdigest()

def scan_tree(dest):
    actual = {}
    if not dest.exists():
        return actual
    if dest.is_symlink() or not dest.is_dir():
        raise Stop("DESTINATION_UNSAFE")
    for parent, dirs, names in os.walk(dest, followlinks=False):
        for d in dirs:
            p = Path(parent) / d
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise Stop("DESTINATION_UNSAFE")
        for name in names:
            p = Path(parent) / name
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise Stop("DESTINATION_UNSAFE")
            actual[str(p.relative_to(dest))] = stream_hash_file(p)
    return actual

def verify_tree(dest, files, modes):
    try:
        if scan_tree(dest) != files:
            return False
        for name, mode in modes.items():
            p = dest / name
            if stat.S_IMODE(os.lstat(p).st_mode) != mode:
                return False
        return True
    except (Stop, OSError):
        return False

def receipt_of(path):
    if not path.exists():
        return None
    return {"path": str(path), "sha256": stream_hash_file(path)}

def verify_journal(req, journal):
    j = read_json(journal, "CORRUPT_JOURNAL")
    files, modes = parse_manifest(req)
    if j.get("schema") != 1 or j.get("request_digest") != digest_bytes(encode(req)) or j.get("attempt_id") != req["attempt_id"]:
        raise Stop("REQUEST_CONFLICT")
    if j.get("files") != files or j.get("modes") != modes or j.get("archive_sha256") != req["inputs"].get("archive_sha256"):
        raise Stop("JOURNAL_MISMATCH")
    return j

def verify_receipt(journal, receipt, dest, recovery):
    r = read_json(receipt, "CORRUPT_RECEIPT")
    if r.get("journal_sha256") != stream_hash_file(journal) or not verify_tree(dest, r.get("files", {}), r.get("modes", {})):
        raise Stop("COMMITTED_STATE_MISMATCH")
    rec = r.get("recovery")
    if rec:
        if str(recovery) != rec.get("path") or not recovery.exists() or stream_hash_file(recovery) != rec.get("sha256"):
            raise Stop("RECOVERY_EVIDENCE_MISMATCH")
    return r

def inspect_locked(req, root):
    _, journal, receipt, snapshot, recovery, dest, _ = state_paths(root, req)
    if receipt.exists():
        if not journal.exists():
            return failure(req, "RECEIPT_WITHOUT_JOURNAL", str(receipt), "INSPECT")
        try:
            verify_journal(req, journal)
            verify_receipt(journal, receipt, dest, recovery)
            return result(req, "COMMITTED", receipt_of(receipt))
        except Stop as e:
            return failure(req, e.code, str(journal), "INSPECT")
    if journal.exists():
        try:
            verify_journal(req, journal)
        except Stop as e:
            return failure(req, e.code, str(journal), "INSPECT")
        return failure(req, "INCOMPLETE_BATCH", str(journal), "INSPECT")
    partial = snapshot_partial(snapshot)
    if snapshot.exists() or partial.exists() or dest.exists() or recovery.exists():
        evidence = snapshot if snapshot.exists() else (partial if partial.exists() else dest)
        return failure(req, "UNJOURNALED_EFFECT", str(evidence), "INSPECT")
    return result(req, "NO_EFFECT")

def make_journal(req, journal):
    files, modes = parse_manifest(req)
    payload = {"schema": 1, "request_digest": digest_bytes(encode(req)), "attempt_id": req["attempt_id"],
               "files": files, "modes": modes, "archive_sha256": req["inputs"]["archive_sha256"]}
    durable_write(journal, encode(payload))

def ensure_snapshot(req, snapshot, files, recover_mode=False, errors=None):
    partial = snapshot_partial(snapshot)
    if partial.exists():
        if not recover_mode:
            raise Stop("STALE_PARTIAL_SNAPSHOT")
        st = os.lstat(partial)
        if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid():
            raise Stop("PARTIAL_SNAPSHOT_OWNERSHIP_UNKNOWN")
        evidence = {"path": str(partial), "size": st.st_size, "sha256": stream_hash_file(partial)}
        if errors is not None:
            persist_error(errors, req, "INTERRUPTED_SNAPSHOT", "RECOVER", evidence)
        os.unlink(partial)
        fsync_dir(partial.parent)
    if snapshot.exists():
        validate_snapshot(snapshot, req["inputs"]["archive_sha256"], files)
    else:
        snapshot_input(req, snapshot)
        validate_snapshot(snapshot, req["inputs"]["archive_sha256"], files)

def clean_owned_partials(dest, files, attempt_id, errors=None, req=None):
    for name in files:
        target = dest / name
        partial = part_path(target, attempt_id)
        if partial.exists():
            st = os.lstat(partial)
            if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid():
                raise Stop("PARTIAL_FILE_OWNERSHIP_UNKNOWN")
            if errors is not None and req is not None:
                persist_error(errors, req, "INTERRUPTED_FILE_WRITE", "RECOVER",
                              {"path": str(partial), "size": st.st_size, "sha256": stream_hash_file(partial)})
            os.unlink(partial)
            fsync_dir(partial.parent)

def install_missing(snapshot, dest, files, modes, attempt_id):
    actual = scan_tree(dest)
    unknown = set(actual) - set(files)
    wrong = {k for k, v in actual.items() if k in files and files[k] != v}
    wrong_mode = {k for k in actual if k in modes and stat.S_IMODE(os.lstat(dest / k).st_mode) != modes[k]}
    if unknown or wrong or wrong_mode:
        raise Stop("PARTIAL_STATE_CONFLICT")
    missing = [name for name in sorted(files) if name not in actual]
    if not missing:
        return []
    with tarfile.open(snapshot, "r:*") as tar:
        mapping = {m.name: m for m in tar.getmembers()}
        for name in missing:
            m = mapping[name]
            target = secure_parent(dest, name)
            src = tar.extractfile(m)
            if src is None or write_stream(target, src, m.size, modes[name], attempt_id) != files[name]:
                raise Stop("WRITE_VERIFY_FAILED")
            _interrupt_hook(name)
    return missing

def _interrupt_hook(_name):
    return None

def commit_receipt(req, journal, receipt, dest, recovery=None):
    files, modes = parse_manifest(req)
    if not verify_tree(dest, files, modes):
        raise Stop("POST_INSTALL_MISMATCH")
    payload = {"schema": 1, "journal_sha256": stream_hash_file(journal), "version": str(dest),
               "files": files, "modes": modes, "recovery": None}
    if recovery is not None:
        payload["recovery"] = {"path": str(recovery), "sha256": stream_hash_file(recovery)}
    durable_write(receipt, encode(payload))

def do_execute(req, root):
    files, modes = parse_manifest(req)
    _, journal, receipt, snapshot, recovery, dest, _ = state_paths(root, req)
    prior = inspect_locked(req, root)
    if prior["status"] != "NO_EFFECT":
        return prior
    ensure_snapshot(req, snapshot, files)
    make_journal(req, journal)
    if not dest.exists():
        dest.mkdir(mode=0o700)
        fsync_dir(dest.parent)
    install_missing(snapshot, dest, files, modes, req["attempt_id"])
    commit_receipt(req, journal, receipt, dest)
    return inspect_locked(req, root)

def do_recover(req, root):
    files, modes = parse_manifest(req)
    _, journal, receipt, snapshot, recovery, dest, errors = state_paths(root, req)
    if receipt.exists():
        return inspect_locked(req, root)
    # A partial current-attempt snapshot is retained as evidence, then rebuilt from the exact digest-bound source.
    ensure_snapshot(req, snapshot, files, recover_mode=True, errors=errors)
    if not journal.exists():
        make_journal(req, journal)
    verify_journal(req, journal)
    validate_snapshot(snapshot, req["inputs"]["archive_sha256"], files)
    if not dest.exists():
        dest.mkdir(mode=0o700)
        fsync_dir(dest.parent)
    clean_owned_partials(dest, files, req["attempt_id"], errors, req)
    before = scan_tree(dest)
    unknown = set(before) - set(files)
    wrong = {k for k, v in before.items() if k in files and files[k] != v}
    if unknown or wrong:
        raise Stop("PARTIAL_STATE_CONFLICT")
    restored = install_missing(snapshot, dest, files, modes, req["attempt_id"])
    if not verify_tree(dest, files, modes):
        raise Stop("RECOVERY_VERIFY_FAILED")
    if not recovery.exists():
        durable_write(recovery, encode({"schema": 1, "journal_sha256": stream_hash_file(journal),
                                        "snapshot_sha256": stream_hash_file(snapshot),
                                        "restored": restored, "preexisting": sorted(before)}))
    else:
        ev = read_json(recovery, "CORRUPT_RECOVERY_EVIDENCE")
        if ev.get("journal_sha256") != stream_hash_file(journal) or ev.get("snapshot_sha256") != stream_hash_file(snapshot):
            raise Stop("RECOVERY_EVIDENCE_MISMATCH")
    commit_receipt(req, journal, receipt, dest, recovery)
    return inspect_locked(req, root)

def locked(req, action):
    stage = "REQUEST"
    root = request_check(req)
    state, _, _, _, _, _, errors = state_paths(root, req)
    lock_path = state / ".lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600:
            raise Stop("LOCK_OWNERSHIP_OR_MODE")
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            if action == "inspect":
                stage = "INSPECT"
                return inspect_locked(req, root)
            if action == "execute":
                stage = "EXECUTE"
                return do_execute(req, root)
            stage = "RECOVER"
            return do_recover(req, root)
        except Stop as e:
            log = persist_error(errors, req, e.code, stage)
            return failure(req, e.code, log, stage)
        except (OSError, tarfile.TarError, ValueError, KeyError, TypeError):
            log = persist_error(errors, req, "IO_OR_FORMAT_ERROR", stage)
            return failure(req, "IO_OR_FORMAT_ERROR", log, stage)
    finally:
        os.close(fd)

def dispatch(req, action):
    try:
        return locked(req, action)
    except Stop as e:
        return failure(req, e.code, None, "REQUEST")
    except (OSError, ValueError, KeyError, TypeError):
        return failure(req, "IO_OR_FORMAT_ERROR", None, "REQUEST")

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
        out = {"schema": 1, "scope": "ISOLATED_TEST_ONLY", "installation_id": None, "batch_id": None,
               "attempt_id": None, "status": "HOLD", "receipt": None,
               "error": {"code": "INVALID_JSON", "stage": "REQUEST", "log": None}}
    print(json.dumps(out, sort_keys=True))
    return 0 if out["status"] in ("COMMITTED", "NO_EFFECT") else 2

if __name__ == "__main__":
    sys.exit(main())
