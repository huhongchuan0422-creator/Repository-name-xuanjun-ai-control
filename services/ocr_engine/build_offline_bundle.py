"""Offline OCR bundle builder.

No network access, package installation, model download, service start, or deployment.
Building is opt-in via --execute-build and requires an explicit platform lock + staged assets.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_MANIFEST = HERE / "model_manifest.json"
REQUIREMENTS = HERE / "requirements.txt"
LICENSE = HERE / "model_distribution" / "LICENSE-2.0.txt"
NOTICE = HERE / "model_distribution" / "NOTICE.md"
CONFIG_SCHEMA = HERE / "deployment_config.schema.json"
REQUIRED_MODELS = ("det", "rec", "cls")

class BundleError(ValueError):
    pass

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def regular_file(path, label):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise BundleError(label + "_NOT_REGULAR_FILE")
    return path

def validate_inputs(target_platform, lock_path, wheelhouse, model_dir, requirements_path=REQUIREMENTS,
                    manifest_path=MODEL_MANIFEST, license_path=LICENSE, notice_path=NOTICE,
                    config_schema_path=CONFIG_SCHEMA):
    if not isinstance(target_platform, str) or not target_platform.strip() or target_platform != target_platform.strip():
        raise BundleError("TARGET_PLATFORM_REQUIRED_EXPLICITLY")
    lock_path = regular_file(lock_path, "LOCK")
    wheelhouse = Path(wheelhouse)
    model_dir = Path(model_dir)
    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        raise BundleError("WHEELHOUSE_NOT_DIRECTORY")
    if model_dir.is_symlink() or not model_dir.is_dir():
        raise BundleError("MODEL_CACHE_NOT_DIRECTORY")
    for path, label in ((requirements_path,"REQUIREMENTS"),(manifest_path,"MODEL_MANIFEST"),
                        (license_path,"MODEL_LICENSE"),(notice_path,"MODEL_NOTICE"),
                        (config_schema_path,"CONFIG_SCHEMA")):
        regular_file(path, label)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    if lock.get("target_platform") != target_platform:
        raise BundleError("TARGET_PLATFORM_MISMATCH")
    if not lock.get("python_implementation") or not lock.get("python_version") or not lock.get("abi"):
        raise BundleError("LOCK_RUNTIME_ABI_METADATA_MISSING")
    if target_platform == "linux-x86_64-cp311":
        if lock.get("python_implementation") != "CPython" or lock.get("python_version") != "3.11.17" or lock.get("abi") != "cp311" or not isinstance(lock.get("soabi"), str) or not lock.get("soabi").startswith("cpython-311-"):
            raise BundleError("LOCK_RUNTIME_VERSION_MISMATCH")
        if lock.get("base_image") != "python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199":
            raise BundleError("LOCK_BASE_IMAGE_MISMATCH")
        if lock.get("base_image_manifest_sha256") != "8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199":
            raise BundleError("LOCK_BASE_MANIFEST_MISMATCH")
        if lock.get("base_image_config_sha256") != "c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee":
            raise BundleError("LOCK_BASE_CONFIG_MISMATCH")
        if not isinstance(lock.get("glibc_version"), str) or not lock["glibc_version"].startswith("glibc "):
            raise BundleError("LOCK_GLIBC_EVIDENCE_MISSING")
    requirements_sha = sha256_file(Path(requirements_path))
    if lock.get("requirements_sha256") != requirements_sha:
        raise BundleError("REQUIREMENTS_LOCK_INPUT_SHA_MISMATCH")
    target_tags = lock.get("target_tags")
    if not isinstance(target_tags, list) or not target_tags or any(not isinstance(tag, str) or not tag for tag in target_tags):
        raise BundleError("LOCK_TARGET_TAGS_REQUIRED")
    target_tag_set = set(target_tags)
    wheels = lock.get("wheels")
    if not isinstance(wheels, list) or not wheels:
        raise BundleError("LOCK_WHEEL_LIST_EMPTY")
    wheel_names = set()
    verified_wheels = []
    for item in wheels:
        if not isinstance(item, dict) or set(item) != {"filename","sha256"}:
            raise BundleError("LOCK_WHEEL_ENTRY_INVALID")
        name, expected = item["filename"], item["sha256"]
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".whl"):
            raise BundleError("WHEEL_FILENAME_INVALID")
        if name in wheel_names:
            raise BundleError("DUPLICATE_WHEEL_FILENAME")
        wheel_names.add(name)
        if not isinstance(expected, str) or len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
            raise BundleError("WHEEL_SHA256_INVALID")
        path = regular_file(wheelhouse / name, "WHEEL")
        if sha256_file(path) != expected:
            raise BundleError("WHEEL_SHA256_MISMATCH:" + name)
        # Check wheel filename tags and internal WHEEL metadata; do not trust filename alone.
        parts = name[:-4].split("-")
        if len(parts) < 5:
            raise BundleError("WHEEL_FILENAME_TAGS_INVALID:" + name)
        py_tag, abi_tag, platform_tag = parts[-3:]
        filename_tags = {"-".join((py, abi, platform))
                         for py in py_tag.split(".") for abi in abi_tag.split(".") for platform in platform_tag.split(".")}
        if not (filename_tags & target_tag_set) and "py3-none-any" not in filename_tags:
            raise BundleError("WHEEL_TARGET_TAG_MISMATCH:" + name)
        try:
            with zipfile.ZipFile(path, "r") as wheel_zip:
                metadata_files = [n for n in wheel_zip.namelist() if n.endswith(".dist-info/WHEEL")]
                if len(metadata_files) != 1:
                    raise BundleError("WHEEL_INTERNAL_METADATA_MISSING:" + name)
                metadata = wheel_zip.read(metadata_files[0]).decode("utf-8")
                internal_tags = {line[5:].strip() for line in metadata.splitlines() if line.startswith("Tag: ")}
        except (zipfile.BadZipFile, UnicodeError, OSError):
            raise BundleError("WHEEL_INTERNAL_METADATA_INVALID:" + name)
        if not internal_tags:
            raise BundleError("WHEEL_INTERNAL_TAGS_MISSING:" + name)
        if not (internal_tags & filename_tags):
            raise BundleError("WHEEL_FILENAME_INTERNAL_TAG_MISMATCH:" + name)
        if not (internal_tags & target_tag_set) and "py3-none-any" not in internal_tags:
            raise BundleError("WHEEL_INTERNAL_TARGET_TAG_MISMATCH:" + name)
        verified_wheels.append((path, "wheelhouse/" + name))
    model_files = manifest.get("model_set", {}).get("files", {})
    if set(model_files) != set(REQUIRED_MODELS):
        raise BundleError("MODEL_MANIFEST_SET_MISMATCH")
    verified_models = []
    for name in REQUIRED_MODELS:
        item = model_files[name]
        filename, expected = item.get("filename"), item.get("sha256")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise BundleError("MODEL_FILENAME_INVALID:" + name)
        path = regular_file(model_dir / filename, "MODEL")
        if sha256_file(path) != expected:
            raise BundleError("MODEL_SHA256_MISMATCH:" + name)
        verified_models.append((path, "models/" + filename))
    if "Apache License" not in Path(license_path).read_text(encoding="utf-8"):
        raise BundleError("MODEL_LICENSE_CONTENT_INVALID")
    notice = Path(notice_path).read_text(encoding="utf-8")
    for name in REQUIRED_MODELS:
        if model_files[name]["filename"] not in notice or model_files[name]["sha256"] not in notice:
            raise BundleError("MODEL_NOTICE_MISSING_ATTRIBUTION:" + name)
    return {
        "target_platform": target_platform,
        "python_implementation": lock["python_implementation"],
        "python_version": lock["python_version"],
        "abi": lock["abi"],
        "soabi": lock.get("soabi"),
        "target_tags": target_tags,
        "base_image": lock.get("base_image"),
        "base_image_manifest_sha256": lock.get("base_image_manifest_sha256"),
        "base_image_config_sha256": lock.get("base_image_config_sha256"),
        "glibc_version": lock.get("glibc_version"),
        "requirements_sha256": requirements_sha,
        "models": [{"filename": str(path.name), "sha256": model_files[name]["sha256"]} for name,path in zip(REQUIRED_MODELS,[x[0] for x in verified_models])],
        "wheels": [{"filename": path.name, "sha256": sha256_file(path)} for path,_ in verified_wheels],
        "verified_wheels": verified_wheels,
        "verified_models": verified_models,
        "inputs": {
            "manifest_sha256": sha256_file(Path(manifest_path)),
            "license_sha256": sha256_file(Path(license_path)),
            "notice_sha256": sha256_file(Path(notice_path)),
            "config_schema_sha256": sha256_file(Path(config_schema_path)),
            "requirements_sha256": requirements_sha,
        },
        "source_files": {
            "services/ocr_engine/api.py": sha256_file(HERE / "api.py"),
            "services/ocr_engine/ocr_core.py": sha256_file(HERE / "ocr_core.py"),
            "services/ocr_engine/secure_store.py": sha256_file(HERE / "secure_store.py"),
            "services/ocr_engine/startup_selfcheck.py": sha256_file(HERE / "startup_selfcheck.py"),
        },
    }

def publish_no_clobber(temp_path, output_path):
    """Atomically publish without replacing a concurrently-created target."""
    try:
        os.link(str(temp_path), str(output_path), follow_symlinks=False)
    except FileExistsError:
        raise BundleError("OUTPUT_ALREADY_EXISTS_NO_CLOBBER")
    os.unlink(str(temp_path))

def build_bundle(target_platform, lock_path, wheelhouse, model_dir, output_path):
    output = Path(output_path)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise BundleError("OUTPUT_MUST_BE_ABSOLUTE_AND_NOT_EXIST")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise BundleError("OUTPUT_PARENT_MUST_ALREADY_EXIST_AND_NOT_BE_SYMLINK")
    if output.parent.stat().st_mode & 0o022:
        raise BundleError("OUTPUT_PARENT_PERMISSIONS_UNSAFE")
    checked = validate_inputs(target_platform, lock_path, wheelhouse, model_dir,
                              requirements_path=REQUIREMENTS, manifest_path=MODEL_MANIFEST,
                              license_path=LICENSE, notice_path=NOTICE, config_schema_path=CONFIG_SCHEMA)
    archive_manifest = {k:v for k,v in checked.items() if not k.startswith("verified_")}
    archive_manifest["requirements_lock"] = "requirements-lock.json"
    archive_manifest["license_file"] = "LICENSE-2.0.txt"
    archive_manifest["notice_file"] = "NOTICE.md"
    # Freeze only the digests already verified by validate_inputs. Never bless bytes
    # observed after validation as the new source of truth.
    frozen = {
        "services/ocr_engine/model_manifest.json": checked["inputs"]["manifest_sha256"],
        "requirements.txt": checked["requirements_sha256"],
        "LICENSE-2.0.txt": checked["inputs"]["license_sha256"],
        "NOTICE.md": checked["inputs"]["notice_sha256"],
        "deployment_config.schema.json": checked["inputs"]["config_schema_sha256"],
        **checked["source_files"],
    }
    for item in checked["models"]:
        frozen["models/" + item["filename"]] = item["sha256"]
    for item in checked["wheels"]:
        frozen["wheelhouse/" + item["filename"]] = item["sha256"]
    # Detect any validate→freeze race before the first archive member is written.
    current_paths = {
        "services/ocr_engine/model_manifest.json": Path(MODEL_MANIFEST),
        "requirements.txt": Path(REQUIREMENTS),
        "LICENSE-2.0.txt": Path(LICENSE),
        "NOTICE.md": Path(NOTICE),
        "deployment_config.schema.json": Path(CONFIG_SCHEMA),
        "services/ocr_engine/api.py": HERE / "api.py",
        "services/ocr_engine/ocr_core.py": HERE / "ocr_core.py",
        "services/ocr_engine/secure_store.py": HERE / "secure_store.py",
        "services/ocr_engine/startup_selfcheck.py": HERE / "startup_selfcheck.py",
    }
    current_paths.update({"models/" + arcname.split("/",1)[1]: path for path,arcname in checked["verified_models"]})
    current_paths.update({"wheelhouse/" + arcname.split("/",1)[1]: path for path,arcname in checked["verified_wheels"]})
    for arcname, expected_sha in frozen.items():
        path = current_paths[arcname]
        regular_file(path, "BUNDLE_INPUT")
        if sha256_file(path) != expected_sha:
            raise BundleError("VALIDATE_FREEZE_SHA256_MISMATCH:" + arcname)
    with tempfile.NamedTemporaryFile(prefix=".ocr-bundle-", suffix=".tmp", dir=str(output.parent), delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with tarfile.open(temp_path, "w:gz") as archive:
            # Include the exact service source needed to run this package; no unrelated tests or secrets.
            source_files = [
                (HERE / "api.py", "services/ocr_engine/api.py"),
                (HERE / "ocr_core.py", "services/ocr_engine/ocr_core.py"),
                (HERE / "secure_store.py", "services/ocr_engine/secure_store.py"),
                (HERE / "startup_selfcheck.py", "services/ocr_engine/startup_selfcheck.py"),
            ]
            for path, arcname in source_files:
                regular_file(path, "OCR_SOURCE")
                archive.add(str(path), arcname=arcname, recursive=False)
            for path, arcname in (
                (Path(MODEL_MANIFEST), "services/ocr_engine/model_manifest.json"),
                (Path(REQUIREMENTS), "requirements.txt"),
                (Path(LICENSE), "LICENSE-2.0.txt"),
                (Path(NOTICE), "NOTICE.md"),
                (Path(CONFIG_SCHEMA), "deployment_config.schema.json"),
            ):
                archive.add(str(path), arcname=arcname, recursive=False)
            for path, arcname in checked["verified_models"] + checked["verified_wheels"]:
                archive.add(str(path), arcname=arcname, recursive=False)
            lock_payload = {
                "target_platform": checked["target_platform"],
                "python_implementation": checked["python_implementation"],
                "python_version": checked["python_version"],
                "abi": checked["abi"],
                "soabi": checked.get("soabi"),
                "target_tags": checked["target_tags"],
                "base_image": checked.get("base_image"),
                "base_image_manifest_sha256": checked.get("base_image_manifest_sha256"),
                "base_image_config_sha256": checked.get("base_image_config_sha256"),
                "glibc_version": checked.get("glibc_version"),
                "requirements_sha256": checked["requirements_sha256"],
                "wheels": archive_manifest["wheels"],
            }
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as lock_temp:
                lock_temp.write(json.dumps(lock_payload, sort_keys=True, indent=2) + "\n")
                lock_temp_path = Path(lock_temp.name)
            try:
                archive.add(str(lock_temp_path), arcname="requirements-lock.json", recursive=False)
            finally:
                lock_temp_path.unlink(missing_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as manifest_temp:
                manifest_temp.write(json.dumps(archive_manifest, sort_keys=True, indent=2) + "\n")
                bundle_manifest_path = Path(manifest_temp.name)
            try:
                archive.add(str(bundle_manifest_path), arcname="offline-bundle-manifest.json", recursive=False)
            finally:
                bundle_manifest_path.unlink(missing_ok=True)
        # Verify the final archive's exact member set and bytes against the frozen snapshot.
        with tarfile.open(temp_path, "r:gz") as archive:
            members = {member.name: member for member in archive.getmembers() if member.isfile()}
            expected_names = set(frozen) | {"requirements-lock.json", "offline-bundle-manifest.json"}
            if set(members) != expected_names:
                raise BundleError("ARCHIVE_MEMBER_SET_MISMATCH")
            for arcname, expected_sha in frozen.items():
                extracted = archive.extractfile(members[arcname])
                if extracted is None:
                    raise BundleError("ARCHIVE_MEMBER_UNREADABLE:" + arcname)
                digest = hashlib.sha256()
                for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                    digest.update(chunk)
                if digest.hexdigest() != expected_sha:
                    raise BundleError("ARCHIVE_MEMBER_SHA256_MISMATCH:" + arcname)
            lock_member = archive.extractfile(members["requirements-lock.json"])
            lock_in_archive = json.loads(lock_member.read().decode("utf-8"))
            if lock_in_archive.get("target_platform") != target_platform or lock_in_archive.get("target_tags") != checked["target_tags"]:
                raise BundleError("ARCHIVE_LOCK_BINDING_MISMATCH")
            manifest_member = archive.extractfile(members["offline-bundle-manifest.json"])
            manifest_in_archive = json.loads(manifest_member.read().decode("utf-8"))
            if manifest_in_archive.get("target_platform") != target_platform or manifest_in_archive.get("inputs") != checked["inputs"]:
                raise BundleError("ARCHIVE_MANIFEST_BINDING_MISMATCH")
        os.chmod(temp_path, 0o600)
        # Atomic no-clobber publication: link creation fails if another process wins the name.
        publish_no_clobber(temp_path, output)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {"output": str(output), "sha256": sha256_file(output), "target_platform": target_platform,
            "model_count": 3, "wheel_count": len(checked["wheels"])}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-platform", required=True, help="Exact platform tag from a reviewed lock; never inferred")
    parser.add_argument("--lock-json", required=True, help="Externally prepared platform-specific lock JSON")
    parser.add_argument("--wheelhouse", required=True, help="Pre-staged wheel directory; no network access")
    parser.add_argument("--model-cache", required=True, help="Pre-staged ONNX model directory; no network access")
    parser.add_argument("--output", required=True, help="Absolute path to a not-yet-existing archive")
    parser.add_argument("--execute-build", action="store_true", help="Explicitly permit local archive creation")
    args = parser.parse_args(argv)
    if not args.execute_build:
        print(json.dumps({"status":"HOLD","reason":"EXPLICIT_BUILD_FLAG_REQUIRED","network":"DISABLED","service_start":"NOT_PERFORMED"}))
        return 3
    try:
        result = build_bundle(args.target_platform, args.lock_json, args.wheelhouse, args.model_cache, args.output)
    except (BundleError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc),"network":"DISABLED","service_start":"NOT_PERFORMED"}, sort_keys=True))
        return 2
    print(json.dumps({"status":"BUILT","result":result,"network":"DISABLED","service_start":"NOT_PERFORMED"},sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
