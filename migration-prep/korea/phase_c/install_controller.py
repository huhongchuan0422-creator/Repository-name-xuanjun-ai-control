"""Single-use installation of a NEW stopped C candidate, preserving frozen B.

The production CLI has no alternate root, model flag, service-start action or
credential/DB provider. Context injection is Python-test-only. No root action
is authorized by this source file or by its tests.
"""
import argparse
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import grp
import re
import shlex
import signal
import stat
import subprocess
import sys
import time
import tarfile
import urllib.request

from gate_common import canonical_bytes, require
from korea.phase_c import artifact
from korea.phase_c.authorization import HOST, INSTALL_ACTION, verify_approval
from korea.phase_c.entry import validate_config
from korea.phase_c.network import compile_rules, validate_policy
from korea.phase_c.prepare import render_units
from korea.phase_c.security import (digest, fsync_dir, hash_value, identifier, read_file,
                                    rename_new, strict_json, trusted_directory, write_once)
from korea.shadow_acceptance import ACCEPTANCE_FIELDS

WORK = "/var/lib/xuanjun-pr99-phase-c-install-v1"
LOCK = "/run/xuanjun-pr99-phase-c-install.lock"
PIN = "/etc/xuanjun-pr99-release/phase-c-offline-install-admission.json"
PUBLIC = "/var/lib/xuanjun-pr99-phase-c-install-receipt.json"
B_MANIFEST = "f887b085508e3ed4831dbed22152e35af5e8aba95b85b899b4697c61449917de"
B_RELEASE = "/opt/xuanjun-binance/releases/f887b085508e3ed4"
B_UNIT_SHA = "824fc0cbe3d879b61ea36b0bd7c45fb8c1e9fb6c463f46ada741ac3f2299899b"
B_TX_SHA = "ee81a70bb417e66dbb58bad5a79a776d1e7a0bce35d0e72bf638a2fe0844eb75"
SHARED = ("morelogin-socks5-permanent.service", "xuanjun-novel-factory.service",
          "postgresql.service", "redis.service", "yibi-api.service", "yibi-scheduler.service")
UNITS = {"broker.service": "xuanjun-binance-phase-c-broker.service",
         "worker.service": "xuanjun-binance-phase-c-worker.service",
         "controller.service": "xuanjun-binance-phase-c-controller.service",
         "network-verified.target": "xuanjun-phase-c-network-verified.target"}
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}


