"""HTTP contract and tenant-isolation tests; inference is explicitly injected, never mocked as proof of OCR."""
import io
import unittest
from fastapi.testclient import TestClient
from .api import create_app, Principal, JobStore

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
        self.client = TestClient(create_app(authenticate=auth, store=JobStore(), infer=inference_fixture))
        self.headers = {"Authorization":"Bearer tenant-a-token", "Idempotency-Key":"0123456789abcdef"}
    def submit(self):
        return self.client.post("/api/v1/ocr/jobs", headers=self.headers,
            data={"document_type":"business_license","onboarding_application_id":"synthetic-app"},
            files={"file":("synthetic.jpg", b"\xff\xd8\xffsynthetic", "image/jpeg")})
    def test_missing_auth_denied(self):
        r=self.client.post("/api/v1/ocr/jobs", data={"document_type":"business_license","onboarding_application_id":"x"},
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
            data={"document_type":"storefront_photo","onboarding_application_id":"synthetic-app"},
            files={"file":("store.jpg",b"\xff\xd8\xffsynthetic","image/jpeg")})
        self.assertEqual(r.status_code,400)
    def test_confirmation_revision_conflict(self):
        r=self.submit(); job_id=r.json()["job_id"]
        url="/api/v1/ocr/jobs/"+job_id+"/confirm"
        payload={"revision":1,"fields":{"company_name":"Human confirmed"}}
        self.assertEqual(self.client.post(url,headers={"Authorization":"Bearer tenant-a-token"},json=payload).status_code,200)
        self.assertEqual(self.client.post(url,headers={"Authorization":"Bearer tenant-a-token"},json=payload).status_code,409)
if __name__ == "__main__": unittest.main()
