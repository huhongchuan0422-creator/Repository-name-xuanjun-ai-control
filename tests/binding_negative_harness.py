"""Disposable-container harness: no host bind mounts; fixture keys are TEST_ONLY."""
import base64,hashlib,io,json,os,shutil,sqlite3,stat,subprocess,sys,tarfile,tempfile,time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat,PrivateFormat,NoEncryption

case=sys.argv[1];assert case in ('POS','field-bootstrap','field-carrier','field-scope','field-lock','signature','keyid','expiry','lock','vendor-change','vendor-delete','vendor-add','external-path','binding-hardlink','lock-hardlink','binding-symlink','lock-symlink','binding-opener-symlink','lock-opener-symlink')
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
# Independent mutation per fresh container; signature intentionally not recomputed except expiry.
v='/opt/test/bootstrap/vendor'
if case.startswith('field-'):
 field={'field-bootstrap':'bootstrap_archive_sha256','field-carrier':'carrier_archive_sha256','field-scope':'tool_scope_sha256','field-lock':'dependency_lock_sha256'}[case]
 binding['payload'][field]='0'*64;write(ctrl+'/binding',canon(binding))
elif case=='signature':
 sig=bytearray(base64.b64decode(binding['signature']));sig[0]^=1;binding['signature']=base64.b64encode(sig).decode();write(ctrl+'/binding',canon(binding))
elif case=='keyid':binding['key_id']='unknown';write(ctrl+'/binding',canon(binding))
elif case=='expiry':
 binding['payload']['expiry']=1;binding['signature']=base64.b64encode(key.sign(canon(binding['payload']))).decode();write(ctrl+'/binding',canon(binding))
elif case=='lock':write(ctrl+'/lock',lock+b' ')
elif case in ('vendor-change','vendor-delete','vendor-add'):
 # Re-sign a semantically equivalent lock to prove vendor checks use the signed lock.
 lock=lock+b' ';trust['dependency_lock_sha256']=sha(lock);binding['payload']['dependency_lock_sha256']=sha(lock);binding['signature']=base64.b64encode(key.sign(canon(binding['payload']))).decode();write(ctrl+'/lock',lock);write(ctrl+'/trust',canon(trust));write(ctrl+'/binding',canon(binding))
if case in ('vendor-change','vendor-delete','vendor-add'):
 path=v+'/cryptography/__init__.py'
 if case=='vendor-change':os.chmod(path,0o644);open(path,'ab').write(b'#');os.chmod(path,0o444)
 elif case=='vendor-delete':os.chmod(v+'/cryptography',0o755);os.unlink(path);os.chmod(v+'/cryptography',0o555)
 else:os.chmod(v,0o755);write(v+'/extra.py',b'x',0o444,0,0);os.chmod(v,0o555)
elif case in ('binding-hardlink','lock-hardlink'):
 name=case.split('-')[0];os.link(ctrl+'/'+name,ctrl+'/'+name+'-alias')
elif case in ('binding-symlink','lock-symlink','binding-opener-symlink','lock-opener-symlink'):
 name=case.split('-')[0];os.rename(ctrl+'/'+name,ctrl+'/'+name+'-actual');os.symlink(name+'-actual',ctrl+'/'+name)
print('case',case,'container uid/gid',os.getuid(),os.getgid(),'child uid/gid',65534,65534)
for path in ('/opt','/opt/test','/opt/test/bootstrap',v):
 st=os.lstat(path);print('stat',path,'uid',st.st_uid,'gid',st.st_gid,'mode',oct(stat.S_IMODE(st.st_mode)),'type',stat.S_IFMT(st.st_mode))
paths=['trust','binding','lock','carrier','manifest','receipt','signkey']
if case in ('binding-opener-symlink','lock-opener-symlink'):
 name=case.split('-')[0];dfd=os.open(ctrl,os.O_RDONLY|os.O_DIRECTORY)
 try:
  try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
  except OSError as e:print('TRUSTED_OPENER_REJECTED',name,'errno',e.errno,'NO_FD_CREATED');fd=None
  assert fd is None
 finally:os.close(dfd)
 with sqlite3.connect(dbpath) as db:count=db.execute('select count(*) from operations').fetchone()[0]
 print('ledger_count',count,'current',os.readlink(release+'/current'));assert count==0 and os.readlink(release+'/current')=='base';print('CASE_PASS');sys.exit(0)
