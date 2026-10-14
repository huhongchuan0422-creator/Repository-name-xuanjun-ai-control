import copy,os,pathlib,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(os.environ['P2_NEW_ROOT'])/'stage1'))
from activation_control import ActivationStore,ActivationError
import epoch5_activation_rebind as subject

class RebindTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();root=self.temp.name
  self.store=ActivationStore(root+'/active.json',root+'/epochs.jsonl',root+'/activation.lock',owner_uid=os.getuid())
  self.store.prepare('a'*64,'b'*64,'c'*64,'12345678-1234-4234-8234-123456789abc',1,
                     '12345678-1234-4234-8234-123456789abc',root+'/state.sqlite',root+'/ledger.sock')
  self.store.fence(1,'12345678-1234-4234-8234-123456789abc')
  self.store.fence(2,'12345678-1234-4234-8234-123456789abc')
  self.store.fence(3,'12345678-1234-4234-8234-123456789abc')
  self.store.fence(4,'12345678-1234-4234-8234-123456789abc')
  self.old=self.store.read();self.new=dict(self.old,epoch=6,release_sha256='d'*64,config_sha256='e'*64)
  self.proof={'approval_body_sha256':'f'*64,'snapshot_sha256':'1'*64,'recovery_plan_sha256':'2'*64,
              'old_descriptor_sha256':self.store.head(self.old),'new_descriptor_sha256':self.store.head(self.new),
              'all_writers_excluded':True,'install_lock_held':True,'retained_resources_verified':True}
 def tearDown(self):self.temp.cleanup()
 def execute(self):return subject.rebind_prepared(self.store,self.old,self.new,self.proof)
 def test_appends_same_journal_without_grant(self):
  self.assertEqual(self.execute(),self.new);self.assertEqual(self.store.read(),self.new)
  with self.assertRaises(ActivationError):self.store.read(require_active=True)
  self.assertEqual(len(self.store._journal()),6)
 def test_repeat_rejected(self):
  self.execute()
  with self.assertRaisesRegex(ValueError,'STALE_OR_UNRECONCILED'):self.execute()
 def test_wrong_old_epoch_rejected(self):
  self.old['epoch']=2
  with self.assertRaises(ValueError):self.execute()
 def test_active_proposal_rejected(self):
  self.new['state']='ACTIVE'
  with self.assertRaises(ValueError):self.execute()
 def test_generation_change_rejected(self):
  self.new['generation']=2
  with self.assertRaisesRegex(ValueError,'CANONICAL_IDENTITY'):self.execute()
 def test_database_change_rejected(self):
  self.new['db_path']+='.new'
  with self.assertRaisesRegex(ValueError,'CANONICAL_IDENTITY'):self.execute()
 def test_missing_gate_rejected(self):
  self.proof['all_writers_excluded']=False
  with self.assertRaisesRegex(ValueError,'LIVE_GATES'):self.execute()
 def test_bool_like_gate_rejected(self):
  self.proof['install_lock_held']=1
  with self.assertRaisesRegex(ValueError,'LIVE_GATES'):self.execute()
 def test_proof_extra_key_rejected(self):
  self.proof['extra']=True
  with self.assertRaisesRegex(ValueError,'PROOF_KEYS'):self.execute()
 def test_hash_mismatch_rejected(self):
  self.proof['new_descriptor_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'DESCRIPTOR_BINDING'):self.execute()
 def test_wrong_owner_rejected(self):
  with mock.patch.object(subject.os,'geteuid',return_value=self.store.owner_uid+1):
   with self.assertRaisesRegex(ValueError,'OWNER_REQUIRED'):self.execute()
 def test_crash_after_journal_before_descriptor_holds(self):
  original=pathlib.Path(self.store.descriptor).read_bytes()
  with mock.patch.object(self.store,'_write_descriptor',side_effect=OSError('simulated crash')):
   with self.assertRaises(OSError):self.execute()
  self.assertEqual(pathlib.Path(self.store.descriptor).read_bytes(),original)
  with self.assertRaises(ActivationError):self.store.read()
  with self.assertRaisesRegex(ValueError,'STALE_OR_UNRECONCILED'):self.execute()
  self.assertEqual(self.store._journal()[-1][0]['descriptor'],self.new)
 def test_lock_released_after_failure(self):
  import fcntl
  with mock.patch.object(self.store,'_append',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.execute()
  fd=os.open(self.store.lock_path,os.O_RDONLY)
  try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  finally:os.close(fd)
  self.assertEqual(self.store.read(),self.old)

if __name__=='__main__':unittest.main()
