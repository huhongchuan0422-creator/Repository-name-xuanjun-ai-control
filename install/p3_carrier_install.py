#!/usr/bin/env python3
"""Verify and stage the immutable P3 carrier as default-off code.

The installer never edits the canonical ledger, activation descriptor, service
unit, provider, outbox, or host callsite.  The existing controlled entry must
fresh-read P2 acceptance, explicit P3 release, locks, attempts and consumed
records at each side-effect boundary and supply that verifier as a callable.
This module deliberately creates no second approval or task system.
"""
from __future__ import absolute_import

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ATTEMPT = re.compile(r"^[a-z0-9][a-z0-9-]{7,79}$")


def _digest(path):
    value = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("REGULAR_FILE_REQUIRED")
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            value.update(chunk)
    finally:
        os.close(descriptor)
    return value.hexdigest()


def _read_json(path, maximum=1024 * 1024):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("INVALID_JSON_FILE")
        chunks = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return json.loads(b"".join(chunks).decode("utf-8")), info
    finally:
        os.close(descriptor)


def _canonical(path):
    if not os.path.isabs(path) or os.path.realpath(path) != path:
        raise ValueError("CANONICAL_ABSOLUTE_PATH_REQUIRED")
    return path


def verify_carrier(root, manifest_path, expected_manifest_sha256):
    _canonical(root)
    _canonical(manifest_path)
    if (not SHA256.fullmatch(expected_manifest_sha256 or "")
            or _digest(manifest_path) != expected_manifest_sha256):
        raise ValueError("CARRIER_MANIFEST_SHA256_MISMATCH")
    manifest, _ = _read_json(manifest_path)
    keys = {
        "schema", "kind", "source_commit", "source_tree", "default_off",
        "execution_enabled", "notifications_enabled", "files",
        "release_files", "base_reviews",
    }
    if not isinstance(manifest, dict) or set(manifest) != keys:
        raise ValueError("EXACT_CARRIER_MANIFEST_REQUIRED")
    if (manifest["schema"] != 1
            or manifest["kind"] != "P3_IMMUTABLE_DEFAULT_OFF_INSTALL_CARRIER"
            or not SHA40.fullmatch(manifest["source_commit"] or "")
            or not SHA40.fullmatch(manifest["source_tree"] or "")
            or manifest["default_off"] is not True
            or manifest["execution_enabled"] is not False
            or manifest["notifications_enabled"] is not False):
        raise ValueError("CARRIER_IDENTITY_OR_DEFAULT_OFF_INVALID")
    files = manifest["files"]
    release_files = manifest["release_files"]
    if not isinstance(files, dict) or not files or not isinstance(release_files, list):
        raise ValueError("CARRIER_FILE_SET_REQUIRED")
    if not release_files or not set(release_files).issubset(set(files)):
        raise ValueError("RELEASE_FILE_SET_INVALID")
    for name, expected in files.items():
        if (not isinstance(name, str) or name.startswith("/")
                or ".." in name.split("/")
                or not SHA256.fullmatch(expected or "")):
            raise ValueError("INVALID_CARRIER_MEMBER")
        path = os.path.join(root, name)
        if os.path.islink(path) or not os.path.isfile(path) or _digest(path) != expected:
            raise ValueError("CARRIER_MEMBER_MISMATCH:%s" % name)
    return manifest


def _fresh_authority(reader):
    if not callable(reader):
        raise PermissionError("CONTROLLED_ENTRY_AUTHORITY_READER_REQUIRED")
    # The existing controlled entry owns validation and returns True only after
    # its current P2/P3/lock/attempt/consumed-record readback.  Preserve any
    # specific exception it raises instead of replacing its evidence.
    if reader() is not True:
        raise PermissionError("CURRENT_CONTROLLED_ENTRY_AUTHORITY_REQUIRED")


