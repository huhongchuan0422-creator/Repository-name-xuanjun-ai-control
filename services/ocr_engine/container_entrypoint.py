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

def check_existing_database(db_path, key_bytes):
    """Read-only check of an existing protected DB; never creates or migrates it."""
    path = Path(db_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        return False, "OCR_DATABASE_NOT_READY"
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            return False, "OCR_DATABASE_PERMISSIONS_UNSAFE"
        uri = path.as_uri() + "?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                return False, "OCR_DATABASE_INTEGRITY_CHECK_FAILED"
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES.issubset(tables):
                return False, "OCR_DATABASE_SCHEMA_NOT_READY"
            rows = db.execute("SELECT check_value FROM ocr_key_check").fetchall()
            signing_key = hashlib.sha256(b"xuanjun-ocr-index-v1:" + key_bytes).digest()
            expected = hmac.new(signing_key, b"encryption-key-check-v1", hashlib.sha256).hexdigest()
            # The store records this derived key check as an HMAC-style opaque digest.
            if len(rows) != 1 or not isinstance(rows[0][0], str) or not hmac.compare_digest(rows[0][0], expected):
                return False, "OCR_DATABASE_KEY_BINDING_MISMATCH"
            return True, "EXISTING_PROTECTED_DATABASE_READY"
        finally:
            db.close()
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return False, "OCR_DATABASE_READ_ONLY_CHECK_FAILED"

def load_bindings(environ=None):
    env = os.environ if environ is None else environ
    module_name = env.get("OCR_TRUSTED_BINDINGS_MODULE", "")
    integration_path = env.get("OCR_INTEGRATION_PATH", "")
    if not module_name or not module_name.isidentifier() or not integration_path:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_MODULE_AND_PATH_REQUIRED")
    root = Path(integration_path)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RuntimeError("OCR_INTEGRATION_PATH_INVALID")
    root = root.resolve(strict=True)
    if module_name in sys.modules:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_MODULE_ALREADY_LOADED")
    candidate = root / (module_name + ".py")
    if candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError("OCR_TRUSTED_BINDINGS_SOURCE_NOT_REGULAR")
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
