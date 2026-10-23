"""HTTP contract and tenant-isolation tests; inference is explicitly injected, never mocked as proof of OCR."""
import io
import os
import hashlib
import tempfile
import unittest
from fastapi.testclient import TestClient
try:
    from .api import create_app, Principal, JobStore, SQLiteJobStore
    from .secure_store import SecureSQLiteJobStore
except ImportError:
    from api import create_app, Principal, JobStore, SQLiteJobStore
    from secure_store import SecureSQLiteJobStore

TOKEN_TENANTS = {
    "tenant-a-token": Principal(subject="user-a", tenant_id="tenant-a", permissions={"ocr:use"}),
    "tenant-b-token": Principal(subject="user-b", tenant_id="tenant-b", permissions={"ocr:use"}),
}
def auth(token):
    if token not in TOKEN_TENANTS:
        raise ValueError("invalid token")
    return TOKEN_TENANTS[token]
def inference_fixture(image, document_type, max_bytes):
    # Test-only dependency injection; this does not constitute OCR inference evidence.
    if not image.startswith(b"\xff\xd8\xff"):
        raise ValueError("UNSUPPORTED_IMAGE_MAGIC")
    return {"fields": {"company_name": {"value": "SYNTHETIC ONLY", "confidence": 0.9, "requires_review": False, "source": "ocr"}},
            "requires_human_confirmation": True, "authenticity_verified": False}
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.image = bytes([255,216,255]) + b"synthetic"
        self.expected_sha = hashlib.sha256(self.image).hexdigest()
        self.revoked_apps = set()
        self.revoked_attachments = set()
        def attachment_resolver(p, app, attachment, content_sha, document_type, expected_application_revision=None):
            valid = (app == "synthetic-app" and attachment == "synthetic-attachment" and
                     content_sha == self.expected_sha and attachment not in self.revoked_attachments and
                     document_type == "business_license" and expected_application_revision in (None, "synthetic-revision-1"))
            return {"authorized": valid, "content_sha256": self.expected_sha,
                    "document_type": "business_license", "application_revision": "synthetic-revision-1"}
        self.attachment_resolver = attachment_resolver
        from cryptography.fernet import Fernet
        self._tmp = tempfile.TemporaryDirectory()
        store = SecureSQLiteJobStore(os.path.join(self._tmp.name, "api-tests.sqlite3"), Fernet.generate_key())
        self.client = TestClient(create_app(authenticate=auth, store=store, infer=inference_fixture,
            authorize_application=lambda p, app: app == "synthetic-app" and app not in self.revoked_apps,
            authorize_attachment=attachment_resolver))
        self.headers = {"Authorization":"Bearer tenant-a-token", "Idempotency-Key":"0123456789abcdef"}
    def submit(self):
        return self.client.post("/api/v1/ocr/jobs", headers=self.headers,
            data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
            files={"file":("synthetic.jpg", b"\xff\xd8\xffsynthetic", "image/jpeg")})
    def test_missing_auth_denied(self):
        r=self.client.post("/api/v1/ocr/jobs", headers={"Idempotency-Key":"0123456789abcdef"}, data={"document_type":"business_license","onboarding_application_id":"x","attachment_id":"synthetic-attachment"},
                           files={"file":("x.jpg",b"abc","image/jpeg")})
        self.assertEqual(r.status_code,401)
    def test_submit_and_get_result(self):
        r=self.submit(); self.assertEqual(r.status_code,202, r.text)
        job=self.client.get("/api/v1/ocr/jobs/"+r.json()["job_id"],headers={"Authorization":"Bearer tenant-a-token"})
        self.assertEqual(job.status_code,200)
        self.assertEqual(job.json()["fields"]["company_name"]["value"],"SYNTHETIC ONLY")
        self.assertTrue(job.json()["requires_human_confirmation"])
        self.assertFalse(job.json()["authenticity_verified"])
    def test_cross_tenant_cannot_read_job(self):
        r=self.submit(); job_id=r.json()["job_id"]
        other=self.client.get("/api/v1/ocr/jobs/"+job_id,headers={"Authorization":"Bearer tenant-b-token"})
        self.assertEqual(other.status_code,404)
    def test_unsupported_material_rejected(self):
        r=self.client.post("/api/v1/ocr/jobs",headers=self.headers,
            data={"document_type":"storefront_photo","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
            files={"file":("store.jpg",b"\xff\xd8\xffsynthetic","image/jpeg")})
        self.assertEqual(r.status_code,400)
    def test_sqlite_persistence_survives_store_recreation_and_isolates_tenant(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "jobs.sqlite3")
            store1 = SQLiteJobStore(path)
            job = store1.create("tenant-a", "user-a", "app-1", "business_license", "a" * 64)
            store1.update(job["job_id"], status="needs_review", fields={"company_name": {"value": "SYNTHETIC"}})
            store2 = SQLiteJobStore(path)
            self.assertEqual(store2.get(job["job_id"], "tenant-a")["status"], "needs_review")
            self.assertIsNone(store2.get(job["job_id"], "tenant-b"))
    def test_ownership_callback_required(self):
        c = TestClient(create_app(authenticate=auth, store=JobStore(), infer=inference_fixture))
        r = c.post("/api/v1/ocr/jobs", headers=self.headers,
            data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
            files={"file":("synthetic.jpg", bytes([255,216,255])+b"synthetic", "image/jpeg")})
        self.assertEqual(r.status_code, 403)
    def test_missing_persistent_store_denied(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"OCR_SQLITE_PATH": ""}):
            with self.assertRaisesRegex(RuntimeError, "OCR_SQLITE_PATH_REQUIRED"):
                create_app(authenticate=auth, infer=inference_fixture)
    def test_http_encrypted_restart_replay_and_tenant_ownership(self):
        from cryptography.fernet import Fernet
        try:
            from .secure_store import SecureSQLiteJobStore
        except ImportError:
            from secure_store import SecureSQLiteJobStore
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "secure-jobs.sqlite")
            key = Fernet.generate_key()
            def app():
                return TestClient(create_app(authenticate=auth,
                    store=SecureSQLiteJobStore(path, key), infer=inference_fixture,
                    authorize_application=lambda p, app_id: app_id == "synthetic-app",
                    authorize_attachment=lambda p, app_id, attachment, content_sha, document_type, expected_revision=None: {"authorized": attachment == "synthetic-attachment" and content_sha == hashlib.sha256(bytes([255,216,255])+b"synthetic").hexdigest() and document_type == "business_license" and expected_revision in (None, "synthetic-revision-1"), "content_sha256": hashlib.sha256(bytes([255,216,255])+b"synthetic").hexdigest(), "document_type": "business_license", "application_revision": "synthetic-revision-1"}))
            with app() as client1:
                first = client1.post("/api/v1/ocr/jobs", headers=self.headers,
                    data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
                    files={"file":("synthetic.jpg", bytes([255,216,255])+b"synthetic", "image/jpeg")})
                self.assertEqual(first.status_code, 202, first.text)
                job_id = first.json()["job_id"]
            with app() as client2:
                read = client2.get("/api/v1/ocr/jobs/"+job_id, headers={"Authorization":"Bearer tenant-a-token"})
                self.assertEqual(read.status_code, 200)
                self.assertEqual(read.json()["fields"]["company_name"]["value"], "SYNTHETIC ONLY")
                replay = client2.post("/api/v1/ocr/jobs", headers=self.headers,
                    data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
                    files={"file":("synthetic.jpg", bytes([255,216,255])+b"synthetic", "image/jpeg")})
                self.assertEqual(replay.status_code, 202)
                self.assertEqual(replay.json()["job_id"],job_id)
                conflict = client2.post("/api/v1/ocr/jobs", headers=self.headers,
                    data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
                    files={"file":("synthetic.jpg", bytes([255,216,255])+b"DIFFERENT", "image/jpeg")})
                self.assertEqual(conflict.status_code,403)
                denied = client2.get("/api/v1/ocr/jobs/"+job_id,headers={"Authorization":"Bearer tenant-b-token"})
                self.assertEqual(denied.status_code,404)
    def test_secure_mode_requires_encryption_key(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"OCR_SQLITE_PATH":os.path.join(temp,"jobs.db"),
                                         "OCR_ENCRYPTION_KEY":""}):
                with self.assertRaisesRegex(RuntimeError,"OCR_ENCRYPTION_KEY_REQUIRED"):
                    create_app(authenticate=auth, infer=inference_fixture)
    def test_confirmation_rejects_extra_fields_and_oversize_values(self):
        r=self.submit(); url="/api/v1/ocr/jobs/"+r.json()["job_id"]+"/confirm"
        headers={"Authorization":"Bearer tenant-a-token","Idempotency-Key":"confirm-validation-0001"}
        self.assertEqual(self.client.post(url, headers=headers, json={"revision":1, "fields":{"authenticity_verified":"true"}}).status_code,400)
        self.assertEqual(self.client.post(url, headers={**headers, "Idempotency-Key":"confirm-validation-0002"}, json={"revision":1, "fields":{"company_name":"x"*257}}).status_code,400)
    def test_wrong_bytes_rejected_for_valid_attachment_id(self):
        r=self.client.post("/api/v1/ocr/jobs",headers={**self.headers,"Idempotency-Key":"wrong-bytes-key-001"},
            data={"document_type":"business_license","onboarding_application_id":"synthetic-app","attachment_id":"synthetic-attachment"},
            files={"file":("synthetic.jpg",bytes([255,216,255])+b"DIFFERENT","image/jpeg")})
        self.assertEqual(r.status_code,403)
        self.assertIn("ATTACHMENT_CONTENT_BINDING_UNVERIFIED",r.text)
    def test_application_revocation_denies_get_confirm_delete(self):
        r=self.submit(); self.assertEqual(r.status_code,202,r.text); job_id=r.json()["job_id"]
        self.revoked_apps.add("synthetic-app")
        headers={"Authorization":"Bearer tenant-a-token","Idempotency-Key":"revoke-confirm-key-001"}
        self.assertEqual(self.client.get("/api/v1/ocr/jobs/"+job_id,headers=headers).status_code,403)
        self.assertEqual(self.client.post("/api/v1/ocr/jobs/"+job_id+"/confirm",headers=headers,json={"revision":1,"fields":{"company_name":"x"}}).status_code,403)
        self.assertEqual(self.client.delete("/api/v1/ocr/jobs/"+job_id,headers=headers).status_code,403)
    def test_attachment_revocation_denies_get_confirm_delete(self):
        r=self.submit(); self.assertEqual(r.status_code,202,r.text); job_id=r.json()["job_id"]
        self.revoked_attachments.add("synthetic-attachment")
        headers={"Authorization":"Bearer tenant-a-token","Idempotency-Key":"revoke-confirm-key-002"}
        self.assertEqual(self.client.get("/api/v1/ocr/jobs/"+job_id,headers=headers).status_code,403)
        self.assertEqual(self.client.post("/api/v1/ocr/jobs/"+job_id+"/confirm",headers=headers,json={"revision":1,"fields":{"company_name":"x"}}).status_code,403)
        self.assertEqual(self.client.delete("/api/v1/ocr/jobs/"+job_id,headers=headers).status_code,403)
    def test_valid_attachment_id_with_different_bytes_is_denied(self):
        wrong = bytes([255,216,255]) + b'different image bytes'
        r = self.client.post('/api/v1/ocr/jobs',headers={**self.headers,'Idempotency-Key':'content-mismatch-key-01'},
            data={'document_type':'business_license','onboarding_application_id':'synthetic-app','attachment_id':'synthetic-attachment'},
            files={'file':('synthetic.jpg',wrong,'image/jpeg')})
        self.assertEqual(r.status_code,403,r.text)
        self.assertIn('ATTACHMENT_CONTENT_BINDING_UNVERIFIED',r.text)
    def test_confirmed_fields_and_revision_read_back(self):
        r=self.submit(); self.assertEqual(r.status_code,202,r.text); job_id=r.json()['job_id']
        confirm_headers={'Authorization':'Bearer tenant-a-token','Idempotency-Key':'readback-confirm-key-001'}
        body={'revision':1,'fields':{'company_name':'Human confirmed synthetic'}}
        confirmed=self.client.post('/api/v1/ocr/jobs/'+job_id+'/confirm',headers=confirm_headers,json=body)
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        read=self.client.get('/api/v1/ocr/jobs/'+job_id,headers={'Authorization':'Bearer tenant-a-token'})
        self.assertEqual(read.status_code,200,read.text)
        self.assertEqual(read.json().get('confirmed_fields'),body['fields'])
        self.assertEqual(read.json().get('confirmation_revision'),1)
    def test_confirmation_revision_conflict(self):
        r=self.submit(); job_id=r.json()["job_id"]
        url="/api/v1/ocr/jobs/"+job_id+"/confirm"
        payload={"revision":1,"fields":{"company_name":"Human confirmed"}}
        self.assertEqual(self.client.post(url,headers={"Authorization":"Bearer tenant-a-token","Idempotency-Key":"confirm-key-00001"},json=payload).status_code,200)
        self.assertEqual(self.client.post(url,headers={"Authorization":"Bearer tenant-a-token","Idempotency-Key":"confirm-key-00002"},json=payload).status_code,409)
if __name__ == "__main__": unittest.main()
