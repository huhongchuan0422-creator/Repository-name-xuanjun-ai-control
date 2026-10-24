"""Non-root runtime metadata; never read unit bodies, argv, env, DB or credentials."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

HOSTS = {
    "tokyo": ("iZ6wee8q9z4t03hvqumwfhZ", 1001),
    "korea": ("iZmj7a5kwr75qc1tul4kf9Z", 1001),
    "domestic": ("iZvt5t8tlrm8oiZ", 1002),
}
UNITS = (
    "secure-secrets-portal.service", "provider-neutral-tunnel.service",
    "provider-neutral-tokyo-tunnel.service", "provider-neutral-domestic-bridge.service",
    "domestic-model-rpc-tunnel.service", "korea-novel-model-rpc-tunnel.service",
    "restricted-rpc-openai-shim.service", "tokyo-restricted-model-executor.service",
    "xuanjun-wecom-customer-contact.service", "xuanjun-wecom-customer-service.service",
    "xuanjun-wecom-novel-ingress.service", "xj-tokyo-vpn.service", "docker.service",
    "nginx.service", "xuanjun-novel-factory.service", "tailscaled.service",
)
PROPS = (
    "Id", "Names", "LoadState", "UnitFileState", "ActiveState", "SubState",
    "User", "Group", "DynamicUser", "WorkingDirectory", "RootDirectory",
    "MainPID", "ControlGroup", "FragmentPath", "DropInPaths", "Requires", "Wants",
    "BindsTo", "PartOf", "After", "TriggeredBy", "Restart", "RuntimeDirectory",
    "StateDirectory", "CacheDirectory", "LogsDirectory", "ReadWritePaths",
)


def call(args):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=12)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return type(e).__name__, ""


def metadata(path):
    try:
        s = Path(path).lstat()
        return {"status": "OBSERVED_METADATA_ONLY", "uid": s.st_uid,
                "gid": s.st_gid, "mode": oct(stat.S_IMODE(s.st_mode)),
                "device": s.st_dev, "inode": s.st_ino,
                "regular": stat.S_ISREG(s.st_mode), "symlink": stat.S_ISLNK(s.st_mode)}
    except FileNotFoundError:
        return {"status": "ABSENT"}
    except PermissionError:
        return {"status": "UNKNOWN_PERMISSION_DENIED"}
    except OSError as e:
        return {"status": "UNKNOWN", "error_type": type(e).__name__}


def process(pid):
    result = {"pid": pid}
    if not pid.isdigit() or int(pid) <= 0:
        return result
    for key in ("exe", "cwd"):
        try:
            result[key] = os.readlink("/proc/" + pid + "/" + key)
        except OSError as e:
            result[key] = {"status": "UNKNOWN", "error_type": type(e).__name__}
    return result


def main():
    side = os.environ["XJ_SIDE"]
    host, uid = HOSTS[side]
    assert os.uname().nodename == host and os.geteuid() == uid and uid != 0
    r = {"schema_version": 1, "side": side, "host": host, "uid": uid,
         "delivery_commit": os.environ["GITHUB_SHA"], "epoch": int(time.time()),
         "sudo_calls": 0, "database_opened": False, "credentials_read": False,
         "unit_bodies_read": False, "argv_or_environment_read": False,
         "cron_contents_read": False, "http_requests": 0, "service_actions": 0,
         "production_changes": 0, "units": {}}
    for unit in UNITS:
        rc, text = call(["/usr/bin/systemctl", "show", unit, "--no-pager"] +
                        [v for key in PROPS for v in ("-p", key)])
        props = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        row = {"exit": rc, "properties": props}
        row["process"] = process(props.get("MainPID", "0"))
        fragment = props.get("FragmentPath", "")
        if fragment.startswith("/"):
            row["fragment_identity"] = metadata(fragment)
        r["units"][unit] = row
    catalog = {}
    for title, args in (
        ("loaded_services", ["list-units", "--type=service", "--all", "--plain"]),
        ("installed_services", ["list-unit-files", "--type=service"]),
    ):
        rc, text = call(["/usr/bin/systemctl"] + args + ["--no-legend", "--no-pager"])
        rows = []
        for line in text.splitlines():
            parts = line.split()
            if parts and re.fullmatch(r"[A-Za-z0-9_.:@\\-]+\.service", parts[0]):
                # Drop free-form descriptions. These are discovery names, not deployment scope.
                rows.append(parts[:4] if title == "loaded_services" else parts[:2])
        catalog[title] = {"exit": rc, "rows": rows[:500], "truncated": len(rows) > 500}
    r["discovery_only"] = catalog
    rc, text = call(["/usr/sbin/ss", "-H", "-lntp"])
    listeners = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            port = int(parts[3].rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if port not in (80, 443, 18080, 18443, 18761, 18770, 18780, 18781, 19443, 19444):
            continue
        pids = sorted(set(re.findall(r"pid=(\d+)", line)))
        listeners.append({"local_endpoint": parts[3], "port": port,
                          "visible_pids": [process(pid) for pid in pids],
                          "owner_proven": bool(pids)})
    r["listeners"] = {"exit": rc, "rows": listeners,
                      "missing_pid_means": "UNKNOWN_NONROOT_NOT_NO_OWNER"}
    r["private_scheduling_metadata"] = {
        name: metadata(name) for name in (
            "/var/spool/cron/root", "/var/spool/cron/admin", "/etc/cron.d",
            "/etc/systemd/user", "/root/.config/systemd/user", "/home/admin/.config/systemd/user")}
    one = r["units"]["provider-neutral-tunnel.service"]["properties"]
    two = r["units"]["provider-neutral-tokyo-tunnel.service"]["properties"]
    if one.get("LoadState") == two.get("LoadState") == "loaded":
        r["tunnel_alias"] = {"status": "SAME_UNIT" if one.get("Id") == two.get("Id") else "DISTINCT_UNITS",
                             "generic_id": one.get("Id"), "tokyo_id": two.get("Id")}
    else:
        r["tunnel_alias"] = {"status": "NOT_BOTH_LOADED_NOT_PROVEN_SAME",
                             "generic_load": one.get("LoadState"), "tokyo_load": two.get("LoadState")}
    r["status"] = "RUNTIME_METADATA_COLLECTED_NOT_PRIVATE_CONFIG_OR_INSTALL_ACCEPTANCE"
    print("PR99_SERVICE_RUNTIME_RECEIPT=" + json.dumps(r, sort_keys=True))


if __name__ == "__main__":
    main()
