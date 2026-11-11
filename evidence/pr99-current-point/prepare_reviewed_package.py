#!/usr/bin/python3.11
"""Stage the frozen review package only; NEVER invoke its migration coordinator."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import urllib.request

REPO = "huhongchuan0422-creator/Repository-name-xuanjun-ai-control"
URL = "https://raw.githubusercontent.com/"+REPO+"/9fbd573852eea301268575c750cda1f2f904321d/evidence/pr99-current-point/PR99_CURRENT_POINT_REVIEW.tar.gz"
ARCHIVE_SHA = "41f3c224cbed1d864104bc206d92a32339372a9d0ecfa9108a2da0123803db70"
BINDING_SHA = "1785c311ab9eb0b5e88c43dbb2bb3da8dce3a519635d6ca7b0e2ad9a68161fa1"
STAGE = Path("/root/pr99-current-point-package-c6ba6ac8")
NAMES = {"BINDING.json", "README.md", "current_point.py", "run_current_point.py",
         "source-identities.json", "test_current_point.py"}

def need(ok, why):
    if not ok:
        raise SystemExit("HOLD_PREPARATION_ONLY:"+why)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def unpack_verified(raw):
    need(len(raw) == 60130 and sha(raw) == ARCHIVE_SHA, "FROZEN_ARCHIVE_HASH")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
        for m in t:
            need(m.name in NAMES and m.name not in files and m.isfile()
                 and 0 <= m.size <= 1024*1024, "EXACT_REGULAR_MEMBER_SET")
            f = t.extractfile(m)
            need(f is not None, "MEMBER_STREAM")
            with f:
                files[m.name] = f.read(m.size+1)
            need(len(files[m.name]) == m.size, "MEMBER_TRUNCATED")
    need(set(files) == NAMES and sha(files["BINDING.json"]) == BINDING_SHA,
         "BINDING_BYTES")
    binding = json.loads(files["BINDING.json"])
    need(set(binding["files"]) == NAMES-{"BINDING.json"}, "BOUND_FILE_SET")
    for name, digest in binding["files"].items():
        need(sha(files[name]) == digest, "BOUND_FILE_HASH")
    return files

def stage_verified(files, folder):
    if os.path.lexists(folder):
        s = folder.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0
             and stat.S_IMODE(s.st_mode) == 0o700, "STAGE_IDENTITY")
        need({p.name for p in folder.iterdir()} == NAMES, "EXISTING_STAGE_FILE_SET")
        for name, data in files.items():
            p = folder/name
            s = p.lstat()
            need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1
                 and stat.S_IMODE(s.st_mode) == 0o400 and p.read_bytes() == data,
                 "EXISTING_STAGE_CHANGED")
        return "EXISTING_EXACT_PACKAGE_VERIFIED_NO_REEXECUTION"
    folder.mkdir(mode=0o700)
    for name, data in files.items():
        fd = os.open(folder/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o400)
            f.write(data); f.flush(); os.fsync(f.fileno())
    fd = os.open(folder, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return "FROZEN_PACKAGE_STAGED_ONLY"

def main():
    need(os.geteuid() == 0 and os.uname().nodename == "iZmj7a5kwr75qc1tul4kf9Z",
         "KOREA_ROOT_REQUIRED")
    os.umask(0o077)
    for p in (Path("/"), Path("/root")):
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode&0o022,
             "TRUSTED_PARENT")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL, timeout=45) as r:
        raw = r.read(60131)
    result = stage_verified(unpack_verified(raw), STAGE)
    print(json.dumps({"status":result,"directory":str(STAGE),"bound_files":5,
                     "archive_sha256":ARCHIVE_SHA,"migration_started":False,
                     "database_opened":False,"approval_consumed":False,"service_actions":0},
                     sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
