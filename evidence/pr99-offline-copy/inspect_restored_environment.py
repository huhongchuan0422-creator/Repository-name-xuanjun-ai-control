#!/usr/bin/python3.11
"""Read restored requirements and existing environment metadata; no pip install/imports."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

root = Path("/root/xuanjun-offline-selected-20261016")
assert os.geteuid() == 0 and os.uname().nodename == "iZmj7a5kwr75qc1tul4kf9Z"
os.umask(0o077)
s = root.lstat()
assert stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o700
manifest = root / "private-file-manifest.json"
assert not manifest.is_symlink()
data = manifest.read_bytes()
assert hashlib.sha256(data).hexdigest() == "33826e49503926497f03dc529056ab798de1afedd74493bf3ef164f7aa35c132"
rows = json.loads(data)["files"]
requirements = []
unsupported = []
for row in rows:
    leaf = Path(row["path"]).name
    if leaf.startswith(("requirements", "constraints")) and leaf.endswith(".txt"):
        p = root / row["path"]
        assert p.is_relative_to(root) and not p.is_symlink()
        raw = p.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        for i, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.\[\],<>=!~; '\"()-]+", line):
                unsupported.append({"file": row["path"], "line": i, "detail": "PRIVATE_OR_NONSTANDARD_REQUIREMENT_NOT_PRINTED"})
                continue
            match = re.match(r"([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
            if not match:
                unsupported.append({"file": row["path"], "line": i, "detail": "UNPARSED"})
                continue
            requirements.append({"name": match.group(1), "declared": line})
assert requirements, "NO_PARSEABLE_REQUIREMENTS"
normal = lambda name: re.sub(r"[-_.]+", "-", name).lower()
code = "import importlib.metadata as m,json;print(json.dumps({d.metadata['Name']:d.version for d in m.distributions() if d.metadata.get('Name')}))"
environments = {}
for name, executable in (("system", "/usr/bin/python3.11"),
                         ("existing_phase_b", "/opt/xuanjun-binance/venv/bin/python")):
    if not Path(executable).is_file():
        environments[name] = {"present": False}
        continue
    raw = subprocess.check_output([executable, "-I", "-B", "-c", code],
                                  text=True, timeout=20)
    versions = {normal(k): v for k, v in json.loads(raw).items()}
    environments[name] = {"present": True, "packages": {
        r["name"]: versions.get(normal(r["name"]), "MISSING") for r in requirements}}
result = {"status": "RESTORED_REQUIREMENTS_AND_EXISTING_ENV_INSPECTED",
          "requirements": requirements, "unsupported": unsupported,
          "environments": environments, "packages_installed": 0,
          "production_imports": 0, "service_actions": 0, "network_requests": 0,
          "environment_ready": "NOT_CLAIMED_VERSION_CONSTRAINTS_AND_ENTRYPOINT_NOT_VERIFIED"}
out = root / "environment-inspection.json"
if not os.path.lexists(out):
    with out.open("x") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
else:
    assert out.read_text().strip() == json.dumps(result, sort_keys=True, indent=2)
print(json.dumps(result, sort_keys=True))
