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
if __name__=='__main__':unittest.main()
