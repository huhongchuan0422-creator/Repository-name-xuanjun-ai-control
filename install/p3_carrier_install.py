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
import hmac
import json
import os
import re
import shutil
import stat
import sys
import tempfile

try:
    from install.p3_secure_fd import open_absolute_dir, copy_member, read_member
except ImportError:
    from p3_secure_fd import open_absolute_dir, copy_member, read_member

try:
    from install.p3_switch_journal import SwitchCoordinator
except ImportError:
    from p3_switch_journal import SwitchCoordinator


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
    if not SHA256.fullmatch(expected_manifest_sha256 or ""):
        raise ValueError("CARRIER_MANIFEST_SHA256_MISMATCH")
    relative_manifest = os.path.relpath(manifest_path, root)
    root_fd = open_absolute_dir(root, os.geteuid())
    try:
        data = read_member(root_fd, relative_manifest, os.geteuid(),
                           expected_manifest_sha256, maximum=1024*1024)
        manifest = json.loads(data.decode("utf-8"))
    finally:
        os.close(root_fd)
    keys = {
        "schema", "kind", "source_commit", "source_tree", "default_off",
        "execution_enabled", "notifications_enabled", "files",
        "release_files", "base_reviews",
    }
    if not isinstance(manifest, dict) or set(manifest) not in (keys, keys | {"artifact_digest"}):
        raise ValueError("EXACT_CARRIER_MANIFEST_REQUIRED")
    if (manifest["schema"] != 1
            or manifest["kind"] != "P3_IMMUTABLE_DEFAULT_OFF_INSTALL_CARRIER"
            or not SHA40.fullmatch(manifest["source_commit"] or "")
            or not SHA40.fullmatch(manifest["source_tree"] or "")
            or manifest["default_off"] is not True
            or manifest["execution_enabled"] is not False
            or manifest["notifications_enabled"] is not False):
        raise ValueError("CARRIER_IDENTITY_OR_DEFAULT_OFF_INVALID")
    if "artifact_digest" in manifest and not SHA256.fullmatch(manifest["artifact_digest"] or ""):
        raise ValueError("INVALID_ARTIFACT_DIGEST")
    files = manifest["files"]
    release_files = manifest["release_files"]
    if not isinstance(files, dict) or not files or not isinstance(release_files, list):
        raise ValueError("CARRIER_FILE_SET_REQUIRED")
    if not release_files or not set(release_files).issubset(set(files)):
        raise ValueError("RELEASE_FILE_SET_INVALID")
    root_fd = open_absolute_dir(root, os.geteuid())
    try:
        for name, expected in files.items():
            if (not isinstance(name, str) or name.startswith("/")
                    or ".." in name.split("/")
                    or not SHA256.fullmatch(expected or "")):
                raise ValueError("INVALID_CARRIER_MEMBER")
            try:
                read_member(root_fd, name, os.geteuid(), expected)
            except ValueError as error:
                if str(error) == "FILE_HASH_MISMATCH":
                    raise ValueError("CARRIER_MEMBER_MISMATCH:%s" % name)
                raise
    finally:
        os.close(root_fd)
    return manifest


def _fresh_authority(reader):
    if not callable(reader):
        raise PermissionError("CONTROLLED_ENTRY_AUTHORITY_READER_REQUIRED")
    # The existing controlled entry owns validation and returns True only after
    # its current P2/P3/lock/attempt/consumed-record readback.  Preserve any
    # specific exception it raises instead of replacing its evidence.
    if reader() is not True:
        raise PermissionError("CURRENT_CONTROLLED_ENTRY_AUTHORITY_REQUIRED")


def _copy_verified(source_root_fd, staging_root_fd, relative, expected):
    """Copy from pinned root into private staging; never reopen source path."""
    return copy_member(source_root_fd, staging_root_fd, relative, os.geteuid(), expected)


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
        "host_bound": False, "real_task_executed": False,
    }
    if set(receipt) != set(expected) | {"attempt_id"}:
        return {"state": "CONFLICT", "target": target,
                "field": "receipt_keys"}
    if not ATTEMPT.fullmatch(receipt.get("attempt_id") or ""):
        return {"state": "CONFLICT", "target": target,
                "field": "attempt_id"}
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


def _archive_check(archive_path, manifest, expected):
    if (not isinstance(archive_path, str) or not os.path.isabs(archive_path)
            or manifest.get("artifact_digest") != expected
            or not SHA256.fullmatch(expected or "")):
        raise ValueError("BOUND_ARCHIVE_REQUIRED")
    parent = open_absolute_dir(os.path.dirname(archive_path), os.geteuid())
    try:
        read_member(parent, os.path.basename(archive_path), os.geteuid(), expected,
                    maximum=256*1024*1024)
    finally:
        os.close(parent)


def _store_required(store):
    if store is None or not all(callable(getattr(store, name, None)) for name in ("get", "reserve", "transition", "reserve_owned", "transition_owned")):
        raise PermissionError("DURABLE_OPERATION_STORE_REQUIRED")


