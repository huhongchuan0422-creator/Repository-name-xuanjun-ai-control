"""Fail-closed admission for atomically published WAL-aware SQLite snapshots."""
from __future__ import print_function

import hashlib
import json
import os
import stat

from gate_common import require


PROTOCOL = "XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1"
FIELDS = frozenset((
    "schema_version", "protocol", "feature_id", "account_id",
    "database_path", "database_sha256", "snapshot_generation_id",
    "captured_at_ms", "published_at_ms", "runtime_manifest_sha256",
    "publisher_identity_sha256",
))


def _sha256_stream(stream):
    digest = hashlib.sha256()
    while True:
        block = stream.read(1024 * 1024)
        if not block:
            break
        digest.update(block)
    return digest.hexdigest()


def _fd_identity(value):
    return {
        "device": value.st_dev, "inode": value.st_ino, "size": value.st_size,
        "mtime_ns": getattr(value, "st_mtime_ns", int(value.st_mtime * 1000000000)),
    }


class AdmittedSnapshotGeneration(object):
    """An authenticated generation held open across verification and capture."""

    def __init__(self, receipt, descriptor, identity):
        self.receipt = receipt
        self.descriptor = descriptor
        self.identity = identity
        self.materialized = None

    def __getitem__(self, name):
        return self.receipt[name]

    def materialize(self, run_dir):
        require(self.descriptor is not None, "SHADOW_SNAPSHOT_GENERATION_ALREADY_CLOSED")
        target = os.path.join(run_dir, "authenticated-generation.sqlite")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        target_fd = os.open(target, flags, 0o600)
        source_fd = os.dup(self.descriptor)
        try:
            with os.fdopen(source_fd, "rb") as source, os.fdopen(target_fd, "wb") as output:
                source_fd = None; target_fd = None
                source.seek(0)
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                output.flush(); os.fsync(output.fileno())
        finally:
            if source_fd is not None: os.close(source_fd)
            if target_fd is not None: os.close(target_fd)
        with open(target, "rb") as stream:
            digest = _sha256_stream(stream)
        require(digest == self.receipt["database_sha256"],
                "SHADOW_SNAPSHOT_MATERIALIZED_HASH_MISMATCH")
        self.materialized = {
            "path": target, "sha256": digest,
            "admitted_source_identity": self.identity,
            "materialized_identity": _fd_identity(os.stat(target)),
            "binding": "AUTHENTICATED_OPEN_DESCRIPTOR_TO_PRIVATE_IMMUTABLE_COPY",
        }
        return self.materialized

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor); self.descriptor = None


def admit_snapshot_handoff(config, verifier, now_ms):
    path = config["snapshot_handoff_receipt"]
    require(os.path.isfile(path) and not os.path.islink(path),
            "SHADOW_SNAPSHOT_HANDOFF_RECEIPT_REQUIRED")
    identity = os.stat(path)
    require(stat.S_IMODE(identity.st_mode) & 0o077 == 0,
            "SHADOW_SNAPSHOT_HANDOFF_RECEIPT_MODE_TOO_BROAD")
    with open(path, "rb") as stream:
        raw = stream.read()
    require(raw and len(raw) <= 16384, "SHADOW_SNAPSHOT_HANDOFF_RECEIPT_SIZE_INVALID")
    receipt = json.loads(raw.decode("utf-8"))
    require(isinstance(receipt, dict) and frozenset(receipt) == FIELDS,
            "SHADOW_SNAPSHOT_HANDOFF_FIELDS_INVALID")
    require(receipt["schema_version"] == 1 and receipt["protocol"] == PROTOCOL,
            "SHADOW_SNAPSHOT_HANDOFF_PROTOCOL_INVALID")
    for name in ("database_sha256", "runtime_manifest_sha256", "publisher_identity_sha256"):
        value = receipt[name]
        require(isinstance(value, str) and len(value) == 64 and
                all(character in "0123456789abcdef" for character in value),
                "SHADOW_SNAPSHOT_HANDOFF_HASH_INVALID:" + name)
    require(receipt["feature_id"] == config["feature_id"] and
            receipt["account_id"] == config["account_id"] and
            receipt["database_path"] == os.path.realpath(config["business_database"]) and
            receipt["runtime_manifest_sha256"] == config["runtime_manifest_sha256"] and
            receipt["publisher_identity_sha256"] == config["snapshot_publisher_identity_sha256"],
            "SHADOW_SNAPSHOT_HANDOFF_IDENTITY_MISMATCH")
    require(isinstance(receipt["snapshot_generation_id"], str) and
            receipt["snapshot_generation_id"], "SHADOW_SNAPSHOT_GENERATION_ID_REQUIRED")
    captured = receipt["captured_at_ms"]; published = receipt["published_at_ms"]
    require(type(captured) is int and type(published) is int and
            captured <= published <= now_ms and
            now_ms - captured <= config["snapshot_max_age_ms"],
            "SHADOW_SNAPSHOT_HANDOFF_STALE")
    database_path = config["business_database"]
    require(not os.path.lexists(database_path + "-wal") and
            not os.path.lexists(database_path + "-shm"),
            "SHADOW_SNAPSHOT_GENERATION_NOT_CLOSED")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(database_path, flags)
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), "SHADOW_SNAPSHOT_DATABASE_REGULAR_REQUIRED")
        path_identity = os.stat(database_path, follow_symlinks=False)
        require(_fd_identity(opened) == _fd_identity(path_identity),
                "SHADOW_SNAPSHOT_DATABASE_PATH_IDENTITY_MISMATCH")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            digest = _sha256_stream(stream)
        require(digest == receipt["database_sha256"],
                "SHADOW_SNAPSHOT_HANDOFF_DATABASE_HASH_MISMATCH")
        require(verifier.verify_snapshot_handoff(receipt),
                "SHADOW_SNAPSHOT_HANDOFF_INDEPENDENT_VERIFICATION_FAILED")
        return AdmittedSnapshotGeneration(receipt, descriptor, _fd_identity(opened))
    except Exception:
        os.close(descriptor)
        raise
