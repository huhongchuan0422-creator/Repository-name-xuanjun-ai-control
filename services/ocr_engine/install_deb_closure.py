"""Install exactly the frozen Debian closure in an offline disposable container."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HEX = re.compile(r"^[0-9a-f]{64}$")

def run(argv):
    try:
        return subprocess.run(argv, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        # Preserve the first failing command and its actual stderr; never retry via APT.
        print("DEB_COMMAND_FAILED:" + repr(argv), file=sys.stderr)
        print("DEB_COMMAND_EXIT:" + str(exc.returncode), file=sys.stderr)
        if exc.stdout:
            print("DEB_COMMAND_STDOUT:" + exc.stdout, file=sys.stderr)
        if exc.stderr:
            print("DEB_COMMAND_STDERR:" + exc.stderr, file=sys.stderr)
        raise SystemExit("OFFLINE_DEB_INSTALL_HOLD") from exc

def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/debs")
    if root.is_symlink() or not root.is_dir():
        raise SystemExit("DEB_CACHE_INVALID")
    lock_path = root / "system-deb-lock.json"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise SystemExit("DEB_LOCK_NOT_REGULAR_FILE")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("DEB_LOCK_UNREADABLE_OR_INVALID:" + str(exc))
    entries = lock.get("packages") if isinstance(lock, dict) else None
    if not isinstance(entries, list) or not entries:
        raise SystemExit("DEB_LOCK_EMPTY")
    by_name, filenames = {}, set()
    for item in entries:
        if not isinstance(item, dict) or not all(k in item for k in
                ("package", "version", "architecture", "filename", "sha256")):
            raise SystemExit("DEB_LOCK_ENTRY_INVALID")
        name, version, arch, filename, digest = (item[k] for k in
                ("package", "version", "architecture", "filename", "sha256"))
        if not all(isinstance(v, str) and v and "\\n" not in v for v in (name, version, arch)):
            raise SystemExit("DEB_LOCK_METADATA_INVALID")
        if name in by_name:
            raise SystemExit("DEB_PACKAGE_DUPLICATE:" + name)
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".deb") or filename in filenames:
            raise SystemExit("DEB_FILENAME_INVALID")
        if not isinstance(digest, str) or not HEX.fullmatch(digest):
            raise SystemExit("DEB_LOCK_SHA_INVALID:" + filename)
        filenames.add(filename)
        path = root / filename
        if path.is_symlink() or not path.is_file():
            raise SystemExit("DEB_NOT_REGULAR_FILE:" + filename)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit("DEB_LOCK_SHA_MISMATCH:" + filename)
        actual = [run(["dpkg-deb", "-f", str(path), field]).stdout.strip()
                  for field in ("Package", "Version", "Architecture")]
        if actual != [name, version, arch]:
            raise SystemExit("DEB_LOCK_METADATA_MISMATCH:" + filename)
        by_name[name] = item
    actual_files = {p.name for p in root.glob("*.deb") if p.is_file() and not p.is_symlink()}
    if actual_files != filenames:
        raise SystemExit("DEB_FILE_SET_DIFFERS_FROM_LOCK")
    run(["dpkg", "--unpack"] + [str(root / by_name[name]["filename"]) for name in sorted(by_name)])
    run(["dpkg", "--configure", "-a"])
    audit = run(["dpkg", "--audit"])
    if audit.stdout.strip() or audit.stderr.strip():
        raise SystemExit("DPKG_AUDIT_NOT_CLEAN:" + audit.stdout + audit.stderr)
    for name in sorted(by_name):
        item = by_name[name]
        output = run(["dpkg-query", "-W", "-f=" + name + "=" + "${Version}" + chr(10), name]).stdout
        if output.strip() != name + "=" + item["version"]:
            raise SystemExit("INSTALLED_DEB_VERSION_MISMATCH:" + name + ":" + output)
    print(json.dumps({"status": "OFFLINE_DEB_CLOSURE_INSTALLED", "package_count": len(by_name),
                      "packages": [{"name": n, "version": by_name[n]["version"]} for n in sorted(by_name)]},
                     sort_keys=True))

if __name__ == "__main__":
    main()
