"""Fixed installer for the reviewed STOPPED_HANDOFF_V1 carrier.

Source-only candidate.  No package is installed at import.  The production CLI only
accepts the frozen carrier bytes and publishes one new fixed directory atomically.
"""
import argparse
import ctypes
import errno
import hashlib
import io
import json
import os
import pwd
import re
import stat
import zipfile

HOST='iZd7oeikknn1z21sq6ji6zZ'
PARENT='/opt/xuanjun-community-preview'
TARGET='control-stopped-v1'
INSTALL_ROOT=PARENT+'/'+TARGET
MODE='STOPPED_HANDOFF_V1'
ARCHIVE_SHA256='5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4'
MANIFEST_SHA256='e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a'
MAX_ARCHIVE=4*1024*1024
MAX_FILE=131072
TEMP=TARGET+'.installing-'+ARCHIVE_SHA256[:16]

class Hold(RuntimeError):
    def __init__(self,reason,publish_attempted=False,temp_identity=None,parent_fsync_completed=False):
        self.reason=reason if type(reason) is str and reason else 'INSTALL_HOLD'
        self.publish_attempted=bool(publish_attempted)
        self.temp_identity=temp_identity
        self.parent_fsync_completed=bool(parent_fsync_completed)
        super().__init__(self.reason)

class PublishedUnknown(Hold):
    def __init__(self,reason,parent_fsync_completed,temp_identity=None,temp_identity_sha256=None):
        super().__init__('V2_INSTALL_PUBLISHED_UNKNOWN',True,temp_identity,parent_fsync_completed)
        self.detail=reason if type(reason) is str and reason else 'POST_PUBLISH_UNKNOWN'
        digest=identity_digest(temp_identity) if temp_identity_sha256 is None else temp_identity_sha256
        if digest is not None and (type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None):
            raise ValueError('TEMP_IDENTITY_DIGEST_REQUIRED')
        self.temp_identity_sha256=digest
        self.target_published=True
        self.retry_safe=False
    def record(self):
        return {'state':'V2_INSTALL_PUBLISHED_UNKNOWN','reason':self.detail,'publish_attempted':True,
                'temp_identity_sha256':self.temp_identity_sha256,'target_published':True,
                'retry_safe':False,'parent_fsync_completed':self.parent_fsync_completed,
                'install_root':INSTALL_ROOT,'archive_sha256':ARCHIVE_SHA256,
                'manifest_sha256':MANIFEST_SHA256,'site_executed':False,'bc_executed':False}

