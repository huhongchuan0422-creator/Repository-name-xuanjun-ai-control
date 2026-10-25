"""Issue76 fixed in-process handoff entry: no independent authority or CLI.

The existing unique installation Writer calls run(...) with an independently
approved action checker. Merely being root/admin does not grant an action.
No B/C hooks, Session.acquire, service start or old intent mutation.
"""
import os
import pwd
import stat
import contextlib
import json
import time
from types import SimpleNamespace
from scripts import community_preview_carrier_handoff_admission as h
from scripts import community_preview_carrier_handoff_call as call

PARENT='/opt/xuanjun-community-preview'
JOURNAL=PARENT+'/update-journal'
ENTRY=PARENT+'/site-prepare-v1.py'
ENTRY_SHA='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'
APPROVAL_NAME='carrier-handoff-approval.json'
APPROVAL_MAX=16384
APPROVAL_TTL_MAX=600
SCRIPTS_DIR=PARENT+'/control-stopped-v1/scripts'
MODULE_PINS={
    'community_preview_carrier_handoff_admission.py':'c23f183753e726dd25a117f730d4180da4f59dcde379591d1dfae5258f74f386',
    'community_preview_carrier_handoff_call.py':'a597e426c0cd696621594c8c62f0fc300fc2a67d17e67236891c0421b8f0a5bc'
}
ATTEMPT='community-update-f13155ed63a3-818fe0b0622c-stopped-v1'
OPERATIONS=('execute','status','rollback')
ROOT_UID=0  # Production invariant, overridden only in isolated fixture tests.

def require(condition,reason):
    if not condition:raise h.Hold(reason)

def identify_admin():
    require(os.geteuid()==ROOT_UID and os.uname().nodename.split('.')[0]==h.HOST,
            'FIXED_UK_HOST_AND_ROOT_REQUIRED')
    admin=pwd.getpwnam('admin')
    require(admin.pw_uid>0 and os.environ.get('SUDO_USER')=='admin'
            and os.environ.get('SUDO_UID')==str(admin.pw_uid)
            and os.environ.get('SUDO_GID')==str(admin.pw_gid),
            'ORIGINAL_ADMIN_SUDO_IDENTITY_REQUIRED')
    fd=os.open('/proc/self/loginuid',os.O_RDONLY|os.O_NOFOLLOW)
    try:require(os.read(fd,32).strip()==str(admin.pw_uid).encode('ascii'),
                'KERNEL_LOGINUID_REQUIRED')
    finally:os.close(fd)
    return admin.pw_uid

def _protected_path_directory(path,stack):
    require(path in (PARENT,JOURNAL),'EXACT_PROTECTED_DIRECTORY_ONLY')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    stack.callback(os.close,fd)
    for part in path.strip('/').split('/'):
        nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
        stack.callback(os.close,nextfd)
        require(os.fstat(nextfd).st_uid==ROOT_UID and not(os.fstat(nextfd).st_mode&0o022),
                'UNTRUSTED_PATH_COMPONENT')
        fd=nextfd
    return fd

def _open_regular(parent,name,stack):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    stack.callback(os.close,fd)
    st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_uid==ROOT_UID
            and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1
            and h.ident(st)==h.ident(os.stat(name,dir_fd=parent,follow_symlinks=False)),
            'ROOT_SINGLE_LINK_0600_IDENTITY_REQUIRED')
    return fd

def _read_fd_exact(fd,limit):
    st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and 0<st.st_size<=limit,'INPUT_SIZE_INVALID')
    body=bytearray()
    while len(body)<=limit:
        chunk=os.read(fd,min(65536,limit-len(body)+1))
        if not chunk:break
        body.extend(chunk)
    require(len(body)==st.st_size and h.ident(os.fstat(fd))==h.ident(st),
            'INPUT_CHANGED')
    return bytes(body)

