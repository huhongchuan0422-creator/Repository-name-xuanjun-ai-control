"""UK community offline release installation and paired rollback rehearsal.

This installs real source/data generations only inside a new private rehearsal
workspace. It never installs a host service, runs a container, changes a live
pointer, constructs Center, loads credentials or calls a provider. The existing
Center owner supplies both its instance and a matching private backup. A trusted
Python composition callback reuses MiniApplication; there is no plugin/CLI loader.
"""
import ast
import concurrent.futures
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import sys
import zipfile
from contextlib import contextmanager

PURPOSE = 'UK_COMMUNITY_OFFLINE_RELEASE_REHEARSAL'
NAMES = ('orders', 'merchants', 'ads', 'refunds', 'modules', 'saas-orders')
PIN_PATH = 'docs/development/COMMUNITY_PINNED_DEPENDENCIES_20261017.json'
MAX_PACKAGE = 64 * 1024 * 1024


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', value):
        raise ValueError('INVALID_RELEASE_IDENTIFIER')
    return value


def _digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('INVALID_DIGEST')
    return value


def _pointer(value, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not dict or set(value) != {'generation', 'ready_sha256'}:
        raise ValueError('EXACT_GENERATION_PAIR_REQUIRED')
    _id(value['generation']); _digest(value['ready_sha256'])
    return value


def _anchor(value):
    fields = {'database_sha256', 'logical_sha256', 'encrypted_objects_sha256', 'key_ids',
              'index_key_id', 'center_restored_by_this_adapter'}
    if type(value) is not dict or set(value) != fields or value['center_restored_by_this_adapter'] is not False:
        raise ValueError('EXACT_CENTER_ANCHOR_REQUIRED')
    _digest(value['database_sha256']); _digest(value['logical_sha256'])
    if (type(value['key_ids']) is not list or not value['key_ids']
            or any(type(k) is not str for k in value['key_ids'])
            or len(set(value['key_ids'])) != len(value['key_ids'])
            or value['index_key_id'] not in value['key_ids']
            or type(value['encrypted_objects_sha256']) is not dict):
        raise ValueError('EXACT_CENTER_ANCHOR_REQUIRED')
    for name, digest in value['encrypted_objects_sha256'].items():
        _id(name); _digest(digest)
    return value


def _path(path, directory=False):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('SYMLINK_PATH_DENIED')
    info = path.stat()
    wanted = stat.S_ISDIR if directory else stat.S_ISREG
    if not wanted(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise PermissionError('PRIVATE_OWNER_PATH_REQUIRED')
    if not directory and info.st_nlink != 1:
        raise ValueError('LINKED_FILE_DENIED')
    return path


def _read(path, limit=MAX_PACKAGE):
    path = _path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if info.st_size > limit or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('FILE_LIMIT_OR_TYPE')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        live = path.stat(follow_symlinks=False)
        attributes = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if attributes(info) != attributes(after) or attributes(after) != attributes(live):
            raise ValueError('FILE_CHANGED_DURING_READ')
    if len(raw) > limit:
        raise ValueError('FILE_LIMIT')
    return raw


def _write(path, raw):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_file(path, expected):
    """Explicit recovery re-syncs file data, not only its directory entry."""
    path = _path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size != len(expected) or stream.read(len(expected) + 1) != expected):
            raise ValueError('RECOVERY_FILE_CHANGED')
        os.fsync(stream.fileno())
        after = os.fstat(stream.fileno())
        live = path.stat(follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(live):
            raise ValueError('RECOVERY_FILE_CHANGED')


def container_candidate(config):
    """Render a stopped, egress-isolated validation container, not live payment."""
    fields = {'service', 'image', 'python_version', 'uid', 'gid', 'nginx_uid', 'nginx_gid',
              'cpu_millis', 'memory_bytes', 'pids', 'disk_bytes', 'log_bytes',
              'network', 'volumes', 'secret_ref', 'https_origin', 'socket_path',
              'privileged', 'host_network', 'docker_socket', 'center_mode'}
    if type(config) is not dict or set(config) != fields:
        raise ValueError('EXACT_CONTAINER_CONTRACT_REQUIRED')
    if (config['service'] != 'uk-community-payment'
            or config['center_mode'] != 'EXISTING_CENTER_IN_PROCESS'
            or any(config[k] is not False for k in ('privileged', 'host_network', 'docker_socket'))):
        raise ValueError('ORIGINAL_ISOLATION_CONTRACT_REQUIRED')
    if not re.fullmatch(r'[a-z0-9./_-]+@sha256:[0-9a-f]{64}', str(config['image'])):
        raise ValueError('PINNED_IMAGE_REQUIRED')
    if not re.fullmatch(r'3\.(11|12)\.[0-9]+', str(config['python_version'])):
        raise ValueError('EXPLICIT_TESTED_RUNTIME_VERSION_REQUIRED')
    for key in ('uid', 'gid', 'nginx_uid', 'nginx_gid', 'cpu_millis', 'memory_bytes',
                'pids', 'disk_bytes', 'log_bytes'):
        if type(config[key]) is not int or not 0 < config[key] <= 2**63 - 1:
            raise ValueError('POSITIVE_EXPLICIT_RESOURCE_AND_ID_REQUIRED')
    if not re.fullmatch(r'uk-community-payment-[a-z0-9_-]+', str(config['network'])):
        raise ValueError('DEDICATED_NETWORK_REQUIRED')
    volumes = config['volumes']
    if (type(volumes) is not dict or set(volumes) != {'release', 'business', 'objects', 'socket'}
            or len(set(volumes.values())) != 4
            or any(type(v) is not str or not re.fullmatch(r'uk-community-payment-[a-z0-9_-]+', v)
                   for v in volumes.values())):
        raise ValueError('DEDICATED_NAMED_VOLUMES_REQUIRED')
    if not re.fullmatch(r'uk-community-payment-[a-z0-9_-]+', str(config['secret_ref'])):
        raise ValueError('SECRET_REFERENCE_ONLY')
    if (not re.fullmatch(r'https://[A-Za-z0-9.-]+', str(config['https_origin']))
            or config['socket_path'] != '/run/community/mini.sock'):
        raise ValueError('FIXED_HTTPS_AND_PRIVATE_SOCKET_REQUIRED')
    # No published ports, provider egress, restart loop, host mounts or secrets in
    # the validation container. The host must enforce disk quota before live use.
    service = {'image': config['image'], 'user': '%s:%s' % (config['uid'], config['gid']),
               'read_only': True, 'privileged': False, 'cap_drop': ['ALL'],
               'security_opt': ['no-new-privileges:true'], 'restart': 'no',
               'cpus': config['cpu_millis'] / 1000, 'mem_limit': config['memory_bytes'],
               'pids_limit': config['pids'], 'network_mode': 'none',
               'logging': {'driver': 'local', 'options': {'max-size': str(config['log_bytes']), 'max-file': '1'}},
               'volumes': [volumes['release'] + ':/candidate:ro'],
               'entrypoint': ['python', '-I', '-B', '/candidate/source/scripts/community_release_candidate.py',
                              'inspect', '/candidate']}
    return {'purpose': PURPOSE, 'compose': {'services': {'uk-community-payment': service},
            'volumes': {volumes['release']: {'external': True}}},
            'protected_live_contract': config, 'production_enabled': False,
            'host_disk_quota_required_bytes': config['disk_bytes'],
            'image_contents_and_target_runtime_verified': False}


def inspect_package(raw, expected_sha256):
    if type(raw) is not bytes or len(raw) > MAX_PACKAGE or _sha(raw) != _digest(expected_sha256):
        raise ValueError('PACKAGE_DIGEST_OR_LIMIT')
    blobs = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) > 4000 or sum(x.file_size for x in members) > MAX_PACKAGE:
            raise ValueError('PACKAGE_CLOSURE_LIMIT')
        for item in members:
            name = item.filename
            parts = PurePosixPath(name)
            if (not name or parts.is_absolute() or '..' in parts.parts or '\\' in name
                    or str(parts) != name or name in blobs or item.is_dir()
                    or item.flag_bits & 1 or stat.S_IFMT(item.external_attr >> 16) != stat.S_IFREG
                    or item.file_size > 8 * 1024 * 1024):
                raise ValueError('UNSAFE_PACKAGE_MEMBER')
            blobs[name] = archive.read(item)
    manifest = _decode(blobs.pop('MANIFEST.json'))
    if (type(manifest) is not dict or set(manifest) != {'format', 'purpose', 'production_payment', 'production_deployment', 'files'}
            or manifest['format'] != 1 or manifest['purpose'] != 'OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE'
            or manifest['production_payment'] != 'HOLD' or manifest['production_deployment'] != 'HOLD'
            or manifest['files'] != {name: _sha(data) for name, data in blobs.items()}):
        raise ValueError('EXACT_ORIGINAL_PACKAGE_REQUIRED')
    required = {'scripts/community_mini_application.py', 'scripts/community_release_candidate.py',
                'scripts/community_stage_recovery.py', 'scripts/community_mini_http.py', PIN_PATH}
    if not required.issubset(blobs):
        raise ValueError('RELEASE_SOURCE_CLOSURE_REQUIRED')
    pins = _decode(blobs[PIN_PATH])['dependencies']
    if len(pins) != 6 or len({p['path'] for p in pins}) != 6:
        raise ValueError('SIX_ORIGINAL_CENTER_PINS_REQUIRED')
    for pin in pins:
        if _sha(blobs[pin['path']]) != pin['sha256']:
            raise ValueError('ORIGINAL_CENTER_PIN_MISMATCH')
    runtime = ast.parse(blobs['scripts/pr122_customer_runtime.py'])
    wheels = next(ast.literal_eval(n.value) for n in runtime.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'WHEELS' for t in n.targets))
    return blobs, {'format': 'COMMUNITY_SOURCE_SBOM_V1', 'files': manifest['files'],
                   'original_center_dependencies': pins, 'existing_cp311_wheel_pins': wheels,
                   'wheel_target_compatibility': 'NOT_INFERRED_FOR_UK_CONTAINER',
                   'license_and_vulnerability_review': 'SEPARATE_RELEASE_GATE'}


