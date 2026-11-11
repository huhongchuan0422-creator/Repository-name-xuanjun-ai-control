"""Durable session save using the existing session path and held lock.

No controller, Writer, session lock, business request or recovery intent is
created here. The original controller must preserve the expected payload hash
before dispatch. Unknown saves are reconciled by query, never replayed here.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid
from credential_key_binding import CredentialBindingHold

LIMIT = 2097152


def encoded(payload):
    raw = (json.dumps(payload, ensure_ascii=True, sort_keys=True,
                      indent=2, allow_nan=False) + '\n').encode()
    if len(raw) > LIMIT:
        raise CredentialBindingHold('SESSION_PAYLOAD_BOUND')
    return raw


def _directory(path):
    path = Path(path)
    if not path.is_absolute() or path.name in {'', '.', '..'}:
        raise CredentialBindingHold('SESSION_PATH_REQUIRED')
    for parent in path.parents:
        if parent.is_symlink():
            raise CredentialBindingHold('SESSION_PATH_SYMLINK')
    fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        os.close(fd)
        raise CredentialBindingHold('PRIVATE_SESSION_DIRECTORY_REQUIRED')
    return path, fd


def _held(check):
    if not callable(check) or check() is not True:
        raise CredentialBindingHold('ORIGINAL_SESSION_LOCK_REQUIRED')


def _query_at(directory, name, expected_sha256):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    except FileNotFoundError:
        return 'UNKNOWN_QUERY_ONLY'
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise CredentialBindingHold('SESSION_FILE_UNTRUSTED')
        raw = b''
        while len(raw) <= LIMIT:
            block = os.read(fd, min(65536, LIMIT + 1 - len(raw)))
            if not block:
                break
            raw += block
        after = os.fstat(fd)
        if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise CredentialBindingHold('SESSION_CHANGED_DURING_QUERY')
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            return 'MISMATCH_HOLD'
        os.fsync(fd)
        os.fsync(directory)
        return 'DURABLE_MATCH'
    finally:
        os.close(fd)


def query_session(path, expected_sha256, assert_held):
    _held(assert_held)
    path, directory = _directory(path)
    try:
        result = _query_at(directory, path.name, expected_sha256)
        _held(assert_held)
        return result
    finally:
        os.close(directory)


def save_session(path, payload, assert_held):
    raw = encoded(payload)
    digest = hashlib.sha256(raw).hexdigest()
    _held(assert_held)
    path, directory = _directory(path)
    temporary = '.pr99-session-' + uuid.uuid4().hex
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        _held(assert_held)
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        if _query_at(directory, path.name, digest) != 'DURABLE_MATCH':
            raise CredentialBindingHold('SESSION_SAVE_UNKNOWN_QUERY_ONLY')
        _held(assert_held)
        return digest
    except Exception:
        raise CredentialBindingHold('SESSION_SAVE_UNKNOWN_QUERY_ONLY') from None
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def save_repository_session(repository, session, assert_held):
    """Called within the original repository.locked(submission_id) scope."""
    check = lambda: assert_held(repository, session.submission_id)
    save_session(repository._path(session.submission_id), repository._serialize(session), check)
    return session
