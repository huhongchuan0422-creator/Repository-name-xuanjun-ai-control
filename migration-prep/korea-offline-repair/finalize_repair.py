"""Separate admitted postflight of one exact stopped, partially completed repair.

Never calls apply(), rewrites unit/transaction, reloads or controls a service.
The old HOLD receipt remains immutable history; this emits a linked supplement.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

CHECKER_SHA = "f524d6408f5b39414391b5c4f93b7a13a052abb4fb9945ff8b3194b1b32bbc9f"
source = Path(__file__).with_name("controlled_repair.py")
if hashlib.sha256(source.read_bytes()).hexdigest() != CHECKER_SHA:
    raise RuntimeError("CHECKER_SOURCE_CHANGED")
spec = importlib.util.spec_from_file_location("pr99_finalizer_core", source)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

ACTION = "PR99_PHASE_B_OFFLINE_REPAIR_FINALIZE_V1"
PIN = "/etc/xuanjun-pr99-release/offline-finalize-admission.json"
WORK = "/var/lib/xuanjun-pr99-offline-finalize-v1"
UNIT_SHA = "824fc0cbe3d879b61ea36b0bd7c45fb8c1e9fb6c463f46ada741ac3f2299899b"
NEW_TX_SHA = "ee81a70bb417e66dbb58bad5a79a776d1e7a0bce35d0e72bf638a2fe0844eb75"


class Context(c.Context):
    final_transaction_sha = NEW_TX_SHA
    prior_source = "bf9373ab6ba2d02dbb7cb5e421cc74632d2cc794"
    prior_artifact = "4c351cdd87a4997c91d311b0345e6dd78192886f4aa657932d549c51af1f016b"


def admission(ctx, binding, files, archive_sha):
    p = ctx.path(PIN)
    c.trusted(p.parent, ctx, directory=True, private=True)
    pin = json.loads(c.read(p, ctx, private=True))
    body = pin["approval_body"]
    c.require(c.sha(body.encode()) == pin["approval_body_sha256"], "APPROVAL_BODY_HASH")
    start = "<!-- PR99_OFFLINE_FINALIZE_APPROVAL_V1\n"
    end = "\nPR99_OFFLINE_FINALIZE_APPROVAL_V1 -->"
    c.require(body.count(start) == body.count(end) == 1, "APPROVAL_MARKER")
    a = json.loads(body.split(start)[1].split(end)[0])
    expected = {"schema_version": 1, "action": ACTION, "host": c.HOST,
                "source_commit": binding["source_commit"], "artifact_sha256": archive_sha,
                "finalizer_sha256": c.sha(files["finalize_repair.py"]), "checker_sha256": CHECKER_SHA,
                "unit_sha256": UNIT_SHA, "transaction_sha256": ctx.final_transaction_sha,
                "prior_repair_approval_comment_id": 6208184098, "max_attempts": 1,
                "adopt_root_verified_retained_lock": True, "unit_write_allowed": False,
                "transaction_write_allowed": False, "reload_allowed": False,
                "service_start_allowed": False, "phase_c_allowed": False}
    c.require(set(a) == set(expected) | {"approval_comment_id", "issued_at", "expires_at"}, "APPROVAL_FIELDS")
    for k, v in expected.items():
        c.require(type(a[k]) is type(v) and a[k] == v, "APPROVAL_SCOPE_MISMATCH")
    c.require(type(a["approval_comment_id"]) is int and a["approval_comment_id"] == pin["approval_comment_id"]
              and a["approval_comment_id"] not in (6208184098, 6207630392), "OLD_OR_WRONG_APPROVAL")
    c.require(type(a["issued_at"]) is int and type(a["expires_at"]) is int
              and a["issued_at"] <= time.time() < a["expires_at"]
              and 0 < a["expires_at"] - a["issued_at"] <= 43200, "APPROVAL_EXPIRED")
    return a, pin


def finalize(folder, archive, ctx):
    binding, files, archive_sha = c.package_files(folder, archive, ctx)
    c.require(c.sha(files["offline.service"]) == UNIT_SHA, "UNIT_PACKAGE_CHANGED")
    a, pin = admission(ctx, binding, files, archive_sha)
    c.require(c.absent(ctx.path(WORK)), "FINALIZE_ALREADY_ATTEMPTED_NO_RETRY")
    old_work = ctx.path(c.WORK)
    c.trusted(old_work, ctx, directory=True, private=True)
    old_receipt_bytes = c.read(old_work / "receipt.json", ctx, private=True)
    c.require(c.sha(old_receipt_bytes) == pin["failed_receipt_sha256"], "FAILED_RECEIPT_CHANGED")
    old_receipt = json.loads(old_receipt_bytes)
    required = {"status": "HOLD_PRESERVE_EVIDENCE", "phase": "replace_unit",
                "error": "MANAGER_NETWORK_PROFILE_NOT_LOADED", "action": c.ACTION,
                "host": c.HOST, "approval_comment_id": 6208184098,
                "source_commit": ctx.prior_source, "artifact_sha256": ctx.prior_artifact,
                "service_started": False, "runtime_changed": False, "credentials_read": False,
                "binance_called": False, "automatic_retry_allowed": False}
    for k, v in required.items():
        c.require(type(old_receipt.get(k)) is type(v) and old_receipt[k] == v, "FAILED_RECEIPT_SCOPE_MISMATCH")
    # The first helper did NOT persist its lock inode. Do not invent provenance:
    # a NEW approval expressly permits Owner-root to adopt the currently empty,
    # private retained lock, binding its actual dev/inode in the private anchor.
    lock = ctx.path("/run/xuanjun-binance-install.lock")
    info = c.trusted(lock, ctx, directory=True, private=True)
    lock_identity = {"device": info.st_dev, "inode": info.st_ino}
    c.require(pin["retained_lock"] == lock_identity and not list(lock.iterdir()), "RETAINED_LOCK_IDENTITY_OR_CONTENT")
    work = ctx.path(WORK)
    c.trusted(work.parent, ctx, directory=True)
    work.mkdir(mode=0o700)
    c.sync_directory(work.parent)
    rp = work / "receipt.json"
    receipt = {"schema_version": 1, "action": ACTION, "host": c.HOST,
               "status": "STARTED_PRESERVE_EVIDENCE", "approval_comment_id": a["approval_comment_id"],
               "source_commit": binding["source_commit"], "artifact_sha256": archive_sha,
               "prior_failed_receipt_sha256": c.sha(old_receipt_bytes), "retained_lock": lock_identity,
               "lock_origin": "EXPLICIT_NEW_OWNER_ROOT_ADOPTION_NOT_HISTORICAL_INODE_PROOF",
               "unit_rewritten": False, "transaction_rewritten": False, "reload": False,
               "service_started": False, "credentials_read": False, "binance_called": False,
               "retry_allowed": False, "started_service_confinement": "NOT_EXERCISED"}
    c.atomic(rp, c.encoded(receipt), 0o600, ctx)
    try:
        c.atomic(work / "prior-failed-receipt.json", old_receipt_bytes, 0o600, ctx)
        old_tx_bytes = c.read(old_work / "transaction.before.json", ctx, private=True)
        c.require(c.sha(old_tx_bytes) == ctx.old_tx_sha, "OLD_TRANSACTION_BACKUP_CHANGED")
        c.require(c.sha(c.read(old_work / "unit.before", ctx, private=True)) == c.OLD_UNIT, "OLD_UNIT_BACKUP_CHANGED")
        tx_bytes = c.read(ctx.path(c.TX), ctx, private=True)
        c.require(c.sha(tx_bytes) == ctx.final_transaction_sha, "FINAL_TRANSACTION_CHANGED")
        tx = json.loads(tx_bytes)
        expected = dict(json.loads(old_tx_bytes), unit_sha256=UNIT_SHA)
        c.require(tx == expected, "TRANSACTION_DELTA_NOT_UNIT_HASH_ONLY")
        c.require(c.read(ctx.path(c.UNIT), ctx) == files["offline.service"], "FINAL_UNIT_CHANGED")
        c.verify(ctx, ctx.path(c.UNIT))
        c.service(ctx, True)  # exact typed D-Bus, never systemctl's placeholder
        c.runtime(ctx, files)
        c.trusted(ctx.path("/opt/xuanjun-binance/venv"), ctx, directory=True)
        python = ctx.path("/opt/xuanjun-binance/venv/bin/python").resolve(strict=True)
        c.require(c.sha(c.read(python, ctx)) == tx["venv_python_sha256"], "VENV_PYTHON_CHANGED")
        before = c.read(old_work / "shared.before.json", ctx, private=True)
        c.require(c.shared(ctx) == before, "SHARED_NAMED_UNITS_CHANGED")
        ctx.checkpoint("finalize_before_unlock")
        c.require(time.time() < a["expires_at"], "APPROVAL_EXPIRED_BEFORE_UNLOCK")
        c.require(c.read(old_work / "receipt.json", ctx, private=True) == old_receipt_bytes, "FAILED_RECEIPT_CHANGED")
        c.require(c.read(ctx.path(c.TX), ctx, private=True) == tx_bytes, "FINAL_TRANSACTION_CHANGED")
        c.require(c.read(ctx.path(c.UNIT), ctx) == files["offline.service"], "FINAL_UNIT_CHANGED")
        c.service(ctx, True)
        s = c.trusted(lock, ctx, directory=True, private=True)
        c.require({"device": s.st_dev, "inode": s.st_ino} == lock_identity and not list(lock.iterdir()),
                  "RETAINED_LOCK_IDENTITY_OR_CONTENT")
        lock.rmdir()  # only the exact adopted empty root directory; never rm -r
        c.sync_directory(lock.parent)
        receipt.update(status="OFFLINE_REPAIR_FINALIZE_PASS_WITH_SCOPE_LIMITS", lock_released=True,
                       unit_sha256=UNIT_SHA, transaction_sha256=ctx.final_transaction_sha,
                       runtime_manifest_sha256=c.OLD_MANIFEST, runtime_files_unchanged=17,
                       private_network=True, address_family_allowlist=["AF_UNIX"],
                       shared_named_unit_metadata_unchanged=True, phase_c="NOT_AUTHORIZED")
        c.atomic(rp, c.encoded(receipt), 0o600, ctx, rp.read_bytes())
    except BaseException as e:
        receipt.update(status="HOLD_PRESERVE_EVIDENCE", error=str(e) if isinstance(e, c.Hold) else type(e).__name__)
        c.atomic(rp, c.encoded(receipt), 0o600, ctx, rp.read_bytes())
        raise
    return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--package", required=True, type=Path)
    p.add_argument("--archive", required=True, type=Path)
    args = p.parse_args()
    try:
        c.require(os.geteuid() == 0 and os.uname().nodename == c.HOST, "WRONG_ROOT_OR_HOST")
        c.require(not any(k.startswith(("KOREA_", "PYTHON")) for k in os.environ), "UNCLEAN_EXECUTION_ENVIRONMENT")
        c.require(Path(__file__).resolve() == args.package / "finalize_repair.py", "FINALIZER_PACKAGE_PATH")
        os.umask(0o077)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(c.Hold("SIGTERM")))
        print(json.dumps(finalize(args.package, args.archive, Context()), sort_keys=True))
    except BaseException as e:
        print(json.dumps({"status": "HOLD_PRESERVE_EVIDENCE", "reason": str(e) if isinstance(e, c.Hold) else type(e).__name__,
                          "retry_allowed": False}), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
