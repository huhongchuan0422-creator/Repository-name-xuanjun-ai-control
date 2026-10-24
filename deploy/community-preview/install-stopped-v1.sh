#!/bin/sh
# SOURCE REVIEW ONLY. Fixed STOPPED_HANDOFF_V1 carrier installer; never starts B/C.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'usage: install-stopped-v1.sh ABS_CONTROL_ZIP ABS_MANIFEST_JSON' >&2
  exit 64
fi
case "$1:$2" in
  /*:/*) ;;
  *) echo 'absolute input paths required' >&2; exit 64 ;;
esac
umask 077
receipt_file="$(mktemp /tmp/xuanjun-v2-install-receipt.XXXXXX)"
trap 'rm -f "$receipt_file"' EXIT HUP INT TERM
set +e
/usr/bin/sudo -n /usr/bin/python3 -I -B -S -c '
import hashlib,os,stat,sys
path="/opt/xuanjun-community-preview/install-stopped-v1.py"
expected="bc4ece1bc6891b770b906dca37304018515495c59c5d3aad8828c0d8ec481260"
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
 st=os.fstat(fd)
 assert stat.S_ISREG(st.st_mode) and st.st_uid==0 and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1 and 0<st.st_size<=131072
 before=(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
 raw=b""
 while len(raw)<=131072:
  part=os.read(fd,131073-len(raw))
  if not part:break
  raw+=part
 after=os.fstat(fd);pathst=os.stat(path,follow_symlinks=False)
 ident=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_gid,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
 assert len(raw)==st.st_size and ident(after)==before and ident(pathst)==before
finally:os.close(fd)
assert hashlib.sha256(raw).hexdigest()==expected
sys.argv=[path,"--archive",sys.argv[1],"--manifest",sys.argv[2]]
ns={"__name__":"__main__","__file__":path}
exec(compile(raw,path,"exec"),ns)
' "$1" "$2" >"$receipt_file"
child_exit=$?
set -e
/usr/bin/python3 -I -B -S -c '
import json,sys
path=sys.argv[1];child=int(sys.argv[2])
try:
 data=open(path,"rb").read(4097)
 if len(data)>4096 or not data.endswith(b"\n") or data.count(b"\n")!=1:raise ValueError()
 value=json.loads(data[:-1])
 keys={"state","install_root","archive_sha256","manifest_sha256","publish_attempted","temp_identity_sha256","target_published","retry_safe","parent_fsync_completed","site_executed","bc_executed"}
 ok=(child==0 and type(value) is dict and set(value)==keys and value["state"]=="V2_CARRIER_INSTALLED"
     and value["install_root"]=="/opt/xuanjun-community-preview/control-stopped-v1"
     and value["archive_sha256"]=="5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4"
     and value["manifest_sha256"]=="e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a"
     and value["publish_attempted"] is True and isinstance(value["temp_identity_sha256"],str) and len(value["temp_identity_sha256"])==64
     and value["target_published"] is True and value["retry_safe"] is False and value["parent_fsync_completed"] is True
     and value["site_executed"] is False and value["bc_executed"] is False)
 if not ok:raise ValueError()
 sys.stdout.buffer.write(data);raise SystemExit(0)
except Exception:
 print(json.dumps({"state":"V2_INSTALL_ENTRY_UNKNOWN","reason":"EXIT_OR_RECEIPT_UNPROVEN","child_exit":child,
                   "retry_safe":False,"inspect_only":True,"bc_admitted":False,"site_executed":False},sort_keys=True))
 raise SystemExit(2)
' "$receipt_file" "$child_exit"