class Context:
    b_unit_sha = B_UNIT_SHA
    b_transaction_sha = B_TX_SHA
    b_manifest_sha = B_MANIFEST
    def path(self, value):
        return Path(value)

    def now(self):
        return time.time()

    def check_identity(self):
        require(os.geteuid() == 0 and os.uname().nodename == HOST, "C_CONTROLLER_ROOT_HOST")
        # CPython may add LC_CTYPE=C.UTF-8 under env-i/LANG=C (PEP538).
        require(set(os.environ) <= {"PATH", "LANG", "LC_ALL", "LC_CTYPE"} and
                os.environ.get("PATH") == ENV["PATH"] and os.environ.get("LANG") == "C" and
                all(os.environ.get(k, "C") in ("C", "C.UTF-8", "C.utf8") for k in ("LC_ALL", "LC_CTYPE")),
                "C_CONTROLLER_CLEAN_ENV_REQUIRED")

    def current_approval(self, comment_id):
        url = ("https://api.github.com/repos/huhongchuan0422-creator/"
               "Repository-name-xuanjun-ai-control/issues/comments/" + str(comment_id))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=20) as response:
            data = response.read(200001)
        require(0 < len(data) <= 200000, "C_CURRENT_APPROVAL_SIZE")
        record = strict_json(data)
        require(type(record["id"]) is int and record["id"] == comment_id and
                type(record["body"]) is str, "C_CURRENT_APPROVAL_ID")
        return record["body"]

    def run(self, args):
        program = Path(args[0]).resolve(strict=True)
        trusted_directory(program.parent)
        s = program.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
                "C_SYSTEM_PROGRAM_IDENTITY")
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=ENV, timeout=30)
        require(len(result.stdout.encode()) + len(result.stderr.encode()) <= 4 * 1024 * 1024,
                "C_COMMAND_OUTPUT_LIMIT")
        return result

    def loaded_source(self, files):
        source_root = Path(__file__).resolve().parents[3]
        trusted_directory(source_root)
        for name in artifact.RUNTIME_FILES:
            require(read_file(source_root / name, modes=(0o400, 0o444, 0o600, 0o644), limit=1048576)
                    == files[name], "C_EXECUTING_SOURCE_NOT_PACKAGE")

    def account_preflight(self, uid, gid):
        broker = pwd.getpwnam("xuanjun_binance")
        require((broker.pw_uid, broker.pw_gid) == (986, 986) and
                broker.pw_shell in ("/sbin/nologin", "/usr/sbin/nologin") and
                len([u for u in pwd.getpwall() if u.pw_uid == 986]) == 1, "C_BROKER_IDENTITY")
        users = [u for u in pwd.getpwall() if u.pw_uid == uid or u.pw_name == "xuanjun_binance_shadow"]
        groups = [g for g in grp.getgrall() if g.gr_gid == gid or g.gr_name == "xuanjun_binance_shadow"]
        if users or groups:
            require(len(users) == len(groups) == 1 and users[0].pw_name == groups[0].gr_name ==
                    "xuanjun_binance_shadow" and (users[0].pw_uid, users[0].pw_gid, groups[0].gr_gid) ==
                    (uid, gid, gid) and users[0].pw_shell in ("/sbin/nologin", "/usr/sbin/nologin"),
                    "C_WORKER_IDENTITY_CONFLICT")
            require(set(os.getgrouplist("xuanjun_binance_shadow", gid)) == {gid},
                    "C_WORKER_SUPPLEMENTARY_GROUPS")
        # This root metadata scan never reads cmdline, environ or credentials.
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                line = next(s for s in (proc / "status").read_text().splitlines() if s.startswith("Uid:"))
            except FileNotFoundError:
                continue
            require(not any(int(x) in (986, uid) for x in line.split()[1:]), "C_DEDICATED_UID_HAS_PROCESS")
        return {"create_worker": not users, "worker_uid": uid, "worker_gid": gid}

    def create_worker(self, identity):
        if not identity["create_worker"]:
            return
        require(self.run(["/usr/sbin/groupadd", "--system", "--gid", str(identity["worker_gid"]),
                          "xuanjun_binance_shadow"]).returncode == 0, "C_GROUP_CREATE_FAILED")
        require(self.run(["/usr/sbin/useradd", "--system", "--no-create-home", "--uid", str(identity["worker_uid"]),
                          "--gid", str(identity["worker_gid"]), "--shell", "/sbin/nologin",
                          "--home-dir", "/nonexistent", "xuanjun_binance_shadow"]).returncode == 0,
                "C_WORKER_CREATE_FAILED")

    def units(self, names):
        result = self.run(["/usr/bin/systemctl", "show", *names, "--no-pager", "-p", "Id",
                           "-p", "LoadState", "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
                           "-p", "FragmentPath", "-p", "DropInPaths", "-p", "User", "-p", "Group"])
        rows = {}
        for block in result.stdout.strip().split("\n\n"):
            value = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            require(value.get("Id") in names and value["Id"] not in rows, "C_UNIT_METADATA_FIELDS")
            rows[value["Id"]] = value
        require(set(rows) == set(names) and result.returncode in (0, 1, 4), "C_UNIT_METADATA_UNAVAILABLE")
        return rows

    def verify_units(self):
        result = self.run(["/usr/bin/systemd-analyze", "verify", *[str(self.path("/etc/systemd/system") / n)
                            for n in UNITS.values()]])
        require(result.returncode == 0 and "Unknown lvalue" not in result.stderr and
                "Unknown key" not in result.stderr, "C_UNIT_VERIFY_FAILED")

    def verify_manager_profiles(self):
        for role, families in (("broker.service", {"AF_UNIX", "AF_INET", "AF_INET6"}),
                               ("worker.service", {"AF_UNIX"}),
                               ("controller.service", {"AF_UNIX", "AF_INET", "AF_INET6", "AF_NETLINK"})):
            name = UNITS[role]
            escaped = ''.join(c if c.isalnum() else '_%02x' % ord(c) for c in name)
            obj = "/org/freedesktop/systemd1/unit/" + escaped
            for property_name in ("PrivateNetwork", "RestrictAddressFamilies"):
                r = self.run(["/usr/bin/busctl", "get-property", "org.freedesktop.systemd1", obj,
                              "org.freedesktop.systemd1.Service", property_name])
                require(r.returncode == 0, "C_MANAGER_PROFILE_QUERY")
                tokens = shlex.split(r.stdout)
                if property_name == "PrivateNetwork":
                    require(tokens == ["b", "true" if role == "worker.service" else "false"],
                            "C_MANAGER_PRIVATE_NETWORK")
                else:
                    require(len(tokens) == 3 + len(families) and tokens[:3] == ["(bas)", "true", str(len(families))]
                            and set(tokens[3:]) == families, "C_MANAGER_ADDRESS_FAMILIES")

    def checkpoint(self, name):
        pass


