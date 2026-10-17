"""Offline proof-of-contract for SaaS cross-channel identity and audit evidence.

Never trusts channel username or self-asserted customer. Production connectors must
verify Telegram webhook/Feishu signatures and authenticated web identity upstream.
"""
import hashlib
import hmac
import json
import secrets
import sqlite3

DDL="""
CREATE TABLE IF NOT EXISTS visual_identity_links(
 channel TEXT NOT NULL,subject_id TEXT NOT NULL,customer_id TEXT NOT NULL,
 tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,verified_at INTEGER NOT NULL,
 PRIMARY KEY(channel,subject_id));
CREATE TABLE IF NOT EXISTS visual_link_challenges(
 token_sha256 TEXT PRIMARY KEY,customer_id TEXT NOT NULL,tenant_id TEXT NOT NULL,
 project_id TEXT NOT NULL,expires_at INTEGER NOT NULL,consumed_at INTEGER);
CREATE TABLE IF NOT EXISTS visual_message_evidence(
 event_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,tenant_id TEXT NOT NULL,
 project_id TEXT NOT NULL,channel TEXT NOT NULL,subject_id TEXT NOT NULL,
 occurred_at INTEGER NOT NULL,body TEXT NOT NULL,previous_sha256 TEXT NOT NULL,
 record_sha256 TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS visual_message_no_update BEFORE UPDATE ON visual_message_evidence
BEGIN SELECT RAISE(ABORT,'EVIDENCE_APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS visual_message_no_delete BEFORE DELETE ON visual_message_evidence
BEGIN SELECT RAISE(ABORT,'EVIDENCE_APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS visual_message_no_replace BEFORE INSERT ON visual_message_evidence
WHEN EXISTS(SELECT 1 FROM visual_message_evidence WHERE event_id=NEW.event_id)
BEGIN SELECT RAISE(ABORT,'EVIDENCE_APPEND_ONLY'); END;
"""
def install(db):
    if not isinstance(db,sqlite3.Connection):raise TypeError("SQLITE_REQUIRED")
    if db.in_transaction:raise ValueError("DDL_TRANSACTION_ACTIVE")
    db.executescript("BEGIN IMMEDIATE;"+DDL+"COMMIT;")

def challenge(db,authenticated_customer,tenant,project,now,ttl=300):
    if not authenticated_customer or not tenant or not project or type(now) is not int:
        raise ValueError("TRUSTED_IDENTITY_REQUIRED")
    if type(ttl) is not int or ttl<1 or ttl>600:raise ValueError("INVALID_TTL")
    token=secrets.token_urlsafe(32)
    db.execute("INSERT INTO visual_link_challenges VALUES(?,?,?,?,?,NULL)",
        (hashlib.sha256(token.encode()).hexdigest(),authenticated_customer,tenant,project,now+ttl))
    db.commit()
    return token

def link(db,token,channel,verified_subject,now,verified_provider=False):
    if not verified_provider or channel not in ("TELEGRAM","FEISHU","WEB") or not verified_subject:
        raise PermissionError("VERIFIED_PROVIDER_REQUIRED")
    if type(now) is not int or type(token) is not str:raise ValueError("INVALID_CONTEXT")
    digest=hashlib.sha256(token.encode()).hexdigest()
    db.execute("BEGIN IMMEDIATE")
    try:
        row=db.execute("SELECT customer_id,tenant_id,project_id,expires_at,consumed_at FROM visual_link_challenges WHERE token_sha256=?",(digest,)).fetchone()
        if not row or row[4] is not None or row[3]<now:raise ValueError("CHALLENGE_NOT_VALID")
        existing=db.execute("SELECT customer_id,tenant_id,project_id FROM visual_identity_links WHERE channel=? AND subject_id=?",(channel,verified_subject)).fetchone()
        if existing and existing!=row[:3]:raise PermissionError("IDENTITY_CONFLICT")
        if not existing:db.execute("INSERT INTO visual_identity_links VALUES(?,?,?,?,?,?)",(channel,verified_subject,*row[:3],now))
        db.execute("UPDATE visual_link_challenges SET consumed_at=? WHERE token_sha256=?",(now,digest))
        db.commit()
        return {"customer_id":row[0],"tenant_id":row[1],"project_id":row[2],"linked":True}
    except BaseException:
        db.rollback();raise

def append_message(db,event_id,channel,verified_subject,project,text,now,verified_provider=False):
    if not verified_provider:raise PermissionError("VERIFIED_PROVIDER_REQUIRED")
    if type(text) is not str or not text.strip() or len(text)>12000:
        raise ValueError("INVALID_MESSAGE")
    if type(now) is not int or type(event_id) is not str or not event_id:
        raise ValueError("INVALID_EVENT")
    db.execute("BEGIN IMMEDIATE")
    try:
        row=db.execute("SELECT customer_id,tenant_id,project_id FROM visual_identity_links WHERE channel=? AND subject_id=?",(channel,verified_subject)).fetchone()
        if not row or project!=row[2]:raise PermissionError("LINKED_PROJECT_REQUIRED")
        existing=db.execute("SELECT record_sha256 FROM visual_message_evidence WHERE event_id=?",(event_id,)).fetchone()
        if existing:raise ValueError("DUPLICATE_EVIDENCE_EVENT")
        previous=db.execute("SELECT record_sha256 FROM visual_message_evidence WHERE customer_id=? AND tenant_id=? AND project_id=? ORDER BY rowid DESC LIMIT 1",row).fetchone()
        parent=previous[0] if previous else "0"*64
        value=[event_id,*row,channel,verified_subject,now,text,parent]
        digest=hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        db.execute("INSERT INTO visual_message_evidence VALUES(?,?,?,?,?,?,?,?,?,?)",(event_id,*row,channel,verified_subject,now,text,parent,digest))
        db.commit()
        return {"event_id":event_id,"customer_id":row[0],"record_sha256":digest,"saved":True}
    except BaseException:db.rollback();raise

def history(db,authenticated_customer,tenant,project):
    if not authenticated_customer or not tenant or not project:raise PermissionError("AUTH_REQUIRED")
    return [{"channel":r[0],"occurred_at":r[1],"text":r[2],"record_sha256":r[3]}
      for r in db.execute("SELECT channel,occurred_at,body,record_sha256 FROM visual_message_evidence WHERE customer_id=? AND tenant_id=? AND project_id=? ORDER BY rowid",(authenticated_customer,tenant,project))]
