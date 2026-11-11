"""Bounded real kernel immutable/recovery capability, never a production fence."""
from array import array
import datetime
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile

HOST='iZ6wee8q9z4t03hvqumwfhZ'
IMMUTABLE=0x10
GETFLAGS=(2<<30)|(struct.calcsize('l')<<16)|(ord('f')<<8)|1
SETFLAGS=(1<<30)|(struct.calcsize('l')<<16)|(ord('f')<<8)|2
PAYLOAD=b'PR99 inert kernel fence capability fixture v1\n'

def need(ok,code):
    if not ok:raise RuntimeError(code)

def get_flags(fd):
    value=array('l',[0]);fcntl.ioctl(fd,GETFLAGS,value,True);return value[0]

def set_flags(fd,value):
    fcntl.ioctl(fd,SETFLAGS,array('l',[value]),False)
    need(get_flags(fd)==value,'FLAG_RESULT_UNKNOWN')

def identity(fd):
    s=os.fstat(fd);return s.st_dev,s.st_ino,s.st_uid

def rejected(call):
    try:call()
    except OSError as error:
        need(error.errno==errno.EPERM,'EXPECTED_KERNEL_EPERM');return True
    raise RuntimeError('KERNEL_WRITE_NOT_BLOCKED')

def capability(directory,filesystem_device,read_flags=get_flags,write_flags=set_flags):
    directory=Path(directory);ds=directory.lstat()
    need(stat.S_ISDIR(ds.st_mode) and ds.st_uid==os.geteuid() and stat.S_IMODE(ds.st_mode)==0o700 and ds.st_dev==filesystem_device,'PRIVATE_SAME_FILESYSTEM_REQUIRED')
    dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    fd=None;file_flags=directory_flags=None;restored=False
    try:
        fd=os.open('held-write.fixture',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=dfd)
        need(os.write(fd,PAYLOAD)==len(PAYLOAD),'FIXTURE_WRITE');os.fsync(fd)
        original=identity(fd);directory_identity=identity(dfd)
        file_flags=read_flags(fd);directory_flags=read_flags(dfd)
        need(not(file_flags|directory_flags)&IMMUTABLE,'NEW_FIXTURE_ALREADY_IMMUTABLE')
        write_flags(fd,file_flags|IMMUTABLE)
        held_write_blocked=rejected(lambda:os.pwrite(fd,b'X',0))
        unlink_blocked=rejected(lambda:os.unlink('held-write.fixture',dir_fd=dfd))
        need(os.pread(fd,len(PAYLOAD)+1,0)==PAYLOAD,'FROZEN_FIXTURE_DRIFT')
        write_flags(dfd,directory_flags|IMMUTABLE)
        def create_child():
            child=os.open('unexpected-child.fixture',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=dfd)
            os.close(child)
        create_blocked=rejected(create_child)
        need(identity(fd)==original and identity(dfd)==directory_identity,'FIXTURE_IDENTITY_DRIFT')
        write_flags(dfd,directory_flags);write_flags(fd,file_flags)
        need(os.pwrite(fd,PAYLOAD[:1],0)==1,'RESTORED_WRITE_FAILED');os.fsync(fd)
        need(os.pread(fd,len(PAYLOAD)+1,0)==PAYLOAD,'RESTORED_BYTES_DRIFT')
        restored=True
        return {'held_writable_fd_write_blocked':held_write_blocked,'file_unlink_blocked':unlink_blocked,
          'directory_create_blocked':create_blocked,'original_flags_restored':True,'write_after_restore_pass':True,
          'same_filesystem_as_project_root':True,'fixture_bytes':len(PAYLOAD),'filesystem_device':filesystem_device}
    finally:
        # Compensation only for these exact owned test descriptors; never touch
        # application flags or paths. Failed restoration retains the fixture.
        if not restored:
            if directory_flags is not None:write_flags(dfd,directory_flags)
            if fd is not None and file_flags is not None:write_flags(fd,file_flags)
        if fd is not None:os.close(fd)
        os.close(dfd)

def observe(expected,nonce):
    need(os.geteuid()==0 and os.uname().nodename==expected==HOST,'FIXED_TOKYO_ROOT')
    device=os.stat('/opt/trading-system').st_dev
    need(os.stat('/var/lib').st_dev==device,'TEST_FILESYSTEM_DIFFERENT_NO_MUTATION')
    directory=Path(tempfile.mkdtemp(prefix='pr99-native-fence-capability-',dir='/var/lib'))
    completed=False
    try:
        result=capability(directory,device)
        need(set(os.listdir(directory))=={'held-write.fixture'},'FIXTURE_CLEANUP_MEMBERSHIP')
        s=directory.lstat();need(s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'FIXTURE_CLEANUP_IDENTITY')
        (directory/'held-write.fixture').unlink();directory.rmdir();completed=True
        return {'scope':'PR99_NATIVE_FENCE_CAPABILITY_ONLY_NOT_SOURCE_FENCED','hostname':expected,'nonce':nonce,
          'observed_at':datetime.datetime.utcnow().isoformat()+'Z','result':result,'fixture_cleaned':True,
          'source_data_selected':False,'source_writer_stopped':False,'production_fence_enforced':False,
          'database_opened':False,'service_actions':0,'writer_acquired':False,'route_changed':False}
    finally:
        # No recursive deletion or retry on failure. Only success cleans exact fixtures.
        if not completed:pass

if __name__=='__main__':
    try:print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
    except BaseException as error:
        code=str(error)
        import re
        print(json.dumps({'status':'NATIVE_FENCE_CAPABILITY_HOLD','exception':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,160}',code) else 'PRIVATE_DETAIL_WITHHELD',
          'errno':getattr(error,'errno',None),'retry_allowed':False}),flush=True)
        raise SystemExit(2)