fds={n:os.open(ctrl+'/'+n,os.O_RDONLY) for n in paths};rfd=os.open(release,os.O_RDONLY|os.O_DIRECTORY)
if case in ('binding-symlink','lock-symlink'):
 name=case.split('-')[0];direct=os.open(ctrl+'/'+name+'-actual',os.O_RDONLY|os.O_NOFOLLOW)
 try:
  a=os.fstat(fds[name]);b=os.fstat(direct);assert (a.st_dev,a.st_ino,a.st_nlink)==(b.st_dev,b.st_ino,1)
  assert os.pread(fds[name],a.st_size,0)==os.pread(direct,b.st_size,0)
  print('PREOPENED_FD_EQUIVALENT',name,'dev',a.st_dev,'ino',a.st_ino,'nlink',a.st_nlink,'sha256',sha(os.pread(direct,b.st_size,0)))
 finally:os.close(direct)
args=[sys.executable,'-I','/opt/test/bootstrap/secure_bootstrap.py','--expected-controller-uid','65534','--expected-controller-gid','65534','--expected-receipt-owner','65534','--expected-receipt-mode','0700','--ledger',dbpath,'--audit',ctrl+'/audit','--root',release,'--task','task','--attempt','attempt','--receipt-key-id','test-receipt','--receipt-dir-fd',str(rfd)]
for name,flag in [('trust','--trust-fd'),('binding','--binding-fd'),('lock','--dependency-lock-fd'),('carrier','--carrier-fd'),('manifest','--manifest-fd'),('receipt','--receipt-fd'),('signkey','--receipt-signing-key-fd')]:args.extend([flag,str(fds[name])])
def demote():os.setgroups([]);os.setgid(65534);os.setuid(65534)
env=dict(os.environ)
if case=='external-path':
 evil='/code/evil';os.mkdir(evil,0o755)
 for n in ('sitecustomize.py','cryptography.py','cffi.py'):write(evil+'/'+n,b"open('/code/EVIL_EXECUTED','w').write('bad')\n",0o644,0,0)
 env['PYTHONPATH']=evil
result=subprocess.run(args,pass_fds=tuple(fds.values())+(rfd,),preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,env=env)
with sqlite3.connect(dbpath) as db:count=db.execute('select count(*) from operations').fetchone()[0];state=db.execute('select state from operations').fetchone()
current=os.readlink(release+'/current');print('exit',result.returncode,'stdout',result.stdout.strip(),'stderr',result.stderr.strip(),'ledger_count',count,'state',state,'current',current)
if case in ('POS','external-path','binding-symlink','lock-symlink'):
 assert result.returncode==0 and count==1 and state==('SUCCEEDED',) and current=='release-nonce',result.stderr
 if case=='external-path':
  assert not os.path.exists('/code/EVIL_EXECUTED')
  script="import sys,os,hashlib;sys.path.insert(0,'/opt/test/bootstrap');import secure_bootstrap as b;raw=open('/opt/test/bootstrap/DEPENDENCY_LOCK.json','rb').read();b.verify_dependency_lock(raw,{'dependency_lock_sha256':hashlib.sha256(raw).hexdigest()});import cryptography,cffi,_cffi_backend;print(cryptography.__file__);print(cffi.__file__);print(_cffi_backend.__file__)"
  origins=subprocess.run([sys.executable,'-I','-B','-c',script],preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,env=env)
  print('module origins exit',origins.returncode,'stdout',origins.stdout.strip(),'stderr',origins.stderr.strip())
  assert origins.returncode==0 and all(line.startswith('/opt/test/bootstrap/vendor/') for line in origins.stdout.strip().splitlines()) and not os.path.exists('/code/EVIL_EXECUTED')
else:assert result.returncode!=0 and count==0 and current=='base',result.stderr
print('CASE_PASS')
