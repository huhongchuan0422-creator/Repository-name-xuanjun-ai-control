"""Create a SHA-locked Debian runtime closure manifest from already downloaded .deb files."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = "python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199"

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else "/debs")
    source=Path(sys.argv[2] if len(sys.argv)>2 else "/etc/apt/sources.list.d/debian.sources")
    apt_root=Path(sys.argv[3] if len(sys.argv)>3 else "/var/lib/apt/lists")
    out=root/"system-deb-lock.json"
    if not root.is_dir() or root.is_symlink(): raise SystemExit("DEB_CACHE_INVALID")
    if not source.is_file() or source.is_symlink(): raise SystemExit("OFFICIAL_APT_SOURCE_FILE_MISSING")
    packages=[]
    for path in sorted(root.glob("*.deb")):
        fields=[]
        for field in ("Package","Version","Architecture"):
            value=subprocess.check_output(["dpkg-deb","-f",str(path),field],text=True).strip()
            if not value or "\n" in value: raise SystemExit("DEB_METADATA_INVALID:"+path.name)
            fields.append(value)
        packages.append({"filename":path.name,"package":fields[0],"version":fields[1],"architecture":fields[2],"sha256":sha(path)})
    if not packages: raise SystemExit("DEB_CLOSURE_EMPTY")
    indexes=[]
    for path in sorted(apt_root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            indexes.append({"path":str(path.relative_to(apt_root)),"bytes":path.stat().st_size,"sha256":sha(path)})
    if not indexes: raise SystemExit("APT_INDEX_CACHE_EMPTY")
    source_bytes=source.read_bytes()
    source_text=source_bytes.decode("utf-8")
    uris=[line.split(":",1)[1].strip().split() for line in source_text.splitlines() if line.strip().startswith("URIs:")]
    if not uris or any(not uri.startswith(("https://deb.debian.org/","http://deb.debian.org/","https://security.debian.org/","http://security.debian.org/")) for group in uris for uri in group):
        raise SystemExit("APT_SOURCE_NOT_OFFICIAL_DEBIAN")
    lock={"base_image":BASE,"apt_source":{"path":source.name,"sha256":hashlib.sha256(source_bytes).hexdigest(),"content":source_text},"packages":packages,"apt_lists":indexes}
    out.write_text(json.dumps(lock,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"LOCKED","deb_count":len(packages),"apt_index_count":len(indexes),"lock_sha256":sha(out)},sort_keys=True))

if __name__=="__main__": main()
