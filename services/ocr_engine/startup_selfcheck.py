"""Read-only OCR deployment preflight. Never creates DBs/keys, downloads models, or enables a service."""
from __future__ import annotations
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from cryptography.fernet import Fernet

MODEL_ENV = {"det": "OCR_DET_MODEL_PATH", "rec": "OCR_REC_MODEL_PATH", "cls": "OCR_CLS_MODEL_PATH"}
SHA_ENV = "OCR_MODEL_SHA256"
DB_ENV = "OCR_SQLITE_PATH"
KEY_ENV = "OCR_ENCRYPTION_KEY"

def check_environment(environ=None, manifest_path=None):
    env = os.environ if environ is None else environ
    errors = []
    required = [DB_ENV, KEY_ENV, *MODEL_ENV.values(), SHA_ENV]
    missing = [name for name in required if not env.get(name)]
    if missing:
        errors.append("MISSING_REQUIRED_SETTINGS:" + ",".join(missing))
        return {"ok": False, "errors": errors, "models": {}, "database": "NOT_CHECKED", "key": "NOT_CHECKED"}

    try:
        Fernet(env[KEY_ENV].encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        errors.append("OCR_ENCRYPTION_KEY_INVALID")
    db_path = Path(env[DB_ENV])
    if not db_path.is_absolute() or db_path.is_symlink():
        errors.append("OCR_DB_PATH_INVALID")
        db_state = "INVALID"
    elif not db_path.parent.is_dir():
        errors.append("OCR_DB_DIRECTORY_NOT_FOUND")
        db_state = "PARENT_MISSING"
    elif db_path.exists() and (not db_path.is_file() or (db_path.stat().st_mode & 0o077)):
        errors.append("OCR_DB_PERMISSIONS_UNSAFE")
        db_state = "UNSAFE_EXISTING_FILE"
    else:
        # Read-only check: do not create or open SQLite and do not create parent directories.
        db_state = "EXISTING_PROTECTED_FILE" if db_path.exists() else "READY_TO_CREATE_BY_SEPARATE_APPROVED_DEPLOYMENT"

    try:
        provided = json.loads(env[SHA_ENV])
    except (ValueError, TypeError):
        provided = None
    if not isinstance(provided, dict) or set(provided) != set(MODEL_ENV):
        errors.append("OCR_MODEL_SHA256_INVALID")
        provided = {}

    if manifest_path is None:
        manifest_path = Path(__file__).with_name("model_manifest.json")
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        expected = {name: item["sha256"] for name, item in manifest["model_set"]["files"].items()}
    except (OSError, ValueError, KeyError, TypeError):
        expected = {}
        errors.append("OCR_MODEL_MANIFEST_UNAVAILABLE")

    models = {}
    for name, env_name in MODEL_ENV.items():
        raw = env.get(env_name, "")
        expected_sha = expected.get(name)
        supplied_sha = provided.get(name)
        if not isinstance(expected_sha, str) or supplied_sha != expected_sha:
            errors.append("OCR_MODEL_PIN_MISMATCH:" + name)
            models[name] = "PIN_MISMATCH"
            continue
        if not isinstance(raw, str) or not Path(raw).is_absolute():
            errors.append("OCR_MODEL_PATH_INVALID:" + name)
            models[name] = "PATH_INVALID"
            continue
        path = Path(raw)
        if path.is_symlink() or not path.is_file():
            errors.append("OCR_MODEL_FILE_UNAVAILABLE:" + name)
            models[name] = "FILE_UNAVAILABLE"
            continue
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            errors.append("OCR_MODEL_FILE_UNREADABLE:" + name)
            models[name] = "UNREADABLE"
            continue
        if digest.hexdigest() != expected_sha:
            errors.append("OCR_MODEL_SHA256_MISMATCH:" + name)
            models[name] = "SHA_MISMATCH"
        else:
            models[name] = "SHA256_VERIFIED"
    return {"ok": not errors, "errors": errors, "models": models, "database": db_state,
            "key": "FORMAT_VALID" if not any(x.startswith("OCR_ENCRYPTION_KEY_") for x in errors) else "INVALID",
            "production_callbacks": "NOT_CONNECTED", "production_start": "HOLD"}

def main():
    mode = sys.argv[1:] or ["--offline-assets-only"]
    if mode not in (["--offline-assets-only"], ["--production-readiness"]):
        print("Usage: startup_selfcheck.py [--offline-assets-only|--production-readiness]")
        return 64
    result = check_environment()
    # Never print environment values, key bytes, or document data.
    print(json.dumps(result, sort_keys=True))
    if not result["ok"]:
        return 2
    if mode == ["--production-readiness"]:
        print("PRODUCTION_START=HOLD: trusted identity/application/attachment callbacks are not connected")
        return 3
    print("OFFLINE_ASSET_PREFLIGHT=PASS; this does not authorize or start a service")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
