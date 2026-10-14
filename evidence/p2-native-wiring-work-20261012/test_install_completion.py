import hashlib,json,os,pathlib,sqlite3,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT']);sys.path.insert(0,str(ROOT/'stage1'))
from execution_ledger import ExecutionLedger
from ledger_install_stage import stage_existing_registry,PROOF_KEYS
from ledger_backup import database_manifest
from uk_owner_callback_core import validate_schema
import legacy_host_adapter as legacy

class SchemaMigrationTests(unittest.TestCase):
 def source(self,p,broken=False):
  d=sqlite3.connect(str(p))
  for name,cols in ExecutionLedger.SCHEMAS.items():
   d.execute('CREATE TABLE '+name+'('+','.join(n+' '+t+(' PRIMARY KEY' if pk else '') for n,t,pk in cols)+')')
  d.execute('CREATE TABLE owner_callback_requests(request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,fence INTEGER NOT NULL,owner_id TEXT NOT NULL,owner_chat TEXT NOT NULL,expires_at REAL NOT NULL,consumed INTEGER NOT NULL DEFAULT 0)')
  d.execute("INSERT INTO owner_callback_requests VALUES('expired','old',1,'owner','chat',1,0)")
  d.execute('CREATE TABLE owner_notification_outbox(id TEXT,status TEXT)');d.execute("INSERT INTO owner_notification_outbox VALUES('old','ACKED')")
  if broken:d.execute('CREATE TABLE owner_callback_replays(wrong TEXT)')
  d.commit();d.close()
 def test_real_stage_adds_callback_replay_without_touching_original(self):
  with tempfile.TemporaryDirectory() as t:
   s=pathlib.Path(t,'source.sqlite');self.source(s);before=s.read_bytes();manifest=database_manifest(str(s))
   result=stage_existing_registry(str(s),t+'/backup.sqlite',t+'/generation.sqlite','owner/repo',dict.fromkeys(PROOF_KEYS,True))
   self.assertIn('owner_callback_replays',result['new_tables']);validate_schema(t+'/generation.sqlite')
   after=database_manifest(t+'/generation.sqlite')
   for k,v in manifest['table_sha256'].items():self.assertEqual(after['table_sha256'][k],v)
   self.assertEqual(s.read_bytes(),before)
   ledger=ExecutionLedger(t+'/generation.sqlite',['owner/repo']);self.assertIsNone(ledger.claim('fixture'))
   with self.assertRaises(PermissionError):ledger.owner_decision('old',1,'APPROVE','expired',100,'owner','chat','fixture',True)
 def test_bad_callback_schema_holds_without_source_change(self):
  with tempfile.TemporaryDirectory() as t:
   s=pathlib.Path(t,'source.sqlite');self.source(s,True);before=s.read_bytes()
   with self.assertRaises(Exception):stage_existing_registry(str(s),t+'/backup.sqlite',t+'/generation.sqlite','owner/repo',dict.fromkeys(PROOF_KEYS,True))
   self.assertEqual(s.read_bytes(),before)
 def test_missing_quiescence_has_no_backup_or_generation(self):
  with tempfile.TemporaryDirectory() as t:
   s=pathlib.Path(t,'source.sqlite');self.source(s)
   with self.assertRaises(ValueError):stage_existing_registry(str(s),t+'/backup.sqlite',t+'/generation.sqlite','owner/repo',dict.fromkeys(PROOF_KEYS,False))
   self.assertFalse(os.path.exists(t+'/backup.sqlite'));self.assertFalse(os.path.exists(t+'/generation.sqlite'))

class MaskRollbackTests(unittest.TestCase):
 def invoke(self,t,drift=False,masked=False):
  prefix='/etc/systemd/system/';units={};commands=[]
  real_open=os.open;real_replace=os.replace;real_link=os.path.islink;real_readlink=os.readlink;real_temp=tempfile.mkstemp
  def mapped(p):return t+'/unit-'+p[len(prefix):] if isinstance(p,str) and p.startswith(prefix) else (t if p=='/etc/systemd/system' else p)
  for n in ('xuanjun-uk-openclaw.service','xuanjun-uk-stage1-minimal.service'):
   b=('original '+n).encode();backup=t+'/'+n+'.backup';pathlib.Path(backup).write_bytes(b)
   path=prefix+n;target=mapped(path)
   if masked or 'stage1' in n:os.symlink('/dev/null',target)
   else:pathlib.Path(target).write_bytes(b)
   units[n]={'path':path,'backup':backup,'sha256':hashlib.sha256(b).hexdigest(),'mode':0o644,'uid':0,'gid':0,'was_active':True}
  if drift:
   p=mapped(prefix+'xuanjun-uk-openclaw.service');os.unlink(p);pathlib.Path(p).write_bytes(b'unknown')
  class Adapter(legacy.LegacyHostAdapter):
   def _state(self):return {'schema':1,'units':units,'source_before':{}}
   def _command(self,*a):commands.append(a)
  adapter=Adapter(t)
  def digest(p):return hashlib.sha256(pathlib.Path(mapped(p)).read_bytes()).hexdigest()
  with patch.object(legacy,'protected_hash',side_effect=digest),patch.object(legacy.os,'open',side_effect=lambda p,*a,**k:real_open(mapped(p),*a,**k)),patch.object(legacy.os,'replace',side_effect=lambda a,b:real_replace(a,mapped(b))),patch.object(legacy.os.path,'islink',side_effect=lambda p:real_link(mapped(p))),patch.object(legacy.os,'readlink',side_effect=lambda p:real_readlink(mapped(p))),patch.object(legacy.tempfile,'mkstemp',side_effect=lambda **k:real_temp(prefix=k['prefix'],dir=t)):
   if drift:
    with self.assertRaises(ValueError):adapter.restore_legacy_files(preserve_mask=True)
    self.assertEqual(commands,[]);self.assertEqual(pathlib.Path(mapped(prefix+'xuanjun-uk-openclaw.service')).read_bytes(),b'unknown')
   else:
    self.assertTrue(adapter.restore_legacy_files(preserve_mask=True)['masks_preserved'])
    adapter.restore_legacy_files(preserve_mask=True)
    for n in units:self.assertEqual(real_readlink(mapped(prefix+n)),'/dev/null')
    self.assertEqual(commands,[('daemon-reload',),('daemon-reload',)])
 def test_known_gateway_restored_directly_to_mask(self):
  with tempfile.TemporaryDirectory() as t:self.invoke(t)
 def test_already_masked_is_idempotent(self):
  with tempfile.TemporaryDirectory() as t:self.invoke(t,masked=True)
 def test_unknown_gateway_target_zero_effects(self):
  with tempfile.TemporaryDirectory() as t:self.invoke(t,drift=True)
 def test_contradictory_selection_rejected(self):
  a=legacy.LegacyHostAdapter('/tmp');a._state=lambda:{'schema':1,'units':{},'source_before':{}}
  with self.assertRaises(ValueError):a.restore_legacy_files(gateway_only=True,preserve_mask=True)

if __name__=='__main__':unittest.main(verbosity=2)
