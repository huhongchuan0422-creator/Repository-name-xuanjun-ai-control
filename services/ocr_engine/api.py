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
except ImportError:
    from ocr_core import run_local_ocr

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_HINTS = {"business_license", "id_front"}
class Principal(BaseModel):
    subject: str
    tenant_id: str
    permissions: set[str] = Field(default_factory=set)
Authenticator = Callable[[str], Principal]
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
def create_app(authenticate: Optional[Authenticator] = None, store=None, infer=run_local_ocr) -> FastAPI:
    app = FastAPI(title="Xuanjun OCR Gateway", version="1.0.0")
    # Persistence is only activated when an explicit absolute path is configured.
    if store is None:
        db_path = os.environ.get("OCR_SQLITE_PATH", "")
        jobs = SQLiteJobStore(db_path) if db_path else JobStore()
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
        if job["status"] not in {"queued", "failed"}:
            return {"job_id": job["job_id"], "status": job["status"], "contract_version": "1.0.0"}
        jobs.update(job["job_id"], status="processing")
        try:
            result = infer(data, document_type, max_bytes=MAX_BYTES)
            jobs.update(job["job_id"], status="needs_review", fields=result["fields"],
                        warnings=[], engine="RapidOCR", model_version="runtime-configured")
        except Exception as exc:
            code = str(exc) if str(exc).isupper() and len(str(exc)) < 80 else "OCR_INFERENCE_FAILED"
            jobs.update(job["job_id"], status="failed", error_code=code, warnings=[code])
        final = jobs.get(job["job_id"], p.tenant_id)
        return {"job_id": final["job_id"], "status": final["status"], "contract_version": final["contract_version"]}
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
