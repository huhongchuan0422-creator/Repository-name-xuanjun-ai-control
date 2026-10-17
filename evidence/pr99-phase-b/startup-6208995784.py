"""Owner-root handoff for permit 6208995784; reviewed finalizer stays unchanged."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request

HOST = "iZmj7a5kwr75qc1tul4kf9Z"
STAGE = Path("/root/pr99-offline-finalize-19f0e27d-b")
OLD = Path("/root/pr99-offline-finalize-19f0e27d/review.tar.gz")
PIN = Path("/etc/xuanjun-pr99-release/offline-finalize-admission.json")
ATTEMPT = Path("/var/lib/xuanjun-pr99-offline-finalize-v1")
LOCK = Path("/run/xuanjun-binance-install.lock")
RECEIPT = Path("/var/lib/xuanjun-pr99-offline-repair-v1/receipt.json")
BODY_SHA = "0b81f5a6049eb7626eef547de3643810e7e68efb7dbfa390185b05b6d09a1414"
ANCHOR_SHA = "44701367ce05fd904429a64dc65900a4d96bbaadc323155983b813a55945fadf"
OLD_BODY_SHA = "c0c9d5d51ceb96b551c032cfa32f9a7020f67a4560281badbcb095ea034943f5"
TAR_SHA = "35caaf41040c734565e68ff0c3a25a40be7304b1d58838596aa73f5acb23ff24"
SOURCE = "19f0e27de89b50eb990573f5b2a3ad13bdd7b3eb"
FINALIZER_SHA = "99565713e359cb583563b2d673282439aae55022d88ee3d3cb189758fe51134a"
CHECKER_SHA = "f524d6408f5b39414391b5c4f93b7a13a052abb4fb9945ff8b3194b1b32bbc9f"
UNIT_SHA = "824fc0cbe3d879b61ea36b0bd7c45fb8c1e9fb6c463f46ada741ac3f2299899b"
TX_SHA = "ee81a70bb417e66dbb58bad5a79a776d1e7a0bce35d0e72bf638a2fe0844eb75"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def trusted(p, directory=False, private=False):
    for parent in reversed(p.parents):
        s = parent.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             "UNTRUSTED_PARENT:" + str(parent))
    s = p.lstat()
    need((stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))
         and s.st_uid == 0 and not s.st_mode & 0o022, "UNTRUSTED_PATH:" + str(p))
    if private:
        need(stat.S_IMODE(s.st_mode) == (0o700 if directory else 0o600), "PRIVATE_MODE:" + str(p))
    return s


def read(p, private=False):
    s = trusted(p, private=private)
    need(s.st_size <= 2000000, "INPUT_SIZE")
    return p.read_bytes()


def sync(p):
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(p, data):
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def main():
    need(os.geteuid() == 0 and os.uname().nodename == HOST, "WRONG_ROOT_OR_HOST")
    need(sys.version_info[:2] == (3, 11) and sys.flags.isolated and sys.dont_write_bytecode,
         "REQUIRE_PYTHON311_ISOLATED_MINUS_B")
    need(not any(k.startswith(("PYTHON", "KOREA_")) for k in os.environ), "UNCLEAN_ENV")
    os.umask(0o077)
    trusted(STAGE.parent, directory=True)
    need(not os.path.lexists(STAGE), "NEW_STAGE_EXISTS_NO_RETRY")
    trusted(PIN.parent, directory=True, private=True)
    old_pin = read(PIN, private=True)
    need(sha(old_pin) == ANCHOR_SHA, "OLD_ANCHOR_CHANGED")
    pin = json.loads(old_pin)
    need(pin["approval_comment_id"] == 6208552859
         and pin["approval_body_sha256"] == OLD_BODY_SHA
         and sha(pin["approval_body"].encode()) == OLD_BODY_SHA, "OLD_APPROVAL_CHANGED")
    identity = {"device": 25, "inode": 4716}

    def check_scene():
        need(not os.path.lexists(ATTEMPT), "FINALIZE_ATTEMPT_EXISTS_NO_RETRY")
        need(read(PIN, private=True) == old_pin, "ANCHOR_CONCURRENT_CHANGE")
        s = trusted(LOCK, directory=True, private=True)
        need({"device": s.st_dev, "inode": s.st_ino} == identity == pin["retained_lock"]
             and not list(LOCK.iterdir()), "LOCK_CHANGED")
        need(sha(read(RECEIPT, private=True)) == pin["failed_receipt_sha256"], "OLD_RECEIPT_CHANGED")
        need(sha(read(Path("/etc/systemd/system/xuanjun-binance-shadow.service"))) == UNIT_SHA,
             "INSTALLED_UNIT_CHANGED")
        need(sha(read(Path("/etc/xuanjun-binance/install-transaction.json"), private=True)) == TX_SHA,
             "TRANSACTION_CHANGED")

    check_scene()
    url = "https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/issues/comments/6208995784"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=20) as response:
        data = response.read(200001)
    need(len(data) <= 200000, "APPROVAL_RESPONSE_TOO_LARGE")
    record = json.loads(data)
    body = record["body"]
    need(record["id"] == 6208995784 and sha(body.encode()) == BODY_SHA, "NEW_APPROVAL_HASH")
    start, end = "<!-- PR99_OFFLINE_FINALIZE_APPROVAL_V1\n", "\nPR99_OFFLINE_FINALIZE_APPROVAL_V1 -->"
    need(body.count(start) == body.count(end) == 1, "APPROVAL_MARKER")
    a = json.loads(body.split(start)[1].split(end)[0])
    expected = {"schema_version": 1, "action": "PR99_PHASE_B_OFFLINE_REPAIR_FINALIZE_V1",
                "host": HOST, "source_commit": SOURCE, "artifact_sha256": TAR_SHA,
                "finalizer_sha256": FINALIZER_SHA, "checker_sha256": CHECKER_SHA,
                "unit_sha256": UNIT_SHA, "transaction_sha256": TX_SHA,
                "prior_repair_approval_comment_id": 6208184098, "max_attempts": 1,
                "adopt_root_verified_retained_lock": True, "unit_write_allowed": False,
                "transaction_write_allowed": False, "reload_allowed": False,
                "service_start_allowed": False, "phase_c_allowed": False,
                "approval_comment_id": 6208995784, "issued_at": 1792129592, "expires_at": 1792136792}
    need(set(a) == set(expected) and all(type(a[k]) is type(v) and a[k] == v
         for k, v in expected.items()), "NEW_APPROVAL_SCOPE")
    need(a["issued_at"] <= time.time() < a["expires_at"], "APPROVAL_EXPIRED")
    raw = read(OLD, private=True)
    need(sha(raw) == TAR_SHA, "ORIGINAL_TAR_HASH")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for m in archive.getmembers():
            p = PurePosixPath(m.name)
            need(m.isfile() and len(p.parts) == 1 and p.as_posix() == m.name
                 and m.name not in (".", "..") and m.name not in files
                 and m.size <= 2000000, "ARCHIVE_MEMBER")
            files[m.name] = archive.extractfile(m).read()
    binding = json.loads(files["REPAIR_BINDING.json"])
    need(binding["source_commit"] == SOURCE and len(binding["files"]) == 9
         and set(files) == set(binding["files"]) | {"REPAIR_BINDING.json"}, "BINDING_SET")
    need(all(sha(files[k]) == v for k, v in binding["files"].items()), "BINDING_HASH")
    need(sha(files["finalize_repair.py"]) == FINALIZER_SHA
         and sha(files["controlled_repair.py"]) == CHECKER_SHA, "ENTRY_HASH")
    check_scene()
    STAGE.mkdir(mode=0o700)
    sync(STAGE.parent)
    package = STAGE / "package"
    package.mkdir(mode=0o700)
    write_new(STAGE / "review.tar.gz", raw)
    for name, content in files.items():
        write_new(package / name, content)
    sync(package)
    write_new(STAGE / "anchor.before.json", old_pin)
    write_new(STAGE / "approval-body.txt", body.encode())
    sync(STAGE)
    spec = importlib.util.spec_from_file_location("approved_finalizer", package / "finalize_repair.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = module.Context()
    module.c.package_files(package, STAGE / "review.tar.gz", ctx)
    check_scene()
    need(time.time() < a["expires_at"], "APPROVAL_EXPIRED_BEFORE_ANCHOR")
    updated = dict(pin, approval_comment_id=6208995784, approval_body_sha256=BODY_SHA, approval_body=body)
    module.c.atomic(PIN, module.c.encoded(updated), 0o600, ctx, expected=old_pin)
    print("ROOT_ANCHOR_UPDATED; START_ONE_FINALIZER_MINUS_B; LOGS=" + str(STAGE), flush=True)
    command = ["/usr/bin/python3.11", "-I", "-B", "-u", str(package / "finalize_repair.py"),
               "--package", str(package), "--archive", str(STAGE / "review.tar.gz")]
    with (STAGE / "finalize.log").open("xb") as log:
        result = subprocess.run(command, env=ENV, stdout=log, stderr=log, timeout=240)
    print((STAGE / "finalize.log").read_text()[-12000:], flush=True)
    need(result.returncode == 0, "FINALIZER_NONZERO_PRESERVE_EVIDENCE")
    outcome = json.loads(read(ATTEMPT / "receipt.json", private=True))
    need(outcome["status"] == "OFFLINE_REPAIR_FINALIZE_PASS_WITH_SCOPE_LIMITS"
         and outcome["approval_comment_id"] == 6208995784 and outcome["lock_released"] is True
         and not os.path.lexists(LOCK), "FINAL_RECEIPT_OR_LOCK")
    print("FINALIZE_EXIT=0 REINSTALL=NO RELOAD=NO SERVICE_START=NO PHASE_C=HOLD TOKYO=UNCHANGED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print("HOLD_PRESERVE_EVIDENCE NO_RETRY: " + str(error) + "; LOGS=" + str(STAGE), flush=True)
        sys.exit(2)
