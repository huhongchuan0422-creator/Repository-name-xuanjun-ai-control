"""SQLite-backed isolated offline contract snapshot journal (no signing/payment).

The caller supplies a *verified* customer/project context. This module does NOT
authenticate users: production HTTP must use trusted customer-center identity
and authorization before calling. It does not change any production database.
Python 3.6 compatible; no model/API or network dependencies.
"""
import hashlib
import hmac
import json
import sqlite3
from contextlib import contextmanager

from single_contract_freeze import ContractHold, freeze, canonical_bytes

class Journal(object):
    def __init__(self, database):
        self.database = database

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    def setup(self):
        with self._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS contract_frozen_candidate (
              project_id TEXT NOT NULL, contract_id TEXT NOT NULL,
              request_id TEXT NOT NULL, candidate_sha TEXT NOT NULL,
              candidate_json BLOB NOT NULL,
              PRIMARY KEY(project_id,contract_id,request_id),
              UNIQUE(project_id,contract_id,candidate_sha))""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS contract_frozen_no_update
              BEFORE UPDATE ON contract_frozen_candidate
              BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS contract_frozen_no_delete
              BEFORE DELETE ON contract_frozen_candidate
              BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END""")

    def submit(self, verified_project_id, verified_customer_id, request_id, snapshot):
        # Never accept arbitrary browser project or customer identifiers as trust.
        if not isinstance(request_id, str) or not request_id or len(request_id)>128:
            raise ContractHold("INVALID_REQUEST_ID")
        candidate=freeze(snapshot)
        scope=candidate["frozen"]["scope"]
        if scope["project_id"] != verified_project_id or scope["verified_customer_id"] != verified_customer_id:
            raise ContractHold("IDENTITY_SCOPE_MISMATCH")
        payload=canonical_bytes(candidate)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("""SELECT candidate_json FROM contract_frozen_candidate
                     WHERE project_id=? AND contract_id=? AND request_id=?""",
                     (verified_project_id,scope["contract_id"],request_id)).fetchone()
                if row is not None:
                    if bytes(row[0]) != payload:
                        raise ContractHold("IDEMPOTENCY_CONFLICT")
                    db.execute("COMMIT")
                    return candidate
                db.execute("""INSERT INTO contract_frozen_candidate
                    (project_id,contract_id,request_id,candidate_sha,candidate_json)
                    VALUES (?,?,?,?,?)""",
                    (verified_project_id,scope["contract_id"],request_id,
                     candidate["contract_document_hash"],sqlite3.Binary(payload)))
                db.execute("COMMIT")
            except sqlite3.IntegrityError:
                db.execute("ROLLBACK")
                raise ContractHold("DUPLICATE_CONTRACT_VERSION")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return candidate

    def read(self, verified_project_id, verified_customer_id, contract_id, request_id):
        with self._connection() as db:
            row=db.execute("""SELECT candidate_json, candidate_sha FROM contract_frozen_candidate
                WHERE project_id=? AND contract_id=? AND request_id=?""",
                (verified_project_id,contract_id,request_id)).fetchone()
        if row is None:
            raise ContractHold("CANDIDATE_NOT_FOUND")
        try:
            obj=json.loads(bytes(row[0]).decode("utf-8"))
            scope=obj["frozen"]["scope"]
            current=freeze_from_stored(obj)
            if not hmac.compare_digest(current, row[1]) or not hmac.compare_digest(current, obj.get("contract_document_hash", "")):
                raise ContractHold("CORRUPT_CANDIDATE_DIGEST")
            if scope["project_id"] != verified_project_id or scope["verified_customer_id"] != verified_customer_id or scope["contract_id"] != contract_id:
                raise ContractHold("CANDIDATE_ACCESS_DENIED")
            if obj.get("status") != "UNSIGNED_CANDIDATE_ONLY" or any(obj.get(k) != "HOLD" for k in ("contract_sign","payment","procurement","development_start")):
                raise ContractHold("CORRUPT_CANDIDATE_STATUS")
        except ContractHold:
            raise
        except (ValueError, KeyError, TypeError):
            raise ContractHold("CORRUPT_CANDIDATE")
        return obj

def freeze_from_stored(obj):
    """Verify content digest of the stored frozen object, not the wrapper."""
    return hashlib.sha256(canonical_bytes(obj["frozen"])).hexdigest()
