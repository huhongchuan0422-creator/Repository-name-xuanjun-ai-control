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
import sys
import types
from types import SimpleNamespace
import hashlib
import sys

class _BootstrapHold(RuntimeError):
    pass

class _Bootstrap(object):
    HOST='iZd7oeikknn1z21sq6ji6zZ'
    Hold=_BootstrapHold
    @staticmethod
    def sha(raw):
        return hashlib.sha256(raw).hexdigest()
    @staticmethod
    def ident(st):
        return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,
                st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns]

try:
    from scripts import community_preview_carrier_handoff_admission as h
    from scripts import community_preview_carrier_handoff_call as call
except ImportError:
    # Standalone fixed caller starts without trusting any carrier Python module;
    # it verifies and loads the pinned module bytes before transaction work.
    h=_Bootstrap
    call=None

PARENT='/opt/xuanjun-community-preview'
JOURNAL=PARENT+'/update-journal'
ENTRY=PARENT+'/site-prepare-v1.py'
ENTRY_SHA='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'
APPROVAL_NAME='carrier-handoff-approval.json'
POST_B_APPROVAL_NAME='post-b-carrier-handoff-approval.json'
OLD_INPUT_NAME='control-stopped-v1-1d639.zip'
NEW_INPUT_NAME='control-stopped-v1-005c.zip'
POST_B_OLD_INPUT_NAME='control-stopped-v1-005c.zip'
POST_B_NEW_INPUT_NAME='control-stopped-v1-post-b-candidate.zip'
POST_B_NEW_ARCHIVE_SHA256=None
POST_B_NEW_MANIFEST_SHA256=None
INPUT_MAX=4*1024*1024
APPROVAL_MAX=16384
APPROVAL_TTL_MAX=600
SCRIPTS_DIR=PARENT
MODULE_PINS={
    # Updated together with this fixed entry after isolated review. Runtime still
    # requires these exact bytes; post-B adds no alternate import/execution path.
    'community_preview_carrier_handoff_admission.py':'151b774836e48c6e73e1773077663bddddff976dcb6fb026b5ba4876ccc5a657',
    'community_preview_carrier_handoff_call.py':'940652bdf1e94d66c0dba5f841c7bf92a5b55ca14e0297dc48d483fc159b0fa0'
}
ATTEMPT='community-update-f13155ed63a3-818fe0b0622c-stopped-v1'
OPERATIONS=('execute','status','rollback','post-b-execute','post-b-status','post-b-rollback')
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
    # Repeated validation must read the same already-open FD from byte zero.
    # Do not reopen the pathname: the FD/path identity is checked by its caller.
    try:
        pos=os.lseek(fd,0,os.SEEK_SET)
    except OSError:
        raise h.Hold('INPUT_SEEK_FAILED')
    require(pos==0 and h.ident(os.fstat(fd))==h.ident(st),'INPUT_CHANGED')
    body=bytearray()
    while len(body)<=limit:
        chunk=os.read(fd,min(65536,limit-len(body)+1))
        if not chunk:break
        body.extend(chunk)
    after=os.fstat(fd)
    require(len(body)==st.st_size and h.ident(after)==h.ident(st),
            'INPUT_CHANGED')
    return bytes(body)

