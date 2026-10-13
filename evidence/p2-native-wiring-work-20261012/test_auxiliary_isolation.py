import os,sys,pathlib,json,hashlib,tempfile,types,unittest
from unittest.mock import patch
sys.path.insert(0,os.environ['P2_SOURCE_ROOT']+'/stage1')
import p2_auxiliary_isolation as a
import p2_fixed_host_runtime as runtime
class AuxiliaryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.old=(a.BASE,a.UNIT_ROOT,a.CGROUP_ROOT)
  a.BASE=str(self.root);a.UNIT_ROOT=str(self.root/'units');a.CGROUP_ROOT=str(self.root/'cgroups')
  (self.root/'units').mkdir();(self.root/'cgroups').mkdir();self.tx='c529c379-9341-4510-8384-fc6be1e412e5'
  self.parent=self.root/('legacy-isolation-'+self.tx)/'auxiliary-owner';self.parent.mkdir(parents=True,mode=0o700)
  self.hashes={}
  for unit in a.UNITS:
   (self.root/'units'/unit).symlink_to('/dev/null');p=self.parent/(unit+'.backup');p.write_bytes(b'[Service]\nUser=xuanjun_dev\n');p.chmod(0o600);self.hashes[unit]=hashlib.sha256(p.read_bytes()).hexdigest()
  v={'state':'AUTHORIZED_AUXILIARY_OWNER_ISOLATED','transaction_id':self.tx,'install':False,'writer_admission':False,'fence_mutation':False,'database_unchanged':True,'original_stage1_gateway_journal_unchanged':True,'unit_hashes':self.hashes}
  self.path=self.parent/'auxiliary-isolation-receipt.json';raw=(json.dumps(v,sort_keys=True)+'\n').encode();self.path.write_bytes(raw);self.path.chmod(0o600)
  self.ref={'path':str(self.path),'sha256':hashlib.sha256(raw).hexdigest(),'transaction_id':self.tx}
  self.run=lambda *args,**kw:types.SimpleNamespace(returncode=0,stdout=b'ActiveState=inactive\nSubState=dead\nMainPID=0\nUnitFileState=masked\n')
  self.target=str(self.root/'units'/sorted(a.UNITS)[0])
 def tearDown(self):a.BASE,a.UNIT_ROOT,a.CGROUP_ROOT=self.old;self.tmp.cleanup()
 def test_valid_receipt_and_exact_masks(self):self.assertEqual(set(a.verify(self.ref,run=self.run)['unit_hashes']),a.UNITS)
 def test_missing_reference_holds(self):
  with self.assertRaisesRegex(ValueError,'EXACT_AUX'):a.verify(None,run=self.run)
 def test_transaction_mismatch_holds(self):
  x=dict(self.ref,transaction_id='different')
  with self.assertRaisesRegex(ValueError,'TRANSACTION_SCOPE'):a.verify(x,run=self.run)
 def test_tampered_receipt_holds(self):
  self.path.write_text('{}')
  with self.assertRaisesRegex(ValueError,'REFERENCE_CHANGED'):a.verify(self.ref,run=self.run)
 def test_tampered_original_backup_holds(self):
  p=self.parent/(sorted(a.UNITS)[0]+'.backup');p.write_text('tamper')
  with self.assertRaisesRegex(ValueError,'REFERENCE_CHANGED'):a.verify(self.ref,run=self.run)
 def test_live_old_service_holds(self):
  run=lambda *x,**kw:types.SimpleNamespace(returncode=0,stdout=b'ActiveState=active\nMainPID=42\nUnitFileState=masked\n')
  with self.assertRaisesRegex(ValueError,'NOT_QUIESCED'):a.verify(self.ref,run=run)
 def test_unmasked_target_holds(self):
  p=pathlib.Path(self.target);p.unlink();p.write_text('new')
  with self.assertRaisesRegex(ValueError,'MASK_CHANGED'):a.verify(self.ref,run=self.run)
 def test_surviving_descendant_holds(self):
  d=self.root/'cgroups'/sorted(a.UNITS)[0]/'nested';d.mkdir(parents=True);(d/'cgroup.procs').write_text('123\n')
  with self.assertRaisesRegex(ValueError,'CGROUP_NOT_EMPTY'):a.verify(self.ref,run=self.run)
 def test_duplicate_backup_never_overwrites(self):
  p=self.root/'snapshot';previous=a.mask_previous(self.ref,self.target,str(p),run=self.run);before=p.read_bytes()
  with self.assertRaises(FileExistsError):a.mask_previous(self.ref,self.target,str(p),run=self.run)
  self.assertEqual(p.read_bytes(),before);self.assertTrue(previous['masked'])
 def test_mask_restore_atomic_and_repeat_noop(self):
  p=pathlib.Path(self.target);p.unlink();p.write_text('new reviewed runtime')
  original=self.path.read_bytes();a.restore_mask(self.target);a.restore_mask(self.target)
  self.assertTrue(a.is_mask(self.target));self.assertEqual(self.path.read_bytes(),original)
 def test_unknown_restore_symlink_rejected(self):
  p=pathlib.Path(self.target);p.unlink();p.symlink_to('/tmp/unknown')
  with self.assertRaisesRegex(ValueError,'UNKNOWN_SYMLINK'):a.restore_mask(self.target)
 def test_restore_cannot_target_other_unit(self):
  with self.assertRaisesRegex(ValueError,'TARGET_SCOPE'):a.restore_mask(a.UNIT_ROOT+'/unapproved.service')
 def test_restore_verification_requires_services_stopped(self):
  p=pathlib.Path(self.target);p.unlink();p.write_text('new unit')
  a.verify(self.ref,masked=False,run=self.run)
 def test_binding_mask_requires_verified_explicit_reference(self):
  b={'source':'deploy/test.service','target':self.target,'source_sha256':'a'*64,'rendered_sha256':'b'*64,'mode':0o644,'owner_uid':0,'group_gid':0,'replacements':{}}
  with patch.object(runtime,'ALLOWED_TARGET_PREFIXES',(a.UNIT_ROOT+'/',)):
   with self.assertRaisesRegex(ValueError,'INVALID_PROVISIONING'):runtime.FixedHostRuntime._binding(b,'/tmp/release')
   original=a.verify
   with patch.object(a,'verify',side_effect=lambda ref:original(ref,run=self.run)):
    self.assertEqual(runtime.FixedHostRuntime._binding(b,'/tmp/release',self.ref)[1],self.target)
if __name__=='__main__':unittest.main()
