"""Copy only explicit immutable candidate inputs to a runner-readable directory and inventory exact upload payload."""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

MODEL_NAMES={"PP-OCRv6_det_small.onnx","PP-OCRv6_rec_small.onnx","ch_ppocr_mobile_v2.0_cls_mobile.onnx"}

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def regular_readable(path):
    return path.is_file() and not path.is_symlink() and os.access(path,os.R_OK)

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else os.environ["RUNNER_TEMP"])
    dest=Path(sys.argv[2] if len(sys.argv)>2 else root/"ocr-candidate-inputs"/"payload")
    dest.mkdir(parents=True,exist_ok=True)
    source_manifest=Path(__file__).with_name("model_manifest.json")
    trusted={}
    try:
        data=json.loads(source_manifest.read_text(encoding="utf-8"))
        trusted={item["filename"]:item["sha256"] for item in data["model_set"]["files"].values()}
    except (OSError,ValueError,KeyError,TypeError):
        trusted={}
    candidates=[]
    def add(path,rel,provenance):
        if regular_readable(path):
            candidates.append((path,rel,provenance))
    wheel=root/"ocr-wheelhouse"
    if wheel.is_dir():
        for p in sorted(wheel.iterdir()):
            if p.suffix==".whl": add(p,"wheelhouse/"+p.name,"downloaded-from-pypi; locally hashed; not independently pinned")
    models=root/"ocr-model-cache"
    if models.is_dir():
        for p in sorted(models.iterdir()):
            if p.name in MODEL_NAMES:
                provenance="fixed-model-manifest-sha256" if trusted.get(p.name)==sha(p) else "downloaded-and-self-hashed-only; fixed manifest SHA mismatch or unavailable"
                add(p,"models/"+p.name,provenance)
    debroot=root/"ocr-deb-cache"
    if debroot.is_dir():
        for p in sorted(debroot.iterdir()):
            if p.suffix==".deb": add(p,"system-debs/"+p.name,"APT-resolved; local SHA only until lock/source verified")
        lock=debroot/"system-deb-lock.json"
        if regular_readable(lock):
            try:
                lockdata=json.loads(lock.read_text(encoding="utf-8"))
                for item in lockdata.get("packages",[]):
                    p=debroot/item["filename"]
                    if regular_readable(p) and sha(p)==item.get("sha256"):
                        add(p,"system-debs/"+p.name,"SHA matches generated Debian lock; verify official source/index provenance before reuse")
                for item in lockdata.get("apt_lists",[]):
                    rel=Path(item["path"])
                    if rel.is_absolute() or ".." in rel.parts or any(part in ("partial","auxfiles") for part in rel.parts) or rel.name in ("lock","partial"):
                        continue
                    p=debroot/"apt-lists"/rel
                    if regular_readable(p) and p.stat().st_size==item.get("bytes") and sha(p)==item.get("sha256"):
                        add(p,"apt-lists/"+str(rel),"SHA matches generated apt index lock; signature provenance not independently asserted")
                add(lock,"system-deb-lock.json","generated lock; only its exact listed package/index hashes are asserted")
            except (OSError,ValueError,KeyError,TypeError):
                pass
    build=root/"ocr-build"
    if build.is_dir():
        for rel in ("requirements-lock-linux-x86_64-cp311.json","SHA256SUMS","xuanjun-ocr-linux-x86_64-cp311.tar.gz"):
            p=build/rel
            add(p,"build-output/"+rel,"partial-or-generated output; NOT_RELEASE unless separate success-only release artifact exists")
        pins=build/"source-pins"
        if pins.is_dir():
            for p in sorted(pins.iterdir()):
                if p.is_file() and not p.is_symlink():
                    add(p,"source-pins/"+p.name,"copied from exact checked-out repository source")
    # Deduplicate destination paths and copy only files that the runner can actually read.
    seen=set(); entries=[]
    for src,rel,provenance in candidates:
        if rel in seen: continue
        seen.add(rel)
        target=dest/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,target)
        os.chmod(target,0o644)
        entries.append({"path":rel,"bytes":target.stat().st_size,"sha256":sha(target),"provenance":provenance})
    result={"classification":"CANDIDATE_INPUTS_ONLY_NOT_A_RELEASE_PACKAGE","files_scope":"exact copied payload under candidate payload directory; manifest is a separate index record and is not self-hashed","source_sha":os.environ.get("GITHUB_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"files":entries}
    manifest=root/"ocr-candidate-inputs"/"candidate-input-manifest.json"
    manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"classification":result["classification"],"candidate_file_count":len(entries),"manifest_sha256":sha(manifest),"payload_dir":str(dest)},sort_keys=True))

if __name__=="__main__": main()
