import unittest
from test_backup_receipt_delta import record
from task_delivery_backup_receipt import map_report,BackupReceiptError

class BackupReferenceTests(unittest.TestCase):
    def test_base_and_result_reject_synthetic_sensitive_sentinel(self):
        # Synthetic sentinel only; values are not emitted in test output.
        for key in ('base_ref','result_ref'):
            r=record();r[key]='password-sentinel'
            with self.subTest(field=key):self.assertRaises(BackupReceiptError,map_report,r)
    def test_full_hashes_and_safe_refs_are_structurally_allowed(self):
        r=record();r['base_ref']='a'*40;r['result_ref']='b'*64
        x=map_report(r);self.assertEqual(x['state'],'UNVERIFIED_REPORT');self.assertEqual(x['provider_verification'],'UNKNOWN')
        r['base_ref']='commit-ref-one';r['result_ref']='version-ref-two';self.assertEqual(map_report(r)['state'],'UNVERIFIED_REPORT')
    def test_unknown_and_invalid_reference_types(self):
        r=record();r.update(reported_status='BACKUP_FAILED',base_ref='UNKNOWN',result_ref='UNKNOWN',last_success_at='UNKNOWN',file_hashes=[])
        self.assertEqual(map_report(r)['state'],'UNVERIFIED_REPORT')
        for value in ('a'*39,'a'*41,'A'*40,None,{},'',17):
            for key in ('base_ref','result_ref'):
                x=record();x[key]=value
                with self.subTest(field=key,kind=type(value).__name__,length=len(value) if hasattr(value,'__len__') else -1):self.assertRaises(BackupReceiptError,map_report,x)
    def test_fixed_exclusion_categories_remain_accepted(self):
        self.assertEqual(map_report(record())['state'],'UNVERIFIED_REPORT')
        x=record();x['excluded'].append('password-sentinel');self.assertRaises(BackupReceiptError,map_report,x)
if __name__=='__main__':unittest.main()
