"""Validate the extracted Korea runtime without workspace fallbacks or network."""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(root, expected_manifest_sha256=None, run_import=True):
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("RUNTIME_CANDIDATE_ROOT_INVALID")
    manifest_path = root / "minimal-runtime-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError("RUNTIME_CANDIDATE_MANIFEST_INVALID")
    manifest_sha = _sha(manifest_path)
    if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
        raise RuntimeError("RUNTIME_CANDIDATE_MANIFEST_HASH_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise RuntimeError("RUNTIME_CANDIDATE_MANIFEST_SCHEMA_INVALID")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise RuntimeError("RUNTIME_CANDIDATE_FILE_LIST_INVALID")
    expected = set()
    content_rows = []
    for record in records:
        if set(record) != {"path", "size", "sha256"}:
            raise RuntimeError("RUNTIME_CANDIDATE_RECORD_FIELDS_INVALID")
        name = record["path"]
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts or name in expected:
            raise RuntimeError("RUNTIME_CANDIDATE_PATH_INVALID")
        expected.add(name)
        target = root / candidate
        if not target.is_file() or target.is_symlink():
            raise RuntimeError("RUNTIME_CANDIDATE_FILE_INVALID:" + name)
        value = target.stat()
        if value.st_size != record["size"] or _sha(target) != record["sha256"]:
            raise RuntimeError("RUNTIME_CANDIDATE_FILE_IDENTITY_MISMATCH:" + name)
        content_rows.append(name + "\0" + record["sha256"])
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("RUNTIME_CANDIDATE_SYMLINK_FORBIDDEN")
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(root).as_posix())
    if actual != expected:
        raise RuntimeError("RUNTIME_CANDIDATE_EXACT_FILE_SET_MISMATCH")
    content_sha = hashlib.sha256("\n".join(content_rows).encode("utf-8")).hexdigest()
    if content_sha != manifest.get("content_sha256"):
        raise RuntimeError("RUNTIME_CANDIDATE_CONTENT_HASH_MISMATCH")
    import_receipt = None
    if run_import:
        module_root = root / "migration-prep"
        code = (
            "import json,sys;sys.path.insert(0,sys.argv[1]);"
            "from korea.migration_shadow_entry import self_check;"
            "from korea.shadow_acceptance import validate_acceptance_config;"
            "print(json.dumps(self_check(),sort_keys=True))"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-I", "-c", code, str(module_root)],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False, env={"PATH": os.environ.get("PATH", "")},
        )
        if result.returncode != 0:
            raise RuntimeError("RUNTIME_CANDIDATE_ISOLATED_IMPORT_FAILED")
        import_receipt = json.loads(result.stdout.decode("utf-8"))
        if import_receipt.get("status") != "SELF_CHECK_PASS_NO_NETWORK":
            raise RuntimeError("RUNTIME_CANDIDATE_SELF_CHECK_FAILED")
    return {"status": "RUNTIME_CANDIDATE_INPUT_PASS",
            "manifest_sha256": manifest_sha, "content_sha256": content_sha,
            "file_count": len(records), "isolated_import": import_receipt,
            "workspace_fallback_used": False, "binance_called": False,
            "production_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--no-import", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = validate(args.root, args.expected_manifest_sha256,
                         run_import=not args.no_import)
        print(json.dumps(value, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "HOLD", "error_type": type(error).__name__,
                          "production_authorized": False}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
