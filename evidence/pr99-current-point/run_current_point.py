#!/usr/bin/python3.11
"""Owner-root coordinator; prepare/copy/verify only after an exact independent permit."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys
import time
import urllib.request

REPO = "huhongchuan0422-creator/Repository-name-xuanjun-ai-control"
ACTION = "PR99_CURRENT_OFFLINE_RECOVERY_POINT_V1"
HOST = "iZmj7a5kwr75qc1tul4kf9Z"
SOURCE_HOST = "iZ6wee8q9z4t03hvqumwfhZ"
STAGE = "/root/pr99-current-point-v1"
LOCAL = Path("/root/pr99-current-point-received-v1")
PINNED_HOSTKEY = "47.245.53.152 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBMfngQ3DTnuC8aP0TZ0fBhcq+8p7Yw0c7VEYKWSpFrtpqWf+shoFTiyrAWj1OlrnoeOlsZq1SS1zOavODbJOnzs=\n"

def need(ok, why):
    if not ok:
        raise RuntimeError(why)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def verify_approval(record, args, now):
    need(record["id"] == args.approval_id
         and record["issue_url"] == "https://api.github.com/repos/"+REPO+"/issues/99",
         "APPROVAL_ID_OR_PR")
    u = record["user"]
    need(u["id"] == 332398908 and u["login"] == "huhongchuan0422-creator"
         and u["type"] == "User" and args.confirm_independent_auditor,
         "INDEPENDENT_AUTHOR_AND_OWNER_ROOT_CONFIRMATION_REQUIRED")
    body = record["body"]
    need(digest(body.encode()) == args.approval_sha256, "APPROVAL_BODY_CHANGED")
    start = "<!-- PR99_CURRENT_POINT_APPROVAL_V1\n"
    end = "\nPR99_CURRENT_POINT_APPROVAL_V1 -->"
    need(body.count(start) == body.count(end) == 1, "APPROVAL_MARKER")
    value = json.loads(body.split(start)[1].split(end)[0])
    need(value["decision"] == "APPROVED_WITH_EXACT_PRECONDITIONS"
         and value["action"] == ACTION and type(value["max_attempts"]) is int
         and value["max_attempts"] == 1, "APPROVAL_ACTION")
    need(value["source_commit"] == args.source_commit
         and re.fullmatch(r"[0-9a-f]{40}", args.source_commit)
         and value["binding_sha256"] == args.binding_sha256
         and value["source_host"] == SOURCE_HOST and value["target_host"] == HOST,
         "APPROVAL_EXACT_BINDING")
    need(type(value["issued_at"]) in (int, float) and type(value["expires_at"]) in (int, float)
         and value["issued_at"] <= now < value["expires_at"]
         and 0 < value["expires_at"]-value["issued_at"] <= 43200, "APPROVAL_TIME")
    return value

def get_approval(args):
    url = "https://api.github.com/repos/"+REPO+"/issues/comments/"+str(args.approval_id)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=20) as r:
        data = r.read(200001)
    need(len(data) <= 200000, "APPROVAL_SIZE")
    record = json.loads(data)
    return record, verify_approval(record, args, time.time())

def load_bundle(folder, expected):
    raw = (folder/"BINDING.json").read_bytes()
    need(digest(raw) == expected, "BINDING_BYTES")
    binding = json.loads(raw)
    need(binding["action"] == ACTION and set(binding["files"]) == {
        "current_point.py", "run_current_point.py", "source-identities.json",
        "test_current_point.py", "README.md"}, "BINDING_SET")
    contents = {}
    for name, sha in binding["files"].items():
        p = folder/name
        s = p.lstat()
        need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1
             and not s.st_mode & 0o022, "BUNDLE_FILE_IDENTITY")
        data = p.read_bytes()
        need(digest(data) == sha, "BUNDLE_FILE_HASH")
        contents[name] = data
    return contents

def bootstrap(contents, approval_id, expires):
    # Transport only approved source, source identities and public authorization metadata.
    payload = {name: contents[name].decode() for name in ("current_point.py", "source-identities.json")}
    return ("import os,json,stat,hashlib,signal,sys,time\n"
            "from pathlib import Path\n"
            "assert os.geteuid()==0 and os.uname().nodename=="+repr(SOURCE_HOST)+"\n"
            "assert time.time()<"+repr(expires)+"\n"
            "os.umask(0o077)\n"
            "payload=json.loads("+repr(json.dumps(payload))+")\n"
            "expected="+repr({n: digest(contents[n]) for n in payload})+"\n"
            "for n,v in payload.items(): assert hashlib.sha256(v.encode()).hexdigest()==expected[n]\n"
            "root=Path('/root'); s=root.lstat()\n"
            "assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022\n"
            "w=Path("+repr(STAGE)+"); w.mkdir(mode=0o700)\n"
            "for n,v in payload.items():\n"
            " with (w/n).open('xb') as f:\n"
            "  os.fchmod(f.fileno(),0o600); f.write(v.encode()); f.flush(); os.fsync(f.fileno())\n"
            "with (w/'approval-id.txt').open('x') as f: f.write("+repr(str(approval_id))+ ")\n"
            "namespace={'__name__':'pr99_collector'}\n"
            "exec(compile(payload['current_point.py'],str(w/'current_point.py'),'exec'),namespace)\n"
            "def timed_out(*_): raise namespace['Hold']('TOTAL_PREPARE_DEADLINE')\n"
            "signal.signal(signal.SIGALRM,timed_out); signal.signal(signal.SIGTERM,timed_out); signal.alarm(300)\n"
            "namespace['prepare'](w,json.loads(payload['source-identities.json']))\n").encode()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-id", type=int, required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--binding-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--confirm-independent-auditor", action="store_true")
    args = parser.parse_args()
    need(os.geteuid() == 0 and os.uname().nodename == HOST, "KOREA_ROOT_REQUIRED")
    os.umask(0o077)
    folder = Path(__file__).resolve().parent
    for p in [folder]+list(folder.parents):
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             "BUNDLE_PARENT_IDENTITY")
    contents = load_bundle(folder, args.binding_sha256)
    need(Path(__file__).read_bytes() == contents["run_current_point.py"], "RUNNER_BYTES")
    record, approval = get_approval(args)  # No execution claims/staging before permission.
    module = importlib.util.spec_from_file_location("pr99_point", folder/"current_point.py")
    cp = importlib.util.module_from_spec(module)
    module.loader.exec_module(cp)
    manifest = json.loads(contents["source-identities.json"])
    cp.manifest_rows(manifest)
    need(approval["source_manifest_sha256"] == manifest["source_aggregate_sha256"],
         "APPROVAL_SOURCE_MANIFEST")
    import shutil
    need(shutil.disk_usage("/root").free >= 1536*1024*1024, "KOREA_FREE_DISK")
    LOCAL.mkdir(mode=0o700)  # Exclusive attempt/consumption; never auto-resume or cleanup.
    cp.json_new(LOCAL/"approval.json", {"record": record, "verified": approval,
                 "body_sha256": args.approval_sha256, "source_commit": args.source_commit})
    cp.write_new(LOCAL/"known_hosts", PINNED_HOSTKEY.encode())
    common = ["/usr/bin/ssh", "-T", "-S", str(LOCAL/"ssh.sock"),
              "-o", "ControlMaster=auto", "-o", "ControlPersist=60",
              "-o", "UserKnownHostsFile="+str(LOCAL/"known_hosts"),
              "-o", "GlobalKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=yes",
              "-o", "HostKeyAlgorithms=ecdsa-sha2-nistp256", "-o", "UpdateHostKeys=no",
              "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
              "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no",
              "-o", "ForwardX11=no"]
    target = "root@47.245.53.152"
    def ssh(command, output, data=None, timeout=120):
        r = subprocess.run(common+["-o", "BatchMode=yes", target, command], input=data,
                           stdout=output, stderr=subprocess.PIPE, timeout=timeout)
        need(r.returncode == 0, "SSH_STEP_FAILED")
    def fetch(name, limit):
        need(name in {"receipt.json", "payload.enc", "payload.key"}, "FETCH_NAME")
        # The private source file is opened no-follow, fstat and stable identity checked.
        code = ("import os,stat,sys; p="+repr(STAGE+"/"+name)+"; "
                "fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW); s=os.fstat(fd); "
                "assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 "
                "and stat.S_IMODE(s.st_mode)==0o600 and s.st_size<="+str(limit)+"; "
                "f=os.fdopen(fd,'rb'); "
                "import shutil; shutil.copyfileobj(f,sys.stdout.buffer); "
                "a=os.fstat(f.fileno()); assert (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)=="
                "(a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)")
        with (LOCAL/name).open("xb") as out:
            os.fchmod(out.fileno(), 0o600)
            ssh("/usr/bin/python3.11 -I -B -c "+shlex.quote(code), out, timeout=1800)
            out.flush()
            os.fsync(out.fileno())
        need((LOCAL/name).stat().st_size <= limit, "FETCH_SIZE")
    try:
        print("请输入东京root密码；仅建立已固定主机身份的现有SSH连接。", flush=True)
        subprocess.run(common+["-n", "-o", "BatchMode=no", "-o", "NumberOfPasswordPrompts=1",
                        target, 'test "$(hostname -s)" = '+SOURCE_HOST+' && test "$(id -u)" = 0'],
                       check=True, timeout=120)
        get_approval(args)  # Reject revocation/body edit/expiry before remote effects.
        print("授权核验通过：制作当前源码和SQLite离线恢复点。", flush=True)
        with (LOCAL/"prepare-private.log").open("xb") as log:
            ssh("/usr/bin/python3.11 -I -B -u -", log,
                bootstrap(contents, args.approval_id, approval["expires_at"]), timeout=330)
        fetch("receipt.json", 20000)
        expected = json.loads((LOCAL/"receipt.json").read_text())
        need(expected["status"] == "CURRENT_OFFLINE_POINT_PREPARED"
             and expected["action"] == ACTION and expected["host"] == SOURCE_HOST
             and expected["source_aggregate_sha256"] == manifest["source_aggregate_sha256"],
             "SOURCE_RECEIPT")
        need(0 < expected["cipher_bytes"] <= cp.MAX_TOTAL*2, "CIPHER_SIZE")
        print("当前恢复点已生成；复制密文和私有恢复密钥。", flush=True)
        fetch("payload.enc", expected["cipher_bytes"])
        need((LOCAL/"payload.enc").stat().st_size == expected["cipher_bytes"]
             and cp.hashfile(LOCAL/"payload.enc") == expected["cipher_sha256"], "CIPHER_HASH")
        fetch("payload.key", 65)
        need(re.fullmatch(b"[0-9a-f]{64}\n", (LOCAL/"payload.key").read_bytes()), "KEY_FORMAT")
        cp.write_new(LOCAL/"payload.tar.gz", b"")
        with (LOCAL/"decrypt-private.log").open("xb") as log, (LOCAL/"payload.tar.gz").open("wb") as plain:
            result = subprocess.run(["/usr/bin/openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                       "-iter", "200000", "-md", "sha256", "-in", str(LOCAL/"payload.enc"),
                       "-pass", "file:"+str(LOCAL/"payload.key")],
                       stdout=plain, stderr=log, timeout=120)
            plain.flush(); os.fsync(plain.fileno())
        need(result.returncode == 0, "DECRYPT_FAILED")
        result = cp.receive_archive(LOCAL/"payload.tar.gz", LOCAL/"verified", expected, manifest)
        result.update({"approval_comment_id": args.approval_id,
                       "cipher_sha256": expected["cipher_sha256"], "retry_allowed": False,
                       "source_commit": args.source_commit, "host": HOST})
        cp.json_new(LOCAL/"final-receipt.json", result)
        cp.fsync_dir(LOCAL)
        print(json.dumps(result, sort_keys=True), flush=True)
    except BaseException as error:
        failure = {"status": "HOLD_PRESERVE_EVIDENCE", "reason": type(error).__name__,
                   "retry_allowed": False, "remote_state": "INSPECT_BEFORE_ANY_NEW_AUTHORITY",
                   "workdir": str(LOCAL)}
        cp.json_new(LOCAL/"failure.json", failure)
        print(json.dumps(failure, sort_keys=True), flush=True)
        raise
    finally:
        subprocess.run(common+["-o", "BatchMode=yes", "-O", "exit", target],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

if __name__ == "__main__":
    main()
