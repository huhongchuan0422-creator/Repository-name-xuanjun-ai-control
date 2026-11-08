#!/usr/bin/env python3
"""Offline, fail-closed migration of the canonical legacy ledger to FORMAL authority.

This tool prepares schema only.  It never manufactures a registration, attempt,
lease, fence, epoch, or authority for a historical task.
"""
import argparse, hashlib, json, os, sqlite3, stat, sys, time

APPLICATION_ID = 0x58534A31
SCHEMA_VERSION = 4
LEGACY_FINGERPRINT = "3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45"
ADDITIONS = (
 ("task_id", "TEXT"), ("attempt_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("spec_sha256", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("checkpoint_sha256", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("owner", "TEXT NOT NULL DEFAULT 'UNKNOWN'"), ("entry", "TEXT NOT NULL DEFAULT 'LEGACY_COMPAT'"),
 ("lease_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"), ("epoch", "INTEGER"),
 ("authority_state", "TEXT NOT NULL DEFAULT 'NONE'"), ("authority_valid_until", "REAL"),
 ("old_fence_invalidated", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("authority_caller_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("authority_run_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("authority_session_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("authority_gateway_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("authority_lock_provider_id", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
 ("resource_scope_json", "TEXT NOT NULL DEFAULT '[]'"),
 ("resource_scope_digest", "TEXT NOT NULL DEFAULT 'UNKNOWN'"), ("last_trusted_time", "REAL"),
)

def canon(v): return json.dumps(v, sort_keys=True, separators=(",", ":"))
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
 return h.hexdigest()
def regular(path, label):
 st=os.lstat(path)
 if not stat.S_ISREG(st.st_mode): raise ValueError(label+"_REGULAR_FILE_REQUIRED")
 return st
def schema_fingerprint(db):
 rows=db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
 material=[[r[0],r[1],r[2]," ".join((r[3] or "").split())] for r in rows]
 return hashlib.sha256(canon(material).encode()).hexdigest()
def inspect(path):
 regular(path,"LEDGER")
 uri="file:%s?mode=ro&immutable=1"%os.path.abspath(path)
 db=sqlite3.connect(uri,uri=True)
 try:
  quick=db.execute("PRAGMA quick_check").fetchall()
  result={"state":"INSPECTED","path":os.path.abspath(path),"file_sha256":sha_file(path),
   "application_id":db.execute("PRAGMA application_id").fetchone()[0],
   "user_version":db.execute("PRAGMA user_version").fetchone()[0],
   "quick_check":[x[0] for x in quick],"schema_fingerprint":schema_fingerprint(db),
   "task_count":db.execute("SELECT count(*) FROM tasks").fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone() else None}
  if result["quick_check"] != ["ok"]: result["classification"]="CORRUPT"
  elif result["application_id"]==0 and result["user_version"]==0 and result["schema_fingerprint"]==LEGACY_FINGERPRINT: result["classification"]="CANONICAL_LEGACY"
  elif result["application_id"]==APPLICATION_ID and result["user_version"]==SCHEMA_VERSION: result["classification"]="AUTHORITY_FORMAL"
  else: result["classification"]="UNKNOWN_OR_PARTIAL"
  return result
 finally: db.close()
def failpoint(name):
 if os.environ.get("XUANJUN_MIGRATION_FAIL_AT")==name: raise RuntimeError("INJECTED_"+name)
def preconditions(path, backup, expected_backup_sha, freeze, require_exact=True):
 a=regular(path,"LEDGER"); b=regular(backup,"BACKUP"); regular(freeze,"WRITE_FREEZE")
 if (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino): raise ValueError("BACKUP_MUST_BE_DISTINCT_FILE")
 actual=sha_file(backup)
 if actual != expected_backup_sha: raise ValueError("BACKUP_SHA256_MISMATCH")
 if require_exact and sha_file(path) != actual: raise ValueError("LEDGER_NOT_EXACT_BACKUP_COPY")
 return actual
def receipt(db, operation_id):
 row=db.execute("SELECT receipt_json FROM authority_migration_receipts WHERE operation_id=?",(operation_id,)).fetchone()
 return json.loads(row[0]) if row else None
def apply(path, backup, expected_backup_sha, expected_fp, freeze, operation_id):
 if not operation_id or len(operation_id)>200: raise ValueError("BOUNDED_OPERATION_ID_REQUIRED")
 if len(expected_backup_sha)!=64 or any(c not in "0123456789abcdef" for c in expected_backup_sha): raise ValueError("BACKUP_SHA256_REQUIRED")
 preconditions(path,backup,expected_backup_sha,freeze,False)
 before=inspect(path)
 if before["classification"]=="AUTHORITY_FORMAL":
  db=sqlite3.connect(path); r=receipt(db,operation_id); db.close()
  if r is None: raise ValueError("MIGRATED_BY_DIFFERENT_OR_UNKNOWN_OPERATION")
  return r
 if sha_file(path) != expected_backup_sha: raise ValueError("LEDGER_NOT_EXACT_BACKUP_COPY")
 if before["classification"]!="CANONICAL_LEGACY" or expected_fp!=LEGACY_FINGERPRINT or before["schema_fingerprint"]!=expected_fp:
  raise ValueError("EXPECTED_CANONICAL_LEGACY_FINGERPRINT_REQUIRED")
 db=sqlite3.connect(path,timeout=0,isolation_level=None)
 try:
  db.execute("PRAGMA foreign_keys=ON"); db.execute("BEGIN EXCLUSIVE"); failpoint("after_lock")
  if schema_fingerprint(db)!=expected_fp: raise ValueError("SCHEMA_CHANGED_AFTER_INSPECT")
  for name,definition in ADDITIONS:
   db.execute('ALTER TABLE tasks ADD COLUMN "%s" %s'%(name,definition)); failpoint("ddl_"+name)
  db.execute("UPDATE tasks SET task_id=id,attempt_id='UNKNOWN',spec_sha256='UNKNOWN',checkpoint_sha256='UNKNOWN',owner='UNKNOWN',entry='LEGACY_COMPAT',lease_id='UNKNOWN',epoch=NULL,authority_state='NONE',authority_valid_until=NULL,old_fence_invalidated='UNKNOWN',authority_caller_id='UNKNOWN',authority_run_id='UNKNOWN',authority_session_id='UNKNOWN',authority_gateway_id='UNKNOWN',authority_lock_provider_id='UNKNOWN',resource_scope_json='[]',resource_scope_digest='UNKNOWN',last_trusted_time=NULL")
  failpoint("after_backfill")
  db.execute("CREATE UNIQUE INDEX authority_tasks_task_id_uq ON tasks(task_id)")
  db.execute("CREATE TABLE authority_runtime_profile(singleton INTEGER PRIMARY KEY CHECK(singleton=1),profile TEXT NOT NULL CHECK(profile='FORMAL'))")
  db.execute("INSERT INTO authority_runtime_profile VALUES(1,'FORMAL')")
  db.execute("CREATE TABLE resource_claims(resource_key TEXT PRIMARY KEY,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,fence INTEGER NOT NULL,epoch INTEGER NOT NULL,state TEXT NOT NULL,updated_at REAL NOT NULL,FOREIGN KEY(task_id) REFERENCES tasks(task_id))")
  db.execute("CREATE INDEX resource_claims_task_idx ON resource_claims(task_id,attempt_id)")
  db.execute("CREATE TABLE authority_registrations(registration_id TEXT PRIMARY KEY,task_id TEXT NOT NULL UNIQUE,registered_at REAL NOT NULL,owner_authorization_source TEXT NOT NULL,developer_subject TEXT NOT NULL,contract_sha256 TEXT NOT NULL,FOREIGN KEY(task_id) REFERENCES tasks(task_id))")
  db.execute("CREATE INDEX authority_registrations_contract_idx ON authority_registrations(contract_sha256,registered_at)")
  db.execute("CREATE TABLE authority_migration_receipts(operation_id TEXT PRIMARY KEY,source_fingerprint TEXT NOT NULL,backup_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,created_at REAL NOT NULL)")
  failpoint("after_tables")
  db.execute("PRAGMA application_id=%d"%APPLICATION_ID); db.execute("PRAGMA user_version=%d"%SCHEMA_VERSION)
  value={"state":"COMMITTED","operation_id":operation_id,"source_fingerprint":expected_fp,"backup_sha256":expected_backup_sha,"legacy_task_count":before["task_count"],"profile":"FORMAL","historical_authority":"NONE","first_registration":"REQUIRED_AFTER_MIGRATION"}
  raw=canon(value); db.execute("INSERT INTO authority_migration_receipts VALUES(?,?,?,?,?,?)",(operation_id,expected_fp,expected_backup_sha,raw,hashlib.sha256(raw.encode()).hexdigest(),time.time()))
  if db.execute("PRAGMA foreign_key_check").fetchall(): raise ValueError("FOREIGN_KEY_CHECK_FAILED")
  failpoint("before_commit"); db.execute("COMMIT"); return value
 except Exception:
  try: db.execute("ROLLBACK")
  except sqlite3.Error: pass
  raise
 finally: db.close()
def query(path,operation_id):
 info=inspect(path)
 if info["classification"]!="AUTHORITY_FORMAL": return {"state":"NOT_COMMITTED","inspection":info}
 db=sqlite3.connect("file:%s?mode=ro"%os.path.abspath(path),uri=True)
 try:
  r=receipt(db,operation_id)
  return r or {"state":"UNKNOWN","operation_id":operation_id}
 finally: db.close()
def main():
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd")
 i=sub.add_parser("inspect"); i.add_argument("--db",required=True)
 a=sub.add_parser("apply"); a.add_argument("--db",required=True); a.add_argument("--backup",required=True); a.add_argument("--backup-sha256",required=True); a.add_argument("--expected-fingerprint",required=True); a.add_argument("--freeze-marker",required=True); a.add_argument("--operation-id",required=True)
 q=sub.add_parser("query"); q.add_argument("--db",required=True); q.add_argument("--operation-id",required=True)
 r=sub.add_parser("recover"); r.add_argument("--db",required=True); r.add_argument("--operation-id",required=True)
 x=p.parse_args()
 if not x.cmd: p.error("a command is required")
 try:
  if x.cmd=="inspect": out=inspect(x.db)
  elif x.cmd=="apply": out=apply(x.db,x.backup,x.backup_sha256,x.expected_fingerprint,x.freeze_marker,x.operation_id)
  else: out=query(x.db,x.operation_id)
  print(canon(out)); return 0 if out.get("state") not in ("UNKNOWN","NOT_COMMITTED") else 3
 except Exception as e: print(canon({"state":"REJECTED","error":str(e)})); return 2
if __name__=="__main__": sys.exit(main())