def _verify_runtime_sources():
    """Verify the exact fixed carrier files before transaction entry."""
    require(os.path.abspath(getattr(h,'__file__',''))==
            SCRIPTS_DIR+'/community_preview_carrier_handoff_admission.py',
            'HANDOFF_MODULE_PATH_MISMATCH')
    require(os.path.abspath(getattr(call,'__file__',''))==
            SCRIPTS_DIR+'/community_preview_carrier_handoff_call.py',
            'HANDOFF_CALL_PATH_MISMATCH')
    for name,wanted in MODULE_PINS.items():
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,
                   dir_fd=_open_fixed_scripts_dir())
        try:
            st=os.fstat(fd)
            require(stat.S_ISREG(st.st_mode) and st.st_uid==ROOT_UID
                    and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1,
                    'HANDOFF_MODULE_IDENTITY_OR_MODE')
            raw=_read_fd_exact(fd,262144)
            require(h.sha(raw)==wanted,'HANDOFF_MODULE_SHA_MISMATCH')
            dfd=_open_fixed_scripts_dir()
            try:
                require(h.ident(st)==h.ident(os.stat(name,dir_fd=dfd,follow_symlinks=False)),
                        'HANDOFF_MODULE_PATH_REPLACED')
            finally:os.close(dfd)
        finally:os.close(fd)

def _open_fixed_scripts_dir():
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in ('opt','xuanjun-community-preview','control-stopped-v1','scripts'):
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
            st=os.fstat(fd)
            require(stat.S_ISDIR(st.st_mode) and st.st_uid==ROOT_UID
                    and stat.S_IMODE(st.st_mode)==0o700,'HANDOFF_MODULE_PARENT_PROTECTION')
        return fd
    except BaseException:
        os.close(fd)
        raise

def _canonical(raw):
    def pairs(rows):
        result={}
        for key,value in rows:
            require(key not in result,'APPROVAL_DUPLICATE_KEY')
            result[key]=value
        return result
    def invalid(_value):
        raise h.Hold('APPROVAL_NONFINITE_JSON')
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid)
    except (ValueError,UnicodeError):raise h.Hold('APPROVAL_JSON_INVALID')
    require(type(value) is dict and h.canonical(value)==raw,'APPROVAL_NONCANONICAL')
    return value

def _approval_fd(parent,operation,old_archive_bytes,new_archive_bytes,uid,stack):
    fd=os.open(APPROVAL_NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    stack.callback(os.close,fd)
    st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_uid==uid
            and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1
            and 0<st.st_size<=APPROVAL_MAX
            and h.ident(st)==h.ident(os.stat(APPROVAL_NAME,dir_fd=parent,follow_symlinks=False)),
            'APPROVAL_FILE_IDENTITY_OR_MODE')
    record=_read_fd_exact(fd,APPROVAL_MAX)
    value=_canonical(record)
    fields={'format','host','operation','attempt','old_archive_sha256',
            'old_manifest_sha256','new_archive_sha256','new_manifest_sha256',
            'issued_at','expires_at'}
    require(set(value)==fields and type(value['format']) is int and value['format']==1,
            'APPROVAL_SCHEMA')
    require(value['host']==h.HOST and value['operation']==operation
            and value['attempt']==ATTEMPT,'APPROVAL_SCOPE_MISMATCH')
    require(value['old_archive_sha256']==h.OLD_ARCHIVE
            and value['old_manifest_sha256']==h.OLD_MANIFEST
            and value['new_archive_sha256']==h.NEW_ARCHIVE
            and value['new_manifest_sha256']==h.NEW_MANIFEST,
            'APPROVAL_PIN_MISMATCH')
    issued=value['issued_at'];expires=value['expires_at'];now=int(time.time())
    require(type(issued) is int and type(expires) is int and issued<=now<=expires
            and expires<=issued+APPROVAL_TTL_MAX,'APPROVAL_EXPIRED_OR_TTL_INVALID')
    require(h.ident(os.fstat(fd))==h.ident(os.stat(APPROVAL_NAME,dir_fd=parent,follow_symlinks=False)),
            'APPROVAL_REPLACED')
    return fd,record,h.ident(st)

def _recheck_approval(parent,fd,expected_raw,expected_identity,operation,old_archive_bytes,new_archive_bytes,uid):
    st=os.fstat(fd)
    require(h.ident(st)==expected_identity and h.ident(os.stat(APPROVAL_NAME,dir_fd=parent,follow_symlinks=False))==expected_identity,
            'APPROVAL_REPLACED')
    raw=_read_fd_exact(fd,APPROVAL_MAX)
    require(raw==expected_raw,'APPROVAL_CONTENT_CHANGED')
    # Revalidate operation, pins and expiry at the last boundary before mutation.
    value=_canonical(raw)
    require(value.get('operation')==operation and value.get('host')==h.HOST
            and value.get('attempt')==ATTEMPT
            and value.get('old_archive_sha256')==h.OLD_ARCHIVE
            and value.get('old_manifest_sha256')==h.OLD_MANIFEST
            and value.get('new_archive_sha256')==h.NEW_ARCHIVE
            and value.get('new_manifest_sha256')==h.NEW_MANIFEST,
            'APPROVAL_SCOPE_MISMATCH')
    now=int(time.time())
    require(type(value.get('issued_at')) is int and type(value.get('expires_at')) is int
            and value['issued_at']<=now<=value['expires_at']<=value['issued_at']+APPROVAL_TTL_MAX,
            'APPROVAL_EXPIRED_OR_TTL_INVALID')
    return True

