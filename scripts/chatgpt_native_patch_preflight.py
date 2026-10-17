"""Offline untrusted native patch manifest preflight for original Issue #19.

This is a *data* validator, never a code runner or writer admission.
No shell execution, filesystem modification, network, signing or model calls.
"""
import hashlib
import json
import re

class NativePatchHold(ValueError):
    pass

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SHA1 = re.compile(r"^[a-f0-9]{40}$")
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_ALLOWED_ENTRY = {"WORK": "WORK_NATIVE", "CHATGPT": "CHATGPT_NATIVE",
                  "DOTS": "DOTS_NATIVE"}
_KEYS = {"task_id","entry","execution_path","control_repository","target_repository",
         "target_base_sha","spec_sha256","checkpoint_sha256","files"}
_FILE_KEYS = {"path","sha256","size","content_utf8"}
_FORBIDDEN = (".git/", ".github/workflows/", "secrets/", "credentials/", "id_rsa",
              ".env", "authorized_keys")

def _id(value):
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise NativePatchHold("INVALID_ID")

def _path(value):
    if not isinstance(value,str) or not value or value.startswith("/"):
        raise NativePatchHold("UNSAFE_PATH")
    if "\\" in value or value.startswith("./") or "//" in value or "\x00" in value:
        raise NativePatchHold("UNSAFE_PATH")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise NativePatchHold("UNSAFE_PATH")
    low=value.lower()
    parts=low.split("/")
    if any(low.startswith(x) or low.endswith(x) for x in _FORBIDDEN) or any(p in (".git", ".env", "secrets", "credentials", "id_rsa", "authorized_keys") for p in parts) or (len(parts)>1 and parts[0]==".github" and parts[1]=="workflows"):
        raise NativePatchHold("PROTECTED_PATH")
    return value

def inspect(package, allowed_paths, max_total_bytes=131072):
    """Exact package check. allowed_paths must come from canonical task spec."""
    if not isinstance(package,dict) or set(package)!=_KEYS:
        raise NativePatchHold("INVALID_SCHEMA")
    for k in ("task_id","control_repository","target_repository"):
        _id(package[k])
    if package["entry"] not in _ALLOWED_ENTRY or package["execution_path"] != _ALLOWED_ENTRY[package["entry"]]:
        raise NativePatchHold("ENTRY_MISMATCH")
    if not _SHA1.fullmatch(package["target_base_sha"]):
        raise NativePatchHold("BASE_SHA_INVALID")
    for k in ("spec_sha256","checkpoint_sha256"):
        if not _SHA256.fullmatch(package[k]):
            raise NativePatchHold("BOUND_HASH_INVALID")
    if not isinstance(allowed_paths,(list,tuple,set)) or not allowed_paths:
        raise NativePatchHold("NO_TRUSTED_PATH_ALLOWLIST")
    allowed={_path(x) for x in allowed_paths}
    files=package["files"]
    if not isinstance(files,list) or not 1<=len(files)<=32:
        raise NativePatchHold("INVALID_FILES")
    used=set();total=0;out=[]
    for f in files:
        if not isinstance(f,dict) or set(f)!=_FILE_KEYS:
            raise NativePatchHold("INVALID_FILE_SCHEMA")
        path=_path(f["path"])
        if path not in allowed or path in used:
            raise NativePatchHold("UNAUTHORIZED_OR_DUPLICATE_PATH")
        used.add(path)
        text=f["content_utf8"]
        if not isinstance(text,str) or "\x00" in text:
            raise NativePatchHold("INVALID_UTF8_DATA")
        raw=text.encode("utf-8")
        if len(raw)!=f["size"] or type(f["size"]) is not int:
            raise NativePatchHold("SIZE_MISMATCH")
        if not _SHA256.fullmatch(f["sha256"]) or hashlib.sha256(raw).hexdigest()!=f["sha256"]:
            raise NativePatchHold("HASH_MISMATCH")
        total+=len(raw)
        if total>max_total_bytes:
            raise NativePatchHold("PACKAGE_SIZE_EXCEEDED")
        out.append({"path":path,"sha256":f["sha256"],"size":len(raw)})
    manifest=json.dumps(out,sort_keys=True,separators=(",",":")).encode("utf-8")
    return {"decision":"SYNTAX_DATA_PRECHECK_ONLY",
            "manifest_sha256":hashlib.sha256(manifest).hexdigest(),
            "files":sorted(out,key=lambda x:x["path"]),
            "writer_permission":"NOT_GRANTED","effect_count":0,
            "independent_review":"REQUIRED","execution":"FORBIDDEN"}
