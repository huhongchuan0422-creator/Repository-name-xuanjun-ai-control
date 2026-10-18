import os,sys,tempfile,unittest
sys.path.insert(0,os.path.dirname(__file__))
from attempt_ledger import Ledger

class TestAttempt(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();os.chmod(self.temp.name,0o700)
  self.g={'grant_id':'grant-123456789','source_commit':'a'*40,'source_tree':'b'*40,
          'kit_sha256':'c'*64,'manifest_sha256':'d'*64,'approval_body_sha256':'e'*64,
          'target_host':'fixed-uk-host','actor_id':'approved-auditor','expires_utc':9999999999,
          'recovery_entry':'original_approved_resume','max_attempts':5}
  self.ledger=Ledger(self.temp.name,self.g,clock=lambda:10000000)
  self.proof={'outcome':'NO_WRITE','evidence_sha256':'1'*64,'checkpoint_sha256':'2'*64,'log_sha256':'3'*64}
 def tearDown(self):self.temp.cleanup()
 def test_success_stops(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  p=dict(self.proof,outcome='SUCCESS');self.assertEqual(self.ledger.reconcile(a,p,lambda _:True),'SUCCEEDED')
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.ledger.claim()
 def test_max_five_after_proof(self):
  for i in range(5):
   a=self.ledger.claim();self.ledger.intent(a,'f'*64);self.ledger.reconcile(a,self.proof,lambda _:True)
  self.assertEqual(len(self.ledger.snapshot()['attempts']),5)
  with self.assertRaisesRegex(ValueError,'EXHAUSTED'):self.ledger.claim()
 def test_unknown_partial_block(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64);self.ledger.uncertain(a)
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.ledger.claim()
  self.ledger.reconcile(a,self.proof,lambda _:True)
  b=self.ledger.claim();self.ledger.intent(b,'f'*64);self.ledger.uncertain(b,partial=True)
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.ledger.claim()
 def test_invalid_verifier_cannot_unblock(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  with self.assertRaisesRegex(ValueError,'PROOF_UNVERIFIED'):self.ledger.reconcile(a,self.proof,lambda _:False)
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.ledger.claim()
 def test_restart_persists(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  new=Ledger(self.temp.name,self.g,clock=lambda:10000001)
  self.assertEqual(new.snapshot()['attempts'][0]['id'],a)
  with self.assertRaisesRegex(ValueError,'UNRESOLVED'):new.claim()
  new.reconcile(a,self.proof,lambda _:True);self.assertEqual(new.claim().split('-')[-2],'2')
 def test_history_removal_cannot_reset_quota(self):
  a=self.ledger.claim();os.unlink(self.ledger.data)
  with self.assertRaisesRegex(ValueError,'HISTORY_MISSING'):self.ledger.claim()
 def test_conflicting_old_attempt(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  with self.assertRaisesRegex(ValueError,'ATTEMPT_ID'):self.ledger.uncertain('unrelated')
 def test_scope_change_denied(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  other=dict(self.g,kit_sha256='9'*64)
  with self.assertRaisesRegex(ValueError,'LEDGER_BINDING'):Ledger(self.temp.name,other).snapshot()
 def test_expiry(self):
  l=Ledger(self.temp.name,dict(self.g,expires_utc=100),clock=lambda:101)
  with self.assertRaisesRegex(ValueError,'EXPIRED'):l.claim()
 def test_checkpoint_idempotent_and_conflict(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  self.assertFalse(self.ledger.checkpoint(a,'stage_one','0'*64))
  self.assertTrue(self.ledger.checkpoint(a,'stage_one','0'*64))
  with self.assertRaisesRegex(ValueError,'CHECKPOINT_CONFLICT'):self.ledger.checkpoint(a,'stage_one','1'*64)
 def test_no_replay_intent(self):
  a=self.ledger.claim();self.ledger.intent(a,'f'*64)
  with self.assertRaisesRegex(ValueError,'INTENT_ALREADY_RECORDED'):self.ledger.intent(a,'f'*64)
 def test_mismatch_authority_and_max(self):
  with self.assertRaisesRegex(ValueError,'GRANT_COUNT'):Ledger(self.temp.name,dict(self.g,max_attempts=6))
  with self.assertRaisesRegex(ValueError,'DIRECTORY_MODE'):
   os.chmod(self.temp.name,0o755);Ledger(self.temp.name,self.g)

if __name__=='__main__':unittest.main()
