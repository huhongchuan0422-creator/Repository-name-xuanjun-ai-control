"""Same-intent backup recovery under the original Host's exclusive locks.
No restore, account mutation, password reset, or authority is supplied here.
"""
import hashlib
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote
from scripts.pr122_customer_core import canonical, digest, Denied


def logical_digest(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        # Original Center uses sqlite3.Row.
        if [tuple(r) for r in db.execute('PRAGMA integrity_check')] != [('ok',)]:
            raise Denied('RECOVERY_DATABASE_INTEGRITY_REQUIRED')
    if list(db.execute('PRAGMA foreign_key_check')):
        raise Denied('RECOVERY_DATABASE_INTEGRITY_REQUIRED')
    h=hashlib.sha256()
    for line in db.iterdump():
        body=line.encode('utf-8');h.update(str(len(body)).encode('ascii')+b':'+body)
    return h.hexdigest()


def ensure_backup(center, path, uid, execution_sha, request_id, inspect_only=False):
    """Resume only our durable intent and unchanged complete logical database.

    Called with original Center inode/runtime locks held, before bootstrap tx.
    A legacy backup lacking this intent is not adopted or overwritten.
    """
    from scripts.community_admin_bootstrap import _regular, _record_identity, _backup
    from scripts.community_mini_host_config import load_protected
    from scripts.pr122_customer_core import identifier
    identifier(request_id)
    if type(execution_sha) is not str or len(execution_sha)!=64 or any(x not in '0123456789abcdef' for x in execution_sha):
        raise Denied('EXACT_RECOVERY_INTENT_REQUIRED')
    dbpath=center.db.execute('PRAGMA database_list').fetchone()[2]
    current_info=_regular(dbpath,uid)
    current=logical_digest(center.db)
    intent_path=path+'.recovery-intent.json';receipt_path=path+'.recovery-receipt.json'
    intent=dict(version=1,request_id=request_id,execution_sha256=execution_sha,
                center_dev=current_info.st_dev,center_ino=current_info.st_ino,
                backup_path=path,logical_sha256=current)
    if os.path.lexists(intent_path):
        _regular(intent_path,uid)
        if load_protected(intent_path)!=intent:raise Denied('RECOVERY_INTENT_OR_CURRENT_CHANGED')
    else:
        if os.path.lexists(path) or os.path.lexists(receipt_path):raise Denied('UNBOUND_EXISTING_BACKUP')
        if inspect_only:return dict(phase='NOT_STARTED',mutation=False)
        _record_identity(intent_path,intent,uid)
    if not os.path.lexists(path):
        if os.path.lexists(receipt_path):raise Denied('RECOVERY_BACKUP_MISSING')
        if inspect_only:return dict(phase='INTENT_ONLY_BACKUP_NOT_CREATED',mutation=False)
        _backup(center,path,uid)
    before=_regular(path,uid)
    backup=sqlite3.connect('file:'+quote(path,safe='/')+'?mode=ro',uri=True)
    try:
        backup.execute('PRAGMA query_only=ON')
        if logical_digest(backup)!=current:raise Denied('RECOVERY_BACKUP_OR_CURRENT_CHANGED')
    finally:backup.close()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        actual=os.fstat(fd)
        if (actual.st_dev,actual.st_ino)!=(before.st_dev,before.st_ino):raise Denied('RECOVERY_BACKUP_REPLACED')
        h=hashlib.sha256()
        while True:
            block=os.read(fd,1024*1024)
            if not block:break
            h.update(block)
        after=os.fstat(fd)
    finally:os.close(fd)
    final=_regular(path,uid)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if identity(before)!=identity(after) or identity(after)!=identity(final):raise Denied('RECOVERY_BACKUP_REPLACED')
    if logical_digest(center.db)!=current:raise Denied('RECOVERY_CURRENT_CHANGED')
    receipt=dict(version=1,intent_sha256=digest(canonical(intent)),backup_sha256=h.hexdigest(),
                 backup_dev=final.st_dev,backup_ino=final.st_ino,backup_bytes=final.st_size)
    if inspect_only:
        if os.path.lexists(receipt_path):
            _regular(receipt_path,uid)
            if load_protected(receipt_path)!=receipt:raise Denied('RECOVERY_RECEIPT_CHANGED')
        return dict(phase='VERIFIED_BACKUP_CURRENT_UNCHANGED_NOT_COMMITTED',backup_sha256=receipt['backup_sha256'],mutation=False)
    _record_identity(receipt_path,receipt,uid)
    return receipt['backup_sha256']
