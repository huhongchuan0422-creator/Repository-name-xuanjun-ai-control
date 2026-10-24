"""Original UK pre-update preparation. Default disabled; NEVER runs an update.

Future root-only stage caller, independently approved fixed files only. No HTTP,
secret output, grant, service installation, container stop/start or data restore
in place. Snapshot requires separately evidenced exclusive writer freeze.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import resource
import signal
import stat
import subprocess
import time
import zipfile

HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/opt/xuanjun-community-preview'
ENTRY=BASE+'/site-prepare-v1.py'
PERMIT=BASE+'/site-prepare-approval.json'
FREEZE=BASE+'/writer-freeze-reference.json'
INSTALL=BASE+'/control-oci2330-v1'
INPUT=BASE+'/image-f131-40059478387'
BACKUP=BASE+'/backup-2330-to-f131-v1'
DATA='/var/lib/xuanjun-community-preview'
DOCKER=['/usr/bin/docker','--host','unix:///var/run/docker.sock']
OLD_ID='818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c'
OLD_IMAGE='sha256:0846f7cfc71d443095a6c5e3a59eabf5d2973eda90e29c831f335c163a2c8f32'
NEW_IMAGE='sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a'
PRODUCT='f13155ed63a3137d41766ee587d9b4b96a81477f'
CARRIER_SHA='aa8afb5c05240e3c4835680e8cec765fa4199f0b7f230e3adaced8bc489397f9'
CARRIER_MANIFEST='e780675ef48c4cd077000c943c5ffe57b390277b6246d43939f54590aabd199a'
OUTER_SHA='c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e'
INNER_SHA='eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875'
EXPIRES=1793072670
UID=0
ROOT_GID=0
ROOT_ANCHOR='/'
ALLOWED_GIDS=(0,1008)
_COMPONENT=None
_ACTIVE=None
MAX_FILES=20000
MAX_BYTES=4*1024**3
RESERVE=1024**3
LAYER_TAR_BYTES=155941888
LAYER_ENTRIES=7690
STAGES=('install','image-load','snapshot','validate-clones')
class Hold(RuntimeError):pass

def need(ok,reason):
    if not ok:raise Hold(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def exact_json(raw):
    def pairs(rows):
        out={}
        for k,v in rows:
            need(k not in out,'DUPLICATE_JSON');out[k]=v
        return out
    def invalid(v):raise Hold('NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
def identity(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def directory(path):
    need(type(path) is str and path.startswith('/') and all(p not in ('','.','..') for p in path.split('/')[1:]),'EXACT_PATH')
    need(ROOT_ANCHOR=='/' or path.startswith(ROOT_ANCHOR+'/'),'ROOT_ANCHOR_SCOPE')
    fd=os.open(ROOT_ANCHOR,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parts=path.split('/')[1:] if ROOT_ANCHOR=='/' else path[len(ROOT_ANCHOR)+1:].split('/')
        current=ROOT_ANCHOR.rstrip('/')
        for part in parts:
            current+='/'+part
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
            s=os.fstat(fd);allowed=current==DATA or current.startswith(DATA+'/') or any(current.startswith(BACKUP+'/'+n+'/'+r) for n in ('snapshot','restore-old','verify-f131','verify-downgrade') for r in ('data','config'))
            need((s.st_uid==UID or allowed and s.st_uid==10001) and not s.st_mode&0o022,'PROTECTED_PARENT')
        return os.dup(fd)
    finally:os.close(fd)
def private_parent(path):
    fd=directory(path);s=os.fstat(fd)
    need(s.st_uid==UID and (not s.st_mode&0o022 if path==BASE else stat.S_IMODE(s.st_mode)==0o700),'PRIVATE_ROOT_PARENT');return fd

def read(path,limit,*,root=True):
    parent=directory(os.path.dirname(path))
    try:
        name=os.path.basename(path);before=os.stat(name,dir_fd=parent,follow_symlinks=False)
        f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        try:
            s=os.fstat(f)
            need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=limit and identity(before)==identity(s),'FILE_BOUNDARY')
            if root:need(s.st_uid==UID and stat.S_IMODE(s.st_mode)==0o600,'ROOT_0600_FILE')
            chunks=[];total=0
            while True:
                b=os.read(f,min(1048576,limit-total+1))
                if not b:break
                total+=len(b);need(total<=limit,'FILE_LIMIT');chunks.append(b)
            need(total==s.st_size and identity(s)==identity(os.fstat(f))==identity(os.stat(name,dir_fd=parent,follow_symlinks=False)),'FILE_CHANGED')
            return b''.join(chunks)
        finally:os.close(f)
    finally:os.close(parent)

def create_file(parent,name,raw,uid=None,gid=None,mode=0o600):
    if uid is None:uid=UID
    if gid is None:gid=ROOT_GID
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
    try:
        os.fchown(fd,uid,gid);os.fchmod(fd,mode)
        view=memoryview(raw)
        while view:n=os.write(fd,view);need(n>0,'WRITE_FAILED');view=view[n:]
        os.fsync(fd)
    finally:os.close(fd)
    os.fsync(parent)

def new_dir(parent,name):
    os.mkdir(name,0o700,dir_fd=parent);os.fsync(parent)
    fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    os.fchmod(fd,0o700);os.fchown(fd,UID,ROOT_GID);return fd

def space(fd,required,files):
    s=os.fstatvfs(fd)
    need(s.f_bavail*s.f_frsize>=required+RESERVE and s.f_favail>=files+128,'SPACE_OR_INODES_HOLD')

def authorize(stage,digest):
    need(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'EXACT_ROOT_HOST')
    need(os.path.abspath(__file__)==ENTRY,'FIXED_ENTRY_REQUIRED')
    need(stage in STAGES and type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest),'STAGE_APPROVAL_REQUIRED')
    raw=read(PERMIT,16384);need(sha(raw)==digest,'APPROVAL_CHANGED');p=exact_json(raw)
    fields={'format','host','stage','entry_sha256','issued_at','expires_at','all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'}
    need(type(p) is dict and set(p)==fields and type(p['format']) is int and p['format']==1 and p['host']==HOST and p['stage']==stage,'EXACT_STAGE_SCOPE')
    need(type(p['issued_at']) is int and type(p['expires_at']) is int and p['issued_at']<=time.time()<=p['expires_at']<=p['issued_at']+600,'STAGE_APPROVAL_EXPIRED')
    need(p['entry_sha256']==sha(read(ENTRY,131072)),'ENTRY_CHANGED')
    for k in ('all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'):
        need(p[k] is None or type(p[k]) is str and re.fullmatch('[0-9a-f]{64}',p[k]),'EXACT_EVIDENCE_REFERENCE')
    if stage in ('install','image-load'):need(p['all_writers_frozen_evidence_sha256'] is None and p['snapshot_manifest_sha256'] is None,'UNRELATED_EVIDENCE_DENIED')
    if stage=='snapshot':need(p['snapshot_manifest_sha256'] is None,'UNRELATED_EVIDENCE_DENIED')
    if stage=='snapshot':
        need(p['all_writers_frozen_evidence_sha256'] is not None,'EXCLUSIVE_WRITER_FREEZE_PROOF_REQUIRED')
        freeze_raw=read(FREEZE,16384)
        need(sha(freeze_raw)==p['all_writers_frozen_evidence_sha256'],'FREEZE_REFERENCE_CHANGED')
        freeze=exact_json(freeze_raw)
        need(type(freeze) is dict and set(freeze)=={'format','host','old_id','old_image','roots','issued_at','expires_at','all_writers_frozen','owner_review_reference_sha256'}
            and type(freeze['format']) is int and freeze['format']==1 and freeze['host']==HOST
            and freeze['old_id']==OLD_ID and freeze['old_image']==OLD_IMAGE and freeze['roots']==[DATA+'/data',DATA+'/config']
            and freeze['all_writers_frozen'] is True and type(freeze['owner_review_reference_sha256']) is str
            and re.fullmatch('[0-9a-f]{64}',freeze['owner_review_reference_sha256'])
            and type(freeze['issued_at']) is int and type(freeze['expires_at']) is int
            and freeze['issued_at']<=time.time()<=freeze['expires_at']<=freeze['issued_at']+600,'EXACT_REVIEWED_WRITER_FREEZE_REQUIRED')
    if stage=='validate-clones':need(p['snapshot_manifest_sha256'] is not None,'REVIEWED_SNAPSHOT_DIGEST_REQUIRED')
    return p

def child_limits():
    resource.setrlimit(resource.RLIMIT_FSIZE,(16384,16384))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))

def capture(args,timeout=10):
    # No shell; bounded temporary private output, kill/reap whole child group.
    import tempfile
    with tempfile.TemporaryFile() as out:
        proc=subprocess.Popen(args,stdout=out,stderr=subprocess.DEVNULL,start_new_session=True,preexec_fn=child_limits,env={'PATH':'/usr/bin:/bin'})
        deadline=time.monotonic()+timeout
        while proc.poll() is None:
            if time.monotonic()>deadline or os.fstat(out.fileno()).st_size>16384:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2);raise Hold('COMMAND_UNKNOWN_NO_RETRY')
            time.sleep(.025)
        need(proc.returncode==0 and os.fstat(out.fileno()).st_size<16384,'COMMAND_UNKNOWN_NO_RETRY')
        out.seek(0);return out.read(16385)

def component():
    global _COMPONENT
    if _COMPONENT is None:
        code=read(INSTALL+'/loader.py',65536)
        need(sha(code)=='393b9c3f3e5720a1a9164aaafba0f2198fd5e461c49c4e58859c497ef5100f19','ROOT_LOADER_CHANGED')
        namespace={'__name__':'protected_preparation_loader'}
        exec(compile(code,INSTALL+'/loader.py','exec'),namespace)
        _COMPONENT=namespace['load'](CARRIER_MANIFEST)
    return _COMPONENT

def checkpoint():
    if _ACTIVE is not None:authorize(*_ACTIVE)

def stopped():
    checkpoint()
    c=component()
    need(c.inspect_bound(OLD_ID,OLD_IMAGE)['running'] is False,'FIXED_OLD_NOT_STOPPED')
    try:os.lstat('/run/xuanjun-community-preview/preview.sock')
    except FileNotFoundError:pass
    else:raise Hold('WRITER_SOCKET_STILL_EXISTS')
    # This proves the fixed container only. External writer exclusion comes from
    # separately reviewed root freeze evidence, not from stopped()==True.

def install():
    raw=read(INPUT+'/control-oci2330-v1.zip',111330)
    need(len(raw)==111330 and sha(raw)==CARRIER_SHA,'EXACT_B789_CARRIER')
    z=zipfile.ZipFile(io.BytesIO(raw));names=z.namelist()
    manifest=z.read('manifest.json');need(sha(manifest)==CARRIER_MANIFEST,'CARRIER_MANIFEST')
    m=exact_json(manifest);need(m['install_root']=='/opt/xuanjun-community-preview/control-oci2330-v1' and m['updates_enabled'] is False,'CARRIER_SCOPE')
    need(len(names)==len(set(names)) and set(names)==set(m['files'])|{'manifest.json'},'EXACT_MEMBERS')
    files={}
    for name,meta in m['files'].items():
        body=z.read(name);need(len(body)==meta['bytes'] and sha(body)==meta['sha256'] and meta['uid']==0 and meta['mode']=='0600','CARRIER_FILE')
        need(all(p not in ('','.','..') for p in name.split('/')) and not name.startswith('/'),'CARRIER_PATH')
        files[name]=body
    base=private_parent(BASE)
    try:
        # Both paths must be absent before any installation writes. Never repair
        # an existing or partial deployment or erase a previous attempt.
        for name in ('control-oci2330-v1','update-journal'):
            try:os.stat(name,dir_fd=base,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise Hold('EXISTING_INSTALL_OR_JOURNAL_HOLD')
        space(base,2*len(raw),64)
        root=new_dir(base,'control-oci2330-v1')
        try:
            for name,body in sorted(files.items()):
                parts=name.split('/');fd=os.dup(root)
                try:
                    for part in parts[:-1]:
                        try:child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                        except FileNotFoundError:child=new_dir(fd,part)
                        os.close(fd);fd=child
                    create_file(fd,parts[-1],body)
                finally:os.close(fd)
            create_file(root,'manifest.json',manifest)
        finally:os.close(root)
        fd=new_dir(base,'update-journal');os.close(fd)
    finally:os.close(base)
    return {'stage':'install','carrier_manifest_sha256':CARRIER_MANIFEST,'update_executed':False}

def image_present(fmt,expected):
    # Inspect only the fixed ID. Absence is proven by an EXACT daemon error,
    # never by timeout/exit code/unknown output. All stderr stays internal.
    import tempfile
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc=subprocess.Popen(DOCKER+['image','inspect','--format',fmt,NEW_IMAGE],stdout=out,stderr=err,
            start_new_session=True,preexec_fn=child_limits,env={'PATH':'/usr/bin:/bin'})
        deadline=time.monotonic()+10
        while proc.poll() is None:
            if time.monotonic()>deadline or max(os.fstat(out.fileno()).st_size,os.fstat(err.fileno()).st_size)>4096:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2);raise Hold('IMAGE_INVENTORY_UNKNOWN')
            time.sleep(.025)
        need(max(os.fstat(out.fileno()).st_size,os.fstat(err.fileno()).st_size)<=4096,'IMAGE_INVENTORY_UNKNOWN')
        out.seek(0);err.seek(0);a=out.read(4097).strip();b=err.read(4097).strip()
        if proc.returncode==0:
            need(a==expected and b==b'','EXISTING_IMAGE_CHANGED');return True
        errors=[('Error: No such image: '+NEW_IMAGE).encode(),('Error response from daemon: No such image: '+NEW_IMAGE).encode()]
        need(proc.returncode==1 and a in (b'',b'[]') and b in errors,'IMAGE_INVENTORY_UNKNOWN')
        return False

def daemon_capacity():
    # Metadata only, original Docker socket. Never list/read Docker data or Env.
    # Do not guess a storage root or assume an unobserved containerd backend.
    fmt='{"root":{{json .DockerRootDir}},"driver":{{json .Driver}}}'
    value=exact_json(capture(DOCKER+['info','--format',fmt]))
    need(type(value) is dict and set(value)=={'root','driver'} and value['driver']=='overlay2'
        and type(value['root']) is str and 1<len(value['root'])<=4096,'DOCKER_STORAGE_METADATA_UNKNOWN')
    root=value['root'];device=None
    for path in (root,root+'/overlay2',root+'/image/overlay2',root+'/tmp'):
        fd=directory(path)
        try:
            info=os.fstat(fd);need(info.st_uid==UID,'ROOT_DOCKER_STORAGE_REQUIRED')
            if device is None:device=info.st_dev
            need(info.st_dev==device,'SEPARATE_DOCKER_STORAGE_HOLD')
            space(fd,3*LAYER_TAR_BYTES,4*LAYER_ENTRIES)
        finally:os.close(fd)
    need(exact_json(capture(DOCKER+['info','--format',fmt]))==value,'DOCKER_STORAGE_CHANGED')

def image_load():
    need(time.time()<EXPIRES,'F131_ARTIFACT_EXPIRED')
    raw=read(INPUT+'/artifact12546452389.zip',57016858)
    need(len(raw)==57016858 and sha(raw)==OUTER_SHA,'OUTER_ARTIFACT')
    z=zipfile.ZipFile(io.BytesIO(raw));infos=z.infolist()
    need(len(infos)==len({x.filename for x in infos}) and sum(x.file_size for x in infos)<=60000000,'IMAGE_ZIP_BOUND')
    body=z.read('community-backend-image.tar.gz')
    need(len(body)==57365044 and sha(body)==INNER_SHA,'INNER_IMAGE_ARCHIVE')
    # Digest fixes every layer/config/stamp byte independently reviewed by root.
    # Never use verify image, URL/pull/tag, Docker daemon defaults or a new image.
    fmt='{{.Id}}|{{.Architecture}}|{{.Os}}|{{.Config.User}}|{{index .Config.Labels "org.opencontainers.image.revision"}}'
    expected='|'.join((NEW_IMAGE,'amd64','linux','10001:1008',PRODUCT)).encode()
    return _load_fixed_archive(body,fmt,expected)

def _load_fixed_archive(body,fmt,expected):
    # If inspection cannot establish absence/presence, HOLD. A reviewed explicit
    # root observation selects loading; CLI errors alone never mean NOT_FOUND.
    parent=private_parent(INPUT)
    try:
        existing=image_present(fmt,expected)
        if existing:return {'stage':'image-load','image':NEW_IMAGE,'existing_exact_image_reused':True,'service_changed':False}
        checkpoint()
        daemon_capacity();space(parent,2*57365044,64)
        create_file(parent,'community-backend-image.tar.gz',body)
        create_file(parent,'image-load-intent.json',canonical({'image':NEW_IMAGE,'archive_sha256':INNER_SHA}))
        # EXCL intent prevents an uncertain/partial import from being repeated.
        capture(DOCKER+['image','load','--input',INPUT+'/community-backend-image.tar.gz'],timeout=120)
        need(capture(DOCKER+['image','inspect','--format',fmt,NEW_IMAGE]).strip()==expected,'LOADED_IMAGE_UNKNOWN')
        create_file(parent,'image-load-observed.json',canonical({'image':NEW_IMAGE,'source':PRODUCT,'loaded_at':int(time.time())}))
    finally:os.close(parent)
    return {'stage':'image-load','image':NEW_IMAGE,'service_changed':False}

def bounded_names(fd):
    names=[]
    # fd-based scandir is required from the existing interpreter; absence HOLDs
    # before writes. No path expansion or unbounded listdir allocation.
    with os.scandir(fd) as rows:
        for row in rows:
            need(len(names)<MAX_FILES,'TREE_COUNT');names.append(row.name)
    return sorted(names)

def tree(source,destination=None):
    """Whole fixed tree, dirfd/no-follow, streaming bounds; preserve owners/modes.

    Contents/relative filenames remain private. Never follows links or excludes
    WAL, keys, Center objects or an unknown filename. Other mounts are refused.
    """
    result={};counter=[0,0,0];start=time.monotonic();dev=os.fstat(source).st_dev
    def walk(src,dst,prefix,depth):
        need(depth<=32 and time.monotonic()-start<120,'TREE_DEPTH_OR_TIMEOUT')
        before=os.fstat(src);need(before.st_uid in (UID,10001) and before.st_gid in ALLOWED_GIDS and stat.S_IMODE(before.st_mode)==0o700,'PRIVATE_TREE_ROOT');names=bounded_names(src);need(len(names)<=MAX_FILES,'TREE_COUNT')
        for name in names:
            need(name not in ('.','..') and '/' not in name and len(os.fsencode(name))<=255,'TREE_NAME')
            s=os.stat(name,dir_fd=src,follow_symlinks=False);mode=stat.S_IMODE(s.st_mode)
            need(s.st_dev==dev and s.st_uid in (UID,10001) and s.st_gid in ALLOWED_GIDS and not mode&0o077 and not mode&0o7000,'PRIVATE_TREE_METADATA')
            counter[0]+=1;need(counter[0]<=MAX_FILES,'TREE_COUNT')
            if counter[0]%300==0:checkpoint()
            key=prefix+name
            need(len(os.fsencode(key))<=1024,'TREE_RELATIVE_PATH_LIMIT')
            counter[2]+=12*len(os.fsencode(key))+512
            need(counter[2]<=3*1024**2,'TREE_MANIFEST_BUDGET')
            if stat.S_ISDIR(s.st_mode):
                f=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=src);out=None
                try:
                    need(identity(s)==identity(os.fstat(f)),'TREE_CHANGED')
                    if dst is not None:out=new_dir(dst,name)
                    result[key]={'type':'directory','uid':s.st_uid,'gid':s.st_gid,'mode':mode}
                    walk(f,out,key+'/',depth+1)
                    if out is not None:os.fchown(out,s.st_uid,s.st_gid);os.fchmod(out,mode);os.fsync(out)
                finally:
                    os.close(f)
                    if out is not None:os.close(out)
            else:
                need(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'TREE_LINK_OR_SPECIAL')
                counter[1]+=s.st_size;need(counter[1]<=MAX_BYTES,'TREE_BYTES')
                f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=src);out=None
                try:
                    need(identity(s)==identity(os.fstat(f)),'TREE_CHANGED');h=hashlib.sha256();total=0
                    if dst is not None:out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=dst)
                    while True:
                        need(time.monotonic()-start<120,'TREE_TIMEOUT');b=os.read(f,1048576)
                        if not b:break
                        total+=len(b);need(total<=s.st_size,'TREE_CHANGED');h.update(b)
                        if out is not None:
                            view=memoryview(b)
                            while view:n=os.write(out,view);need(n>0,'WRITE_FAILED');view=view[n:]
                    need(total==s.st_size and identity(s)==identity(os.fstat(f)),'TREE_CHANGED')
                    result[key]={'type':'file','uid':s.st_uid,'gid':s.st_gid,'mode':mode,'bytes':total,'sha256':h.hexdigest()}
                    if out is not None:os.fchown(out,s.st_uid,s.st_gid);os.fchmod(out,mode);os.fsync(out)
                finally:
                    os.close(f)
                    if out is not None:os.close(out)
            need(identity(s)==identity(os.stat(name,dir_fd=src,follow_symlinks=False)),'TREE_REPLACED')
        need(names==bounded_names(src) and identity(before)==identity(os.fstat(src)),'DIRECTORY_CHANGED')
        if dst is not None:os.fsync(dst)
    walk(source,destination,'',0)
    root=os.fstat(source)
    return {'entries':result,'bytes':counter[1],'count':counter[0],
            'root':{'uid':root.st_uid,'gid':root.st_gid,'mode':stat.S_IMODE(root.st_mode)}}

def copy_roots(src,dst):
    records={}
    for name in ('data','config'):
        checkpoint()
        source=directory(src+'/'+name);target=None
        try:
            if dst is not None:
                parent=private_parent(dst)
                try:target=new_dir(parent,name)
                finally:os.close(parent)
            records[name]=tree(source,target)
            if target is not None:
                s=os.fstat(source);os.fchown(target,s.st_uid,s.st_gid);os.fchmod(target,stat.S_IMODE(s.st_mode));os.fsync(target)
        finally:
            os.close(source)
            if target is not None:os.close(target)
    return records

def snapshot(permit):
    stopped();records=copy_roots(DATA,None);base=private_parent(BASE)
    try:
        space(base,7*sum(x['bytes'] for x in records.values()),7*sum(x['count'] for x in records.values()))
        root=new_dir(base,'backup-2330-to-f131-v1')
        try:target=new_dir(root,'snapshot');os.close(target)
        finally:os.close(root)
    finally:os.close(base)
    stopped();need(copy_roots(DATA,BACKUP+'/snapshot')==records,'SNAPSHOT_COPY_CHANGED')
    stopped();need(copy_roots(DATA,None)==records,'SOURCE_CHANGED_DURING_SNAPSHOT')
    need(copy_roots(BACKUP+'/snapshot',None)==records,'SNAPSHOT_READBACK_CHANGED')
    raw=canonical({'format':1,'old_id':OLD_ID,'old_image':OLD_IMAGE,'product_image':NEW_IMAGE,
        'all_writers_frozen_evidence_sha256':permit['all_writers_frozen_evidence_sha256'],'trees':records})
    need(len(raw)<=8*1024*1024,'MANIFEST_LIMIT')
    parent=private_parent(BACKUP)
    try:create_file(parent,'private-manifest.json',raw)
    finally:os.close(parent)
    return {'stage':'snapshot','manifest_sha256':sha(raw),'bytes':sum(x['bytes'] for x in records.values()),
            'recovery_verified':False,'downgrade_verified':False}

# Actual original PlatformHost, no listen/provider calls/identity writes/grants.
# Only clone volumes and no network. Exceptions/DB paths/contents are suppressed.
CLONE_CODE=r'''import hashlib,json,os
from pathlib import Path
from scripts.community_platform_host import PlatformHost
try:
 h=PlatformHost.open('/var/lib/xuanjun-community-preview/config/host.json','/var/lib/xuanjun-community-preview/config/center-keys.json','/var/lib/xuanjun-community-preview/config/wechat.json')
 try:
  dbs=[h.center.db]+list(h.persistence.handles)
  for db in dbs:
   assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
   assert not db.execute('PRAGMA foreign_key_check').fetchall()
  h.center.check_integrity()
  records=[]
  for db in dbs:
   rows=[]
   tables=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
   for table in tables:
    q='"'+table.replace('"','""')+'"';chunks=[]
    for row in db.execute('SELECT * FROM '+q):
     def encode(v):return {'bytes':v.hex()} if isinstance(v,bytes) else v
     chunks.append(hashlib.sha256(json.dumps([encode(v) for v in row],sort_keys=True,separators=(',',':')).encode()).hexdigest())
    rows.append([table,len(chunks),hashlib.sha256(''.join(sorted(chunks)).encode()).hexdigest()])
   records.append(rows)
  print(json.dumps({'format':1,'original_host_open':True,'center_integrity':True,'stores':records},sort_keys=True,separators=(',',':')))
 finally:h.close()
except BaseException:raise SystemExit(2)
'''

def clone_run(name,image):
    checkpoint()
    need(name in ('restore-old','verify-f131','verify-downgrade') and image in (OLD_IMAGE,NEW_IMAGE),'FIXED_CLONE_ONLY')
    args=DOCKER+['run','--rm','--name','xuanjun-community-preview-'+name+'-probe-f131','--network','none','--user','10001:1008','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--pids-limit','64','--memory','384m','--memory-swap','384m','--cpus','0.5',
        '--pull','never','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777',
        '--mount','type=bind,src='+BACKUP+'/'+name+'/data,dst='+DATA+'/data',
        '--mount','type=bind,src='+BACKUP+'/'+name+'/config,dst='+DATA+'/config,readonly',
        '--entrypoint','/usr/local/bin/python',image,'-B','-c',CLONE_CODE]
    return exact_json(capture(args,120))

def validate_clones(permit):
    raw=read(BACKUP+'/private-manifest.json',8*1024*1024)
    need(sha(raw)==permit['snapshot_manifest_sha256'],'SNAPSHOT_MANIFEST_CHANGED');m=exact_json(raw)
    need(set(m)=={'format','old_id','old_image','product_image','all_writers_frozen_evidence_sha256','trees'}
         and m['format']==1 and m['old_id']==OLD_ID and m['old_image']==OLD_IMAGE and m['product_image']==NEW_IMAGE,'SNAPSHOT_SCOPE')
    need(copy_roots(BACKUP+'/snapshot',None)==m['trees'],'SNAPSHOT_CHANGED')
    parent=private_parent(BACKUP)
    try:
        space(parent,6*sum(t['bytes'] for t in m['trees'].values()),6*sum(t['count'] for t in m['trees'].values()))
        # A partial/existing clone is never reused after an ambiguous run.
        for name in ('restore-old','verify-f131','verify-downgrade'):
            try:os.stat(name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise Hold('EXISTING_CLONE_HOLD')
        for name in ('restore-old','verify-f131'):
            fd=new_dir(parent,name);os.close(fd)
            need(copy_roots(BACKUP+'/snapshot',BACKUP+'/'+name)==m['trees'],'CLONE_COPY_CHANGED')
        old=clone_run('restore-old',OLD_IMAGE)
        new=clone_run('verify-f131',NEW_IMAGE)
        fd=new_dir(parent,'verify-downgrade');os.close(fd)
        migrated=copy_roots(BACKUP+'/verify-f131',None)
        need(copy_roots(BACKUP+'/verify-f131',BACKUP+'/verify-downgrade')==migrated,'MIGRATED_COPY_CHANGED')
        down=clone_run('verify-downgrade',OLD_IMAGE)
        # Strict full logical-row comparison; any migration/additional metadata
        # needing interpretation is HOLD, not a relaxed count-only PASS.
        need(old==new==down and old.get('original_host_open') is True and old.get('center_integrity') is True,'RESTORE_OR_DOWNGRADE_REVIEW_REQUIRED')
        need(copy_roots(BACKUP+'/snapshot',None)==m['trees'],'SNAPSHOT_CHANGED')
        result={'stage':'validate-clones','snapshot_manifest_sha256':sha(raw),'logical_evidence_sha256':sha(canonical(old)),
            'tested_at':int(time.time()),'restore_original_host':True,'downgrade_logical_equality':True,
            'production_acceptance':False,'rollback_health_acceptance':False}
        create_file(parent,'clone-results.json',canonical(result))
        return result
    finally:os.close(parent)

def main(argv=None):
    global _ACTIVE
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=STAGES);parser.add_argument('--approval-sha256')
    args=parser.parse_args(argv)
    if args.stage is None:
        print('{"state":"PREPARATION_DEFAULT_DISABLED","site_executed":false}');return 2
    # Authorize twice, after waiting on exclusive process lock. Lock is on the
    # fixed protected entry inode; never invent a new daemon or authority.
    permit=authorize(args.stage,args.approval_sha256)
    parent=private_parent(BASE)
    fd=os.open('site-prepare-v1.py',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        need(os.fstat(fd).st_ino==os.stat('site-prepare-v1.py',dir_fd=parent,follow_symlinks=False).st_ino,'ENTRY_REPLACED')
        permit=authorize(args.stage,args.approval_sha256)
        _ACTIVE=(args.stage,args.approval_sha256)
        result={'install':install,'image-load':image_load,'snapshot':lambda:snapshot(permit),
                'validate-clones':lambda:validate_clones(permit)}[args.stage]()
        print(json.dumps(result,sort_keys=True));return 0
    finally:_ACTIVE=None;os.close(fd);os.close(parent)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        # Never leak secret filenames, configuration, DB error payloads or
        # Docker output. Preserve all partial files; inspect, never blind retry.
        reason=str(error) if type(error) is Hold and re.fullmatch('[A-Z_]{1,96}',str(error)) else 'PROTECTED_BOUNDARY_UNKNOWN'
        print(json.dumps({'state':'HOLD_INSPECT_PRESERVED_ATTEMPT','reason':reason,'site_update_executed':False}));raise SystemExit(2)
