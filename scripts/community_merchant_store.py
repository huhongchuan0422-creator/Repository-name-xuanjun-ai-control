"""Isolated Stage5 tenant-scoped merchant catalog persistence. Offline, no login/payment."""
import sqlite3
from scripts.community_merchant_contract import scope, valid_id, text_ok, merchant_authorized

SCHEMA="""
CREATE TABLE merchant_profiles (
 tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
 name TEXT NOT NULL, description TEXT NOT NULL, contact TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ACTIVE','PAUSED')),
 version INTEGER NOT NULL CHECK(version>0),
 PRIMARY KEY(tenant_id,merchant_id,store_id)
);
CREATE TABLE catalog_items (
 tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
 item_id TEXT NOT NULL, name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ACTIVE','HIDDEN')),
 sort_order INTEGER NOT NULL, version INTEGER NOT NULL CHECK(version>0),
 PRIMARY KEY(tenant_id,merchant_id,store_id,item_id),
 FOREIGN KEY(tenant_id,merchant_id,store_id)
 REFERENCES merchant_profiles(tenant_id,merchant_id,store_id)
);
"""
def _catalog(db):
    return sorted(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL").fetchall())
def open_store(path=":memory:"):
    db=sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        template=sqlite3.connect(":memory:")
        try:
            template.executescript(SCHEMA)
            expected=_catalog(template)
        finally:template.close()
        actual=_catalog(db)
        if not actual and db.execute("PRAGMA user_version").fetchone()[0]==0:
            db.executescript("BEGIN IMMEDIATE;"+SCHEMA+"PRAGMA user_version=1;COMMIT;")
        elif actual!=expected or db.execute("PRAGMA user_version").fetchone()[0]!=1:
            raise ValueError("INVALID_MERCHANT_SCHEMA")
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("INVALID_MERCHANT_DATABASE")
        return db
    except BaseException:
        if db.in_transaction:db.rollback()
        db.close()
        raise
def upsert_profile(db,identity,actor,record,expected_version=None):
    t,m,s=scope(identity)
    if not merchant_authorized(actor,identity,"EDIT") or actor.get("role")!="MERCHANT_ADMIN":
        raise ValueError("MERCHANT_ADMIN_REQUIRED")
    if type(record) is not dict or set(record)!={"name","description","contact","status"} or record["status"] not in ("ACTIVE","PAUSED") or not text_ok(record["name"],120) or not text_ok(record["description"],2048) or not text_ok(record["contact"],120):
        raise ValueError("INVALID_PROFILE")
    if expected_version is not None and (type(expected_version) is not int or expected_version<1):raise ValueError("INVALID_VERSION")
    with db:
        old=db.execute("SELECT version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?",(t,m,s)).fetchone()
        if old is None:
            if expected_version is not None:raise ValueError("STALE_VERSION")
            db.execute("INSERT INTO merchant_profiles VALUES(?,?,?,?,?,?,?,1)",(t,m,s,record["name"],record["description"],record["contact"],record["status"]))
            version=1
        else:
            if expected_version!=old[0]:raise ValueError("STALE_VERSION")
            version=old[0]+1
            db.execute("UPDATE merchant_profiles SET name=?,description=?,contact=?,status=?,version=? WHERE tenant_id=? AND merchant_id=? AND store_id=? AND version=?",(record["name"],record["description"],record["contact"],record["status"],version,t,m,s,old[0]))
    return {"version":version}
def profile(db,identity):
    t,m,s=scope(identity)
    row=db.execute("SELECT name,description,contact,status,version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?",(t,m,s)).fetchone()
    if row is None or row[3]!="ACTIVE":raise ValueError("UNAVAILABLE_STOREFRONT")
    return dict(zip(("name","description","contact","status","version"),row))
def put_item(db,identity,actor,item):
    t,m,s=scope(identity)
    if not merchant_authorized(actor,identity,"EDIT"):raise ValueError("ACCESS_DENIED")
    if type(item) is not dict or set(item)!={"id","name","status","sort"} or not valid_id(item["id"]) or not text_ok(item["name"],120) or item["status"] not in ("ACTIVE","HIDDEN") or type(item["sort"]) is not int:raise ValueError("INVALID_ITEM")
    with db:
        db.execute("INSERT INTO catalog_items VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(tenant_id,merchant_id,store_id,item_id) DO UPDATE SET name=excluded.name,status=excluded.status,sort_order=excluded.sort_order,version=catalog_items.version+1",(t,m,s,item["id"],item["name"],item["status"],item["sort"]))
def list_items(db,identity,limit=100):
    t,m,s=scope(identity)
    if type(limit) is not int or not 1<=limit<=100:raise ValueError("INVALID_LIMIT")
    rows=db.execute("SELECT item_id,name,sort_order FROM catalog_items WHERE tenant_id=? AND merchant_id=? AND store_id=? AND status='ACTIVE' ORDER BY sort_order,item_id LIMIT ?",(t,m,s,limit)).fetchall()
    return [{"id":x[0],"name":x[1],"sort":x[2]} for x in rows]
