"""Disposable-container harness: no host bind mounts; fixture keys are TEST_ONLY."""
import base64,hashlib,io,json,os,shutil,sqlite3,stat,subprocess,sys,tarfile,tempfile,time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat,PrivateFormat,NoEncryption

case=sys.argv[1];assert case in ('POS','A','B','C-py','C-so','D')
root='/code/case';os.mkdir(root,0o700);os.chown(root,65534,65534)
ctrl=root+'/controller';os.mkdir(ctrl,0o700);os.chown(ctrl,65534,65534)
release=ctrl+'/releases';os.mkdir(release,0o700);os.chown(release,65534,65534)
base=release+'/base';os.mkdir(base,0o700);os.chown(base,65534,65534)
canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
sha=lambda v:hashlib.sha256(v).hexdigest()
def write(path,data,mode=0o600,uid=65534,gid=65534):
 with open(path,'wb') as f:f.write(data)
 os.chmod(path,mode);os.chown(path,uid,gid)
write(base+'/.bootstrap-manifest.json',canon({'members':{}}));os.symlink('base',release+'/current')
# CLI uses current directly beneath root.
os.unlink(release+'/current');os.symlink('base',release+'/current')
dbpath=ctrl+'/ledger';db=sqlite3.connect(dbpath);db.execute('pragma journal_mode=wal');db.execute('create table operations(nonce text primary key,task text,attempt text,state text,prestate_target text,prestate_hash text,staging_target text,manifest_hash text,intended_target text,receipt_hash text,operation_id text,carrier_digest text,manifest_digest text,tree_digest text,prestate_digest text,key_id text,receipt_path text,prestate_dev integer,prestate_ino integer,switch_intent text)');db.execute('create table rollbacks(operation_id text primary key,request_digest text,install_op text,attempt text,from_target text,to_target text,from_digest text,to_digest text,state text,receipt_json text,receipt_path text,key_id text)');db.close();os.chmod(dbpath,0o600);os.chown(dbpath,65534,65534)
write(ctrl+'/audit',b'');key=Ed25519PrivateKey.generate();pub=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
lock=open('/opt/test/bootstrap/DEPENDENCY_LOCK.json','rb').read();scope=open('/scope.json','rb').read();boot_hash=sha(open('/bootstrap.tar','rb').read());carrier_hash=sha(open('/carrier.tar','rb').read())
trust={'mode':'ED25519','environment':'TEST_ONLY','controller':'fixture','public_key':base64.b64encode(pub).decode(),'key_id':'test-receipt','binding_key_id':'test-binding','binding_public_key':base64.b64encode(pub).decode(),'dependency_lock_sha256':sha(lock),'expected_controller_uid':65534,'expected_controller_gid':65534,'expected_receipt_owner':65534,'expected_receipt_mode':448}
payload={'schema':1,'environment':'TEST_ONLY','production_trust_anchor':'REQUIRED','expiry':int(time.time())+3600,'dependency_lock_sha256':sha(lock),'vendor_tree_digest':sha(lock),'bootstrap_manifest_sha256':boot_hash,'carrier_manifest_sha256':carrier_hash,'bootstrap_archive_sha256':boot_hash,'carrier_archive_sha256':carrier_hash,'tool_scope_sha256':sha(scope)}
binding={'payload':payload,'key_id':'test-binding','signature':base64.b64encode(key.sign(canon(payload))).decode()}
stream=io.BytesIO()
with tarfile.open(fileobj=stream,mode='w') as tf:
 t=tarfile.TarInfo('payload');t.size=3;tf.addfile(t,io.BytesIO(b'abc'))
carrier=stream.getvalue();manifest=canon({'members':{'payload':{'type':'file','size':3,'sha256':sha(b'abc')}},'tool_scope':{},'minimum_sqlite':[3,35,0]})
auth={'carrier_sha256':sha(carrier),'manifest_sha256':sha(manifest),'task':'task','attempt':'attempt','nonce':'nonce','expiry':int(time.time())+3600,'controller':'fixture','tool_scope':{'mode':'READ_ONLY','tools':{}}}
receipt=canon({'payload':auth,'signature':base64.b64encode(key.sign(canon(auth))).decode()})
for name,data in [('trust',canon(trust)),('binding',canon(binding)),('lock',lock),('carrier',carrier),('manifest',manifest),('receipt',receipt),('signkey',key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))]:write(ctrl+'/'+name,data)
# Mutate package only after creating TEST_ONLY fixture binding.
v='/opt/test/bootstrap/vendor'
if case=='A':
 for d,dirs,files in os.walk(v):
  os.chown(d,1002,1002)
  for name in files:os.chown(os.path.join(d,name),1002,1002)
elif case=='B':os.chmod(v,0o775)
elif case in ('C-py','C-so'):os.chmod(v+('/cryptography/__init__.py' if case=='C-py' else '/_cffi_backend.cpython-312-x86_64-linux-gnu.so'),0o664)
elif case=='D':os.rename(v,v+'-actual');os.symlink('vendor-actual',v)
print('case',case,'container uid/gid',os.getuid(),os.getgid(),'child uid/gid',65534,65534)
for path in ('/opt','/opt/test','/opt/test/bootstrap',v):
 st=os.lstat(path);print('stat',path,'uid',st.st_uid,'gid',st.st_gid,'mode',oct(stat.S_IMODE(st.st_mode)),'type',stat.S_IFMT(st.st_mode))
paths=['trust','binding','lock','carrier','manifest','receipt','signkey'];fds={n:os.open(ctrl+'/'+n,os.O_RDONLY) for n in paths};rfd=os.open(release,os.O_RDONLY|os.O_DIRECTORY)
args=[sys.executable,'-I','/opt/test/bootstrap/secure_bootstrap.py','--expected-controller-uid','65534','--expected-controller-gid','65534','--expected-receipt-owner','65534','--expected-receipt-mode','0700','--ledger',dbpath,'--audit',ctrl+'/audit','--root',release,'--task','task','--attempt','attempt','--receipt-key-id','test-receipt','--receipt-dir-fd',str(rfd)]
for name,flag in [('trust','--trust-fd'),('binding','--binding-fd'),('lock','--dependency-lock-fd'),('carrier','--carrier-fd'),('manifest','--manifest-fd'),('receipt','--receipt-fd'),('signkey','--receipt-signing-key-fd')]:args.extend([flag,str(fds[name])])
def demote():os.setgroups([]);os.setgid(65534);os.setuid(65534)
result=subprocess.run(args,pass_fds=tuple(fds.values())+(rfd,),preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
with sqlite3.connect(dbpath) as db:count=db.execute('select count(*) from operations').fetchone()[0];state=db.execute('select state from operations').fetchone()
current=os.readlink(release+'/current');print('exit',result.returncode,'stdout',result.stdout.strip(),'stderr',result.stderr.strip(),'ledger_count',count,'state',state,'current',current)
if case=='POS':assert result.returncode==0 and count==1 and state==('SUCCEEDED',) and current=='release-nonce'
else:assert result.returncode!=0 and count==0 and current=='base' and ('VENDOR_DIRECTORY_POLICY' in result.stderr or 'DEPENDENCY_FILE_POLICY' in result.stderr or 'VENDOR_DIRECTORY_REQUIRED' in result.stderr or 'DEPENDENCY_PATH_LINK' in result.stderr),result.stderr
print('CASE_PASS')
