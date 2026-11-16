"""Standalone, offline Stage5 advertisement persistence and API contracts.

A consumer of this library must authenticate the session and payment evidence.
No HTTP listener, payment mutation, network calls or production configuration.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from scripts.community_ad_contract import AMOUNT, SUCCESS, SLOTS, safe_creative_url, ALLOWED_TRANSITIONS

SCHEMA = """
CREATE TABLE campaigns (
  tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL, slot TEXT NOT NULL CHECK(slot IN ('AD_SLOT_PAYMENT_AMOUNT','AD_SLOT_PAYMENT_SUCCESS')),
  status TEXT NOT NULL CHECK(status IN ('DRAFT','REVIEW','APPROVED','ACTIVE','PAUSED','REJECTED','ARCHIVED')),
  moderation TEXT NOT NULL CHECK(moderation IN ('PENDING','APPROVED','REJECTED')),
  priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 100000),
  starts_at INTEGER NOT NULL, ends_at INTEGER NOT NULL,
  title TEXT NOT NULL, target_url TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
  PRIMARY KEY(tenant_id,merchant_id,store_id,campaign_id),
  CHECK(starts_at < ends_at)
);
CREATE INDEX campaigns_live ON campaigns(tenant_id,merchant_id,store_id,slot,status,starts_at,ends_at,priority);
CREATE TABLE metric_events (
  tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
  slot TEXT NOT NULL CHECK(slot IN ('AD_SLOT_PAYMENT_AMOUNT','AD_SLOT_PAYMENT_SUCCESS')),
  kind TEXT NOT NULL CHECK(kind IN ('IMPRESSION','CLICK')),
  event_id TEXT NOT NULL, campaign_id TEXT NOT NULL, created_at INTEGER NOT NULL,
  PRIMARY KEY(tenant_id,merchant_id,store_id,slot,kind,event_id)
);
CREATE TABLE audit_events (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL, merchant_id TEXT NOT NULL, store_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL,
  previous_version INTEGER, new_version INTEGER, happened_at INTEGER NOT NULL,
  previous_hash TEXT, new_hash TEXT
);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'AUDIT_APPEND_ONLY'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'AUDIT_APPEND_ONLY'); END;
"""

def _schema_catalog(db):
    return sorted((typ, name, table, statement)
                  for typ, name, table, statement in db.execute(
                      "SELECT type,name,tbl_name,sql FROM sqlite_master "
                      "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"))

def open_offline(path=":memory:"):
    """Create only an empty schema; reopen only an exact compatible schema."""
    db=sqlite3.connect(path, isolation_level="DEFERRED")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        existing=_schema_catalog(db)
        expected=sqlite3.connect(":memory:")
        try:
            expected.executescript(SCHEMA)
            target=_schema_catalog(expected)
        finally:
            expected.close()
        if not existing:
            if db.execute("PRAGMA user_version").fetchone()[0] != 0:
                raise ValueError("INCOMPATIBLE_AD_SCHEMA")
            db.executescript("BEGIN IMMEDIATE;" + SCHEMA + "PRAGMA user_version=1; COMMIT;")
        elif existing != target:
            raise ValueError("INCOMPATIBLE_AD_SCHEMA")
        version=db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0,1):
            raise ValueError("INCOMPATIBLE_AD_SCHEMA")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("INVALID_AD_DATABASE")
        return db
    except BaseException:
        if db.in_transaction:
            db.rollback()
        db.close()
        raise

def _scope(scope):
    if not isinstance(scope, dict) or set(scope) != {"tenant_id","merchant_id","store_id"}:
        raise ValueError("INVALID_SCOPE")
    values=tuple(scope[k] for k in ("tenant_id","merchant_id","store_id"))
    if not all(isinstance(x,str) and 1<=len(x)<=100 and x.isascii() and x.replace("_","").replace("-","").isalnum() for x in values):
        raise ValueError("INVALID_SCOPE")
    return values

def _now(value):
    if type(value) is not int or not 0<=value<=253402300799:
        raise ValueError("INVALID_TIME")
    return value

def create_campaign(db,scope,record,actor,now):
    """Transactional creation; internal caller must supply authenticated actor."""
    t,m,s=_scope(scope); _now(now)
    if not isinstance(actor,dict) or actor.get("authenticated") is not True or actor.get("role") not in ("MERCHANT_ADMIN","PLATFORM_ADMIN") or not isinstance(actor.get("actor_id"),str) or not actor["actor_id"]:
        raise ValueError("UNAUTHENTICATED_ACTOR")
    if actor["role"]=="MERCHANT_ADMIN" and (actor.get("tenant_id"),actor.get("merchant_id"))!=(t,m):
        raise ValueError("CROSS_TENANT_DENIED")
    if not isinstance(record,dict) or set(record)!={"id","slot","starts_at","ends_at","title","target_url","priority"}:
        raise ValueError("INVALID_CAMPAIGN")
    cid=record["id"]
    if not isinstance(cid,str) or not cid.isascii() or not 1<=len(cid)<=100 or not cid.replace("-","").replace("_","").isalnum():
        raise ValueError("INVALID_CAMPAIGN_ID")
    if record["slot"] not in SLOTS or type(record["priority"]) is not int or not 0<=record["priority"]<=100000:
        raise ValueError("INVALID_CAMPAIGN_SETTINGS")
    start,end=_now(record["starts_at"]),_now(record["ends_at"])
    if start>=end or not isinstance(record["title"],str) or not 1<=len(record["title"])<=160 or not safe_creative_url(record["target_url"]):
        raise ValueError("INVALID_CREATIVE")
    with db:
        db.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (t,m,s,cid,record["slot"],"DRAFT","PENDING",record["priority"],start,end,record["title"],record["target_url"],1))
        db.execute("INSERT INTO audit_events(tenant_id,merchant_id,store_id,campaign_id,actor_id,action,previous_version,new_version,happened_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (t,m,s,cid,actor["actor_id"],"CREATE",None,1,now))
    return {"campaign_id":cid,"version":1,"status":"DRAFT","publication":False}

def list_campaigns(db,scope,limit=50,after_id=""):
    t,m,s=_scope(scope)
    if type(limit) is not int or not 1<=limit<=200 or not isinstance(after_id,str) or len(after_id)>100:
        raise ValueError("INVALID_PAGE")
    rows=db.execute("SELECT campaign_id,slot,status,moderation,priority,version FROM campaigns WHERE tenant_id=? AND merchant_id=? AND store_id=? AND campaign_id>? ORDER BY campaign_id LIMIT ?",
                    (t,m,s,after_id,limit+1)).fetchall()
    return {"campaigns":[dict(zip(("id","slot","status","moderation","priority","version"),row)) for row in rows[:limit]],
            "has_more":len(rows)>limit,"next_cursor":rows[limit-1][0] if len(rows)>limit else None}

def choose(db,scope,slot,now):
    t,m,s=_scope(scope); _now(now)
    if slot not in SLOTS: raise ValueError("INVALID_SLOT")
    row=db.execute("SELECT campaign_id,title,target_url FROM campaigns WHERE tenant_id=? AND merchant_id=? AND store_id=? AND slot=? AND status='ACTIVE' AND moderation='APPROVED' AND starts_at<=? AND ends_at>? ORDER BY priority DESC,campaign_id LIMIT 1",
                   (t,m,s,slot,now,now)).fetchone()
    return None if row is None else {"id":row[0],"title":row[1],"url":row[2],"slot":slot}

def record_metric(db,scope,slot,kind,event_id,campaign_id,now):
    t,m,s=_scope(scope);_now(now)
    if slot not in SLOTS or kind not in ("IMPRESSION","CLICK") or not all(isinstance(v,str) and 1<=len(v)<=100 for v in (event_id,campaign_id)):
        raise ValueError("INVALID_METRIC")
    if db.execute("SELECT 1 FROM campaigns WHERE tenant_id=? AND merchant_id=? AND store_id=? AND campaign_id=? AND slot=?",
                  (t,m,s,campaign_id,slot)).fetchone() is None:
        raise ValueError("UNKNOWN_CAMPAIGN")
    with db:
        cur=db.execute("INSERT OR IGNORE INTO metric_events VALUES(?,?,?,?,?,?,?,?)",
                       (t,m,s,slot,kind,event_id,campaign_id,now))
    return {"recorded":cur.rowcount==1,"payment_affected":False}

def change_campaign_state(db, scope, campaign_id, next_state, actor, now, expected_version):
    """Bound optimistic state transition; no public authentication shortcut."""
    t,m,s=_scope(scope);_now(now)
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("INVALID_VERSION")
    if not isinstance(campaign_id,str) or not campaign_id or len(campaign_id)>100:
        raise ValueError("INVALID_CAMPAIGN_ID")
    if not isinstance(next_state,str) or next_state not in ALLOWED_TRANSITIONS:
        raise ValueError("INVALID_STATE")
    if (not isinstance(actor,dict) or actor.get("authenticated") is not True or
        actor.get("role") not in ("MERCHANT_ADMIN","PLATFORM_ADMIN") or
        not isinstance(actor.get("actor_id"),str) or not actor["actor_id"]):
        raise ValueError("UNAUTHENTICATED_ACTOR")
    if actor["role"]=="MERCHANT_ADMIN" and (actor.get("tenant_id"),actor.get("merchant_id"))!=(t,m):
        raise ValueError("CROSS_TENANT_DENIED")
    with db:
        row=db.execute("SELECT status,moderation,version FROM campaigns WHERE tenant_id=? AND merchant_id=? AND store_id=? AND campaign_id=?",
                       (t,m,s,campaign_id)).fetchone()
        if row is None: raise ValueError("UNKNOWN_CAMPAIGN")
        previous,moderation,version=row
        if version!=expected_version: raise ValueError("STALE_VERSION")
        if next_state not in ALLOWED_TRANSITIONS[previous]: raise ValueError("INVALID_TRANSITION")
        if next_state=="ACTIVE" and moderation!="APPROVED": raise ValueError("MODERATION_REQUIRED")
        changed=db.execute("UPDATE campaigns SET status=?,version=version+1 WHERE tenant_id=? AND merchant_id=? AND store_id=? AND campaign_id=? AND version=?",
                           (next_state,t,m,s,campaign_id,expected_version))
        if changed.rowcount!=1: raise ValueError("CONCURRENT_VERSION_CHANGE")
        db.execute("INSERT INTO audit_events(tenant_id,merchant_id,store_id,campaign_id,actor_id,action,previous_version,new_version,happened_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (t,m,s,campaign_id,actor["actor_id"],"STATUS_"+next_state,version,version+1,now))
    return {"id":campaign_id,"state":next_state,"version":version+1}

def review_creative(db, scope, campaign_id, approved, actor, now, expected_version):
    """Only trusted platform moderator can record approval/rejection in local store."""
    t,m,s=_scope(scope);_now(now)
    if (not isinstance(actor,dict) or actor.get("authenticated") is not True or
        actor.get("role")!="PLATFORM_ADMIN" or not isinstance(actor.get("actor_id"),str)
        or not actor["actor_id"] or type(approved) is not bool or
        type(expected_version) is not int or expected_version < 1):
        raise ValueError("MODERATOR_REQUIRED")
    verdict="APPROVED" if approved else "REJECTED"
    with db:
        row=db.execute("SELECT status,version FROM campaigns WHERE tenant_id=? AND merchant_id=? AND store_id=? AND campaign_id=?",
                       (t,m,s,campaign_id)).fetchone()
        if row is None: raise ValueError("UNKNOWN_CAMPAIGN")
        if row[1]!=expected_version: raise ValueError("STALE_VERSION")
        if row[0] not in ("REVIEW","APPROVED","PAUSED"): raise ValueError("INVALID_REVIEW_STAGE")
        if db.execute("UPDATE campaigns SET moderation=?,version=version+1 WHERE tenant_id=? AND merchant_id=? AND store_id=? AND campaign_id=? AND version=?",
                      (verdict,t,m,s,campaign_id,expected_version)).rowcount!=1:
            raise ValueError("CONCURRENT_VERSION_CHANGE")
        db.execute("INSERT INTO audit_events(tenant_id,merchant_id,store_id,campaign_id,actor_id,action,previous_version,new_version,happened_at) VALUES(?,?,?,?,?,?,?,?,?)",
                   (t,m,s,campaign_id,actor["actor_id"],"MODERATION_"+verdict,expected_version,expected_version+1,now))
    return {"id":campaign_id,"moderation":verdict,"version":expected_version+1}
