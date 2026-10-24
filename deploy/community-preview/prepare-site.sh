#!/bin/sh
# REVIEW CANDIDATE ONLY. Owner separately approves each stage; not run by CI.
set -eu
[ "$#" -eq 2 ] || exit 2
case "$1" in install|image-load|snapshot|validate-clones) ;; *) exit 2;; esac
exec /usr/bin/python3 -I -B -S - "$1" "$2" <<'PREPARE'
import hashlib,json,os,re,stat,sys,time
BASE='/opt/xuanjun-community-preview'
EXPECTED='807891f48b80ed336a7eab8dc6efd2906d0d15261488bc54eaabc157f6ebc810'
HOST='iZd7oeikknn1z21sq6ji6zZ'
def need(v):
 if not v:raise SystemExit('HOLD_PROTECTED_BOOTSTRAP')
def directory(path):
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in path.split('/')[1:]:
   child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
   s=os.fstat(fd);need(s.st_uid==0 and not s.st_mode&0o022)
  return os.dup(fd)
 finally:os.close(fd)
def identity(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def read(parent,name,limit):
 fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
 try:
  s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and s.st_size<=limit)
  b=os.read(fd,limit+1);need(len(b)==s.st_size and identity(s)==identity(os.fstat(fd))==identity(os.stat(name,dir_fd=parent,follow_symlinks=False)));return b
 finally:os.close(fd)
need(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST)
stage,digest=sys.argv[1:];need(re.fullmatch('[0-9a-f]{64}',digest))
base=directory(BASE)
try:
 raw=read(base,'site-prepare-approval.json',16384);need(hashlib.sha256(raw).hexdigest()==digest)
 def unique(pairs):
  out={}
  for k,v in pairs:need(k not in out);out[k]=v
  return out
 p=json.loads(raw,object_pairs_hook=unique)
 need(type(p) is dict and set(p)=={'format','host','stage','entry_sha256','issued_at','expires_at','all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'}
      and type(p.get('format')) is int and p['format']==1 and p.get('host')==HOST and p.get('stage')==stage and p.get('entry_sha256')==EXPECTED
      and type(p.get('issued_at')) is int and type(p.get('expires_at')) is int
      and p['issued_at']<=time.time()<=p['expires_at']<=p['issued_at']+600)
 try:entry=read(base,'site-prepare-v1.py',131072)
 except FileNotFoundError:
  need(stage=='install' and p['all_writers_frozen_evidence_sha256'] is None and p['snapshot_manifest_sha256'] is None)
  source=directory(BASE+'/image-f131-40059478387')
  try:
   need(stat.S_IMODE(os.fstat(source).st_mode)==0o700)
   entry=read(source,'community_preview_site_prepare.py',131072);need(hashlib.sha256(entry).hexdigest()==EXPECTED)
  finally:os.close(source)
  fd=os.open('site-prepare-v1.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=base)
  try:
   os.fchown(fd,0,0);os.fchmod(fd,0o600);v=memoryview(entry)
   while v:n=os.write(fd,v);need(n>0);v=v[n:]
   os.fsync(fd)
  finally:os.close(fd)
  os.fsync(base)
 need(hashlib.sha256(entry).hexdigest()==EXPECTED)
finally:os.close(base)
# Original preparation source guard rechecks exact permit/source/stage and locks
# the protected entry inode. No untrusted cwd/import path or shell expansion.
os.execv('/usr/bin/python3',['/usr/bin/python3','-I','-B','-S',BASE+'/site-prepare-v1.py','--stage',stage,'--approval-sha256',digest])
PREPARE