def mkdir(ctx, name, mode=0o755):
    path = ctx.path(name)
    if not os.path.lexists(path):
        trusted_directory(path.parent)
        path.mkdir(mode=mode)
        os.chmod(path, mode)  # umask077 must not turn expected0755 into0700.
        fsync_dir(path.parent)
    trusted_directory(path, exact_mode=mode)
    return path


def atomic_receipt(path, value):
    target = Path(path)
    temporary = target.with_name(".receipt-" + str(os.getpid()) + "-" + str(time.monotonic_ns()))
    write_once(temporary, canonical_bytes(value) + b"\n")
    os.replace(temporary, target)
    fsync_dir(target.parent)


def package_bytes(raw):
    require(0 < len(raw) <= 2 * 1024 * 1024, "C_INSTALL_ARCHIVE_SIZE")
    files = {}
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        expanded = compressed.read(16 * 1024 * 1024 + 1)
    require(len(expanded) <= 16 * 1024 * 1024, "C_INSTALL_ARCHIVE_EXPANSION_LIMIT")
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
        for m in archive:
            require(len(files) < len(artifact.REVIEW_FILES) + 2, "C_INSTALL_ARCHIVE_COUNT")
            path = PurePosixPath(m.name)
            require(m.type in (tarfile.REGTYPE,tarfile.AREGTYPE) and path.as_posix() == m.name and not path.is_absolute() and
                    ".." not in path.parts and m.name not in files and 0 < m.size <= 1048576,
                    "C_INSTALL_ARCHIVE_MEMBER")
            files[m.name] = archive.extractfile(m).read()
    binding = strict_json(files["REVIEW_BINDING.json"])
    require(binding["schema_version"] == 1 and binding["production_authorized"] is False and
            binding["phase_b_frozen_manifest"] == B_MANIFEST and
            re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"]) and
            set(files) == set(binding["files"]) | {"REVIEW_BINDING.json"} and
            set(files) == set(artifact.REVIEW_FILES) | {"PHASE_C_RUNTIME_MANIFEST.json", "REVIEW_BINDING.json"},
            "C_INSTALL_BINDING")
    for name, value in binding["files"].items():
        require(digest(files[name]) == value, "C_INSTALL_FILE_HASH")
    manifest = strict_json(files["PHASE_C_RUNTIME_MANIFEST.json"])
    require(set(row["path"] for row in manifest["files"]) == set(artifact.RUNTIME_FILES) and
            len(manifest["files"]) == len(artifact.RUNTIME_FILES), "C_INSTALL_RUNTIME_CLOSURE")
    for row in manifest["files"]:
        require(digest(files[row["path"]]) == row["sha256"] and len(files[row["path"]]) == row["size"],
                "C_INSTALL_RUNTIME_HASH")
    return binding, files


