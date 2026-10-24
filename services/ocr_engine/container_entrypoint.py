"""Fail-closed entrypoint for an isolated OCR preview container.

The trusted integration adapter is supplied externally and is never synthesized here.
"""
import importlib
import os
import sys
from pathlib import Path

from services.ocr_engine.api import Principal, create_app
from services.ocr_engine.startup_selfcheck import check_environment

CALLBACKS = ("authenticate", "authorize_application", "authorize_attachment")

def load_bindings():
    module_name = os.environ.get("OCR_TRUSTED_BINDINGS_MODULE", "")
    integration_path = os.environ.get("OCR_INTEGRATION_PATH", "")
    if not module_name or not integration_path:
        raise RuntimeError("OCR_TRUSTED_BINDINGS_MODULE_AND_PATH_REQUIRED")
    path = Path(integration_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise RuntimeError("OCR_INTEGRATION_PATH_INVALID")
    sys.path.insert(0, str(path))
    module = importlib.import_module(module_name)
    callbacks = {}
    for name in CALLBACKS:
        callback = getattr(module, name, None)
        if not callable(callback):
            raise RuntimeError("OCR_TRUSTED_CALLBACK_MISSING:" + name)
        callbacks[name] = callback
    return callbacks

def main():
    try:
        callbacks = load_bindings()
    except Exception as exc:
        print("OCR_START_HOLD:" + (str(exc) if str(exc).startswith("OCR_") else type(exc).__name__), file=sys.stderr)
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
        result = callbacks["authorize_application"](principal, application_id)
        return result is True

    preflight = check_environment()
    # Only sanitized status/errors are emitted; never print environment values or secrets.
    print("OCR_PREFLIGHT=" + str(preflight.get("ok")) + "; DATABASE=" + str(preflight.get("database")) +
          "; MODEL_STATUS=" + ",".join(str(k) + ":" + str(v) for k, v in sorted(preflight.get("models", {}).items())))
    if not preflight.get("ok"):
        print("OCR_START_HOLD:OFFLINE_PREFLIGHT_FAILED:" + ",".join(preflight.get("errors", [])), file=sys.stderr)
        return 78
    try:
        app = create_app(authenticate=authenticate,
                         authorize_application=authorize_application,
                         authorize_attachment=callbacks["authorize_attachment"])
    except Exception as exc:
        print("OCR_START_HOLD:APP_CONSTRUCTION_FAILED:" + type(exc).__name__, file=sys.stderr)
        return 78

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("OCR_PORT", "8080")),
                workers=1, access_log=False, log_level="info")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
