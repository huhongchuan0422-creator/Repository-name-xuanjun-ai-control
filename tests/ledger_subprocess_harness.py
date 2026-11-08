"""Disposable container test: real UID 65534 CLI, TEST_ONLY signing key."""
import base64,hashlib,io,json,os,sqlite3,stat,subprocess,sys,tarfile,time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat,PrivateFormat,NoEncryption
case=sys.argv[1];assert case in ('crash','normal','path-replace')
root='/code/case';os.mkdir(root,0o700);os.chown(root,65534,65534);ctrl=root+'/controller';os.mkdir(ctrl,0o700);os.chown(ctrl,65534,65534);release=ctrl+'/releases';os.mkdir(release,0o700);os.chown(release,65534,65534);base=release+'/base';os.mkdir(base,0o700);os.chown(base,65534,65534)
canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode();sha=lambda x:hashlib.sha256(x).hexdigest()
def write(path,data):
 with open(path,'wb') as f:f.write(data)
 os.chmod(path,0o600);os.chown(path,65534,65534)
write(base+'/.bootstrap-manifest.json',canon({'members':{}}));os.symlink('base',release+'/current')
dbpath=ctrl+'/ledger';db=sqlite3.connect(dbpath);db.execute('pragma journal_mode=wal');db.execute('create table operations(nonce text primary key,task text,attempt text,state text,prestate_target text,prestate_hash text,staging_target text,manifest_hash text,intended_target text,receipt_hash text,operation_id text,carrier_digest text,manifest_digest text,tree_digest text,prestate_digest text,key_id text,receipt_path text,prestate_dev integer,prestate_ino integer,switch_intent text,binding_digest text,carrier_archive_digest text,carrier_manifest_digest text,tool_scope_digest text,source_manifest_digest text,staged_tree_digest text,receipt_key_id text)');db.execute('create table rollbacks(operation_id text primary key,request_digest text,install_op text,attempt text,from_target text,to_target text,from_digest text,to_digest text,state text,receipt_json text,receipt_path text,key_id text)');db.close();os.chmod(dbpath,0o600);os.chown(dbpath,65534,65534);write(ctrl+'/audit',b'')
key=Ed25519PrivateKey.generate();pub=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw);lock=open('/opt/test/bootstrap/DEPENDENCY_LOCK.json','rb').read();scope=canon({'schema':1,'default_off':True,'default_mode':'READ_ONLY','allowed_write_tools':[],'unknown_dynamic_tools':'DENY'});out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w') as t:
 for name,data in [('TOOL_SCOPE.json',scope),('payload',b'abc')]:
  entry=tarfile.TarInfo(name);entry.size=len(data);t.addfile(entry,io.BytesIO(data))
archive=out.getvalue();members=[{'path':name,'type':'file','size':len(data),'sha256':sha(data)} for name,data in [('TOOL_SCOPE.json',scope),('payload',b'abc')]];manifest=canon({'artifact_sha256':sha(archive),'tool_scope_sha256':sha(scope),'members':members});trust={'mode':'ED25519','environment':'TEST_ONLY','controller':'fixture','public_key':base64.b64encode(pub).decode(),'key_id':'test-receipt','binding_key_id':'test-binding','binding_public_key':base64.b64encode(pub).decode(),'dependency_lock_sha256':sha(lock),'expected_controller_uid':65534,'expected_controller_gid':65534,'expected_receipt_owner':65534,'expected_receipt_mode':448}
bp={'schema':1,'environment':'TEST_ONLY','production_trust_anchor':'REQUIRED','expiry':int(time.time())+3600,'dependency_lock_sha256':sha(lock),'carrier_archive_sha256':sha(archive),'carrier_manifest_sha256':sha(manifest),'tool_scope_sha256':sha(scope)};binding=canon({'payload':bp,'key_id':'test-binding','signature':base64.b64encode(key.sign(canon(bp))).decode()});auth={'carrier_sha256':sha(archive),'manifest_sha256':sha(manifest),'task':'task','attempt':'attempt','nonce':'nonce','expiry':int(time.time())+3600,'controller':'fixture','tool_scope':{'mode':'READ_ONLY','tools':{}}};receipt=canon({'payload':auth,'signature':base64.b64encode(key.sign(canon(auth))).decode()})
for n,data in [('trust',canon(trust)),('binding',binding),('lock',lock),('carrier',archive),('manifest',manifest),('scope',scope),('receipt',receipt),('signkey',key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))]:write(ctrl+'/'+n,data)
fds={n:os.open(ctrl+'/'+n,os.O_RDONLY) for n in ('trust','binding','lock','carrier','manifest','scope','receipt','signkey')};rfd=os.open(release,os.O_RDONLY|os.O_DIRECTORY)
args=[sys.executable,'-I','/opt/test/bootstrap/secure_bootstrap.py','--expected-controller-uid','65534','--expected-controller-gid','65534','--expected-receipt-owner','65534','--expected-receipt-mode','0700','--ledger',dbpath,'--audit',ctrl+'/audit','--root',release,'--task','task','--attempt','attempt','--receipt-key-id','test-receipt','--receipt-dir-fd',str(rfd)]
for name,flag in [('trust','--trust-fd'),('binding','--binding-fd'),('lock','--dependency-lock-fd'),('carrier','--carrier-fd'),('manifest','--manifest-fd'),('scope','--tool-scope-fd'),('receipt','--receipt-fd'),('signkey','--receipt-signing-key-fd')]:args.extend([flag,str(fds[name])])
print('CASE',case,'python',sys.version.split()[0],'sqlite',sqlite3.sqlite_version,'parent_uid_gid',os.getuid(),os.getgid(),'child_uid_gid',65534,65534)
for p in ('/opt/test/bootstrap','/opt/test/bootstrap/vendor',ctrl,release):
 st=os.stat(p);print('STAT',p,st.st_uid,st.st_gid,oct(stat.S_IMODE(st.st_mode)))
