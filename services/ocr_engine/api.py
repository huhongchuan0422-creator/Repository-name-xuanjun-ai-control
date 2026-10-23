"""Local OCR HTTP API prototype. Auth is injected; default app denies every request."""
from __future__ import annotations
import secrets
import threading
import uuid
from typing import Callable, Optional
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from .ocr_core import run_local_ocr

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_HINTS = {"business_license", "id_front"}
class Principal(BaseModel):
    subject: str
    tenant_id: str
    permissions: set[str] = Field(default_factory=set)
class AuthDenied(Exception):
    pass
Authenticator = Callable[[str], Principal]
class JobStore:
    """Process-local prototype only; replace with durable tenant-scoped repository before production."""
    def __init__(self):
        self._lock = threading.RLock()
        self._jobs = {}
    def create(self, tenant_id: str, subject: str, onboarding_id: str, doc_type: str, digest: str) -> dict:
        with self._lock:
            for job in self._jobs.values():
                if (job["tenant_id"], job["onboarding_application_id"], job["document_sha256"]) == (tenant_id, onboarding_id, digest):
                    return dict(job)
            job = {"job_id": str(uuid.uuid4()), "tenant_id": tenant_id, "subject": subject,
                   "onboarding_application_id": onboarding_id, "document_type": doc_type,
                   "document_sha256": digest, "status": "queued", "fields": {},
                   "requires_human_confirmation": True, "authenticity_verified": False,
                   "contract_version": "1.0.0"}
            self._jobs[job["job_id"]] = job
            return dict(job)
    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            self._jobs[job_id].update(changes)
    def get(self, job_id: str, tenant_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job and secrets.compare_digest(job["tenant_id"], tenant_id) else None
    def confirm(self, job_id: str, tenant_id: str, revision: int, fields: dict) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not secrets.compare_digest(job["tenant_id"], tenant_id):
                return None
            if job.get("confirmation_revision", 0) >= revision:
                raise ValueError("STALE_CONFIRMATION_REVISION")
            job["confirmed_fields"] = dict(fields)
            job["confirmation_revision"] = revision
            job["status"] = "confirmed"
            return dict(job)
def create_app(authenticate: Optional[Authenticator] = None, store: Optional[JobStore] = None, infer=run_local_ocr) -> FastAPI:
    app = FastAPI(title="Xuanjun OCR Gateway", version="1.0.0")
    jobs = store or JobStore()
    # Fail closed: a host application must inject its existing token verifier and tenant identity.
    def principal(auth_header: Optional[str]) -> Principal:
        if not authenticate or not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="AUTHENTICATION_REQUIRED")
        try:
            p = authenticate(auth_header[7:])
        except Exception:
            raise HTTPException(status_code=401, detail="AUTHENTICATION_FAILED")
        if not p.tenant_id or not p.subject or "ocr:use" not in p.permissions:
            raise HTTPException(status_code=403, detail="OCR_PERMISSION_DENIED")
        return p
    @app.post("/api/v1/ocr/jobs", status_code=202)
    async def submit(file: UploadFile = File(...), document_type: str = Form(...),
                     onboarding_application_id: str = Form(...),
                     idempotency_key: str = Header(..., alias="Idempotency-Key"),
                     authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        if document_type not in ALLOWED_HINTS:
            raise HTTPException(status_code=400, detail="UNSUPPORTED_DOCUMENT_TYPE")
        if not onboarding_application_id.strip() or not (16 <= len(idempotency_key) <= 128):
            raise HTTPException(status_code=400, detail="INVALID_REQUEST")
        data = await file.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="IMAGE_SIZE_LIMIT")
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        job = jobs.create(p.tenant_id, p.subject, onboarding_application_id, document_type, digest)
        # Do not retain raw image bytes in the job store. Run local inference synchronously for this prototype.
        jobs.update(job["job_id"], status="processing")
        try:
            result = infer(data, document_type, max_bytes=MAX_BYTES)
            jobs.update(job["job_id"], status="needs_review", fields=result["fields"],
                        warnings=[], engine="RapidOCR", model_version="runtime-configured")
        except Exception as exc:
            code = str(exc) if str(exc).isupper() and len(str(exc)) < 80 else "OCR_INFERENCE_FAILED"
            jobs.update(job["job_id"], status="failed", error_code=code, warnings=[code])
        final = jobs.get(job["job_id"], p.tenant_id)
        return {"job_id": final["job_id"], "status": "queued" if final["status"] == "processing" else final["status"],
                "contract_version": final["contract_version"]}
    @app.get("/api/v1/ocr/jobs/{job_id}")
    def get_job(job_id: str, authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        job = jobs.get(job_id, p.tenant_id)
        if not job:
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        return {k: v for k, v in job.items() if k not in {"tenant_id", "subject", "onboarding_application_id", "document_sha256", "confirmed_fields", "confirmation_revision"}}
    class Confirmation(BaseModel):
        revision: int = Field(ge=1)
        fields: dict[str, str]
    @app.post("/api/v1/ocr/jobs/{job_id}/confirm")
    def confirm(job_id: str, body: Confirmation, authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        try:
            job = jobs.confirm(job_id, p.tenant_id, body.revision, body.fields)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if not job:
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        return {"job_id": job_id, "status": job["status"], "revision": body.revision, "recorded": True}
    app.state.ocr_job_store = jobs
    return app
