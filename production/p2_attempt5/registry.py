"""Root-managed immutable configuration source registry. Not an execution permit.

No production DB access, Grant registration, Writer lease acquisition, private
key read, adapter execution, directory creation or overwrite. A dedicated local
SQLite metadata index records registry commits only; it is NOT AuthorityStore.
"""
import contextlib
import fcntl
import sqlite3
import hashlib
import json
import os
import re
import stat

DEFAULT_ROOT = '/etc/xuanjun-p2/registry'
BOUND = 65536
INDEX = '.registry-commits.sqlite3'
INDEX_APPLICATION = 0x50325247
LOCK = '.registry-registration.lock'
IDENTIFIER = re.compile(r'^[a-z0-9][a-z0-9_-]{11,79}$')
HEX = re.compile(r'^[0-9a-f]{64}$')
CONFIG_FIELDS = {'schema', 'database', 'socket', 'principal', 'key',
    'public_der_sha256', 'issuer', 'adapter_path', 'adapter_sha256',
    'ledger_directory', 'grant', 'review_id', 'cycle_policy', 'command_sha256'}
KINDS = {'issuer': 'ISSUER_TRUST', 'adapter': 'ADAPTER_SOURCE',
         'authority_store': 'AUTHORITY_STORE_SOURCE', 'writer_fence': 'WRITER_FENCE_SOURCE'}


def need(ok, code):
    if not ok:
        raise RuntimeError('P2_CONFIG_REGISTRY_' + code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')


def decode(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'DUPLICATE_KEY')
            value[key] = item
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
        parse_constant=lambda unused: need(False, 'NONFINITE_JSON'))


def text(value, code, pattern=r'[A-Za-z0-9_.:/#@+%=~-]{1,256}'):
    need(type(value) is str and value.strip() == value and
         value.upper() != 'UNKNOWN' and re.fullmatch(pattern, value), code)
    return value


def digest_value(value, code):
    need(type(value) is str and HEX.fullmatch(value), code)
    return value


def absolute_path(value, code):
    need(type(value) is str and value.startswith('/') and
         not value.startswith('//') and value != '/' and
         os.path.normpath(value) == value and
         not any(ord(c) < 32 or ord(c) == 127 for c in value) and
         '\\' not in value, code)
    return value


def config_values(cfg):
    text(cfg['issuer'], 'ISSUER_VALUE', r'[A-Za-z0-9_.-]{1,80}')
    for name in ('public_der_sha256', 'adapter_sha256', 'command_sha256'):
        digest_value(cfg[name], 'CONFIG_DIGEST')
    for name in ('adapter_path', 'database', 'socket', 'key', 'ledger_directory'):
        absolute_path(cfg[name], 'CONFIG_ABSOLUTE_PATH')
    need(type(cfg['review_id']) is int and cfg['review_id'] > 0 and
         type(cfg['cycle_policy']) is dict and type(cfg['grant']) is dict,
         'CONFIG_VALUE_TYPES')
    for name in ('host', 'actor_id', 'writer_id'):
        text(cfg['principal'][name], 'PRINCIPAL_VALUE')
    need(type(cfg['grant'].get('target_host')) is str and
         type(cfg['grant'].get('actor_id')) is str, 'GRANT_IDENTITY_TYPES')


