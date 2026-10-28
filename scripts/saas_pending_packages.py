"""Pending package-version registration inside the existing Center SQLite.
Not a catalog replacement: only IDs from the original catalog are accepted.
No approval, entitlement, payment or publish operation is defined.
"""
import hashlib
import json
import re
import sqlite3
from scripts.pr122_customer_core import Denied,Conflict,Unavailable,canonical
from scripts.saas_module_package_gate import manifest_digest

VERSION=re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
KEY=re.compile(r'[A-Za-z0-9_-]{16,96}\Z')
SHA=re.compile(r'[0-9a-f]{64}\Z')
DDL=(
'''CREATE TABLE saas_package_heads(tenant TEXT NOT NULL,project TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>=0),PRIMARY KEY(tenant,project))''',
'''CREATE TABLE saas_pending_packages(record_id TEXT PRIMARY KEY,tenant TEXT NOT NULL,project TEXT NOT NULL,module_id TEXT NOT NULL,version TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,artifact_sha256 TEXT NOT NULL,manifest BLOB NOT NULL,state TEXT NOT NULL CHECK(state='PENDING_REVIEW'),created_by TEXT NOT NULL,created_at INTEGER NOT NULL,catalog_revision INTEGER NOT NULL CHECK(catalog_revision>0),UNIQUE(tenant,project,module_id,version))''',
'''CREATE TABLE saas_package_receipts(tenant TEXT NOT NULL,project TEXT NOT NULL,actor TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_sha256 TEXT NOT NULL,record_id TEXT NOT NULL,receipt BLOB NOT NULL,PRIMARY KEY(tenant,project,actor,idempotency_key),FOREIGN KEY(record_id) REFERENCES saas_pending_packages(record_id))''',
'''CREATE TRIGGER saas_pending_packages_no_update BEFORE UPDATE ON saas_pending_packages BEGIN SELECT RAISE(ABORT,'PENDING_PACKAGE_IMMUTABLE'); END''',
'''CREATE TRIGGER saas_pending_packages_no_delete BEFORE DELETE ON saas_pending_packages BEGIN SELECT RAISE(ABORT,'PENDING_PACKAGE_IMMUTABLE'); END''',
'''CREATE TRIGGER saas_pending_packages_no_replace BEFORE INSERT ON saas_pending_packages WHEN EXISTS(SELECT 1 FROM saas_pending_packages WHERE record_id=NEW.record_id OR (tenant=NEW.tenant AND project=NEW.project AND module_id=NEW.module_id AND version=NEW.version)) BEGIN SELECT RAISE(ABORT,'PENDING_PACKAGE_VERSION_EXISTS'); END''',
'''CREATE TRIGGER saas_package_receipts_no_update BEFORE UPDATE ON saas_package_receipts BEGIN SELECT RAISE(ABORT,'PACKAGE_RECEIPT_IMMUTABLE'); END''',
'''CREATE TRIGGER saas_package_receipts_no_delete BEFORE DELETE ON saas_package_receipts BEGIN SELECT RAISE(ABORT,'PACKAGE_RECEIPT_IMMUTABLE'); END''',
'''CREATE TRIGGER saas_package_receipts_no_replace BEFORE INSERT ON saas_package_receipts WHEN EXISTS(SELECT 1 FROM saas_package_receipts WHERE tenant=NEW.tenant AND project=NEW.project AND actor=NEW.actor AND idempotency_key=NEW.idempotency_key) BEGIN SELECT RAISE(ABORT,'PACKAGE_RECEIPT_IMMUTABLE'); END''')
NAMES={'saas_package_heads','saas_pending_packages','saas_package_receipts','saas_pending_packages_no_update','saas_pending_packages_no_delete','saas_pending_packages_no_replace','saas_package_receipts_no_update','saas_package_receipts_no_delete','saas_package_receipts_no_replace'}

def _objects(db):
 return {r[0]:r[1] for r in db.execute('SELECT name,sql FROM sqlite_master') if r[0] in NAMES}

def verify_schema(db):
 reference=sqlite3.connect(':memory:')
 try:
  for ddl in DDL:reference.execute(ddl)
  if _objects(db)!=_objects(reference):raise Unavailable('PENDING_PACKAGE_SCHEMA_NOT_INSTALLED')
 finally:reference.close()

