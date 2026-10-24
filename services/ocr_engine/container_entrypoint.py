"""Fail-closed entrypoint for an isolated OCR preview container.

The trusted integration adapter is externally supplied and never synthesized here.
"""
import hashlib
import hmac
import importlib.util
import inspect
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path

from services.ocr_engine.api import Principal, create_app
from services.ocr_engine.startup_selfcheck import check_environment

CALLBACKS = {
    "authenticate": 1,
    "authorize_application": 2,
    "authorize_attachment": 6,
}
REQUIRED_TABLES = {
    "ocr_jobs", "ocr_confirm_idempotency", "ocr_rate_window",
    "ocr_audit", "ocr_audit_details", "ocr_key_check",
}

EXPECTED_COLUMNS = {
    "ocr_jobs": [("job_id","TEXT",0,1,None),("tenant_key","TEXT",1,0,None),("subject_key","TEXT",1,0,None),("idem_key","TEXT",1,0,None),("payload_hash","TEXT",1,0,None),("state","TEXT",1,0,None),("ciphertext","BLOB",1,0,None),("updated_unix","INTEGER",1,0,"unixepoch()")],
    "ocr_confirm_idempotency": [("tenant_key","TEXT",1,1,None),("job_id","TEXT",1,2,None),("idem_key","TEXT",1,3,None),("payload_hash","TEXT",1,0,None),("response_ciphertext","BLOB",1,0,None)],
    "ocr_rate_window": [("tenant_key","TEXT",1,1,None),("window_start","INTEGER",1,2,None),("hits","INTEGER",1,0,None)],
    "ocr_audit": [("id","INTEGER",0,1,None),("job_key","TEXT",1,0,None),("event","TEXT",1,0,None),("time_unix","INTEGER",1,0,"unixepoch()")],
    "ocr_audit_details": [("audit_id","TEXT",0,1,None),("tenant_key","TEXT",1,0,None),("job_id","TEXT",1,0,None),("event_type","TEXT",1,0,None),("event_ciphertext","BLOB",1,0,None),("created_unix","INTEGER",1,0,"unixepoch()")],
    "ocr_key_check": [("check_value","TEXT",1,0,None)],
}
REQUIRED_INDEXES = {
    "idx_ocr_tenant": ("ocr_jobs", False, ("tenant_key",)),
    "idx_ocr_audit_job": ("ocr_audit_details", False, ("tenant_key","job_id")),
}

def _norm_default(value):
    return None if value is None else str(value).strip().strip("()").lower()

def _index_columns(db, index_name):
    return tuple(row[2] for row in db.execute("PRAGMA index_info(" + json.dumps(index_name) + ")"))

