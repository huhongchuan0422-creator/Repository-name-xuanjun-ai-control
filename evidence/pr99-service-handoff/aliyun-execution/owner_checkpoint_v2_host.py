CHUNK_HASHES=['ed365f253ab5b6326970d533f6bb8cfa801937aaf52560f4b13939a898035119', 'dbd87c0f9eee6ae7684c0af4185739311d7149151d6c8de35d12e4f03b798405', '31f5af664e2b4e9d4c2fbbd8dd19a62c236f920574edac5f9d36e97b1282ce1c']
PREFIX_HASHES=['e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'ed365f253ab5b6326970d533f6bb8cfa801937aaf52560f4b13939a898035119', '84a4849cf01629a1f70a48d87dcb1a68959e0b7328f3c6fce5bc7baf4661df35', '5f4cf2f5be4646054f8dc0a13fc1b7862f5e95ff7b7a6b39ba1e63faa00183b8']
"""Install the hash-pinned, inert Owner start helper. No activation or data copy."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import urllib.request

PARENT=Path('/opt/xuanjun-migration-s07/bin/owner-start-v2')
TARGET=PARENT/'owner_production_start.py'
SOURCE_SHA='5f4cf2f5be4646054f8dc0a13fc1b7862f5e95ff7b7a6b39ba1e63faa00183b8'
SOURCE_URL='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/370cc24a4b8c07dc0100ff2c89f9dd6e53a0c243/evidence/pr99-service-handoff/owner-start/owner_production_start.py'
PROTECTED=('nginx.service','provider-neutral-domestic-bridge.service','windows-interaction-http.service')


def need(ok,code):
    if not ok:raise RuntimeError(code)


def states():
    result={}
    for name in PROTECTED:
        p=subprocess.run(['/usr/bin/systemctl','show',name,'--property=LoadState,ActiveState,SubState,MainPID','--no-pager'],capture_output=True,timeout=10)
        need(p.returncode==0 and len(p.stdout)<=8192,'PROTECTED_STATE_UNKNOWN')
        result[name]=p.stdout.decode('utf-8','strict')
    return result


def stage_file(directory,raw):
    need(hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'START_SOURCE_DRIFT')
    d=directory.lstat()
    need(stat.S_ISDIR(d.st_mode) and d.st_uid==os.geteuid() and not d.st_mode&0o022,'CODE_DIRECTORY_IDENTITY')
    target=directory/'owner_production_start.py';created=False
    if not os.path.lexists(target):
        fd=os.open(target,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            offset=0
            while offset<len(raw):
                size=os.write(fd,raw[offset:]);need(size>0,'PARTIAL_CODE_PRESERVE');offset+=size
            os.fsync(fd);need(os.pread(fd,len(raw)+1,0)==raw,'CODE_WRITE_DRIFT')
            os.fchmod(fd,0o400);os.fsync(fd)
        finally:os.close(fd)
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
        created=True
    fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.geteuid() and
             stat.S_IMODE(before.st_mode)==0o400 and before.st_size==len(raw),'EXISTING_CODE_IDENTITY_CONFLICT')
        observed=os.read(fd,len(raw)+1);after=os.fstat(fd)
        need(observed==raw and (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_ctime_ns)==
             (after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns),'EXISTING_CODE_BYTES_CONFLICT')
    finally:os.close(fd)
    return created


TRANSFER=PARENT/'owner_production_start.py.transfer-v1'

def receive(directory,index,chunk):
    need(type(index)is int and 0<=index<3,'PART_INDEX')
    need(hashlib.sha256(chunk).hexdigest()==CHUNK_HASHES[index],'PART_SOURCE_DRIFT')
    s=directory.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and not s.st_mode&0o022,'CODE_DIRECTORY_IDENTITY')
    path=directory/TRANSFER.name
    flags=os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open(path,flags|(os.O_CREAT|os.O_EXCL if index==0 else 0),0o600)
    try:
        s=os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'PART_FILE_IDENTITY')
        prior=os.pread(fd,34426,0)
        need(len(prior)==index*11500 and hashlib.sha256(prior).hexdigest()==PREFIX_HASHES[index],'PART_PRIOR_CONFLICT_PRESERVE')
        need(os.lseek(fd,0,os.SEEK_END)==len(prior),'PART_OFFSET')
        off=0
        while off<len(chunk):
            size=os.write(fd,chunk[off:]);need(size>0,'PARTIAL_CODE_PRESERVE');off+=size
        os.fsync(fd)
        raw=os.pread(fd,34426,0)
        need(raw==prior+chunk,'PART_WRITE_DRIFT_PRESERVE')
    finally:os.close(fd)
    if index==2:
        need(len(raw)==34425 and hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'FINAL_SOURCE_DRIFT')
        stage_file(directory,raw)
        ns={'__name__':'installed_owner_start_definitions','__file__':str(directory/'owner_production_start.py')}
        exec(compile(raw,ns['__file__'],'exec'),ns)
        need(len(ns['units']('xuanjun-s07'))==3,'FINAL_DEFINITION_BINDING')
    return len(raw),hashlib.sha256(raw).hexdigest()

def observe(expected,nonce):
    need(os.geteuid()==0 and os.uname().nodename==expected=='iZvt5t8tlrm8oiZ','FIXED_DOMESTIC_ROOT')
    before=states()
    for parent in reversed(PARENT.parents):
        s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'CODE_PARENT_IDENTITY')
    if not os.path.lexists(PARENT):PARENT.mkdir(mode=0o700)
    size,digest=receive(PARENT,PART,CHUNK)
    need(before==states(),'PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')
    return {'scope':'PR99_INLINE_OWNER_HELPER_ONLY','hostname':expected,'nonce':nonce,'part':PART,
      'prefix_bytes':size,'prefix_sha256':digest,'final_installed':PART==2,'source_sha256':SOURCE_SHA,
      'protected_state_unchanged':True,'service_actions':0,'production_started':False,'route_changed':False}

if __name__=='__main__':
    try:print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
    except BaseException as error:
        import re
        code=str(error)
        print(json.dumps({'status':'OWNER_INLINE_STAGE_HOLD','error_type':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,160}',code) else 'PRIVATE_DETAIL_WITHHELD','retry_allowed':False}),flush=True)
        raise SystemExit(2)
