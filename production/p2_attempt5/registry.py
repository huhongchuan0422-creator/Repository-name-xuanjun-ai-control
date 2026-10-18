"""Root-managed immutable configuration source registry. Not an execution permit.

No SQLite, Grant registration, Writer lease acquisition, private key read,
adapter execution, directory creation, overwrite or recursive discovery.
"""
import hashlib
import json
import os
import re
import stat

DEFAULT_ROOT = '/etc/xuanjun-p2/registry'
BOUND = 65536
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
             source['source_id'] != 'UNKNOWN' and source['subject'] == wanted[name],
             'SOURCE_BINDING')
    # Source IDs are root-admin provenance references, not independent live
    # transaction attestations. No lease/fence validity is inferred here.
    need(canonical(record) == raw, 'CANONICAL_RECORD_REQUIRED')
    return record, cfg


def register(root, binding_file, record_sha256):
    raw, unused = read(binding_file, record_sha256)
    record, cfg = verified_record(raw)
    directory = root_fd(root)
    name = record['registration_id'] + '.json'
    try:
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=directory)
        except FileExistsError:
            prior, unused = read(root + '/' + name, record_sha256)
            need(prior == raw, 'REGISTRATION_CONFLICT')
            return {'state': 'ALREADY_REGISTERED', 'record_sha256': record_sha256}
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                need(count > 0, 'WRITE_FAILED_HOLD')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        return {'state': 'REGISTERED_SOURCE_BINDING_ONLY', 'record_sha256': record_sha256}
    finally:
        # Keep partial output on every failure. Never unlink/recreate history.
        os.close(directory)


def load(root, registration_id, record_sha256):
    need(type(registration_id) is str and IDENTIFIER.fullmatch(registration_id), 'QUERY_ID')
    directory = root_fd(root)
    os.close(directory)
    raw, unused = read(root + '/' + registration_id + '.json', record_sha256)
    record, cfg = verified_record(raw)
    need(record['registration_id'] == registration_id, 'QUERY_ID_BINDING')
    return record, cfg


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
            'issuer_public_der_sha256': cfg['public_der_sha256'],
            'adapter_sha256': cfg['adapter_sha256'],
            'sources': {name: record['sources'][name]['sha256'] for name in KINDS},
            'authority_live_state': 'UNKNOWN', 'writer_fence_live_state': 'UNKNOWN',
            'installation_permission': 'NOT_INFERRED', 'release': 'HOLD'}
