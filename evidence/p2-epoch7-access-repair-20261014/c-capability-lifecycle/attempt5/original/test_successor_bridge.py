import os,sys,tempfile,unittest
sys.path.insert(0,os.path.dirname(__file__))
from attempt_ledger import Ledger
from successor_bridge import Bridge,PHASES
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();os.chmod(self.t.name,0o700)
  self.g={'grant_id':'new-v2-grant-123456','source_commit':'a'*40,'source_tree':'b'*40,'kit_sha256':'c'*64,'manifest_sha256':'d'*64,'approval_body_sha256':'e'*64,'target_host':'fixed-host','actor_id':'approved-actor','expires_utc':9999999999,'recovery_entry':'new-reviewed-entry','max_attempts':5}
  self.l=Ledger(self.t.name,self.g,clock=lambda:100)
  self.runs=[];self.v={p:'3'*64 for p in PHASES}
  self.auth=lambda *args:dict(writer=True,lease=True,fence=True,exclusive=True,digest='1'*64)
  self.executor=lambda a,p,h:(self.runs.append(p) or dict(status='SUCCESS',effect_sha256=h,log_sha256='2'*64))
  self.b=Bridge(self.l,self.auth,lambda *args:True,self.executor)
  self.proof=dict(outcome='SAFE_CHECKPOINT',evidence_sha256='5'*64,checkpoint_sha256='6'*64,log_sha256='7'*64)
 def tearDown(self):self.t.cleanup()
 def test_sixteen_and_success(self):
  a=self.b.begin('4'*64);self.assertEqual(self.b.phases(a,self.v),'ALL_16_VERIFIED');self.assertEqual(len(self.runs),16)
  self.b.terminal(a,dict(self.proof,outcome='SUCCESS'))
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.b.begin('4'*64)
 def test_new_attempt_skips_completed(self):
  a=self.b.begin('4'*64);self.b.phases(a,self.v);self.b.terminal(a,self.proof)
  b=self.b.begin('4'*64);self.b.phases(b,self.v);self.assertEqual(len(self.runs),16)
 def test_writer_unknown_blocks(self):
  self.b.authority=lambda *args:dict(writer=False,lease=True,fence=True,exclusive=True,digest='1'*64)
  with self.assertRaisesRegex(ValueError,'GLOBAL_FENCE_UNKNOWN'):self.b.begin('4'*64)
 def test_lease_loss_blocks_reclaim(self):
  def auth(g,a,phase):
   x=self.auth(g,a,phase)
   if phase=='phase_02':x['lease']=False
   return x
  self.b.authority=auth;a=self.b.begin('4'*64)
  with self.assertRaisesRegex(ValueError,'GLOBAL_FENCE_UNKNOWN'):self.b.phases(a,self.v)
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.b.begin('4'*64)
 def test_result_unknown_blocks(self):
  self.b.executor=lambda a,p,h:dict(status='UNKNOWN',effect_sha256=h,log_sha256='2'*64)
  a=self.b.begin('4'*64)
  with self.assertRaisesRegex(ValueError,'EFFECT_UNKNOWN'):self.b.phases(a,self.v)
 def test_unreconciled_stage_blocks(self):
  self.b.reconciler=lambda *args:False;a=self.b.begin('4'*64)
  with self.assertRaisesRegex(ValueError,'EFFECT_UNRECONCILED'):self.b.phases(a,self.v)
  self.assertEqual(self.l.snapshot()['completed'],[])
 def test_reboot_checkpoint_resume(self):
  counter=[0]
  def fail(a,p,h):
   counter[0]+=1
   if counter[0]==3:raise RuntimeError('crash')
   return dict(status='SUCCESS',effect_sha256=h,log_sha256='2'*64)
  self.b.executor=fail;a=self.b.begin('4'*64)
  with self.assertRaises(RuntimeError):self.b.phases(a,self.v)
  self.assertEqual(len(self.l.snapshot()['completed']),2)
  self.b.terminal(a,self.proof)
  second=Bridge(Ledger(self.t.name,self.g,clock=lambda:101),self.auth,lambda *args:True,self.executor)
  b=second.begin('4'*64);second.phases(b,self.v);self.assertEqual(len(self.runs),14)
