import copy,hashlib,json,os,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT']);sys.path.insert(0,str(ROOT/'stage1'))
import p2_legacy_adoption as adoption
from legacy_host_adapter import LegacyHostAdapter
class AdoptionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.tmp.name);self.oldbase=adoption.BASE;self.oldunits=adoption.UNIT_ROOT
  adoption.BASE=str(self.base);adoption.UNIT_ROOT=str(self.base/'units');(self.base/'units').mkdir()
  self.tx='c529c379-9341-4510-8384-fc6be1e412e5';self.d=self.base/('legacy-isolation-'+self.tx);self.d.mkdir(mode=0o700)
  self.source=self.base/'old.sqlite';self.source.write_bytes(b'synthetic stable old db');os.chown(str(self.source),1002,1002)
  bindings={};states={}
  for unit in ('xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service'):
   p=self.base/'units'/unit;p.symlink_to('/dev/null');backup=self.d/(unit+'.backup');backup.write_bytes(b'[Service]\nUser=xuanjun_dev\n');backup.chmod(0o600);h=hashlib.sha256(backup.read_bytes()).hexdigest()
   bindings[unit]={'fragment_path':str(p),'sha256':h,'cgroup':'/system.slice/'+unit}
   states[unit]={'path':str(p),'backup':str(backup),'sha256':h,'mode':0o644,'uid':0,'gid':0,'was_active':True}
  self.plan={'schema':1,'transaction_id':self.tx,'source':str(self.source),'rollback_snapshot':'/var/lib/xuanjun-development/backups/'+self.tx+'.sqlite','staged_generation':'/var/lib/xuanjun-development/generations/adoption-test/state.sqlite','repository':'huhongchuan0422-creator/Repository-name-xuanjun-ai-control','legacy_bindings':bindings}
  pdir=self.base/'plan-p2pkg-1-1';pdir.mkdir(mode=0o700);original=pdir/'core.json';osh=self.write(original,{'transaction_id':self.tx,'cutover':copy.deepcopy(self.plan)})
  lsh=self.write(self.d/'legacy-units.json',{'schema':1,'units':states,'source_before':{'original':'preserved'}})
  rsh=self.write(self.d/'owner-isolation-receipt.json',{'state':'AUTHORIZED_OLD_SERVICES_ISOLATED','transaction_id':self.tx,'core_plan_sha256':osh,'install':False,'fence_mutation':False,'writer_admission':False})
  self.plan['legacy_isolation']={'directory':str(self.d),'original_plan_path':str(original),'original_plan_sha256':osh,'receipt_sha256':rsh,'legacy_state_sha256':lsh,'database_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}
  self.a=LegacyHostAdapter(str(self.d));self.a._authority=lambda:None;self.a.measure_quiescence=lambda b:{'proof':dict.fromkeys(adoption.PROOF,True)}
  self.a._command=lambda *a:(_ for _ in ()).throw(AssertionError('REPEATED_SYSTEMD_EFFECT'))
  self.before={str(p):p.read_bytes() for p in self.d.iterdir()}
 def write(self,p,v):
  raw=(json.dumps(v,sort_keys=True)+'\n').encode();p.write_bytes(raw);p.chmod(0o600);return hashlib.sha256(raw).hexdigest()
 def tearDown(self):
  adoption.BASE=self.oldbase;adoption.UNIT_ROOT=self.oldunits;self.tmp.cleanup()
 def test_explicit_adoption_and_duplicate_stop_have_zero_effects(self):
  self.assertTrue(self.a.preflight(self.plan));self.a.stop_and_inhibit(self.plan['legacy_bindings']);self.a.stop_and_inhibit(self.plan['legacy_bindings'])
  self.assertEqual(self.before,{str(p):p.read_bytes() for p in self.d.iterdir()})
 def test_no_reference_retains_existing_journal_hold(self):
  p=copy.deepcopy(self.plan);del p['legacy_isolation']
  # Direct adoption API never infers approval from a discovered journal.
  with self.assertRaisesRegex(ValueError,'EXACT_ISOLATION'):adoption.bind(self.a,p)
 def test_wrong_transaction_rejected(self):
  p=copy.deepcopy(self.plan);p['transaction_id']='different'
  with self.assertRaisesRegex(ValueError,'TRANSACTION_DIRECTORY'):self.a.preflight(p)
 def test_changed_backup_rejected(self):
  p=next(self.d.glob('*.backup'));p.write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'REFERENCE_CHANGED'):self.a.preflight(self.plan)
 def test_changed_original_journal_rejected(self):
  (self.d/'legacy-units.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'REFERENCE_CHANGED'):self.a.preflight(self.plan)
 def test_changed_database_rejected(self):
  self.source.write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'DATABASE_CHANGED'):self.a.preflight(self.plan)
 def test_unmasked_unit_rejected_without_stop(self):
  p=next((self.base/'units').iterdir());p.unlink();p.write_text('changed')
  with self.assertRaisesRegex(ValueError,'MASK_CHANGED'):self.a.preflight(self.plan)
 def test_failed_live_proof_restores_adapter_scope(self):
  previous=(self.a.directory,self.a.state_path);self.a.measure_quiescence=lambda b:{'proof':dict.fromkeys(adoption.PROOF,False)}
  with self.assertRaisesRegex(ValueError,'QUIESCENCE_FAILED'):self.a.preflight(self.plan)
  self.assertEqual(previous,(self.a.directory,self.a.state_path))
 def test_nonempty_wal_holds(self):
  pathlib.Path(str(self.source)+'-wal').write_bytes(b'wal')
  with self.assertRaisesRegex(ValueError,'NONEMPTY_WAL'):self.a.preflight(self.plan)
 def test_backup_symlink_holds(self):
  p=next(self.d.glob('*.backup'));raw=p.read_bytes();p.unlink();other=self.base/'elsewhere';other.write_bytes(raw);other.chmod(0o600);p.symlink_to(other)
  with self.assertRaisesRegex(ValueError,'SYMLINK'):self.a.preflight(self.plan)
if __name__=='__main__':unittest.main()
