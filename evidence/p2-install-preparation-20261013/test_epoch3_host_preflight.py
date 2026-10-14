import hashlib,json,os,pathlib,sys,types,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(os.environ['P2_NEW_ROOT'])/'stage1'))
import epoch3_host_preflight as subject
import activation_control,ledger_backup,legacy_host_adapter,p2_prerequisites,p2_auxiliary_isolation

class Tests(unittest.TestCase):
 def setUp(self):
  self.plan={'artifact':{'root':subject.C+'/xuanjun-p2-package','manifest':'manifest'},
   'runtime':{'prerequisites':{},'release_directory':'old','auxiliary_isolation':{}},
   'cutover':{'legacy_isolation':{'legacy_state_sha256':'legacyhash','receipt_sha256':'ownerhash',
    'original_plan_path':'oldplan','original_plan_sha256':'oldplanhash'},'legacy_bindings':{},
    'source':'source','rollback_snapshot':'backup','staged_generation':'generation'}}
  self.raw=json.dumps(self.plan).encode();self.active={'epoch':3,'state':'PREPARED'}
  self.cutover={'stage':'STAGED','source_replaced':False,'activation_executed':False,'task_replay':False,
                'migration':{'rollback':'backup-manifest','generation':'generation-manifest'}}
  self.scanner=mock.Mock();self.scanner.MANIFEST_SHA=hashlib.sha256(b'{"files":{}}').hexdigest()
  self.scanner.RETAINED_CACHE_HASHES={};self.scanner.RUNNER='runner';self.scanner.scheduler_exclusion.return_value='schedulerhash'
  self.scanner.verify_prerequisites.return_value='prereq';self.scanner.validate_retained_caches.return_value={}
  self.scanner.database_file_set.side_effect=lambda path,*a,**kw:({'database_sha256':path},path.encode())
  self.scanner.manifest_from_copy.side_effect=lambda data,*a:data.decode()+'-manifest'
  self.info=types.SimpleNamespace(st_gid=0,st_mode=0o100644)
  def read(path,**kw):
   if path=='manifest' or path.endswith('/INTEGRATION_MANIFEST.json'):return b'{"files":{}}',self.info
   if path.endswith('ledger-cutover.json'):return json.dumps(self.cutover).encode(),self.info
   if path.endswith('legacy-units.json'):return b'legacy',self.info
   if path.endswith('owner-isolation-receipt.json'):return b'owner',self.info
   if path=='oldplan':return b'oldplan',self.info
   return b'journal',self.info
  self.scanner.read.side_effect=read
  ref=self.plan['cutover']['legacy_isolation']
  for key,data in [('legacy_state_sha256',b'legacy'),('receipt_sha256',b'owner'),('original_plan_sha256',b'oldplan')]:ref[key]=hashlib.sha256(data).hexdigest()
  self.raw=json.dumps(self.plan).encode()
  self.store=mock.Mock();self.store.read.return_value=self.active
  self.store._journal.return_value=[({'descriptor':self.active},None)]
  self.store.lock_path='lock';self.store.epoch_journal='journal'
  self.proof={k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')}
  self.adapter=mock.Mock();self.adapter.measure_quiescence.return_value={'proof':self.proof}
  self.containment=mock.Mock();self.containment.verify_all.return_value={'verified_stopped':True}
  self.patches=[mock.patch.object(subject.os,'geteuid',return_value=0),
   mock.patch.object(subject.socket,'gethostname',return_value=subject.HOST),
   mock.patch.object(subject,'file_data',return_value=(self.raw,self.info)),
   mock.patch.object(subject,'PINS',{subject.C+'/protected-core-install-plan.json':hashlib.sha256(self.raw).hexdigest()}),
   mock.patch.object(subject,'capture_retained',return_value={'evidence':{},'native_binding_before':b'private'}),
   mock.patch.object(subject.os.path,'lexists',return_value=False),
   mock.patch.object(subject.os.path,'islink',return_value=True),
   mock.patch.object(subject.os,'readlink',return_value='/dev/null'),
   mock.patch.object(subject.os.path,'isfile',return_value=True),
   mock.patch.object(subject,'ServiceContainment',return_value=self.containment),
   mock.patch.object(subject.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=b'MainPID=0\nActiveState=inactive\nConditionResult=no\n')),
   mock.patch.object(activation_control,'ActivationStore',return_value=self.store),
   mock.patch.object(legacy_host_adapter,'LegacyHostAdapter',return_value=self.adapter),
   mock.patch.object(p2_prerequisites,'Prerequisites'),mock.patch.object(p2_auxiliary_isolation,'verify')]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def execute(self):return subject.capture_host('a'*64,self.scanner)
 def test_complete_readonly_composition(self):
  evidence,private=self.execute();self.assertEqual(evidence['effects'],0)
  self.assertEqual(evidence['install_admission'],'NOT_GRANTED')
  self.assertNotIn('native_binding_before',json.dumps(evidence));self.assertIn('retained',private)
  self.scanner.fd_exclusion.assert_called();self.scanner.scheduler_exclusion.assert_called_once()
 def test_wrong_host(self):
  with mock.patch.object(subject.socket,'gethostname',return_value='other'):
   with self.assertRaises(ValueError):self.execute()
 def test_prior_effect_rejected(self):
  with mock.patch.object(subject.os.path,'lexists',return_value=True):
   with self.assertRaisesRegex(ValueError,'LATER_EFFECT'):self.execute()
 def test_activation_epoch_changed(self):
  self.active['epoch']=4
  with self.assertRaisesRegex(ValueError,'ACTIVATION_STATE'):self.execute()
 def test_journal_mismatch(self):
  self.store._journal.return_value=[]
  with self.assertRaisesRegex(ValueError,'JOURNAL_HEAD'):self.execute()
 def test_process_exclusion_failure(self):
  self.containment.verify_all.side_effect=ValueError('busy')
  with self.assertRaises(ValueError):self.execute()
 def test_legacy_busy(self):
  self.proof['cgroups_empty']=False
  with self.assertRaisesRegex(ValueError,'QUIESCENCE'):self.execute()
 def test_source_already_replaced(self):
  self.cutover['source_replaced']=True
  with self.assertRaisesRegex(ValueError,'CUTOVER_EFFECTS'):self.execute()
 def test_scheduler_denied(self):
  self.scanner.scheduler_exclusion.side_effect=PermissionError('denied')
  with self.assertRaises(PermissionError):self.execute()
 def test_database_changed(self):
  original=self.scanner.database_file_set.side_effect;count=[0]
  def change(path,*a,**kw):
   count[0]+=1
   return original(path,*a,**kw) if count[0]<=3 else ({'database_sha256':'changed'},b'')
  self.scanner.database_file_set.side_effect=change
  with self.assertRaisesRegex(ValueError,'DATABASE_RACE'):self.execute()
 def test_runner_guard_missing(self):
  with mock.patch.object(subject.os.path,'isfile',return_value=False):
   with self.assertRaisesRegex(ValueError,'RUNNER_ISOLATION'):self.execute()
 def test_old_package_drift(self):
  self.scanner.validate_release.side_effect=ValueError('hash changed')
  with self.assertRaises(ValueError):self.execute()
if __name__=='__main__':unittest.main()