def _verify_runtime_sources():
    """Verify and execute the exact pinned source bytes before transaction entry."""
    global h,call
    expected_paths={
        'community_preview_carrier_handoff_admission.py':
            SCRIPTS_DIR+'/community_preview_carrier_handoff_admission.py',
        'community_preview_carrier_handoff_call.py':
            SCRIPTS_DIR+'/community_preview_carrier_handoff_call.py'
    }
    raw_by_name={}
    for name,wanted in MODULE_PINS.items():
        full=expected_paths[name]
        dfd=_open_fixed_scripts_dir()
        try:
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
            try:
                st=os.fstat(fd)
                require(stat.S_ISREG(st.st_mode) and st.st_uid==ROOT_UID
                        and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1,
                        'HANDOFF_MODULE_IDENTITY_OR_MODE')
                raw=_read_fd_exact(fd,262144)
                require(h.sha(raw)==wanted,'HANDOFF_MODULE_SHA_MISMATCH')
                require(h.ident(st)==h.ident(os.stat(name,dir_fd=dfd,follow_symlinks=False)),
                        'HANDOFF_MODULE_PATH_REPLACED')
                raw_by_name[name]=(full,raw)
            finally:os.close(fd)
        finally:os.close(dfd)
    package=sys.modules.get('scripts')
    if package is None:
        package=types.ModuleType('scripts')
        package.__path__=[]
        sys.modules['scripts']=package
    loaded={}
    for name in ('community_preview_carrier_handoff_admission.py',
                 'community_preview_carrier_handoff_call.py'):
        short=name[:-3]
        full,raw=raw_by_name[name]
        module=types.ModuleType('scripts.'+short)
        module.__file__=full
        module.__package__='scripts'
        sys.modules[module.__name__]=module
        exec(compile(raw,full,'exec'),module.__dict__)
        setattr(package,short,module)
        loaded[short]=module
    h=loaded['community_preview_carrier_handoff_admission']
    call=loaded['community_preview_carrier_handoff_call']
    require(os.path.abspath(h.__file__)==expected_paths['community_preview_carrier_handoff_admission.py']
            and os.path.abspath(call.__file__)==expected_paths['community_preview_carrier_handoff_call.py'],
            'HANDOFF_MODULE_LOAD_PATH_MISMATCH')
    return True

