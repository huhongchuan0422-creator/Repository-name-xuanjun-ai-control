"""Encrypted tenant-scoped SQLite OCR job journal; no images stored.

A deployment must supply an external Fernet key. Job and confirmation payloads are
encrypted at rest. HMAC indexes hide tenant/application/subject values from DB.
Synchronous requests use a transaction claim; interrupted work fails closed.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import sqlite3
import stat
import uuid
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

class SecureSQLiteJobStore:
    def __init__(self, db_path: str, encryption_key: bytes):
        path = Path(db_path)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("OCR_DB_PATH_INVALID")
        if not isinstance(encryption_key, bytes):
            raise ValueError("OCR_ENCRYPTION_KEY_REQUIRED")
        try:
            self.cipher = Fernet(encryption_key)
        except (ValueError, TypeError) as exc:
            raise ValueError("OCR_ENCRYPTION_KEY_INVALID") from exc
        self.signing_key = hashlib.sha256(b"xuanjun-ocr-index-v1:" + encryption_key).digest()
        self.db_path = str(path)
        if not path.parent.exists():
            raise ValueError("OCR_DB_DIRECTORY_NOT_FOUND")
        if path.exists() and (not path.is_file() or (path.stat().st_mode & 0o077)):
            raise ValueError("OCR_DB_PERMISSIONS_UNSAFE")
        fd = os.open(self.db_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ocr_jobs(
                job_id TEXT PRIMARY KEY,
                tenant_key TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                idem_key TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                updated_unix INTEGER NOT NULL DEFAULT (unixepoch()),
                UNIQUE(tenant_key, idem_key)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ocr_tenant ON ocr_jobs(tenant_key)")
            db.execute("CREATE TABLE IF NOT EXISTS ocr_key_check(check_value TEXT NOT NULL)")
            expected = self._index("encryption-key-check-v1")
            row = db.execute("SELECT check_value FROM ocr_key_check LIMIT 1").fetchone()
            if row is None:
                db.execute("INSERT INTO ocr_key_check VALUES(?)", (expected,))
            elif not hmac.compare_digest(row["check_value"], expected):
                raise RuntimeError("OCR_ENCRYPTION_KEY_MISMATCH")
            db.execute("""CREATE TABLE IF NOT EXISTS ocr_audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_key TEXT NOT NULL,
                event TEXT NOT NULL, time_unix INTEGER NOT NULL DEFAULT (unixepoch()))""")


    def recover_interrupted(self):
        """Call only with exclusive lifecycle control, after proving no live OCR workers.

        A second web worker opening the DB must never kill a legitimate claim.
        """
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("SELECT job_id,ciphertext FROM ocr_jobs WHERE state='processing'").fetchall():
                payload = self._open(row["ciphertext"])
                payload["status"] = "failed"
                payload["error_code"] = "OCR_INTERRUPTED"
                db.execute("UPDATE ocr_jobs SET state=?, ciphertext=? WHERE job_id=?",
                           ("failed", self._seal(payload), row["job_id"]))
            db.execute("COMMIT")

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _index(self, value: str) -> str:
        return hmac.new(self.signing_key, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def _seal(self, payload: dict) -> bytes:
        return self.cipher.encrypt(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    def _open(self, data: bytes) -> dict:
        try:
            return json.loads(self.cipher.decrypt(data))
        except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError("OCR_ENCRYPTED_JOB_UNREADABLE") from exc

    def create(self, tenant_id: str, subject: str, onboarding_id: str,
               doc_type: str, digest: str, idempotency_key: str = "") -> dict:
        if not idempotency_key:
            raise ValueError("OCR_IDEMPOTENCY_REQUIRED")
        tenant_key = self._index(tenant_id)
        subject_key = self._index(tenant_id + "/" + subject)
        idem_key = self._index(tenant_id + "/" + idempotency_key)
        payload_hash = self._index("/".join((tenant_id, subject, onboarding_id, doc_type, digest)))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload_hash, ciphertext FROM ocr_jobs WHERE tenant_key=? AND idem_key=?",
                             (tenant_key, idem_key)).fetchone()
            if row:
                if row["payload_hash"] != payload_hash:
                    db.execute("ROLLBACK")
                    raise ValueError("OCR_IDEMPOTENCY_CONFLICT")
                payload = self._open(row["ciphertext"])
                db.execute("COMMIT")
                return payload
            job = {"job_id": str(uuid.uuid4()), "tenant_id": tenant_id, "subject": subject,
                   "onboarding_application_id": onboarding_id, "document_type": doc_type,
                   "document_sha256": digest, "status": "queued", "fields": {},
                   "requires_human_confirmation": True, "authenticity_verified": False,
                   "contract_version": "1.0.0"}
            db.execute("INSERT INTO ocr_jobs(job_id,tenant_key,subject_key,idem_key,payload_hash,state,ciphertext) VALUES(?,?,?,?,?,?,?)",
                       (job["job_id"], tenant_key, subject_key, idem_key, payload_hash, "queued", self._seal(job)))
            db.execute("INSERT INTO ocr_audit(job_key,event) VALUES(?,?)", (self._index(job["job_id"]), "created"))
            db.execute("COMMIT")
            return job

    def get(self, job_id: str, tenant_id: str):
        with self._connect() as db:
            row = db.execute("SELECT ciphertext FROM ocr_jobs WHERE job_id=? AND tenant_key=?",
                             (job_id, self._index(tenant_id))).fetchone()
        return self._open(row["ciphertext"]) if row else None

    def _modify(self, job_id: str, tenant_id: str | None, action):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            query = "SELECT ciphertext,state FROM ocr_jobs WHERE job_id=?"
            args = (job_id,)
            if tenant_id is not None:
                query += " AND tenant_key=?"
                args += (self._index(tenant_id),)
            row = db.execute(query, args).fetchone()
            if not row:
                db.execute("ROLLBACK")
                return None
            job = self._open(row["ciphertext"])
            result = action(job)
            if result is None:
                db.execute("ROLLBACK")
                return None
            db.execute("UPDATE ocr_jobs SET ciphertext=?,state=?,updated_unix=unixepoch() WHERE job_id=?",
                       (self._seal(job), job["status"], job_id))
            db.execute("INSERT INTO ocr_audit(job_key,event) VALUES(?,?)", (self._index(job_id), "updated"))
            db.execute("COMMIT")
            return job

    def claim(self, job_id: str) -> bool:
        def action(job):
            if job["status"] != "queued":
                return None
            job["status"] = "processing"
            return job
        return self._modify(job_id, None, action) is not None

    def update(self, job_id: str, **changes):
        forbidden = {"tenant_id", "subject", "onboarding_application_id", "document_sha256", "job_id",
                     "confirmed_fields", "confirmation_revision", "authenticity_verified"}
        if forbidden.intersection(changes):
            raise ValueError("OCR_IMMUTABLE_FIELD")
        def action(job):
            if job["status"] == "confirmed":
                raise ValueError("OCR_CONFIRMED_IMMUTABLE")
            if "status" in changes and changes["status"] not in {"needs_review", "failed", "processing"}:
                raise ValueError("OCR_INVALID_STATUS")
            job.update(changes)
            return job
        if self._modify(job_id, None, action) is None:
            raise KeyError("OCR_JOB_NOT_FOUND")

    def confirm(self, job_id: str, tenant_id: str, revision: int, fields: dict):
        def action(job):
            if job["status"] not in {"needs_review", "confirmed"}:
                raise ValueError("OCR_JOB_NOT_READY")
            if revision <= job.get("confirmation_revision", 0):
                raise ValueError("STALE_CONFIRMATION_REVISION")
            job["confirmed_fields"] = dict(fields)
            job["confirmation_revision"] = revision
            job["status"] = "confirmed"
            return job
        return self._modify(job_id, tenant_id, action)

    def delete(self, job_id: str, tenant_id: str) -> bool:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("DELETE FROM ocr_jobs WHERE job_id=? AND tenant_key=?",
                                 (job_id, self._index(tenant_id))).rowcount
            if changed:
                db.execute("INSERT INTO ocr_audit(job_key,event) VALUES(?,?)", (self._index(job_id), "deleted"))
            db.execute("COMMIT")
        return changed == 1

    def purge_before(self, cutoff_unix: int) -> int:
        """Retention deletion by last update; never returns sensitive field values."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT job_id FROM ocr_jobs WHERE updated_unix < ?", (cutoff_unix,)).fetchall()
            for row in rows:
                db.execute("INSERT INTO ocr_audit(job_key,event) VALUES(?,?)",
                           (self._index(row["job_id"]), "retention_deleted"))
            db.execute("DELETE FROM ocr_jobs WHERE updated_unix < ?", (cutoff_unix,))
            db.execute("COMMIT")
            return len(rows)
