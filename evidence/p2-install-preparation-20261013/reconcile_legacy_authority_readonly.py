"""Readonly authority reconciliation; never writes canonical database."""
import os,sys,socket,json,sqlite3,hashlib,stat,subprocess
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
B='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
D=B+'/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5'
def private(p,digest=None):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());r=f.read(1048577);assert s.st_uid==0 and stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600 and len(r)<=1048576
 if digest:assert hashlib.sha256(r).hexdigest()==digest
 return json.loads(r.decode())
receipt=private(D+'/owner-isolation-receipt.json','70d8e244f7f72c15a16299b9eef19670cd7cdee452b1913d864af93c2f4824bc')
plan=private(B+'/plan-p2pkg-38420216343-1/protected-core-install-plan.json','6a7789a023d0cbb265663275ee7442fdd026eaaee0fc4ee4a0f237ec5a62e970')
state=private(D+'/legacy-units.json')
for unit,row in state['units'].items():
 assert row['backup']==D+'/'+unit+'.backup'
 with open(row['backup'],'rb') as f:assert hashlib.sha256(f.read()).hexdigest()==row['sha256']
 assert os.path.islink(row['path']) and os.readlink(row['path'])=='/dev/null'
 r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=ActiveState,MainPID,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 assert r.returncode==0
 props=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
 assert props=={'ActiveState':'inactive','MainPID':'0','UnitFileState':'masked'}
p=plan['cutover']['source'];assert os.path.realpath(p)==p
# immutable reader is valid only with no nonempty WAL. Do not ignore WAL.
assert not os.path.exists(p+'-wal') or os.stat(p+'-wal').st_size==0,'HOLD_NONEMPTY_WAL_REQUIRES_PROTECTED_SNAPSHOT'
def files():
 result={}
 for x in (p,p+'-wal',p+'-shm'):
  if os.path.exists(x):
   with open(x,'rb') as f:
    s=os.fstat(f.fileno());h=hashlib.sha256()
    for c in iter(lambda:f.read(65536),b''):h.update(c)
   result[x]={'sha256':h.hexdigest(),'size':s.st_size}
 return result
before=files()
db=sqlite3.connect('file:'+p+'?mode=ro&immutable=1',uri=True,timeout=3)
db.execute('PRAGMA query_only=ON')
assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
tables={}
for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
 assert name.replace('_','').isalnum()
 cols=[x[1] for x in db.execute('PRAGMA table_info("'+name+'")')]
 row={'columns':cols,'count':db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]}
 for c in ('state','status'):
  if c in cols:row[c+'_counts']=db.execute('SELECT "'+c+'",COUNT(*) FROM "'+name+'" GROUP BY "'+c+'" LIMIT 100').fetchall()
 for c in ('lease_owner','lease_until','fence','epoch'):
  if c in cols:
   row[c+'_nonnull_count']=db.execute('SELECT COUNT(*) FROM "'+name+'" WHERE "'+c+'" IS NOT NULL').fetchone()[0]
   if c!='lease_owner':row[c+'_range']=db.execute('SELECT MIN("'+c+'"),MAX("'+c+'") FROM "'+name+'"').fetchone()
 tables[name]=row
db.close();after=files();assert before==after,'HOLD_DATABASE_CHANGED_DURING_READ'
ROOT='/tmp/p2pkg-38420216343-1/xuanjun-p2-package'
sys.path.insert(0,ROOT+'/stage1')
from legacy_host_adapter import LegacyHostAdapter
a=LegacyHostAdapter(D)
try:a.preflight(plan['cutover']);resume='UNEXPECTED_PREFLIGHT_PASS'
except ValueError as e:resume=str(e)
proof=a.measure_quiescence(plan['cutover']['legacy_bindings'])
print(json.dumps({'schema':1,'transaction_id':plan['transaction_id'],'database_integrity':'OK','canonical_files_unchanged':True,'database_files':before,'tables':tables,'adapter_preflight_existing_transaction':resume,'quiescence':proof,'other_writers':'UNKNOWN_OUTSIDE_AUTHORIZED_UNITS','fence_mutation':False,'install':False,'writer_admission':False,'model_calls':0},sort_keys=True))
print('READ_ONLY=YES; FENCE_MUTATION=NO; INSTALL=NO')
