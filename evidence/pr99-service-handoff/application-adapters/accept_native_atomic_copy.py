"""Tokyo native-method / actual-schema acceptance on a NEW PRIVATE copy only.

No original application imports, production DB opens, services or exchange calls.
Uses synthetic credentials and a test-only guard, NOT a production Writer claim.
"""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from credential_atomic_write import AtomicCredentialWriter, BoundCredentialStore, SCHEMA_SQL, request_digest

SOURCE_SHA = '513ae2c21db4ccdf047d02796702941986be09275d9dafd2931fdc5af52e27cd'
COPY_SHA = '3ab916e90b9ed1ad1bffad8037118de22c0133691e95106ef0d1b9d92da98fb5'


def read_regular(path, limit):
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise RuntimeError('INPUT_SYMLINK')
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise RuntimeError('INPUT_BOUND')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or len(raw) != before.st_size:
            raise RuntimeError('INPUT_CHANGED')
        return raw
    finally:
        os.close(fd)


def native_factory(raw, include_verification=False):
    tree = ast.parse(raw)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CredentialStore')
    methods = {'_load_master_key', '_encrypt', '_decrypt', 'save_credential', 'load_credential'}
    if include_verification:
        methods.add('mark_verified')
    selected = []
    for node in cls.body:
        if isinstance(node, ast.Assign):
            ast.literal_eval(node.value)
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in methods:
            selected.append(node)
    if len([n for n in selected if isinstance(n, ast.FunctionDef)]) != len(methods):
        raise RuntimeError('NATIVE_METHODS_MISSING')
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'fingerprint_api_key')
    helpers = [helper]
    if include_verification:
        helpers.append(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'safe_record'))
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    args = init.args.posonlyargs + init.args.args
    defaults = {a.arg: ast.literal_eval(v) for a, v in zip(args[-len(init.args.defaults):], init.args.defaults)}
    class CredentialError(RuntimeError):
        pass
    namespace = dict(os=os, uuid=uuid, base64=base64, hashlib=hashlib,
                     AESGCM=AESGCM, CredentialError=CredentialError)
    module = ast.Module(body=[
        ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
        *helpers, ast.ClassDef(name='CredentialStore', bases=[], keywords=[], body=selected, decorator_list=[])
    ], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<hash-pinned-native-pure-methods>', 'exec'), namespace)
    native = namespace['CredentialStore']
    def factory(repository, master_key):
        store = native()
        store.repository = repository
        store.master_key = store._load_master_key(master_key)
        store.key_version = defaults['key_version']
        return store
    return factory


def main():
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'iZ6wee8q9z4t03hvqumwfhZ':
        raise RuntimeError('TOKYO_ROOT_REQUIRED')
    os.umask(0o077)
    source = read_regular(Path('/opt/trading-system/accounts/credential_store.py'), 262144)
    snapshot = read_regular(Path('/root/pr99-precopy-dhtmwlx_/database.sqlite'), 67108864)
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA or hashlib.sha256(snapshot).hexdigest() != COPY_SHA:
        raise RuntimeError('PINNED_INPUT_CHANGED')
    directory = Path(tempfile.mkdtemp(prefix='pr99-native-atomic-copy-', dir='/root'))
    print('DIRECTORY=' + str(directory), flush=True)
    copy = directory / 'private-test.sqlite'
    with copy.open('xb') as stream:
        stream.write(snapshot)
        stream.flush()
        os.fsync(stream.fileno())
    del snapshot
    db = sqlite3.connect(str(copy))
    try:
        # Changes below are confined to this new copy, never the accepted backup.
        original_rows = db.execute('SELECT * FROM credential_records ORDER BY id').fetchall()
        if len(original_rows) != 3:
            raise RuntimeError('BASELINE_CREDENTIAL_COUNT_CHANGED')
        original_tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        for statement in SCHEMA_SQL:
            db.execute(statement)
        db.commit()
        writer = AtomicCredentialWriter(db, lambda: True)  # Synthetic copy-only guard.
        store = BoundCredentialStore(writer, native_factory(source),
                                     {'test-only': base64.b64encode(os.urandom(32)).decode()}, 'test-only')
        identifier = 'pr99-copy-test-' + uuid.uuid4().hex
        prepared = store.prepare_save(customer_id='pr99-copy-test', account_id='pr99-copy-test',
                                      api_key='synthetic-not-an-exchange-key', api_secret='synthetic-not-an-exchange-secret',
                                      credential_id=identifier, trade_permission=False, withdraw_permission=False)
        operation = 'copy-only-' + uuid.uuid4().hex
        result = writer.commit(operation, prepared, None)
        if result['status'] != 'COMMITTED':
            raise RuntimeError('COPY_COMMIT_FAILED')
        decoded = store.load_credential(identifier)
        if decoded['api_key'] != 'synthetic-not-an-exchange-key' or decoded['api_secret'] != 'synthetic-not-an-exchange-secret':
            raise RuntimeError('NATIVE_ROUNDTRIP_FAILED')
        del decoded
        db.close()
        db = sqlite3.connect(str(copy))
        writer = AtomicCredentialWriter(db, lambda: True)
        if writer.query(operation, request_digest(prepared, None))['status'] != 'COMMITTED':
            raise RuntimeError('RESTART_RECONCILIATION_FAILED')
        remaining = db.execute('SELECT * FROM credential_records WHERE credential_id<>? ORDER BY id', (identifier,)).fetchall()
        if remaining != original_rows or db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise RuntimeError('COPY_BASELINE_OR_INTEGRITY_CHANGED')
        receipt = dict(status='NATIVE_METHODS_ACTUAL_SCHEMA_COPY_PASS', original_tables=len(original_tables),
                       baseline_credentials_unchanged=3, synthetic_credentials_committed=1,
                       restart_query='PASS', source_sha256=SOURCE_SHA, snapshot_sha256=COPY_SHA,
                       production_writer_claimed=False, live_hook_installed=False,
                       production_database_opened=False, service_changes=0, migration_started=False)
        raw = json.dumps(receipt, sort_keys=True, indent=2).encode()
        target = directory / 'receipt.json'
        with target.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print('STATUS=' + receipt['status'])
        print('NATIVE_SAVE_LOAD=PASS; RESTART_QUERY=PASS; ORIGINAL_ROWS_UNCHANGED=3/3')
        print('RECEIPT=' + str(target))
        print('SHA256=' + hashlib.sha256(raw).hexdigest())
        print('LIVE_HOOK=NOT_INSTALLED; SERVICE_CHANGES=0; MIGRATION_STARTED=NO')
    finally:
        db.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STATUS=HOLD; ERROR_TYPE=' + type(error).__name__)
        raise SystemExit(2)
