"""Project private received code/units into a value-free runtime dependency inventory.
No network, app imports, service action, DB/key/config reads or file writes.
Static syntax clues are not a complete runtime contract or a cutover permit.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shlex

RESOLVER = Path('/root/pr99-handoff-resolve-51c23aaa/resolve.py')
RESOLVER_SHA = '10d24ddfea39347930115a4dc57e81b0b41461c10bd71e70b7f7d15afeb3fea4'
ORIGINAL = Path('/root/pr99-s07-install-launch.a5NZU99H/install.py')
ORIGINAL_SHA = '745c67d34cf4b0d546aee28c74c11b1586a315a03d970cbebc37508ebc61f8fd'
PACKAGE = Path('/root/pr99-s07-domestic-stage-v1/package.json')
PACKAGE_SHA = '9b702576d48883786d051b2f1b49972baf94db3d1e8bf330ee59250a5974efa3'
UNITS = ('secure-secrets-portal.service', 'xuanjun-wecom-customer-contact.service',
         'xuanjun-wecom-customer-service.service')


def digest(b):
    return hashlib.sha256(b).hexdigest()


def load_pinned(path, sha):
    # Authenticate all parent and file identities before executing frozen helpers.
    import stat
    for p in reversed(path.parents):
        st = p.lstat()
        assert stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as f:
        a = os.fstat(f.fileno())
        assert stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1
        assert not a.st_mode & 0o077 and a.st_size <= 100000
        raw = f.read(100001)
        b = os.fstat(f.fileno())
    c = path.lstat()
    assert all(getattr(a,k) == getattr(b,k) == getattr(c,k) for k in
               ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))
    assert len(raw) == a.st_size and digest(raw) == sha
    ns = {'__name__': 'pinned_helper_functions', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), ns)
    return ns


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = call_name(node.value)
        return prefix + '.' + node.attr if prefix else node.attr
    return 'EXPRESSION'


def path_hint(value):
    if not isinstance(value, str) or len(value) > 180 or '\\' in value:
        return False
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', value) or '..' in value.split('/'):
        return False
    if any(len(x) > 48 for x in value.split('/')):
        return False
    if value.startswith('/') and not value.startswith(('/opt/', '/home/', '/var/', '/etc/', '/run/')):
        return False
    return value.endswith(('.db', '.sqlite', '.sqlite3', '.json', '.yaml', '.yml', '.env', '.pem', '.key'))


def source_clues(raw):
    tree = ast.parse(raw)
    env, paths, io_calls = set(), set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = call_name(n.func)
            if name in ('os.getenv', 'os.environ.get', 'getenv') and n.args:
                key = n.args[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,100}', key.value):
                    env.add(key.value)
            if name.split('.')[-1] in ('open','read_text','read_bytes','write_text','write_bytes','load_dotenv','create_engine','connect','mkdir','FileHandler','RotatingFileHandler','import_module','spec_from_file_location'):
                io_calls.append({'line': n.lineno, 'call': name})
        if isinstance(n, ast.Subscript) and call_name(n.value) == 'os.environ':
            key = n.slice
            if isinstance(key, ast.Constant) and isinstance(key.value,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,100}', key.value):
                env.add(key.value)
        if isinstance(n, ast.Constant) and path_hint(n.value):
            paths.add(n.value)
    return {'environment_variable_names': sorted(env), 'literal_path_clues': sorted(paths),
            'io_or_dynamic_call_sites': sorted(io_calls, key=lambda r:r['line'])}


def unit_clues(raw):
    section, env, fields = '', set(), {}
    for line in raw.decode().replace('\\\n',' ').splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif section == 'Service' and '=' in line and not line.startswith(('#',';')):
            k,v = line.split('=',1)
            if k == 'Environment':
                if not v.strip():
                    env.clear()
                for token in shlex.split(v):
                    name = token.partition('=')[0]
                    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,100}',name):
                        env.add(name)
            elif k in ('EnvironmentFile','LoadCredential'):
                fields[k+'_configured'] = bool(v.strip())
            elif k in ('User','Group','WorkingDirectory'):
                # Only established path roots or account names; no command/value echo.
                if k == 'WorkingDirectory':
                    fields[k] = v if re.fullmatch(r'/(?:opt/trading-system|home/admin)(?:/[A-Za-z0-9_.-]{1,48})*',v) and '..' not in v.split('/') else 'UNKNOWN_REDACTED'
                else:
                    fields[k] = v if re.fullmatch(r'[A-Za-z0-9_-]{0,40}',v) else 'UNKNOWN_REDACTED'
    fields['inline_environment_variable_names'] = sorted(env)
    fields['unit_sha256'] = digest(raw)
    return fields


def main():
    assert os.geteuid() == 0 and os.uname().nodename == 'iZmj7a5kwr75qc1tul4kf9Z'
    resolver = load_pinned(RESOLVER, RESOLVER_SHA)
    projection, collector = resolver['bootstrap']()
    read = collector['stable_file']
    receipt = json.loads(read(projection['ROOT']/'receipt.json',20000,private=True))
    assert receipt['archive_sha256'] == projection['ARCHIVE_SHA']
    archive = read(projection['ROOT']/'payload.tar.gz',4*1024*1024+65536,private=True)
    assert digest(archive) == projection['ARCHIVE_SHA']
    units = collector['verify_archive'](archive,receipt)
    old = load_pinned(ORIGINAL, ORIGINAL_SHA)
    raw = old['stable'](PACKAGE,64*1024*1024)
    assert digest(raw) == PACKAGE_SHA
    plan, sources = old['unpack'](raw,PACKAGE_SHA)
    assert len(sources) == 79
    clues = {name: source_clues(data) for name,data in sources.items() if name.endswith('.py')}
    clues = {name:r for name,r in clues.items() if any(r.values())}
    print(json.dumps({'status':'S07_RECEIVED_RUNTIME_STATIC_INVENTORY',
        'evidence_scope':'RECEIVED_PRIVATE_COPIES_STATIC_SYNTAX_ONLY',
        'source_files':len(sources), 'units':{n:unit_clues(units['units/'+n]) for n in UNITS},
        'source_clues':clues,'environment_values_disclosed':False,
        'application_imports':0,'network_requests':0,'service_actions':0,
        'database_or_config_or_key_files_opened':False,'runtime_closure_proven':False,
        'production_cutover':False},sort_keys=True),flush=True)

if __name__ == '__main__':
    main()
