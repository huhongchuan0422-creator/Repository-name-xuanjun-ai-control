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

def cross_store_audit(quote_db,order_db,tenant_id):
    """Read-only, per-tenant integrity audit across separate SQLite files.

    A cross-database sale is NOT atomic. This audit detects inconsistency and
    returns HOLD rather than inventing a successful payment or restoration.
    """
    from scripts.community_merchant_contract import valid_id
    from scripts.community_saas_order_preparation import quote_provenance,status
    from scripts.community_saas_offer_catalog import read_quote
    if type(tenant_id) is not str or not valid_id(tenant_id):
        raise ValueError("INVALID_TENANT")
    rows=order_db.execute(
        "SELECT order_id,quote_id FROM saas_order_preparations "
        "WHERE tenant_id=? ORDER BY order_id",(tenant_id,)).fetchall()
    pending=[]
    for order_id,quote_id in rows:
        try:
            quote_provenance(order_db,order_id,tenant_id)
            read_quote(quote_db,quote_id,tenant_id)
            status(order_db,order_id,tenant_id)
        except (ValueError,sqlite3.DatabaseError):
            pending.append(order_id)
    return {"tenant_id":tenant_id,"orders_checked":len(rows),
            "integrity_hold":pending,"approval_for_payment":False,
            "automatic_repair_executed":False,
            "cross_database_atomicity_proven":False}

def rollback_preview(backup_path, expected_sha256, target_path):
    """Read-only plan. Never replace a live database automatically."""
    verified=verify_backup(backup_path,expected_sha256)
    target=pathlib.Path(target_path).resolve()
    saved=pathlib.Path(backup_path).resolve()
    if target==saved:
        raise ValueError("ROLLBACK_SOURCE_EQUALS_TARGET")
    return {"backup_verified":verified["verified"],
            "target":str(target),"source":str(saved),
            "requires_manual_service_stop":True,
            "requires_authorized_restore":True,
            "rollback_executed":False,"production_gate":"HOLD"}