def check_database_schema(db):
    try:
        table_sql = {r[0]: (r[1] or "") for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES.issubset(table_sql):
            return False, "OCR_DATABASE_SCHEMA_NOT_READY"
        all_indexes = {}
        for table, expected in EXPECTED_COLUMNS.items():
            rows = db.execute("PRAGMA table_info(" + table + ")").fetchall()
            actual = [(r[1],str(r[2]).upper(),int(r[3]),int(r[5]),_norm_default(r[4])) for r in rows]
            wanted = [(n,t,nn,pk,_norm_default(d)) for n,t,nn,pk,d in expected]
            if actual != wanted:
                return False, "OCR_DATABASE_COLUMN_CONTRACT_MISMATCH:" + table
            for row in db.execute("PRAGMA index_list(" + table + ")").fetchall():
                all_indexes[row[1]] = (table,bool(row[2]),_index_columns(db,row[1]))
        if "AUTOINCREMENT" not in table_sql["ocr_audit"].upper():
            return False, "OCR_DATABASE_AUDIT_PK_CONSTRAINT_MISMATCH"
        if "UNIQUE(TENANT_KEY,IDEM_KEY)" not in table_sql["ocr_jobs"].replace(" ","").upper():
            return False, "OCR_DATABASE_JOB_UNIQUE_CONSTRAINT_MISSING"
        for name, expected in REQUIRED_INDEXES.items():
            if all_indexes.get(name) != expected:
                return False, "OCR_DATABASE_REQUIRED_INDEX_MISMATCH:" + name
        unique = {(table,cols) for table,is_unique,cols in all_indexes.values() if is_unique}
        required = {("ocr_jobs",("tenant_key","idem_key")),("ocr_confirm_idempotency",("tenant_key","job_id","idem_key")),("ocr_rate_window",("tenant_key","window_start")),("ocr_audit_details",("audit_id",))}
        if not required.issubset(unique):
            return False, "OCR_DATABASE_UNIQUE_CONSTRAINTS_MISMATCH"
        return True, "OCR_DATABASE_SCHEMA_VERIFIED"
    except (sqlite3.Error, TypeError, ValueError, KeyError):
        return False, "OCR_DATABASE_SCHEMA_READ_FAILED"

def check_existing_database(db_path, key_bytes):
    path = Path(db_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        return False, "OCR_DATABASE_NOT_READY"
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            return False, "OCR_DATABASE_PERMISSIONS_UNSAFE"
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                return False, "OCR_DATABASE_INTEGRITY_CHECK_FAILED"
            schema_ok, schema_reason = check_database_schema(db)
            if not schema_ok:
                return False, schema_reason
            rows = db.execute("SELECT check_value FROM ocr_key_check").fetchall()
            signing_key = hashlib.sha256(b"xuanjun-ocr-index-v1:" + key_bytes).digest()
            expected = hmac.new(signing_key, b"encryption-key-check-v1", hashlib.sha256).hexdigest()
            if len(rows) != 1 or not isinstance(rows[0][0], str) or not hmac.compare_digest(rows[0][0], expected):
                return False, "OCR_DATABASE_KEY_BINDING_MISMATCH"
            return True, "EXISTING_PROTECTED_DATABASE_READY"
        finally:
            db.close()
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return False, "OCR_DATABASE_READ_ONLY_CHECK_FAILED"

def _decode_mount_path(value):
    return value.replace("\\040", " ").replace("\\011", chr(9)).replace("\\012", chr(10)).replace("\\134", chr(92))

def readonly_mount_for(path, mountinfo_text=None):
    try:
        target = Path(path).resolve(strict=True)
        text = Path("/proc/self/mountinfo").read_text(encoding="utf-8") if mountinfo_text is None else mountinfo_text
        matches = []
        for line in text.splitlines():
            fields = line.split()
            if "-" not in fields or len(fields) < 7:
                continue
            sep = fields.index("-")
            if sep < 6 or sep + 3 >= len(fields):
                continue
            mountpoint = Path(_decode_mount_path(fields[4]))
            try:
                target.relative_to(mountpoint)
            except ValueError:
                continue
            options = set(fields[5].split(",")) | set(fields[sep+3].split(","))
            matches.append((len(str(mountpoint)), "ro" in options))
        return max(matches, key=lambda item:item[0])[1] if matches else False
    except (OSError, ValueError, IndexError):
        return False

def _safe_root_owned(path, is_dir):
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or (is_dir and not stat.S_ISDIR(info.st_mode)) or (not is_dir and not stat.S_ISREG(info.st_mode)):
            return False
        return info.st_uid == 0 and not (info.st_mode & 0o022)
    except OSError:
        return False

def load_bindings(environ=None, mountinfo_text=None, mount_checker=None):
    env = os.environ if environ is None else environ
    module_name = env.get("OCR_TRUSTED_BINDINGS_MODULE", "")
    integration_path = env.get("OCR_INTEGRATION_PATH", "")
    if not module_name or not module_name.isidentifier() or not integration_path:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_MODULE_AND_PATH_REQUIRED")
    supplied_root = Path(integration_path)
    if not supplied_root.is_absolute() or ".." in supplied_root.parts:
        raise RuntimeError("OCR_INTEGRATION_PATH_INVALID")
    # Reject symlinks in every path component, not only at the leaf.
    current = Path(supplied_root.anchor)
    for part in supplied_root.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError:
            raise RuntimeError("OCR_INTEGRATION_PATH_INVALID")
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError("OCR_INTEGRATION_PATH_SYMLINK")
    if not supplied_root.is_dir():
        raise RuntimeError("OCR_INTEGRATION_PATH_INVALID")
    root = supplied_root.resolve(strict=True)
    if not _safe_root_owned(root, True):
        raise RuntimeError("OCR_INTEGRATION_ROOT_OWNER_OR_MODE_UNSAFE")
    checker = readonly_mount_for if mount_checker is None else mount_checker
    if not checker(root, mountinfo_text):
        raise RuntimeError("OCR_INTEGRATION_ROOT_MOUNT_NOT_READ_ONLY")
    if module_name in sys.modules:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_MODULE_ALREADY_LOADED")
    candidate = root / (module_name + ".py")
    if candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SOURCE_NOT_REGULAR")
    if not _safe_root_owned(candidate, False):
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SOURCE_OWNER_OR_MODE_UNSAFE")
    if not checker(candidate, mountinfo_text):
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SOURCE_MOUNT_NOT_READ_ONLY")
    origin = candidate.resolve(strict=True)
    try:
        origin.relative_to(root)
    except ValueError:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_ORIGIN_ESCAPE")
    spec = importlib.util.spec_from_file_location(module_name, str(origin))
    if spec is None or spec.loader is None or spec.origin is None:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SPEC_INVALID")
    spec_origin = Path(spec.origin)
    if spec_origin.is_symlink() or spec_origin.resolve(strict=True) != origin:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SPEC_ORIGIN_MISMATCH")
    try:
        spec_origin.resolve(strict=True).relative_to(root)
    except ValueError:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SPEC_ORIGIN_ESCAPE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        module_origin = Path(getattr(module, "__file__", "")).resolve(strict=True)
        module_origin.relative_to(root)
        if module_origin != origin:
            raise RuntimeError("OCR_TRUSTED_BINDINGS_IMPORTED_ORIGIN_MISMATCH")
        callbacks = {}
        for name, arity in CALLBACKS.items():
            callback = getattr(module, name, None)
            if not callable(callback):
                raise RuntimeError("OCR_TRUSTED_CALLBACK_MISSING:" + name)
            try:
                inspect.signature(callback).bind(*([object()] * arity))
            except (TypeError, ValueError):
                raise RuntimeError("OCR_TRUSTED_CALLBACK_SIGNATURE_INVALID:" + name)
            callbacks[name] = callback
        return callbacks
    except Exception:
        sys.modules.pop(module_name, None)
        raise

def main():
    # Preflight is read-only. An absent DB must never be allowed to reach create_app(),
    # because SecureSQLiteJobStore creates a new DB and schema during construction.
    preflight = check_environment()
    print("OCR_PREFLIGHT=" + str(preflight.get("ok")) + "; DATABASE=" + str(preflight.get("database")) +
          "; MODEL_STATUS=" + ",".join(str(k) + ":" + str(v) for k, v in sorted(preflight.get("models", {}).items())))
    if not preflight.get("ok"):
        print("OCR_START_HOLD:OFFLINE_PREFLIGHT_FAILED:" + ",".join(preflight.get("errors", [])), file=sys.stderr)
        return 78
    if preflight.get("database") != "EXISTING_PROTECTED_FILE_VERIFIED":
        print("OCR_START_HOLD:EXISTING_DATABASE_REQUIRED", file=sys.stderr)
        return 78
    db_path = os.environ.get("OCR_SQLITE_PATH", "")
    raw_key = os.environ.get("OCR_ENCRYPTION_KEY", "")
    try:
        key_bytes = raw_key.encode("ascii")
    except UnicodeError:
        print("OCR_START_HOLD:OCR_ENCRYPTION_KEY_INVALID", file=sys.stderr)
        return 78
    ready, reason = check_existing_database(db_path, key_bytes)
    if not ready:
        print("OCR_START_HOLD:" + reason, file=sys.stderr)
        return 78
    try:
        callbacks = load_bindings()
    except Exception as exc:
        code = str(exc) if str(exc).startswith("OCR_") else type(exc).__name__
        print("OCR_START_HOLD:" + code, file=sys.stderr)
        return 78

    def authenticate(token):
        principal = callbacks["authenticate"](token)
        if not isinstance(principal, Principal):
            raise ValueError("TRUSTED_AUTHENTICATOR_MUST_RETURN_OCR_PRINCIPAL")
        if not isinstance(principal.subject, str) or not principal.subject:
            raise ValueError("TRUSTED_PRINCIPAL_SUBJECT_INVALID")
        if not isinstance(principal.tenant_id, str) or not principal.tenant_id:
            raise ValueError("TRUSTED_PRINCIPAL_TENANT_INVALID")
        if not isinstance(principal.permissions, (set, frozenset)):
            raise ValueError("TRUSTED_PRINCIPAL_PERMISSIONS_INVALID")
        return principal

    def authorize_application(principal, application_id):
        return callbacks["authorize_application"](principal, application_id) is True

    try:
        app = create_app(authenticate=authenticate,
                         authorize_application=authorize_application,
                         authorize_attachment=callbacks["authorize_attachment"])
    except Exception as exc:
        print("OCR_START_HOLD:APP_CONSTRUCTION_FAILED:" + type(exc).__name__, file=sys.stderr)
        return 78
    import uvicorn
    try:
        port = int(os.environ.get("OCR_PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("OCR_START_HOLD:OCR_PORT_INVALID", file=sys.stderr)
        return 78
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1, access_log=False, log_level="info")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
