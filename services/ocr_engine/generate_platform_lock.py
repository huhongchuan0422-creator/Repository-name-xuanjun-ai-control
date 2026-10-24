"""Generate a platform lock from the actual pinned OCR base runtime."""
import hashlib
import json
import os
import platform
import sys
import sysconfig
from pathlib import Path
from pip._vendor.packaging.tags import sys_tags

BASE_IMAGE = "python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199"
BASE_MANIFEST_SHA256 = "8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199"
BASE_CONFIG_SHA256 = "c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee"
TARGET = "linux-x86_64-cp311"

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/src")
    wheel_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "/wheelhouse")
    output = Path(sys.argv[3] if len(sys.argv) > 3 else "/build/requirements-lock-linux-x86_64-cp311.json")
    req = root / "services/ocr_engine/requirements.txt"
    if platform.python_implementation() != "CPython" or platform.python_version() != "3.11.17" or platform.machine() != "x86_64":
        raise SystemExit("TARGET_RUNTIME_MISMATCH")
    if os.environ.get("OCR_BASE_IMAGE") != BASE_IMAGE or os.environ.get("OCR_BASE_MANIFEST_SHA256") != BASE_MANIFEST_SHA256 or os.environ.get("OCR_BASE_CONFIG_SHA256") != BASE_CONFIG_SHA256:
        raise SystemExit("BASE_IMAGE_BINDING_MISMATCH")
    wheels = sorted(wheel_dir.glob("*.whl"))
    if not wheels:
        raise SystemExit("WHEELHOUSE_EMPTY")
    lock = {
        "target_platform": TARGET,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "abi": "cp311",
        "soabi": sysconfig.get_config_var("SOABI"),
        "base_image": BASE_IMAGE,
        "base_image_manifest_sha256": BASE_MANIFEST_SHA256,
        "base_image_config_sha256": BASE_CONFIG_SHA256,
        "glibc_version": os.confstr("CS_GNU_LIBC_VERSION"),
        "target_tags": [str(tag) for tag in sys_tags()],
        "requirements_sha256": hashlib.sha256(req.read_bytes()).hexdigest(),
        "wheels": [{"filename": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in wheels],
    }
    output.write_text(json.dumps(lock, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"target": TARGET, "python": lock["python_version"], "soabi": lock["soabi"], "glibc": lock["glibc_version"], "wheel_count": len(wheels)}, sort_keys=True))

if __name__ == "__main__":
    main()