def frozen_b(ctx):
    unit = read_file(ctx.path("/etc/systemd/system/xuanjun-binance-shadow.service"), modes=(0o644,))
    tx = read_file(ctx.path("/etc/xuanjun-binance/install-transaction.json"), modes=(0o600,))
    require(digest(unit) == ctx.b_unit_sha and digest(tx) == ctx.b_transaction_sha, "C_FROZEN_B_UNIT_OR_TRANSACTION")
    current = ctx.path("/opt/xuanjun-binance/current")
    s = current.lstat()
    require(stat.S_ISLNK(s.st_mode) and s.st_uid == 0 and os.readlink(current) == B_RELEASE,
            "C_FROZEN_B_CURRENT")
    release = ctx.path(B_RELEASE)
    manifest_raw = read_file(release / "minimal-runtime-manifest.json", modes=(0o400, 0o444, 0o600, 0o644))
    require(digest(manifest_raw) == ctx.b_manifest_sha, "C_FROZEN_B_MANIFEST")
    manifest = strict_json(manifest_raw)
    require(len(manifest["files"]) == 17, "C_FROZEN_B_FILE_COUNT")
    for row in manifest["files"]:
        relative = PurePosixPath(row["path"])
        require(not relative.is_absolute() and ".." not in relative.parts, "C_B_MANIFEST_PATH")
        require(digest(read_file(release / relative, modes=(0o400, 0o444, 0o600, 0o644, 0o755), limit=1048576))
                == row["sha256"], "C_FROZEN_B_FILE_HASH")
    state = ctx.units(("xuanjun-binance-shadow.service",))["xuanjun-binance-shadow.service"]
    require(state["LoadState"] == "loaded" and state["ActiveState"] == "inactive" and
            state["SubState"] == "dead" and state["MainPID"] == "0" and not state["DropInPaths"],
            "C_FROZEN_B_SERVICE")
    enabled = ctx.run(["/usr/bin/systemctl", "is-enabled", "xuanjun-binance-shadow.service"])
    require(enabled.returncode == 1 and enabled.stdout.strip() == "disabled", "C_B_NOT_DISABLED")
    return {"unit_sha256": digest(unit), "transaction_sha256": digest(tx), "manifest_sha256": digest(manifest_raw)}


def validate_plan(plan, files, now):
    require(set(plan) == {"schema_version", "host", "runtime_config", "acceptance_config",
                         "render_values", "worker_gid", "public_key_inputs"} and
            plan["schema_version"] == 1 and plan["host"] == HOST, "C_INSTALL_PLAN_FIELDS")
    config = validate_config(plan["runtime_config"])
    validate_policy(config["network_policy"], int(now * 1000))
    uid = config["network_policy"]["worker_uid"]
    require(plan["worker_gid"] == uid and type(plan["worker_gid"]) is int and
            config["snapshot_reader_uid"] == uid, "C_WORKER_UID_GID_BINDING")
    a = plan["acceptance_config"]
    require(set(a) == ACCEPTANCE_FIELDS and a["owner_approved"] is False and
            a["feature_id"] == config["feature_id"], "C_OFFLINE_ACCEPTANCE_MUST_REMAIN_UNAPPROVED")
    values = plan["render_values"]
    units = render_units(values)
    manifest_sha = digest(files["PHASE_C_RUNTIME_MANIFEST.json"])
    require(config["runtime_manifest_sha256"] == manifest_sha and
            values["C_RELEASE"] == "/opt/xuanjun-binance-phase-c/releases/" + manifest_sha and
            values["C_CONFIG"] == "/etc/xuanjun-binance-phase-c/runtime.json" and
            config["acceptance_path"] == "/etc/xuanjun-binance-phase-c/acceptance.json" and
            config["admission_path"] == "/etc/xuanjun-binance-phase-c/live-admission.json" and
            config["snapshot_root"] == values["C_SNAPSHOT_ROOT"] and
            config["evidence_root"] == values["C_EVIDENCE_ROOT"] and
            config["socket_path"] == "/run/xuanjun-phase-c-broker/broker.sock" and
            config["business_database"] == values["C_SNAPSHOT_ROOT"] + "/unused.sqlite" and
            config["credential_generation"].startswith(values["C_CREDENTIAL_ROOT"] + "/") and
            config["broker_private_key"] == values["C_PRIVATE_KEY_ROOT"] + "/broker.pem" and
            config["verifier_sha256"] == digest(files[artifact.PREFIX + "security.py"]), "C_PLAN_PATH_BINDING")
    identifier(Path(config["credential_generation"]).name)
    inputs = plan["public_key_inputs"]
    require(set(inputs) == {"broker", "source", "authority"}, "C_PUBLIC_KEYS_REQUIRED")
    require(len({config[n + "_public_key_sha256"] for n in inputs}) == 3,
            "C_SIGNING_IDENTITIES_MUST_BE_DISTINCT")
    for name, row in inputs.items():
        require(set(row) == {"path", "sha256"} and row["sha256"] == config[name + "_public_key_sha256"] and
                config[name + "_public_key"] == values["C_KEY_ROOT"] + "/" + name + ".pem" and
                row['path'] == '/etc/xuanjun-pr99-release/phase-c-public-inputs/' + name + '.pem',
                "C_PUBLIC_KEY_PLAN_PIN")
    return units


