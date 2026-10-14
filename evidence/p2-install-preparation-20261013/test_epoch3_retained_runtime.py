import hashlib,json,os,pathlib,sys,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(os.environ['P2_NEW_ROOT'])/'stage1'))
import epoch3_retained_runtime as subject
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.obj=subject.RetainedEpoch3Runtime.__new__(subject.RetainedEpoch3Runtime)
  self.obj.directory=subject.T;self.obj.receipt_path=subject.T+'/epoch4-runtime-provisioning.json'
  mandatory=['/etc/xuanjun-development/tls-renewal.json','/etc/systemd/system/'+subject.TLS_TIMER,
             '/etc/systemd/system/'+subject.TLS_SERVICE,'/etc/systemd/system/nginx.service',
             '/etc/xuanjun-development/nginx-main.conf']
  targets=mandatory+['/etc/xuanjun-development/fixture-'+str(n) for n in range(19)]
  self.rows=[{'target':p,'previous':None} for p in targets]
  self.raw=json.dumps({'targets':self.rows}).encode();self.events=[]
  self.plan={'release_directory':'integration-'+'a'*16,'auxiliary_isolation':{},'tls_renewal':{},'prerequisites':{},
             'provisioning':[{'target':p,'source':p,'replacements':{},'source_sha256':hashlib.sha256(b'{}').hexdigest(),
                             'rendered_sha256':hashlib.sha256(b'{}').hexdigest(),'mode':0o600,'owner_uid':0,'group_gid':0} for p in targets]}
  self.obj._authority=lambda:None;self.obj._binding=lambda b,*a:(b['source'],b['target'])
  self.obj._dropin_parent_state=lambda:True
  self.obj._create_dropin_parent=lambda:self.events.append('mkdir')
  self.obj._atomic_target=lambda *a:self.events.append('target')
  self.obj._command=lambda *a:self.events.append('command')
  self.obj._install_plugin=lambda *a:self.events.append('plugin')
  self.tls=mock.Mock();self.tls.prepare.return_value={};self.tls.apply.side_effect=lambda *a:self.events.append('tls')
  self.patches=[mock.patch.object(subject,'private_read',return_value=self.raw),
   mock.patch.dict(subject.PINS,{subject.T+'/runtime-provisioning.json':hashlib.sha256(self.raw).hexdigest()}),
   mock.patch.object(subject,'_read_regular',return_value=(b'{}',None)),
   mock.patch.object(subject.Auxiliary,'verify'),mock.patch.object(subject.os.path,'lexists',return_value=False),
   mock.patch.object(subject,'TlsLifecycle',return_value=self.tls),
   mock.patch.object(subject,'_atomic_receipt',side_effect=lambda *a:self.events.append('receipt'))]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def execute(self):return self.obj.provision('/opt/xuanjun-control-releases/'+self.plan['release_directory'],self.plan)
 def test_success_order_retains_resources(self):
  result=self.execute();self.assertEqual(self.events[:3],['receipt','tls','mkdir'])
  self.assertEqual(self.events.count('target'),24);self.assertEqual(self.events[-1],'plugin')
  self.assertFalse(result['rollback_complete']);self.assertFalse(result['retained_resources_replayed'])
 def test_receipt_hash_binds_serialized_file_newline(self):
  saved=[]
  with mock.patch.object(subject,'_atomic_receipt',side_effect=lambda path,value:saved.append(value)):
   result=self.execute()
  raw=(json.dumps(saved[0],sort_keys=True,separators=(',',':'))+'\n').encode()
  self.assertEqual(result['receipt_sha256'],hashlib.sha256(raw).hexdigest())
 def test_tls_failure_does_not_restore_or_write_targets(self):
  self.tls.apply.side_effect=ValueError('tls failed')
  with self.assertRaises(ValueError):self.execute()
  self.assertEqual(self.events,['receipt'])
 def test_source_mismatch_before_receipt(self):
  self.plan['provisioning'][0]['source_sha256']='0'*64
  with self.assertRaises(ValueError):self.execute()
  self.assertEqual(self.events,[])
 def test_duplicate_target_rejected(self):
  self.plan['provisioning'][1]=self.plan['provisioning'][0]
  with self.assertRaises(ValueError):self.execute()
  self.assertEqual(self.events,[])
 def test_prior_receipt_hash_rejected(self):
  with mock.patch.object(subject,'private_read',return_value=b'{}'):
   with self.assertRaises(ValueError):self.execute()
 def test_existing_attempt_rejected(self):
  with mock.patch.object(subject.os.path,'lexists',return_value=True):
   with self.assertRaises(ValueError):self.execute()
 def test_generic_restore_forbidden(self):
  with self.assertRaisesRegex(ValueError,'GENERIC_RESTORE_FORBIDDEN'):self.obj.restore({})
 def test_nss_replay_and_removal_forbidden(self):
  for action in (self.obj.prepare_prerequisites,self.obj.restore_prerequisites):
   with self.assertRaises(ValueError):action({})

