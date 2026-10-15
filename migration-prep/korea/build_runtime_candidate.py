"""Build an exact self-contained runtime-candidate directory from this commit."""
from __future__ import print_function

import argparse
import json
import os
import shutil
from pathlib import Path

from korea.build_minimal_runtime_manifest import ROOT, build


def build_candidate(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise RuntimeError("RUNTIME_CANDIDATE_OUTPUT_MUST_NOT_EXIST")
    output.mkdir(mode=0o700, parents=False)
    manifest = build()
    for record in manifest["files"]:
        source = ROOT / record["path"]
        target = output / record["path"]
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(target))
        os.chmod(str(target), 0o755 if target.suffix == ".sh" else 0o644)
    manifest_path = output / "minimal-runtime-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    os.chmod(str(manifest_path), 0o600)
    return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args(argv)
    print(build_candidate(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