def install(archive, plan_path, ctx=None):
    ctx = ctx or Context()
    ctx.check_identity()
    raw = read_file(archive, modes=(0o400, 0o600), limit=2097152)
    binding, files = package_bytes(raw)
    # Compare loaded runtime bytes too: an approved archive cannot bless another
    # script/import closure loaded from a writable checkout.
    ctx.loaded_source(files)
    plan_raw = read_file(plan_path, modes=(0o400, 0o600), limit=65536)
    plan = strict_json(plan_raw)
    units = validate_plan(plan, files, ctx.now())
    trusted_directory(ctx.path(PIN).parent, exact_mode=0o700)
    pin_raw = read_file(ctx.path(PIN), modes=(0o600,), limit=110000)
    pin = strict_json(pin_raw)
    expected = {"action": INSTALL_ACTION, "source_commit": binding["source_commit"],
                "artifact_sha256": digest(raw), "controller_sha256": digest(files[artifact.PREFIX + "install_controller.py"]),
                "handoff_sha256": digest(files[artifact.PREFIX + "root_handoff.py"]),
                "plan_sha256": digest(plan_raw), "create_dedicated_worker_allowed": True}
    approval = verify_approval(pin, expected, ctx.now())
    current_body = ctx.current_approval(approval["approval_comment_id"])
    require(current_body == pin["approval_body"] and digest(current_body.encode()) == pin["approval_body_sha256"],
            "C_CURRENT_APPROVAL_CHANGED_OR_REVOKED")
    # No durable changes or root commands above this point; all authority is exact.
    before = frozen_b(ctx)
    shared = ctx.units(SHARED)
    identity = ctx.account_preflight(plan["runtime_config"]["network_policy"]["worker_uid"], plan["worker_gid"])
    config = plan["runtime_config"]
    root_names = (WORK, LOCK, PUBLIC, "/opt/xuanjun-binance-phase-c", "/etc/xuanjun-binance-phase-c",
                  "/var/lib/xuanjun-binance-phase-c")
    for name in root_names:
        require(not os.path.lexists(ctx.path(name)), "C_PREEXISTING_INSTALL_OBJECT:" + name)
        trusted_directory(ctx.path(name).parent)
    for name in UNITS.values():
        require(not os.path.lexists(ctx.path("/etc/systemd/system") / name), "C_UNIT_DESTINATION_EXISTS")
    observed = ctx.units(tuple(UNITS.values()))
    require(all(v["LoadState"] == "not-found" and v["MainPID"] == "0" and
                v["ActiveState"] == "inactive" for v in observed.values()), "C_EXISTING_MANAGER_CANDIDATE")
    public_keys = {}
    for name, row in plan["public_key_inputs"].items():
        key = read_file(ctx.path(row["path"]), modes=(0o400, 0o444, 0o600, 0o644))
        require(digest(key) == row["sha256"] and key.startswith(b"-----BEGIN PUBLIC KEY-----"),
                "C_PUBLIC_KEY_INPUT")
        result = ctx.run(["/usr/bin/openssl", "rsa", "-pubin", "-in", str(ctx.path(row["path"])),
                          "-noout", "-modulus"])
        modulus = result.stdout.strip().removeprefix("Modulus=")
        require(result.returncode == 0 and 512 <= len(modulus) <= 2048 and
                all(c in "0123456789ABCDEFabcdef" for c in modulus), "C_RSA_PUBLIC_KEY_INVALID")
        public_keys[name] = key
    require(ctx.now() < approval["expires_at"] and
            read_file(ctx.path(PIN), modes=(0o600,), limit=110000) == pin_raw and
            ctx.current_approval(approval["approval_comment_id"]) == current_body,
            "C_AUTHORITY_CHANGED_BEFORE_CLAIM")
    # Atomic root-only attempt/lock. Partial acquisition is preserved on failure.
    work = ctx.path(WORK)
    work.mkdir(mode=0o700)  # exclusive permanent attempt, no reuse after preflight race
    os.chmod(work, 0o700); fsync_dir(work.parent)
    receipt = {"schema_version": 1, "status": "INSTALLING", "phase": "claim",
               "source_commit": binding["source_commit"], "artifact_sha256": digest(raw),
               "plan_sha256": digest(plan_raw), "approval_comment_id": approval["approval_comment_id"],
               "service_started": False, "network_changed": False, "credentials_read": False,
               "database_read": False, "writer_enabled": False, "retry_allowed": False}
    lock = ctx.path(LOCK)
    try:
        atomic_receipt(work / "receipt.json", receipt)
        lock.mkdir(mode=0o700); os.chmod(lock, 0o700); fsync_dir(lock.parent)
        s = lock.lstat(); lock_identity = (s.st_dev, s.st_ino)
        write_once(work / "consumed-approval.json", canonical_bytes(pin))
        write_once(work / "input-plan.json", plan_raw)
        ctx.checkpoint("after_claim")
        require(ctx.now() < approval["expires_at"], "C_APPROVAL_EXPIRED_BEFORE_INSTALL")
        receipt["phase"] = "create_worker"; atomic_receipt(work / "receipt.json", receipt)
        ctx.create_worker(identity)
        # No deletion of user/group is ever attempted on failure.
        ctx.account_preflight(identity["worker_uid"], identity["worker_gid"])
        receipt["phase"] = "stage_runtime"; atomic_receipt(work / "receipt.json", receipt)
        mkdir(ctx, "/opt/xuanjun-binance-phase-c")
        releases = mkdir(ctx, "/opt/xuanjun-binance-phase-c/releases")
        staging = releases / (".pending-" + config["runtime_manifest_sha256"])
        staging.mkdir(mode=0o700); os.chmod(staging, 0o700)
        for name in sorted(artifact.RUNTIME_FILES) + ["PHASE_C_RUNTIME_MANIFEST.json"]:
            target = staging / name
            for folder in reversed(target.parent.parents):
                if staging == folder or staging in folder.parents:
                    if not folder.exists(): folder.mkdir(mode=0o755); os.chmod(folder, 0o755)
            if not target.parent.exists(): target.parent.mkdir(mode=0o755); os.chmod(target.parent, 0o755)
            write_once(target, files[name], mode=0o444)
        for folder in sorted((p for p in staging.rglob('*') if p.is_dir()),
                             key=lambda p:len(p.parts), reverse=True):
            fsync_dir(folder)
        os.chmod(staging, 0o755); fsync_dir(staging)
        destination = ctx.path(plan["render_values"]["C_RELEASE"])
        rename_new(staging, destination)
        artifact.verify_runtime(destination, config["runtime_manifest_sha256"])
        ctx.checkpoint("after_runtime")
        config_root = mkdir(ctx, "/etc/xuanjun-binance-phase-c")
        keys = mkdir(ctx, "/etc/xuanjun-binance-phase-c/keys")
        for name, key in public_keys.items(): write_once(keys / (name + ".pem"), key, mode=0o444)
        write_once(config_root / "runtime.json", canonical_bytes(config), mode=0o444)
        write_once(config_root / "acceptance.json", canonical_bytes(plan["acceptance_config"]), mode=0o444)
        mkdir(ctx, "/var/lib/xuanjun-binance-phase-c")
        mkdir(ctx, "/var/lib/xuanjun-binance-phase-c/snapshots", 0o711)
        evidence = ctx.path("/var/lib/xuanjun-binance-phase-c/evidence")
        evidence.mkdir(mode=0o700)
        os.chown(evidence, identity["worker_uid"], identity["worker_gid"])
        os.chmod(evidence, 0o700); fsync_dir(evidence.parent)
        write_once(work / "candidate.nft", compile_rules(config["network_policy"], int(ctx.now()*1000)).encode())
        receipt["phase"] = "install_stopped_units"; atomic_receipt(work / "receipt.json", receipt)
        for name, data in units.items():
            write_once(ctx.path("/etc/systemd/system") / UNITS[name], data.encode(), mode=0o644)
        ctx.verify_units()
        ctx.checkpoint("before_reload")
        require(ctx.now() < approval["expires_at"], "C_APPROVAL_EXPIRED_BEFORE_RELOAD")
        require(ctx.run(["/usr/bin/systemctl", "daemon-reload"]).returncode == 0, "C_RELOAD_FAILED")
        ctx.checkpoint("after_reload")
        states = ctx.units(tuple(UNITS.values()))
        for name, state in states.items():
            require(state["LoadState"] == "loaded" and state["ActiveState"] == "inactive" and
                    state["SubState"] == "dead" and state["MainPID"] == "0" and not state["DropInPaths"] and
                    state["FragmentPath"] == str(ctx.path("/etc/systemd/system") / name), "C_INSTALLED_UNIT_STATE")
            if name.endswith(".service"):
                require(state["Group"] == ("root" if name==UNITS['controller.service'] else "xuanjun_binance_shadow") and
                        state["User"] == ("root" if name==UNITS['controller.service'] else
                                          "xuanjun_binance" if name == UNITS["broker.service"] else "xuanjun_binance_shadow"),
                        "C_MANAGER_SERVICE_IDENTITY")
            enabled = ctx.run(["/usr/bin/systemctl", "is-enabled", name])
            require(enabled.stdout.strip() in ("static", "disabled") and enabled.returncode in (0, 1),
                    "C_CANDIDATE_MUST_NOT_BE_ENABLED")
        ctx.verify_manager_profiles()
        require(frozen_b(ctx) == before and ctx.units(SHARED) == shared, "C_PROTECTED_OBJECT_CHANGED")
        artifact.verify_runtime(destination, config["runtime_manifest_sha256"])
        require(read_file(config_root / "runtime.json", modes=(0o444,)) == canonical_bytes(config) and
                read_file(config_root / "acceptance.json", modes=(0o444,)) == canonical_bytes(plan["acceptance_config"]),
                "C_INSTALLED_CONFIG_CHANGED")
        for name, key in public_keys.items():
            require(read_file(keys / (name + '.pem'), modes=(0o444,)) == key, "C_INSTALLED_PUBLIC_KEY_CHANGED")
        evidence_state = evidence.lstat()
        require(stat.S_ISDIR(evidence_state.st_mode) and evidence_state.st_uid == identity['worker_uid'] and
                evidence_state.st_gid == identity['worker_gid'] and stat.S_IMODE(evidence_state.st_mode) == 0o700,
                "C_INSTALLED_EVIDENCE_DIRECTORY")
        for name, data in units.items():
            require(read_file(ctx.path("/etc/systemd/system") / UNITS[name], modes=(0o644,)) == data.encode(),
                    "C_INSTALLED_UNIT_BYTES_CHANGED")
        require(not os.path.lexists(ctx.path(config["admission_path"])), "C_LIVE_ADMISSION_UNEXPECTED")
        ctx.checkpoint("before_unlock")
        s = lock.lstat()
        require((s.st_dev,s.st_ino) == lock_identity and s.st_uid == 0 and
                stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o700 and not list(lock.iterdir()),
                "C_INSTALL_LOCK_CHANGED")
        lock.rmdir(); fsync_dir(lock.parent)
        receipt.update(status="C_OFFLINE_CANDIDATE_INSTALLED_NOT_STARTED", phase="complete",
                       lock_released=True, runtime_manifest_sha256=config["runtime_manifest_sha256"],
                       frozen_b_unchanged=True, shared_metadata_unchanged=True,
                       live_phase_c="NOT_AUTHORIZED", started_service_confinement="NOT_EXERCISED")
        atomic_receipt(work / "receipt.json", receipt)
        write_once(ctx.path(PUBLIC), canonical_bytes(receipt) + b"\n", mode=0o644)
        return receipt
    except BaseException as error:
        receipt.update(status="HOLD_PRESERVE_EVIDENCE", error_type=type(error).__name__,
                       error=str(error) if type(error).__name__ == "GateError" else "BOUNDED_FAILURE")
        try:
            atomic_receipt(work / "receipt.json", receipt)
        except BaseException:
            raise RuntimeError("C_UNKNOWN_FAILURE_RECEIPT_UNAVAILABLE") from error
        raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("SIGTERM")))
    try:
        result = install(args.archive, args.plan)
        print(json.dumps(result, sort_keys=True)); return 0
    except BaseException as error:
        print(json.dumps({"status": "HOLD_PRESERVE_EVIDENCE", "error_type": type(error).__name__,
                          "retry_allowed": False, "service_started": False}), flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
