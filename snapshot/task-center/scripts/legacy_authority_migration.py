#!/usr/bin/env python3
"""Offline fail-closed legacy-ledger migration (never grants historical authority)."""
import argparse, hashlib, hmac, json, os, sqlite3, stat, sys, time

APPLICATION_ID=0x58534A31
SCHEMA_VERSION=4
LEGACY_FINGERPRINT="3e871a9911be87760cb7aa691113b570228f922a609b50ffbd2974e31b7ceb45"
ADDITIONS=(("task_id","TEXT"),("attempt_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("spec_sha256","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("checkpoint_sha256","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("owner","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("entry","TEXT NOT NULL DEFAULT 'LEGACY_COMPAT'"),("lease_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("epoch","INTEGER"),("authority_state","TEXT NOT NULL DEFAULT 'NONE'"),("authority_valid_until","REAL"),("old_fence_invalidated","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("authority_caller_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("authority_run_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("authority_session_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("authority_gateway_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("authority_lock_provider_id","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("resource_scope_json","TEXT NOT NULL DEFAULT '[]'"),("resource_scope_digest","TEXT NOT NULL DEFAULT 'UNKNOWN'"),("last_trusted_time","REAL"))
FORMAL_TABLES={"tasks","authority_runtime_profile","resource_claims","authority_registrations","authority_migration_receipts"}
FORMAL_INDEXES={"authority_tasks_task_id_uq","resource_claims_task_idx","authority_registrations_contract_idx"}
RECEIPT_FIELDS={"state","operation_id","request_digest","source_fingerprint","backup_sha256","target_fingerprint","legacy_task_count","profile","historical_authority","first_registration","generation"}

def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()
def sha_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
 return h.hexdigest()
def regular(path,label):
 st=os.lstat(path)
 if not stat.S_ISREG(st.st_mode): raise ValueError(label+"_REGULAR_FILE_REQUIRED")
 return st
def schema_manifest(db):
 objects=[]
 for typ,name,tbl,sql in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"):
  item={"type":typ,"name":name,"table":tbl,"sql":" ".join((sql or "").split())}
  if typ=="table":
   item["columns"]=[list(x) for x in db.execute('PRAGMA table_info("%s")'%name.replace('"','""'))]
   item["foreign_keys"]=[list(x) for x in db.execute('PRAGMA foreign_key_list("%s")'%name.replace('"','""'))]
   item["indexes"]=[list(x) for x in db.execute('PRAGMA index_list("%s")'%name.replace('"','""'))]
  objects.append(item)
 return {"application_id":db.execute("PRAGMA application_id").fetchone()[0],"user_version":db.execute("PRAGMA user_version").fetchone()[0],"objects":objects}
def schema_fingerprint(db): return digest(schema_manifest(db)["objects"])
def formal_schema_valid(db):
 names={(x[0],x[1]) for x in db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
 if not FORMAL_TABLES <= {n for t,n in names if t=="table"} or not FORMAL_INDEXES <= {n for t,n in names if t=="index"}: return False
 cols={x[1]:(str(x[2]).upper(),x[3],x[4],x[5]) for x in db.execute("PRAGMA table_info(tasks)")}
 for name,definition in ADDITIONS:
  if name not in cols or cols[name][0] != definition.split()[0]: return False
 if db.execute("SELECT singleton,profile FROM authority_runtime_profile").fetchall()!=[(1,"FORMAL")]: return False
 if db.execute("PRAGMA foreign_key_check").fetchall(): return False
 for table in ("resource_claims","authority_registrations"):
  if not db.execute("PRAGMA foreign_key_list(%s)"%table).fetchall(): return False
 receipt={x[1] for x in db.execute("PRAGMA table_info(authority_migration_receipts)")}
 return {"operation_id","source_fingerprint","backup_sha256","receipt_json","receipt_sha256","created_at"} <= receipt
def inspect(path):
 regular(path,"LEDGER"); real=os.path.realpath(path)
 db=sqlite3.connect("file:%s?mode=ro&immutable=1"%real,uri=True)
 try:
  quick=[x[0] for x in db.execute("PRAGMA quick_check")]; fp=schema_fingerprint(db)
  out={"state":"INSPECTED","path":real,"file_sha256":sha_file(real),"application_id":db.execute("PRAGMA application_id").fetchone()[0],"user_version":db.execute("PRAGMA user_version").fetchone()[0],"quick_check":quick,"schema_fingerprint":fp,"task_count":db.execute("SELECT count(*) FROM tasks").fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone() else None}
  if quick != ["ok"]: out["classification"]="CORRUPT"
  elif out["application_id"]==0 and out["user_version"]==0 and fp==LEGACY_FINGERPRINT: out["classification"]="CANONICAL_LEGACY"
  elif out["application_id"]==APPLICATION_ID and out["user_version"]==SCHEMA_VERSION and formal_schema_valid(db): out["classification"]="AUTHORITY_FORMAL"
  else: out["classification"]="UNKNOWN_OR_PARTIAL"
  return out
 finally: db.close()
def file_identity(path):
 p=os.path.realpath(path); st=regular(p,"FREEZE_BOUND_FILE")
 return {"path":p,"device":st.st_dev,"inode":st.st_ino,"size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":sha_file(p)}
def load_key(path):
 regular(path,"FREEZE_TRUST_KEY")
 with open(path,"rb") as source: key=source.read()
 if len(key)<32: raise ValueError("FREEZE_TRUST_KEY_TOO_SHORT")
 return key
def create_freeze(db_path,backup,backup_sha,operation_id,key_path,output,ttl=300,service_state="STOPPED",writer_state="NO_WRITER",lock_state="EXCLUSIVE_AVAILABLE"):
 if sha_file(backup)!=backup_sha: raise ValueError("BACKUP_SHA256_MISMATCH")
 now=int(time.time()); body={"kind":"AUTHORITY_FREEZE_V1","schema_version":SCHEMA_VERSION,"operation_id":operation_id,"created_at":now,"expires_at":now+ttl,"database":file_identity(db_path),"wal":file_identity(db_path+'-wal') if os.path.exists(db_path+'-wal') else None,"shm":file_identity(db_path+'-shm') if os.path.exists(db_path+'-shm') else None,"backup":{"path":os.path.realpath(backup),"sha256":backup_sha},"service_state":service_state,"writer_state":writer_state,"lock_state":lock_state}
 signed={"payload":body,"hmac_sha256":hmac.new(load_key(key_path),canon(body).encode(),hashlib.sha256).hexdigest()}
 flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL; fd=os.open(output,flags,0o600)
 with os.fdopen(fd,"w") as f: f.write(canon(signed)+"\n")
 return signed
def verify_freeze(path,key_path,db_path,backup,backup_sha,operation_id):
 regular(path,"FREEZE_RECEIPT")
 try:
  with open(path,encoding="utf-8") as source: signed=json.load(source)
  body=signed["payload"]; sig=signed["hmac_sha256"]
 except Exception as e: raise ValueError("FREEZE_INTEGRITY_INVALID") from e
 expected=hmac.new(load_key(key_path),canon(body).encode(),hashlib.sha256).hexdigest()
 if not hmac.compare_digest(sig,expected): raise ValueError("FREEZE_INTEGRITY_INVALID")
 if body.get("kind")!="AUTHORITY_FREEZE_V1" or body.get("schema_version")!=SCHEMA_VERSION or body.get("operation_id")!=operation_id: raise ValueError("FREEZE_BINDING_MISMATCH")
 if int(time.time())>body.get("expires_at",0): raise ValueError("FREEZE_EXPIRED")
 if body.get("service_state")!="STOPPED" or body.get("writer_state")!="NO_WRITER" or body.get("lock_state")!="EXCLUSIVE_AVAILABLE": raise ValueError("FREEZE_UNSAFE_STATE")
 if body.get("database")!=file_identity(db_path) or body.get("wal")!=(file_identity(db_path+'-wal') if os.path.exists(db_path+'-wal') else None) or body.get("shm")!=(file_identity(db_path+'-shm') if os.path.exists(db_path+'-shm') else None): raise ValueError("FREEZE_DATABASE_STATE_CHANGED")
 if body.get("backup")!={"path":os.path.realpath(backup),"sha256":backup_sha}: raise ValueError("FREEZE_BACKUP_MISMATCH")
def failpoint(name):
 if os.environ.get("XUANJUN_MIGRATION_FAIL_AT")==name: raise RuntimeError("INJECTED_"+name)
def read_receipt(db,operation_id,expected=None):
 row=db.execute("SELECT operation_id,source_fingerprint,backup_sha256,receipt_json,receipt_sha256 FROM authority_migration_receipts WHERE operation_id=?",(operation_id,)).fetchone()
 if not row: raise ValueError("INTEGRITY_RECEIPT_MISSING")
 try: value=json.loads(row[3])
 except Exception as e: raise ValueError("INTEGRITY_RECEIPT_JSON_INVALID") from e
 raw=canon(value)
 if row[3]!=raw or not hmac.compare_digest(hashlib.sha256(raw.encode()).hexdigest(),row[4]): raise ValueError("INTEGRITY_RECEIPT_SHA256_MISMATCH")
 if set(value)!=RECEIPT_FIELDS or value["state"]!="COMMITTED" or value["operation_id"]!=operation_id or row[:3]!=(operation_id,value["source_fingerprint"],value["backup_sha256"]): raise ValueError("INTEGRITY_RECEIPT_BINDING_MISMATCH")
 if expected and any(value.get(k)!=v for k,v in expected.items()): raise ValueError("INTEGRITY_RECEIPT_BINDING_MISMATCH")
 return value
def apply(path,backup,backup_sha,expected_fp,freeze,operation_id,key_path):
 if not operation_id or len(operation_id)>200: raise ValueError("BOUNDED_OPERATION_ID_REQUIRED")
 if len(backup_sha)!=64 or any(c not in "0123456789abcdef" for c in backup_sha): raise ValueError("BACKUP_SHA256_REQUIRED")
 a=regular(path,"LEDGER"); b=regular(backup,"BACKUP")
 if (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino): raise ValueError("BACKUP_MUST_BE_DISTINCT_FILE")
 if sha_file(backup)!=backup_sha: raise ValueError("BACKUP_SHA256_MISMATCH")
 verify_freeze(freeze,key_path,path,backup,backup_sha,operation_id)
 before=inspect(path); request_digest=digest({"operation_id":operation_id,"source_fingerprint":expected_fp,"backup_sha256":backup_sha,"database":os.path.realpath(path)})
 if before["classification"]=="AUTHORITY_FORMAL":
  db=sqlite3.connect("file:%s?mode=ro"%os.path.abspath(path),uri=True)
  try:
   # Idempotent apply must reject schema drift just as query/recover do.
   # Check within the same connection, not against the earlier inspection:
   # another writer could have changed the schema between the two opens.
   db.execute("BEGIN")
   value=read_receipt(db,operation_id,{"request_digest":request_digest,"backup_sha256":backup_sha})
   if value["target_fingerprint"]!=schema_fingerprint(db): raise ValueError("INTEGRITY_RECEIPT_TARGET_MISMATCH")
   return value
  finally: db.close()
 if sha_file(path)!=backup_sha: raise ValueError("LEDGER_NOT_EXACT_BACKUP_COPY")
 if before["classification"]!="CANONICAL_LEGACY" or expected_fp!=LEGACY_FINGERPRINT or before["schema_fingerprint"]!=expected_fp: raise ValueError("EXPECTED_CANONICAL_LEGACY_FINGERPRINT_REQUIRED")
 db=sqlite3.connect(path,timeout=0,isolation_level=None)
 try:
  db.execute("PRAGMA foreign_keys=ON"); db.execute("BEGIN EXCLUSIVE"); failpoint("after_lock")
  if schema_fingerprint(db)!=expected_fp: raise ValueError("SCHEMA_CHANGED_AFTER_INSPECT")
  for name,definition in ADDITIONS: db.execute('ALTER TABLE tasks ADD COLUMN "%s" %s'%(name,definition)); failpoint("ddl_"+name)
  db.execute("UPDATE tasks SET task_id=id,attempt_id='UNKNOWN',spec_sha256='UNKNOWN',checkpoint_sha256='UNKNOWN',owner='UNKNOWN',entry='LEGACY_COMPAT',lease_id='UNKNOWN',epoch=NULL,authority_state='NONE',authority_valid_until=NULL,old_fence_invalidated='UNKNOWN',authority_caller_id='UNKNOWN',authority_run_id='UNKNOWN',authority_session_id='UNKNOWN',authority_gateway_id='UNKNOWN',authority_lock_provider_id='UNKNOWN',resource_scope_json='[]',resource_scope_digest='UNKNOWN',last_trusted_time=NULL"); failpoint("after_backfill")
  for statement in ("CREATE UNIQUE INDEX authority_tasks_task_id_uq ON tasks(task_id)","CREATE TABLE authority_runtime_profile(singleton INTEGER PRIMARY KEY CHECK(singleton=1),profile TEXT NOT NULL CHECK(profile='FORMAL'))","INSERT INTO authority_runtime_profile VALUES(1,'FORMAL')","CREATE TABLE resource_claims(resource_key TEXT PRIMARY KEY,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,fence INTEGER NOT NULL,epoch INTEGER NOT NULL,state TEXT NOT NULL,updated_at REAL NOT NULL,FOREIGN KEY(task_id) REFERENCES tasks(task_id))","CREATE INDEX resource_claims_task_idx ON resource_claims(task_id,attempt_id)","CREATE TABLE authority_registrations(registration_id TEXT PRIMARY KEY,task_id TEXT NOT NULL UNIQUE,registered_at REAL NOT NULL,owner_authorization_source TEXT NOT NULL,developer_subject TEXT NOT NULL,contract_sha256 TEXT NOT NULL,FOREIGN KEY(task_id) REFERENCES tasks(task_id))","CREATE INDEX authority_registrations_contract_idx ON authority_registrations(contract_sha256,registered_at)","CREATE TABLE authority_migration_receipts(operation_id TEXT PRIMARY KEY,source_fingerprint TEXT NOT NULL,backup_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,created_at REAL NOT NULL)"): db.execute(statement)
  failpoint("after_tables"); db.execute("PRAGMA application_id=%d"%APPLICATION_ID); db.execute("PRAGMA user_version=%d"%SCHEMA_VERSION)
  target=schema_fingerprint(db); value={"state":"COMMITTED","operation_id":operation_id,"request_digest":request_digest,"source_fingerprint":expected_fp,"backup_sha256":backup_sha,"target_fingerprint":target,"legacy_task_count":before["task_count"],"profile":"FORMAL","historical_authority":"NONE","first_registration":"REQUIRED_AFTER_MIGRATION","generation":1}
  raw=canon(value); db.execute("INSERT INTO authority_migration_receipts VALUES(?,?,?,?,?,?)",(operation_id,expected_fp,backup_sha,raw,hashlib.sha256(raw.encode()).hexdigest(),time.time()))
  if not formal_schema_valid(db): raise ValueError("FORMAL_SCHEMA_VALIDATION_FAILED")
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
  # Receipt and schema must be observed in the same SQLite snapshot; the
  # preliminary inspection can race a schema change before this connection.
  db.execute("BEGIN")
  value=read_receipt(db,operation_id)
  if value["target_fingerprint"]!=schema_fingerprint(db): raise ValueError("INTEGRITY_RECEIPT_TARGET_MISMATCH")
  return value
 finally: db.close()
def probe(path):
 info=inspect(path); return {k:info[k] for k in ("state","path","file_sha256","application_id","user_version","quick_check","schema_fingerprint","task_count","classification")}
def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd")
 i=s.add_parser("inspect"); i.add_argument("--db",required=True)
 for n in ("query","recover"): q=s.add_parser(n); q.add_argument("--db",required=True); q.add_argument("--operation-id",required=True)
 a=s.add_parser("apply"); a.add_argument("--db",required=True); a.add_argument("--backup",required=True); a.add_argument("--backup-sha256",required=True); a.add_argument("--expected-fingerprint",required=True); a.add_argument("--freeze-receipt",required=True); a.add_argument("--freeze-trust-key",required=True); a.add_argument("--operation-id",required=True)
 f=s.add_parser("create-freeze"); f.add_argument("--db",required=True); f.add_argument("--backup",required=True); f.add_argument("--backup-sha256",required=True); f.add_argument("--operation-id",required=True); f.add_argument("--freeze-trust-key",required=True); f.add_argument("--output",required=True); f.add_argument("--ttl-seconds",type=int,default=300)
 z=s.add_parser("probe"); z.add_argument("--db",required=True)
 x=p.parse_args()
 try:
  if x.cmd=="inspect": out=inspect(x.db)
  elif x.cmd in ("query","recover"): out=query(x.db,x.operation_id)
  elif x.cmd=="probe": out=probe(x.db)
  elif x.cmd=="create-freeze": out=create_freeze(x.db,x.backup,x.backup_sha256,x.operation_id,x.freeze_trust_key,x.output,x.ttl_seconds)
  elif x.cmd=="apply": out=apply(x.db,x.backup,x.backup_sha256,x.expected_fingerprint,x.freeze_receipt,x.operation_id,x.freeze_trust_key)
  else: p.error("a command is required")
  print(canon(out)); return 0
 except Exception as e: print(canon({"state":"REJECTED","error":str(e)})); return 2
if __name__=="__main__": sys.exit(main())
