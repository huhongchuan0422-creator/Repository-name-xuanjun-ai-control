"""Build a deterministic review archive, never an execution authorization."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


def build(folder, output, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("EXACT_COMMIT_REQUIRED")
    names = ("controlled_repair.py", "finalize_repair.py", "offline.service", "installed-runtime-manifest.json",
             "approved-runtime-632bbe6f.tar.gz", "README.md", "build_review.py")
    files = {name: (folder / name).read_bytes() for name in names}
    tests = folder / "test_korea_offline_repair.py"
    if not tests.is_file():
        tests = folder.parent / "test_korea_offline_repair.py"
    files["test_korea_offline_repair.py"] = tests.read_bytes()
    tests2 = folder / "test_korea_offline_finalize.py"
    if not tests2.is_file():
        tests2 = folder.parent / "test_korea_offline_finalize.py"
    files["test_korea_offline_finalize.py"] = tests2.read_bytes()
    binding = {"schema_version": 1, "source_commit": commit,
               "production_authorized": False,
               "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["REPAIR_BINDING.json"] = (json.dumps(binding, indent=2, sort_keys=True) + "\n").encode()
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0, filename="") as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, data in sorted(files.items()):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o600
                archive.addfile(member, io.BytesIO(data))
    with output.open("xb") as f:
        f.write(stream.getvalue())
    return {"source_commit": commit, "tar_sha256": hashlib.sha256(stream.getvalue()).hexdigest(),
            "bound_files": len(binding["files"]), "archive_members": len(files),
            "production_authorized": False, "server_commands_executed": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--commit", required=True)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(build(Path(__file__).parent, a.output, a.commit), sort_keys=True))
