"""Isolated Stage5 tenant-scoped merchant catalog persistence. Offline, no login/payment."""
import sqlite3
from scripts.community_merchant_contract import scope, valid_id, text_ok, merchant_authorized

SCHEMA_V1="""
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
CONTENT_SCHEMA="""
CREATE TABLE catalog_item_content (
 tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
 item_id TEXT NOT NULL, description TEXT NOT NULL, image_name TEXT NOT NULL,
 image_data TEXT NOT NULL,
 PRIMARY KEY(tenant_id,merchant_id,store_id,item_id),
 FOREIGN KEY(tenant_id,merchant_id,store_id,item_id)
 REFERENCES catalog_items(tenant_id,merchant_id,store_id,item_id) ON DELETE CASCADE
);
"""
SCHEMA=SCHEMA_V1+CONTENT_SCHEMA
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
            db.executescript("BEGIN IMMEDIATE;"+SCHEMA+"PRAGMA user_version=2;COMMIT;")
            actual=_catalog(db)
        elif db.execute("PRAGMA user_version").fetchone()[0]==1:
            legacy=sqlite3.connect(":memory:")
            try:
                legacy.executescript(SCHEMA_V1)
                if actual!=_catalog(legacy):raise ValueError("INVALID_MERCHANT_SCHEMA")
            finally:legacy.close()
            db.executescript("BEGIN IMMEDIATE;"+CONTENT_SCHEMA+"PRAGMA user_version=2;COMMIT;")
            actual=_catalog(db)
        if actual!=expected or db.execute("PRAGMA user_version").fetchone()[0]!=2:
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
            updated=db.execute("UPDATE merchant_profiles SET name=?,description=?,contact=?,status=?,version=? WHERE tenant_id=? AND merchant_id=? AND store_id=? AND version=?",(record["name"],record["description"],record["contact"],record["status"],version,t,m,s,old[0]))
            if updated.rowcount!=1:raise ValueError("STALE_VERSION")
    return {"version":version}
def profile(db,identity):
    t,m,s=scope(identity)
    row=db.execute("SELECT name,description,contact,status,version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?",(t,m,s)).fetchone()
    if row is None or row[3]!="ACTIVE":raise ValueError("UNAVAILABLE_STOREFRONT")
    return dict(zip(("name","description","contact","status","version"),row))
def put_item(db,identity,actor,item):
    t,m,s=scope(identity)
    if not merchant_authorized(actor,identity,"EDIT"):raise ValueError("ACCESS_DENIED")
    legacy=type(item) is dict and set(item)=={"id","name","status","sort"}
    complete=type(item) is dict and set(item)=={"id","name","description","image_name","image_data","status","sort"}
    if not (legacy or complete) or not valid_id(item["id"]) or not text_ok(item["name"],120) or item["status"] not in ("ACTIVE","HIDDEN") or type(item["sort"]) is not int:raise ValueError("INVALID_ITEM")
    description=item.get("description","");image_name=item.get("image_name","");image_data=item.get("image_data","")
    if complete and (not text_ok(description,2000) or not text_ok(image_name,160) or not isinstance(image_data,str) or len(image_data)>750000 or not image_data.startswith("data:image/") or ";base64," not in image_data):raise ValueError("INVALID_ITEM_CONTENT")
    with db:
        db.execute("INSERT INTO catalog_items VALUES(?,?,?,?,?,?,?,1) ON CONFLICT(tenant_id,merchant_id,store_id,item_id) DO UPDATE SET name=excluded.name,status=excluded.status,sort_order=excluded.sort_order,version=catalog_items.version+1",(t,m,s,item["id"],item["name"],item["status"],item["sort"]))
        if complete:db.execute("INSERT INTO catalog_item_content VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id,merchant_id,store_id,item_id) DO UPDATE SET description=excluded.description,image_name=excluded.image_name,image_data=excluded.image_data",(t,m,s,item["id"],description,image_name,image_data))
def list_items(db,identity,limit=100):
    t,m,s=scope(identity)
    if type(limit) is not int or not 1<=limit<=100:raise ValueError("INVALID_LIMIT")
    rows=db.execute("SELECT i.item_id,i.name,i.sort_order,COALESCE(c.description,''),COALESCE(c.image_name,''),COALESCE(c.image_data,'') FROM catalog_items i LEFT JOIN catalog_item_content c ON c.tenant_id=i.tenant_id AND c.merchant_id=i.merchant_id AND c.store_id=i.store_id AND c.item_id=i.item_id WHERE i.tenant_id=? AND i.merchant_id=? AND i.store_id=? AND i.status='ACTIVE' ORDER BY i.sort_order,i.item_id LIMIT ?",(t,m,s,limit)).fetchall()
    return [{"id":x[0],"name":x[1],"sort":x[2],"description":x[3],"image_name":x[4],"image_data":x[5]} for x in rows]
