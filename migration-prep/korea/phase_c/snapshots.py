"""Closed WAL-aware generations with detached source authentication and atomic pointer.

The receipt retains the original strict FIELDS contract.  Signature lives beside
it.  A reader fixes the generation name before opening either member; publication
never edits/removes old generations. No production database path is built in.
"""
import os
import sqlite3
from pathlib import Path

from gate_common import canonical_bytes, require
from korea.snapshot_handoff import FIELDS, PROTOCOL, admit_snapshot_handoff
from korea.phase_c.security import (digest, fsync_dir, identifier, read_file, rename_new,
                                    strict_json, trusted_directory, write_once)
from readonly_reconciliation_adapter import ReadOnlyBusinessDatabase

GENERATION_FILES = {"business-snapshot.sqlite", "receipt.json", "signature.json", "collection.json"}


def receive_generation(root, generation_id, files, config, verifier, now_ms):
    """Receive an authenticated closed generation; unknown/duplicate ACK never overwrites.

    Transport authentication/custody is an external deployment gate. Even a
    transport peer cannot publish different bytes under the trusted source key.
    """
    root = trusted_directory(root, exact_mode=0o711)
    identifier(generation_id)
    require(isinstance(files, dict) and set(files) == GENERATION_FILES and
            all(type(v) is bytes and v for v in files.values()), "C_TRANSFER_FILE_SET")
    require(len(files["business-snapshot.sqlite"]) <= 512 * 1024 * 1024 and
            all(len(files[n]) <= 16384 for n in GENERATION_FILES - {"business-snapshot.sqlite"}),
            "C_TRANSFER_SIZE")
    receipt = strict_json(files["receipt.json"])
    packet = strict_json(files["signature.json"])
    require(set(packet) == {"signature"} and set(receipt) == FIELDS and
            receipt["snapshot_generation_id"] == generation_id and
            receipt["database_path"] == str(root / generation_id / "business-snapshot.sqlite") and
            receipt["database_sha256"] == digest(files["business-snapshot.sqlite"]) and
            receipt["publisher_identity_sha256"] == verifier.identity and
            verifier.verify(receipt, packet["signature"]), "C_TRANSFER_AUTHENTICATION")
    final = root / generation_id
    # A receipt, even byte-identical, is not permission to rerun capture or commit.
    require(not os.path.lexists(final), "C_TRANSFER_DUPLICATE_GENERATION")
    pending = root / (".pending-receive-" + generation_id)
    pending.mkdir(mode=0o700); os.chmod(pending, 0o700)
    for name, data in files.items():
        uid = config["snapshot_reader_uid"] if name in {"receipt.json", "business-snapshot.sqlite"} else 0
        write_once(pending / name, data, mode=0o444 if name == "signature.json" else 0o400, uid=uid)
    os.chmod(pending, 0o755); fsync_dir(pending)
    rename_new(pending, final)
    # Pointer cannot change until complete hash, original admission and signature pass.
    publish_pointer(root, generation_id, config, verifier, now_ms)
    return {"generation_id": generation_id, "database_sha256": receipt["database_sha256"],
            "status": "GENERATION_COMMITTED", "retry_allowed": False}