def install(center):
 """Explicit opt-in original DB migration; never called by an HTTP request."""
 if center.db.in_transaction:raise ValueError('INSTALL_REQUIRES_OWN_TRANSACTION')
 required={'projects','members','audit'}
 tables={r[0] for r in center.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 if not required<=tables:raise ValueError('EXISTING_CENTER_REQUIRED')
 with center.tx():
  existing=_objects(center.db)
  if existing:verify_schema(center.db)
  else:
   for ddl in DDL:center.db.execute(ddl)
   verify_schema(center.db)
 return {'installed_in_existing_center':True,'new_database':False,'publish_enabled':False}

def _body(body):
 if type(body) is not dict or set(body)!={'module_id','version','expected_revision','idempotency_key'}:raise ValueError('EXACT_PACKAGE_REGISTER_REQUIRED')
 if type(body['module_id']) is not str or type(body['version']) is not str or not VERSION.fullmatch(body['version']):raise ValueError('INVALID_PACKAGE_ID_VERSION')
 if type(body['expected_revision']) is not int or not 0<=body['expected_revision']<9007199254740991:raise ValueError('INVALID_EXPECTED_REVISION')
 if type(body['idempotency_key']) is not str or not KEY.fullmatch(body['idempotency_key']):raise ValueError('INVALID_IDEMPOTENCY_KEY')
 return body

def _manifest(manifest,artifact,module):
 if type(manifest) is not dict or manifest.get('module_id')!=module['id'] or type(manifest.get('version')) is not str or not VERSION.fullmatch(manifest['version']):raise ValueError('PACKAGE_MANIFEST_IDENTITY')
 # A pending record can lack approvals, not basic package integrity or source binding.
 required={'module_id','version','artifact_sha256','capabilities','dependencies'}
 if not required<=set(manifest) or type(manifest['capabilities']) is not list or not all(type(x) is str for x in manifest['capabilities']) or set(manifest['capabilities'])!=set(module['capabilities']):raise ValueError('PACKAGE_CAPABILITY_CONTRACT')
 deps=manifest['dependencies']
 if type(deps) is not dict or set(deps)!=set(module['dependencies']) or not all(type(v) is str and VERSION.fullmatch(v) for v in deps.values()):raise ValueError('PACKAGE_DEPENDENCY_CONTRACT')
 if type(artifact) is not bytes or not artifact or len(artifact)>16*1024*1024:raise ValueError('PACKAGE_ARTIFACT_REQUIRED')
 sha=manifest['artifact_sha256']
 if type(sha) is not str or not SHA.fullmatch(sha) or hashlib.sha256(artifact).hexdigest()!=sha:raise ValueError('PACKAGE_ARTIFACT_MISMATCH')
 raw=canonical(manifest)
 if len(raw)>65536:raise ValueError('PACKAGE_MANIFEST_TOO_LARGE')
 return manifest_digest(manifest),sha,raw

class PendingPackages:
 def __init__(self,snapshot_provider):self.snapshot_provider=snapshot_provider
 def register(self,center,uid,pid,body):
  b=_body(body)
  with center.tx():
   verify_schema(center.db)
   project,_,_=center.project(uid,pid,('OWNER',))
   tenant=project['tenant']
   adapter,manifests,artifacts,_,_=self.snapshot_provider(tenant,pid)
   row=next((r for r in adapter.modules.catalog() if r['id']==b['module_id']),None)
   m=manifests.get(b['module_id'])
   if row is None or type(m) is not dict or m.get('version')!=b['version']:raise ValueError('UNKNOWN_PACKAGE_VERSION')
   manifest_sha,artifact_sha,raw=_manifest(m,artifacts.get(b['module_id']),row)
   request_sha=hashlib.sha256(canonical({'tenant':tenant,'project':pid,'actor':uid,'body':b,'manifest_sha256':manifest_sha,'artifact_sha256':artifact_sha})).hexdigest()
   prior=center.db.execute('SELECT request_sha256,receipt FROM saas_package_receipts WHERE tenant=? AND project=? AND actor=? AND idempotency_key=?',(tenant,pid,uid,b['idempotency_key'])).fetchone()
   if prior:
    if prior[0]!=request_sha:raise Conflict('IDEMPOTENCY_BINDING_CONFLICT')
    return {**json.loads(center.decrypt(prior[1],'package-receipt:'+request_sha)),'duplicate':True}
   current=center.db.execute('SELECT revision FROM saas_package_heads WHERE tenant=? AND project=?',(tenant,pid)).fetchone()
   revision=current[0] if current else 0
   if b['expected_revision']!=revision:raise Conflict('PACKAGE_CATALOG_CAS_CONFLICT')
   exists=center.db.execute('SELECT record_id FROM saas_pending_packages WHERE tenant=? AND project=? AND module_id=? AND version=?',(tenant,pid,b['module_id'],b['version'])).fetchone()
   if exists:raise Conflict('PACKAGE_VERSION_ALREADY_REGISTERED')
   record='pkg_'+hashlib.sha256(canonical([tenant,pid,b['module_id'],b['version'],manifest_sha])).hexdigest()
   receipt={'state':'PENDING_REVIEW','module_registered':True,'registration_scope':'TENANT_PROJECT_PENDING_ONLY','published':False,'approval_verified':False,'entitlement_granted':False,'record_id':record,'module_id':b['module_id'],'version':b['version'],'manifest_sha256':manifest_sha,'artifact_sha256':artifact_sha,'catalog_revision':revision+1,'duplicate':False}
   center.db.execute('INSERT INTO saas_pending_packages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(record,tenant,pid,b['module_id'],b['version'],manifest_sha,artifact_sha,center.encrypt(raw,'package:'+record),'PENDING_REVIEW',uid,center.now(),revision+1))
   if current:
    updated=center.db.execute('UPDATE saas_package_heads SET revision=? WHERE tenant=? AND project=? AND revision=?',(revision+1,tenant,pid,revision))
    if updated.rowcount!=1:raise Conflict('PACKAGE_CATALOG_CAS_CONFLICT')
   else:center.db.execute('INSERT INTO saas_package_heads VALUES(?,?,?)',(tenant,pid,1))
   center.db.execute('INSERT INTO saas_package_receipts VALUES(?,?,?,?,?,?,?)',(tenant,pid,uid,b['idempotency_key'],request_sha,record,center.encrypt(canonical(receipt),'package-receipt:'+request_sha)))
   center.audit(pid,uid,'SAAS_PENDING_PACKAGE_REGISTERED',record)
   return receipt
 def listing(self,center,uid,pid):
  with center.tx():
   verify_schema(center.db);p,role,_=center.project(uid,pid)
   if role not in ('OWNER','EDITOR','VIEWER','REVIEWER'):raise Denied('PROJECT_ROLE_NOT_ALLOWED')
   head=center.db.execute('SELECT revision FROM saas_package_heads WHERE tenant=? AND project=?',(p['tenant'],pid)).fetchone()
   rows=center.db.execute('SELECT record_id,module_id,version,manifest_sha256,artifact_sha256,state,catalog_revision FROM saas_pending_packages WHERE tenant=? AND project=? ORDER BY catalog_revision',(p['tenant'],pid)).fetchall()
   records=[dict(zip(('record_id','module_id','version','manifest_sha256','artifact_sha256','state','catalog_revision'),r)) for r in rows]
   if role not in ('OWNER','REVIEWER'):records=[{k:v for k,v in r.items() if k not in ('manifest_sha256','artifact_sha256')} for r in records]
   return {'catalog_revision':head[0] if head else 0,'packages':records,'scope':'TENANT_PROJECT_PENDING_ONLY','published':False}
 def read_receipt(self,center,uid,pid,key):
  if type(key) is not str or not KEY.fullmatch(key):raise ValueError('INVALID_IDEMPOTENCY_KEY')
  with center.tx():
   verify_schema(center.db);p,_,_=center.project(uid,pid,('OWNER',))
   r=center.db.execute('SELECT request_sha256,receipt FROM saas_package_receipts WHERE tenant=? AND project=? AND actor=? AND idempotency_key=?',(p['tenant'],pid,uid,key)).fetchone()
   if r is None:raise Denied('RECEIPT_NOT_VISIBLE')
   return json.loads(center.decrypt(r[1],'package-receipt:'+r[0]))
