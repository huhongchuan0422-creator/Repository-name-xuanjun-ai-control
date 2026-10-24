"""Install only the frozen, hash-verified Debian closure inside the disposable offline container."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

def run(argv):
    return subprocess.run(argv,check=True,text=True,capture_output=True)

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else "/debs")
    lock_path=root/"system-deb-lock.json"
    lock=json.loads(lock_path.read_text(encoding="utf-8"))
    entries=lock.get("packages")
    if not isinstance(entries,list) or not entries: raise SystemExit("DEB_LOCK_EMPTY")
    by_name={}
    filenames=set()
    for item in entries:
        if not isinstance(item,dict) or not all(k in item for k in ("package","version","architecture","filename","sha256")):
            raise SystemExit("DEB_LOCK_ENTRY_INVALID")
        name=item["package"]
        if name in by_name: raise SystemExit("DEB_PACKAGE_DUPLICATE:"+name)
        filename=item["filename"]
        if Path(filename).name!=filename or not filename.endswith(".deb") or filename in filenames:
            raise SystemExit("DEB_FILENAME_INVALID")
        filenames.add(filename)
        path=root/filename
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            raise SystemExit("DEB_LOCK_SHA_MISMATCH:"+filename)
        actual=[]
        for field in ("Package","Version","Architecture"):
            actual.append(run(["dpkg-deb","-f",str(path),field]).stdout.strip())
        if actual != [name,item["version"],item["architecture"]]:
            raise SystemExit("DEB_LOCK_METADATA_MISMATCH:"+filename)
        by_name[name]=item
    actual_files={p.name for p in root.glob("*.deb") if p.is_file() and not p.is_symlink()}
    if actual_files!=filenames: raise SystemExit("DEB_FILE_SET_DIFFERS_FROM_LOCK")
    # No apt, no network fallback: unpack the exact set, configure, audit, then verify versions.
    run(["dpkg","--unpack"]+[str(root/by_name[name]["filename"]) for name in sorted(by_name)])
    run(["dpkg","--configure","-a"])
    audit=run(["dpkg","--audit"])
    if audit.stdout.strip() or audit.stderr.strip(): raise SystemExit("DPKG_AUDIT_NOT_CLEAN:"+audit.stdout+audit.stderr)
    for name in sorted(by_name):
        item=by_name[name]
        output=run(["dpkg-query","-W","-f="+name+"="+ "${Version}" + chr(10),name]).stdout
        if output.strip()!=name+"="+item["version"]:
            raise SystemExit("INSTALLED_DEB_VERSION_MISMATCH:"+name+":"+output)
    print(json.dumps({"status":"OFFLINE_DEB_CLOSURE_INSTALLED","package_count":len(by_name),"packages":[{"name":n,"version":by_name[n]["version"]} for n in sorted(by_name)]},sort_keys=True))

if __name__=="__main__": main()