def need(ok,why):
    if not ok:raise Hold(why)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def read_exact_fd(fd,limit):
    st=os.fstat(fd)
    need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and 0<st.st_size<=limit,'INPUT_REGULAR_SINGLE_LINK_REQUIRED')
    before=(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    chunks=[];total=0
    while True:
        b=os.read(fd,min(1048576,limit-total+1))
        if not b:break
        total+=len(b);need(total<=limit,'INPUT_OVERSIZE');chunks.append(b)
    after=os.fstat(fd)
    identity=(after.st_dev,after.st_ino,after.st_mode,after.st_uid,after.st_gid,after.st_nlink,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
    need(total==st.st_size and identity==before,'INPUT_CHANGED')
    return b''.join(chunks)

def open_input(path,limit):
    need(type(path) is str and os.path.isabs(path),'ABSOLUTE_INPUT_PATH_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and not (stat.S_IMODE(st.st_mode)&0o022),'PROTECTED_INPUT_FILE_REQUIRED')
        return read_exact_fd(fd,limit)
    finally:os.close(fd)

def manifest_value(raw):
    need(sha(raw)==MANIFEST_SHA256,'FIXED_MANIFEST_SHA_REQUIRED')
    try:value=json.loads(raw)
    except (ValueError,UnicodeError):raise Hold('MANIFEST_JSON_REQUIRED') from None
    need(raw==canonical(value),'CANONICAL_MANIFEST_REQUIRED')
    need(type(value) is dict and set(value)=={'format','mode','install_root','files','updates_enabled'}
         and type(value['format']) is int and value['format']==1 and value['mode']==MODE
         and value['install_root']==INSTALL_ROOT and value['updates_enabled'] is False
         and type(value['files']) is dict,'EXACT_MANIFEST_REQUIRED')
    for name,meta in value['files'].items():
        need(safe_member(name) and name!='manifest.json','MANIFEST_PATH_REQUIRED')
        need(type(meta) is dict and set(meta)=={'bytes','sha256','uid','mode'}
             and type(meta['bytes']) is int and 0<meta['bytes']<=MAX_FILE
             and type(meta['sha256']) is str and re.fullmatch('[0-9a-f]{64}',meta['sha256'])
             and type(meta['uid']) is int and meta['uid']==0 and meta['mode']=='0600','MANIFEST_ENTRY_REQUIRED')
    return value

def safe_member(name):
    if type(name) is not str or not name or '\\' in name or name.startswith('/') or name.endswith('/'):
        return False
    parts=name.split('/')
    return all(p not in ('','.','..') and '/' not in p for p in parts)

def validate_archive_contents(archive,manifest_raw):
    manifest=manifest_value(manifest_raw)
    expected=set(manifest['files'])|{'manifest.json'}
    try:z=zipfile.ZipFile(io.BytesIO(archive),'r')
    except (zipfile.BadZipFile,ValueError):raise Hold('VALID_ZIP_REQUIRED') from None
    with z:
        infos=z.infolist();names=[i.filename for i in infos]
        need(len(names)==len(set(names)),'DUPLICATE_MEMBER_DENIED')
        need(set(names)==expected,'EXACT_ARCHIVE_MEMBER_SET_REQUIRED')
        bodies={}
        for info in infos:
            name=info.filename;need(safe_member(name),'UNSAFE_MEMBER_PATH')
            need(info.compress_type==zipfile.ZIP_DEFLATED,'DEFLATED_MEMBER_REQUIRED')
            mode=(info.external_attr>>16)&0xffff
            need(stat.S_IFMT(mode)==stat.S_IFREG and stat.S_IMODE(mode)==0o600,'REGULAR_0600_MEMBER_REQUIRED')
            need(0<info.file_size<=MAX_FILE and info.compress_size<=MAX_ARCHIVE,'MEMBER_SIZE_REQUIRED')
            raw=z.read(info);need(len(raw)==info.file_size,'MEMBER_TRUNCATED')
            if name=='manifest.json':need(raw==manifest_raw,'ZIP_MANIFEST_MISMATCH')
            else:
                meta=manifest['files'][name]
                need(len(raw)==meta['bytes'] and sha(raw)==meta['sha256'],'MEMBER_HASH_MISMATCH')
            bodies[name]=raw
    return manifest,bodies

def validate_archive(archive,manifest_raw):
    need(sha(archive)==ARCHIVE_SHA256,'FIXED_ARCHIVE_SHA_REQUIRED')
    return validate_archive_contents(archive,manifest_raw)

def _identity(st):return (st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def identity_digest(value):
    if value is None:return None
    return sha(canonical(list(value)))

def parent_identity(st):
    return (st.st_dev,st.st_ino,stat.S_IFMT(st.st_mode),st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))

def verify_parent(fd,root_uid=0):
    st=os.fstat(fd)
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==root_uid and not (stat.S_IMODE(st.st_mode)&0o022),'PROTECTED_INSTALL_PARENT_REQUIRED')
    return parent_identity(st)

def absent(parent,name):
    try:os.stat(name,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return
    raise Hold('TARGET_OR_PARTIAL_ALREADY_EXISTS')

def mkdir_owned(parent,name,root_uid=0,root_gid=0):
    os.mkdir(name,0o700,dir_fd=parent)
    fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        os.fchown(fd,root_uid,root_gid);os.fchmod(fd,0o700);os.fsync(fd)
        need(stat.S_IMODE(os.fstat(fd).st_mode)==0o700,'PRIVATE_DIRECTORY_MODE_REQUIRED')
        return fd
    except BaseException:os.close(fd);raise

def write_owned(parent,name,body,root_uid=0,root_gid=0):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
    try:
        os.fchown(fd,root_uid,root_gid);os.fchmod(fd,0o600)
        view=memoryview(body)
        while view:
            n=os.write(fd,view);need(n>0,'WRITE_FAILED');view=view[n:]
        os.fsync(fd)
    finally:os.close(fd)

def create_tree(root,bodies,root_uid=0,root_gid=0,fault=None):
    dirs={'scripts','deploy','deploy/community-preview'}
    fds={'':root}
    try:
        for rel in ('scripts','deploy','deploy/community-preview'):
            parent_rel=rel.rsplit('/',1)[0] if '/' in rel else ''
            leaf=rel.rsplit('/',1)[-1]
            fds[rel]=mkdir_owned(fds[parent_rel],leaf,root_uid,root_gid)
        for index,name in enumerate(sorted(bodies)):
            if fault is not None:fault('before-file',name,index)
            parent_rel=name.rsplit('/',1)[0] if '/' in name else ''
            leaf=name.rsplit('/',1)[-1]
            write_owned(fds[parent_rel],leaf,bodies[name],root_uid,root_gid)
            if fault is not None:fault('after-file',name,index)
        for rel in ('deploy/community-preview','deploy','scripts',''):
            os.fsync(fds[rel])
    finally:
        for rel in ('deploy/community-preview','deploy','scripts'):
            fd=fds.get(rel)
            if fd is not None:os.close(fd)

def verify_tree(parent,name,manifest,bodies,root_uid=0):
    root=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        st=os.fstat(root);need(st.st_uid==root_uid and stat.S_IMODE(st.st_mode)==0o700,'FINAL_ROOT_MODE_REQUIRED')
        expected_dirs={'scripts','deploy','deploy/community-preview'}
        children={'':set(),'scripts':set(),'deploy':set(),'deploy/community-preview':set()}
        for rel in expected_dirs:
            parent_rel=rel.rsplit('/',1)[0] if '/' in rel else '';children[parent_rel].add(rel.rsplit('/',1)[-1])
        for rel in bodies:
            parent_rel=rel.rsplit('/',1)[0] if '/' in rel else '';children[parent_rel].add(rel.rsplit('/',1)[-1])
        need(set(os.listdir(root))==children[''],'FINAL_MEMBER_SET_CHANGED')
        for rel in expected_dirs:
            fd=root
            opened=[]
            try:
                for part in rel.split('/'):
                    child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);opened.append(child);fd=child
                    st_child=os.fstat(fd);need(st_child.st_uid==root_uid and stat.S_IMODE(st_child.st_mode)==0o700,'FINAL_DIRECTORY_REQUIRED')
                need(set(os.listdir(fd))==children[rel],'FINAL_MEMBER_SET_CHANGED')
            finally:
                for child in reversed(opened):os.close(child)
        for rel,body in bodies.items():
            fd=root;opened=[]
            try:
                parts=rel.split('/')
                for part in parts[:-1]:
                    child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);opened.append(child);fd=child
                f=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                try:
                    s=os.fstat(f);need(stat.S_ISREG(s.st_mode) and s.st_uid==root_uid and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1,'FINAL_FILE_REQUIRED')
                    got=read_exact_fd(f,MAX_FILE);need(got==body,'FINAL_FILE_BYTES_CHANGED')
                finally:os.close(f)
            finally:
                for child in reversed(opened):os.close(child)
    finally:os.close(root)


def dir_identity(st):
    return (st.st_dev,st.st_ino,stat.S_IFMT(st.st_mode),st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode))

