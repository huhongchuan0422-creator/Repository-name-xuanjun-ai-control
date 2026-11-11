"""Fixed non-root source-contract metadata; never imports a production module.

Outputs identifier names and hashes only. Literal values, source text, docstrings,
defaults, credential files and database bytes are never exported.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import time

HOST = "iZ6wee8q9z4t03hvqumwfhZ"
ROOT = Path("/opt/trading-system")
SOURCES = ("accounts/credential_store.py", "trading_execution/secure_credential_intake.py",
           "trading_execution/dual_api_readiness.py", "database/repositories/__init__.py")
DATABASE = ROOT / "database/data/trading.db"
MARKERS = ("BINANCE_ACCOUNT_READONLY", "BINANCE_TRADING", "TRADING_CREDENTIAL_MASTER_KEY")


def catalogue(raw):
    tree = ast.parse(raw)
    imports = set()
    definitions = []
    markers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imports.update(x.name for x in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module)
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            markers.update(m for m in MARKERS if m in node.value)
    class Visitor(ast.NodeVisitor):
        def __init__(self): self.scope = []
        def definition(self, node):
            self.scope.append(node.name)
            row = {"name": '.'.join(self.scope), "kind": type(node).__name__}
            if hasattr(node, 'args'):
                row['parameters'] = [x.arg for x in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
                row['varargs'] = node.args.vararg is not None or node.args.kwarg is not None
            if len(definitions) < 128: definitions.append(row)
            self.generic_visit(node)
            self.scope.pop()
        visit_ClassDef = definition
        visit_FunctionDef = definition
        visit_AsyncFunctionDef = definition
    Visitor().visit(tree)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "imports": sorted(imports),
            "definitions": definitions, "recognized_role_markers": sorted(markers),
            "literal_values_exported": False, "production_module_executed": False,
            "semantics_or_role_permission_proven": False}


def checked_path(path, file=True):
    for parent in reversed(tuple(path.parents)):
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, 1000) or s.st_mode & 0o022:
            raise ValueError("SOURCE_PARENT_IDENTITY")
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 1000 or s.st_mode & 0o022 or s.st_nlink != 1:
        raise ValueError("SOURCE_FILE_IDENTITY")
    return s


def read_source(path):
    checked_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(262145)
        after = os.fstat(stream.fileno())
    current = checked_path(path)
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if len(raw) > 262144 or any(getattr(before,k) != getattr(after,k) or
                              getattr(after,k) != getattr(current,k) for k in fields):
        raise ValueError("SOURCE_CHANGED")
    return raw


def collect():
    if os.geteuid() != 1001 or os.uname().nodename != HOST:
        raise RuntimeError("EXACT_TOKYO_RUNNER_REQUIRED")
    files = []
    for name in SOURCES:
        try: value = dict(status='SOURCE_CONTRACT_METADATA_COLLECTED', **catalogue(read_source(ROOT/name)))
        except Exception: value = {'status':'SOURCE_UNREADABLE_OR_IDENTITY_UNKNOWN'}
        files.append(dict(path=name, **value))
    try:
        s = checked_path(DATABASE)
        database = {"status":"METADATA_ONLY", "uid":s.st_uid, "gid":s.st_gid,
                    "mode":oct(stat.S_IMODE(s.st_mode)), "size":s.st_size,
                    "device":s.st_dev,"inode":s.st_ino,"mtime_ns":s.st_mtime_ns}
    except Exception: database = {'status':'PATH_METADATA_UNKNOWN'}
    return {"schema_version":1,"observed_epoch":int(time.time()),"host":HOST,"uid":os.geteuid(),
            "files":files,"database_path":str(DATABASE),"database_metadata":database,
            "credentials_read":False,"database_opened":False,"production_modules_imported":0,
            "sudo_calls":0,"http_calls":0,"service_actions":0,"production_changes":0,
            "actual_secretref_or_readonly_provider_permission":"NOT_PROVEN",
            "status":"SOURCE_CONTRACT_METADATA_ONLY_NOT_C_ACCEPTANCE"}


if __name__ == '__main__':
    print('PR99_PHASE_C_SOURCE_CONTRACT_RECEIPT='+json.dumps(collect(),sort_keys=True))
