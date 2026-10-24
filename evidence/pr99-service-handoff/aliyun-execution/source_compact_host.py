import ast
import datetime
import hashlib
import json
import os
import re
import stat
import time
ROOT = '/opt/trading-system'
SKIP = frozenset(('.git', '.venv', 'venv', '__pycache__', 'node_modules', 'runtime', 'tests', 'test', 'docs', 'evidence', 'backup', 'backups'))
SAFE = re.compile('[A-Za-z0-9_./-]{1,240}')
ENV = re.compile('[A-Z][A-Z0-9_]{1,100}')
KINDS = ('DB_FACTORY', 'FILE_WRITE', 'MUTATION_CALL')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_at(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise RuntimeError('SOURCE_TYPE_OR_SIZE')
        raw = b''
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(fd)
        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:
            raise RuntimeError('SOURCE_DRIFT')
        return raw
    finally:
        os.close(fd)

def analyze(raw):
    """Only fixed categories, counts and environment variable NAMES leave AST."""
    tree = ast.parse(raw)
    counts = {name: 0 for name in KINDS}
    env = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        if name in ('connect', 'create_engine', 'sessionmaker'):
            counts['DB_FACTORY'] += 1
        elif name in ('write_text', 'write_bytes', 'dump', 'dumps', 'mkdir', 'makedirs', 'replace', 'rename', 'unlink'):
            if name != 'dumps':
                counts['FILE_WRITE'] += 1
        elif name in ('commit', 'add', 'add_all', 'delete', 'execute', 'executemany'):
            counts['MUTATION_CALL'] += 1
        if name in ('getenv', 'get') and node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if type(value) is str and ENV.fullmatch(value):
                env.add(value)
        if name == 'open':
            modes = [node.args[1]] if len(node.args) > 1 else []
            modes += [x.value for x in node.keywords if x.arg == 'mode']
            if any((isinstance(x, ast.Constant) and type(x.value) is str and any((c in x.value for c in 'wax+')) for x in modes)):
                counts['FILE_WRITE'] += 1
    return (counts, sorted(env))

def code_inventory(deadline):
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        root_identity = os.fstat(fd)
        manifest = []
        rows = []
        errors = []
        total = 0
        excluded_links = 0
        for relative, dirs, files, directory in os.fwalk('.', topdown=True, follow_symlinks=False, dir_fd=fd):
            if time.monotonic() > deadline:
                raise RuntimeError('SOURCE_DEADLINE')
            keep = []
            for name in sorted(dirs):
                if name in SKIP or name.startswith('.'):
                    continue
                s = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISLNK(s.st_mode):
                    excluded_links += 1
                elif stat.S_ISDIR(s.st_mode):
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(files):
                if not name.endswith('.py') or name.startswith('test_'):
                    continue
                path = (relative + '/' + name).removeprefix('./')
                if not SAFE.fullmatch(path):
                    raise RuntimeError('SOURCE_NAME_BOUND')
                s = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISLNK(s.st_mode):
                    excluded_links += 1
                    continue
                raw = read_at(directory, name, 1048576)
                total += len(raw)
                if total > 67108864 or len(manifest) >= 2048:
                    raise RuntimeError('SOURCE_TOTAL_BOUND')
                manifest.append([path, sha(raw)])
                try:
                    counts, env = analyze(raw)
                except (SyntaxError, UnicodeError):
                    if len(errors) >= 32:
                        raise RuntimeError('SOURCE_PARSE_BOUND')
                    errors.append(path)
                    continue
                if any(counts.values()):
                    rows.append({'path': path, 'sha256': sha(raw), 'calls': counts, 'environment_keys': env[:12], 'environment_keys_total': len(env)})
        named = os.stat(ROOT, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (root_identity.st_dev, root_identity.st_ino):
            raise RuntimeError('SOURCE_ROOT_DRIFT')
        required = {'scripts/secure_secrets_portal_server.py', 'ai_service/wecom_customer_contact_service.py', 'ai_service/wecom_customer_service.py'}
        if not required <= {item[0] for item in manifest}:
            raise RuntimeError('SOURCE_ROLE_ENTRIES_MISSING')
        rows.sort(key=lambda row: (-row['calls']['DB_FACTORY'], -row['calls']['MUTATION_CALL'], row['path']))
        return {'files': len(manifest), 'bytes': total, 'manifest_sha256': sha(json.dumps(sorted(manifest), separators=(',', ':')).encode()), 'candidate_files_total': len(rows), 'omitted_candidate_files': max(0, len(rows) - 128), 'candidates': rows[:128], 'parse_errors': errors, 'excluded_links': excluded_links}
    finally:
        os.close(fd)

def observe(expected,nonce):
    assert os.geteuid()==0 and os.uname().nodename==expected=='iZ6wee8q9z4t03hvqumwfhZ'
    return {'hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z',
        'scope':'PR99_SOURCE_ONLY_STATIC_CANDIDATES_NOT_AUTHORITY',
        'source':code_inventory(time.monotonic()+35),
        'scheduler_evidence':'INHERIT_T_JPN70EXLHV86XA8_NO_RESCAN',
        'business_source_imports':0,'database_opened':False,'service_actions':0,'business_requests':0,
        'canonical_data_assigned':False,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN',
        'limitations':['STATIC_CANDIDATES_NOT_PROVEN_WRITERS','DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED',
                       'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED']}

if __name__=='__main__':
    import base64,zlib
    raw=json.dumps(observe(EXPECTED,NONCE),sort_keys=True,separators=(',',':')).encode()
    assert len(raw)<=110000
    wire={'encoding':'PR99_ZLIB_BASE64_V1','bytes':len(raw),'sha256':sha(raw),'payload':base64.b64encode(zlib.compress(raw,9)).decode()}
    assert len(wire['payload'])<22000,'SOURCE_RECEIPT_PAYLOAD_BOUND'
    text=json.dumps(wire,separators=(',',':'))
    assert len(text.encode())<23000,'SOURCE_RECEIPT_WIRE_BOUND'
    print(text,flush=True)
