"""Lock a downloaded Debian closure without mutating APT's working cache."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = "python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def regular_file(path):
    return path.is_file() and not path.is_symlink()

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/debs")
    source = Path(sys.argv[2] if len(sys.argv) > 2 else "/etc/apt/sources.list.d/debian.sources")
    apt_root = Path(sys.argv[3] if len(sys.argv) > 3 else "/var/lib/apt/lists")
    out = root / "system-deb-lock.json"
    if root.is_symlink() or not root.is_dir():
        raise SystemExit("DEB_CACHE_INVALID")
    if source.is_symlink() or not regular_file(source):
        raise SystemExit("OFFICIAL_APT_SOURCE_FILE_MISSING")
    if apt_root.is_symlink() or not apt_root.is_dir():
        raise SystemExit("APT_WORK_DIRECTORY_INVALID")

    packages = []
    for path in sorted(root.glob("*.deb")):
        if path.is_symlink() or not path.is_file():
            raise SystemExit("DEB_NOT_REGULAR_FILE:" + path.name)
        fields = [subprocess.check_output(["dpkg-deb", "-f", str(path), field], text=True).strip()
                  for field in ("Package", "Version", "Architecture")]
        if any(not value or "\\n" in value for value in fields):
            raise SystemExit("DEB_METADATA_INVALID:" + path.name)
        packages.append({"filename": path.name, "package": fields[0], "version": fields[1],
                         "architecture": fields[2], "sha256": sha(path)})
    if not packages:
        raise SystemExit("DEB_CLOSURE_EMPTY")

    source_bytes = source.read_bytes()
    source_text = source_bytes.decode("utf-8")
    uris = [line.split(":", 1)[1].strip().split() for line in source_text.splitlines()
            if line.strip().startswith("URIs:")]
    allowed = ("https://deb.debian.org/", "http://deb.debian.org/",
               "https://security.debian.org/", "http://security.debian.org/")
    if not uris or any(not uri.startswith(allowed) for group in uris for uri in group):
        raise SystemExit("APT_SOURCE_NOT_OFFICIAL_DEBIAN")

    # Copy the exact readable immutable index set to a separate controlled staging
    # directory. Never chmod, chown, or otherwise mutate APT's working files.
    stage = root / "apt-lists"
    if stage.exists() or stage.is_symlink():
        raise SystemExit("APT_INDEX_STAGING_ALREADY_EXISTS")
    stage.mkdir(mode=0o755)
    indexes = []
    excluded = {"lock", "partial"}
    try:
        for path in sorted(apt_root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(apt_root)
            if any(part in ("partial", "auxfiles") for part in rel.parts) or path.name in excluded:
                continue
            try:
                with path.open("rb") as stream:
                    stream.read(1)
            except OSError as exc:
                raise SystemExit("APT_INDEX_UNREADABLE:" + str(rel) + ":" + str(exc))
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            os.chmod(target, 0o644)
            indexes.append({"path": str(rel), "bytes": target.stat().st_size, "sha256": sha(target)})
        if not indexes:
            raise SystemExit("APT_INDEX_CACHE_EMPTY")
        lock = {"base_image": BASE,
                "apt_source": {"path": source.name, "sha256": hashlib.sha256(source_bytes).hexdigest(),
                               "content": source_text},
                "packages": packages, "apt_lists": indexes}
        lock_bytes = (json.dumps(lock, sort_keys=True, indent=2) + "\n").encode("utf-8")
        temp = root / ".system-deb-lock.json.tmp"
        with temp.open("xb") as stream:
            stream.write(lock_bytes)
        os.chmod(temp, 0o644)
        os.replace(str(temp), str(out))
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print(json.dumps({"status": "LOCKED", "deb_count": len(packages),
                      "apt_index_count": len(indexes), "lock_sha256": sha(out)}, sort_keys=True))

if __name__ == "__main__":
    main()