def _open_fixed_scripts_dir():
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for index,part in enumerate(('opt','xuanjun-community-preview')):
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
            st=os.fstat(fd)
            require(stat.S_ISDIR(st.st_mode) and st.st_uid==ROOT_UID
                    and not (st.st_mode & 0o022),
                    'HANDOFF_MODULE_PARENT_PROTECTION')
            # Protected parent may be 0700 or 0755; group/world write is forbidden.
            # Root-owned 0600 module files and FD/path identity are enforced below.
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_fixed_archive(parent,name,expected_sha,uid):
    require(name in (OLD_INPUT_NAME,NEW_INPUT_NAME),'FIXED_INPUT_NAME_DENIED')
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    try:
        st=os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid==uid
                and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1
                and 0<st.st_size<=INPUT_MAX
                and h.ident(st)==h.ident(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                'FIXED_INPUT_IDENTITY_OR_MODE')
        raw=_read_fd_exact(fd,INPUT_MAX)
        require(h.sha(raw)==expected_sha,'FIXED_INPUT_SHA_MISMATCH')
        require(h.ident(st)==h.ident(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                'FIXED_INPUT_REPLACED')
        return raw
    finally:os.close(fd)

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

def _approval_fd(parent,operation,old_archive_bytes,new_archive_bytes,uid,stack,approval_name=APPROVAL_NAME):
    try:fd=os.open(approval_name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    except FileNotFoundError:raise h.Hold('APPROVAL_MISSING')
    except OSError:raise h.Hold('APPROVAL_OPEN_REJECTED')
    stack.callback(os.close,fd)
    st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_uid==uid
            and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1
            and 0<st.st_size<=APPROVAL_MAX
            and h.ident(st)==h.ident(os.stat(approval_name,dir_fd=parent,follow_symlinks=False)),
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
    require(h.ident(os.fstat(fd))==h.ident(os.stat(approval_name,dir_fd=parent,follow_symlinks=False)),
            'APPROVAL_REPLACED')
    return fd,record,h.ident(st)

def _recheck_approval(parent,fd,expected_raw,expected_identity,operation,old_archive_bytes,new_archive_bytes,uid,approval_name=APPROVAL_NAME):
    st=os.fstat(fd)
    require(h.ident(st)==expected_identity and h.ident(os.stat(approval_name,dir_fd=parent,follow_symlinks=False))==expected_identity,
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

def main(argv=None):
    """Fixed caller CLI. The command selects an operation; only the protected
    short-lived record authorizes it. No approval flags or caller-supplied paths.
    """
    import sys
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)!=1 or args[0] not in OPERATIONS:
        print('HOLD HANDOFF_OPERATION_DENIED')
        return 2
    operation=args[0]
    try:
        result=run(operation)
        state=result.get('state') if isinstance(result,dict) else None
        base_operation=operation[7:] if operation.startswith('post-b-') else operation
        if base_operation=='execute':
            accepted=state=='SWAPPED_OLD_RETAINED_IN_STAGE' and result.get('retry_safe') is False
        elif base_operation=='rollback':
            accepted=state=='ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED' and result.get('retry_safe') is False
        else:
            accepted=state in ('NO_HANDOFF_JOURNAL','PREPARED_OR_REVERTED',
                'SWAPPED_OLD_RETAINED_IN_STAGE',
                'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_RETAINED')
        print(h.canonical({'operation':operation,'state':state,
                           'accepted':bool(accepted),'retry_safe':False}))
        return 0 if accepted else 3
    except h.Hold as exc:
        # Print only the stable reason code, never input data, approval bytes,
        # paths from untrusted JSON, or signed URLs.
        print('HOLD '+str(exc))
        return 3
    except BaseException:
        print('UNKNOWN_INSPECT_ONLY')
        return 4


def run(operation):
    """Fixed original-entry caller; current approval is read from the protected record."""
    require(operation in OPERATIONS,'HANDOFF_OPERATION_DENIED')
    post_b=operation.startswith('post-b-');base_operation=operation[7:] if post_b else operation
    approval_name=POST_B_APPROVAL_NAME if post_b else APPROVAL_NAME
    approval_operation=operation if post_b else base_operation
    if post_b:
        require(type(POST_B_NEW_ARCHIVE_SHA256) is str and len(POST_B_NEW_ARCHIVE_SHA256)==64
                and type(POST_B_NEW_MANIFEST_SHA256) is str and len(POST_B_NEW_MANIFEST_SHA256)==64,
                'POST_B_CANDIDATE_PINS_NOT_REGISTERED')
    identify_admin()
    _verify_runtime_sources()
    with contextlib.ExitStack() as stack:
        parent=_protected_path_directory(PARENT,stack)
        journal=_protected_path_directory(JOURNAL,stack)
        old_archive_bytes=_read_fixed_archive(parent,OLD_INPUT_NAME,h.OLD_ARCHIVE,ROOT_UID)
        new_archive_bytes=_read_fixed_archive(parent,NEW_INPUT_NAME,h.NEW_ARCHIVE,ROOT_UID)
        approval_fd,approval_raw,approval_identity=_approval_fd(
            parent,approval_operation,old_archive_bytes,new_archive_bytes,ROOT_UID,stack,approval_name)
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
            if key=='backup_dir':
                require(stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode)==0o700
                        and st.st_uid==ROOT_UID,'HISTORY_UNEXPECTED_OBJECT')
                refs[key]=(home,name,h.parent_ident(os.fstat(home)),h.dirident(st),None)
                continue
            require(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600
                    and st.st_uid==ROOT_UID and st.st_nlink==1,'HISTORY_UNEXPECTED_OBJECT')
            body=h.readfile(home,name,ROOT_UID,8*1024*1024)
            refs[key]=(home,name,h.parent_ident(os.fstat(home)),h.ident(st),h.sha(body))
        h.capture_history(refs,ROOT_UID,parent,journal)
        _recheck_approval(parent,approval_fd,approval_raw,approval_identity,
                          approval_operation,old_archive_bytes,new_archive_bytes,ROOT_UID,approval_name)
        ctx=SimpleNamespace(
            host_id=h.HOST,
            authority_check=lambda:_recheck_approval(parent,approval_fd,approval_raw,
                approval_identity,approval_operation,old_archive_bytes,new_archive_bytes,ROOT_UID,approval_name),
            parent_fd=parent,journal_fd=journal,entry_fd=entry,lease_fd=lease,uid=ROOT_UID,
            parent_identity=h.parent_ident(os.fstat(parent)),
            journal_identity=h.dirident(os.fstat(journal)),
            entry_identity=h.ident(os.fstat(entry)),lock_identity=h.ident(os.fstat(lease)),
            history_refs=refs,old_archive_bytes=old_archive_bytes,
            new_archive_bytes=new_archive_bytes,attempt=ATTEMPT)
        _recheck_approval(parent,approval_fd,approval_raw,approval_identity,
                          approval_operation,old_archive_bytes,new_archive_bytes,ROOT_UID,approval_name)
        if post_b:
            if base_operation=='execute':return call.call_once_post_b_from_original_entry(ctx)
            if base_operation=='status':return call.reconcile_post_b_from_original_entry(ctx)
            return call.rollback_post_b_from_original_entry(ctx)
        if base_operation=='execute':return call.call_once_from_original_entry(ctx)
        if base_operation=='status':return call.reconcile_from_original_entry(ctx)
        return call.rollback_from_original_entry(ctx)

if __name__=='__main__':
    raise SystemExit(main())
