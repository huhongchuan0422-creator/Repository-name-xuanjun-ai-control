import unittest
from unittest.mock import patch
from test_community_shared_license_cas import SharedLicenseCas

class RecoveryWriteback(SharedLicenseCas):
 def recover(self,**changes):
  options=dict(document_type='business_license',expected_application_revision=self.rev,
   expected_wechat_version=self.version,confirmed_fields={'company_name':'SYNTHETIC','credit_code':'SYNTHETIC_CODE','legal_representative':'SYNTHETIC_PERSON','registered_address':'SYNTHETIC_ADDRESS'},
   recovery_receipt={'id':'a'*64,'payload_hash':'b'*64},recovery_replay_check=lambda a,p:None)
  options.update(changes)
  return self.service._fill_confirmed_document_draft(self.fx.applicant['token'],self.fx.applicant['csrf'],self.app['application'],**options)
 def test_recovery_four_fields_and_same_receipt_replay(self):
  result=self.recover();before=self.snapshot();self.assertEqual(result,self.recover());self.assertEqual(before,self.snapshot())
  profile=self.service._read(self.app['application'])['profile']['subject_info']['business_license_info']
  self.assertEqual(set(profile),{'merchant_name','license_number','legal_person','license_address'})
  self.assertEqual(len(result['applied']),4)
 def test_receipt_payload_conflict_no_write(self):
  self.recover();before=self.snapshot()
  with self.assertRaises(ValueError):self.recover(recovery_receipt={'id':'a'*64,'payload_hash':'c'*64})
  self.assertEqual(before,self.snapshot())
 def test_receipt_replay_rechecks_material(self):
  self.recover();before=self.snapshot()
  def fail(a,p):raise PermissionError('MATERIAL_REPLACED')
  with self.assertRaises(PermissionError):self.recover(recovery_replay_check=fail)
  self.assertEqual(before,self.snapshot())
 def test_failed_transaction_has_no_receipt_or_profile(self):
  before=self.snapshot()
  with patch.object(self.service,'_save',side_effect=RuntimeError('FAIL')):
   with self.assertRaises(RuntimeError):self.recover()
  self.assertEqual(before,self.snapshot())
 def test_replay_after_later_change_denied(self):
  self.recover();r=self.service._read(self.app['application']);r['version']+=1
  with self.c.tx():self.service._save(self.app['application'],self.fx.fx.uid1,r)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.recover()
  self.assertEqual(before,self.snapshot())
if __name__=='__main__':unittest.main()
