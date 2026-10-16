"""Deterministic offline review bundle; never packages credentials or databases."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

from gate_common import canonical_bytes, require
from korea.phase_c.security import digest, read_file, strict_json

PREFIX = "migration-prep/korea/phase_c/"
ADAPTERS = tuple(PREFIX + name for name in (
    "__init__.py", "security.py", "network.py", "credentials.py", "snapshots.py",
    "broker.py", "runtime.py", "entry.py", "artifact.py", "prepare.py", "resources.py",
    "authorization.py", "install_controller.py", "root_handoff.py", "private_transfer.py", "lifecycle.py", "fence.py"))
REUSED = tuple("migration-prep/" + name for name in (
    "gate_common.py", "final_snapshot.py", "readonly_reconciliation_adapter.py",
    "korea/__init__.py", "korea/get_only_policy.py", "korea/migration_shadow_entry.py",
    "korea/snapshot_handoff.py", "korea/shadow_acceptance.py"))
TEMPLATES = tuple(PREFIX + name for name in ("broker.service.in", "worker.service.in", "network-verified.target.in"))
RUNTIME_FILES = tuple(sorted(ADAPTERS + REUSED + TEMPLATES))
REVIEW_FILES = RUNTIME_FILES + tuple(PREFIX + name for name in (
    "test_phase_c.py", "test_install_controller.py", "test_root_handoff.py", "test_private_transfer.py", "test_lifecycle.py", "test_fence.py", "source_contracts.py", "test_source_contracts.py", "source_schema.py", "test_source_schema.py", "README.md")) + ("migration-prep/korea/shadow-acceptance.template.json",)


def runtime_manifest(root):
    rows = []
    for name in RUNTIME_FILES:
        path = Path(root) / name
        require(path.is_file() and not path.is_symlink(), "C_BUILD_SOURCE_REGULAR")
        data = path.read_bytes()
        rows.append({"path": name, "sha256": digest(data), "size": len(data)})
    return {"schema_version": 1, "artifact_role": "PR99_PHASE_C_OFFLINE_ADAPTER_CANDIDATE",
            "files": rows, "production_authorized": False, "provider_requests": 0}


def verify_runtime(root, expected):
    root = Path(root)
    raw = read_file(root / "PHASE_C_RUNTIME_MANIFEST.json", modes=(0o400, 0o444, 0o644))
    require(digest(raw) == expected, "C_RUNTIME_MANIFEST_PIN")
    manifest = strict_json(raw)
    require(manifest == runtime_manifest(root), "C_RUNTIME_BYTES_CHANGED")
    # Additionally require actual installed ownership/path protection, not just hash.
    for row in manifest["files"]:
        data = read_file(root / row["path"], modes=(0o400, 0o444, 0o644), limit=1048576)
        require(digest(data) == row["sha256"], "C_INSTALLED_RUNTIME_IDENTITY")
    return manifest


def build(root, commit, output):
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "C_BUILD_EXACT_COMMIT")
    root = Path(root)
    files = {}
    for name in REVIEW_FILES:
        path = root / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1048576,
                "C_REVIEW_SOURCE_REGULAR_BOUNDED")
        files[name] = path.read_bytes()
    files["PHASE_C_RUNTIME_MANIFEST.json"] = canonical_bytes(runtime_manifest(root)) + b"\n"
    binding = {"schema_version": 1, "source_commit": commit,
               "scope": "OFFLINE_CODE_REVIEW_ONLY_NOT_INSTALL_PERMISSION",
               "files": {name: digest(raw) for name, raw in sorted(files.items())},
               "phase_b_frozen_manifest": "f887b085508e3ed4831dbed22152e35af5e8aba95b85b899b4697c61449917de",
               "production_authorized": False}
    files["REVIEW_BINDING.json"] = canonical_bytes(binding) + b"\n"
    output = Path(output)
    with output.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.mode = 0o400; info.size = len(data); info.mtime = 0
                    info.uid = info.gid = 0; info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    return {"source_commit": commit, "sha256": digest(output.read_bytes()),
            "size": output.stat().st_size, "bound_files": len(binding["files"]),
            "runtime_manifest_sha256": digest(files["PHASE_C_RUNTIME_MANIFEST.json"]),
            "production_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[3], args.commit, args.output), sort_keys=True))
