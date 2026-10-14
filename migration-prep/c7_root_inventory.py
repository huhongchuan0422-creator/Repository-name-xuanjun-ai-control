"""Root-only, zero-argument, redacted and completeness-bound C7 inventory.

Every systemd entry is accounted for as read, resolved link, skipped, or
failed. Any missing root, walk/read error, unresolved link, non-regular entry,
or identity drift makes the inventory HOLD. Configuration bodies and raw paths
are never emitted.
"""
from __future__ import print_function

import errno
import hashlib
import json
import os
import pwd
import socket
import stat
import subprocess
import sys

from root_policy_audit import effective_policy, parsed_sources, protected_digest


HOSTS = frozenset(("iZ6wee8q9z4t03hvqumwfhZ", "iZmj7a5kwr75qc1tul4kf9Z"))
USERS = ("root", "yibi", "githubrunner")
SYSTEMD_ROOTS = ("/etc/systemd/system", "/usr/lib/systemd/system")
MATCHERS = (b"/opt/trading-system", b"binance-eth-trader", b"yibi", b"openclaw")
SUCCESS_OUTCOMES = frozenset(("READ_REGULAR", "RESOLVED_SYMLINK",
                              "RESOLVED_MASKED_UNIT", "DIRECTORY_TRAVERSED"))


class InventoryProblem(Exception):
    def __init__(self, outcome):
        Exception.__init__(self, outcome)
        self.outcome = outcome


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _path_digest(path):
    return digest_bytes(os.fsencode(path))


def _identity(value):
    fields = (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode),
              stat.S_IMODE(value.st_mode), value.st_uid, value.st_gid,
              value.st_size, getattr(value, "st_mtime_ns",
                                     int(value.st_mtime * 1000000000)))
    return digest_bytes(json.dumps(fields, separators=(",", ":")).encode("ascii"))


def redacted_text_summary(raw):
    if not isinstance(raw, bytes):
        raise ValueError("BYTES_REQUIRED")
    active = [line for line in raw.splitlines()
              if line.strip() and not line.lstrip().startswith(b"#")]
    return {"sha256": digest_bytes(raw), "bytes": len(raw),
            "active_line_count": len(active),
            "writer_marker_line_count": sum(
                1 for line in active if any(marker in line for marker in MATCHERS))}


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=20, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                             "LC_ALL": "C"})
    if result.returncode:
        raise ValueError("COMMAND_FAILED")
    return result.stdout


class NoCrontab(Exception):
    """Raised only when crontab's exact C-locale absence message is observed."""


def _read_crontab(user):
    result = subprocess.run(["/usr/bin/crontab", "-u", user, "-l"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=20, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                                             "LC_ALL": "C"})
    if result.returncode == 0:
        return result.stdout
    expected = "no crontab for {0}".format(user).encode("ascii")
    if result.returncode == 1 and result.stderr.strip() == expected:
        raise NoCrontab()
    raise ValueError("CRONTAB_READ_FAILED")


def cron_inventory(user, runner=None):
    runner = runner or _read_crontab
    try:
        pwd.getpwnam(user)
    except KeyError:
        return {"status": "USER_NOT_PRESENT", "complete": True}
    try:
        value = redacted_text_summary(runner(
            ["/usr/bin/crontab", "-u", user, "-l"]))
        return dict({"status": "READ", "complete": True}, **value)
    except NoCrontab:
        return {"status": "CONFIRMED_NO_CRONTAB", "complete": True}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"status": "READ_FAILED", "complete": False}


def _stable_regular_read(path):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise InventoryProblem("NONREGULAR_SKIPPED")
        chunks = []
        while True:
            value = os.read(descriptor, 1024 * 1024)
            if not value:
                break
            chunks.append(value)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_after = os.lstat(path)
    except OSError:
        raise InventoryProblem("CONCURRENT_ALTERATION")
    if (_identity(before) != _identity(after) or before.st_dev != path_after.st_dev or
            before.st_ino != path_after.st_ino or not stat.S_ISREG(path_after.st_mode)):
        raise InventoryProblem("CONCURRENT_ALTERATION")
    return b"".join(chunks), _identity(after)


def _under_roots(path, roots):
    resolved = os.path.realpath(path)
    for root in roots:
        canonical_root = os.path.realpath(root)
        if resolved == canonical_root or resolved.startswith(canonical_root + os.sep):
            return True
    return False


