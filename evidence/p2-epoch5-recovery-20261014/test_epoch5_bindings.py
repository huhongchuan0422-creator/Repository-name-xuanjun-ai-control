import hashlib,json,os,pathlib,shutil,tempfile,unittest
import prepare_epoch5_bindings as subject
class BindingsTests(unittest.TestCase):
 def setUp(self):
  self.old=pathlib.Path(os.environ['P2_ORIGINAL_ROOT']);self.new=pathlib.Path(os.environ['P2_NEW_ROOT'])
  self.plan=pathlib.Path(os.environ['P2_PLAN_PATH']).read_bytes()
 def run_proposal(self,new=None,plan=None):return subject.proposal(plan or self.plan,str(self.old),str(new or self.new))
 def test_all_24_bindings(self):
  report,private=self.run_proposal()
  self.assertEqual(len(report['target_bindings']),24)
  self.assertEqual(sum(r['changed'] for r in report['target_bindings']),12)
  self.assertEqual(sum(r['original_source_hash_kind']=='ORIGINAL_RAW_HASH_KNOWN_INSTALL_BUG' for r in report['target_bindings']),7)
 def test_public_report_omits_replacement_values(self):
  report,private=self.run_proposal();data=json.dumps(report)
  self.assertNotIn('oc_b2695',data);self.assertNotIn('cli_aa405',data)
  self.assertNotIn('replacements',data)
 def test_preserves_canonical_identity(self):
  report,private=self.run_proposal();old=json.loads(self.plan.decode())['activation'];new=private['activation_proposal']
  for key in ('db_path','generation','instance','ledger_uuid','ledger_socket','binary_sha256'):self.assertEqual(old[key],new[key])
  self.assertEqual(new['epoch'],6);self.assertEqual(new['state'],'PREPARED')
  self.assertEqual(report['install_admission'],'NOT_GRANTED')
 def test_new_config_hash_exact(self):
  report,private=self.run_proposal();data=private['rendered_targets']['/etc/xuanjun-development/dispatcher.json']
  self.assertEqual(hashlib.sha256(data).hexdigest(),report['dispatcher_config_sha256'])
  self.assertNotIn(subject.OLD_MANIFEST.encode(),data)
 def test_changed_plan_rejected(self):
  with self.assertRaisesRegex(ValueError,'ORIGINAL_PLAN_CHANGED'):self.run_proposal(plan=self.plan+b' ')
 def test_unrelated_delta_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d)/'root';shutil.copytree(str(self.new),str(r))
   path=r/'deploy/integration-manifest.json';path.chmod(0o600);m=json.loads(path.read_text());m['source_parent']='0'*40;path.write_text(json.dumps(m))
   with self.assertRaisesRegex(ValueError,'UNREVIEWED_MANIFEST_DELTA'):self.run_proposal(new=r)
 def test_actual_file_drift_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d)/'root';shutil.copytree(str(self.new),str(r))
   path=r/'stage1/p2_tls_lifecycle.py';path.chmod(0o600);path.write_text('#wrong')
   with self.assertRaisesRegex(ValueError,'SOURCE_FILE_CHANGED'):self.run_proposal(new=r)
class NativeBindingTests(unittest.TestCase):
 def setUp(self):
  from unittest.mock import patch
  self.bridge='/opt/xuanjun-control-releases/integration-'+subject.OLD_MANIFEST[:16]+'/stage1/native_ledger_bridge.py'
  self.config='/etc/xuanjun-development/p2-native-ledger-client.json'
  value={'ledger':{'python':'/usr/bin/python3','pythonSha256':'a'*64,'bridge':self.bridge,'config':self.config,'files':{self.bridge:'b'*64,self.config:'c'*64}},'gatewayIdentity':{'fixture':True}}
  self.raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
  self.patch=patch.object(subject,'NATIVE_BINDING_SHA',hashlib.sha256(self.raw).hexdigest());self.patch.start()
 def tearDown(self):self.patch.stop()
 def test_only_bridge_paths_change(self):
  old=json.loads(self.raw.decode());new=json.loads(subject.native_binding_delta(self.raw,'d'*64).decode())
  self.assertEqual(old['gatewayIdentity'],new['gatewayIdentity'])
  self.assertEqual(old['ledger']['files'][self.bridge],new['ledger']['files'][new['ledger']['bridge']])
  self.assertEqual(old['ledger']['files'][self.config],new['ledger']['files'][self.config])
  self.assertNotIn(self.bridge,new['ledger']['files'])
 def test_old_bytes_mismatch_rejected(self):
  with self.assertRaisesRegex(ValueError,'OLD_NATIVE_BINDING_CHANGED'):subject.native_binding_delta(self.raw+b' ', 'd'*64)
 def test_new_hash_invalid_rejected(self):
  with self.assertRaisesRegex(ValueError,'NEW_MANIFEST_HASH'):subject.native_binding_delta(self.raw,'../bad')
 def test_old_release_cannot_be_reused(self):
  with self.assertRaisesRegex(ValueError,'STALE_NATIVE_RELEASE'):subject.native_binding_delta(self.raw,subject.OLD_MANIFEST)

if __name__=='__main__':unittest.main()
