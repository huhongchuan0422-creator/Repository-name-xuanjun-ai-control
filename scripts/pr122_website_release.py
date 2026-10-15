#!/usr/bin/env python3
"""Fail-closed offline candidate release transaction for PR122."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import sys
import tarfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

SOURCE_PREFIX = "package/public/"


class Hold(RuntimeError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def safe_relative(name: str) -> Path:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise Hold("UNSAFE_ARCHIVE_MEMBER_PATH")
    return Path(*pure.parts)


@contextmanager
def lock(base: Path, wait_seconds: float):
    base.mkdir(parents=True, exist_ok=True, mode=0o755)
    lock_path = base / ".release.lock"
    handle = lock_path.open("a+")
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                raise Hold("LOCK_TIMEOUT")
            time.sleep(0.05)
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def verify_tree(public: Path, manifest: dict, deadline: float) -> None:
    if time.monotonic() > deadline:
        raise Hold("VERIFY_TIMEOUT")
    expected = {item["path"]: item for item in manifest["files"]}
    actual = {}
    for path in public.rglob("*"):
        if time.monotonic() > deadline:
            raise Hold("VERIFY_TIMEOUT")
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise Hold("UNSAFE_RELEASE_OBJECT")
        if path.is_file():
            relative = path.relative_to(public).as_posix()
            actual[relative] = {"size": path.stat().st_size, "sha256": digest(path)}
    if set(actual) != set(expected):
        raise Hold("RELEASE_FILE_SET_MISMATCH")
    for name, wanted in expected.items():
        if actual[name] != {"size": wanted["size"], "sha256": wanted["sha256"]}:
            raise Hold("RELEASE_CONTENT_MISMATCH:" + name)


def extract_source(source: Path, public: Path, source_pin: dict, deadline: float) -> None:
    if source.stat().st_size != source_pin["source_archive_size"] or digest(source) != source_pin["source_archive_sha256"]:
        raise Hold("SOURCE_ARCHIVE_IDENTITY_MISMATCH")
    with tarfile.open(source, "r:gz") as archive:
        seen = set()
        for member in archive.getmembers():
            if time.monotonic() > deadline:
                raise Hold("EXTRACT_TIMEOUT")
            safe_relative(member.name)
            if member.name in seen:
                raise Hold("DUPLICATE_SOURCE_MEMBER")
            seen.add(member.name)
            if not (member.isdir() or member.isfile()):
                raise Hold("UNSAFE_SOURCE_MEMBER_TYPE")
            if member.name in ("package", "package/public") or member.name.startswith("package/public/"):
                if member.isdir():
                    continue
                if not member.isfile():
                    raise Hold("UNSAFE_SOURCE_MEMBER_TYPE")
                relative_name = member.name[len(SOURCE_PREFIX):]
                if not relative_name:
                    continue
                relative = safe_relative(relative_name)
                target = public / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                source_handle = archive.extractfile(member)
                with target.open("wb") as output:
                    shutil.copyfileobj(source_handle, output)
                os.chmod(target, 0o644)


def prepare(args) -> dict:
    bundle = args.bundle.resolve()
    base = args.webroot_base.resolve()
    releases = base / "releases"
    transactions = base / "transactions"
    releases.mkdir(parents=True, exist_ok=True, mode=0o755)
    transactions.mkdir(parents=True, exist_ok=True, mode=0o700)
    release = releases / args.release_id
    receipt_path = transactions / (args.transaction_id + ".json")
    if release.exists() or receipt_path.exists():
        raise Hold("TARGET_OR_TRANSACTION_ALREADY_EXISTS")
    deadline = time.monotonic() + args.deadline_seconds
    manifest = load(bundle / "candidate-manifest.json")
    pin = load(bundle / "source-pin.json")
    staging = base / (".staging-" + args.transaction_id)
    receipt = {"schema_version": 1, "transaction_id": args.transaction_id, "release_id": args.release_id,
               "state": "STARTED", "release": str(release), "previous_current": None}
    atomic_json(receipt_path, receipt)
    try:
        staging.mkdir(mode=0o700)
        public = staging / "public"
        public.mkdir(mode=0o755)
        extract_source(args.source_archive, public, pin, deadline)
        for path, baseline in pin["overlay_baselines"].items():
            target = public / path
            if not target.is_file() or digest(target) != baseline:
                raise Hold("OVERLAY_BASELINE_DRIFT:" + path)
            overlay = bundle / "overlay" / "public" / path
            if not overlay.is_file():
                raise Hold("OVERLAY_MISSING:" + path)
            shutil.copyfile(overlay, target)
            os.chmod(target, 0o644)
        verify_tree(public, manifest, deadline)
        os.replace(staging, release)
        receipt["state"] = "PREPARED"
        receipt["candidate_manifest_sha256"] = digest(bundle / "candidate-manifest.json")
        atomic_json(receipt_path, receipt)
        return receipt
    except Exception:
        receipt["state"] = "HOLD_PARTIAL"
        atomic_json(receipt_path, receipt)
        raise


def activate(args) -> dict:
    base = args.webroot_base.resolve()
    receipt_path = base / "transactions" / (args.transaction_id + ".json")
    receipt = load(receipt_path)
    if receipt.get("state") != "PREPARED" or receipt.get("release_id") != args.release_id:
        raise Hold("TRANSACTION_NOT_PREPARED")
    release = (base / "releases" / args.release_id).resolve()
    if not release.is_dir() or release != Path(receipt["release"]).resolve():
        raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
    current = base / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    if current.exists() and not current.is_symlink():
        raise Hold("CURRENT_NOT_SYMLINK")
    temporary = base / (".current-" + args.transaction_id)
    if temporary.exists() or temporary.is_symlink():
        raise Hold("TEMPORARY_POINTER_EXISTS")
    os.symlink(str(release), temporary)
    os.replace(temporary, current)
    if not current.is_symlink() or current.resolve() != release:
        receipt.update({"state": "UNKNOWN_AFTER_ACTIVATE", "previous_current": previous})
        atomic_json(receipt_path, receipt)
        raise Hold("ACTIVATION_RESULT_UNKNOWN")
    receipt.update({"state": "ACTIVATED", "previous_current": previous})
    atomic_json(receipt_path, receipt)
    return receipt


def check(args) -> dict:
    base = args.webroot_base.resolve()
    receipt_path = base / "transactions" / (args.transaction_id + ".json")
    receipt = load(receipt_path)
    if receipt.get("release_id") != args.release_id or receipt.get("state") != "ACTIVATED":
        raise Hold("TRANSACTION_NOT_ACTIVATED")
    current = base / "current"
    expected = (base / "releases" / args.release_id).resolve()
    if not current.is_symlink() or current.resolve() != expected:
        receipt["state"] = "UNKNOWN_AFTER_CHECK"
        atomic_json(receipt_path, receipt)
        raise Hold("CURRENT_RELEASE_MISMATCH")
    manifest = load(args.bundle.resolve() / "candidate-manifest.json")
    try:
        verify_tree(current / "public", manifest, time.monotonic() + args.deadline_seconds)
    except Hold:
        receipt["state"] = "CHECK_FAILED"
        atomic_json(receipt_path, receipt)
        raise
    receipt["state"] = "CHECKED"
    atomic_json(receipt_path, receipt)
    return {"state": "PASS", "release_id": args.release_id}


def rollback(args) -> dict:
    base = args.webroot_base.resolve()
    receipt_path = base / "transactions" / (args.transaction_id + ".json")
    receipt = load(receipt_path)
    current = base / "current"
    installed = (base / "releases" / receipt["release_id"]).resolve()
    if receipt.get("state") not in {"ACTIVATED", "CHECKED", "CHECK_FAILED", "UNKNOWN_AFTER_CHECK"}:
        raise Hold("TRANSACTION_NOT_ROLLBACK_ELIGIBLE")
    if not current.is_symlink() or current.resolve() != installed:
        raise Hold("CURRENT_IDENTITY_UNKNOWN_NO_ROLLBACK")
    previous = receipt.get("previous_current")
    if previous is None:
        current.unlink()
        if current.exists() or current.is_symlink():
            raise Hold("ROLLBACK_RESULT_UNKNOWN")
    else:
        previous_path = Path(previous)
        if not previous_path.is_absolute():
            previous_path = (base / previous_path).resolve()
        if not previous_path.is_dir():
            raise Hold("PREVIOUS_RELEASE_MISSING")
        temporary = base / (".rollback-" + args.transaction_id)
        os.symlink(previous, temporary)
        os.replace(temporary, current)
        if current.resolve() != previous_path.resolve():
            raise Hold("ROLLBACK_RESULT_UNKNOWN")
    receipt["state"] = "ROLLED_BACK"
    atomic_json(receipt_path, receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("command", choices=("prepare", "activate", "check", "rollback"))
    value.add_argument("--webroot-base", type=Path, required=True)
    value.add_argument("--bundle", type=Path)
    value.add_argument("--source-archive", type=Path)
    value.add_argument("--transaction-id", required=True)
    value.add_argument("--release-id", required=True)
    value.add_argument("--lock-wait-seconds", type=float, default=5)
    value.add_argument("--deadline-seconds", type=float, default=120)
    value.add_argument("--allow-non-root-test", action="store_true", help=argparse.SUPPRESS)
    return value


def main() -> int:
    args = parser().parse_args()
    if os.geteuid() != 0 and not args.allow_non_root_test:
        print(json.dumps({"state": "HOLD", "reason": "ROOT_REQUIRED"}), file=sys.stderr)
        return 77
    try:
        with lock(args.webroot_base.resolve(), args.lock_wait_seconds):
            if args.command == "prepare":
                if not args.bundle or not args.source_archive:
                    raise Hold("PREPARE_INPUT_REQUIRED")
                result = prepare(args)
            elif args.command == "activate":
                result = activate(args)
            elif args.command == "check":
                if not args.bundle:
                    raise Hold("CHECK_BUNDLE_REQUIRED")
                result = check(args)
            else:
                result = rollback(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Hold, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"state": "HOLD", "reason": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
