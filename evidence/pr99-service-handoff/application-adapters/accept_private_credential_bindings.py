"""Tokyo-only private snapshot acceptance, never a live service installation.

Uses hash-pinned original pure credential methods; does not import application
modules, open the live database, call exchange APIs, or install service hooks.
"""
import ast
import base64
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

HOST = 'iZ6wee8q9z4t03hvqumwfhZ'
ROOT = Path('/opt/trading-system')
PRIVATE = Path('/root/pr99-key-preservation-etcq8gnf')
COPY = Path('/root/pr99-precopy-dhtmwlx_/database.sqlite')
COPY_SHA = '3ab916e90b9ed1ad1bffad8037118de22c0133691e95106ef0d1b9d92da98fb5'
SOURCE_SHA = '513ae2c21db4ccdf047d02796702941986be09275d9dafd2931fdc5af52e27cd'
ADAPTER_SHA = 'd0206d5c443516c1edea277baeaaff79eef6e65e20a67179c75d4ea1ee397007'


def read_regular(path, limit):
    path = Path(path)
    for part in (path, *path.parents):
        if part.is_symlink():
            raise RuntimeError('SYMLINK_INPUT')
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise RuntimeError('INPUT_LIMIT')
        chunks = []
        count = 0
        while True:
            block = os.read(fd, min(1048576, limit + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
            if count > limit:
                raise RuntimeError('INPUT_LIMIT')
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
            before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                    after.st_mtime_ns, after.st_ctime_ns):
            raise RuntimeError('INPUT_CHANGED')
        return b''.join(chunks)
    finally:
        os.close(fd)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_new(path, value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2).encode()
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    directory = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return digest(data)


def original_pure_factory(source):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    cls = next(n for n in ast.parse(source).body
               if isinstance(n, ast.ClassDef) and n.name == 'CredentialStore')
    selected = []
    for node in cls.body:
        if isinstance(node, ast.Assign):
            ast.literal_eval(node.value)
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {
                '_load_master_key', '_decrypt', 'load_credential'}:
            selected.append(node)
    if sum(isinstance(n, ast.FunctionDef) for n in selected) != 3:
        raise RuntimeError('SOURCE_METHODS')
    module = ast.Module(body=[
        ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
        ast.ClassDef(name='CredentialStore', bases=[], keywords=[], body=selected,
                     decorator_list=[])], type_ignores=[])
    class CredentialError(RuntimeError):
        pass
    namespace = dict(os=os, base64=base64, hashlib=hashlib, AESGCM=AESGCM,
                     CredentialError=CredentialError)
    exec(compile(ast.fix_missing_locations(module), '<pinned-original-pure-methods>', 'exec'), namespace)
    store_class = namespace['CredentialStore']
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    args = init.args.posonlyargs + init.args.args
    defaults = {a.arg: ast.literal_eval(v)
                for a, v in zip(args[-len(init.args.defaults):], init.args.defaults)}
    def factory(repository, master_key):
        store = store_class()
        store.repository = repository
        store.master_key = store._load_master_key(master_key)
        store.key_version = defaults['key_version']
        return store
    return store_class.ENV_MASTER_KEY, factory


def verify_rows(adapter, rows, factory, keys):
    if len(rows) != 3 or len({r['credential_id'] for r in rows}) != 3:
        raise RuntimeError('EXACT_SNAPSHOT_ROWS_REQUIRED')
    # Exact snapshot order inherited from the accepted Owner terminal result;
    # real native decryption below confirms every explicit assignment again.
    bindings = {r['credential_id']: {
        'record_sha256': adapter.fingerprint(r),
        'key_ref': 'project' if i < 2 else 'portal'} for i, r in enumerate(rows)}
    class Repository:
        def get(self, identifier):
            return dict(next(r for r in rows if r['credential_id'] == identifier))
    reader = adapter.BoundCredentialReader(Repository(), factory, bindings, keys)
    for row in rows:
        result = reader.load_credential(row['credential_id'])
        if not isinstance(result, dict):
            raise RuntimeError('NATIVE_RESULT_INVALID')
        del result
    return bindings


def main(adapter_path):
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != HOST:
        raise RuntimeError('TOKYO_ROOT_REQUIRED')
    os.umask(0o077)
    if PRIVATE.is_symlink() or PRIVATE.stat().st_uid != 0 or PRIVATE.stat().st_mode & 0o077:
        raise RuntimeError('PRIVATE_DIRECTORY_PERMISSIONS')
    lock = os.open(str(PRIVATE / 'credential-acceptance.lock'),
                   os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Private validation lock only; never a production Writer or migration lock.
    adapter_raw = read_regular(adapter_path, 65536)
    if digest(adapter_raw) != ADAPTER_SHA:
        raise RuntimeError('ADAPTER_CHANGED')
    source = read_regular(ROOT / 'accounts/credential_store.py', 262144)
    if digest(source) != SOURCE_SHA:
        raise RuntimeError('ORIGINAL_SOURCE_CHANGED')
    if digest(read_regular(COPY, 67108864)) != COPY_SHA:
        raise RuntimeError('PREPARATION_COPY_CHANGED')
    manifest_raw = read_regular(PRIVATE / 'manifest.json', 262144)
    manifest = json.loads(manifest_raw)
    spec = importlib.util.spec_from_loader('pr99_exact_key_binding', loader=None)
    adapter = importlib.util.module_from_spec(spec)
    exec(compile(adapter_raw, '<pinned-credential-key-binding>', 'exec'), adapter.__dict__)
    key_name, factory = original_pure_factory(source)
    keys, hashes = {}, {}
    for ref, filename in (('project', 'project-config.env'), ('portal', 'portal-config.env')):
        path = PRIVATE / filename
        if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            raise RuntimeError('PRIVATE_KEY_COPY_PERMISSIONS')
        raw = read_regular(path, 262144)
        expected = next(r['sha256'] for r in manifest['files'] if r['name'] == filename)
        if digest(raw) != expected:
            raise RuntimeError('PRESERVED_CONFIGURATION_CHANGED')
        values = [line.split('=', 1)[1] for line in raw.decode().splitlines()
                  if line.startswith(key_name + '=')]
        if len(values) != 1 or not values[0]:
            raise RuntimeError('AMBIGUOUS_KEY_FIELD')
        keys[ref], hashes[ref] = values[0], digest(raw)
    inputs = {'snapshot': COPY_SHA, 'source': SOURCE_SHA, 'adapter': ADAPTER_SHA,
              'preservation_manifest': digest(manifest_raw), 'private_key_files': hashes,
              'acceptance_program': digest(read_regular(__file__, 65536))}
    receipt_path = PRIVATE / 'credential-binding-acceptance.json'
    binding_path = PRIVATE / 'credential-bindings.json'
    attempt_path = PRIVATE / 'credential-binding-attempt.json'
    if receipt_path.exists():
        old = json.loads(read_regular(receipt_path, 262144))
        if (old.get('status') != 'PRIVATE_COPY_NATIVE_METHODS_PASS' or
                old.get('inputs') != inputs or
                digest(read_regular(binding_path, 262144)) != old.get('bindings_sha256')):
            raise RuntimeError('EXISTING_ACCEPTANCE_UNKNOWN_OR_CHANGED')
        print('STATUS=REUSED_PRIVATE_COPY_ACCEPTANCE; VERIFIED=3/3')
        print('RECEIPT=' + str(receipt_path))
        print('SERVICE_CHANGES=0; MIGRATION_STARTED=NO')
        return
    if attempt_path.exists() or binding_path.exists():
        raise RuntimeError('PRIOR_ATTEMPT_NEEDS_RECONCILIATION')
    write_new(attempt_path, {'inputs': inputs, 'purpose': 'PRIVATE_COPY_ACCEPTANCE_ONLY'})
    stage = 'SNAPSHOT_ACCEPTANCE'
    try:
        db = sqlite3.connect(COPY.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute('SELECT * FROM credential_records LIMIT 4')]
        finally:
            db.close()
        bindings = verify_rows(adapter, rows, factory, keys)
        if digest(read_regular(COPY, 67108864)) != COPY_SHA:
            raise RuntimeError('COPY_CHANGED_DURING_ACCEPTANCE')
        bindings_sha = write_new(binding_path, {'schema': 1, 'inputs': inputs,
                                               'bindings': bindings})
        result = {'status': 'PRIVATE_COPY_NATIVE_METHODS_PASS', 'inputs': inputs,
                  'bindings_sha256': bindings_sha, 'verified_records': 3,
                  'live_application_instance_verified': False,
                  'new_credential_writes_integrated': False, 'service_changes': 0,
                  'migration_started': False,
                  'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        receipt_sha = write_new(receipt_path, result)
        print('STATUS=PRIVATE_COPY_NATIVE_METHODS_PASS; VERIFIED=3/3')
        print('BINDINGS=PRIVATE_SAVED; KEYS_IN_BINDINGS=NO')
        print('RECEIPT=' + str(receipt_path))
        print('RECEIPT_SHA256=' + receipt_sha)
        print('LIVE_APP_HOOK=NOT_INSTALLED; SERVICE_CHANGES=0; MIGRATION_STARTED=NO')
    except Exception as error:
        write_new(receipt_path, {'status': 'HOLD', 'inputs': inputs, 'stage': stage,
                                'error_type': type(error).__name__, 'service_changes': 0})
        raise RuntimeError('ACCEPTANCE_HOLD_SAVED') from None
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        main(sys.argv[1])
    except Exception as error:
        print('STATUS=HOLD; ERROR_TYPE=' + type(error).__name__)
        print('NO_PRODUCTION_ACTIONS; KEEP_EXISTING_CHECKPOINTS')
        sys.exit(2)