def _copy_verified(source, destination, expected):
    source_descriptor = os.open(
        source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(source_descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("REGULAR_SOURCE_REQUIRED")
        destination_descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        value = hashlib.sha256()
        with os.fdopen(destination_descriptor, "wb") as output:
            while True:
                chunk = os.read(source_descriptor, 65536)
                if not chunk:
                    break
                value.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(source_descriptor)
    if value.hexdigest() != expected:
        raise ValueError("SOURCE_CHANGED_DURING_COPY")


def _atomic_json(path, value, mode=0o440):
    parent = os.path.dirname(path)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"))
               + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=parent)
    os.fchmod(descriptor, mode)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.rename(temporary, path)
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _exclusive_json(path, value, mode=0o440):
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"))
               + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    parent = os.path.dirname(path)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _readback_target(target, manifest, manifest_sha256, carrier_archive_sha256):
    receipt_path = os.path.join(target, "INSTALL_RECEIPT.json")
    if not os.path.isdir(target) or os.path.islink(target) or not os.path.isfile(receipt_path):
        return {"state": "ABSENT", "target": target}
    receipt, _ = _read_json(receipt_path, maximum=65536)
    expected = {
        "schema": 1, "state": "INSTALLED_DEFAULT_OFF_NOT_BOUND",
        "source_commit": manifest["source_commit"],
        "source_tree": manifest["source_tree"],
        "carrier_manifest_sha256": manifest_sha256,
        "carrier_archive_sha256": carrier_archive_sha256,
        "execution_enabled": False, "notifications_enabled": False,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            return {"state": "CONFLICT", "target": target, "field": key}
    for name in manifest["release_files"]:
        path = os.path.join(target, name)
        if os.path.islink(path) or not os.path.isfile(path) \
                or _digest(path) != manifest["files"][name]:
            return {"state": "CONFLICT", "target": target, "field": name}
    return {"state": "INSTALLED_DEFAULT_OFF_NOT_BOUND", "target": target,
            "attempt_id": receipt.get("attempt_id"), "verified": True}


def install(root, manifest_path, manifest_sha256, carrier_archive_sha256,
            release_root, state_root, attempt_id, fresh_authority,
            enforce_root=True):
    if enforce_root and os.geteuid() != 0:
        raise PermissionError("ROOT_INSTALL_REQUIRED")
    for path in (root, manifest_path, release_root, state_root):
        _canonical(path)
    if (not SHA256.fullmatch(carrier_archive_sha256 or "")
            or not ATTEMPT.fullmatch(attempt_id or "")):
        raise ValueError("CARRIER_SHA_AND_ATTEMPT_REQUIRED")
    manifest = verify_carrier(root, manifest_path, manifest_sha256)
    _fresh_authority(fresh_authority)
    os.makedirs(release_root, mode=0o750, exist_ok=True)
    os.makedirs(state_root, mode=0o750, exist_ok=True)
    attempts = os.path.join(state_root, "attempts")
    os.makedirs(attempts, mode=0o750, exist_ok=True)
    target = os.path.join(release_root, "p3-" + carrier_archive_sha256[:20])
    observed = _readback_target(
        target, manifest, manifest_sha256, carrier_archive_sha256)
    if observed["state"] == "INSTALLED_DEFAULT_OFF_NOT_BOUND":
        return dict(observed, idempotent=True)
    if observed["state"] != "ABSENT":
        raise ValueError("EXISTING_RELEASE_CONFLICT")
    intent = os.path.join(attempts, attempt_id + ".intent.json")
    if os.path.lexists(intent):
        # UNKNOWN effect: never replay.  The caller must use readback/recover.
        raise RuntimeError("ATTEMPT_ALREADY_HAS_INTENT_RECONCILE_FIRST")
    _exclusive_json(intent, {
        "schema": 1, "state": "INSTALLING_DEFAULT_OFF",
        "attempt_id": attempt_id, "target": target,
        "carrier_archive_sha256": carrier_archive_sha256,
    })
    staging = tempfile.mkdtemp(prefix=".p3-", dir=release_root)
    try:
        for name in sorted(manifest["release_files"]):
            destination = os.path.join(staging, name)
            os.makedirs(os.path.dirname(destination), mode=0o750, exist_ok=True)
            _copy_verified(os.path.join(root, name), destination,
                           manifest["files"][name])
        # Permissions, P2/P3 release, locks and consumed records are mutable.
        # Fresh-read again immediately before the atomic release rename.
        _fresh_authority(fresh_authority)
        receipt = {
            "schema": 1, "state": "INSTALLED_DEFAULT_OFF_NOT_BOUND",
            "attempt_id": attempt_id,
            "source_commit": manifest["source_commit"],
            "source_tree": manifest["source_tree"],
            "carrier_manifest_sha256": manifest_sha256,
            "carrier_archive_sha256": carrier_archive_sha256,
            "execution_enabled": False, "notifications_enabled": False,
            "host_bound": False, "real_task_executed": False,
        }
        _atomic_json(os.path.join(staging, "INSTALL_RECEIPT.json"), receipt)
        os.rename(staging, target)
        directory = os.open(release_root,
                            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.isdir(staging):
            shutil.rmtree(staging)
    return _readback_target(target, manifest, manifest_sha256,
                            carrier_archive_sha256)


def readback(root, manifest_path, manifest_sha256, carrier_archive_sha256,
             release_root):
    for path in (root, manifest_path, release_root):
        _canonical(path)
    if not SHA256.fullmatch(carrier_archive_sha256 or ""):
        raise ValueError("CARRIER_ARCHIVE_SHA256_REQUIRED")
    manifest = verify_carrier(root, manifest_path, manifest_sha256)
    target = os.path.join(release_root, "p3-" + carrier_archive_sha256[:20])
    return _readback_target(target, manifest, manifest_sha256,
                            carrier_archive_sha256)


def recover(root, manifest_path, manifest_sha256, carrier_archive_sha256,
            release_root, state_root, attempt_id):
    """Read an interrupted attempt without repeating any write."""
    for path in (root, manifest_path, release_root, state_root):
        _canonical(path)
    if (not ATTEMPT.fullmatch(attempt_id or "")
            or not SHA256.fullmatch(carrier_archive_sha256 or "")):
        raise ValueError("VALID_ATTEMPT_AND_CARRIER_SHA_REQUIRED")
    observed = readback(root, manifest_path, manifest_sha256,
                        carrier_archive_sha256, release_root)
    intent = os.path.join(state_root, "attempts", attempt_id + ".intent.json")
    if not os.path.isfile(intent) or os.path.islink(intent):
        return dict(observed, recovery="NO_MATCHING_INTENT")
    value, _ = _read_json(intent, maximum=65536)
    if (value.get("attempt_id") != attempt_id
            or value.get("carrier_archive_sha256") != carrier_archive_sha256):
        return dict(observed, recovery="INTENT_CONFLICT_HOLD")
    if observed["state"] == "INSTALLED_DEFAULT_OFF_NOT_BOUND":
        return dict(observed, recovery="INSTALLED_EFFECT_RECOVERED_NO_REPLAY")
    return dict(observed, recovery="RESULT_MISSING_HOLD_NO_REPLAY")


def rollback(root, manifest_path, manifest_sha256, carrier_archive_sha256,
             release_root, state_root, attempt_id, fresh_authority,
             enforce_root=True):
    """Quarantine an unbound default-off release; never touch ledger/history."""
    if enforce_root and os.geteuid() != 0:
        raise PermissionError("ROOT_ROLLBACK_REQUIRED")
    for path in (root, manifest_path, release_root, state_root):
        _canonical(path)
    if (not ATTEMPT.fullmatch(attempt_id or "")
            or not SHA256.fullmatch(carrier_archive_sha256 or "")):
        raise ValueError("VALID_ATTEMPT_AND_CARRIER_SHA_REQUIRED")
    manifest = verify_carrier(root, manifest_path, manifest_sha256)
    _fresh_authority(fresh_authority)
    target = os.path.join(release_root, "p3-" + carrier_archive_sha256[:20])
    observed = _readback_target(target, manifest, manifest_sha256,
                                carrier_archive_sha256)
    if observed["state"] == "ABSENT":
        return dict(observed, idempotent=True)
    if observed["state"] != "INSTALLED_DEFAULT_OFF_NOT_BOUND":
        raise ValueError("ROLLBACK_READBACK_CONFLICT")
    receipt, _ = _read_json(os.path.join(target, "INSTALL_RECEIPT.json"), 65536)
    if receipt.get("host_bound") is not False or receipt.get("real_task_executed") is not False:
        raise PermissionError("BOUND_OR_EXECUTED_RELEASE_REQUIRES_HOST_STOP_RECONCILIATION")
    _fresh_authority(fresh_authority)
    quarantine_root = os.path.join(state_root, "rolled-back")
    os.makedirs(quarantine_root, mode=0o750, exist_ok=True)
    destination = os.path.join(quarantine_root, attempt_id)
    if os.path.lexists(destination):
        raise RuntimeError("ROLLBACK_ATTEMPT_ALREADY_EXISTS_RECONCILE_FIRST")
    os.rename(target, destination)
    _atomic_json(os.path.join(destination, "ROLLBACK_RECEIPT.json"), {
        "schema": 1, "state": "ROLLED_BACK_DEFAULT_OFF_QUARANTINED",
        "attempt_id": attempt_id,
        "carrier_archive_sha256": carrier_archive_sha256,
        "source_commit": manifest["source_commit"],
        "source_tree": manifest["source_tree"],
        "ledger_modified": False, "host_binding_modified": False,
        "evidence_preserved": True,
    })
    return {"state": "ROLLED_BACK_DEFAULT_OFF_QUARANTINED",
            "destination": destination, "verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("verify", "readback", "recover"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--carrier-archive-sha256")
    parser.add_argument("--release-root")
    parser.add_argument("--state-root")
    parser.add_argument("--attempt-id")
    args = parser.parse_args(argv)
    if args.operation == "verify":
        verify_carrier(args.root, args.manifest, args.manifest_sha256)
        print("CARRIER_OK_DEFAULT_OFF")
        return 0
    if not args.carrier_archive_sha256 or not args.release_root:
        parser.error("readback/recover require carrier archive hash and release root")
    if args.operation == "readback":
        print(json.dumps(readback(
            args.root, args.manifest, args.manifest_sha256,
            args.carrier_archive_sha256, args.release_root), sort_keys=True))
        return 0
    if args.operation == "recover":
        if not args.state_root or not args.attempt_id:
            parser.error("recover requires state root and attempt ID")
        print(json.dumps(recover(
            args.root, args.manifest, args.manifest_sha256,
            args.carrier_archive_sha256, args.release_root,
            args.state_root, args.attempt_id), sort_keys=True))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
