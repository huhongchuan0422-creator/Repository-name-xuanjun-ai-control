"""Install the hash-pinned, inert Owner start helper. No activation or data copy."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import urllib.request

PARENT=Path('/opt/xuanjun-migration-s07/bin')
TARGET=PARENT/'owner_production_start.py'
SOURCE_SHA='7936650e5911f71216c1dfe1873754bcf09ddac45894df3214018dd5f21ace40'
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


def observe(expected,nonce):
    need(os.geteuid()==0 and os.uname().nodename==expected=='iZvt5t8tlrm8oiZ','FIXED_DOMESTIC_ROOT')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw):return None
    with urllib.request.build_opener(NoRedirect()).open(SOURCE_URL,timeout=20) as response:raw=response.read(34426)
    need(len(raw)==34425 and hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'START_SOURCE_DRIFT')
    before=states()
    for parent in reversed(PARENT.parents):
        s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'CODE_PARENT_IDENTITY')
    directory_created=False
    if not os.path.lexists(PARENT):PARENT.mkdir(mode=0o700);directory_created=True
    created=stage_file(PARENT,raw)
    ns={'__name__':'installed_owner_start_definitions','__file__':str(TARGET)}
    exec(compile(raw,str(TARGET),'exec'),ns)
    unit_bytes=ns['units']('xuanjun-s07')
    need(len(unit_bytes)==3 and all(b'User=xuanjun-s07' in b and b'domestic-final-v1/rootfs' in b for b in unit_bytes.values()),'INSTALLED_START_DEFINITION_BINDING')
    need(before==states(),'PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')
    return {'scope':'PR99_STAGE_OWNER_START_PROGRAM_ONLY','hostname':expected,'nonce':nonce,
      'observed_at':datetime.datetime.utcnow().isoformat()+'Z','path':str(TARGET),'source_sha256':SOURCE_SHA,
      'bytes':len(raw),'mode':0o400,'created':created,'directory_created':directory_created,'compiled':True,
      'protected_state_unchanged':True,'service_actions':0,'start_called':False,'writer_acquired':False,
      'production_data_copied':False,'production_started':False,'route_changed':False,
      'production_state_exists':os.path.lexists('/var/lib/xuanjun-pr99-s09-production-start-v1')}


if __name__=='__main__':
    try:print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
    except BaseException as error:
        import re
        code=str(error)
        print(json.dumps({'status':'OWNER_START_STAGE_HOLD','error_type':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,160}',code) else 'PRIVATE_DETAIL_WITHHELD','retry_allowed':False}),flush=True)
        raise SystemExit(2)
