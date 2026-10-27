"""Fixed public-source inventory; no imports/execution of production modules.

This does not enumerate private state or prove that all possible writers are
known. Hash mismatch/permission failures retain UNKNOWN and publish no source.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import time

SOURCE_HOST = 'iZ6wee8q9z4t03hvqumwfhZ'
ROOT = Path('/opt/trading-system')
SOURCES = {
    'scripts/secure_secrets_portal_server.py': '57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1',
    'ai_service/secure_secrets_portal.py': '3804d540281c0e07480e5c95ef98f800b498fd09e2f14966d9d3737830157ba7',
    'douyin/open_api_foundation.py': 'cb9ca6f29796a1e280f88681cf84a3533a3529b955efab38975030582c9d8140',
    'tiktok/open_api_foundation.py': 'cce9f45ccdfe681e88117814227a714aa17e49e22881c1d922eb3ccd191c2afe',
    'ai_service/internal_provider_neutral_bridge.py': '9a7703b0ecac1dbd614668ffa1aa88e265989513a3babb05333b3fd2226daff1',
}
CALLS = frozenset(('store_secret', 'save', 'save_account_binding', 'disconnect',
    'create_state', 'consume_state', '_write_json_0600', '_write_text_0600',
    'write_text', 'replace', 'unlink'))


def catalogue(data, expected_sha256):
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        return {'status': 'SOURCE_VERSION_MISMATCH', 'sha256': digest}
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        return {'status': 'SOURCE_PARSE_UNKNOWN', 'sha256': digest}
    rows = []
    class Visitor(ast.NodeVisitor):
        def __init__(self): self.scope = []
        def definition(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()
        visit_ClassDef = definition
        visit_FunctionDef = definition
        visit_AsyncFunctionDef = definition
        def visit_Call(self, node):
            call = node.func
            name = call.attr if isinstance(call, ast.Attribute) else call.id if isinstance(call, ast.Name) else None
            if name in CALLS:
                rows.append({'scope': '.'.join(self.scope), 'line': node.lineno, 'call': name})
            self.generic_visit(node)
    Visitor().visit(tree)
    return {'status': 'PUBLIC_SOURCE_BYTES_MATCH', 'sha256': digest,
            'lexical_write_capable_calls': rows}


def read_public_source(path):
    """Fixed caller-selected public code only. Never follow source links."""
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('SOURCE_LINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 1000
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) & 0o022):
            raise ValueError('SOURCE_IDENTITY')
        data = handle.read(262145)
        after = os.fstat(handle.fileno())
    fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    current = path.lstat()
    if len(data) > 262144 or any(getattr(before,k) != getattr(after,k)
            or getattr(current,k) != getattr(after,k) for k in fields):
        raise ValueError('SOURCE_UNSTABLE')
    return data


def collect():
    if os.geteuid() == 0 or os.uname().nodename != SOURCE_HOST:
        raise RuntimeError('TOKYO_NONROOT_REQUIRED')
    files = []
    for relative, expected in SOURCES.items():
        try:
            result = catalogue(read_public_source(ROOT/relative), expected)
        except Exception:
            result = {'status': 'SOURCE_UNREADABLE_OR_IDENTITY_UNKNOWN'}
        files.append(dict(path=relative, **result))
    return {'schema_version': 1, 'observed_epoch': int(time.time()),
        'host': os.uname().nodename, 'uid': os.geteuid(),
        'delivery_commit': os.environ.get('GITHUB_SHA'), 'files': files,
        'status': 'FIXED_SOURCE_SCOPE_MATCH' if all(x['status']=='PUBLIC_SOURCE_BYTES_MATCH'
                    for x in files) else 'FIXED_SOURCE_SCOPE_INCOMPLETE',
        'lexical_catalogue_only': True, 'all_writer_custody_proven': False,
        'unknown_external_writers': True, 'production_module_imports': 0,
        'private_state_reads': 0, 'http_requests': 0, 'production_changes': 0,
        'limitations': ['Five fixed source files only; no whole-host/repository writer census',
            'Lexical calls do not prove reachability, authentication, scheduling or exclusive custody',
            'Source match does not authorize stopping any writer or transmitting private values']}


if __name__ == '__main__':
    print('PR122_SOURCE_WRITER_RECEIPT='+json.dumps(collect(), sort_keys=True))
