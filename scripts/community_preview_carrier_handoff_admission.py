"""Issue76 old->new stopped V2 carrier: source-only authority constants.

This module does NOT authorize installation, rename, rollback, B, or C.
Current host identity, unique writer, existing intents, and durable handoff
state must be independently reviewed before a future site operation.
"""
import hashlib
import json
import re

HOST='iZd7oeikknn1z21sq6ji6zZ'
INSTALL_ROOT='/opt/xuanjun-community-preview/control-stopped-v1'
OLD_ARCHIVE='5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4'
OLD_MANIFEST='e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a'
NEW_ARCHIVE='2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff'
NEW_MANIFEST='d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd'

class Hold(RuntimeError):
    pass

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')

def verify_inputs(old_manifest,new_archive,new_manifest):
    if sha(old_manifest)!=OLD_MANIFEST:
        raise Hold('OLD_INSTALLED_MANIFEST_UNPROVEN')
    if sha(new_archive)!=NEW_ARCHIVE or sha(new_manifest)!=NEW_MANIFEST:
        raise Hold('NEW_CARRIER_DIGEST_UNPROVEN')
    try:
        value=json.loads(new_manifest.decode('utf-8'))
    except (ValueError,UnicodeError):
        raise Hold('NEW_MANIFEST_INVALID')
    if (new_manifest!=canonical(value) or type(value) is not dict or
        set(value)!={'format','mode','install_root','files','updates_enabled'} or
        value['format']!=1 or type(value['format']) is not int or
        value['mode']!='STOPPED_HANDOFF_V1' or
        value['install_root']!=INSTALL_ROOT or value['updates_enabled'] is not False):
        raise Hold('NEW_MANIFEST_SCOPE_INVALID')
    return {'state':'SOURCE_HASHES_VERIFIED_LIVE_HANDOFF_HOLD',
            'old_manifest_sha256':OLD_MANIFEST,
            'new_archive_sha256':NEW_ARCHIVE,
            'new_manifest_sha256':NEW_MANIFEST,
            'site_executed':False,'bc_executed':False,
            'live_identity_verified':False,'retry_safe':False}

# This transaction engine accepts only a caller-supplied isolated parent fd and
# proven candidate bytes. It never opens the production root or runs B/C.
import os
import stat
import fcntl
import errno
import uuid

STATE='carrier-handoff-state-v1.json'
LOCK='community-update.lock'
OLD_NAME='control-stopped-v1'
STAGE='control-stopped-v1.handoff-stage'
ARCHIVE='control-stopped-v1.handoff-old'

def _identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns]

def _stat(parent,name):
    try:return os.stat(name,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return None

def _fsync_file(parent,name,body):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
    try:
        n=0
        while n<len(body):
            k=os.write(fd,body[n:]);assert k>0;n+=k
        os.fsync(fd)
    finally:os.close(fd)
    os.fsync(parent)

def _journal(parent):
    fd=os.open(STATE,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        b=os.read(fd,8193)
        if len(b)>8192:raise Hold('JOURNAL_OVERSIZE')
        result=json.loads(b.decode('utf-8'))
        if canonical(result)!=b:raise Hold('JOURNAL_NONCANONICAL')
        return result
    finally:os.close(fd)

def _read_member(parent,dirname,name):
    fd=os.open(dirname,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        leaf=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            st=os.fstat(leaf)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_size>65536:
                raise Hold('MEMBER_IDENTITY_UNKNOWN')
            body=os.read(leaf,65537)
            if len(body)!=st.st_size or _identity(st)!=_identity(os.fstat(leaf)):
                raise Hold('MEMBER_REPLACED')
            return body
        finally:os.close(leaf)
    finally:os.close(fd)

def _safe_dir(parent,name,root_uid):
    st=_stat(parent,name)
    if st is None or not stat.S_ISDIR(st.st_mode) or st.st_uid!=root_uid or stat.S_IMODE(st.st_mode)!=0o700:
        raise Hold('CARRIER_DIRECTORY_UNKNOWN')
    return _identity(st)

def status(parent):
    try:j=_journal(parent)
    except FileNotFoundError:return {'state':'NO_HANDOFF_JOURNAL','retry_safe':False}
    if j.get('format')!=1 or j.get('old_manifest')!=OLD_MANIFEST or j.get('new_manifest')!=NEW_MANIFEST:
        raise Hold('JOURNAL_BINDING_UNKNOWN')
    now={name:(_identity(_stat(parent,name)) if _stat(parent,name) is not None else None)
         for name in (OLD_NAME,STAGE,ARCHIVE)}
    if now[OLD_NAME]==j['new_identity'] and now[ARCHIVE]==j['old_identity'] and now[STAGE] is None:
        state='PUBLISHED_RECONCILED'
    elif now[OLD_NAME]==j['old_identity'] and now[ARCHIVE] is None:
        state='INTENT_ONLY_OR_STAGED'
    elif now[OLD_NAME] is None and now[ARCHIVE]==j['old_identity']:
        state='OLD_RETAINED_PUBLISH_UNKNOWN'
    else:state='UNKNOWN_INSPECT_ONLY'
    return {'state':state,'retry_safe':False,'attempt':j['attempt'],'journal':j,'observed':now}

def execute(parent,archive_bytes,manifest_bytes,old_target_identity,
            expected_parent_identity,root_uid=None,fault=None):
    # Deliberately inert for all real production paths: fd-based isolated review.
    if root_uid is None:raise Hold('ISOLATED_EXECUTION_IDENTITY_REQUIRED')
    if _identity(os.fstat(parent))!=expected_parent_identity:raise Hold('PARENT_IDENTITY_CHANGED')
    lock=os.open(LOCK,os.O_RDWR|os.O_NOFOLLOW,dir_fd=parent)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if _stat(parent,STATE) is not None or _stat(parent,ARCHIVE) is not None or _stat(parent,STAGE) is not None:
            raise Hold('EXISTING_OR_INFLIGHT_HANDOFF')
        old=_safe_dir(parent,OLD_NAME,root_uid)
        if old!=old_target_identity:raise Hold('OLD_IDENTITY_CHANGED')
        old_manifest=_read_member(parent,OLD_NAME,'manifest.json')
        verify_inputs(old_manifest,archive_bytes,manifest_bytes)
        # Reject a live transaction until all original writer and attempt
        # authorities are wired into this same held lease. This is a
        # deliberate blocker, not a recoverable exception.
        raise Hold('ORIGINAL_WRITER_AND_ATTEMPT_ADMISSION_NOT_BOUND')
    finally:os.close(lock)

def rollback(*args,**kwargs):
    raise Hold('ROLLBACK_OWNERSHIP_NOT_PROVEN')