def collect_generation(source, root, generation_id, config, signer, now_ms):
    root = trusted_directory(root, exact_mode=0o711)
    identifier(generation_id)
    pending = root / (".pending-" + generation_id)
    final = root / generation_id
    require(not os.path.lexists(final), "C_SNAPSHOT_GENERATION_EXISTS")
    pending.mkdir(mode=0o700)
    os.chmod(pending, 0o700)
    database = ReadOnlyBusinessDatabase(str(source), str(pending), config["account_id"],
                                        None, now_ms, config["snapshot_max_age_ms"])
    try:
        authoritative = database.snapshot_id
    finally:
        database.connection.close()
    closed = pending / "business-snapshot.sqlite"
    # The backup can inherit WAL mode in its header. Normalize ONLY this private
    # closed copy, otherwise a later mode=ro backup can create sidecars and fail
    # source-stability checks. Never checkpoint/change the live source journal.
    connection = sqlite3.connect(str(closed))
    try:
        require(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete",
                "C_CLOSED_COPY_JOURNAL")
        require(connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                "C_CLOSED_COPY_INTEGRITY")
    finally:
        connection.close()
    fd = os.open(closed, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    require(not os.path.lexists(str(closed) + "-wal") and
            not os.path.lexists(str(closed) + "-shm"), "C_COLLECTOR_NOT_CLOSED")
    import hashlib
    hasher = hashlib.sha256()
    with closed.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            hasher.update(block)
    receipt = {"schema_version": 1, "protocol": PROTOCOL,
               "feature_id": config["feature_id"], "account_id": config["account_id"],
               "database_path": str(final / "business-snapshot.sqlite"),
               "database_sha256": hasher.hexdigest(), "snapshot_generation_id": generation_id,
               "captured_at_ms": now_ms, "published_at_ms": now_ms,
               "runtime_manifest_sha256": config["runtime_manifest_sha256"],
               "publisher_identity_sha256": signer.identity}
    require(set(receipt) == FIELDS, "C_ORIGINAL_HANDOFF_CONTRACT")
    reader = config["snapshot_reader_uid"]
    write_once(pending / "receipt.json", canonical_bytes(receipt), mode=0o400, uid=reader)
    write_once(pending / "signature.json", canonical_bytes({"signature": signer.sign(receipt)}), mode=0o444)
    write_once(pending / "collection.json", canonical_bytes({
        "authoritative_business_snapshot_id": authoritative,
        "capture_semantics": "SQLITE_BACKUP_API_FROM_MODE_RO_WAL_AWARE",
        "production_freeze_claimed": False}), mode=0o400)
    os.chown(closed, reader, reader)
    closed.chmod(0o400)
    # Only file names are public; business bytes remain readable only by worker.
    os.chmod(pending, 0o755)
    fsync_dir(pending)
    rename_new(pending, final)
    return receipt


def verify_generation(root, generation_id, config, verifier, now_ms):
    root = trusted_directory(root, exact_mode=0o711)
    identifier(generation_id)
    path = trusted_directory(root / generation_id, exact_mode=0o755)
    require(set(x.name for x in path.iterdir()) == GENERATION_FILES,
        "C_SNAPSHOT_FILE_SET")
    receipt = strict_json(read_file(path / "receipt.json", owner=config["snapshot_reader_uid"], modes=(0o400,)))
    # Signature is public authentication material, not a database/credential export.
    signature = strict_json(read_file(path / "signature.json", modes=(0o400, 0o444)))
    require(set(signature) == {"signature"} and set(receipt) == FIELDS and
            receipt["snapshot_generation_id"] == generation_id and
            receipt["publisher_identity_sha256"] == verifier.identity and
            receipt["database_path"] == str(path / "business-snapshot.sqlite") and
            verifier.verify(receipt, signature["signature"]), "C_SOURCE_SIGNATURE_INVALID")
    pinned = dict(config, business_database=receipt["database_path"],
                  snapshot_handoff_receipt=str(path / "receipt.json"),
                  snapshot_publisher_identity_sha256=verifier.identity)
    class AuthenticatedSource:
        def verify_snapshot_handoff(self, candidate):
            return candidate == receipt
    admitted = admit_snapshot_handoff(pinned, AuthenticatedSource(), now_ms)
    return pinned, receipt, admitted


def publish_pointer(root, generation_id, config, verifier, now_ms):
    """Commit only verified entire generations. Root-local atomic JSON, no symlinks."""
    root = trusted_directory(root, exact_mode=0o711)
    _, receipt, admitted = verify_generation(root, generation_id, config, verifier, now_ms)
    admitted.close()
    pending = root / (".pointer-" + generation_id)
    write_once(pending, canonical_bytes({"generation_id": generation_id,
                                        "receipt_sha256": digest(canonical_bytes(receipt))}), mode=0o444)
    os.replace(pending, root / "current.json")
    fsync_dir(root)


def pin_current(root, config, verifier, now_ms):
    root = trusted_directory(root, exact_mode=0o711)
    pointer = strict_json(read_file(root / "current.json", modes=(0o444,)))
    require(set(pointer) == {"generation_id", "receipt_sha256"}, "C_POINTER_FIELDS")
    pinned, receipt, admitted = verify_generation(root, pointer["generation_id"], config, verifier, now_ms)
    if digest(canonical_bytes(receipt)) != pointer["receipt_sha256"]:
        admitted.close()
        require(False, "C_POINTER_RECEIPT_MISMATCH")
    return pinned, receipt, admitted
