#!/bin/sh
# SOURCE REVIEW ONLY. Fixed STOPPED_HANDOFF_V1 carrier installer; does not run B/C.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'usage: install-stopped-v1.sh ABS_CONTROL_ZIP ABS_MANIFEST_JSON' >&2
  exit 64
fi
case "$1:$2" in
  /*:/*) ;;
  *) echo 'absolute input paths required' >&2; exit 64 ;;
esac
exec /usr/bin/sudo -n /usr/bin/python3 -I -B -S -c '
import hashlib,os,stat,sys
path="/opt/xuanjun-community-preview/install-stopped-v1.py"
expected="e4989f75d7bd1892b78fe131f51d6868910f58d4fa1ae88e7628c112bebca529"
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
' "$1" "$2"
