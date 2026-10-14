"""Root-only, zero-argument, redacted C7 inventory candidate.

It reads cron/systemd/sudo policy metadata and emits only counts and digests.
It never prints cron lines, unit contents, environment values or source paths.
"""
from __future__ import print_function

import hashlib
import json
import os
import pwd
import socket
import subprocess
import sys

from root_policy_audit import effective_policy, parsed_sources, protected_digest


HOSTS = frozenset(("iZ6wee8q9z4t03hvqumwfhZ", "iZmj7a5kwr75qc1tul4kf9Z"))
USERS = ("root", "yibi", "githubrunner")
SYSTEMD_ROOTS = ("/etc/systemd/system", "/usr/lib/systemd/system")
MATCHERS = (b"/opt/trading-system", b"binance-eth-trader", b"yibi", b"openclaw")


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def redacted_text_summary(raw):
    require_bytes = isinstance(raw, bytes)
    if not require_bytes:
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


def cron_inventory(user):
    try:
        pwd.getpwnam(user)
    except KeyError:
        return {"status": "USER_NOT_PRESENT"}
    try:
        return dict({"status": "READ"}, **redacted_text_summary(
            run(["/usr/bin/crontab", "-u", user, "-l"])))
    except ValueError:
        # crontab uses exit 1 for an empty/nonexistent spool; do not guess which.
        return {"status": "NO_CRONTAB_OR_READ_FAILED"}


def systemd_inventory():
    records = []
    for root in SYSTEMD_ROOTS:
        for directory, unused_directories, files in os.walk(root, followlinks=False):
            for name in files:
                path = os.path.join(directory, name)
                try:
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    raw = open(path, "rb").read()
                except OSError:
                    continue
                records.append((digest_bytes(path.encode("utf-8")), digest_bytes(raw),
                                any(marker in raw for marker in MATCHERS)))
    records.sort()
    payload = json.dumps(records, separators=(",", ":")).encode("ascii")
    return {"unit_file_count": len(records), "aggregate_sha256": digest_bytes(payload),
            "writer_marker_unit_count": sum(1 for unused_path, unused_digest, hit in records if hit)}


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
        value = {"schema_version": 1, "host": host,
                 "crontabs": {user: cron_inventory(user) for user in USERS},
                 "systemd": systemd_inventory(),
                 "sudoers_source_count": len(sources),
                 "sudoers_aggregate_sha256": digest_bytes(
                     json.dumps(source_digests, separators=(",", ":")).encode("ascii")),
                 "githubrunner_grant_shape": effective_policy(grant),
                 "raw_policy_disclosed": False, "production_mutation": False,
                 "gateway_global_triggers_included": False}
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except BaseException as error:
        print(json.dumps({"status": "HOLD", "error_type": type(error).__name__,
                          "production_mutation": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())

