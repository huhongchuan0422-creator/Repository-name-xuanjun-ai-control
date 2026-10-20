"""Current offline recovery handoff; never activates trading or claims cutover.

Reuses korea_project_controller's SSH and the already received archive. Each
SQLite backup has its own capture point; the tree is not an atomic live snapshot.
"""
import argparse, fcntl, hashlib, io, json, os, shlex, shutil, sqlite3
import stat, subprocess, sys, tarfile, tempfile, time
from pathlib import Path, PurePosixPath
import korea_project_controller as existing

BASE=Path('/opt/trading-system')
SHA='f4db2e4e5f205df7e0eb7997e6df41d818d007485736a1add65124cb695276e9'
ROOT='/opt/xuanjun-migration-s07/releases/korea-project-precopy-f4db2e4e5f20'

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
    return h.hexdigest()

def relative(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or any(x in ('','..','.') for x in name.split('/')) or '\\' in name:
        raise RuntimeError('INVALID_RELATIVE_PATH')
    return name

def stable_copy(source,dest):
    fd=os.open(str(source),os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as inp,open(dest,'xb') as out:
        before=os.fstat(inp.fileno())
        if not stat.S_ISREG(before.st_mode): raise RuntimeError('FILE_TYPE')
        shutil.copyfileobj(inp,out,1048576);out.flush();os.fsync(out.fileno())
        after=os.fstat(inp.fileno())
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise RuntimeError('SOURCE_CHANGED_KEEP_CHECKPOINT')
    return before

def sqlite_copy(source,dest,seconds=45):
    deadline=time.monotonic()+seconds
    def progress(*unused):
        if time.monotonic()>deadline: raise TimeoutError('SQLITE_BACKUP_DEADLINE')
    # URI mode=ro includes committed WAL without checkpointing the source.
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=2) as inp:
        with sqlite3.connect(str(dest)) as out:
            inp.backup(out,pages=256,progress=progress,sleep=.05)
            if out.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                raise RuntimeError('SQLITE_INTEGRITY')
    with open(dest,'rb') as f: os.fsync(f.fileno())

def collect(base,work,baseline):
    files={};dirs=[];links={};snapshots=[];skipped=[]
    for current,subdirs,names in os.walk(base,followlinks=False):
        current=Path(current)
        for name in list(subdirs)+names:
            p=current/name;rel=relative(p.relative_to(base).as_posix());s=p.lstat()
            if stat.S_ISLNK(s.st_mode):
                links[rel]=os.readlink(p)
                if name in subdirs: subdirs.remove(name)
                continue
            if stat.S_ISDIR(s.st_mode): dirs.append(rel);continue
            if not stat.S_ISREG(s.st_mode): raise RuntimeError('SPECIAL_FILE_NOT_SUPPORTED')
            # Sidecars belong to the backup of their corresponding SQLite main.
            if any(name.endswith(x) for x in ('-wal','-shm','-journal')):
                main=p.with_name(name.rsplit('-',1)[0])
                if main.is_file():
                    with main.open('rb') as f: header=f.read(16)
                    if header==b'SQLite format 3\x00': skipped.append(rel);continue
            dest=work/'files'/rel;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as f: header=f.read(16)
            if header==b'SQLite format 3\x00':
                identity=(s.st_dev,s.st_ino)
                sqlite_copy(p,dest)
                after=p.lstat()
                if identity!=(after.st_dev,after.st_ino) or not stat.S_ISREG(after.st_mode):
                    raise RuntimeError('SQLITE_SOURCE_REPLACED')
                snapshots.append(rel)
            else: stable_copy(p,dest)
            h=digest(dest);files[rel]={'sha256':h,'bytes':dest.stat().st_size,'mode':stat.S_IMODE(s.st_mode)&0o777}
            if baseline.get(rel)==h: dest.unlink()
    return {'schema':1,'source':existing.SOURCE,'target':existing.TARGET,
            'baseline_sha256':SHA,'files':files,'directories':sorted(dirs),
            'symlinks_not_activated':links,'sqlite_backups':snapshots,
            'sqlite_sidecars_not_copied':skipped,'production_cutover':False,
            'consistency':'PER_FILE_STABLE_AND_PER_DATABASE_BACKUP_NOT_GLOBAL_ATOMIC'}

# This program is sent over the existing authenticated SSH session. It writes
# only a new private release; no live configuration, units or routes are touched.
REMOTE=r'''
import os,sys,json,stat,tarfile,hashlib,tempfile,shutil,fcntl
from pathlib import Path
if os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZmj7a5kwr75qc1tul4kf9Z': raise SystemExit('HOST_OR_ROOT')
os.umask(0o077)
root=Path('/opt/xuanjun-migration-s07/releases')
baseline=root/'korea-project-precopy-f4db2e4e5f20/opt/trading-system'
lock=os.open('/root/pr99-korea-project-install.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
expected=sys.argv[1]
action=sys.argv[2] if len(sys.argv)>2 else 'receive'
if action not in ('receive','query'): raise SystemExit('ACTION')
if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected): raise SystemExit('PACKAGE_ID')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def safe(name):
 if not name or name.startswith('/') or '\\' in name or any(p in ('','..','.') for p in name.split('/')): raise RuntimeError('UNSAFE_MEMBER')
 return name
if not baseline.is_dir() or any(p.is_symlink() for p in [baseline]+list(baseline.parents)): raise SystemExit('BASELINE_MISSING_OR_SYMLINK')
final=root/('korea-current-recovery-'+expected)
if final.exists():
 if any(p.is_symlink() for p in [final]+list(final.parents)): raise SystemExit('RESULT_SYMLINK')
 manifest=json.loads((final/'manifest.json').read_text())
 receipt=json.loads((final/'receipt.json').read_text())
 if receipt.get('status')!='PASS_CURRENT_OFFLINE_RECOVERY' or receipt.get('package_sha256')!=expected: raise SystemExit('RESULT_IDENTITY')
 for name,meta in manifest['files'].items():
  p=final/'project'/safe(name)
  if any(q.is_symlink() for q in [p]+list(p.parents)) or p.stat().st_size!=meta['bytes'] or sha(p)!=meta['sha256']: raise SystemExit('RESULT_DISK_DRIFT')
 print(json.dumps(receipt),flush=True);sys.exit(0)
if action=='query': raise SystemExit('REMOTE_RESULT_NOT_COMMITTED_KEEP_CHECKPOINT')
work=Path(tempfile.mkdtemp(prefix='.korea-current-',dir=str(root)))
print('TARGET_CHECKPOINT='+str(work),file=sys.stderr,flush=True)
package=work/'delta.tar.gz'
with package.open('xb') as out:
 shutil.copyfileobj(sys.stdin.buffer,out,1048576);out.flush();os.fsync(out.fileno())
if sha(package)!=expected: raise SystemExit('DELTA_SHA')
with tarfile.open(str(package),'r:gz') as tar:
 members=tar.getmembers();seen=set()
 if len(members)>50000 or sum(m.size for m in members)>2000000000: raise SystemExit('PACKAGE_LIMIT')
 for m in members:
  safe(m.name)
  if not m.isfile() or m.name in seen or m.size<0: raise SystemExit('UNSAFE_MEMBER')
  seen.add(m.name)
 manifest=json.load(tar.extractfile('manifest.json'))
 if manifest.get('baseline_sha256')!='f4db2e4e5f205df7e0eb7997e6df41d818d007485736a1add65124cb695276e9' or manifest.get('source')!='iZ6wee8q9z4t03hvqumwfhZ' or manifest.get('target')!='iZmj7a5kwr75qc1tul4kf9Z': raise SystemExit('MANIFEST_IDENTITY')
 if shutil.disk_usage(str(root)).free<sum(m['bytes'] for m in manifest['files'].values())+104857600: raise SystemExit('DISK_SPACE')
 app=work/'project';app.mkdir(mode=0o700)
 for name in manifest['directories']: (app/safe(name)).mkdir(parents=True,exist_ok=True,mode=0o700)
 needed={'manifest.json'}
 for name,meta in manifest['files'].items():
  safe(name);dest=app/name;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  member='files/'+name
  if member in seen:
   inp=tar.extractfile(member);needed.add(member)
  else:
   source=baseline/name
   if any(p.is_symlink() for p in [source]+list(source.parents)) or not source.is_file(): raise SystemExit('BASELINE_FILE_UNAVAILABLE')
   inp=source.open('rb')
  with inp, dest.open('xb') as out:
   shutil.copyfileobj(inp,out,1048576);out.flush();os.fsync(out.fileno())
  if dest.stat().st_size!=meta['bytes'] or sha(dest)!=meta['sha256']: raise SystemExit('DISK_READBACK')
 if needed!=seen: raise SystemExit('UNDECLARED_DELTA_MEMBERS')
 # Preserve link metadata only: never create links that could escape staging.
 with (work/'manifest.json').open('x') as f: json.dump(manifest,f,sort_keys=True);f.flush();os.fsync(f.fileno())
 result={'status':'PASS_CURRENT_OFFLINE_RECOVERY','package_sha256':expected,'files':len(manifest['files']),'sqlite_backups':len(manifest['sqlite_backups']),'symlinks_not_activated':len(manifest['symlinks_not_activated']),'directory':str(final),'production_cutover':False,'source_services_stopped':False}
 with (work/'receipt.json').open('x') as f: json.dump(result,f,sort_keys=True);f.flush();os.fsync(f.fileno())
 os.rename(str(work),str(final))
 fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 print(json.dumps(result),flush=True)
'''

def main():
    existing.require(os.geteuid()==0 and os.uname().nodename.split('.')[0]==existing.SOURCE,'SOURCE_IDENTITY')
    os.umask(0o077)
    lock=os.open('/root/pr99-controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    job=Path('/root/pr99-korea-current-sync-v1')
    if job.exists():
        print('CHECKPOINT='+str(job),flush=True)
        if not (job/'transfer.intent.json').exists(): raise RuntimeError('LOCAL_PREPARATION_INCOMPLETE_KEEP_CHECKPOINT')
        intent=json.loads((job/'transfer.intent.json').read_text())
        command=shlex.join(['/usr/bin/sudo','-n','/usr/bin/python3','-I','-B','-S','-c',REMOTE,intent['sha256'],'query'])
        response=subprocess.run(existing.SSH+[command],input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        if response.returncode: raise RuntimeError('REMOTE_QUERY_NOT_COMMITTED_NO_REPLAY')
        result=json.loads(response.stdout)
        if result.get('status')!='PASS_CURRENT_OFFLINE_RECOVERY' or result.get('package_sha256')!=intent['sha256']: raise RuntimeError('REMOTE_RECEIPT')
        if not (job/'receipt.json').exists(): existing.save(job/'receipt.json',result)
        print(json.dumps(result,sort_keys=True),flush=True);return
    # Verify and reuse the completed precopy before allocating a new attempt.
    prior=json.loads((existing.JOB/'receipt.json').read_text())
    existing.require(prior.get('status')=='PASS_ARCHIVE_PRECOPY' and prior.get('sha256')==SHA,'PRECOPY_ACCEPTANCE')
    existing.require(digest(existing.ARCHIVE)==SHA,'BASELINE_ARCHIVE_SHA')
    job.mkdir(mode=0o700);print('CHECKPOINT='+str(job),flush=True)
    baseline={}
    with tarfile.open(str(existing.ARCHIVE),'r:gz') as t:
        for m in t:
            prefix='opt/trading-system/'
            if m.isfile() and m.name.startswith(prefix):
                h=hashlib.sha256()
                with t.extractfile(m) as f:
                    for b in iter(lambda:f.read(1048576),b''): h.update(b)
                baseline[m.name[len(prefix):]]=h.hexdigest()
    print('PHASE=CURRENT_SOURCE_AND_SQLITE_BACKUPS',flush=True)
    manifest=collect(BASE,job,baseline)
    existing.save(job/'manifest.json',manifest)
    package=job/'delta.tar.gz'
    with tarfile.open(str(package),'w:gz') as t:
        t.add(str(job/'manifest.json'),arcname='manifest.json',recursive=False)
        for name in sorted(manifest['files']):
            p=job/'files'/name
            if p.exists(): t.add(str(p),arcname='files/'+name,recursive=False)
    with package.open('rb') as f: os.fsync(f.fileno())
    h=digest(package)
    existing.save(job/'transfer.intent.json',{'sha256':h,'bytes':package.stat().st_size})
    print('PHASE=EXISTING_SSH_DELTA_TRANSFER_AND_PRIVATE_INSTALL',flush=True)
    command=shlex.join(['/usr/bin/sudo','-n','/usr/bin/python3','-I','-B','-S','-c',REMOTE,h])
    with package.open('rb') as inp,(job/'remote.stdout').open('xb') as out,(job/'remote.stderr').open('xb') as err:
        p=subprocess.Popen(existing.SSH+[command],stdin=inp,stdout=out,stderr=err)
        deadline=time.monotonic()+1800
        try:
            while True:
                try: code=p.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('TRANSFER_OR_TARGET_VERIFICATION_RUNNING',flush=True)
                    if time.monotonic()>deadline: raise TimeoutError('REMOTE_DEADLINE_UNKNOWN_QUERY_ONLY')
        except BaseException:
            if p.poll() is None: p.kill();p.wait()
            raise
    if code: raise RuntimeError('REMOTE_OUTCOME_UNKNOWN_NO_REPLAY')
    result=json.loads((job/'remote.stdout').read_text())
    if result.get('package_sha256')!=h or result.get('status')!='PASS_CURRENT_OFFLINE_RECOVERY': raise RuntimeError('REMOTE_RECEIPT')
    existing.save(job/'receipt.json',result);print(json.dumps(result,sort_keys=True),flush=True)
    print('BUSINESS_SERVICE_CUTOVER=NOT_IMPLEMENTED_IN_THIS_OFFLINE_HANDOFF',flush=True)

if __name__=='__main__':
    try: main()
    except BaseException as exc:
        print('STATUS=HOLD\nREASON='+type(exc).__name__+'\nPRESERVE_CHECKPOINT_NO_BLIND_RETRY=YES',flush=True)
        sys.exit(2)
