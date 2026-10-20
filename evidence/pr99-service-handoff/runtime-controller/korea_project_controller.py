"""Tokyo -> Korea existing-channel precopy; deployment is deliberately separate.

Reuses the existing full-project archive, never treats it as final live state.
No service changes, extraction, database replacement, or trade execution.
"""
import os, sys, stat, json, hashlib, subprocess, shlex, tempfile, fcntl, time
from pathlib import Path

SOURCE='iZ6wee8q9z4t03hvqumwfhZ'
TARGET='iZmj7a5kwr75qc1tul4kf9Z'
ARCHIVE=Path('/root/pr99-full-project-transfer-lho67lqn/project.tar.gz')
JOB=Path('/root/pr99-korea-project-precopy-v1')
SSH=['/usr/bin/sudo','-n','-u','admin','/usr/bin/ssh','-T',
 '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
 '-o','ConnectionAttempts=1','-o','ClearAllForwardings=yes','-o','ForwardAgent=no',
 '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','yibi-dev']

REMOTE=r'''
import os,sys,stat,json,hashlib,shutil,subprocess,fcntl
from pathlib import Path
if os.uname().nodename.split('.')[0]!='iZmj7a5kwr75qc1tul4kf9Z':
 raise SystemExit('HOLD_TARGET_HOST')
os.umask(0o077)
action=sys.argv[1]
if action=='inspect':
 units=subprocess.run(['systemctl','list-units','--type=service','--all','--no-legend','--no-pager'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=20)
 if units.returncode: raise SystemExit('HOLD_UNIT_QUERY')
 root=subprocess.run(['sudo','-n','/usr/bin/python3','-I','-B','-S','-c','import os;print(os.geteuid())'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 paths={}
 for name in ('/opt/trading-system','/opt/xuanjun-migration-s07','/var/lib/pr99-migration-channel'):
  p=Path(name);paths[name]={'exists':p.exists(),'symlink':p.is_symlink()}
 print(json.dumps({'host':os.uname().nodename.split('.')[0],'uid':os.geteuid(),'python':sys.version.split()[0],
  'home':str(Path.home()),'free_disk':shutil.disk_usage(str(Path.home())).free,'paths':paths,
  'related_units':[line for line in units.stdout.splitlines() if any(w in line.lower() for w in ('binance','trading','xuanjun','rpc','runner','tailscale','openclaw'))],
  'root_python_available':root.returncode==0 and root.stdout.strip()==b'0','service_changes':0}),flush=True)
 sys.exit(0)
if action not in ('receive','verify'): raise SystemExit('HOLD_ACTION')
sha=sys.argv[2];size=int(sys.argv[3])
if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) or not 0<size<1000000000: raise SystemExit('HOLD_PACKAGE_REQUEST')
base=Path.home()/'pr99-tokyo-project-precopy'
for p in [base]+list(base.parents):
 if p.is_symlink(): raise SystemExit('HOLD_DESTINATION_SYMLINK')
if action=='receive': base.mkdir(mode=0o700,exist_ok=True)
s=base.stat()
if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode&0o077: raise SystemExit('HOLD_PRIVATE_DESTINATION')
final=base/(sha+'.tar.gz');partial=base/(sha+'.partial')
if action=='receive':
 if final.exists() or final.is_symlink(): raise SystemExit('HOLD_EXISTING_FINAL_QUERY_ONLY')
 if shutil.disk_usage(str(base)).free<size+104857600: raise SystemExit('HOLD_TARGET_DISK')
 fd=os.open(str(partial),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 h=hashlib.sha256();count=0
 with os.fdopen(fd,'wb') as f:
  while count<size:
   b=sys.stdin.buffer.read(min(1048576,size-count))
   if not b: raise SystemExit('HOLD_SHORT_TRANSFER_KEEP_PARTIAL')
   f.write(b);h.update(b);count+=len(b)
  if sys.stdin.buffer.read(1): raise SystemExit('HOLD_EXTRA_TRANSFER_BYTES')
  f.flush();os.fsync(f.fileno())
 if h.hexdigest()!=sha: raise SystemExit('HOLD_TRANSFER_SHA_KEEP_PARTIAL')
else:
 partial=final
fd=os.open(str(partial),os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
 s=os.fstat(f.fileno())
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_nlink!=1 or s.st_size!=size or s.st_mode&0o077: raise SystemExit('HOLD_RECEIVED_FILE_IDENTITY')
 h=hashlib.sha256()
 while True:
  b=f.read(1048576)
  if not b:break
  h.update(b)
 if h.hexdigest()!=sha: raise SystemExit('HOLD_DISK_SHA')
if action=='receive':
 os.rename(str(partial),str(final))
 fd=os.open(str(base),os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
print(json.dumps({'host':os.uname().nodename.split('.')[0],'status':'PASS_ARCHIVE_PRECOPY',
 'sha256':sha,'bytes':size,'archive':str(final),'final_sync':False,'production_cutover':False}),flush=True)
'''

