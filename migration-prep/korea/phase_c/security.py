"""Small filesystem and detached-signature primitives; no production defaults."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from gate_common import canonical_bytes, require


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}", value),
            "C_IDENTIFIER")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hash_value(value):
    return digest(canonical_bytes(value))


def trusted_directory(path, owner=0, exact_mode=None):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "C_ABSOLUTE_PATH")
    for item in reversed((path,) + tuple(path.parents)):
        s = item.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == owner and not s.st_mode & 0o022,
                "C_UNTRUSTED_DIRECTORY")
    if exact_mode is not None:
        require(stat.S_IMODE(path.lstat().st_mode) == exact_mode, "C_DIRECTORY_MODE")
    return path


def read_file(path, owner=0, modes=(0o400, 0o600), limit=65536):
    path = Path(path)
    trusted_directory(path.parent)
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == owner and s.st_nlink == 1 and
                stat.S_IMODE(s.st_mode) in modes and 0 < s.st_size <= limit,
                "C_FILE_IDENTITY")
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        require(0 < len(data) <= limit, "C_FILE_SIZE")
        after = os.fstat(fd)
        require((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "C_FILE_CHANGED")
        return bytes(data)
    finally:
        os.close(fd)


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def rename_new(source, destination):
    """Linux atomic directory publication without replacement, including empty dirs."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    fsync_dir(Path(destination).parent)


def write_once(path, data, mode=0o600, uid=None, gid=None):
    path = Path(path)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        if uid is not None:
            os.fchown(out.fileno(), uid, gid if gid is not None else uid)
        os.fchmod(out.fileno(), mode)
        out.flush()
        os.fsync(out.fileno())
    fsync_dir(path.parent)


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "C_DUPLICATE_JSON_FIELD")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("C_NONFINITE_JSON")))


class DetachedRSA:
    """OpenSSL 1.1.1-compatible RSA/SHA256; public key pinned outside worker control.

    Signing is available only to a separately confined custodian/collector.
    This class never accepts a public key, key path or executable from a receipt.
    """
    def __init__(self, public_key, public_sha256, openssl="/usr/bin/openssl", private_key=None,
                 key_owner=0):
        self.public_key = str(public_key)
        raw = read_file(public_key, modes=(0o400, 0o600, 0o644))
        require(digest(raw) == public_sha256, "C_PUBLIC_KEY_PIN")
        self.identity = public_sha256
        self.openssl = str(openssl)
        executable = Path(openssl).resolve(strict=True)
        trusted_directory(executable.parent)
        info = executable.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "C_OPENSSL_IDENTITY")
        self.private_key = None if private_key is None else str(private_key)
        if private_key is not None:
            read_file(private_key, owner=key_owner)

    def sign(self, value):
        require(self.private_key is not None, "C_SIGNER_NOT_AVAILABLE")
        result = subprocess.run([self.openssl, "dgst", "-sha256", "-sign", self.private_key],
                                input=canonical_bytes(value), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=5, check=True)
        require(256 <= len(result.stdout) <= 1024, "C_RSA_SIGNATURE_SIZE")
        return base64.b64encode(result.stdout).decode("ascii")

    def verify(self, value, signature):
        # memfd has no persistent pathname, cache or user-controlled temporary file.
        try:
            raw = base64.b64decode(signature, validate=True)
            require(256 <= len(raw) <= 1024, "C_RSA_SIGNATURE_SIZE")
            fd = os.memfd_create("pr99-signature", os.MFD_CLOEXEC)
            try:
                os.write(fd, raw)
                os.lseek(fd, 0, os.SEEK_SET)
                result = subprocess.run(
                    [self.openssl, "dgst", "-sha256", "-verify", self.public_key,
                     "-signature", "/proc/self/fd/" + str(fd)],
                    input=canonical_bytes(value), stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, pass_fds=(fd,), timeout=5)
                return result.returncode == 0
            finally:
                os.close(fd)
        except (ValueError, TypeError, OSError, subprocess.SubprocessError):
            return False
