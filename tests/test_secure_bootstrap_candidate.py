import base64, hashlib, importlib.util, io, json, os, sqlite3, sys, tarfile, tempfile, time, unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","bootstrap"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
import subprocess
spec=importlib.util.spec_from_file_location('bootstrap_candidate',os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class BootstrapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.getcwd());self.dir=self.tmp.name;self.fds=[]
  self.sqlite_version=sqlite3.sqlite_version_info
  if os.environ.get('MCP_TEST_TMPDIR')=='1':self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']);self.dir=self.tmp.name
  if os.environ.get('MCP_UNIT_TEST_VERSION_OVERRIDE')=='1':sqlite3.sqlite_version_info=(3,53,1)
  self.key=Ed25519PrivateKey.generate(); pub=self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
  self.trust={'mode':'ED25519','environment':'TEST_ONLY','controller':'fixture','public_key':base64.b64encode(pub).decode(),'key_id':'fixture-key'}
  with open(os.path.join(os.path.dirname(__file__),'..','bootstrap','DEPENDENCY_LOCK.json'),'rb') as f:self.lock_raw=f.read()
  self.trust['dependency_lock_sha256']=hashlib.sha256(self.lock_raw).hexdigest()
  verifier=os.path.realpath('/usr/bin/openssl');keypath=os.path.join(self.dir,'binding-public.pem')
  with open(keypath,'wb') as f:f.write(self.key.public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo))
  os.chmod(keypath,0o644);self.binding_public_key=open(keypath,'rb').read()
  with open(verifier,'rb') as f:verifier_sha=hashlib.sha256(f.read()).hexdigest()
  with open(keypath,'rb') as f:key_sha=hashlib.sha256(f.read()).hexdigest()
  self.trust.update({'binding_key_id':'binding-test-only','binding_verifier_path':verifier,'binding_verifier_sha256':verifier_sha,'binding_public_key_path':keypath,'binding_public_key_sha256':key_sha})
  bp={'schema':1,'environment':'TEST_ONLY','production_trust_anchor':'REQUIRED','expiry':int(time.time())+3600,'dependency_lock_sha256':self.trust['dependency_lock_sha256'],'vendor_tree_digest':self.trust['dependency_lock_sha256'],'bootstrap_manifest_sha256':'1'*64,'carrier_manifest_sha256':'2'*64,'tool_scope_sha256':'3'*64}
  self.binding_raw=b.canonical({'payload':bp,'key_id':'binding-test-only','signature':base64.b64encode(self.key.sign(b.canonical(bp))).decode()})
  z=io.BytesIO()
  with tarfile.open(fileobj=z,mode='w') as t:
   m=tarfile.TarInfo('payload');m.size=3;t.addfile(m,io.BytesIO(b'abc'))
  self.carrier=z.getvalue();self.manifest=b.canonical({'members':{'payload':{'type':'file','size':3,'sha256':b.sha(b'abc')}},'tool_scope':{},'minimum_sqlite':[3,35,0]})
  self.payload={'carrier_sha256':b.sha(self.carrier),'manifest_sha256':b.sha(self.manifest),'task':'task','attempt':'attempt','nonce':'nonce','expiry':int(time.time())+1000,'controller':'fixture','tool_scope':{'mode':'READ_ONLY','tools':{}}}
  self.ledger=os.path.join(self.dir,'ledger');db=sqlite3.connect(self.ledger);db.execute('pragma journal_mode=wal');db.execute('create table operations(nonce text primary key,task text,attempt text,state text,prestate_target text,prestate_hash text,staging_target text,manifest_hash text,intended_target text,receipt_hash text,operation_id text,carrier_digest text,manifest_digest text,tree_digest text,prestate_digest text,key_id text,receipt_path text,prestate_dev integer,prestate_ino integer,switch_intent text)');db.execute('create table rollbacks(operation_id text primary key,request_digest text,install_op text,attempt text,from_target text,to_target text,from_digest text,to_digest text,state text,receipt_json text,receipt_path text,key_id text)');db.close();os.chmod(self.ledger,0o600)
  self.log=os.path.join(self.dir,'log');open(self.log,'wb').close();os.chmod(self.log,0o600)
 def tearDown(self):
  for fd in self.fds:os.close(fd)
  sqlite3.sqlite_version_info=self.sqlite_version;self.tmp.cleanup()
 def fd(self,name,data):
  p=os.path.join(self.dir,name);open(p,'wb').write(data);os.chmod(p,0o600);fd=os.open(p,os.O_RDONLY);self.fds.append(fd);return fd
 def make_lock_fd(self):return self.fd('dependency-lock',self.lock_raw)
 def make_binding_fd(self):return self.fd('binding',self.binding_raw)
 def verify(self, payload=None,signature=None,carrier=None,manifest=None,trust=None,scope=None):
  p=payload or self.payload; signature=signature if signature is not None else base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier if carrier is None else carrier);mf=self.fd('manifest',self.manifest if manifest is None else manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':signature}));tf=self.fd('trust',b.canonical(trust or self.trust));lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  return b.verify(cf,mf,rf,tf,self.ledger,lf,scope or {'task':'task','attempt':'attempt'},owner=os.getuid())
 def test_valid_and_replay(self):
  self.assertEqual(self.verify()[0],self.carrier)
  with self.assertRaises(Exception):self.verify()
 def test_signature(self):
  with self.assertRaisesRegex(b.Hold,'SIGNATURE_INVALID'):self.verify(signature=base64.b64encode(b'bad').decode())
 def test_digest(self):
  with self.assertRaisesRegex(b.Hold,'DIGEST_MISMATCH'):self.verify(carrier=b'bad')
 def test_expiry(self):
  p=dict(self.payload,expiry=1)
  with self.assertRaisesRegex(b.Hold,'RECEIPT_EXPIRED'):self.verify(payload=p)
 def test_scope(self):
  with self.assertRaisesRegex(b.Hold,'RECEIPT_SCOPE'):self.verify(scope={'task':'other','attempt':'attempt'})
 def test_archive_traversal_and_link(self):
  for name,kind in [('../x',tarfile.REGTYPE),('link',tarfile.SYMTYPE)]:
   z=io.BytesIO()
   with tarfile.open(fileobj=z,mode='w') as t:
    m=tarfile.TarInfo(name);m.type=kind;m.linkname='x';t.addfile(m)
   with self.assertRaises(b.Hold):b.inspect_archive(z.getvalue(),{})
 def test_open_nofollow_and_traversal(self):
  os.symlink('/etc/passwd',os.path.join(self.dir,'link'));dfd=os.open(self.dir,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(dfd)
  for path in ('../x','/etc/passwd','link'):
   with self.assertRaises(Exception):b.open_relative(dfd,path)
 def test_hardlink_and_device(self):
  self.fd('a',b'x');os.link(os.path.join(self.dir,'a'),os.path.join(self.dir,'hard'));f=os.open(os.path.join(self.dir,'hard'),os.O_RDONLY);self.fds.append(f)
  with self.assertRaises(b.Hold):b.stable_read(f,os.getuid(),100)
  f=os.open('/dev/null',os.O_RDONLY);self.fds.append(f)
  with self.assertRaises(b.Hold):b.stable_read(f,os.getuid(),100)
 def test_missing_log(self):
  os.unlink(self.log)
  with self.assertRaises(FileNotFoundError):self.verify()
 def test_missing_ledger(self):
  os.unlink(self.ledger)
  with self.assertRaises((OSError,ValueError)):self.verify()
if __name__=='__main__':unittest.main()

class InstallerTests(BootstrapTests):
 def setUp(self):
  super().setUp();self.root=os.path.join(self.dir,'root');os.mkdir(self.root,0o700)
  os.mkdir(os.path.join(self.root,'base'),0o700)
  with open(os.path.join(self.root,'base','.bootstrap-manifest.json'),'wb') as f:f.write(b.canonical({'members':{}}))
  os.chmod(os.path.join(self.root,'base','.bootstrap-manifest.json'),0o600);os.symlink('base',os.path.join(self.root,'current'))
 def run_install(self,failpoint=None):
  import sys
  sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'))
  import controller
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  args=[self.fd('carrier',self.carrier),self.fd('manifest',self.manifest),self.fd('receipt',b.canonical({'payload':p,'signature':sig})),self.fd('trust',b.canonical(self.trust)),self.ledger]
  lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  keyfd=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
  return controller.run(*(args+[lf,{'task':p['task'],'attempt':p['attempt']},self.root]),owner=os.getuid(),failpoint=failpoint,signing_key_fd=keyfd,key_id='fixture-key')
 def state(self):
  with sqlite3.connect(self.ledger) as db:return db.execute('select state from operations').fetchone()[0]
 def test_install_and_reinstall(self):
  self.assertEqual(self.run_install(),'release-nonce');self.assertEqual(os.readlink(os.path.join(self.root,'current')),'release-nonce');self.assertEqual(self.state(),'SUCCEEDED')
  with self.assertRaises(Exception):self.run_install()
 def test_signed_receipt_and_reconcile(self):
  import controller
  self.run_install()
  with open(os.path.join(self.root,'receipt-nonce.json'),'rb') as f:raw=f.read()
  item=b.parse(raw);self.key.public_key().verify(base64.b64decode(item['signature']),b.canonical(item['payload']))
  self.assertEqual(item['payload']['operation_id'],'install:nonce')
  with sqlite3.connect(self.ledger) as db:db.execute("update operations set state='UNKNOWN' where nonce='nonce'")
  lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  self.assertEqual(controller.reconcile_pending(self.ledger,os.getuid(),self.root,lf,trust_raw=b.canonical(self.trust)),0)
  self.assertEqual(self.state(),'SUCCEEDED')
 def test_bad_signing_key_prevents_effects(self):
  import controller
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  args=[self.fd('carrier',self.carrier),self.fd('manifest',self.manifest),self.fd('receipt',b.canonical({'payload':p,'signature':sig})),self.fd('trust',b.canonical(self.trust)),self.ledger]
  lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  bad=self.fd('bad-key',Ed25519PrivateKey.generate().private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
  with self.assertRaisesRegex(controller.ControllerError,'SIGNING_KEY_MISMATCH'):
   controller.run(*(args+[lf,{'task':'task','attempt':'attempt'},self.root]),owner=os.getuid(),signing_key_fd=bad,key_id='fixture-key')
  self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
 def test_receipt_write_failure_is_unknown(self):
  open(os.path.join(self.root,'receipt-nonce.json'),'wb').close()
  with self.assertRaises(Exception):self.run_install()
  self.assertEqual(self.state(),'UNKNOWN')
 def test_tree_tamper_prevents_recovery_success(self):
  import controller
  self.run_install()
  with sqlite3.connect(self.ledger) as db:db.execute("update operations set state='UNKNOWN' where nonce='nonce'")
  with open(os.path.join(self.root,'release-nonce','payload'),'wb') as f:f.write(b'evil')
  lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  self.assertEqual(controller.reconcile_pending(self.ledger,os.getuid(),self.root,lf,trust_raw=b.canonical(self.trust)),1)
  self.assertEqual(self.state(),'UNKNOWN')
 def test_failure_windows_unknown(self):
  import sys
  sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'));import controller
  with self.assertRaises(controller.ControllerError):self.run_install('after_switch')
  self.assertEqual(self.state(),'UNKNOWN')
  with self.assertRaises(Exception):self.run_install()
 def test_missing_switch_intent_blocks_new_reservation(self):
  with self.assertRaises(Exception):self.run_install('after_extract')
  self.assertEqual(self.state(),'UNKNOWN');self.payload=dict(self.payload,nonce='next',attempt='next-attempt')
  with self.assertRaisesRegex(Exception,'UNKNOWN_RECONCILIATION_REQUIRED'):self.run_install()
 def test_ambiguous_switch_blocks_next_install(self):
  with self.assertRaises(Exception):self.run_install('after_switch')
  self.payload=dict(self.payload,nonce='next',attempt='next-attempt')
  with self.assertRaisesRegex(Exception,'UNKNOWN_RECONCILIATION_REQUIRED'):self.run_install()
  self.assertEqual(self.state(),'UNKNOWN')
 def test_cli_install_with_actual_runtime(self):
  import subprocess
  if os.getuid()!=0:
   self.skipTest('CLI enforces root-owned inputs; run in isolated uid-0 container')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd()
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py')
  cmd=[sys.executable,'-I',cli,'--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--ledger',self.ledger,'--audit',self.log,'--task','task','--attempt','attempt','--root',self.root]
  proc=subprocess.run(cmd,pass_fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd),stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
  if os.environ.get('MCP_EXPECT_OLD_SQLITE')=='1':
   self.assertLess(sqlite3.sqlite_version_info,(3,35,0));self.assertNotEqual(proc.returncode,0);self.assertIn('SQLITE_VERSION_UNSUPPORTED',proc.stderr)
   with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select count(*) from operations').fetchone()[0],0)
   return
  self.assertGreaterEqual(sqlite3.sqlite_version_info,(3,35,0));self.assertEqual(proc.returncode,0,proc.stderr);self.assertEqual(self.state(),'SUCCEEDED')
  with open(os.path.join(self.root,'release-nonce','payload'),'rb') as f:self.assertEqual(f.read(),b'abc')
  with open(os.path.join(self.root,'receipt-nonce.json'),'rb') as f:item=b.parse(f.read())
  self.key.public_key().verify(base64.b64decode(item['signature']),b.canonical(item['payload']))
  with open(self.log,'rb') as f:self.assertIn(b'SUCCEEDED',f.read())
 def test_cli_reconcile_tampering(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd()
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py')
  base=[sys.executable,'-I',cli,'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root]
  install=base+['--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--task','task','--attempt','attempt']
  fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd);r=subprocess.run(install,pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.assertEqual(r.returncode,0,r.stderr);target=os.path.join(self.root,'release-nonce');receipt=os.path.join(self.root,'receipt-nonce.json')
  with open(receipt,'rb') as f:original=f.read()
  for mode in ('content','symlink','receipt'):
   with self.subTest(mode=mode):
    with sqlite3.connect(self.ledger) as db:db.execute("update operations set state='UNKNOWN' where nonce='nonce'")
    if mode=='content':
     with open(os.path.join(target,'payload'),'wb') as f:f.write(b'bad')
    elif mode=='symlink':os.symlink('/etc/passwd',os.path.join(target,'evil'))
    else:
     with open(receipt,'wb') as f:f.write(b'bad')
    r=subprocess.run(base+['--reconcile'],pass_fds=(tf,rd,lockfd,bindingfd),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertNotEqual(r.returncode,0);self.assertEqual(self.state(),'UNKNOWN')
    r=subprocess.run(install,pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertNotEqual(r.returncode,0)
    if mode=='content':
     with open(os.path.join(target,'payload'),'wb') as f:f.write(b'abc')
    elif mode=='symlink':os.unlink(os.path.join(target,'evil'))
    else:
     with open(receipt,'wb') as f:f.write(original)
 def test_cli_nonroot_receipt_isolation(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires disposable root-owned container')
  uid=65534;gid=65534;p=self.payload;self.trust.update({'expected_controller_uid':uid,'expected_controller_gid':gid,'expected_receipt_owner':0,'expected_receipt_mode':0o555})
  sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd()
  os.chown(os.path.dirname(__file__),0,0);os.chmod(os.path.dirname(__file__),0o755)
  os.chown(os.path.join(os.path.dirname(__file__),'..','bootstrap'),0,0);os.chmod(os.path.join(os.path.dirname(__file__),'..','bootstrap'),0o755)
  os.chown(os.path.join(os.path.dirname(__file__),'..','bootstrap','vendor'),0,0);os.chmod(os.path.join(os.path.dirname(__file__),'..','bootstrap','vendor'),0o755)
  for source in ('secure_bootstrap.py','controller.py','path_guard.py'):
   path=os.path.join(os.path.dirname(__file__),'..','bootstrap',source);os.chown(path,0,0);os.chmod(path,0o644)
  receipt_dir=os.path.join(self.dir,'locked-receipts');os.mkdir(receipt_dir,0o555);os.chmod(receipt_dir,0o555);rd=os.open(receipt_dir,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  for path in [self.dir,self.ledger,self.log,self.root,os.path.join(self.root,'base'),os.path.join(self.root,'base','.bootstrap-manifest.json')]+[os.path.join(self.dir,n) for n in ('carrier','manifest','receipt','trust','signing-key','dependency-lock','binding')]:os.chown(path,uid,gid)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py')
  cmd=[sys.executable,'-I',cli,'--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--receipt-dir-fd',str(rd),'--expected-controller-uid',str(uid),'--expected-controller-gid',str(gid),'--expected-receipt-owner','0','--expected-receipt-mode','0555','--ledger',self.ledger,'--audit',self.log,'--task','task','--attempt','attempt','--root',self.root]
  def demote():os.setgroups([]);os.setgid(gid);os.setuid(uid)
  r=subprocess.run(cmd,pass_fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd),preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.assertNotEqual(r.returncode,0);self.assertIn(b'RECEIPT_DIRECTORY_UNWRITABLE',r.stderr);self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select count(*) from operations').fetchone()[0],0)
  print('NONROOT_TEST uid=%s gid=%s receipt=0:0 mode=0555 exit=%s ledger=empty current=base' %(uid,gid,r.returncode))
  os.chmod(receipt_dir,0o700);os.chown(receipt_dir,uid,gid)
  self.trust.update({'expected_receipt_owner':uid,'expected_receipt_mode':0o700})
  with open(os.path.join(self.dir,'trust'),'wb') as f:f.write(b.canonical(self.trust))
  cmd[cmd.index('--expected-receipt-owner')+1]=str(uid);cmd[cmd.index('--expected-receipt-mode')+1]='0700'
  r=subprocess.run(cmd,pass_fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd),preexec_fn=demote,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(os.readlink(os.path.join(self.root,'current')),'release-nonce')
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from operations').fetchone()[0],'SUCCEEDED')
  self.assertTrue(os.path.isfile(os.path.join(receipt_dir,'receipt-nonce.json')))
  print('NONROOT_POSITIVE uid=%s receipt_owner=%s mode=0700 exit=0 ledger=SUCCEEDED' %(uid,uid))
 def test_cli_authorized_rollback(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd();rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py');common=[sys.executable,'-I',cli,'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root];fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd)
  install=common+['--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--task','task','--attempt','attempt']
  r=subprocess.run(install,pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,0,r.stderr)
  with sqlite3.connect(self.ledger) as db:pre=db.execute('select prestate_digest from operations').fetchone()[0]
  payload={'install_op':'install:nonce','prestate_digest':pre,'rollback_op':'rollback:one','nonce':'rollback-nonce','expiry':int(time.time())+600,'controller':'fixture'}
  def authfd(data,signature=None):
   sign=signature or base64.b64encode(self.key.sign(b.canonical(data))).decode()
   return self.fd('rollback-auth',b.canonical({'payload':data,'signature':sign,'key_id':'fixture-key'}))
  def call(data,signature=None):
   fd=authfd(data,signature);cmd=common+['--rollback','--rollback-authorization-fd',str(fd),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key']
   return subprocess.run(cmd,pass_fds=fds+(fd,),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  for invalid in (dict(payload,expiry=1),dict(payload,install_op='install:wrong')):
   result=call(invalid);self.assertNotEqual(result.returncode,0);self.assertEqual(os.readlink(os.path.join(self.root,'current')),'release-nonce')
  result=call(payload,base64.b64encode(b'bad').decode());self.assertNotEqual(result.returncode,0)
  result=call(payload);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
  with open(self.log,'rb') as f:events=[json.loads(x) for x in f if x.strip()]
  self.assertEqual(sum(e.get('event')=='ROLLBACK_SWITCH' and e.get('operation')=='rollback:one' for e in events),1)
  again=call(payload);self.assertEqual(again.returncode,0,again.stderr);self.assertEqual(result.stdout,again.stdout)
  with open(self.log,'rb') as f:events=[json.loads(x) for x in f if x.strip()]
  self.assertEqual(sum(e.get('event')=='ROLLBACK_SWITCH' and e.get('operation')=='rollback:one' for e in events),1)
  receipt_path=os.path.join(self.root,'rollback-'+hashlib.sha256(b'rollback:one').hexdigest()+'.json')
  with open(receipt_path,'rb') as f:original=f.read()
  original_hash=hashlib.sha256(original).hexdigest();linkstat=os.lstat(os.path.join(self.root,'current'))
  for field in ('payload','signature','key_id','operation'):
   obj=b.parse(original)
   if field=='payload':obj['payload']['from_tree_digest']='0'*64
   elif field=='signature':obj['signature']=base64.b64encode(b'bad').decode()
   elif field=='key_id':obj['key_id']='wrong'
   else:obj['payload']['rollback_op']='wrong'
   with open(receipt_path,'wb') as f:f.write(b.canonical(obj))
   attempt=call(payload);self.assertNotEqual(attempt.returncode,0);self.assertEqual(os.lstat(os.path.join(self.root,'current')).st_ino,linkstat.st_ino)
   with open(receipt_path,'wb') as f:f.write(original)
  self.assertEqual(hashlib.sha256(original).hexdigest(),original_hash)
 def test_cli_rollback_crash_windows(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd();rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py');common=[sys.executable,'-I',cli,'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root];fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd)
  cmd=common+['--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--task','task','--attempt','attempt']
  r=subprocess.run(cmd,pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,0,r.stderr)
  with sqlite3.connect(self.ledger) as db:pre=db.execute('select prestate_digest from operations').fetchone()[0]
  for i,(hook,code,current,state) in enumerate([('crash_before_rename',91,'release-nonce','FAILED'),('crash_after_rename',92,'base','UNKNOWN'),('crash_before_receipt',93,'base','UNKNOWN')]):
   with self.subTest(hook=hook):
    if os.readlink(os.path.join(self.root,'current'))!='release-nonce':os.unlink(os.path.join(self.root,'current'));os.symlink('release-nonce',os.path.join(self.root,'current'))
    with sqlite3.connect(self.ledger) as db:db.execute('delete from rollbacks')
    payload={'install_op':'install:nonce','prestate_digest':pre,'rollback_op':'rollback:'+str(i),'nonce':'nonce:'+str(i),'expiry':int(time.time())+600,'controller':'fixture'}
    afd=self.fd('authorization-'+str(i),b.canonical({'payload':payload,'signature':base64.b64encode(self.key.sign(b.canonical(payload))).decode(),'key_id':'fixture-key'}))
    rb=common+['--rollback','--rollback-authorization-fd',str(afd),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--test-only-crash-hook',hook]
    r=subprocess.run(rb,pass_fds=fds+(afd,),stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,code,r.stderr)
    with sqlite3.connect(self.ledger) as db:
     row=db.execute('select state,receipt_path,key_id,from_digest,to_digest,install_op,operation_id from rollbacks').fetchone()
     self.assertEqual(row[0],'SWITCHED' if i==2 else 'ROLLBACK_PREPARED');self.assertTrue(all(row[1:]));self.assertEqual(row[-2: ],('install:nonce','rollback:'+str(i)))
    self.assertEqual(os.readlink(os.path.join(self.root,'current')),current)
    with open(self.log,'rb') as f:before=[json.loads(x) for x in f if x.strip()]
    switches=lambda events:sum(e.get('event')=='ROLLBACK_SWITCH' and e.get('operation')=='rollback:'+str(i) for e in events)
    self.assertEqual(switches(before),0 if i==0 else 1)
    r=subprocess.run(common+['--reconcile'],pass_fds=(tf,rd,lockfd,bindingfd),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertEqual(r.returncode,0 if state=='FAILED' else 1,r.stderr)
    with open(self.log,'rb') as f:after=[json.loads(x) for x in f if x.strip()]
    self.assertEqual(switches(before),switches(after))
    with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from rollbacks').fetchone()[0],state)
    if state=='UNKNOWN':
     r=subprocess.run(rb,pass_fds=fds+(afd,),stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertNotEqual(r.returncode,0)
 def test_cli_rollback_missing_schema_columns(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd();tf=self.fd('schema-trust',b.canonical(self.trust));rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py');cmd=[sys.executable,'-I',cli,'--reconcile','--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root]
  columns=['operation_id','request_digest','install_op','attempt','from_target','to_target','from_digest','to_digest','state','receipt_json','receipt_path','key_id']
  for missing in ('state','receipt_path','key_id','from_digest','to_digest','install_op','operation_id'):
   with self.subTest(missing=missing):
    with sqlite3.connect(self.ledger) as db:
     db.execute('drop table rollbacks');remaining=[c for c in columns if c!=missing]
     db.execute('create table rollbacks('+','.join(c+' text' for c in remaining)+')');db.execute('insert into rollbacks('+','.join(remaining)+') values('+','.join('?' for _ in remaining)+')',tuple('UNKNOWN' if c=='state' else 'fixture' for c in remaining))
    r=subprocess.run(cmd,pass_fds=(tf,rd,lockfd,bindingfd),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertNotEqual(r.returncode,0);self.assertIn(b'ROLLBACK_SCHEMA_REQUIRED',r.stderr);self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
    with sqlite3.connect(self.ledger) as db:
     if missing!='state':self.assertEqual(db.execute('select state from rollbacks').fetchone()[0],'UNKNOWN')
 def test_cli_twenty_process_install_rollback(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd();rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py');base=[sys.executable,'-I',cli,'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root];fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd)
  cmd=base+['--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--task','task','--attempt','attempt']
  procs=[subprocess.Popen(cmd,pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(20)];results=[(p.wait(timeout=30),p.communicate()) for p in procs]
  self.assertEqual(sum(r[0]==0 for r in results),1)
  with sqlite3.connect(self.ledger) as db:pre=db.execute('select prestate_digest from operations').fetchone()[0]
  payload={'install_op':'install:nonce','prestate_digest':pre,'rollback_op':'rollback:parallel','nonce':'parallel-nonce','expiry':int(time.time())+600,'controller':'fixture'}
  afd=self.fd('concurrent-auth',b.canonical({'payload':payload,'signature':base64.b64encode(self.key.sign(b.canonical(payload))).decode(),'key_id':'fixture-key'}))
  rb=base+['--rollback','--rollback-authorization-fd',str(afd),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key']
  procs=[subprocess.Popen(rb,pass_fds=fds+(afd,),stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(20)];results=[(p.wait(timeout=30),p.communicate()) for p in procs]
  self.assertTrue(all(r[0]==0 for r in results),results);self.assertEqual(len({r[1][0] for r in results}),1)
  with open(self.log,'rb') as f:events=[json.loads(x) for x in f if x.strip()]
  self.assertEqual(sum(e.get('event')=='ROLLBACK_SWITCH' and e.get('operation')=='rollback:parallel' for e in events),1)
  self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
 def test_cli_install_crash_after_switch_before_audit(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd();rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py');base=[sys.executable,'-I',cli,'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root];fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd)
  install=base+['--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--task','task','--attempt','attempt']
  r=subprocess.run(install+['--test-only-crash-hook','install_crash_after_rename'],pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,94,r.stderr)
  self.assertEqual(os.readlink(os.path.join(self.root,'current')),'release-nonce');before=os.lstat(os.path.join(self.root,'current')).st_ino
  with sqlite3.connect(self.ledger) as db:
   state,intent=db.execute('select state,switch_intent from operations').fetchone();self.assertEqual(state,'RUNNING');self.assertEqual(json.loads(intent)['operation_id'],'install:nonce')
  r=subprocess.run(base+['--reconcile'],pass_fds=(tf,rd,lockfd,bindingfd),stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertNotEqual(r.returncode,0)
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from operations').fetchone()[0],'UNKNOWN')
  self.assertEqual(os.lstat(os.path.join(self.root,'current')).st_ino,before)
 def test_cli_three_install_crash_windows(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd();rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py');base=[sys.executable,'-I',cli,'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--ledger',self.ledger,'--audit',self.log,'--root',self.root];fds=(cf,mf,rf,tf,kf,rd,lockfd,bindingfd)
  install=base+['--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--receipt-signing-key-fd',str(kf),'--receipt-key-id','fixture-key','--task','task','--attempt','attempt']
  for hook,code,expected_current,expected_state in [('install_crash_before_rename',95,'base','FAILED'),('install_crash_after_rename',94,'release-nonce','UNKNOWN'),('install_crash_before_receipt',96,'release-nonce','UNKNOWN')]:
   with self.subTest(hook=hook):
    r=subprocess.run(install+['--test-only-crash-hook',hook],pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(r.returncode,code,r.stderr)
    with sqlite3.connect(self.ledger) as db:row=db.execute('select switch_intent,operation_id,attempt,prestate_dev,prestate_ino,prestate_digest,tree_digest from operations').fetchone()
    intent=json.loads(row[0]);self.assertEqual(intent['operation_id'],row[1]);self.assertEqual(intent['fence'],row[2]);self.assertEqual((intent['from_dev'],intent['from_ino']),(row[3],row[4]));self.assertEqual((intent['from_tree'],intent['to_tree']),(row[5],row[6]))
    st=os.stat(os.path.join(self.root,'release-nonce'));self.assertEqual((intent['to_dev'],intent['to_ino']),(st.st_dev,st.st_ino));self.assertEqual(os.readlink(os.path.join(self.root,'current')),expected_current)
    before=os.lstat(os.path.join(self.root,'current')).st_ino;r=subprocess.run(base+['--reconcile'],pass_fds=(tf,rd,lockfd,bindingfd),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertEqual(r.returncode,0 if expected_state=='FAILED' else 1,r.stderr);self.assertEqual(os.lstat(os.path.join(self.root,'current')).st_ino,before)
    with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from operations').fetchone()[0],expected_state);db.execute('delete from operations')
    if expected_current!='base':os.unlink(os.path.join(self.root,'current'));os.symlink('base',os.path.join(self.root,'current'))
    import shutil
    shutil.rmtree(os.path.join(self.root,'release-nonce'))
    try:os.unlink(os.path.join(self.root,'.current-nonce'))
    except FileNotFoundError:pass
 def test_cli_negative_cases(self):
  import subprocess
  if os.getuid()!=0:self.skipTest('requires isolated uid 0')
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  cf=self.fd('carrier',self.carrier);mf=self.fd('manifest',self.manifest);rf=self.fd('receipt',b.canonical({'payload':p,'signature':sig}));tf=self.fd('trust',b.canonical(self.trust));kf=self.fd('signing-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));lockfd=self.make_lock_fd();bindingfd=self.make_binding_fd()
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd)
  bad=self.fd('bad-key',Ed25519PrivateKey.generate().private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
  cli=os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py')
  common=[cli,'--carrier-fd',str(cf),'--manifest-fd',str(mf),'--receipt-fd',str(rf),'--binding-fd',str(bindingfd),'--dependency-lock-fd',str(lockfd),'--trust-fd',str(tf),'--receipt-dir-fd',str(rd),'--receipt-key-id','fixture-key','--ledger',self.ledger,'--audit',self.log,'--task','task','--attempt','attempt','--root',self.root]
  fds=(cf,mf,rf,tf,kf,bad,rd,lockfd,bindingfd)
  for name,extra in [('missing-key',[]),('wrong-key',['--receipt-signing-key-fd',str(bad)])]:
   with self.subTest(name=name):
    proc=subprocess.run([sys.executable,'-I']+common+extra,pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    self.assertNotEqual(proc.returncode,0);self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
  with open(os.path.join(self.root,'receipt-nonce.json'),'wb') as f:f.write(b'conflict')
  proc=subprocess.run([sys.executable,'-I']+common+['--receipt-signing-key-fd',str(kf)],pass_fds=fds,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.assertNotEqual(proc.returncode,0);self.assertEqual(self.state(),'UNKNOWN')
 def test_old_schema_install_fails_closed(self):
  with sqlite3.connect(self.ledger) as db:
   db.execute('drop table operations');db.execute('create table operations(nonce text primary key,task text,attempt text,state text)')
  with self.assertRaisesRegex(Exception,'LEDGER_SCHEMA_UPGRADE_REQUIRED'):self.run_install()
  self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
 def test_rollback_success_and_idempotence(self):
  import controller
  self.run_install();trustfd=self.fd('rollback-trust',b.canonical(self.trust));keyfd=self.fd('rollback-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd);lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  args=(self.ledger,self.root,os.getuid(),lf,trustfd,keyfd,'fixture-key',rd,'install:nonce','rollback:one','a'*64)
  result=controller.rollback(*args);self.assertEqual(result['state'],'SUCCEEDED');self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
  item=b.parse(result['receipt'].encode());self.key.public_key().verify(base64.b64decode(item['signature']),b.canonical(item['payload']))
  self.assertEqual(controller.rollback(*args),result)
 def test_rollback_prestate_tampering_refused(self):
  import controller
  self.run_install();trustfd=self.fd('rollback-trust',b.canonical(self.trust));keyfd=self.fd('rollback-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd);lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  with open(os.path.join(self.root,'base','.bootstrap-manifest.json'),'wb') as f:f.write(b'tampered')
  with self.assertRaises(Exception):controller.rollback(self.ledger,self.root,os.getuid(),lf,trustfd,keyfd,'fixture-key',rd,'install:nonce','rollback:one','a'*64)
  self.assertEqual(os.readlink(os.path.join(self.root,'current')),'release-nonce')
 def test_rollback_faults_leave_unknown(self):
  import controller
  self.run_install();trustfd=self.fd('rollback-trust',b.canonical(self.trust));keyfd=self.fd('rollback-key',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
  rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd);lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  with self.assertRaises(controller.ControllerError):controller.rollback(self.ledger,self.root,os.getuid(),lf,trustfd,keyfd,'fixture-key',rd,'install:nonce','rollback:one','a'*64,failpoint='after_rename')
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from rollbacks').fetchone()[0],'UNKNOWN')
  self.assertEqual(os.readlink(os.path.join(self.root,'current')),'base')
 def test_rollback_three_failure_windows_reconcile(self):
  import controller
  self.run_install();tf=self.fd('rbtrust',b.canonical(self.trust));kf=self.fd('rbkey',self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()));rd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.fds.append(rd);lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  args=(self.ledger,self.root,os.getuid(),lf,tf,kf,'fixture-key',rd,'install:nonce','rollback:one','a'*64)
  with self.assertRaises(controller.ControllerError):controller.rollback(*args,failpoint='before_rename')
  self.assertEqual(controller.reconcile_pending(self.ledger,os.getuid(),self.root,lf,trust_raw=b.canonical(self.trust),receipt_dir_fd=rd),0)
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from rollbacks').fetchone()[0],'FAILED');db.execute('delete from rollbacks')
  with self.assertRaises(controller.ControllerError):controller.rollback(*args,failpoint='after_rename')
  self.assertEqual(controller.reconcile_pending(self.ledger,os.getuid(),self.root,lf,trust_raw=b.canonical(self.trust),receipt_dir_fd=rd),1)
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from rollbacks').fetchone()[0],'UNKNOWN');db.execute('delete from rollbacks')
  os.unlink(os.path.join(self.root,'current'));os.symlink('release-nonce',os.path.join(self.root,'current'))
  with self.assertRaises(controller.ControllerError):controller.rollback(*args,failpoint='before_receipt')
  self.assertEqual(controller.reconcile_pending(self.ledger,os.getuid(),self.root,lf,trust_raw=b.canonical(self.trust),receipt_dir_fd=rd),1)
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select state from rollbacks').fetchone()[0],'UNKNOWN')
 def test_recover_running_as_unknown(self):
  import sys
  sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'));import controller
  with sqlite3.connect(self.ledger) as db:db.execute("insert into operations(nonce,task,attempt,state) values('n','t','a','RUNNING')")
  controller.recover(self.ledger,os.getuid());self.assertEqual(self.state(),'UNKNOWN')

class ScopeAndConcurrencyTests(BootstrapTests):
 def test_write_scope_denied_by_default(self):
  manifest=b.canonical({'members':{'payload':{'type':'file','size':3,'sha256':b.sha(b'abc')}},'tool_scope':{'task_submit':'project-a'},'minimum_sqlite':[3,35,0]})
  p=dict(self.payload,manifest_sha256=b.sha(manifest))
  with self.assertRaisesRegex(b.Hold,'TOOL_SCOPE_DENIED'):self.verify(payload=p,manifest=manifest)
 def test_write_scope_allowed_when_explicit(self):
  manifest=b.canonical({'members':{'payload':{'type':'file','size':3,'sha256':b.sha(b'abc')}},'tool_scope':{'task_submit':'project-a'},'minimum_sqlite':[3,35,0]})
  p=dict(self.payload,manifest_sha256=b.sha(manifest),tool_scope={'mode':'WRITE_ALLOWED','tools':{'task_submit':'project-a'}})
  self.verify(payload=p,manifest=manifest)
 def test_read_only_rejects_named_write(self):
  manifest=b.canonical({'members':{'payload':{'type':'file','size':3,'sha256':b.sha(b'abc')}},'tool_scope':{'task_submit':'project-a'},'minimum_sqlite':[3,35,0]})
  p=dict(self.payload,manifest_sha256=b.sha(manifest),tool_scope={'mode':'READ_ONLY','tools':{'task_submit':'project-a'}})
  with self.assertRaisesRegex(b.Hold,'WRITE_TOOL_DENIED'):self.verify(payload=p,manifest=manifest)
 def test_relative_ledger_rejected(self):
  with self.assertRaisesRegex(b.Hold,'LEDGER_ABSOLUTE_REQUIRED'):b.checked_ledger_path('ledger',os.getuid())
 def test_concurrent_consume_twenty_processes(self):
  import multiprocessing
  ctx=multiprocessing.get_context('fork');start=ctx.Event();queue=ctx.Queue()
  def worker(i):
   start.wait()
   try:b.consume(self.ledger,dict(self.payload,nonce='n'+str(i)),os.getuid());queue.put('ok')
   except Exception:queue.put('reject')
  jobs=[ctx.Process(target=worker,args=(i,)) for i in range(20)]
  for job in jobs:job.start()
  start.set();out=[queue.get(timeout=15) for _ in jobs]
  for job in jobs:job.join(15);self.assertEqual(job.exitcode,0)
  self.assertEqual(out.count('ok'),1);self.assertEqual(out.count('reject'),19)

class SqlitePreflightTests(BootstrapTests):
 def test_unsupported_sqlite_rejected_before_reserve(self):
  sqlite3.sqlite_version_info=(3,26,0)
  with self.assertRaisesRegex(b.Hold,'SQLITE_VERSION_UNSUPPORTED'):self.verify()
  with sqlite3.connect(self.ledger) as db:self.assertEqual(db.execute('select count(*) from operations').fetchone()[0],0)

class UnknownToolTests(BootstrapTests):
 def test_signed_unknown_tool_rejected(self):
  manifest=b.canonical({'members':{'payload':{'type':'file','size':3,'sha256':b.sha(b'abc')}},'tool_scope':{'dynamic_admin':'project-a'},'minimum_sqlite':[3,35,0]})
  p=dict(self.payload,manifest_sha256=b.sha(manifest),tool_scope={'mode':'WRITE_ALLOWED','tools':{'dynamic_admin':'project-a'}})
  with self.assertRaisesRegex(b.Hold,'UNKNOWN_TOOL_DENIED'):self.verify(payload=p,manifest=manifest)

class VendorTamperTests(unittest.TestCase):
 def test_vendor_tampering_and_isolated_paths(self):
  import shutil,subprocess
  source=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','bootstrap'))
  with tempfile.TemporaryDirectory(dir=os.getcwd()) as d:
   copy=os.path.join(d,'bootstrap');shutil.copytree(source,copy,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   raw=open(os.path.join(copy,'DEPENDENCY_LOCK.json'),'rb').read();digest=hashlib.sha256(raw).hexdigest()
   script="import sys,hashlib;sys.path.insert(0,sys.argv[1]);import secure_bootstrap as b;raw=open(sys.argv[1]+'/DEPENDENCY_LOCK.json','rb').read();b.verify_dependency_lock(raw,{'dependency_lock_sha256':sys.argv[2]});import cryptography,cffi,_cffi_backend;print(cryptography.__file__,cffi.__file__,_cffi_backend.__file__)"
   def run():return subprocess.run([sys.executable,'-I','-B','-c',script,copy,digest],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONPATH=d))
   r=run();self.assertEqual(r.returncode,0,r.stderr);self.assertIn((copy+'/vendor/').encode(),r.stdout)
   for rel in ('cryptography/__init__.py','_cffi_backend.cpython-312-x86_64-linux-gnu.so','cryptography-50.0.2.dist-info/METADATA','cryptography-50.0.2.dist-info/RECORD'):
    path=os.path.join(copy,'vendor',rel);original=open(path,'rb').read()
    with open(path,'wb') as f:f.write(original+b'x')
    self.assertNotEqual(run().returncode,0,rel)
    with open(path,'wb') as f:f.write(original)
   target=os.path.join(copy,'vendor','cryptography','__init__.py');os.rename(target,target+'.bak')
   self.assertNotEqual(run().returncode,0);os.rename(target+'.bak',target)
   extra=os.path.join(copy,'vendor','extra.py');open(extra,'wb').close();self.assertNotEqual(run().returncode,0);os.unlink(extra)
   self.assertEqual(run().returncode,0)
