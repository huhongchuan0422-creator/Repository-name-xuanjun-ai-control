"""Export a bounded, readable candidate payload; never label failure inputs as a release."""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

MODEL_NAMES = {"PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx"}
BUILD_NAMES = ("requirements-lock-linux-x86_64-cp311.json", "SHA256SUMS", "xuanjun-ocr-linux-x86_64-cp311.tar.gz")

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def regular_readable(path):
    return path.is_file() and not path.is_symlink() and os.access(str(path), os.R_OK)

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ["RUNNER_TEMP"])
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else root / "ocr-candidate-inputs" / "payload")
    if dest.exists() or dest.is_symlink():
        raise SystemExit("CANDIDATE_STAGING_MUST_BE_NEW")
    dest.mkdir(parents=True, mode=0o700)
    source_manifest = Path(__file__).with_name("model_manifest.json")
    trusted = {}
    try:
        data = json.loads(source_manifest.read_text(encoding="utf-8"))
        trusted = {item["filename"]: item["sha256"] for item in data["model_set"]["files"].values()}
    except (OSError, ValueError, KeyError, TypeError):
        pass

    candidates, missing = [], []
    def add(path, rel, provenance, required=False):
        if regular_readable(path):
            candidates.append((path, rel, provenance))
        elif required:
            missing.append({"path": rel, "reason": "MISSING_UNREADABLE_OR_NOT_REGULAR"})

    wheel = root / "ocr-wheelhouse"
    if wheel.is_dir() and not wheel.is_symlink():
        for p in sorted(wheel.iterdir()):
            if p.suffix == ".whl":
                add(p, "wheelhouse/" + p.name, "downloaded-from-pypi; locally hashed; not independently pinned")

    models = root / "ocr-model-cache"
    for filename in sorted(MODEL_NAMES):
        p = models / filename
        if regular_readable(p) and trusted.get(filename) == sha(p):
            add(p, "models/" + filename, "FIXED_MODEL_MANIFEST_SHA256_MATCH")
        else:
            add(p, "models/" + filename, "MODEL_SHA_NOT_VERIFIED_AGAINST_FIXED_MANIFEST", required=True)

    debroot = root / "ocr-deb-cache"
    if debroot.is_dir() and not debroot.is_symlink():
        lock = debroot / "system-deb-lock.json"
        lockdata = {}
        if regular_readable(lock):
            try:
                lockdata = json.loads(lock.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                missing.append({"path": "system-deb-lock.json", "reason": "LOCK_INVALID"})
        locked = lockdata.get("packages", []) if isinstance(lockdata, dict) else []
        expected = {x.get("filename"): x for x in locked if isinstance(x, dict) and isinstance(x.get("filename"), str)}
        actual = {p.name for p in debroot.glob("*.deb") if p.is_file() and not p.is_symlink()}
        for filename, item in sorted(expected.items()):
            p = debroot / filename
            if regular_readable(p) and sha(p) == item.get("sha256"):
                add(p, "system-debs/" + filename, "SHA256_MATCHES_LOCK_PACKAGE_VERSION_ARCH")
            else:
                missing.append({"path": "system-debs/" + filename, "reason": "LOCKED_DEB_MISSING_UNREADABLE_OR_SHA_MISMATCH"})
        for filename in sorted(actual - set(expected)):
            add(debroot / filename, "unlocked-debs/" + filename, "UNLOCKED_DEB_NOT_INSTALLABLE")
        add(lock, "system-deb-lock.json", "LOCKED_CANDIDATE_INPUT_NOT_RELEASE", required=True)
        apt_root = debroot / "apt-lists"
        apt_entries = lockdata.get("apt_lists", []) if isinstance(lockdata, dict) else []
        apt_expected = set()
        for item in apt_entries:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                missing.append({"path": "apt-lists", "reason": "APT_INDEX_LOCK_ENTRY_INVALID"})
                continue
            rel = Path(item["path"])
            if rel.is_absolute() or ".." in rel.parts or any(x in ("partial", "auxfiles") for x in rel.parts) or rel.name in ("lock", "partial"):
                missing.append({"path": item["path"], "reason": "APT_INDEX_PATH_REJECTED"})
                continue
            key = str(rel)
            if key in apt_expected:
                missing.append({"path": key, "reason": "APT_INDEX_DUPLICATE"})
                continue
            apt_expected.add(key)
            p = apt_root / rel
            if regular_readable(p) and p.stat().st_size == item.get("bytes") and sha(p) == item.get("sha256"):
                add(p, "apt-lists/" + key, "SHA256_AND_SIZE_MATCH_LOCKED_APT_INDEX")
            else:
                missing.append({"path": "apt-lists/" + key, "reason": "LOCKED_APT_INDEX_MISSING_UNREADABLE_OR_MISMATCH"})
        if apt_root.is_dir() and not apt_root.is_symlink():
            actual_apt = {str(p.relative_to(apt_root)) for p in apt_root.rglob("*") if p.is_file() and not p.is_symlink()}
            for extra in sorted(actual_apt - apt_expected):
                missing.append({"path": "apt-lists/" + extra, "reason": "UNLOCKED_APT_INDEX_EXCLUDED"})

    build = root / "ocr-build"
    if build.is_dir() and not build.is_symlink():
        for name in BUILD_NAMES:
            p = build / name
            if p.exists() or p.is_symlink():
                add(p, "build-output/" + name, "PARTIAL_OR_GENERATED_OUTPUT_NOT_A_RELEASE", required=False)
        pins = build / "source-pins"
        if pins.is_dir() and not pins.is_symlink():
            for p in sorted(pins.iterdir()):
                if p.is_file() and not p.is_symlink():
                    add(p, "source-pins/" + p.name, "COPIED_FROM_EXACT_CHECKED_OUT_SOURCE")

    entries, seen = [], set()
    for src, rel, provenance in candidates:
        if rel in seen:
            raise SystemExit("CANDIDATE_DESTINATION_COLLISION:" + rel)
        seen.add(rel)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        os.chmod(target, 0o644)
        entries.append({"path": rel, "bytes": target.stat().st_size, "sha256": sha(target), "provenance": provenance})
    result = {
        "classification": "CANDIDATE_INPUTS_ONLY_NOT_A_RELEASE_PACKAGE",
        "source_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "files_scope": "exact regular files copied under payload; manifest is separate and not self-hashed",
        "files": entries,
        "missing_or_rejected": missing,
        "complete": not missing,
    }
    manifest = dest.parent / "candidate-input-manifest.json"
    with manifest.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True, indent=2) + "\\n")
    os.chmod(manifest, 0o644)
    print(json.dumps({"classification": result["classification"], "candidate_file_count": len(entries),
                      "missing_or_rejected_count": len(missing), "complete": result["complete"],
                      "manifest_sha256": sha(manifest), "payload_dir": str(dest)}, sort_keys=True))
    # Incomplete inputs remain uploadable diagnostics, but are never represented as complete.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
