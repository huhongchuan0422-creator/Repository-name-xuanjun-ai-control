"""Write an inventory for exactly the candidate artifact upload set, never label it a release."""
import hashlib
import json
import os
import sys
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else os.environ["RUNNER_TEMP"])
    manifest_path=Path(sys.argv[2] if len(sys.argv)>2 else root/"ocr-candidate-inputs"/"candidate-input-manifest.json")
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    include=[]
    for rel in ("ocr-wheelhouse","ocr-model-cache","ocr-deb-cache","ocr-build"):
        base=root/rel
        if not base.exists(): continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.is_symlink() and path != manifest_path:
                include.append(path)
    entries=[]
    for path in include:
        rel=str(path.relative_to(root))
        if rel.startswith("ocr-model-cache/"):
            source="fixed-model-manifest-sha256" if path.name in ("PP-OCRv6_det_small.onnx","PP-OCRv6_rec_small.onnx","ch_ppocr_mobile_v2.0_cls_mobile.onnx") else "downloaded-and-self-hashed-unverified"
        elif rel.startswith("ocr-wheelhouse/"):
            source="downloaded-from-pypi-and-self-hashed-not-independently-pinned"
        elif rel.startswith("ocr-deb-cache/apt-lists/"):
            source="downloaded-from-configured-debian-source-and-self-hashed"
        elif rel.startswith("ocr-deb-cache/") and path.name.endswith(".deb"):
            source="apt-resolved-package-and-self-hashed; verify lock/source fingerprint before reuse"
        elif path.name=="requirements-lock-linux-x86_64-cp311.json":
            source="generated-from-current-run-runtime-and-self-hashed"
        elif path.name.endswith(".tar.gz") or path.name=="SHA256SUMS":
            source="partial-or-final-build-output; not release unless success-only artifact also exists"
        else:
            source="generated-candidate-file-self-hashed"
        entries.append({"path":rel,"bytes":path.stat().st_size,"sha256":sha(path),"provenance":source})
    result={"classification":"CANDIDATE_INPUTS_ONLY_NOT_A_RELEASE_PACKAGE","source_sha":os.environ.get("GITHUB_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"files":entries}
    manifest_path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"classification":result["classification"],"candidate_file_count":len(entries),"manifest_sha256":sha(manifest_path)},sort_keys=True))

if __name__=="__main__": main()
