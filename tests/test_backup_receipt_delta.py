import copy,unittest
from task_delivery_backup_receipt import map_report,unavailable,BackupReceiptError
from task_delivery_ledger.core import LedgerError

def record():return {'schema_version':1,'project_ref':'demo-project','receipt_id':'receipt-1','source_ref':'fixture-provider','reported_status':'BACKUP_SUCCEEDED','observed_at':'2026-11-16T10:00:00Z','base_ref':'base-1','result_ref':'result-1','manifest_ref':'manifest-1','restore_ref':'restore-1','last_success_at':'2026-11-16T09:59:00Z','content_changed':True,'file_hashes':[{'file_ref':'file-1','sha256':'a'*64}],'excluded':['secrets','environment','customer','business_database','raw_logs','cache'],'limitations':['not-full-history']}
class BackupTests(unittest.TestCase):
    def test_default_is_not_enabled_or_success(self):
        x=unavailable();self.assertEqual(x['state'],'UNAVAILABLE');self.assertEqual(x['schedule_enabled'],'UNKNOWN');self.assertFalse(x['backup_started']);self.assertEqual(x['requested_interval_seconds'],300)
    def test_changed_report_is_not_verified_success(self):
        x=map_report(record());self.assertEqual(x['state'],'UNVERIFIED_REPORT');self.assertEqual(x['provider_verification'],'UNKNOWN');self.assertEqual(x['verified_last_success_at'],'UNKNOWN');self.assertEqual(x['reported_new_backup'],'UNKNOWN')
    def test_no_change_is_check_only_no_new_backup(self):
        r=record();r.update(reported_status='CHECK_NO_CHANGE',content_changed=False,result_ref=r['base_ref'],file_hashes=[])
        x=map_report(r);self.assertFalse(x['reported_new_backup']);self.assertEqual(x['receipt']['last_success_at'],r['last_success_at'])
        r['result_ref']='changed';self.assertRaises(BackupReceiptError,map_report,r)
    def test_actual_read_only_route_shows_unavailable(self):
        import json
        import test_delivery_ledger_route as fixture
        t=fixture.RouteTests();t.setUp()
        try:
            status,body,_=t.call('/api/admin/delivery-ledger');self.assertEqual(status,200)
            backup=json.loads(body.decode())['backup'];self.assertEqual(backup['state'],'UNAVAILABLE');self.assertEqual(backup['schedule_enabled'],'UNKNOWN');self.assertFalse(backup['backup_started'])
        finally:t.tearDown()
    def test_invalid_scopes_and_failed_report(self):
        for field in ('restore_ref','manifest_ref'):
            r=record();r[field]='UNKNOWN';self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r['excluded'].remove('raw_logs');self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r['file_hashes'][0]['file_ref']='/customer/data';self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r['file_hashes'][0]['sha256']='not-a-hash';self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r['observed_at']='2026-99-99T99:00:00Z';self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r['excluded']=[{}];self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r['extra']='untrusted';self.assertRaises(BackupReceiptError,map_report,r)
        r=record();r.update(reported_status='BACKUP_FAILED',last_success_at='UNKNOWN',file_hashes=[]);self.assertEqual(map_report(r)['state'],'UNVERIFIED_REPORT')
if __name__=='__main__':unittest.main()