def require(value,reason):
 if not value: raise RuntimeError(reason)

def safe_archive():
 for p in [ARCHIVE]+list(ARCHIVE.parents): require(not p.is_symlink(),'SOURCE_ARCHIVE_SYMLINK')
 fd=os.open(str(ARCHIVE),os.O_RDONLY|os.O_NOFOLLOW)
 f=os.fdopen(fd,'rb');s=os.fstat(fd)
 require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and s.st_size==167760742,'SOURCE_ARCHIVE_IDENTITY')
 return f,s

def query(action,*args):
 remote=shlex.join(['/usr/bin/python3','-I','-B','-S','-c',REMOTE,action,*map(str,args)])
 p=subprocess.run(SSH+[remote],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=70)
 require(p.returncode==0,'REMOTE_QUERY_FAILED_PRIVATE_LOG_REQUIRED')
 data=json.loads(p.stdout);require(data.get('host')==TARGET,'REMOTE_HOST_BINDING')
 return data

def save(path,value):
 with path.open('x') as f:
  json.dump(value,f,indent=2,sort_keys=True);f.flush();os.fsync(f.fileno())
 fd=os.open(str(path.parent),os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)

def main():
 require(os.geteuid()==0 and os.uname().nodename.split('.')[0]==SOURCE,'SOURCE_IDENTITY')
 os.umask(0o077)
 lock=os.open('/root/pr99-controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 require(not JOB.is_symlink(),'JOB_SYMLINK')
 if JOB.exists():
  print('MODE=EXISTING_CHECKPOINT_QUERY_ONLY',flush=True)
  if (JOB/'package.json').is_file():
   package=json.loads((JOB/'package.json').read_text())
   print(json.dumps(query('verify',package['sha256'],package['bytes']),sort_keys=True),flush=True)
  print('CHECKPOINT='+str(JOB),flush=True)
  return
 print('PHASE=KOREA_EXISTING_SSH_INSPECTION',flush=True)
 remote=query('inspect')
 print('KOREA_ENVIRONMENT='+json.dumps(remote,sort_keys=True),flush=True)
 f,s=safe_archive()
 with f:
  h=hashlib.sha256()
  while True:
   b=f.read(1048576)
   if not b:break
   h.update(b)
  digest=h.hexdigest()
  require(remote['free_disk']>s.st_size+104857600,'TARGET_DISK_SPACE')
  JOB.mkdir(mode=0o700)
  save(JOB/'korea-environment.json',remote)
  package={'sha256':digest,'bytes':s.st_size,'source':str(ARCHIVE),'snapshot':'EXISTING_PRECOPY_NOT_FINAL'}
  save(JOB/'package.json',package)
  print('CHECKPOINT='+str(JOB),flush=True)
  print('PHASE=REUSE_EXISTING_PROJECT_ARCHIVE',flush=True)
  save(JOB/'transfer.intent.json',{'target':TARGET,'alias':'yibi-dev','package':package})
  cmd=shlex.join(['/usr/bin/python3','-I','-B','-S','-c',REMOTE,'receive',digest,str(s.st_size)])
  f.seek(0)
  with (JOB/'remote.stdout').open('xb') as out,(JOB/'remote.stderr').open('xb') as err:
   p=subprocess.Popen(SSH+[cmd],stdin=subprocess.PIPE,stdout=out,stderr=err)
   try:
    sent=0;last=0
    while True:
     b=f.read(1048576)
     if not b:break
     p.stdin.write(b);sent+=len(b)
     progress=sent*100//s.st_size
     if progress>=last+10:
      print('SENT_PROGRESS='+str(progress)+'%',flush=True);last=progress
    p.stdin.close()
    while True:
     try: rc=p.wait(timeout=10);break
     except subprocess.TimeoutExpired: print('WAITING_TARGET_DISK_READBACK',flush=True)
   except BaseException:
    if p.poll() is None:p.kill();p.wait()
    raise
  require(rc==0,'TRANSFER_OUTCOME_UNKNOWN_NO_REPLAY')
  after=os.fstat(f.fileno());require((s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),'SOURCE_ARCHIVE_CHANGED')
  result=query('verify',digest,s.st_size)
  require(result.get('status')=='PASS_ARCHIVE_PRECOPY' and result.get('sha256')==digest and result.get('bytes')==s.st_size,'TARGET_READBACK')
  save(JOB/'receipt.json',result)
  print('RESULT='+json.dumps(result,sort_keys=True),flush=True)
  print('RECEIPT='+str(JOB/'receipt.json'),flush=True)
  print('NEXT_REQUIRED=LIVE_SERVICE_DEPENDENCY_BINDING_AND_FINAL_SYNC',flush=True)

if __name__=='__main__':
 try:main()
 except BaseException as exc:
  print('STATUS=HOLD\nREASON='+str(exc)+'\nPRESERVE_CHECKPOINT_NO_BLIND_RETRY=YES',flush=True)
  sys.exit(2)
