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
        return self.store.create("tenant-a", "user-a", "app-a", "business_license", digest, idem)
    def test_encrypted_and_restart_read(self):
        job=self.create()
        self.store.claim(job["job_id"])
        self.store.update(job["job_id"],status="needs_review",fields={"company_name":{"value":"synthetic secret marker"}})
        raw=open(self.path,"rb").read()
        self.assertNotIn(b"synthetic secret marker",raw)
        second=SecureSQLiteJobStore(self.path,self.key)
        self.assertEqual(second.get(job["job_id"],"tenant-a")["fields"]["company_name"]["value"],"synthetic secret marker")
        self.assertIsNone(second.get(job["job_id"],"tenant-b"))
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
        self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"human verified text"})
        with self.assertRaisesRegex(ValueError,"OCR_CONFIRMED_IMMUTABLE"):
            self.store.update(job["job_id"],status="needs_review")
        with self.assertRaisesRegex(ValueError,"STALE_CONFIRMATION_REVISION"):
            self.store.confirm(job["job_id"],"tenant-a",1,{"company_name":"overwrite"})
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
        self.assertNotIn(b"tenant-a", open(self.path, "rb").read())
    def test_reject_wrong_key(self):
        job=self.create()
        with self.assertRaisesRegex(RuntimeError, "OCR_ENCRYPTION_KEY_MISMATCH"):
            SecureSQLiteJobStore(self.path,Fernet.generate_key())

if __name__=="__main__":unittest.main()
