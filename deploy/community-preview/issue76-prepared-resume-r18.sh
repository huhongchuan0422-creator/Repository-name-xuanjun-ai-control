#!/bin/sh
set -eu
[ "$#" -eq 1 ] || { echo 'usage: issue76-prepared-resume-r18.sh inspect|update|resume|query|recover' >&2; exit 2; }
case "$1" in inspect|update|resume|query|recover) ;; *) echo HOLD_OPERATION >&2; exit 2;; esac
bootstrap=$(/usr/bin/cat <<'PY'
import hashlib,os,pwd,stat,sys
path='/home/admin/community_preview_prepared_resume_delivery.py'
expected='4bb22238837df15f856538b3cdb9daffef02603ea7fcc41fa414064e25614724'
admin=pwd.getpwnam('admin').pw_uid
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
 before=os.stat(path,follow_symlinks=False);opened=os.fstat(fd)
 identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 assert stat.S_ISREG(opened.st_mode) and opened.st_uid==admin and stat.S_IMODE(opened.st_mode)==0o600 and opened.st_nlink==1 and opened.st_size<=131072
 assert identity(before)==identity(opened)
 raw=b''
 while len(raw)<opened.st_size:
  part=os.read(fd,opened.st_size-len(raw));assert part;raw+=part
 assert identity(opened)==identity(os.fstat(fd))==identity(os.stat(path,follow_symlinks=False))
finally:os.close(fd)
assert hashlib.sha256(raw).hexdigest()==expected
ns={'__name__':'issue76_prepared_resume_delivery'}
exec(compile(raw,path,'exec'),ns)
raise SystemExit(ns['cli']([sys.argv[1]]))
PY
)
exec sudo -n /usr/bin/python3 -I -B -S -c "$bootstrap" "$1"
