"""Export exact, hash-verified candidate bytes; a failed candidate is never a release."""
import hashlib
import json
import os
import sys
from pathlib import Path

MODEL_NAMES = {"PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx"}
BUILD_NAMES = ("requirements-lock-linux-x86_64-cp311.json", "SHA256SUMS", "xuanjun-ocr-linux-x86_64-cp311.tar.gz")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def readable_regular(path):
    return path.is_file() and not path.is_symlink() and os.access(str(path), os.R_OK)

def read_snapshot(path):
    if not readable_regular(path):
        raise OSError("MISSING_UNREADABLE_OR_NOT_REGULAR:" + str(path))
    data = path.read_bytes()
    return data, digest(data)

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ["RUNNER_TEMP"])
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else root / "ocr-candidate-inputs" / "payload")
    if dest.exists() or dest.is_symlink():
        raise SystemExit("CANDIDATE_STAGING_MUST_BE_NEW")
    dest.mkdir(parents=True, mode=0o700)

    missing, snapshots, labels = [], {}, {}
    def stage_source(path, rel, label, expected=None, required=False):
        try:
            data, observed = read_snapshot(path)
        except (OSError, ValueError) as exc:
            if required:
                missing.append({"path": rel, "reason": str(exc)})
            return
        if expected is not None and observed != expected:
            missing.append({"path": rel, "reason": "SOURCE_SHA_MISMATCH_FROZEN_EXPECTED"})
            return
        snapshots[rel] = data
        labels[rel] = label

    model_manifest_path = Path(__file__).with_name("model_manifest.json")
    try:
        model_manifest_bytes, model_manifest_sha = read_snapshot(model_manifest_path)
        model_manifest = json.loads(model_manifest_bytes.decode("utf-8"))
        model_pins = {item["filename"]: item["sha256"] for item in model_manifest["model_set"]["files"].values()}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        model_manifest_bytes, model_manifest_sha, model_pins = None, None, {}
        missing.append({"path": "source-pins/model_manifest.json", "reason": "FIXED_MODEL_MANIFEST_INVALID:" + str(exc)})

    wheel_root = root / "ocr-wheelhouse"
    if wheel_root.is_dir() and not wheel_root.is_symlink():
        for path in sorted(wheel_root.iterdir()):
            if path.suffix == ".whl":
                stage_source(path, "wheelhouse/" + path.name, "DOWNLOADED_WHEEL_LOCALLY_HASHED_NOT_INDEPENDENTLY_PINNED")

    model_root = root / "ocr-model-cache"
    for name in sorted(MODEL_NAMES):
        expected = model_pins.get(name)
        if not isinstance(expected, str):
            missing.append({"path": "models/" + name, "reason": "FIXED_MODEL_PIN_MISSING"})
        else:
            stage_source(model_root / name, "models/" + name, "FIXED_MODEL_MANIFEST_SHA256_MATCH", expected, True)

    deb_root = root / "ocr-deb-cache"
    if deb_root.is_dir() and not deb_root.is_symlink():
        lock_path = deb_root / "system-deb-lock.json"
        lock_bytes = None
        lock_sha = None
        lock_data = {}
        try:
            lock_bytes, lock_sha = read_snapshot(lock_path)
            lock_data = json.loads(lock_bytes.decode("utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            missing.append({"path": "system-deb-lock.json", "reason": "LOCK_INVALID:" + str(exc)})
        if lock_bytes is not None:
            snapshots["system-deb-lock.json"] = lock_bytes
            labels["system-deb-lock.json"] = "EXACT_LOCK_SNAPSHOT_NOT_A_RELEASE"
        packages = lock_data.get("packages", []) if isinstance(lock_data, dict) else []
        expected_debs = {}
        for item in packages:
            if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
                missing.append({"path": "system-deb-lock.json", "reason": "LOCK_PACKAGE_ENTRY_INVALID"})
                continue
            filename = item["filename"]
            if Path(filename).name != filename or not filename.endswith(".deb") or filename in expected_debs:
                missing.append({"path": filename, "reason": "LOCK_PACKAGE_FILENAME_INVALID_OR_DUPLICATE"})
                continue
            expected_debs[filename] = item
        actual_debs = {p.name for p in deb_root.glob("*.deb") if p.is_file() and not p.is_symlink()}
        for filename, item in sorted(expected_debs.items()):
            stage_source(deb_root / filename, "system-debs/" + filename,
                         "SHA256_MATCHES_FROZEN_LOCK_PACKAGE_VERSION_ARCH", item.get("sha256"), True)
        for filename in sorted(actual_debs - set(expected_debs)):
            missing.append({"path": "system-debs/" + filename, "reason": "UNLOCKED_DEB_EXCLUDED_FROM_EXACT_SET"})

        apt_root = deb_root / "apt-lists"
        apt_items = lock_data.get("apt_lists", []) if isinstance(lock_data, dict) else []
        expected_indexes = {}
        if not apt_items:
            missing.append({"path": "apt-lists", "reason": "APT_INDEX_LOCK_EMPTY"})
        for item in apt_items:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                missing.append({"path": "apt-lists", "reason": "APT_INDEX_ENTRY_INVALID"})
                continue
            rel = Path(item["path"])
            key = str(rel)
            if rel.is_absolute() or ".." in rel.parts or any(p in ("partial", "auxfiles") for p in rel.parts) or rel.name in ("lock", "partial") or key in expected_indexes:
                missing.append({"path": key, "reason": "APT_INDEX_PATH_INVALID_OR_DUPLICATE"})
                continue
            expected_indexes[key] = item
        for key, item in sorted(expected_indexes.items()):
            try:
                data, observed = read_snapshot(apt_root / key)
                if len(data) != item.get("bytes") or observed != item.get("sha256"):
                    missing.append({"path": "apt-lists/" + key, "reason": "APT_INDEX_BYTES_OR_SHA_MISMATCH_FROZEN_LOCK"})
                else:
                    snapshots["apt-lists/" + key] = data
                    labels["apt-lists/" + key] = "SIZE_AND_SHA256_MATCH_FROZEN_APT_INDEX_LOCK"
            except (OSError, ValueError) as exc:
                missing.append({"path": "apt-lists/" + key, "reason": str(exc)})
        if apt_root.is_dir() and not apt_root.is_symlink():
            actual_indexes = {str(p.relative_to(apt_root)) for p in apt_root.rglob("*") if p.is_file() and not p.is_symlink()}
            for key in sorted(actual_indexes - set(expected_indexes)):
                if key == "lock" or "partial" in Path(key).parts or "auxfiles" in Path(key).parts:
                    continue
                missing.append({"path": "apt-lists/" + key, "reason": "UNLOCKED_APT_INDEX_EXCLUDED"})

    build_root = root / "ocr-build"
    if build_root.is_dir() and not build_root.is_symlink():
        for name in BUILD_NAMES:
            path = build_root / name
            if path.exists() or path.is_symlink():
                stage_source(path, "build-output/" + name, "PARTIAL_OR_GENERATED_OUTPUT_NOT_A_RELEASE")
        pins = build_root / "source-pins"
        if pins.is_dir() and not pins.is_symlink():
            for path in sorted(pins.iterdir()):
                if path.is_file() and not path.is_symlink():
                    stage_source(path, "source-pins/" + path.name, "EXACT_CHECKED_OUT_SOURCE_COPY")

    # Write the bytes already read and validated; never reread mutable sources as authority.
    entries = []
    for rel, data in sorted(snapshots.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        os.chmod(target, 0o644)
        copied = target.read_bytes()
        observed = digest(copied)
        if observed != digest(data):
            raise SystemExit("CANDIDATE_COPY_SHA_MISMATCH:" + rel)
        entries.append({"path": rel, "bytes": len(copied), "sha256": observed, "provenance": labels[rel]})

    result = {
        "classification": "CANDIDATE_INPUTS_ONLY_NOT_A_RELEASE_PACKAGE",
        "source_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "files_scope": "exact copied payload; manifest is separate and not self-hashed",
        "files": entries,
        "missing_or_rejected": missing,
        "complete": not missing,
    }
    manifest = dest.parent / "candidate-input-manifest.json"
    manifest_bytes = (json.dumps(result, sort_keys=True, indent=2) + chr(10)).encode("utf-8")
    with manifest.open("xb") as stream:
        stream.write(manifest_bytes)
    os.chmod(manifest, 0o644)
    # Parse the final persisted bytes; a malformed manifest must fail this step.
    parsed = json.loads(manifest.read_bytes().decode("utf-8"))
    if parsed != result:
        raise SystemExit("CANDIDATE_MANIFEST_READBACK_MISMATCH")
    print(json.dumps({"classification": result["classification"], "candidate_file_count": len(entries),
                      "missing_or_rejected_count": len(missing), "complete": result["complete"],
                      "manifest_sha256": digest(manifest.read_bytes()), "payload_dir": str(dest)}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