def run(operation, old_archive_bytes, new_archive_bytes):
    """Fixed original-entry caller; current approval is read from the protected record."""
    require(operation in OPERATIONS,'HANDOFF_OPERATION_DENIED')
    identify_admin()
    _verify_runtime_sources()
    require(type(old_archive_bytes) is bytes and type(new_archive_bytes) is bytes,
            'EXACT_PROTECTED_ARCHIVE_BYTES_REQUIRED')
    with contextlib.ExitStack() as stack:
        parent=_protected_path_directory(PARENT,stack)
        journal=_protected_path_directory(JOURNAL,stack)
        approval_fd,approval_raw,approval_identity=_approval_fd(
            parent,operation,old_archive_bytes,new_archive_bytes,ROOT_UID,stack)
        h.members(old_archive_bytes,h.OLD_MANIFEST,h.OLD_ARCHIVE)
        h.members(new_archive_bytes,h.NEW_MANIFEST,h.NEW_ARCHIVE)
        require(h.dirident(os.fstat(journal))==h.dirident(os.stat(
                    h.JOURNAL_DIR,dir_fd=parent,follow_symlinks=False)),
                'JOURNAL_PARENT_PATH_CHANGED')
        entry=_open_regular(parent,h.ENTRY_NAME,stack)
        require(h.sha(_read_fd_exact(entry,131072))==ENTRY_SHA,'ORIGINAL_A_ENTRY_SHA_CHANGED')
        lease=os.open(h.LOCK,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=journal)
        stack.callback(os.close,lease)
        ls=os.fstat(lease)
        require(stat.S_ISREG(ls.st_mode) and ls.st_uid==ROOT_UID
                and stat.S_IMODE(ls.st_mode)==0o600 and ls.st_nlink==1
                and h.ident(ls)==h.ident(os.stat(h.LOCK,dir_fd=journal,follow_symlinks=False)),
                'ORIGINAL_LOCK_IDENTITY_CHANGED')
        refs={}
        for key,name in h.HISTORY_NAMES.items():
            home=journal if key in h.JOURNAL_HISTORY_KEYS else parent
            st=h.childstat(home,name)
            if st is None:
                refs[key]=(home,name,h.parent_ident(os.fstat(home)),None,None)
                continue
            require(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600
                    and st.st_uid==ROOT_UID and st.st_nlink==1,'HISTORY_UNEXPECTED_OBJECT')
            body=h.readfile(home,name,ROOT_UID,8*1024*1024)
            refs[key]=(home,name,h.parent_ident(os.fstat(home)),h.ident(st),h.sha(body))
        h.capture_history(refs,ROOT_UID,parent,journal)
        _recheck_approval(parent,approval_fd,approval_raw,approval_identity,
                          operation,old_archive_bytes,new_archive_bytes,ROOT_UID)
        ctx=SimpleNamespace(
            host_id=h.HOST,
            authority_check=lambda:_recheck_approval(parent,approval_fd,approval_raw,
                approval_identity,operation,old_archive_bytes,new_archive_bytes,ROOT_UID),
            parent_fd=parent,journal_fd=journal,entry_fd=entry,lease_fd=lease,uid=ROOT_UID,
            parent_identity=h.parent_ident(os.fstat(parent)),
            journal_identity=h.dirident(os.fstat(journal)),
            entry_identity=h.ident(os.fstat(entry)),lock_identity=h.ident(os.fstat(lease)),
            history_refs=refs,old_archive_bytes=old_archive_bytes,
            new_archive_bytes=new_archive_bytes,attempt=ATTEMPT)
        _recheck_approval(parent,approval_fd,approval_raw,approval_identity,
                          operation,old_archive_bytes,new_archive_bytes,ROOT_UID)
        if operation=='execute':return call.call_once_from_original_entry(ctx)
        if operation=='status':return call.reconcile_from_original_entry(ctx)
        return call.rollback_from_original_entry(ctx)
