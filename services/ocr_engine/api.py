"""Local OCR HTTP API prototype. Auth is injected; default app denies every request."""
from __future__ import annotations
import json
import os
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
try:
    from .ocr_core import run_local_ocr
    from .secure_store import SecureSQLiteJobStore
except ImportError:
    from ocr_core import run_local_ocr
    from secure_store import SecureSQLiteJobStore

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_HINTS = {"business_license", "id_front"}
CONFIRM_KEYS = {
    "business_license": {"company_name", "credit_code", "legal_representative", "registered_address", "business_scope"},
    "id_front": {"id_name", "id_number", "registered_address"},
}
class Principal(BaseModel):
    subject: str
    tenant_id: str
    permissions: set[str] = Field(default_factory=set)
Authenticator = Callable[[str], Principal]
class Confirmation(BaseModel):
    revision: int = Field(ge=1)
    fields: dict[str, str]
    # Echo the exact versions shown to the human reviewer; these are compared to stored
    # and freshly resolved authoritative values, never treated as proof by themselves.
    application_revision: str | int
    provider_version: str | int | None = None
class JobStore:
    """In-memory test adapter. Never use as production persistence."""
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
class SQLiteJobStore:
    """Durable local job metadata store; deploy with a protected path, encrypted volume and backup/retention policy."""
    def __init__(self, db_path: str):
        if not db_path or not Path(db_path).is_absolute():
            raise ValueError("OCR_SQLITE_PATH_MUST_BE_ABSOLUTE")
        self.db_path = db_path
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ocr_jobs (
                job_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, subject TEXT NOT NULL,
                onboarding_application_id TEXT NOT NULL, document_type TEXT NOT NULL,
                document_sha256 TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
                UNIQUE(tenant_id, onboarding_application_id, document_sha256))""")
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
    def create(self, tenant_id: str, subject: str, onboarding_id: str, doc_type: str, digest: str) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT payload_json FROM ocr_jobs WHERE tenant_id=? AND onboarding_application_id=? AND document_sha256=?",
                             (tenant_id, onboarding_id, digest)).fetchone()
            if row:
                return json.loads(row["payload_json"])
            job = {"job_id": str(uuid.uuid4()), "tenant_id": tenant_id, "subject": subject,
                   "onboarding_application_id": onboarding_id, "document_type": doc_type,
                   "document_sha256": digest, "status": "queued", "fields": {},
                   "requires_human_confirmation": True, "authenticity_verified": False,
                   "contract_version": "1.0.0"}
            db.execute("INSERT INTO ocr_jobs VALUES(?,?,?,?,?,?,?,?)",
                       (job["job_id"], tenant_id, subject, onboarding_id, doc_type, digest, job["status"], json.dumps(job)))
            return job
    def update(self, job_id: str, **changes) -> None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT payload_json FROM ocr_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError("OCR_JOB_NOT_FOUND")
            job = json.loads(row["payload_json"]); job.update(changes)
            db.execute("UPDATE ocr_jobs SET status=?, payload_json=? WHERE job_id=?",
                       (job["status"], json.dumps(job), job_id))
    def get(self, job_id: str, tenant_id: str) -> Optional[dict]:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM ocr_jobs WHERE job_id=? AND tenant_id=?", (job_id, tenant_id)).fetchone()
            return json.loads(row["payload_json"]) if row else None
    def confirm(self, job_id: str, tenant_id: str, revision: int, fields: dict) -> Optional[dict]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT payload_json FROM ocr_jobs WHERE job_id=? AND tenant_id=?", (job_id, tenant_id)).fetchone()
            if not row:
                return None
            job = json.loads(row["payload_json"])
            if job.get("confirmation_revision", 0) >= revision:
                raise ValueError("STALE_CONFIRMATION_REVISION")
            job["confirmed_fields"] = dict(fields); job["confirmation_revision"] = revision; job["status"] = "confirmed"
            db.execute("UPDATE ocr_jobs SET status=?, payload_json=? WHERE job_id=? AND tenant_id=?",
                       (job["status"], json.dumps(job), job_id, tenant_id))
            return job
def _valid_revision(value):
    return (not isinstance(value, bool) and isinstance(value, (str, int)) and
            str(value).strip() != "" and str(value) == str(value).strip() and
            not (isinstance(value, int) and value < 0) and
            (not isinstance(value, str) or __import__("re").fullmatch(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){0,3}", value) is not None))

def _valid_provider_version(value):
    return _valid_revision(value)

def create_app(authenticate: Optional[Authenticator] = None, store=None, infer=run_local_ocr, authorize_application=None, authorize_attachment=None) -> FastAPI:
    app = FastAPI(title="Xuanjun OCR Gateway", version="1.0.0")
    # Persistence is only activated when an explicit absolute path is configured.
    if store is None:
        db_path = os.environ.get("OCR_SQLITE_PATH", "")
        if not db_path:
            raise RuntimeError("OCR_SQLITE_PATH_REQUIRED")
        raw_key = os.environ.get("OCR_ENCRYPTION_KEY", "")
        if not raw_key:
            raise RuntimeError("OCR_ENCRYPTION_KEY_REQUIRED")
        jobs = SecureSQLiteJobStore(db_path, raw_key.encode("ascii"))
    else:
        jobs = store
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
                     onboarding_application_id: str = Form(...), attachment_id: str = Form(...),
                     idempotency_key: str = Header(..., alias="Idempotency-Key"),
                     authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        if document_type not in ALLOWED_HINTS:
            raise HTTPException(status_code=400, detail="UNSUPPORTED_DOCUMENT_TYPE")
        if not onboarding_application_id.strip() or not (16 <= len(idempotency_key) <= 128):
            raise HTTPException(status_code=400, detail="INVALID_REQUEST")
        if isinstance(jobs, SecureSQLiteJobStore) and not jobs.check_rate(p.tenant_id):
            raise HTTPException(status_code=429, detail="OCR_TENANT_RATE_LIMIT")
        data = await file.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="IMAGE_SIZE_LIMIT")
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        if authorize_application is None or not authorize_application(p, onboarding_application_id):
            raise HTTPException(status_code=403, detail="APPLICATION_OWNERSHIP_UNVERIFIED")
        # A trusted attachment resolver must compare the submitted bytes with the authorized
        # server-side object. A boolean "ID is allowed" callback is insufficient.
        try:
            binding = (authorize_attachment(p, onboarding_application_id, attachment_id, digest, document_type, None)
                       if authorize_attachment is not None and attachment_id.strip() else None)
        except Exception:
            binding = None
        if (not isinstance(binding, dict) or binding.get("authorized") is not True or
                binding.get("content_sha256") != digest or binding.get("document_type") != document_type or
                not _valid_revision(binding.get("application_revision")) or
                ("provider_version" in binding and binding.get("provider_version") is not None and not _valid_provider_version(binding.get("provider_version")))):
            raise HTTPException(status_code=403, detail="ATTACHMENT_CONTENT_BINDING_UNVERIFIED")
        application_revision = str(binding["application_revision"])
        provider_version = binding.get("provider_version")
        if not isinstance(jobs, SecureSQLiteJobStore):
            raise HTTPException(status_code=501, detail="OCR_REQUIRES_SECURE_DURABLE_STORE")
        try:
            job = jobs.create(p.tenant_id, p.subject, onboarding_application_id, document_type, digest, idempotency_key, attachment_id, application_revision, provider_version)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if job["document_type"] != document_type:
            raise HTTPException(status_code=409, detail="DOCUMENT_TYPE_CONFLICT")
        if job["status"] != "queued":
            return {"job_id": job["job_id"], "status": job["status"], "contract_version": "1.0.0"}
        if isinstance(jobs, SecureSQLiteJobStore):
            if not jobs.claim(job["job_id"]):
                raise HTTPException(status_code=409, detail="OCR_JOB_ALREADY_CLAIMED")
        else:
            jobs.update(job["job_id"], status="processing")
        try:
            result = infer(data, document_type, max_bytes=MAX_BYTES)
            jobs.update(job["job_id"], status="needs_review", fields=result["fields"],
                        warnings=[], engine="RapidOCR", model_version="runtime-configured")
        except Exception as exc:
            code = "OCR_INFERENCE_FAILED"
            jobs.update(job["job_id"], status="failed", error_code=code, warnings=[code])
        final = jobs.get(job["job_id"], p.tenant_id)
        return {"job_id": final["job_id"], "status": final["status"], "contract_version": final["contract_version"]}
    def reauthorize_existing_job(p: Principal, job: dict) -> None:
        if authorize_application is None or not authorize_application(p, job["onboarding_application_id"]):
            raise HTTPException(status_code=403, detail="APPLICATION_AUTHORIZATION_REVOKED")
        # Old records without a trusted application revision fail closed; never invent revision 0.
        expected_revision = job.get("application_revision")
        if not expected_revision or not job.get("attachment_id") or not job.get("document_type"):
            raise HTTPException(status_code=403, detail="ATTACHMENT_BINDING_METADATA_MISSING")
        try:
            binding = (authorize_attachment(p, job["onboarding_application_id"], job["attachment_id"],
                                            job["document_sha256"], job["document_type"], expected_revision)
                       if authorize_attachment is not None else None)
        except Exception:
            binding = None
        if (not isinstance(binding, dict) or binding.get("authorized") is not True or
                binding.get("content_sha256") != job["document_sha256"] or
                binding.get("document_type") != job["document_type"] or
                str(binding.get("application_revision", "")) != str(expected_revision) or
                (job.get("provider_version") is not None and binding.get("provider_version") != job.get("provider_version"))):
            raise HTTPException(status_code=403, detail="ATTACHMENT_AUTHORIZATION_REVOKED")

    @app.get("/api/v1/ocr/jobs/{job_id}")
    def get_job(job_id: str, authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        job = jobs.get(job_id, p.tenant_id)
        if not job or (job["subject"] != p.subject and "ocr:admin" not in p.permissions):
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        reauthorize_existing_job(p, job)
        response = {k: v for k, v in job.items() if k not in {"tenant_id", "subject", "onboarding_application_id", "attachment_id", "document_sha256"}}
        response["provider_version"] = job.get("provider_version")
        response["shared_writeback_eligible"] = bool(job.get("provider_version") is not None and job.get("confirmed_binding"))
        return response
    @app.post("/api/v1/ocr/jobs/{job_id}/confirm")
    def confirm(job_id: str, body: Confirmation, idempotency_key: str = Header(..., alias="Idempotency-Key"), authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        existing = jobs.get(job_id, p.tenant_id)
        if not existing or (existing["subject"] != p.subject and "ocr:admin" not in p.permissions):
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        reauthorize_existing_job(p, existing)
        if existing["status"] not in {"needs_review", "confirmed"}:
            raise HTTPException(status_code=409, detail="JOB_NOT_READY_FOR_CONFIRMATION")
        if (not body.fields or len(body.fields) > 12 or
                not set(body.fields).issubset(CONFIRM_KEYS[existing["document_type"]]) or
                any(len(value) > (2048 if key == "business_scope" else 256)
                    for key, value in body.fields.items())):
            raise HTTPException(status_code=400, detail="OCR_CONFIRM_FIELDS_INVALID")
        if not (16 <= len(idempotency_key) <= 128):
            raise HTTPException(status_code=400, detail="INVALID_IDEMPOTENCY_KEY")
        if (not _valid_revision(body.application_revision) or
                (body.provider_version is not None and not _valid_provider_version(body.provider_version))):
            raise HTTPException(status_code=400, detail="OCR_CONFIRM_BINDING_VERSION_INVALID")
        if str(body.application_revision) != str(existing.get("application_revision")):
            raise HTTPException(status_code=409, detail="OCR_APPLICATION_REVISION_CONFLICT")
        if body.provider_version != existing.get("provider_version"):
            raise HTTPException(status_code=409, detail="OCR_PROVIDER_VERSION_CONFLICT")
        try:
            if isinstance(jobs, SecureSQLiteJobStore):
                job = jobs.confirm(job_id, p.tenant_id, body.revision, body.fields, idempotency_key,
                                   body.application_revision, body.provider_version)
            else:
                job = jobs.confirm(job_id, p.tenant_id, body.revision, body.fields)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if not job:
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        return {"job_id": job_id, "status": job["status"], "revision": job["confirmation_revision"],
                "confirmed_fields": job["confirmed_fields"], "confirmed_binding": job.get("confirmed_binding"),
                "application_revision": job.get("application_revision"),
                "provider_version": job.get("provider_version"),
                "shared_writeback_eligible": bool(job.get("provider_version") is not None and job.get("confirmed_binding")),
                "recorded": True}
    @app.delete("/api/v1/ocr/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str, authorization: Optional[str] = Header(None)):
        p = principal(authorization)
        job = jobs.get(job_id, p.tenant_id)
        if not job or (job["subject"] != p.subject and "ocr:admin" not in p.permissions):
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        reauthorize_existing_job(p, job)
        if not isinstance(jobs, SecureSQLiteJobStore):
            raise HTTPException(status_code=501, detail="OCR_DELETE_REQUIRES_DURABLE_STORE")
        if not jobs.delete(job_id, p.tenant_id):
            raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
        return None
    app.state.ocr_job_store = jobs
    return app
