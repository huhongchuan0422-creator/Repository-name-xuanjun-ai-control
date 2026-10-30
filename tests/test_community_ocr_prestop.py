"""Original OCR compiled-plan/pre-stop regression; Docker observations are mocks.

Run from repository root with unittest discovery; no review workspace paths.
"""
import os,json,copy,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from test_community_preview_update_checkpoint import Checkpoints,fixtures
from scripts import community_preview_release_plan as plan
from scripts import community_preview_update_checkpoint as u
class Prestop(Checkpoints):
 def setUp(self):
  source=fixtures.source()
  source['applicant_ocr']=plan.APPLICANT_OCR_CONTRACT
  with patch.object(fixtures,'source',return_value=source):super().setUp()
  self.synthetic=self.p # Actual compiler output already accepted by real Journal.
 def install_probe(self,response):
  real=self.t.applicant_ocr_config_preflight
  self.probe_calls=[]
  def command(argv):
   if argv[3:5]==['image','inspect']:return '\n'.join(json.dumps(v) for v in (self.p['image']['image_id'],self.p['source']['source_sha'],'10001:1008'))
   if argv[3]=='run':
    self.probe_calls.append(argv)
    if isinstance(response,Exception):raise response
    return response
   return ''
  patch.object(u.original,'command',side_effect=command).start()

 def test_rejection_preserves_prepared_old_and_files(self):
  self.install_probe('OCR_ONBOARDING_REQUIRED')
  before={p.name:p.read_bytes() for p in Path(self.tmp.name).rglob('*') if p.is_file()}
  with self.assertRaisesRegex(u.Hold,'PREFLIGHT_REJECTED'):self.update().run()
  self.assertTrue(self.old);self.assertEqual(self.calls,[]);self.assertEqual(self.j.state['phase'],'PREPARED')
  self.j.validate_history() # same-attempt read/query remains valid; not recovery-stop
  self.assertEqual(before,{p.name:p.read_bytes() for p in Path(self.tmp.name).rglob('*') if p.is_file()})
  mounts=[a for a in self.probe_calls[0] if a.startswith('type=bind')]
  self.assertEqual(len(mounts),1);self.assertTrue(mounts[0].endswith('/config,readonly'))
 def test_timeout_does_not_claim_stop_or_recovery(self):
  self.install_probe(TimeoutError('secret must not leak'))
  with self.assertRaisesRegex(u.Hold,'UNPROVEN_OLD_UNTOUCHED'):self.update().run()
  self.assertTrue(self.old);self.assertEqual(self.calls,[]);self.assertEqual(self.j.state['phase'],'PREPARED');self.j.validate_history()
 def test_config_success_is_not_membership_evidence(self):
  self.install_probe('OCR_CONFIGURATION_VALIDATED_NOT_ACTIVATED')
  self.update().run()
  self.assertTrue(self.probe_calls);self.assertEqual(self.calls[0][3],'stop')
 def test_known_inflight_never_runs_another_probe(self):
  real=self.t.applicant_ocr_config_preflight
  name='xuanjun-community-preview-ocr-preflight-'+self.synthetic['plan_sha256'][:16]
  with patch.object(u.original,'command',return_value=name+'\n') as cmd:
   with self.assertRaisesRegex(u.Hold,'IN_FLIGHT_OR_UNKNOWN'):real(self.synthetic)
   self.assertEqual(cmd.call_count,1)
  self.assertTrue(self.old);self.assertEqual(self.calls,[])
 def test_arbitrary_reference_rejected_by_real_journal(self):
  changed=copy.deepcopy(self.p)
  argv=changed['actions'][3]['argv'];argv[argv.index('--applicant-ocr-store-reference')+1]='/unapproved/db'
  with self.assertRaisesRegex(u.Hold,'EXACT_COMPILED_PLAN_REQUIRED'):u.Journal(self.parent,changed)
  self.assertTrue(self.old);self.assertEqual(self.calls,[])
 def test_contract_digest_and_fixed_pair(self):
  argv=self.p['actions'][3]['argv']
  self.assertEqual(argv[argv.index('--applicant-ocr-key-reference')+1],plan.OCR_KEY_REFERENCE)
  self.assertEqual(argv[argv.index('--applicant-ocr-store-reference')+1],plan.OCR_STORE_REFERENCE)
  source=dict(self.p['source']);source.pop('applicant_ocr')
  old=plan.prepare(source,self.p['current'],self.p['image'])
  self.assertNotEqual(old['plan_sha256'],self.p['plan_sha256'])
  self.assertNotIn('--applicant-ocr-key-reference',old['actions'][3]['argv'])
  self.j.validate_history()
 def test_stopped_compiler_journal_preserves_same_contract(self):
  current=dict(self.p['current'],running=False)
  compiled=plan.prepare_stopped(self.p['source'],current,self.p['image'])
  with tempfile.TemporaryDirectory() as directory,patch.object(u,'JOURNAL_PARENT',directory):
   parent=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
   lease=os.open('community-update.lock',os.O_RDWR|os.O_CREAT,0o600,dir_fd=parent)
   try:
    journal=u.Journal(parent,compiled,lease_fd=lease,handoff_binding={'approval_sha256':'a'*64,'handoff_sha256':'b'*64})
    try:
     self.assertEqual(journal.state['phase'],'PREPARED');journal.validate_history()
     self.assertIn('--applicant-ocr-store-reference',journal.plan['actions'][3]['argv'])
    finally:journal.close()
   finally:os.close(lease);os.close(parent)


def load_tests(loader, standard_tests, pattern):
 # Select the original seven cases only; inherited fixture tests stay in their own module.
 return unittest.TestSuite(Prestop(n) for n in ('test_rejection_preserves_prepared_old_and_files','test_timeout_does_not_claim_stop_or_recovery','test_config_success_is_not_membership_evidence','test_known_inflight_never_runs_another_probe','test_arbitrary_reference_rejected_by_real_journal','test_contract_digest_and_fixed_pair','test_stopped_compiler_journal_preserves_same_contract'))

if __name__ == "__main__":
 unittest.main()
