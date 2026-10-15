"""Stage5 Phase2 verified offline SQLite backup; no production deployment.

Backups are only created from explicitly passed offline stores. Recovery is
manual: this module never overwrites live storage, processes money or grants.
"""
import hashlib
import os
import pathlib
import sqlite3
import tempfile

def _file(path):
    p=pathlib.Path(path).resolve()
    if not p.is_file() or p.is_symlink():raise ValueError("SOURCE_DB_MISSING")
    return p

def backup(source_path, output_path):
    src=_file(source_path)
    dest=pathlib.Path(output_path).resolve()
    if dest==src or dest.exists():raise ValueError("BACKUP_PATH_UNSAFE")
    dest.parent.mkdir(parents=True,exist_ok=True)
    handle=None
    db=sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("SOURCE_DB_INTEGRITY")
        tmp=tempfile.NamedTemporaryFile(dir=str(dest.parent),suffix=".sqlite",delete=False)
        temp=pathlib.Path(tmp.name);tmp.close()
        try:
            handle=sqlite3.connect(temp)
            db.backup(handle)
            if handle.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise ValueError("BACKUP_INTEGRITY")
            handle.close();handle=None
            raw=temp.read_bytes()
            os.replace(temp,dest)
            return {"sha256":hashlib.sha256(raw).hexdigest(),
                    "size_bytes":len(raw),
                    "destination":str(dest),
                    "restored":False}
        finally:
            if handle is not None:handle.close()
            if temp.exists():temp.unlink()
    finally:db.close()

def verify_backup(path,expected_sha256):
    if type(expected_sha256) is not str or len(expected_sha256)!=64:
        raise ValueError("INVALID_BACKUP_DIGEST")
    p=_file(path)
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if digest!=expected_sha256:raise ValueError("BACKUP_DIGEST_MISMATCH")
    db=sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("BACKUP_INTEGRITY")
    finally:db.close()
    return {"verified":True,"restored":False,"production_release_authorized":False}
