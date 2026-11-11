#!/usr/bin/python3.11
"""Prepare a distinct dependency environment; never import production code/start services."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import signal
import stat
import subprocess
import time

ROOT = Path("/root/xuanjun-offline-selected-20261016")
BUILD = ROOT / "environment-build"
DEST = Path("/opt/xuanjun-binance-offline-env-20261016")
PACKAGES = ("numpy", "pandas", "requests", "websocket-client", "python-dotenv",
            "pyyaml", "sqlalchemy", "pymysql", "redis", "cryptography",
            "ccxt", "ta", "loguru")
IMPORTS = ("numpy", "pandas", "requests", "websocket", "dotenv", "yaml",
           "sqlalchemy", "pymysql", "redis", "cryptography", "ccxt", "ta", "loguru")
REMOTE = "import importlib.metadata as m,json,os,re,subprocess,sys\nfrom pathlib import Path\nassert os.geteuid()==0 and os.uname().nodename==\"iZ6wee8q9z4t03hvqumwfhZ\"\nprobe=\"import importlib.metadata as m,json,sys;print(json.dumps({'python':list(sys.version_info[:2]),'versions':{d.metadata['Name']:d.version for d in m.distributions() if d.metadata.get('Name')}}))\"\nprofiles=[]\nfor raw in (\"/opt/trading-system/venv/bin/python\",\"/opt/trading-system/.venv/bin/python\",\"/usr/bin/python3.11\",\"/usr/local/bin/python3.11\"):\n if not Path(raw).is_file():continue\n r=subprocess.run([raw,\"-I\",\"-B\",\"-c\",probe],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=25)\n if r.returncode==0:\n  v=json.loads(r.stdout);v[\"interpreter\"]=raw;profiles.append(v)\n else:profiles.append({\"interpreter\":raw,\"error\":\"METADATA_QUERY_FAILED\"})\nuser_site=Path(\"/home/admin/.local/lib/python3.11/site-packages\")\nif user_site.is_dir():\n local={d.metadata[\"Name\"]:d.version for d in m.distributions(path=[str(user_site)]) if d.metadata.get(\"Name\")}\n for profile in list(profiles):\n  if profile.get(\"python\")==[3,11] and profile[\"interpreter\"] in (\"/usr/bin/python3.11\",\"/usr/local/bin/python3.11\"):\n   norm=lambda x:re.sub(r\"[-_.]+\",\"-\",x).lower()\n   combined={norm(k):v for k,v in profile[\"versions\"].items()}\n   combined.update({norm(k):v for k,v in local.items()})\n   profiles.append({\"interpreter\":profile[\"interpreter\"]+\" + admin user-site metadata\",\"python\":[3,11],\"versions\":combined})\nprint(json.dumps({\"host\":os.uname().nodename,\"profiles\":profiles,\"api_calls\":0,\"database_reads\":0}))\n"

def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def normalized(value):
    return re.sub(r"[-_.]+", "-", value).lower()

def select_source(record):
    need(record["host"] == "iZ6wee8q9z4t03hvqumwfhZ", "SOURCE_HOST")
    for profile in record.get("profiles", []):
        if profile.get("python") != [3, 11]:
            continue
        versions = {}
        for name, version in profile.get("versions", {}).items():
            need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) is not None, "UNSAFE_PACKAGE_NAME")
            need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version) is not None, "UNSAFE_PACKAGE_VERSION")
            key = normalized(name)
            need(key not in versions or versions[key] == version, "AMBIGUOUS_INSTALLED_VERSION")
            versions[key] = version
        if all(normalized(name) in versions for name in PACKAGES):
            return profile["interpreter"], versions
    raise RuntimeError("NO_TOKYO_PY311_PROFILE_CONTAINS_ALL_13_PACKAGES_NO_INSTALL_STARTED")

def write_json(path, value):
    with path.open("x") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(value, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())

def stable_service():
    r = subprocess.run(["systemctl", "show", "xuanjun-binance-shadow.service",
                        "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
                        "--no-pager"], capture_output=True, text=True, timeout=15, check=True)
    info = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    need(info.get("ActiveState") == "inactive" and info.get("MainPID") == "0",
         "EXISTING_SERVICE_NOT_INACTIVE")
    disabled = subprocess.run(["systemctl", "is-enabled", "xuanjun-binance-shadow.service"],
                              capture_output=True, text=True, timeout=15)
    need(disabled.stdout.strip() == "disabled", "EXISTING_SERVICE_NOT_DISABLED")
    return info

def run_logged(args, filename, timeout, cwd=None):
    start = time.monotonic()
    with (BUILD / filename).open("xb") as log:
        p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             cwd=cwd, start_new_session=True)
        try:
            while True:
                try:
                    code = p.wait(timeout=15)
                    need(code == 0, filename + "_FAILED_SEE_PRIVATE_LOG")
                    return
                except subprocess.TimeoutExpired:
                    need(time.monotonic() - start < timeout, filename + "_TIMEOUT")
                    print("PROGRESS " + filename + " elapsed_seconds=" +
                          str(int(time.monotonic() - start)), flush=True)
        except BaseException:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait(timeout=10)
            raise

def main():
    def interrupted(signum, frame):
        raise InterruptedError("OWNER_SESSION_TERMINATED")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    need(os.geteuid() == 0 and os.uname().nodename == "iZmj7a5kwr75qc1tul4kf9Z",
         "KOREA_ROOT_REQUIRED")
    os.umask(0o077)
    for folder in (Path("/"), Path("/root"), ROOT, Path("/opt")):
        s = folder.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             "UNTRUSTED_PARENT")
    need(stat.S_IMODE(ROOT.lstat().st_mode) == 0o700, "RESTORE_ROOT_NOT_PRIVATE")
    need(not os.path.lexists(BUILD) and not os.path.lexists(DEST), "PRIOR_BUILD_EXISTS_DO_NOT_RERUN")
    receipt = json.loads((ROOT / "receipt.json").read_text())
    need(receipt["status"] == "SELECTED_HISTORICAL_RECOVERY_PASS"
         and receipt["private_manifest_sha256"] == "33826e49503926497f03dc529056ab798de1afedd74493bf3ef164f7aa35c132",
         "RESTORE_RECEIPT_MISMATCH")
    manifest = ROOT / "private-file-manifest.json"
    need(hashlib.sha256(manifest.read_bytes()).hexdigest() == receipt["private_manifest_sha256"],
         "RESTORE_MANIFEST_CHANGED")
    inspection = json.loads((ROOT / "environment-inspection.json").read_text())
    need(not inspection["unsupported"] and
         {normalized(x["name"]) for x in inspection["requirements"]} == {normalized(x) for x in PACKAGES},
         "REQUIREMENTS_SCOPE_CHANGED")
    account = pwd.getpwnam("xuanjun_binance")
    need(account.pw_uid == 986 and account.pw_gid == 986, "DEDICATED_ACCOUNT_CHANGED")
    before = stable_service()
    BUILD.mkdir(mode=0o700)
    try:
        known = sorted(Path("/root").glob("pr99-tokyo-hostkey.*"))
        need(bool(known), "PINNED_KNOWN_HOSTS_MISSING")
        metadata = BUILD / "tokyo-package-metadata.json"
        ssh = ["ssh", "-n", "-T", "-o", "UserKnownHostsFile=" + str(known[0]),
               "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
               "-o", "HostKeyAlgorithms=ecdsa-sha2-nistp256", "-o", "UpdateHostKeys=no",
               "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
               "-o", "NumberOfPasswordPrompts=1", "-o", "ClearAllForwardings=yes",
               "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "root@47.245.53.152",
               "/usr/bin/python3 -I -B -c " + shlex.quote(REMOTE)]
        print("读取东京包版本；请在终端输入东京root密码。", flush=True)
        with metadata.open("xb") as out:
            subprocess.run(ssh, stdin=subprocess.DEVNULL, stdout=out, check=True, timeout=180)
        need(metadata.stat().st_size < 500000, "PACKAGE_METADATA_TOO_LARGE")
        interpreter, versions = select_source(json.loads(metadata.read_text()))
        print("TOKYO_PACKAGE_VERSIONS=PINNED_13; 创建独立环境。", flush=True)
        DEST.mkdir(mode=0o755)
        DEST.chmod(0o755)
        inputs = DEST / "inputs"
        inputs.mkdir(mode=0o755)
        inputs.chmod(0o755)
        requirements = inputs / "requirements.lock"
        constraints = inputs / "source-constraints.txt"
        requirements.write_text("".join(name + "==" + versions[normalized(name)] + "\n" for name in PACKAGES))
        constraints.write_text("".join(name + "==" + version + "\n" for name, version in sorted(versions.items())))
        requirements.chmod(0o444)
        constraints.chmod(0o444)
        venv = DEST / "venv"
        run_logged(["/usr/bin/python3.11", "-I", "-B", "-m", "venv", "--copies", str(venv)],
                   "venv-create.log", 120)
        for p in [venv] + list(venv.rglob("*")):
            os.chown(p, account.pw_uid, account.pw_gid, follow_symlinks=False)
        temp = DEST / "build-tmp"
        temp.mkdir(mode=0o700)
        os.chown(temp, account.pw_uid, account.pw_gid)
        py = venv / "bin/python"
        base = ["runuser", "-u", "xuanjun_binance", "--", "/usr/bin/env", "-i",
                "PATH=/usr/sbin:/usr/bin:/sbin:/bin", "LANG=C.UTF-8",
                "PIP_CONFIG_FILE=/dev/null", "PYTHONNOUSERSITE=1", "PYTHONDONTWRITEBYTECODE=1",
                "TMPDIR=" + str(temp), "OPENBLAS_NUM_THREADS=1",
                str(py), "-I", "-B", "-m", "pip", "--disable-pip-version-check", "--no-input"]
        run_logged(base + ["install", "--index-url", "https://pypi.org/simple",
                   "--no-cache-dir", "--timeout", "30", "--retries", "1", "--prefer-binary",
                   "--only-binary=:all:", "--no-binary=ta", "-r", str(requirements),
                   "-c", str(constraints), "--report", str(temp / "pip-report.json")],
                   "pip-install.log", 1800, cwd=str(DEST))
        run_logged(base + ["check"], "pip-check.log", 60, cwd=str(DEST))
        for p in list(venv.rglob("*")) + [venv]:
            os.chown(p, 0, 0, follow_symlinks=False)
            if not p.is_symlink():
                mode = stat.S_IMODE(p.lstat().st_mode)
                p.chmod(0o755 if p.is_dir() else 0o644 | (mode & 0o111))
        host_ns = os.stat("/proc/self/ns/net").st_ino
        probe = ("import importlib,json,importlib.metadata as m,os,socket;"
                 "assert os.stat('/proc/self/ns/net').st_ino!=" + str(host_ns) + ";"
                 "assert [x[1] for x in socket.if_nameindex()]==['lo'];"
                 "names=" + repr(IMPORTS) + ";"
                 "[importlib.import_module(n) for n in names];"
                 "print(json.dumps({n:m.version(n) for n in " + repr(PACKAGES) + "},sort_keys=True))")
        run_logged(["unshare", "--net", "--", "runuser", "-u", "xuanjun_binance", "--",
                    "/usr/bin/env", "-i", "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
                    "LANG=C.UTF-8", "OPENBLAS_NUM_THREADS=1", str(py), "-I", "-B", "-c", probe],
                   "offline-imports.log", 120, cwd=str(DEST))
        installed = json.loads((BUILD / "offline-imports.log").read_text())
        need(all(installed[name] == versions[normalized(name)] for name in PACKAGES), "INSTALLED_VERSION_MISMATCH")
        after = stable_service()
        need(after == before, "EXISTING_SERVICE_CHANGED")
        result = {"schema_version": 1, "status": "ISOLATED_DEPENDENCY_ENVIRONMENT_PASS",
                  "source_interpreter_profile": interpreter,
                  "source_profile_scope": "DEPENDENCY_METADATA_NOT_PROVEN_WRITER_ENTRYPOINT",
                  "packages": installed, "packages_verified": 13,
                  "pip_check": "PASS", "offline_namespace_imports": "PASS",
                  "venv": str(venv), "source_files_deployed": False,
                  "production_code_executed": False, "api_credentials_read": False,
                  "api_requests": 0, "service_actions": 0,
                  "existing_phase_b_venv_modified": False, "existing_service_state_unchanged": True,
                  "current_final_snapshot": False, "tokyo_retirement": "HOLD"}
        write_json(BUILD / "receipt.json", result)
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as error:
        failed = {"status": "HOLD_PRESERVE_EVIDENCE",
                  "reason": str(error) if isinstance(error, RuntimeError) else type(error).__name__,
                  "logs": str(BUILD), "retry_allowed": False, "service_actions": 0}
        write_json(BUILD / "failure-receipt.json", failed)
        print(json.dumps(failed, sort_keys=True), flush=True)
        raise

if __name__ == "__main__":
    main()