print('COMMAND',repr(args));print('BOUND_DIGESTS',sha(archive),sha(manifest),sha(scope))
if case=='path-replace':
 os.rename(ctrl+'/carrier',ctrl+'/carrier-original');write(ctrl+'/carrier',b'path-replaced');print('REPLACED_PATH_AFTER_OPEN',os.fstat(fds['carrier']).st_ino,os.stat(ctrl+'/carrier').st_ino)
def demote():os.setgroups([]);os.setgid(65534);os.setuid(65534)
def call(command):
 r=subprocess.run(command,pass_fds=tuple(fds.values())+(rfd,),preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True);print('SUBPROCESS',r.returncode,'STDOUT',r.stdout.strip(),'STDERR',r.stderr.strip());return r
def projection(label):
 with sqlite3.connect(dbpath) as d:
  d.row_factory=sqlite3.Row;rows=[dict(x) for x in d.execute('select operation_id,state,binding_digest,carrier_archive_digest,carrier_manifest_digest,tool_scope_digest,source_manifest_digest,staged_tree_digest,receipt_key_id,switch_intent,receipt_hash from operations')]
 current=os.readlink(release+'/current');link=os.lstat(release+'/current');print('PROJECTION',label,json.dumps(rows,sort_keys=True),'current',current,'current_symlink_inode',link.st_ino)
 audit=open(ctrl+'/audit','rb').read();print('AUDIT_SHA256',sha(audit),'AUDIT',audit.decode())
 if current!='base':
  for name in ('payload','TOOL_SCOPE.json','.bootstrap-manifest.json'):
   with open(release+'/'+current+'/'+name,'rb') as f:print('CURRENT_FILE_SHA256',name,sha(f.read()))
 return rows,current,link.st_ino
if case=='crash':
 r=call(args+['--test-only-crash-hook','install_crash_before_receipt']);assert r.returncode==96
 before,current,inode=projection('before_reconcile');assert current=='release-nonce' and before[0]['state']=='RUNNING' and all(before[0][x] for x in ('binding_digest','carrier_archive_digest','carrier_manifest_digest','tool_scope_digest','staged_tree_digest','receipt_key_id'))
 rec=[sys.executable,'-I','/opt/test/bootstrap/secure_bootstrap.py','--reconcile','--expected-controller-uid','65534','--expected-controller-gid','65534','--expected-receipt-owner','65534','--expected-receipt-mode','0700','--ledger',dbpath,'--audit',ctrl+'/audit','--root',release,'--receipt-dir-fd',str(rfd),'--trust-fd',str(fds['trust']),'--binding-fd',str(fds['binding']),'--dependency-lock-fd',str(fds['lock'])]
 r=call(rec);assert r.returncode!=0
 after,current,inode2=projection('after_reconcile');assert after[0]['state']=='UNKNOWN' and inode==inode2 and current=='release-nonce'
 r=call(args);assert r.returncode!=0;projection('after_retry');assert os.lstat(release+'/current').st_ino==inode
 print('RENAME_COUNT_ESTIMATE install_current_transition=1 reconcile_additional=0 basis=symlink_inode_and_controller_flow')
else:
 r=call(args);rows,current,inode=projection('after_install');assert r.returncode==0 and rows[0]['state']=='SUCCEEDED' and current=='release-nonce'
 print('RENAME_COUNT_ESTIMATE install_current_transition=1 basis=controller_flow')
print('CASE_PASS')
