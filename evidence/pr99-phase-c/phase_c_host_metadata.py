"""Non-root, bounded host metadata only. No sudo, network probe or state change."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

HOST = "iZmj7a5kwr75qc1tul4kf9Z"
FIELDS = {"LoadState", "ActiveState", "SubState", "MainPID", "User", "Group",
          "FragmentPath", "DropInPaths", "PrivateNetwork", "RestrictAddressFamilies"}
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}


def read_bounded(path, limit=65536):
    try:
        with open(path, "rb") as f:
            data = f.read(limit + 1)
        if len(data) > limit:
            return None, "SIZE_LIMIT"
        return data.decode("utf-8", "strict"), None
    except (OSError, UnicodeError) as error:
        return None, type(error).__name__


def program(name):
    for folder in ("/usr/sbin", "/usr/bin", "/sbin", "/bin"):
        p = Path(folder) / name
        try:
            resolved = p.resolve(strict=True)
            for parent in list(resolved.parents) + [resolved]:
                info = parent.lstat()
                if info.st_uid != 0 or info.st_mode & 0o022:
                    raise ValueError("untrusted")
            if not stat.S_ISREG(resolved.stat().st_mode) or not os.access(resolved, os.X_OK):
                continue
            return str(resolved)
        except (OSError, ValueError):
            continue
    return None


def command(path, args):
    try:
        r = subprocess.run([path] + args, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=8, env=ENV, check=False)
        if len(r.stdout) > 16384:
            return None, {"status": "OUTPUT_LIMIT"}
        return r.stdout, {"exit": r.returncode}
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, {"status": type(error).__name__}


def collect():
    if os.geteuid() == 0 or os.uname().nodename != HOST:
        return {"status": "HOLD_WRONG_HOST_OR_ROOT", "production_mutation": False}, 2
    report = {"schema_version": 1, "kind": "PR99_PHASE_C_NONROOT_METADATA",
              "status": "METADATA_COLLECTED_NOT_PHASE_C_ACCEPTANCE",
              "host": HOST, "uid": os.geteuid(), "observed_epoch": int(time.time()),
              "kernel": os.uname().release, "python": sys.version.split()[0],
              "root_used": False, "sudo_calls": 0, "service_actions": 0,
              "provider_requests": 0, "credential_reads": 0, "database_reads": 0,
              "production_mutation": False, "phase_c_authorized": False,
              "root_firewall_enforcement": "NOT_VERIFIED",
              "started_service_confinement": "NOT_EXERCISED"}
    versions = {"systemctl": ["--version"], "ip": ["-Version"],
                "iptables": ["--version"], "ip6tables": ["--version"],
                "nft": ["--version"], "openssl": ["version"]}
    report["tools"] = {}
    for name, args in versions.items():
        binary = program(name)
        row = {"path": binary, "present_trusted": binary is not None}
        if binary:
            output, meta = command(binary, args)
            row.update(meta)
            # Fixed programs' version-only outputs; no arbitrary diagnostics.
            if output and meta.get("exit") == 0:
                row["version"] = output.splitlines()[0][:240]
        report["tools"][name] = row
    for name in ("busctl", "systemd-analyze", "unshare", "setpriv"):
        report["tools"][name] = {"path": program(name)}
    sysctl = report["tools"]["systemctl"]["path"]
    if sysctl:
        output, meta = command(sysctl, ["show", "xuanjun-binance-shadow.service", "--no-pager"] +
                               [part for key in sorted(FIELDS) for part in ("-p", key)])
        report["candidate_service_query"] = meta
        report["candidate_service"] = {key: value[:512] for line in (output or "").splitlines()
                                       if "=" in line for key, value in [line.split("=", 1)]
                                       if key in FIELDS}
    text, error = read_bounded("/etc/passwd")
    account = None
    if text:
        for line in text.splitlines():
            parts = line.split(":")
            if len(parts) == 7 and parts[0] == "xuanjun_binance":
                account = {"uid": int(parts[2]), "gid": int(parts[3]),
                           "interactive_shell": Path(parts[6]).name not in ("nologin", "false")}
    report["dedicated_identity"] = account if not error else {"error": error}
    text, error = read_bounded("/proc/modules")
    names = {line.split()[0] for line in (text or "").splitlines() if line.split()}
    report["loaded_modules_metadata"] = ({"error": error} if error else
        {name: name in names for name in ("xt_owner", "iptable_filter", "ip6table_filter",
                                          "nf_tables", "nf_conntrack", "xt_conntrack")})
    report["kernel_metadata"] = {}
    for label, path in (("ip_tables_matches", "/proc/net/ip_tables_matches"),
                        ("ip6_tables_matches", "/proc/net/ip6_tables_matches")):
        text, error = read_bounded(path, 8192)
        report["kernel_metadata"][label] = {"error": error} if error else {
            "owner_listed": "owner" in (text or "").split(),
            "conntrack_listed": "conntrack" in (text or "").split()}
    text, error = read_bounded("/proc/self/cgroup", 8192)
    report["cgroup_layout"] = {"error": error} if error else {
        "v2": any(line.startswith("0::") for line in (text or "").splitlines()),
        "memory_controller_listed": any("memory" in line.split(":")[1].split(",")
             for line in (text or "").splitlines() if len(line.split(":")) == 3),
        "runtime_memory_peak_oom_evidence": "NOT_VERIFIED"}
    return report, 0


if __name__ == "__main__":
    report, code = collect()
    print("PR99_PHASE_C_METADATA_RECEIPT=" + json.dumps(report, sort_keys=True))
    sys.exit(code)