def _error_name(error):
    if isinstance(error, PermissionError) or getattr(error, "errno", None) in (
            errno.EACCES, errno.EPERM):
        return "PERMISSION_DENIED"
    if isinstance(error, FileNotFoundError) or getattr(error, "errno", None) == errno.ENOENT:
        return "MISSING_DURING_READ"
    return "READ_FAILED"


def _entry_record(path, roots, stable_reader):
    base = {"path_sha256": _path_digest(path),
            "unit_name_sha256": digest_bytes(os.path.basename(path).encode("utf-8"))}
    try:
        value = os.lstat(path)
    except OSError as error:
        base["outcome"] = _error_name(error)
        return base
    base["lstat_identity_sha256"] = _identity(value)
    if stat.S_ISLNK(value.st_mode):
        try:
            link_text = os.readlink(path)
            target = os.path.realpath(path)
        except OSError as error:
            base["outcome"] = _error_name(error)
            return base
        base["link_text_sha256"] = digest_bytes(os.fsencode(link_text))
        base["resolved_target_sha256"] = _path_digest(target)
        if target == "/dev/null":
            base["effective_unit_name_sha256"] = base["unit_name_sha256"]
            base["outcome"] = "RESOLVED_MASKED_UNIT"
            return base
        if not os.path.exists(target):
            base["outcome"] = "DANGLING_SYMLINK"
            return base
        if os.path.isdir(target):
            base["outcome"] = "SYMLINK_DIRECTORY_NOT_TRAVERSED"
            return base
        if not _under_roots(target, roots):
            base["outcome"] = "SYMLINK_TARGET_OUTSIDE_ALLOWED_ROOTS"
            return base
        try:
            raw, identity = stable_reader(target)
        except InventoryProblem as error:
            base["outcome"] = error.outcome
            return base
        except OSError as error:
            base["outcome"] = _error_name(error)
            return base
        base.update({"outcome": "RESOLVED_SYMLINK", "target_identity_sha256": identity,
                     "effective_unit_name_sha256": digest_bytes(
                         os.path.basename(target).encode("utf-8")),
                     "content_sha256": digest_bytes(raw),
                     "writer_marker": any(marker in raw for marker in MATCHERS)})
        return base
    if not stat.S_ISREG(value.st_mode):
        base["outcome"] = "NONREGULAR_SKIPPED"
        return base
    try:
        raw, identity = stable_reader(path)
    except InventoryProblem as error:
        base["outcome"] = error.outcome
        return base
    except OSError as error:
        base["outcome"] = _error_name(error)
        return base
    base.update({"outcome": "READ_REGULAR", "target_identity_sha256": identity,
                 "content_sha256": digest_bytes(raw),
                 "writer_marker": any(marker in raw for marker in MATCHERS)})
    return base


def _directory_record(path):
    value = {"path_sha256": _path_digest(path)}
    try:
        metadata = os.lstat(path)
    except OSError as error:
        value["outcome"] = _error_name(error)
        return value
    value["lstat_identity_sha256"] = _identity(metadata)
    value["outcome"] = ("DIRECTORY_TRAVERSED" if stat.S_ISDIR(metadata.st_mode) and
                        not stat.S_ISLNK(metadata.st_mode) else
                        "DIRECTORY_IDENTITY_INVALID")
    return value


