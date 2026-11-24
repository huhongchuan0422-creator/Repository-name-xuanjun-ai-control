"""Stage exact FunASR publisher assets. Only run during installation, not inference."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote
from urllib.request import urlopen

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("destination",type=Path)
    p.add_argument("--lock",type=Path,default=Path(__file__).with_name("model-lock.json"))
    args=p.parse_args()
    lock=json.loads(args.lock.read_text())
    dest=args.destination.resolve()
    for role, data in lock.items():
        if role not in ("streaming","offline","vad") or not re.fullmatch(r"funasr/[a-z0-9-]+",data["repository"]) or not re.fullmatch(r"[0-9a-f]{40}",data["revision"]):
            raise ValueError("Model lock does not name the exact publisher revision")
        folder=(dest/role).resolve()
        if not folder.is_relative_to(dest):
            raise ValueError("Model path must remain inside destination")
        folder.mkdir(parents=True,exist_ok=True)
        for name, sha in data["files"].items():
            if name != PurePosixPath(name).name or name in (".","..") or not re.fullmatch("[0-9a-f]{64}",sha):
                raise ValueError("Invalid staged filename or SHA-256")
            file=folder/name
            if file.is_symlink() or (folder/(name+".partial")).is_symlink():
                raise ValueError("Refusing linked checkpoint asset")
            if file.exists():
                with file.open("rb") as handle:
                    if hashlib.file_digest(handle,"sha256").hexdigest() == sha:
                        print(f"{role}/{name}: already verified",flush=True)
                        continue
                raise ValueError("Contents differ from lock; preserve and use a new staging directory")
            partial=file.with_name(name+".partial")
            digest=hashlib.sha256()
            url=f"https://huggingface.co/{data['repository']}/resolve/{data['revision']}/{quote(name)}"
            try:
                with urlopen(url,timeout=90) as response, partial.open("wb") as out:
                    while block:=response.read(1024*1024):
                        digest.update(block)
                        out.write(block)
                if digest.hexdigest()!=sha:
                    raise ValueError(f"{role}/{name} SHA-256 mismatch")
                partial.replace(file)
                print(f"{role}/{name}: verified",flush=True)
            finally:
                if partial.exists():
                    partial.unlink()

if __name__=="__main__":
    main()