def parent(path):
    need(os.geteuid() == 0, 'ROOT_ADMIN_REQUIRED')
    need(type(path) is str and path.startswith('/') and path != '/' and
         os.path.normpath(path) == path, 'ABSOLUTE_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.strip('/').split('/')[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            need(info.st_uid == 0 and not info.st_mode & 0o022, 'PARENT_PROTECTION')
        return fd, path.rsplit('/', 1)[1]
    except BaseException:
        os.close(fd)
        raise


def read(path, expected):
    need(type(expected) is str and HEX.fullmatch(expected), 'SHA_PIN_REQUIRED')
    directory, leaf = parent(path)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
             before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600 and
             before.st_size <= BOUND, 'PRIVATE_SOURCE_PROTECTION')
        raw = os.read(fd, BOUND + 1)
        after = os.fstat(fd)
        need(len(raw) == before.st_size and
             (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             'SOURCE_CHANGED')
        need(hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_SHA')
        return raw, decode(raw)
    finally:
        os.close(fd)


def reference(value):
    need(type(value) is dict and set(value) == {'path', 'sha256'}, 'REFERENCE_FIELDS')
    return read(value['path'], value['sha256'])[1]


def root_fd(root):
    fd, unused = parent(root + '/probe')
    info = os.fstat(fd)
    try:
        need(stat.S_IMODE(info.st_mode) == 0o700, 'REGISTRY_DIRECTORY')
    except BaseException:
        os.close(fd)
        raise
    return fd


def verified_record(raw):
    record = decode(raw)
    need(type(record) is dict and set(record) ==
         {'schema', 'registration_id', 'hostname', 'config', 'sources'}, 'RECORD_FIELDS')
    need(type(record['schema']) is int and record['schema'] == 1 and
         type(record['registration_id']) is str and
         IDENTIFIER.fullmatch(record['registration_id']), 'RECORD_VERSION_OR_ID')
    need(record['hostname'] == os.uname().nodename, 'HOST_BINDING')
    need(type(record['sources']) is dict and set(record['sources']) == set(KINDS),
         'SOURCE_SET')
    cfg = reference(record['config'])
    need(type(cfg) is dict and set(cfg) == CONFIG_FIELDS and
         type(cfg['schema']) is int and cfg['schema'] == 1, 'CONFIG_FIELDS')
    need(type(cfg['principal']) is dict and set(cfg['principal']) ==
         {'host', 'actor_id', 'writer_id'} and
         all(type(v) is str and 0 < len(v) <= 256 and v != 'UNKNOWN'
             for v in cfg['principal'].values()), 'PRINCIPAL')
    config_values(cfg)
    need(cfg['principal']['host'] == record['hostname'] == cfg['grant']['target_host'] and
         cfg['principal']['actor_id'] == cfg['grant']['actor_id'], 'CONFIG_IDENTITY')
    wanted = {
        'issuer': {'issuer': cfg['issuer'], 'public_der_sha256': cfg['public_der_sha256']},
        'adapter': {'path': cfg['adapter_path'], 'sha256': cfg['adapter_sha256']},
        'authority_store': {'database': cfg['database']},
        'writer_fence': {'principal': cfg['principal']}}
    for name, kind in KINDS.items():
        source = reference(record['sources'][name])
        need(type(source) is dict and set(source) ==
             {'schema', 'kind', 'hostname', 'source_id', 'subject'}, 'SOURCE_FIELDS')
        need(type(source['schema']) is int and source['schema'] == 1 and
             source['kind'] == kind and source['hostname'] == record['hostname'] and
             type(source['source_id']) is str and 0 < len(source['source_id']) <= 256 and
             source['source_id'] != 'UNKNOWN' and
             type(source['subject']) is dict and set(source['subject']) == set(wanted[name]) and
             source['subject'] == wanted[name],
             'SOURCE_BINDING')
        text(source['source_id'], 'SOURCE_ID_VALUE')
    # Source IDs are root-admin provenance references, not independent live
    # transaction attestations. No lease/fence validity is inferred here.
    need(canonical(record) == raw, 'CANONICAL_RECORD_REQUIRED')
    return record, cfg



def private_info(fd):
    info = os.fstat(fd)
    need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and
         info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
         'PRIVATE_COMMIT_FILE')
    return info


@contextlib.contextmanager
def registration_lock(root, writer):
    directory = root_fd(root)
    fd = None
    try:
        flags = os.O_RDWR | os.O_CREAT if writer else os.O_RDONLY
        fd = os.open(LOCK, flags | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
        private_info(fd)
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if writer else fcntl.LOCK_SH) |
                        fcntl.LOCK_NB)
        except BlockingIOError:
            need(False, 'REGISTRATION_IN_PROGRESS_HOLD')
        yield directory
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def index_info(root):
    directory, leaf = parent(root + '/' + INDEX)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        return private_info(fd)
    finally:
        os.close(fd)