def _fd_receipt(staging_fd, value):
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open("INSTALL_RECEIPT.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o400, dir_fd=staging_fd)
    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(fd, encoded[offset:])
            if written <= 0: raise IOError("SHORT_RECEIPT_WRITE")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(staging_fd)


def install(root, manifest_path, manifest_sha256, carrier_archive_sha256,
            release_root, state_root, attempt_id, fresh_authority,
            enforce_root=True, operation_store=None, archive_path=None, fault_hook=None):
    if enforce_root and os.geteuid() != 0:
        raise PermissionError("ROOT_INSTALL_REQUIRED")
    _store_required(operation_store)
    for path in (root, manifest_path, release_root, state_root):
        _canonical(path)
    if not ATTEMPT.fullmatch(attempt_id or ""):
        raise ValueError("VALID_ATTEMPT_REQUIRED")
    manifest = verify_carrier(root, manifest_path, manifest_sha256)
    _archive_check(archive_path, manifest, carrier_archive_sha256)
    _fresh_authority(fresh_authority)
    parent_fd = open_absolute_dir(os.path.dirname(release_root), os.geteuid())
    try:
        name = os.path.basename(release_root)
        if name in ('', '.', '..'):
            raise ValueError("VALID_RELEASE_ROOT_REQUIRED")
        try:
            os.mkdir(name, 0o750, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
        release_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    release_info = os.fstat(release_fd)
    if release_info.st_uid != os.geteuid() or release_info.st_mode & 0o022:
        os.close(release_fd)
        raise PermissionError("UNTRUSTED_RELEASE_ROOT")
    source_fd = None
    staged = ".p3-stage-" + attempt_id
    target = "p3-" + carrier_archive_sha256[:20]
    op = "p3-install:" + attempt_id
    coordinator = SwitchCoordinator(release_fd, operation_store)
    try:
        from_stat = os.fstat(release_fd)
        stage_op = "p3-stage:" + attempt_id
        owner_fence = os.urandom(32).hex()
        owns_stage = False
        created, _ = operation_store.reserve_owned(stage_op, {"kind":"install-stage"},
            {"root_dev":from_stat.st_dev, "root_ino":from_stat.st_ino, "staged":staged,
             "target":target, "manifest_sha256":manifest_sha256,
             "artifact_digest":carrier_archive_sha256}, "stage", owner_fence)
        if not created:
            # Losing calls do not change, reconcile, clean up, or inspect staging.
            return {"state":"IN_PROGRESS_OR_HOLD", "automatic_retry":False}
        owns_stage = True
        try:
            os.stat(target, dir_fd=release_fd, follow_symlinks=False)
            raise ValueError("EXISTING_RELEASE_CONFLICT")
        except FileNotFoundError:
            pass
        os.mkdir(staged, 0o700, dir_fd=release_fd)
        os.fsync(release_fd)
        staging_fd = os.open(staged, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=release_fd)
        try:
            if os.fstat(staging_fd).st_dev != from_stat.st_dev:
                raise ValueError("CROSS_FILESYSTEM_REFUSED")
            source_fd = open_absolute_dir(root, os.geteuid())
            for name in sorted(manifest["release_files"]):
                _copy_verified(source_fd, staging_fd, name, manifest["files"][name])
            receipt = {"schema":1, "state":"INSTALLED_DEFAULT_OFF_NOT_BOUND", "attempt_id":attempt_id,
                       "source_commit":manifest["source_commit"], "source_tree":manifest["source_tree"],
                       "carrier_manifest_sha256":manifest_sha256, "carrier_archive_sha256":carrier_archive_sha256,
                       "execution_enabled":False, "notifications_enabled":False,
                       "host_bound":False, "real_task_executed":False}
            if fault_hook: fault_hook("before_receipt")
            _fd_receipt(staging_fd, receipt)
            if fault_hook: fault_hook("after_receipt")
        finally:
            if source_fd is not None: os.close(source_fd)
            os.close(staging_fd)
        _fresh_authority(fresh_authority)
        if not coordinator.prepare(op, staged, target, context={
                "manifest_sha256":manifest_sha256, "artifact_digest":carrier_archive_sha256}, require_absent=True):
            raise RuntimeError("INSTALL_ATTEMPT_RECONCILE_FIRST")
        if not operation_store.transition_owned(stage_op, owner_fence, "RUNNING", "SUCCEEDED", {"phase":"STAGED"}):
            raise RuntimeError("STAGING_JOURNAL_CONFLICT")
        result = coordinator.switch(op, staged, target, fault_hook, prepared=True)
        if result["state"] != "SWITCHED":
            return {"state":"UNKNOWN", "automatic_retry":False}
        return {"state":"INSTALLED_DEFAULT_OFF_NOT_BOUND", "attempt_id":attempt_id,
                "target":os.path.join(release_root,target), "verified":True}
    except BaseException:
        if 'owns_stage' in locals() and owns_stage:
            operation_store.transition_owned(stage_op, owner_fence, "RUNNING", "UNKNOWN", {"phase":"STAGING_UNKNOWN"})
        raise
    finally:
        coordinator.close()
        os.close(release_fd)

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
            release_root, state_root, attempt_id, operation_store=None, owner_fence=None):
    _store_required(operation_store)
    if not ATTEMPT.fullmatch(attempt_id or ""):
        raise ValueError("VALID_ATTEMPT_REQUIRED")
    stage = operation_store.get("p3-stage:" + attempt_id)
    stored_fence = stage.get("adapter_correlation") if stage else None
    if (not isinstance(owner_fence, str) or not isinstance(stored_fence, str)
            or not hmac.compare_digest(owner_fence, stored_fence)):
        return {"state":"UNKNOWN", "recovery":"OWNER_FENCE_MISMATCH_HOLD", "automatic_retry":False}
    fd = open_absolute_dir(release_root, os.geteuid())
    coordinator = SwitchCoordinator(fd, operation_store)
    try:
        op = "p3-install:" + attempt_id
        row = operation_store.get(op)
        if not row:
            return {"state":"UNKNOWN", "recovery":"RESULT_MISSING_HOLD_NO_REPLAY", "automatic_retry":False}
        binding = json.loads(row["request_json"])["admission"]
        if (binding.get("context") != {"manifest_sha256":manifest_sha256, "artifact_digest":carrier_archive_sha256}
                or binding.get("current") != "p3-" + carrier_archive_sha256[:20]):
            return {"state":"UNKNOWN", "recovery":"SCOPE_CONFLICT_HOLD", "automatic_retry":False}
        result = coordinator.reconcile(op)
        state = result["state"]
        return {"state":state,
                "recovery":"INSTALLED_EFFECT_RECOVERED_NO_REPLAY" if state == "SWITCHED" else "RESULT_MISSING_HOLD_NO_REPLAY",
                "automatic_retry":False}
    finally:
        coordinator.close(); os.close(fd)

def _rollback_checkpoint(path, manifest):
    receipt = os.path.join(path, "INSTALL_RECEIPT.json")
    if os.path.islink(receipt) or not os.path.isfile(receipt):
        raise ValueError("ROLLBACK_INSTALL_RECEIPT_MISSING")
    members = {}
    for name in manifest["release_files"]:
        member = os.path.join(path, name)
        if os.path.islink(member) or not os.path.isfile(member):
            raise ValueError("ROLLBACK_MEMBER_MISSING:%s" % name)
        members[name] = _digest(member)
    return {"install_receipt_sha256": _digest(receipt), "members": members}


def _rollback_receipt(attempt_id, carrier_archive_sha256, manifest):
    return {
        "schema": 1, "state": "ROLLED_BACK_DEFAULT_OFF_QUARANTINED",
        "attempt_id": attempt_id,
        "carrier_archive_sha256": carrier_archive_sha256,
        "source_commit": manifest["source_commit"],
        "source_tree": manifest["source_tree"],
        "ledger_modified": False, "host_binding_modified": False,
        "evidence_preserved": True,
    }


def rollback(root, manifest_path, manifest_sha256, carrier_archive_sha256,
             release_root, state_root, attempt_id, fresh_authority,
             enforce_root=True, operation_store=None, original_install_attempt=None,
             fault_hook=None):
    if enforce_root and os.geteuid() != 0:
        raise PermissionError("ROOT_ROLLBACK_REQUIRED")
    _store_required(operation_store)
    if not ATTEMPT.fullmatch(attempt_id or "") or not ATTEMPT.fullmatch(original_install_attempt or ""):
        raise ValueError("VALID_ATTEMPTS_REQUIRED")
    _fresh_authority(fresh_authority)
    original = operation_store.get("p3-install:"+original_install_attempt)
    if not original:
        return {"state":"UNKNOWN", "automatic_retry":False}
    binding = json.loads(original["request_json"])["admission"]
    if (binding.get("context") != {"manifest_sha256":manifest_sha256, "artifact_digest":carrier_archive_sha256}
            or binding.get("current") != "p3-" + carrier_archive_sha256[:20]):
        return {"state":"UNKNOWN", "automatic_retry":False}
    fd = open_absolute_dir(release_root, os.geteuid())
    coordinator = SwitchCoordinator(fd, operation_store)
    try:
        result = coordinator.rollback("p3-rollback:"+attempt_id,
                                      "p3-install:"+original_install_attempt, fault_hook)
        if result["state"] != "ROLLED_BACK":
            return {"state":"UNKNOWN", "automatic_retry":False}
        return {"state":"ROLLED_BACK_DEFAULT_OFF_QUARANTINED", "verified":True,
                "recovery":"ROLLBACK_EFFECT_RECOVERED_NO_REPLAY"}
    finally:
        coordinator.close(); os.close(fd)

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
        parser.error("recover requires a host-injected durable OperationStore; CLI recovery is disabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
