import copy
import importlib.util
import json
import os
from pathlib import Path
import runpy
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
# Emulate the real read-only tool staging. Hosted checkout permissions are not
# the protected deployment input and must not be mistaken for that input.
TOOL=REPO/'production/p2_install/initialize.py'
STAGING=None
if '--crash' not in sys.argv:
 STAGING=tempfile.TemporaryDirectory(prefix='p2-b3-tools-')
 staged=Path(STAGING.name)
 for relative in ('production/p2_install/initialize.py',
                  'evidence/p2-epoch7-access-repair-20261014/runtime/stage1/activation_control.py'):
  dest=staged/relative;dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_bytes((REPO/relative).read_bytes());dest.chmod(0o440)
 TOOL=staged/'production/p2_install/initialize.py'
else:
 TOOL=Path(os.environ['P2_TEST_STAGED_TOOL'])
def load():
 s=importlib.util.spec_from_file_location('init_adapter',str(TOOL));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load()
PYTHON_BIN=sys.executable
CHILD_ENV=dict(os.environ,PYTHONHOME=sys.prefix,
               LD_LIBRARY_PATH=str(Path(sys.prefix)/'lib')+':'+os.environ.get('LD_LIBRARY_PATH',''))
if STAGING is not None:
 # Hosted toolcache permits group writes. Preserve the production protection
 # check by executing the identical bytes from a private nonwritable copy.
 executable=Path(STAGING.name)/'python'
 executable.write_bytes(Path(os.path.realpath(sys.executable)).read_bytes())
 executable.chmod(0o500)
 PYTHON_BIN=str(executable)
CHILD_ENV['P2_TEST_STAGED_TOOL']=str(TOOL)

def snapshot(root):
 return {str(p.relative_to(root)):(m.sha(p.read_bytes()),m.stamp(p.stat())) for p in root.rglob('*') if p.is_file()}

class InitializationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='p2-b3-test-',dir='/tmp');self.base=Path(self.temp.name)
  os.umask(0o077)
  self.root=self.base/'b3-initialize';self.root.mkdir(mode=0o700)
  source=self.base/'sources';source.mkdir(mode=0o700)
  b1=runpy.run_path(str(REPO/'scripts/p2_b1_owner_first_install_20261020.py'),run_name='metadata_only')
  _,files,_,req=b1['validate_payload']();(source/'MANIFEST.json').write_bytes(files['MANIFEST.json'])
  journal={'schema':1,'request_digest':m.sha(m.encode(req)),'attempt_id':req['attempt_id'],
   'files':req['inputs']['files'],'modes':req['inputs']['modes'],'archive_sha256':req['inputs']['archive_sha256']}
  receipt={'schema':1,'journal_sha256':m.sha(m.encode(journal)),
   'version':req['root']+'/versions/'+req['installation_id']+'--'+req['batch_id'],
   'files':req['inputs']['files'],'modes':req['inputs']['modes'],'recovery':None}
  (source/'b1-receipt.json').write_bytes(m.encode(receipt))
  cfg=json.loads((REPO/'docs/p2-b3-initialize-20261020/binding-config.json').read_bytes())
  cfg.update(db_path=str(self.root/'data/ledger.sqlite3'),ledger_socket=str(self.root/'run/ledger.sock'))
  binary=Path(os.path.realpath(PYTHON_BIN));raw=binary.read_bytes()
  self.req={'schema':1,'scope':'ISOLATED_TEST_ONLY','origin':'ISOLATED_NEW',
   'installation_id':cfg['installation_id'],'batch_id':cfg['batch_id'],'attempt_id':cfg['attempt_id'],
   'root':str(self.root),'source_root':str(source),'config':cfg,'config_sha256':m.sha(m.encode(cfg)),
   'binary':{'path':str(binary),'bytes':len(raw),'sha256':m.sha(raw)}}
  self.req['descriptor']={'schema':1,'state':'PREPARED','epoch':1,'release_sha256':m.MANIFEST_SHA,
   'config_sha256':self.req['config_sha256'],'binary_sha256':m.sha(raw),
   'ledger_uuid':cfg['ledger_uuid'],'generation':1,'instance':cfg['instance'],
   'db_path':cfg['db_path'],'ledger_socket':cfg['ledger_socket']}
 def tearDown(self):self.temp.cleanup()
 def call(self,action='execute',req=None):
  req=req or self.req
  p=subprocess.run([PYTHON_BIN,'-B','-S',str(TOOL),action,'--request-sha256',m.sha(m.encode(req))],
   input=m.encode(req),capture_output=True,timeout=15,env=CHILD_ENV)
  self.assertEqual(p.stderr,b'');return json.loads(p.stdout)
 def crash(self,point):
  p=subprocess.run([PYTHON_BIN,'-B',__file__,'--crash',point],input=m.encode(self.req),timeout=15,env=CHILD_ENV)
  self.assertEqual(p.returncode,-signal.SIGKILL)
 def test_three_processes_and_duplicate_preserve_original(self):
  first=self.call();self.assertEqual(first['status'],'COMMITTED');before=snapshot(self.root)
  for action in ('inspect','recover','execute'):
   result=self.call(action);self.assertEqual(result,first);self.assertEqual(snapshot(self.root),before)
  self.assertEqual(len((self.root/'activation/epochs.jsonl').read_bytes().splitlines()),1)
 def test_intent_interruption_recovers_in_new_process(self):
  self.crash('after_intent');self.assertEqual(self.call('execute')['status'],'HOLD')
  self.assertEqual(self.call('recover')['status'],'COMMITTED')
 def test_config_interruption_recovers_in_new_process(self):
  self.crash('after_config');self.assertEqual(self.call('inspect')['status'],'HOLD')
  self.assertEqual(self.call('recover')['status'],'COMMITTED')
 def test_original_store_append_before_descriptor_sigkill(self):
  self.crash('append_before_descriptor');journal=self.root/'activation/epochs.jsonl';raw=journal.read_bytes()
  self.assertFalse((self.root/'activation/active.json').exists());self.assertEqual(self.call('inspect')['status'],'HOLD')
  self.assertEqual(self.call('recover')['status'],'COMMITTED');self.assertEqual(journal.read_bytes(),raw)
 def test_descriptor_before_receipt_interruption(self):
  self.crash('before_receipt');before=(self.root/'activation/epochs.jsonl').read_bytes()
  self.assertEqual(self.call('recover')['status'],'COMMITTED');self.assertEqual((self.root/'activation/epochs.jsonl').read_bytes(),before)
 def test_identity_conflict_keeps_state(self):
  self.assertEqual(self.call()['status'],'COMMITTED');before=snapshot(self.root)
  req=copy.deepcopy(self.req);req['config']['instance']='33333333-3333-3333-3333-333333333333'
  req['config_sha256']=m.sha(m.encode(req['config']));req['descriptor'].update(instance=req['config']['instance'],config_sha256=req['config_sha256'])
  self.assertEqual(self.call('recover',req)['status'],'HOLD');self.assertEqual(snapshot(self.root),before)
 def test_binary_missing_is_hold_before_effect(self):
  req=copy.deepcopy(self.req);req['binary']['sha256']=None
  self.assertEqual(self.call(req=req)['status'],'HOLD');self.assertEqual(list(self.root.iterdir()),[])
 def test_wrong_binary_rejected_before_effect(self):
  req=copy.deepcopy(self.req);req['binary']['sha256']='0'*64
  self.assertEqual(self.call(req=req)['status'],'HOLD');self.assertEqual(list(self.root.iterdir()),[])
 def test_config_digest_conflict(self):
  self.assertEqual(self.call()['status'],'COMMITTED');before=snapshot(self.root)
  req=copy.deepcopy(self.req);req['config_sha256']='0'*64
  self.assertEqual(self.call('recover',req)['status'],'HOLD');self.assertEqual(snapshot(self.root),before)
 def test_corrupt_journal_never_reappends(self):
  self.crash('append_before_descriptor');p=self.root/'activation/epochs.jsonl';p.write_bytes(p.read_bytes()+b'{broken\n');before=p.read_bytes()
  self.assertEqual(self.call('recover')['status'],'HOLD');self.assertEqual(p.read_bytes(),before)
 def test_foreign_descriptor_not_overwritten(self):
  self.crash('before_receipt');p=self.root/'activation/active.json';v=json.loads(p.read_bytes());v['epoch']=2;p.write_bytes(m.encode(v)+b'\n');before=p.read_bytes()
  self.assertEqual(self.call('recover')['status'],'HOLD');self.assertEqual(p.read_bytes(),before)
 def test_no_intent_does_not_adopt_existing_activation(self):
  (self.root/'activation').mkdir(mode=0o700)
  self.assertEqual(self.call('recover')['status'],'HOLD');self.assertFalse((self.root/'intent.json').exists())
 def test_existing_database_not_touched_or_adopted(self):
  (self.root/'data').mkdir();p=self.root/'data/ledger.sqlite3';p.write_bytes(b'not ours')
  self.assertEqual(self.call()['status'],'HOLD');self.assertEqual(p.read_bytes(),b'not ours');self.assertFalse((self.root/'intent.json').exists())
 def test_receipt_tamper_holds_without_overwrite(self):
  self.assertEqual(self.call()['status'],'COMMITTED');p=self.root/'commit-receipt.json';p.chmod(0o600);p.write_bytes(b'tampered');p.chmod(0o400);before=snapshot(self.root)
  self.assertEqual(self.call('recover')['status'],'HOLD');self.assertEqual(snapshot(self.root),before)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--crash':
  req=json.loads(sys.stdin.buffer.read());point=sys.argv[2]
  if point=='append_before_descriptor':
   original=m.store_module
   def patched():
    mod=original()
    def stop(self,value):os.kill(os.getpid(),signal.SIGKILL)
    mod.ActivationStore._write_descriptor=stop
    return mod
   m.store_module=patched
  else:
   def check(name):
    if name==point:os.kill(os.getpid(),signal.SIGKILL)
   m._checkpoint=check
  print(json.dumps(m.dispatch(req,'execute',m.sha(m.encode(req)))));sys.exit(3)
 unittest.main()
