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
    if not db_path.is_absolute():
        errors.append("OCR_DB_PATH_INVALID")
        db_state = "INVALID"
    else:
        # Inspect the lexical path without resolving through symlinks. This is read-only.
        chain = list(reversed(db_path.parents)) + [db_path]
        chain_ok = True
        for index, component in enumerate(chain):
            try:
                info = component.lstat()
            except FileNotFoundError:
                # Missing final DB file is acceptable for offline preparation, but every
                # directory in its parent chain must already exist.
                if component == db_path:
                    continue
                errors.append("OCR_DB_PARENT_CHAIN_MISSING")
                chain_ok = False
                break
            except OSError:
                errors.append("OCR_DB_PATH_UNREADABLE")
                chain_ok = False
                break
            if stat.S_ISLNK(info.st_mode):
                errors.append("OCR_DB_PATH_SYMLINK")
                chain_ok = False
                break
            if component != db_path:
                if not stat.S_ISDIR(info.st_mode):
                    errors.append("OCR_DB_PARENT_NOT_DIRECTORY")
                    chain_ok = False
                    break
                # Sticky world-writable ancestors such as /tmp are allowed for isolated
                # test sandboxes; the actual DB parent and all non-sticky ancestors must
                # not be group/world writable.
                writable = bool(info.st_mode & 0o022)
                sticky = bool(info.st_mode & stat.S_ISVTX)
                if writable and not sticky:
                    errors.append("OCR_DB_PARENT_PERMISSIONS_UNSAFE:" + str(component))
                    chain_ok = False
                    break
        if not chain_ok:
            db_state = "PARENT_CHAIN_NOT_VERIFIED"
        elif db_path.exists() and (not stat.S_ISREG(db_path.lstat().st_mode) or (db_path.lstat().st_mode & 0o077)):
            errors.append("OCR_DB_PERMISSIONS_UNSAFE")
            db_state = "UNSAFE_EXISTING_FILE"
        else:
            parent_info = db_path.parent.lstat()
            if parent_info.st_mode & 0o022:
                errors.append("OCR_DB_PARENT_PERMISSIONS_UNSAFE:" + str(db_path.parent))
                db_state = "PARENT_CHAIN_NOT_VERIFIED"
            else:
                # Shape and current path protections were checked without writes. No claim
                # is made that the DB can safely be created or that service startup is ready.
                db_state = "EXISTING_PROTECTED_FILE_VERIFIED" if db_path.exists() else "DB_ABSENT_PARENT_CHAIN_VERIFIED_NOT_READY"

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