class OwnerMaskTests(unittest.TestCase):
 def setUp(self):
  from types import SimpleNamespace
  self.obj=subject.RetainedEpoch3Runtime.__new__(subject.RetainedEpoch3Runtime)
  self.obj.directory=subject.T;self.obj._authority=lambda:None;self.obj._command=mock.Mock()
  self.targets=sorted(subject.Auxiliary.UNIT_ROOT+'/'+n for n in subject.Auxiliary.UNITS)
  self.raw=json.dumps({'targets':[{'target':t,'previous':{'masked':True}} for t in self.targets]}).encode()
  self.plan={'runtime':{'auxiliary_isolation':{},'provisioning':[{'target':t,'rendered_sha256':hashlib.sha256(b'new').hexdigest(),
   'owner_uid':0,'group_gid':0,'mode':0o644} for t in self.targets]}}
  self.patches=[mock.patch.object(subject,'private_read',return_value=self.raw),
   mock.patch.dict(subject.PINS,{subject.T+'/runtime-provisioning.json':hashlib.sha256(self.raw).hexdigest()}),
   mock.patch.object(subject.Auxiliary,'is_mask',return_value=False),mock.patch.object(subject.Auxiliary,'restore_mask'),
   mock.patch.object(subject.Auxiliary,'verify'),mock.patch.object(subject,'_read_regular',return_value=(b'new',SimpleNamespace(st_uid=0,st_gid=0,st_mode=0o100644)))]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def execute(self):return self.obj.restore_retained_owner_masks(self.plan)
 def test_exact_two_original_owner_masks(self):
  self.assertTrue(self.execute()['original_owner_masks_restored'])
  self.assertEqual([c[0][0] for c in subject.Auxiliary.restore_mask.call_args_list],self.targets)
 def test_existing_masks_preserved(self):
  subject.Auxiliary.is_mask.return_value=True;self.execute();subject._read_regular.assert_not_called()
 def test_changed_target_bytes_hold_before_masks(self):
  subject._read_regular.return_value=(b'drift',subject._read_regular.return_value[1])
  with self.assertRaises(ValueError):self.execute()
  subject.Auxiliary.restore_mask.assert_not_called()
 def test_old_receipt_changed(self):
  subject.private_read.return_value=b'{}'
  with self.assertRaises(ValueError):self.execute()
 def test_unexpected_old_mask_scope(self):
  raw=json.dumps({'targets':[{'target':'/etc/systemd/system/sshd.service','previous':{'masked':True}}]}).encode()
  subject.private_read.return_value=raw
  with mock.patch.dict(subject.PINS,{subject.T+'/runtime-provisioning.json':hashlib.sha256(raw).hexdigest()}):
   with self.assertRaises(ValueError):self.execute()
  subject.Auxiliary.restore_mask.assert_not_called()
 def test_mask_failure_not_hidden(self):
  subject.Auxiliary.restore_mask.side_effect=OSError('mask')
  with self.assertRaises(OSError):self.execute()

if __name__=='__main__':unittest.main()
