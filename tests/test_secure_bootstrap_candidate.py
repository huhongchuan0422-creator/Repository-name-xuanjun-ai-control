import base64, hashlib, importlib.util, io, json, os, sqlite3, sys, tarfile, tempfile, time, unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","bootstrap"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
spec=importlib.util.spec_from_file_location('bootstrap_candidate',os.path.join(os.path.dirname(__file__),'..','bootstrap','secure_bootstrap.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class BootstrapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.getcwd());self.dir=self.tmp.name;self.fds=[]
  self.sqlite_version=sqlite3.sqlite_version_info;sqlite3.sqlite_version_info=(3,53,1)
  self.key=Ed25519PrivateKey.generate(); pub=self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
  self.trust={'mode':'ED25519','environment':'TEST_ONLY','controller':'fixture','public_key':base64.b64encode(pub).decode()}
  z=io.BytesIO()
  with tarfile.open(fileobj=z,mode='w') as t:
   m=tarfile.TarInfo('payload');m.size=3;t.addfile(m,io.BytesIO(b'abc'))
  self.carrier=z.getvalue();self.manifest=b.canonical({'members':{'payload':{'type':'file','size':3,'sha256':b.sha(b'abc')}},'tool_scope':{},'minimum_sqlite':[3,35,0]})
  self.payload={'carrier_sha256':b.sha(self.carrier),'manifest_sha256':b.sha(self.manifest),'task':'task','attempt':'attempt','nonce':'nonce','expiry':int(time.time())+1000,'controller':'fixture','tool_scope':{'mode':'READ_ONLY','tools':{}}}
  self.ledger=os.path.join(self.dir,'ledger');db=sqlite3.connect(self.ledger);db.execute('pragma journal_mode=wal');db.execute('create table operations(nonce text primary key,task text,attempt text,state text,prestate_target text,prestate_hash text,staging_target text,manifest_hash text,intended_target text,receipt_hash text)');db.close();os.chmod(self.ledger,0o600)
  self.log=os.path.join(self.dir,'log');open(self.log,'wb').close();os.chmod(self.log,0o600)
 def tearDown(self):
  for fd in self.fds:os.close(fd)
  sqlite3.sqlite_version_info=self.sqlite_version;self.tmp.cleanup()
 def fd(self,name,data):
  p=os.path.join(self.dir,name);open(p,'wb').write(data);os.chmod(p,0o600);fd=os.open(p,os.O_RDONLY);self.fds.append(fd);return fd
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
  with open(os.path.join(self.root,'base','.bootstrap-manifest.json'),'wb') as f:f.write(b'base')
  os.chmod(os.path.join(self.root,'base','.bootstrap-manifest.json'),0o600);os.symlink('base',os.path.join(self.root,'current'))
 def run_install(self,failpoint=None):
  import sys
  sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'))
  import controller
  p=self.payload;sig=base64.b64encode(self.key.sign(b.canonical(p))).decode()
  args=[self.fd('carrier',self.carrier),self.fd('manifest',self.manifest),self.fd('receipt',b.canonical({'payload':p,'signature':sig})),self.fd('trust',b.canonical(self.trust)),self.ledger]
  lf=os.open(self.log,os.O_WRONLY|os.O_APPEND);self.fds.append(lf)
  return controller.run(*(args+[lf,{'task':p['task'],'attempt':p['attempt']},self.root]),owner=os.getuid(),failpoint=failpoint)
 def state(self):
  with sqlite3.connect(self.ledger) as db:return db.execute('select state from operations').fetchone()[0]
 def test_install_and_reinstall(self):
  self.assertEqual(self.run_install(),'release-nonce');self.assertEqual(os.readlink(os.path.join(self.root,'current')),'release-nonce');self.assertEqual(self.state(),'SUCCEEDED')
  with self.assertRaises(Exception):self.run_install()
 def test_failure_windows_unknown(self):
  import sys
  sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'));import controller
  with self.assertRaises(controller.ControllerError):self.run_install('after_switch')
  self.assertEqual(self.state(),'UNKNOWN')
  with self.assertRaises(Exception):self.run_install()
 def test_next_start_auto_reconciles_before_new_reservation(self):
  with self.assertRaises(Exception):self.run_install('after_extract')
  self.assertEqual(self.state(),'UNKNOWN')
  self.payload=dict(self.payload,nonce='next',attempt='next-attempt')
  self.assertEqual(self.run_install(),'release-next')
  with sqlite3.connect(self.ledger) as db:
   self.assertEqual(db.execute("select state from operations where nonce='nonce'").fetchone()[0],'FAILED')
 def test_ambiguous_switch_blocks_next_install(self):
  with self.assertRaises(Exception):self.run_install('after_switch')
  self.payload=dict(self.payload,nonce='next',attempt='next-attempt')
  with self.assertRaisesRegex(Exception,'UNKNOWN_RECONCILIATION_REQUIRED'):self.run_install()
  self.assertEqual(self.state(),'UNKNOWN')
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
