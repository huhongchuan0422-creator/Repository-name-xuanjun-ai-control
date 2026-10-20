#!/usr/bin/env python3
"""Build the PR122 delta bundle without repacking the immutable source site."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "deploy" / "pr122-domestic-website"
SOURCE_PREFIX = "package/public/"
SOURCE_MANIFEST = "package/MANIFEST.json"
TARGET_ASSET = "assets/tiktok-integration.js"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def load_source(source: Path) -> tuple[dict, bytes]:
    pin = json.loads((CANDIDATE / "source-pin.json").read_text())
    if source.stat().st_size != pin["source_archive_size"]:
        raise ValueError("SOURCE_ARCHIVE_SIZE_MISMATCH")
    if sha256_file(source) != pin["source_archive_sha256"]:
        raise ValueError("SOURCE_ARCHIVE_SHA256_MISMATCH")
    with tarfile.open(source, "r:gz") as archive:
        by_name = {member.name: member for member in archive.getmembers()}
        if any(not safe_member(member.name) for member in by_name.values()):
            raise ValueError("UNSAFE_SOURCE_MEMBER_PATH")
        manifest_member = by_name.get(SOURCE_MANIFEST)
        asset_member = by_name.get(SOURCE_PREFIX + TARGET_ASSET)
        if not manifest_member or not manifest_member.isfile() or not asset_member or not asset_member.isfile():
            raise ValueError("REQUIRED_SOURCE_MEMBER_MISSING")
        manifest_bytes = archive.extractfile(manifest_member).read()
        if sha256_bytes(manifest_bytes) != pin["source_manifest_sha256"]:
            raise ValueError("SOURCE_MANIFEST_SHA256_MISMATCH")
        asset_bytes = archive.extractfile(asset_member).read()
    if sha256_bytes(asset_bytes) != pin["overlay_baselines"][TARGET_ASSET]:
        raise ValueError("OVERLAY_BASELINE_DRIFT")
    return json.loads(manifest_bytes), asset_bytes


def build_final_manifest(source_manifest: dict) -> dict:
    overlay = CANDIDATE / "overlay" / "public" / TARGET_ASSET
    overlay_bytes = overlay.read_bytes()
    records = source_manifest["files"]
    matching = [record for record in records if record["path"] == TARGET_ASSET]
    if len(matching) != 1:
        raise ValueError("SOURCE_MANIFEST_TARGET_AMBIGUOUS")
    old_size = matching[0]["size"]
    matching[0].update({"sha256": sha256_bytes(overlay_bytes), "size": len(overlay_bytes), "mode": "0644", "uid": 0, "gid": 0})
    if source_manifest.get("file_count") != len(records):
        raise ValueError("SOURCE_MANIFEST_COUNT_MISMATCH")
    source_total = sum(record["size"] for record in records) - len(overlay_bytes) + old_size
    pin = json.loads((CANDIDATE / "source-pin.json").read_text())
    if source_total != pin["source_total_size"]:
        raise ValueError("SOURCE_MANIFEST_TOTAL_MISMATCH")
    return {
        "schema_version": 1,
        "base_archive_sha256": pin["source_archive_sha256"],
        "base_source_version": pin["source_version"],
        "file_count": len(records),
        "total_size": sum(record["size"] for record in records),
        "files": sorted(records, key=lambda record: record["path"]),
    }


def bundle_sources():
    for path in sorted(CANDIDATE.rglob("*")):
        if path.is_file() and path.name != "PACKAGE_MANIFEST.json":
            yield path, path.relative_to(CANDIDATE).as_posix()
    yield ROOT / "scripts" / "pr122_website_release.py", "bin/pr122_website_release.py"


def bundle_file_manifest() -> dict:
    files = []
    for path, relative in bundle_sources():
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return {"schema_version": 1, "files": files}


def deterministic_bundle(output: Path) -> None:
    package_manifest = CANDIDATE / "PACKAGE_MANIFEST.json"
    package_manifest.write_bytes(canonical_json(bundle_file_manifest()))
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                package_manifest = CANDIDATE / "PACKAGE_MANIFEST.json"
                sources = list(bundle_sources()) + [(package_manifest, "PACKAGE_MANIFEST.json")]
                for path, relative_name in sorted(sources, key=lambda item: item[1]):
                    relative = Path("pr122-domestic-website-candidate") / relative_name
                    info = tarfile.TarInfo(relative.as_posix())
                    payload = path.read_bytes()
                    info.size = len(payload)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                    archive.addfile(info, io.BytesIO(payload))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_manifest, _ = load_source(args.source_archive)
    final_manifest = build_final_manifest(source_manifest)
    (CANDIDATE / "candidate-manifest.json").write_bytes(canonical_json(final_manifest))
    deterministic_bundle(args.output)
    print(json.dumps({
        "status": "PASS",
        "bundle": str(args.output),
        "bundle_sha256": sha256_file(args.output),
        "candidate_manifest_sha256": sha256_file(CANDIDATE / "candidate-manifest.json"),
        "file_count": final_manifest["file_count"],
        "total_size": final_manifest["total_size"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
