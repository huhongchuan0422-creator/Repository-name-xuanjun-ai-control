"""Render systemd239 candidate units in memory. No installation or service action."""
from pathlib import Path
import re

from gate_common import require


def render_units(values):
    fields = {"C_RELEASE", "PYTHON", "C_CONFIG", "C_CONFIG_ROOT", "C_CREDENTIAL_ROOT",
              "C_KEY_ROOT", "C_PRIVATE_KEY_ROOT", "C_SNAPSHOT_ROOT", "C_EVIDENCE_ROOT",
              "RUNTIME_SECONDS"}
    require(set(values) == fields, "C_RENDER_FIELDS")
    for name, value in values.items():
        if name == "RUNTIME_SECONDS":
            require(type(value) is int and 60 <= value <= 7 * 86400, "C_RENDER_DURATION")
        else:
            require(type(value) is str and re.fullmatch(r"/[a-zA-Z0-9_./-]+", value) and
                    ".." not in Path(value).parts and "//" not in value, "C_RENDER_PATH")
    require(re.fullmatch(r"/opt/xuanjun-binance-phase-c/releases/[0-9a-f]{64}", values["C_RELEASE"]),
            "C_NEW_RELEASE_ONLY")
    require(values["PYTHON"] == "/usr/bin/python3.11" and
            values["C_CONFIG_ROOT"] == "/etc/xuanjun-binance-phase-c" and
            values["C_CONFIG"].startswith(values["C_CONFIG_ROOT"] + "/") and
            values["C_CREDENTIAL_ROOT"] == "/run/xuanjun-phase-c-credentials" and
            values["C_PRIVATE_KEY_ROOT"] == "/run/xuanjun-phase-c-private-keys" and
            values["C_KEY_ROOT"] == "/etc/xuanjun-binance-phase-c/keys" and
            values["C_SNAPSHOT_ROOT"] == "/var/lib/xuanjun-binance-phase-c/snapshots" and
            values["C_EVIDENCE_ROOT"] == "/var/lib/xuanjun-binance-phase-c/evidence",
            "C_RENDER_DEDICATED_SCOPE")
    root = Path(__file__).parent
    result = {}
    for name in ("broker.service", "worker.service", "network-verified.target", "controller.service"):
        data = (root / (name + ".in")).read_text()
        for key, value in values.items():
            data = data.replace("@" + key + "@", str(value))
        data = data.replace("@CONTROL_RUNTIME_SECONDS@", str(values["RUNTIME_SECONDS"]+120))
        require("@" not in data, "C_RENDER_UNRESOLVED_TOKEN")
        result[name] = data
    return result
