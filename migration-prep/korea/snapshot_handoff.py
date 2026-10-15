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


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


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
    require(_sha256_file(config["business_database"]) == receipt["database_sha256"],
            "SHADOW_SNAPSHOT_HANDOFF_DATABASE_HASH_MISMATCH")
    require(verifier.verify_snapshot_handoff(receipt),
            "SHADOW_SNAPSHOT_HANDOFF_INDEPENDENT_VERIFICATION_FAILED")
    return receipt