def _logical_database(db):
    if db.in_transaction:
        raise ValueError('COMMITTED_CENTER_REQUIRED')
    if [tuple(row) for row in db.execute('PRAGMA integrity_check')] != [('ok',)]:
        raise ValueError('CENTER_BACKUP_INTEGRITY')
    return _sha('\n'.join(db.iterdump()).encode())


def _objects(path):
    root = _path(path, True)
    result = {}
    for path in sorted(root.iterdir()):
        result[path.name] = _sha(_read(path, 16 * 1024 * 1024))
    return result


def verify_center_backup(center, evidence):
    """Compare actual host-owned private backup bytes and logical live state.

    An arbitrary backup ID is insufficient. No backup is made, changed, imported,
    or restored here; key values never enter receipts. Existing historical keys
    remain the Center owner's responsibility.
    """
    from scripts.pr122_customer_core import Center
    if type(center) is not Center or type(evidence) is not dict or set(evidence) != {'database', 'objects', 'database_sha256'}:
        raise ValueError('ORIGINAL_CENTER_AND_PRIVATE_BACKUP_REQUIRED')
    if center.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0] != '1':
        raise PermissionError('EXISTING_CENTER_MAINTENANCE_REQUIRED')
    backup = _path(evidence['database'])
    live = Path(center.db.execute('PRAGMA database_list').fetchone()[2]).resolve()
    if backup.resolve() == live or Path(evidence['objects']).resolve() == center.objects.resolve():
        raise ValueError('INDEPENDENT_CENTER_BACKUP_REQUIRED')
    if any(os.path.lexists(str(backup) + suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('CLOSED_STANDALONE_CENTER_BACKUP_REQUIRED')
    raw = _read(backup)
    if _sha(raw) != _digest(evidence['database_sha256']):
        raise ValueError('CENTER_BACKUP_DIGEST')
    # Only a closed standalone backup may be read immutable. Recheck its bytes
    # and sidecar absence after the logical read; a live WAL is never ignored.
    saved = sqlite3.connect(backup.as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        logical = _logical_database(saved)
    finally:
        saved.close()
    if (any(os.path.lexists(str(backup) + suffix) for suffix in ('-wal', '-shm', '-journal'))
            or _read(backup) != raw):
        raise ValueError('CENTER_BACKUP_CHANGED_DURING_READ')
    if logical != _logical_database(center.db):
        raise ValueError('CENTER_BACKUP_NOT_SAME_GENERATION')
    objects = _objects(evidence['objects'])
    if objects != _objects(center.objects):
        raise ValueError('CENTER_OBJECT_BACKUP_NOT_SAME_GENERATION')
    center.check_integrity()
    return {'database_sha256': evidence['database_sha256'], 'logical_sha256': logical,
            'encrypted_objects_sha256': objects, 'key_ids': sorted(center.keys),
            'index_key_id': center.index_key, 'center_restored_by_this_adapter': False}


def _application(app, directory=None):
    from scripts.community_mini_application import MiniApplication
    if (type(app) is not MiniApplication or app.stage is None or app.server is not None
            or len(app.stage.handles) != 6
            or getattr(app.gateway, 'payments', None) is not None
            or app.provider_actions is not None or app.fulfillment is not None):
        raise PermissionError('STOPPED_NONMONEY_ORIGINAL_COMPOSITION_REQUIRED')
    stage = app.stage
    runtime = stage.runtime
    if (runtime.demo is not stage.demo or app.gateway.runtime is not runtime
            or app.identity.runtime is not runtime or app.gateway.identity is not app.identity
            or app.identity.center is not app.center or runtime.saas is None
            or (stage.demo.db, stage.demo.merchant_db, stage.demo.ad_db, stage.demo.refund_db,
                runtime.saas.modules, runtime.saas.orders) != tuple(stage.handles)
            or runtime.saas.quotes is not stage.handles[4]):
        raise ValueError('SAME_ORIGINAL_RUNTIME_CONNECTIONS_REQUIRED')
    if directory is not None:
        actual = [Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve() for db in app.stage.handles]
        if actual != [(directory / (n + '.sqlite')).resolve() for n in NAMES]:
            raise ValueError('EXACT_RESTORED_SIX_STORES_REQUIRED')


def probe_original_health(app):
    """Exercise actual original loopback HTTP while Center remains in maintenance."""
    _application(app)
    if app.center.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0] != '1':
        raise PermissionError('MAINTENANCE_REHEARSAL_ONLY')
    server = app.listen()
    try:
        def get():
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            try:
                client.request('GET', '/community/health')
                response = client.getresponse()
                return response.status, _decode(response.read())
            finally:
                client.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(get)
            server.timeout = 3
            server.handle_request()
            status, body = result.result(timeout=5)
        if (status != 503 or body.get('status') != 'MAINTENANCE'
                or body.get('scope') != 'PROCESS_AND_DATABASE_CONNECTIVITY'
                or body.get('production_acceptance') is not False):
            raise ValueError('ORIGINAL_HEALTH_NOT_SAFE')
        return {'http_status': status, 'health': body}
    finally:
        server.server_close()
        app.server = None


def inspect_generation(directory, expected_ready=None):
    root = _path(directory, True)
    ready = _read(root / 'READY', 128).decode()
    if expected_ready is not None and ready != _digest(expected_ready):
        raise ValueError('GENERATION_PAIR_MISMATCH')
    raw = _read(root / 'generation.json')
    if _sha(raw) != ready or (root / 'HOLD').exists():
        raise ValueError('GENERATION_UNREADY')
    record = _decode(raw)
    fields = {'purpose', 'generation', 'source_commit', 'package_sha256', 'center_backup',
              'six_store_snapshot_sha256', 'health', 'files', 'production_installed',
              'live_activation', 'source_commit_binding', 'cross_database_atomic', 'live_writer_fence_verified'}
    if (type(record) is not dict or set(record) != fields or record['purpose'] != PURPOSE
            or record['production_installed'] is not False or record['cross_database_atomic'] is not False
            or record['live_writer_fence_verified'] is not False or record['live_activation'] != 'NOT_IMPLEMENTED'
            or record['source_commit_binding'] != 'CALLER_REFERENCE_PACKAGE_BYTES_VERIFIED'
            or type(record['source_commit']) is not str or not re.fullmatch('[0-9a-f]{40}', record['source_commit'])):
        raise ValueError('OFFLINE_GENERATION_REQUIRED')
    _id(record['generation']); _digest(record['package_sha256'])
    _digest(record['six_store_snapshot_sha256']); _anchor(record['center_backup'])
    if record['health'] != {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}:
        raise ValueError('EXACT_HEALTH_EVIDENCE_REQUIRED')
    expected = record['files']
    if (type(expected) is not dict or len(expected) > 5000
            or not {'sbom.json', 'container.json', 'snapshot/snapshot.json',
                    'source/scripts/community_mini_application.py', *('state/' + n + '.sqlite' for n in NAMES)}.issubset(expected)):
        raise ValueError('EXACT_GENERATION_FILES_REQUIRED')
    if any(p.is_symlink() or not (p.is_dir() or p.is_file()) for p in root.rglob('*')):
        raise ValueError('GENERATION_UNSAFE_OBJECT')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected) | {'READY', 'generation.json'}:
        raise ValueError('GENERATION_FILE_SET_CHANGED')
    for relative, digest in expected.items():
        if type(relative) is not str:
            raise ValueError('INVALID_GENERATION_PATH')
        path = PurePosixPath(relative)
        if (path.is_absolute() or '..' in path.parts or str(path) != relative or '\\' in relative
                or _sha(_read(root / relative)) != _digest(digest)):
            raise ValueError('GENERATION_FILE_CHANGED')
    return record, ready


class OfflineReleases:
    """Persistent private rehearsal generations with lock/CAS and crash receipts."""
    def __init__(self, root, *, create=False):
        self.root = Path(root).absolute()
        if create:
            for part in (self.root, *self.root.parents):
                if part.is_symlink():
                    raise ValueError('SYMLINK_PATH_DENIED')
            self.root.mkdir(mode=0o700)
            _write(self.root / 'workspace.json', _json({'purpose': PURPOSE, 'production': False}))
            (self.root / 'generations').mkdir(mode=0o700)
            (self.root / 'transactions').mkdir(mode=0o700)
            _write(self.root / 'lock', b'')
            _sync(self.root)
        _path(self.root, True)
        if _decode(_read(self.root / 'workspace.json')) != {'purpose': PURPOSE, 'production': False}:
            raise ValueError('NEW_OFFLINE_WORKSPACE_REQUIRED')
        _path(self.root / 'generations', True)
        _path(self.root / 'transactions', True)

    @contextmanager
    def _lock(self):
        fd = os.open(_path(self.root / 'lock'), os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _path(self.root, True)
            _path(self.root / 'generations', True)
            _path(self.root / 'transactions', True)
            yield
        finally:
            os.close(fd)

    def current(self):
        path = self.root / 'current.json'
        return _pointer(_decode(_read(path))) if os.path.lexists(path) else None

    def install(self, generation, raw, expected_sha256, source_commit, application, compose, center_backup, container):
        """Install source + snapshot + restored DBs; READY written only after checks."""
        generation = _id(generation)
        if type(source_commit) is not str or not re.fullmatch('[0-9a-f]{40}', source_commit):
            raise ValueError('EXACT_SOURCE_COMMIT_REQUIRED')
        _application(application)
        blobs, sbom = inspect_package(raw, expected_sha256)
        deployment = container_candidate(container)
        # Never test a different package using the currently imported application.
        source_root = Path(__file__).resolve().parents[1]
        for name, blob in blobs.items():
            if name.startswith('scripts/') and name.endswith('.py'):
                if (source_root / name).read_bytes() != blob:
                    raise ValueError('RUNNING_SOURCE_DOES_NOT_MATCH_CANDIDATE')
        for name, module in list(sys.modules.items()):
            relative = name.replace('.', '/') + '.py'
            if relative in blobs:
                origin = getattr(module, '__file__', None)
                if (origin is None or Path(origin).resolve() != (source_root / relative).resolve()
                        or Path(origin).read_bytes() != blobs[relative]):
                    raise ValueError('IMPORTED_SOURCE_ORIGIN_MISMATCH')
        anchor = verify_center_backup(application.center, center_backup)
        with self._lock():
            root = self.root / 'generations' / generation
            root.mkdir(mode=0o700)
            try:
                source = root / 'source'
                source.mkdir(mode=0o700)
                for name, blob in blobs.items():
                    target = source / name
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    _write(target, blob)
                from scripts.community_stage_recovery import snapshot, restore
                receipt = snapshot(application, root / 'snapshot')
                restore(root / 'snapshot', receipt['manifest_sha256'], root / 'state')
                candidate = compose(application.center, root / 'state')
                try:
                    _application(candidate, root / 'state')
                    if candidate.center is not application.center:
                        raise ValueError('EXISTING_CENTER_INSTANCE_REQUIRED')
                    health = probe_original_health(candidate)
                finally:
                    candidate.close()
                if verify_center_backup(application.center, center_backup) != anchor:
                    raise ValueError('CENTER_CHANGED_DURING_REHEARSAL')
                _write(root / 'sbom.json', _json(sbom))
                _write(root / 'container.json', _json(deployment))
                files = {p.relative_to(root).as_posix(): _sha(_read(p))
                         for p in sorted(root.rglob('*')) if p.is_file()}
                record = {'purpose': PURPOSE, 'generation': generation, 'source_commit': source_commit,
                          'package_sha256': expected_sha256, 'center_backup': anchor,
                          'six_store_snapshot_sha256': receipt['manifest_sha256'], 'health': health,
                          'files': files, 'production_installed': False, 'live_activation': 'NOT_IMPLEMENTED',
                          'source_commit_binding': 'CALLER_REFERENCE_PACKAGE_BYTES_VERIFIED',
                          'cross_database_atomic': False, 'live_writer_fence_verified': False}
                encoded = _json(record)
                _write(root / 'generation.json', encoded)
                for directory in sorted((p for p in root.rglob('*') if p.is_dir()),
                                        key=lambda p: len(p.parts), reverse=True):
                    _sync(directory)
                _write(root / 'READY', _sha(encoded).encode())
                _sync(root)
                _sync(root.parent)
                return {'generation': generation, 'ready_sha256': _sha(encoded)}
            except BaseException as error:
                _write(root / 'HOLD', _json({'error_type': type(error).__name__, 'retry_same_generation': False}))
                _sync(root)
                raise

    def select(self, target, expected_current, transaction, center, center_backup, *, rollback_of=None):
        """Atomically select an offline source/data pair; never start its writer."""
        transaction = _id(transaction)
        _pointer(target); _pointer(expected_current, True)
        generation = _id(target['generation'])
        with self._lock():
            for prior in (self.root / 'transactions').iterdir():
                if self.transaction(prior.name)['state'] not in ('COMMITTED', 'ABORTED', 'RECOVERED_COMMITTED', 'RECOVERED_ABORTED'):
                    raise ValueError('UNRESOLVED_TRANSACTION_HOLD')
            current = self.current()
            if current != expected_current:
                raise ValueError('OFFLINE_SELECTION_CAS_MISMATCH')
            if target == current:
                raise ValueError('ALREADY_SELECTED')
            if current is not None:
                previous, _ = inspect_generation(self.root / 'generations' / current['generation'],
                                                 current['ready_sha256'])
                if previous['generation'] != current['generation']:
                    raise ValueError('CURRENT_GENERATION_IDENTITY_MISMATCH')
            record, ready = inspect_generation(self.root / 'generations' / generation, target['ready_sha256'])
            if record['generation'] != generation:
                raise ValueError('GENERATION_IDENTITY_MISMATCH')
            if verify_center_backup(center, center_backup) != record['center_backup']:
                raise ValueError('SOURCE_DATA_CENTER_PAIR_MISMATCH')
            if rollback_of is not None:
                prior = self.transaction(rollback_of)
                if prior['state'] not in ('COMMITTED', 'RECOVERED_COMMITTED') or prior['to'] != current or prior['from'] != target:
                    raise ValueError('EXACT_PREVIOUS_PAIR_REQUIRED')
            path = self.root / 'transactions' / transaction
            path.mkdir(mode=0o700)
            intent = {'transaction': transaction, 'from': current, 'to': target, 'rollback_of': rollback_of}
            try:
                _write(path / 'intent.json', _json(intent))
                _sync(path)
                _sync(path.parent)
                # Intent is durable before the single atomic source+data pointer.
                _write(path / 'selection.json', _json(target))
                self._before_select()
                os.replace(path / 'selection.json', self.root / 'current.json')
                _sync(self.root)
                self._after_select()
                self._complete(path, intent, 'COMMITTED')
            except BaseException as error:
                self._hold(path, error)
                raise
            return self.transaction(transaction)

    def _hold(self, path, error):
        # A visible completion marker is insufficient after an observed sync
        # failure. Preserve a conservative HOLD, even when directory sync itself
        # is unavailable; never report that the HOLD was durably persisted.
        try:
            if not os.path.lexists(path / 'HOLD'):
                _write(path / 'HOLD', _json({'status': 'DURABILITY_UNKNOWN', 'error_type': type(error).__name__}))
            _sync(path)
        except BaseException:
            pass

    def _complete(self, path, intent, marker):
        digest = _sha(_json(intent)).encode()
        if os.path.lexists(path / marker):
            _sync_file(path / marker, digest)
        else:
            _write(path / marker, digest)
        _sync(path)
        if os.path.lexists(path / 'HOLD'):
            _read(path / 'HOLD')
            (path / 'HOLD').unlink()
            _sync(path)

    def resolve_transaction(self, transaction, center, center_backup):
        """Explicitly reconcile a durable crash intent, without changing selection."""
        transaction = _id(transaction)
        with self._lock():
            report = self.transaction(transaction)
            if report['state'] not in ('SELECTED_RECEIPT_PENDING_HOLD', 'NOT_SELECTED_HOLD'):
                raise ValueError('NO_RESOLVABLE_SELECTION_INTENT')
            selected = self.current()
            if selected is not None:
                record, _ = inspect_generation(self.root / 'generations' / _id(selected['generation']),
                                               selected['ready_sha256'])
                if record['generation'] != selected['generation']:
                    raise ValueError('CURRENT_GENERATION_IDENTITY_MISMATCH')
                if verify_center_backup(center, center_backup) != record['center_backup']:
                    raise ValueError('SOURCE_DATA_CENTER_PAIR_MISMATCH')
            else:
                verify_center_backup(center, center_backup)
            path = self.root / 'transactions' / transaction
            intent = _decode(_read(path / 'intent.json'))
            marker = 'COMMITTED' if report['state'] == 'SELECTED_RECEIPT_PENDING_HOLD' else 'ABORTED'
            try:
                recovery = {'outcome': marker, 'observed_state': report['state'],
                            'action': 'RECONCILE_WITHOUT_POINTER_WRITE', 'original_call_success_proven': False}
                if os.path.lexists(path / 'RECOVERED.json'):
                    if _decode(_read(path / 'RECOVERED.json')) != recovery:
                        raise ValueError('RECOVERY_RECORD_CHANGED')
                else:
                    _write(path / 'RECOVERED.json', _json(recovery))
                # An earlier failure may have left any of these files visible
                # without durable data. This is a new explicit reconciliation,
                # never proof that the original invocation returned success.
                _sync_file(path / 'intent.json', _json(intent))
                if selected is not None:
                    _sync_file(self.root / 'current.json', _json(selected))
                _sync(self.root)
                _sync(path.parent)
                _sync_file(path / 'RECOVERED.json', _json(recovery))
                self._complete(path, intent, marker)
            except BaseException as error:
                self._hold(path, error)
                raise
            return self.transaction(transaction)

    def _before_select(self):
        pass

    def _after_select(self):
        pass

    def transaction(self, transaction):
        """Read-only crash diagnosis; never replay an uncertain selection."""
        path = _path(self.root / 'transactions' / _id(transaction), True)
        intent = _decode(_read(path / 'intent.json'))
        if (type(intent) is not dict or set(intent) != {'transaction', 'from', 'to', 'rollback_of'}
                or intent['transaction'] != transaction or intent['to'] == intent['from']):
            raise ValueError('EXACT_TRANSACTION_INTENT_REQUIRED')
        _pointer(intent['from'], True); _pointer(intent['to'])
        if intent['rollback_of'] is not None:
            _id(intent['rollback_of'])
        names = {p.name for p in path.iterdir()}
        if (not names.issubset({'intent.json', 'selection.json', 'COMMITTED', 'ABORTED', 'HOLD', 'RECOVERED.json'})
                or {'COMMITTED', 'ABORTED'}.issubset(names)):
            raise ValueError('TRANSACTION_FILE_SET_CHANGED')
        if 'selection.json' in names and _pointer(_decode(_read(path / 'selection.json'))) != intent['to']:
            raise ValueError('TRANSACTION_SELECTION_CHANGED')
        current = self.current()
        marker = 'COMMITTED' if (path / 'COMMITTED').exists() else 'ABORTED' if (path / 'ABORTED').exists() else None
        hold = 'HOLD' in names
        if hold:
            value = _decode(_read(path / 'HOLD'))
            if (type(value) is not dict or set(value) != {'status', 'error_type'}
                    or value['status'] != 'DURABILITY_UNKNOWN' or type(value['error_type']) is not str):
                raise ValueError('EXACT_HOLD_REQUIRED')
        if marker is not None:
            if _read(path / marker).decode() != _sha(_json(intent)):
                raise ValueError('TRANSACTION_RECEIPT_CHANGED')
        recovered = 'RECOVERED.json' in names
        if recovered:
            recovery = _decode(_read(path / 'RECOVERED.json'))
            if (type(recovery) is not dict or set(recovery) != {'outcome', 'observed_state', 'action', 'original_call_success_proven'}
                    or recovery['outcome'] not in ('COMMITTED', 'ABORTED')
                    or recovery['observed_state'] != ('SELECTED_RECEIPT_PENDING_HOLD' if recovery['outcome'] == 'COMMITTED' else 'NOT_SELECTED_HOLD')
                    or recovery['action'] != 'RECONCILE_WITHOUT_POINTER_WRITE'
                    or recovery['original_call_success_proven'] is not False
                    or marker is not None and recovery['outcome'] != marker):
                raise ValueError('EXACT_RECOVERY_RECORD_REQUIRED')
        if marker is not None and not hold:
            state = ('RECOVERED_' if recovered else '') + marker
        elif current == intent['to']:
            state = 'SELECTED_RECEIPT_PENDING_HOLD'
        elif current == intent['from']:
            state = 'NOT_SELECTED_HOLD'
        else:
            state = 'UNKNOWN_HOLD'
        return {**intent, 'state': state, 'production_changed': False, 'automatic_retry': False,
                'original_call_success_proven': False, 'completion_record_present': marker is not None,
                'recovered': recovered,
                'observed_durability': 'UNKNOWN' if hold or marker is None else 'COMPLETION_RECORD_PRESENT'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Inspect one stopped offline release; no live install command')
    parser.add_argument('action', choices=['inspect'])
    parser.add_argument('generation')
    args = parser.parse_args()
    record, ready = inspect_generation(args.generation)
    print(json.dumps({'generation': record['generation'], 'ready_sha256': ready,
                      'offline_files_verified': True, 'production_installed': False}, sort_keys=True))
