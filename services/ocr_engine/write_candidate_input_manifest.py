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
    trusted_model_hashes={}
    model_manifest=Path(__file__).with_name("model_manifest.json")
    if model_manifest.is_file():
        try:
            data=json.loads(model_manifest.read_text(encoding="utf-8"))
            trusted_model_hashes={item["filename"]:item["sha256"] for item in data["model_set"]["files"].values()}
        except (ValueError,KeyError,TypeError):
            trusted_model_hashes={}
    entries=[]
    for path in include:
        rel=str(path.relative_to(root))
        digest=sha(path)
        if rel.startswith("ocr-build/source-pins/"):
            source="repository-pinned-source-input-copied-after-exact-source-checkout"
        elif rel.startswith("ocr-model-cache/"):
            if path.name in trusted_model_hashes and digest == trusted_model_hashes[path.name]:
                source="sha256-matches-fixed-model-manifest"
            else:
                source="downloaded-and-self-hashed-only-not-trusted-by-model-manifest"
        elif rel.startswith("ocr-wheelhouse/"):
            source="downloaded-from-pypi-and-self-hashed-not-independently-pinned"
        elif rel.startswith("ocr-deb-cache/apt-lists/"):
            source="downloaded-from-configured-debian-source-and-self-hashed"
        elif rel.startswith("ocr-deb-cache/apt-lists/") and ("InRelease" in path.name or "Release" in path.name):
            source="apt-index-signature-checked-by-apt-get-update-and-self-hashed"
        elif rel.startswith("ocr-deb-cache/") and path.name == "system-deb-lock.json":
            source="generated-lock; package and apt-index digests recorded; validate lock/source fingerprint before reuse"
        elif rel.startswith("ocr-deb-cache/") and path.name.endswith(".deb"):
            source="apt-resolved-package-and-self-hashed; validate package SHA and signed-index provenance before reuse"

        elif path.name=="requirements-lock-linux-x86_64-cp311.json":
            source="generated-from-current-run-runtime-and-self-hashed"
        elif path.name.endswith(".tar.gz") or path.name=="SHA256SUMS":
            source="partial-or-final-build-output; not release unless success-only artifact also exists"
        else:
            source="generated-candidate-file-self-hashed"
        entries.append({"path":rel,"bytes":path.stat().st_size,"sha256":digest,"provenance":source})
    result={"classification":"CANDIDATE_INPUTS_ONLY_NOT_A_RELEASE_PACKAGE","files_scope":"exact payload files under ocr-wheelhouse/, ocr-model-cache/, ocr-deb-cache/, and ocr-build/; this manifest is the separate index record and does not self-hash","source_sha":os.environ.get("GITHUB_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"files":entries}
    manifest_path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"classification":result["classification"],"candidate_file_count":len(entries),"manifest_sha256":sha(manifest_path)},sort_keys=True))

if __name__=="__main__": main()