def open_index(root, writer=False, initialize=False):
    # Only this fixed dedicated registry metadata file is ever opened as SQL.
    # No config-provided production path is passed to sqlite3.
    path = root + '/' + INDEX
    if initialize:
        directory = root_fd(root)
        try:
            fd = os.open(INDEX, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                private_info(fd)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory)
        finally:
            os.close(directory)
    before = index_info(root)
    for suffix in ('-journal', '-wal', '-shm'):
        need(not os.path.lexists(path + suffix), 'INDEX_RECOVERY_REQUIRED')
    from urllib.parse import quote
    uri = 'file:' + quote(path, safe='/') + '?mode=' + ('rw' if writer else 'ro')
    db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=0)
    try:
        if writer:
            db.execute('PRAGMA synchronous=FULL')
            need(db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete',
                 'INDEX_JOURNAL_MODE')
        else:
            db.execute('PRAGMA query_only=ON')
        if initialize:
            db.executescript('BEGIN IMMEDIATE; PRAGMA application_id=1345475143; '
                'PRAGMA user_version=1; CREATE TABLE registry_commits '
                '(registration_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, '
                'device INTEGER NOT NULL, inode INTEGER NOT NULL); COMMIT;')
        need(db.execute('PRAGMA application_id').fetchone()[0] == INDEX_APPLICATION and
             db.execute('PRAGMA user_version').fetchone()[0] == 1,
             'DEDICATED_INDEX_REQUIRED')
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        need(tables == [('registry_commits',)], 'NO_PRODUCTION_LEDGER_TABLES')
        after = index_info(root)
        need((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
             'INDEX_REPLACED')
        return db
    except BaseException:
        db.close()
        raise


def committed(db, registration_id, record_sha256, info):
    row = db.execute('SELECT sha256,device,inode FROM registry_commits '
                     'WHERE registration_id=?', (registration_id,)).fetchone()
    need(row == (record_sha256, info.st_dev, info.st_ino), 'REGISTRATION_NOT_COMMITTED')


def record_info(root, name):
    directory, leaf = parent(root + '/' + name)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        return private_info(fd)
    finally:
        os.close(fd)


def dedicated_namespace(root, cfg):
    need(cfg['database'] != root and not cfg['database'].startswith(root + '/'),
         'AUTHORITY_STORE_NOT_REGISTRY_INDEX')


def register(root, binding_file, record_sha256):
    raw, unused = read(binding_file, record_sha256)
    record, cfg = verified_record(raw)
    dedicated_namespace(root, cfg)
    name = record['registration_id'] + '.json'
    with registration_lock(root, True) as directory:
        path = root + '/' + INDEX
        if not os.path.lexists(path):
            db = open_index(root, writer=True, initialize=True)
        else:
            # Validate a pre-existing file through a read-only connection first;
            # never recover or mutate an unrelated/unknown SQLite file.
            check = open_index(root)
            check.close()
            db = open_index(root, writer=True)
        try:
            if os.path.lexists(root + '/' + name):
                prior, unused = read(root + '/' + name, record_sha256)
                need(prior == raw, 'REGISTRATION_CONFLICT')
                committed(db, record['registration_id'], record_sha256, record_info(root, name))
                return {'state': 'ALREADY_REGISTERED', 'record_sha256': record_sha256}
            need(db.execute('SELECT 1 FROM registry_commits WHERE registration_id=?',
                 (record['registration_id'],)).fetchone() is None, 'COMMITTED_RECORD_MISSING')
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                info = private_info(fd)
                view = memoryview(raw)
                while view:
                    count = os.write(fd, view)
                    need(count > 0, 'WRITE_FAILED_HOLD')
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory)
            # All Python-level file/directory fsyncs precede the commit. The
            # SQLite FULL transaction is the final atomic durable publication.
            # There is no failing post-publication fsync or optimistic marker.
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO registry_commits VALUES(?,?,?,?)',
                    (record['registration_id'], record_sha256, info.st_dev, info.st_ino))
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise
            return {'state': 'REGISTERED_SOURCE_BINDING_ONLY', 'record_sha256': record_sha256}
        finally:
            # Failed/partial data remains, but no committed row authorizes it.
            db.close()


def load(root, registration_id, record_sha256):
    need(type(registration_id) is str and IDENTIFIER.fullmatch(registration_id), 'QUERY_ID')
    with registration_lock(root, False):
        db = open_index(root)
        try:
            name = registration_id + '.json'
            info = record_info(root, name)
            committed(db, registration_id, record_sha256, info)
            raw, unused = read(root + '/' + name, record_sha256)
            record, cfg = verified_record(raw)
            dedicated_namespace(root, cfg)
            need(record['registration_id'] == registration_id, 'QUERY_ID_BINDING')
            return record, cfg
        finally:
            db.close()


def require_binding(root, registration_id, record_sha256, config_path, config_sha256):
    record, cfg = load(root, registration_id, record_sha256)
    need(record['config'] == {'path': config_path, 'sha256': config_sha256},
         'EXECUTION_CONFIG_NOT_REGISTERED')
    return cfg


def query(root, registration_id, record_sha256):
    record, cfg = load(root, registration_id, record_sha256)
    return {'schema': 1, 'state': 'ROOT_REGISTERED_SOURCE_BINDINGS_VERIFIED',
            'registration_id': registration_id, 'record_sha256': record_sha256,
            'config_sha256': record['config']['sha256'],
            'issuer_public_der_sha256': digest_value(cfg['public_der_sha256'], 'OUTPUT_DIGEST'),
            'adapter_sha256': digest_value(cfg['adapter_sha256'], 'OUTPUT_DIGEST'),
            'sources': {name: record['sources'][name]['sha256'] for name in KINDS},
            'authority_live_state': 'UNKNOWN', 'writer_fence_live_state': 'UNKNOWN',
            'installation_permission': 'NOT_INFERRED', 'release': 'HOLD'}
