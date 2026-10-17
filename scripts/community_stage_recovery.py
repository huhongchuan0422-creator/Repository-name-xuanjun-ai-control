"""Exclusive candidate snapshot/restore of original six community stores.

Center backup belongs to the existing Center owner. No host installation or
in-place rollback exists here. Restores always create a new private directory.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import stat
from pathlib import Path

NAMES=('orders','merchants','ads','refunds','modules','saas-orders')

def _private_root(path):
    root=Path(path)
    for part in (root,*root.parents):
        if part.is_symlink():raise ValueError('SYMLINK_PATH_DENIED')
    if not root.is_dir() or stat.S_IMODE(root.stat().st_mode)!=0o700:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    return root

def _create(path):
    root=Path(path)
    for part in (root,*root.parents):
        if part.is_symlink():raise ValueError('SYMLINK_PATH_DENIED')
    root.mkdir(mode=0o700)
    return _private_root(root)

def _read(root,name,limit):
    fd=os.open(str(root/name),os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:
            raise ValueError('INVALID_SNAPSHOT_FILE')
        return stream.read(limit+1)

def _integrity(path):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SNAPSHOT_INTEGRITY_FAILED')
    finally:db.close()

def snapshot(application,destination):
    from scripts.community_mini_application import MiniApplication
    if type(application) is not MiniApplication or application.stage is None or application.server is not None:
        raise PermissionError('STOPPED_ADMITTED_APPLICATION_REQUIRED')
    if application.center.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0]!='1':
        raise PermissionError('EXISTING_CENTER_MAINTENANCE_REQUIRED')
    stage=application.stage
    if len(stage.handles)!=len(NAMES) or any(db.in_transaction for db in stage.handles):
        raise PermissionError('COMMITTED_STORES_REQUIRED')
    root=_create(destination)
    try:
        files={}
        for name,db in zip(NAMES,stage.handles):
            target=root/(name+'.sqlite')
            fd=os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            out=sqlite3.connect(str(target))
            try:db.backup(out);out.execute('PRAGMA journal_mode=DELETE');out.commit()
            finally:out.close()
            _integrity(target)
            files[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
        manifest={'format':1,'purpose':'OFFLINE_RESTORE_CANDIDATE','cross_database_atomic':False,
                  'center_backup':'EXISTING_CENTER_OWNER_REQUIRED','payment_enabled':False,'files':files}
        raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
        fd=os.open(str(root/'snapshot.json'),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        return {'manifest_sha256':hashlib.sha256(raw).hexdigest(),'files':files,
                'cross_database_atomic':False,'center_backup':'EXISTING_CENTER_OWNER_REQUIRED'}
    except BaseException:
        shutil.rmtree(root)
        raise

def restore(source,expected_manifest_sha256,destination):
    """Verify a separately retained digest; never overwrite an existing target."""
    root=_private_root(source)
    raw=_read(root,'snapshot.json',32768)
    if type(expected_manifest_sha256) is not str or hashlib.sha256(raw).hexdigest()!=expected_manifest_sha256:
        raise ValueError('SNAPSHOT_MANIFEST_MISMATCH')
    manifest=json.loads(raw)
    expected={n+'.sqlite' for n in NAMES}
    if (type(manifest) is not dict or set(manifest)!={'format','purpose','cross_database_atomic','center_backup','payment_enabled','files'}
            or manifest['format']!=1 or manifest['purpose']!='OFFLINE_RESTORE_CANDIDATE'
            or manifest['cross_database_atomic'] is not False or manifest['payment_enabled'] is not False
            or manifest['center_backup']!='EXISTING_CENTER_OWNER_REQUIRED'
            or type(manifest['files']) is not dict or set(manifest['files'])!=expected
            or set(p.name for p in root.iterdir())!=expected|{'snapshot.json'}):
        raise ValueError('SNAPSHOT_MANIFEST_INVALID')
    # Validate all bytes before creating any restore destination.
    blobs={}
    for name in sorted(expected):
        blob=_read(root,name,128*1024*1024)
        if hashlib.sha256(blob).hexdigest()!=manifest['files'][name]:raise ValueError('SNAPSHOT_FILE_MISMATCH')
        blobs[name]=blob
    target=_create(destination)
    try:
        for name,blob in blobs.items():
            fd=os.open(str(target/name),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(blob)
            _integrity(target/name)
        return {'restored':True,'production_installed':False,'payment_enabled':False,
                'center_backup':'EXISTING_CENTER_OWNER_REQUIRED'}
    except BaseException:
        shutil.rmtree(target)
        raise