def publish_noreplace(parent,old,new):
    libc=ctypes.CDLL(None,use_errno=True)
    fn=getattr(libc,'renameat2',None)
    need(fn is not None,'RENAME_NOREPLACE_REQUIRED')
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    fn.restype=ctypes.c_int
    if fn(parent,old.encode(),parent,new.encode(),1)!=0:
        error=ctypes.get_errno()
        if error in (errno.EEXIST,errno.ENOTEMPTY):raise Hold('TARGET_OR_PARTIAL_ALREADY_EXISTS')
        raise Hold('ATOMIC_NOREPLACE_PUBLISH_REQUIRED')

def _post_publish_reason(error):
    if type(error) is Hold and str(error):return str(error)
    return 'POST_PUBLISH_'+type(error).__name__.upper()

def _path_dir_identity(parent,name):
    try:st=os.stat(name,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return None
    need(stat.S_ISDIR(st.st_mode),'PUBLISH_RECONCILE_NON_DIRECTORY')
    return dir_identity(st)

def reconcile_publish(parent,temp_identity):
    try:
        temp_now=_path_dir_identity(parent,TEMP)
        target_now=_path_dir_identity(parent,TARGET)
    except BaseException:return 'unknown'
    if temp_now==temp_identity:return 'not_published'
    if temp_now is None and target_now==temp_identity:return 'published'
    return 'unknown'

def install_bytes(archive,manifest_raw,parent_fd,root_uid=0,root_gid=0,fault=None):
    manifest,bodies=validate_archive(archive,manifest_raw)
    parent_identity_before=verify_parent(parent_fd,root_uid)
    absent(parent_fd,TARGET);absent(parent_fd,TEMP)
    try:os.mkdir(TEMP,0o700,dir_fd=parent_fd)
    except FileExistsError:raise Hold('TARGET_OR_PARTIAL_ALREADY_EXISTS') from None
    temp=os.open(TEMP,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd)
    attempted=False;published=False;parent_fsync_completed=False;pending=None;temp_identity=None
    try:
        os.fchown(temp,root_uid,root_gid);os.fchmod(temp,0o700);os.fsync(temp);os.fsync(parent_fd)
        create_tree(temp,bodies,root_uid,root_gid,fault)
        verify_tree(parent_fd,TEMP,manifest,bodies,root_uid)
        need(parent_identity(os.fstat(parent_fd))==parent_identity_before,'INSTALL_PARENT_CHANGED')
        absent(parent_fd,TARGET)
        temp_identity=dir_identity(os.fstat(temp))
        need(temp_identity==dir_identity(os.stat(TEMP,dir_fd=parent_fd,follow_symlinks=False)),'TEMP_PATH_REPLACED')
        if fault is not None:fault('before-publish',TARGET,-1)
        attempted=True
        try:publish_noreplace(parent_fd,TEMP,TARGET)
        except BaseException as error:
            outcome=reconcile_publish(parent_fd,temp_identity)
            if outcome=='not_published':raise Hold(str(error),True,temp_identity,parent_fsync_completed) from error
            raise PublishedUnknown(_post_publish_reason(error),parent_fsync_completed,temp_identity) from error
        outcome=reconcile_publish(parent_fd,temp_identity)
        if outcome!='published':raise PublishedUnknown('PUBLISH_IDENTITY_UNPROVEN',parent_fsync_completed,temp_identity)
        published=True
        if fault is not None:fault('after-publish',TARGET,-1)
        os.fsync(parent_fd);parent_fsync_completed=True
        if fault is not None:fault('after-parent-fsync',TARGET,-1)
        need(dir_identity(os.fstat(temp))==dir_identity(os.stat(TARGET,dir_fd=parent_fd,follow_symlinks=False)),'FINAL_PATH_REPLACED')
        verify_tree(parent_fd,TARGET,manifest,bodies,root_uid)
    except BaseException as error:
        if isinstance(error,PublishedUnknown):pending=error
        elif published:pending=PublishedUnknown(_post_publish_reason(error),parent_fsync_completed,temp_identity)
        elif attempted and not isinstance(error,Hold):
            outcome=reconcile_publish(parent_fd,temp_identity)
            if outcome=='not_published':pending=Hold(str(error),True,temp_identity,parent_fsync_completed)
            else:pending=PublishedUnknown(_post_publish_reason(error),parent_fsync_completed,temp_identity)
        else:pending=error
    try:os.close(temp)
    except BaseException as error:
        if published or isinstance(pending,PublishedUnknown):
            if pending is None:pending=PublishedUnknown('TEMP_CLOSE_UNKNOWN',parent_fsync_completed,temp_identity)
        elif pending is None:pending=error
    if pending is not None:raise pending
    return {'state':'V2_CARRIER_INSTALLED','install_root':INSTALL_ROOT,'archive_sha256':ARCHIVE_SHA256,
            'manifest_sha256':MANIFEST_SHA256,'publish_attempted':True,
            'temp_identity_sha256':identity_digest(temp_identity),'target_published':True,'retry_safe':False,
            'parent_fsync_completed':True,'site_executed':False,'bc_executed':False}

SUCCESS_RECEIPT_KEYS={'state','install_root','archive_sha256','manifest_sha256','publish_attempted',
                      'temp_identity_sha256','target_published','retry_safe','parent_fsync_completed',
                      'site_executed','bc_executed'}

def hold_record(error):
    return {'state':'V2_INSTALL_HOLD','reason':str(error),'publish_attempted':error.publish_attempted,
            'temp_identity_sha256':identity_digest(error.temp_identity),'target_published':False,'retry_safe':False,
            'parent_fsync_completed':error.parent_fsync_completed,'site_executed':False,'bc_executed':False}

def consume_entry_receipt(child_exit,raw):
    need(type(child_exit) is int and type(raw) is bytes and len(raw)<=4096,'INSTALL_ENTRY_RECEIPT_UNKNOWN')
    need(raw.endswith(b'\n') and raw.count(b'\n')==1,'INSTALL_ENTRY_RECEIPT_UNKNOWN')
    try:value=json.loads(raw[:-1])
    except (ValueError,UnicodeError):raise Hold('INSTALL_ENTRY_RECEIPT_UNKNOWN') from None
    need(child_exit==0 and type(value) is dict and set(value)==SUCCESS_RECEIPT_KEYS
         and value['state']=='V2_CARRIER_INSTALLED' and value['install_root']==INSTALL_ROOT
         and value['archive_sha256']==ARCHIVE_SHA256 and value['manifest_sha256']==MANIFEST_SHA256
         and value['publish_attempted'] is True and type(value['temp_identity_sha256']) is str
         and re.fullmatch('[0-9a-f]{64}',value['temp_identity_sha256']) is not None
         and value['target_published'] is True and value['retry_safe'] is False
         and value['parent_fsync_completed'] is True and value['site_executed'] is False
         and value['bc_executed'] is False,'INSTALL_ENTRY_RECEIPT_UNKNOWN')
    return value

def production_identity():
    need(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'EXACT_ROOT_HOST_REQUIRED')
    admin=pwd.getpwnam('admin')
    need(admin.pw_uid>0 and os.environ.get('SUDO_USER')=='admin' and os.environ.get('SUDO_UID')==str(admin.pw_uid)
         and os.environ.get('SUDO_GID')==str(admin.pw_gid),'ORIGINAL_ADMIN_SUDO_REQUIRED')
    fd=os.open('/proc/'+str(os.getpid())+'/loginuid',os.O_RDONLY|os.O_NOFOLLOW)
    try:need(os.read(fd,32).strip()==str(admin.pw_uid).encode(),'KERNEL_LOGINUID_REQUIRED')
    finally:os.close(fd)

def open_fixed_parent():
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in PARENT.split('/')[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        verify_parent(fd,0);return fd
    except BaseException:os.close(fd);raise

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',required=True)
    parser.add_argument('--manifest',required=True)
    args=parser.parse_args(argv)
    production_identity()
    archive=open_input(args.archive,MAX_ARCHIVE);need(sha(archive)==ARCHIVE_SHA256,'FIXED_ARCHIVE_SHA_REQUIRED')
    manifest=open_input(args.manifest,MAX_FILE);need(sha(manifest)==MANIFEST_SHA256,'FIXED_MANIFEST_SHA_REQUIRED')
    parent=open_fixed_parent();result=None;pending=None
    try:result=install_bytes(archive,manifest,parent,0,0)
    except BaseException as error:pending=error
    try:os.close(parent)
    except BaseException as error:
        if isinstance(pending,PublishedUnknown):pass
        elif result is not None and result.get('target_published') is True:
            pending=PublishedUnknown('INSTALL_PARENT_CLOSE_UNKNOWN',result.get('parent_fsync_completed') is True,
                                     temp_identity_sha256=result.get('temp_identity_sha256'))
        elif pending is None:pending=error
    if pending is not None:raise pending
    print(json.dumps(result,sort_keys=True),flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except PublishedUnknown as error:
        print(json.dumps(error.record(),sort_keys=True),flush=True)
        raise SystemExit(2)
    except Hold as error:
        print(json.dumps(hold_record(error),sort_keys=True),flush=True)
        raise SystemExit(2)