def systemd_inventory(roots=None, walk_fn=None, stable_reader=None):
    roots = tuple(roots or SYSTEMD_ROOTS)
    walk_fn = walk_fn or os.walk
    stable_reader = stable_reader or _stable_regular_read
    records = []
    root_results = []
    walk_errors = []

    def onerror(error):
        walk_errors.append({"path_sha256": _path_digest(getattr(error, "filename", "")),
                            "outcome": _error_name(error)})

    for root in roots:
        root_start = len(records)
        root_error_start = len(walk_errors)
        try:
            root_value = os.lstat(root)
            if not stat.S_ISDIR(root_value.st_mode) or stat.S_ISLNK(root_value.st_mode):
                raise InventoryProblem("ROOT_NOT_CANONICAL_DIRECTORY")
        except InventoryProblem as error:
            root_results.append({"root_sha256": _path_digest(root),
                                 "status": "HOLD_INCOMPLETE",
                                 "outcome": error.outcome, "entry_count": 0})
            continue
        except OSError as error:
            root_results.append({"root_sha256": _path_digest(root),
                                 "status": "HOLD_INCOMPLETE",
                                 "outcome": _error_name(error), "entry_count": 0})
            continue
        try:
            iterator = walk_fn(root, followlinks=False, onerror=onerror)
            for directory, directories, files in iterator:
                records.append(_directory_record(directory))
                for name in list(directories):
                    path = os.path.join(directory, name)
                    try:
                        if stat.S_ISLNK(os.lstat(path).st_mode):
                            records.append(_entry_record(path, roots, stable_reader))
                            directories.remove(name)
                    except OSError as error:
                        records.append({"path_sha256": _path_digest(path),
                                        "outcome": _error_name(error)})
                        directories.remove(name)
                for name in files:
                    records.append(_entry_record(os.path.join(directory, name),
                                                 roots, stable_reader))
        except OSError as error:
            onerror(error)
        root_records = records[root_start:]
        root_walk_errors = walk_errors[root_error_start:]
        complete = (not root_walk_errors and
                    all(item["outcome"] in SUCCESS_OUTCOMES for item in root_records))
        root_results.append({"root_sha256": _path_digest(root),
                             "status": "PASS_COMPLETE" if complete else "HOLD_INCOMPLETE",
                             "outcome": "WALK_COMPLETE" if not root_walk_errors else "WALK_FAILED",
                             "entry_count": len(root_records)})
    records.extend(walk_errors)
    records.sort(key=lambda item: (item.get("path_sha256", ""), item["outcome"]))
    outcome_counts = {}
    for item in records:
        outcome_counts[item["outcome"]] = outcome_counts.get(item["outcome"], 0) + 1
    incomplete_count = sum(count for outcome, count in outcome_counts.items()
                           if outcome not in SUCCESS_OUTCOMES)
    complete = (len(root_results) == len(roots) and
                all(item["status"] == "PASS_COMPLETE" for item in root_results) and
                incomplete_count == 0)
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("ascii")
    return {"status": "PASS_COMPLETE" if complete else "HOLD_INCOMPLETE",
            "root_count_expected": len(roots), "root_count_recorded": len(root_results),
            "roots": root_results, "outcome_counts": outcome_counts,
            "incomplete_count": incomplete_count, "entry_count": len(records),
            "writer_marker_unit_count": sum(1 for item in records
                                            if item.get("writer_marker") is True),
            "aggregate_sha256": digest_bytes(payload), "outcomes": records,
            "raw_paths_disclosed": False, "raw_content_disclosed": False}


def main():
    try:
        if len(sys.argv) != 1 or os.geteuid() != 0:
            raise ValueError("ROOT_ZERO_ARGUMENTS_REQUIRED")
        host = socket.gethostname().split(".")[0]
        if host not in HOSTS:
            raise ValueError("HOST_MISMATCH")
        visudo = run(["/usr/sbin/visudo", "-c"]).decode("utf-8", "strict")
        sources = parsed_sources(visudo)
        source_digests = sorted(protected_digest(path) for path in sources)
        grant = run(["/usr/bin/sudo", "-n", "-l", "-U", "githubrunner"]).decode(
            "utf-8", "strict")
        crontabs = {user: cron_inventory(user) for user in USERS}
        systemd = systemd_inventory()
        complete = (systemd["status"] == "PASS_COMPLETE" and
                    all(value["complete"] for value in crontabs.values()))
        value = {"schema_version": 2, "status": ("PASS_COMPLETE" if complete else
                                                   "HOLD_INCOMPLETE"),
                 "host": host, "crontabs": crontabs, "systemd": systemd,
                 "sudoers_source_count": len(sources),
                 "sudoers_aggregate_sha256": digest_bytes(
                     json.dumps(source_digests, separators=(",", ":")).encode("ascii")),
                 "githubrunner_grant_shape": effective_policy(grant),
                 "raw_policy_disclosed": False, "production_mutation": False,
                 "gateway_global_triggers_included": False}
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0 if complete else 2
    except BaseException as error:
        print(json.dumps({"status": "HOLD", "error_type": type(error).__name__,
                          "production_mutation": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
