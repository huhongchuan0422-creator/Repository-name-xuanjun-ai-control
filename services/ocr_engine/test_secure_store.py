"""Real SQLite persistence/concurrency/encryption tests; synthetic values only."""
import os
import sqlite3
import tempfile
import threading
import unittest
from cryptography.fernet import Fernet
try:
    from .secure_store import SecureSQLiteJobStore
except ImportError:
    from secure_store import SecureSQLiteJobStore

class SecureStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "jobs.sqlite3")
        self.key = Fernet.generate_key()
        self.store = SecureSQLiteJobStore(self.path, self.key)
    def tearDown(self):
        self.tmp.cleanup()
    def create(self, idem="0123456789abcdef", digest="a"*64):
        return self.store.create("tenant-a", "user-a", "app-a", "business_license", digest, idem, "synthetic-attachment", "1")
    def test_encrypted_and_restart_read(self):
        job=self.create()
        self.store.claim(job["job_id"])
        self.store.update(job["job_id"],status="needs_review",fields={"company_name":{"value":"synthetic secret marker"}})
        with open(self.path,"rb") as stream:
            raw=stream.read()
        self.assertNotIn(b"synthetic secret marker",raw)
        second=SecureSQLiteJobStore(self.path,self.key)
        self.assertEqual(second.get(job["job_id"],"tenant-a")["fields"]["company_name"]["value"],"synthetic secret marker")
        self.assertIsNone(second.get(job["job_id"],"tenant-b"))
    def test_durable_rate_limit_across_instances(self):
        self.assertTrue(self.store.check_rate("tenant-a", limit=2))
        restarted = SecureSQLiteJobStore(self.path, self.key)
        self.assertTrue(restarted.check_rate("tenant-a", limit=2))
        self.assertFalse(self.store.check_rate("tenant-a", limit=2))
        self.assertTrue(self.store.check_rate("tenant-b", limit=2))
    def test_idempotency_and_payload_conflict(self):
        first=self.create()
        self.assertEqual(first["job_id"],self.create()["job_id"])
        with self.assertRaisesRegex(ValueError,"OCR_IDEMPOTENCY_CONFLICT"):
            self.create(digest="b"*64)
    def test_atomic_claim_across_connections(self):
        job=self.create(); wins=[]
        def attempt():
            wins.append(SecureSQLiteJobStore(self.path,self.key).claim(job["job_id"]))
        threads=[threading.Thread(target=attempt) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(wins.count(True),1)
    def test_crash_recovery_and_no_automatic_replay(self):
        job=self.create(); self.assertTrue(self.store.claim(job["job_id"]))
        reboot=SecureSQLiteJobStore(self.path,self.key)
        self.assertEqual(reboot.get(job["job_id"],"tenant-a")["status"],"processing")
        reboot.recover_interrupted()
        self.assertEqual(reboot.get(job["job_id"],"tenant-a")["status"],"failed")
        self.assertEqual(reboot.get(job["job_id"],"tenant-a")["error_code"],"OCR_INTERRUPTED")
        self.assertFalse(reboot.claim(job["job_id"]))
    def test_confirmation_not_overwritten(self):
        job=self.create()
        self.store.claim(job["job_id"])
        self.store.update(job["job_id"],status="needs_review")
        self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"human verified text"},"confirm-key-original-01")
        with self.assertRaisesRegex(ValueError,"OCR_CONFIRMED_IMMUTABLE"):
            self.store.update(job["job_id"],status="needs_review")
        with self.assertRaisesRegex(ValueError,"STALE_CONFIRMATION_REVISION"):
            self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"overwrite"},"confirm-key-overwrite-01")
        self.assertEqual(self.store.get(job["job_id"],"tenant-a")["confirmed_fields"]["company_name"],"human verified text")
    def test_confirmation_idempotency_and_encrypted_audit(self):
        job=self.create()
        self.store.claim(job["job_id"])
        self.store.update(job["job_id"],status="needs_review",fields={})
        first=self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"human confirmed"},"confirm-key-00001")
        replay=self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"human confirmed"},"confirm-key-00001")
        self.assertEqual(first["job_id"],replay["job_id"])
        self.assertEqual(self.store.get(job["job_id"],"tenant-a")["confirmed_fields"]["company_name"],"human confirmed")
        events=self.store.audit_events(job["job_id"],"tenant-a")
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]["event"],"USER_CONFIRMATION")
        with self.assertRaisesRegex(ValueError,"OCR_CONFIRM_IDEMPOTENCY_CONFLICT"):
            self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"different"},"confirm-key-00001")
        with self.assertRaisesRegex(ValueError,"STALE_CONFIRMATION_REVISION"):
            self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"overwrite"},"confirm-key-00002")
    def test_delete_tenant_scoped(self):
        job=self.create()
        self.assertFalse(self.store.delete(job["job_id"],"tenant-b"))
        self.assertTrue(self.store.delete(job["job_id"],"tenant-a"))
        self.assertIsNone(self.store.get(job["job_id"],"tenant-a"))
    def test_retention_purge_and_non_sensitive_audit(self):
        job = self.create()
        import time
        count = self.store.purge_before(int(time.time()) + 60)
        self.assertEqual(count, 1)
        self.assertIsNone(self.store.get(job["job_id"], "tenant-a"))
        with sqlite3.connect(self.path) as db:
            events = [r[0] for r in db.execute("SELECT event FROM ocr_audit")]
        self.assertIn("created", events)
        self.assertIn("retention_deleted", events)
        with open(self.path, "rb") as stream:
            self.assertNotIn(b"tenant-a", stream.read())
    def test_independent_instances_concurrent_same_key_same_job(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(8)
        def create_once(_):
            store = SecureSQLiteJobStore(self.path, self.key)
            barrier.wait()
            return store.create("tenant-a", "user-a", "app-a", "business_license", "c"*64, "concurrent-key-0001", "synthetic-attachment", "1")
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = list(pool.map(create_once, range(8)))
        self.assertEqual(len({job["job_id"] for job in jobs}), 1)
    def test_same_idempotency_key_changed_application_revision_conflicts(self):
        first=self.store.create('tenant-a','user-a','app-a','business_license','f'*64,'revision-key-0001','synthetic-attachment','1')
        with self.assertRaisesRegex(ValueError,'OCR_IDEMPOTENCY_CONFLICT'):
            self.store.create('tenant-a','user-a','app-a','business_license','f'*64,'revision-key-0001','synthetic-attachment','2')
        self.assertEqual(self.store.get(first['job_id'],'tenant-a')['application_revision'],'1')
    def test_attachment_changes_idempotency_fingerprint(self):
        first = self.store.create("tenant-a", "user-a", "app-a", "business_license", "d"*64, "attachment-key-0001", "attachment-a", "1")
        with self.assertRaisesRegex(ValueError, "OCR_IDEMPOTENCY_CONFLICT"):
            self.store.create("tenant-a", "user-a", "app-a", "business_license", "d"*64, "attachment-key-0001", "attachment-b", "1")
    def test_confirmation_audit_and_idempotency_survive_independent_process(self):
        import json, subprocess, sys
        job=self.create(idem="process-restart-job-0001",digest="e"*64)
        self.store.claim(job["job_id"])
        self.store.update(job["job_id"],status="needs_review",fields={"company_name":{"value":"synthetic only"}})
        fields={"company_name":"synthetic confirmed"}
        self.store.confirm(job["job_id"],"tenant-a",1,fields,"process-confirm-key-0001")
        child = r'''
import json, os
from services.ocr_engine.secure_store import SecureSQLiteJobStore
s=SecureSQLiteJobStore(os.environ['OCR_TEST_DB'],os.environ['OCR_TEST_KEY'].encode('ascii'))
j=s.get(os.environ['OCR_TEST_JOB'],'tenant-a')
assert j and j['status']=='confirmed', 'PROCESS_RESTART_CONFIRMATION_MISSING'
assert j['confirmed_fields']=={'company_name':'synthetic confirmed'}, 'PROCESS_RESTART_CONFIRMED_FIELDS_MISSING'
events=s.audit_events(os.environ['OCR_TEST_JOB'],'tenant-a')
assert len(events)==1 and events[0].get('event')=='USER_CONFIRMATION', 'PROCESS_RESTART_AUDIT_MISSING'
r=s.confirm(os.environ['OCR_TEST_JOB'],'tenant-a',1,{'company_name':'synthetic confirmed'},'process-confirm-key-0001')
assert r.get('recorded') is True and r.get('status')=='confirmed', 'PROCESS_RESTART_IDEMPOTENT_REPLAY_FAILED'
print('INDEPENDENT_PROCESS_RESTART=PASS')
print('CONFIRMED_SQLITE_STATE=PASS')
print('ENCRYPTED_AUDIT_PERSISTENCE=PASS')
print('CONFIRM_IDEMPOTENCY_REPLAY=PASS')
'''
        env=dict(os.environ, OCR_TEST_DB=self.path, OCR_TEST_KEY=self.key.decode('ascii'), OCR_TEST_JOB=job["job_id"])
        result=subprocess.run([sys.executable,"-c",child],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("INDEPENDENT_PROCESS_RESTART=PASS",result.stdout)
        self.assertIn("CONFIRM_IDEMPOTENCY_REPLAY=PASS",result.stdout)
    def test_reject_wrong_key(self):
        job=self.create()
        with self.assertRaisesRegex(RuntimeError, "OCR_ENCRYPTION_KEY_MISMATCH"):
            SecureSQLiteJobStore(self.path,Fernet.generate_key())

if __name__=="__main__":unittest.main()
