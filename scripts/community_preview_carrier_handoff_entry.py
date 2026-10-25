"""Issue76 fixed in-process handoff entry: no independent authority or CLI.

The existing unique installation Writer calls run(...) with an independently
approved action checker. Merely being root/admin does not grant an action.
No B/C hooks, Session.acquire, service start or old intent mutation.
"""
import os
import pwd
import stat
import contextlib
from types import SimpleNamespace
from scripts import community_preview_carrier_handoff_admission as h
from scripts import community_preview_carrier_handoff_call as call

PARENT='/opt/xuanjun-community-preview'
JOURNAL=PARENT+'/update-journal'
ENTRY=PARENT+'/site-prepare-v1.py'
ENTRY_SHA='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'
ATTEMPT='community-update-f13155ed63a3-818fe0b0622c-stopped-v1'
OPERATIONS=('execute','status','rollback')

def require(condition,reason):
    if not condition:raise h.Hold(reason)

def identify_admin():
    require(os.geteuid()==0 and os.uname().nodename.split('.')[0]==h.HOST,
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
        require(os.fstat(nextfd).st_uid==0 and not(os.fstat(nextfd).st_mode&0o022),
                'UNTRUSTED_PATH_COMPONENT')
        fd=nextfd
    return fd

def _open_regular(parent,name,stack):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    stack.callback(os.close,fd)
    st=os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_uid==0
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

def run(operation, authority_checker, old_archive_bytes, new_archive_bytes):
    """Requires original Writer's independently approved action checker.

    The checker is invoked once with (operation, fixed host, attempt).
    It must verify a separately protected current approval; identity alone
    is not approval. On rejected/unknown grant, no stage/write occurs.
    """
    require(operation in OPERATIONS,'HANDOFF_OPERATION_DENIED')
    require(callable(authority_checker),'INSTALL_WRITER_AUTHORITY_REQUIRED')
    identify_admin()
    approved=authority_checker(operation,h.HOST,ATTEMPT)
    require(approved is True,'CURRENT_INSTALL_WRITER_APPROVAL_REQUIRED')
    require(type(old_archive_bytes) is bytes and type(new_archive_bytes) is bytes,
            'EXACT_PROTECTED_ARCHIVE_BYTES_REQUIRED')
    # Complete pinned archive/manifests must be verified before any transaction.
    h.members(old_archive_bytes,h.OLD_MANIFEST,h.OLD_ARCHIVE)
    h.members(new_archive_bytes,h.NEW_MANIFEST,h.NEW_ARCHIVE)
    with contextlib.ExitStack() as stack:
        parent=_protected_path_directory(PARENT,stack)
        journal=_protected_path_directory(JOURNAL,stack)
        require(h.dirident(os.fstat(journal))==h.dirident(os.stat(
                    h.JOURNAL_DIR,dir_fd=parent,follow_symlinks=False)),
                'JOURNAL_PARENT_PATH_CHANGED')
        entry=_open_regular(parent,h.ENTRY_NAME,stack)
        require(h.sha(_read_fd_exact(entry,131072))==ENTRY_SHA,'ORIGINAL_A_ENTRY_SHA_CHANGED')
        lease=os.open(h.LOCK,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=journal)
        stack.callback(os.close,lease)
        ls=os.fstat(lease)
        require(stat.S_ISREG(ls.st_mode) and ls.st_uid==0
                and stat.S_IMODE(ls.st_mode)==0o600 and ls.st_nlink==1
                and h.ident(ls)==h.ident(os.stat(h.LOCK,dir_fd=journal,follow_symlinks=False)),
                'ORIGINAL_LOCK_IDENTITY_CHANGED')
        # Bind all fixed historical names; absent stays absent, existing is
        # read with stable fd and protected SHA/identity. No historical writes.
        refs={}
        for key,name in h.HISTORY_NAMES.items():
            home=journal if key in h.JOURNAL_HISTORY_KEYS else parent
            st=h.childstat(home,name)
            if st is None:
                refs[key]=(home,name,h.parent_ident(os.fstat(home)),None,None)
                continue
            require(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600
                    and st.st_uid==0 and st.st_nlink==1,'HISTORY_UNEXPECTED_OBJECT')
            body=h.readfile(home,name,0,8*1024*1024)
            refs[key]=(home,name,h.parent_ident(os.fstat(home)),h.ident(st),h.sha(body))
        h.capture_history(refs,0,parent,journal)
        ctx=SimpleNamespace(
            host_id=h.HOST,authority_check=lambda:approved is True,
            parent_fd=parent,journal_fd=journal,entry_fd=entry,lease_fd=lease,uid=0,
            parent_identity=h.parent_ident(os.fstat(parent)),
            journal_identity=h.dirident(os.fstat(journal)),
            entry_identity=h.ident(os.fstat(entry)),lock_identity=h.ident(os.fstat(lease)),
            history_refs=refs,old_archive_bytes=old_archive_bytes,
            new_archive_bytes=new_archive_bytes,attempt=ATTEMPT)
        if operation=='execute':return call.call_once_from_original_entry(ctx)
        if operation=='status':return call.reconcile_from_original_entry(ctx)
        return call.rollback_from_original_entry(ctx)
