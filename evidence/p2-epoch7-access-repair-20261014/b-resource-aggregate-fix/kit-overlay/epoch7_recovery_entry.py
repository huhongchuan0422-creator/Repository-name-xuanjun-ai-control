#!/usr/bin/env python3
"""Protected epoch7 source-kit loader with explicit approval-gated composition.

The interpreter/stdlib and this entry's independently checked SHA are bootstrap
trust. Invoke with -I -B -S. All candidate bytes are verified before candidate
imports, and Python sources execute from the verified in-memory snapshot.
"""
import argparse
import contextlib
import errno
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import re
import stat
import sys

ENTRY = 'epoch7_recovery_entry.py'
MANIFEST = 'recovery-kit-manifest.json'
RUNTIME = 'xuanjun-p2-package/'
SHA = re.compile(r'^[0-9a-f]{64}$')
NAME = re.compile(r'^[a-z_][a-z0-9_]*$')
MAX_FILE = 16 * 1024 * 1024
MAX_PRIVATE_SEED = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_FILES = 1024
MAX_DIRS = 1024
BOOTSTRAP_PATH = tuple(sys.path)
RESUME_REFUSED = 'REFUSED_UNCOMPOSED'
RESUME_COMPOSED = 'AUTHENTICATED_APPROVAL_GATED_SINGLE_ATTEMPT'
MODE_STATUS = {RESUME_REFUSED: 'SOURCE_KIT_GROUNDWORK_NOT_INSTALL_ADMISSION',
               RESUME_COMPOSED: 'COMPOSED_CANDIDATE_REQUIRES_FRESH_APPROVAL'}
CANDIDATE_PARENT = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
FIXED_HOST = 'iZd7oeikknn1z21sq6ji6zZ'
PROBE_RECEIPT_PARENT = '/run'
MAX_PROBE_RECEIPT = 128 * 1024
PRIVATE_RAW_FIELDS = frozenset(('native_before', 'tls_journal_before', 'prior_provision_bytes',
    'legacy_units_raw', 'publisher_journal_raw', 'sandbox_candidate_raw'))
PRIVATE_SEED_FIELDS = PRIVATE_RAW_FIELDS | frozenset(('observation', 'compiled',
    'additive_deltas', 'identity_payloads', 'activate_retained_renewal_timer', 'fresh_release_parent'))
CACHE_SEED_FIELDS = frozenset(('installer_source', 'source_manifest_raw', 'source_payloads',
                              'artifact', 'kit_manifest_sha256'))
IDENTITY_PATHS = frozenset(('/etc/xuanjun-development/p2-owner-process-identity.json',
                          '/etc/xuanjun-development/p2-ledger-server-identity.json'))
COMPOSITION_MODULES = ('epoch7_host_factory', 'epoch7_recovery_sequence',
                       'epoch7_complete_approval', 'epoch7_snapshot', 'node_sqlite_probe')


def need(value, reason):
    if not value: raise ValueError('EPOCH7_KIT_' + reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def same_json(left, right):
    """Typed canonical comparison (JSON true must never equal integer one)."""
    def packed(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                          allow_nan=False)
    return packed(left) == packed(right)


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: need(False, 'NONFINITE_JSON'))


def relative(name):
    need(type(name) is str and 0 < len(name) <= 512 and
         re.fullmatch(r'[A-Za-z0-9_.\-/]+', name) and
         all(part not in ('', '.', '..') for part in name.split('/')),
         'UNSAFE_RELATIVE_PATH')
    need(not any(part == '__pycache__' or part.endswith(('.pyc', '.pyo'))
                 for part in name.split('/')), 'BYTECODE_FORBIDDEN')
    return name


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def directories(paths):
    result = set()
    for name in paths:
        parts = relative(name).split('/')
        for index in range(1, len(parts)): result.add('/'.join(parts[:index]))
    return result


class DescriptorTree(object):
    """No-follow openat traversal; pinned descriptors and parent bindings.

    Production passes only (0,0). Offline builder/tests explicitly pass local
    identities. No CLI flag changes production authority.
    """
    def __init__(self, root, owners=((0, 0),)):
        need(type(root) is str and root.startswith('/') and root != '/' and
             os.path.normpath(root) == root and not root.endswith('/'), 'ABSOLUTE_ROOT')
        self.root, self.owners = root, tuple(owners)
        self.opened = []
        self.by_path = {}
        self.closed = False
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._remember(fd, None, None, '/')
            path = ''
            for part in root[1:].split('/'):
                path += '/' + part
                parent = fd
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent)
                self._remember(fd, parent, part, path)
            self.fd = fd
        except BaseException:
            self.close()
            raise

    def _authority(self, fd, directory, maximum=MAX_FILE):
        info = os.fstat(fd)
        need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
             and (info.st_uid, info.st_gid) in self.owners and
             not info.st_mode & 0o7022, 'UNTRUSTED_AUTHORITY')
        if not directory:
            need(info.st_nlink == 1 and 0 <= info.st_size <= maximum, 'FILE_AUTHORITY')
        for key in ('system.posix_acl_access', 'system.posix_acl_default'):
            try:
                value = os.getxattr(fd, key)
            except OSError as error:
                need(error.errno in (errno.ENODATA, errno.ENOTSUP), 'ACL_READ_FAILED')
            else:
                need(False, 'UNREVIEWED_ACL')
        return info

    def _remember(self, fd, parent, name, logical):
        # Remember first so constructor failure also closes this descriptor.
        row = [fd, parent, name, logical, None]
        self.opened.append(row)
        row[4] = stamp(self._authority(fd, True))
        self.by_path[logical] = fd
        if parent is not None:
            need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == row[4],
                 'DIRECTORY_BINDING_RACE')
        return fd

    def parent(self, name):
        parts = relative(name).split('/')
        fd = self.fd
        logical = self.root
        for part in parts[:-1]:
            logical += '/' + part
            if logical in self.by_path:
                fd = self.by_path[logical]
            else:
                candidate = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=fd)
                fd = self._remember(candidate, fd, part, logical)
        return fd, parts[-1]

    def read(self, name, max_bytes=MAX_FILE, private=False):
        need(type(max_bytes) is int and 0 < max_bytes <= (MAX_PRIVATE_SEED if private else MAX_FILE),
             'FILE_BOUND')
        parent, leaf = self.parent(name)
        before_path = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = self._authority(fd, False, MAX_PRIVATE_SEED if private else MAX_FILE)
            need(before.st_size <= max_bytes, 'FILE_BOUND')
            need(not private or stat.S_IMODE(before.st_mode) == 0o600, 'PRIVATE_FILE_MODE')
            need(stamp(before_path) == stamp(before), 'OPEN_RACE')
            chunks, count = [], 0
            while True:
                chunk = os.read(fd, min(65536, max_bytes + 1 - count))
                if not chunk: break
                chunks.append(chunk); count += len(chunk)
                need(count <= max_bytes, 'FILE_BOUND')
            after = self._authority(fd, False, MAX_PRIVATE_SEED if private else MAX_FILE)
            linked = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            need(stamp(before) == stamp(after) == stamp(linked) and
                 count == before.st_size, 'READ_RACE')
            return b''.join(chunks)
        finally:
            os.close(fd)

    def inventory(self):
        files, dirs = set(), set()
        def walk(fd, prefix):
            before = stamp(self._authority(fd, True))
            names = os.listdir(fd)
            need(len(names) <= MAX_FILES, 'DIRECTORY_BOUND')
            for name in sorted(names):
                logical = prefix + name
                relative(logical)
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    dirs.add(logical); need(len(dirs) <= MAX_DIRS, 'DIRECTORY_BOUND')
                    absolute = self.root + '/' + logical
                    if absolute in self.by_path:
                        child = self.by_path[absolute]
                    else:
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=fd)
                        self._remember(child, fd, name, absolute)
                    walk(child, logical + '/')
                else:
                    need(stat.S_ISREG(info.st_mode), 'NONREGULAR_CONTENT')
                    files.add(logical); need(len(files) <= MAX_FILES, 'FILE_COUNT_BOUND')
            need(before == stamp(self._authority(fd, True)), 'INVENTORY_RACE')
        walk(self.fd, '')
        return files, dirs

    def recheck(self):
        for fd, parent, name, logical, before in self.opened:
            need(before == stamp(self._authority(fd, True)), 'ANCESTRY_RACE')
            if parent is not None:
                need(before == stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                     'ANCESTRY_BINDING_RACE')

    def close(self):
        if not self.closed:
            for row in reversed(self.opened): os.close(row[0])
            self.closed = True

    def __enter__(self): return self
    def __exit__(self, *unused): self.close()


def validate_manifest(value):
    need(type(value) is dict and set(value) == {'schema', 'epoch', 'status', 'files',
         'modules', 'test_suites', 'runtime_manifest_sha256', 'runtime_source_commit',
         'runtime_source_tree', 'kit_source_commit', 'kit_source_tree', 'production_resume'}, 'MANIFEST_SCHEMA')
    need(type(value['schema']) is int and value['schema'] == 1 and
         type(value['epoch']) is int and value['epoch'] == 7 and
         type(value['production_resume']) is str and value['production_resume'] in MODE_STATUS and
         value['status'] == MODE_STATUS[value['production_resume']] and
         type(value['runtime_manifest_sha256']) is str and SHA.fullmatch(value['runtime_manifest_sha256']) and
         all(type(value[key]) is str and re.fullmatch(r'[0-9a-f]{40}', value[key]) for key in
             ('runtime_source_commit','runtime_source_tree','kit_source_commit','kit_source_tree')),
         'EXACT_SCOPE')
    files = value['files']
    need(type(files) is dict and 1 <= len(files) < MAX_FILES and ENTRY in files and
         MANIFEST not in files, 'FILE_SCOPE')
    for name, wanted in files.items():
        relative(name)
        need(type(wanted) is str and SHA.fullmatch(wanted), 'FILE_DIGEST')
    need(not set(files) & directories(files), 'FILE_DIRECTORY_COLLISION')
    modules = value['modules']
    need(type(modules) is dict and 1 <= len(modules) <= 256, 'MODULE_SCOPE')
    for name, path in modules.items():
        need(type(name) is str and NAME.fullmatch(name) and path in files and
             path.endswith('/' + name + '.py') and
             (path.startswith('helpers/') or path.startswith(RUNTIME + 'stage1/')),
             'MODULE_PATH')
    need(len(set(modules.values())) == len(modules), 'MODULE_ALIAS')
    suites = value['test_suites']
    need(type(suites) is dict and 1 <= len(suites) <= 64, 'TEST_SCOPE')
    for name, suite in suites.items():
        need(type(name) is str and NAME.fullmatch(name) and type(suite) is dict and
             set(suite) == {'tests', 'imports', 'enabled', 'reason'} and
             type(suite['enabled']) is bool and type(suite['reason']) is str and
             type(suite['tests']) is list and 1 <= len(suite['tests']) <= 64 and
             type(suite['imports']) is dict, 'TEST_SUITE_SCHEMA')
        need(len(set(suite['tests'])) == len(suite['tests']), 'DUPLICATE_TEST')
        for path in suite['tests']:
            need(path in files and path.startswith('tests/' + name + '/') and
                 re.fullmatch(r'test_[a-z0-9_]+\.py', path.split('/')[-1]), 'TEST_PATH')
        for alias, path in suite['imports'].items():
            need(type(alias) is str and NAME.fullmatch(alias) and alias.startswith('test_') and
                 path in files and path.startswith('tests/') and
                 path.endswith('/' + alias + '.py'), 'TEST_IMPORT')
        need(set(suite['tests']) <= set(suite['imports'].values()), 'TEST_IMPORT_SCOPE')
    candidates = {path for path in files if path.endswith('.py') and
                  (path.startswith('helpers/') or path.startswith(RUNTIME + 'stage1/'))}
    need(set(modules.values()) == candidates, 'EXACT_IMPORTABLE_MODULE_SET')
    if value['production_resume'] == RESUME_COMPOSED:
        need(all(modules.get(name) == 'helpers/' + name + '.py' for name in COMPOSITION_MODULES),
             'COMPOSITION_MODULES_REQUIRED')
        need(RUNTIME + 'scripts/uk-integration-install.py' in files, 'COMPOSITION_INSTALLER_REQUIRED')
    return value


PUBLIC_SERVICE_FIXTURE = 'tests/service_contract/fixtures/public-service-units.json'
PUBLIC_OPENCLAW_FIXTURE = 'tests/service_contract/fixtures/openclaw-source-profile.json'
PUBLIC_OPENCLAW_DIRECT_FIXTURE = 'tests/service_contract/fixtures/openclaw-direct-source-profile.json'
PUBLIC_OPENCLAW_DIRECT_PATH = 'dist/is-main-DYSvvM1W.mjs'
PUBLIC_OPENCLAW_DIRECT_SHA = 'cedd59a24eadaaf873515fabea73b776a66d40773c8ee5298f4946b9eef10469'
PUBLIC_OPENCLAW_LICENSE = 'tests/service_contract/fixtures/openclaw-LICENSE.txt'
PUBLIC_OPENCLAW_NOTICES = 'tests/service_contract/fixtures/openclaw-THIRD_PARTY_NOTICES.md'
PUBLIC_FIXTURE_SOURCES = {
    target: 'p2-epoch7-repair/sequence-candidate/fixtures/' + target.rsplit('/', 1)[1]
    for target in (PUBLIC_SERVICE_FIXTURE, PUBLIC_OPENCLAW_FIXTURE, PUBLIC_OPENCLAW_DIRECT_FIXTURE,
                   PUBLIC_OPENCLAW_LICENSE, PUBLIC_OPENCLAW_NOTICES)}
PUBLIC_SERVICE_UNITS = {
    '/etc/systemd/system/' + name: 'deploy/' + name for name in (
        'xj-root-broker.service', 'xj-root-broker.socket',
        'xuanjun-development-dispatcher.service', 'xuanjun-github-intake.service',
        'xuanjun-github-intake.timer', 'xuanjun-ledger.service', 'xuanjun-ledger.socket',
        'xuanjun-p2-gateway-relay.service', 'xuanjun-p2-gateway-relay.socket',
        'xuanjun-p2-tls-renew.service', 'xuanjun-p2-tls-renew.timer')}
PUBLIC_SERVICE_UNITS.update({
    '/etc/systemd/system/nginx.service': 'deploy/p2-nginx.service',
    '/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf': 'deploy/xuanjun-uk-openclaw-p2-docker.conf',
    '/etc/systemd/system/xuanjun-uk-owner-callback.service': 'deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service',
    '/etc/systemd/system/xuanjun-uk-owner-dashboard.service': 'deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service'})


def validate_public_service_fixture(value, cache):
    """Public unit fixtures contain only current runtime-derived bytes."""
    if PUBLIC_SERVICE_FIXTURE not in cache: return
    fixture = decode(cache[PUBLIC_SERVICE_FIXTURE])
    need(type(fixture) is dict and set(fixture) == {'schema', 'kind', 'host_evidence',
        'production_admission', 'runtime_manifest_raw', 'runtime_manifest_sha256',
        'runtime_source_commit', 'runtime_source_tree', 'units'}, 'PUBLIC_FIXTURE_SCHEMA')
    need(type(fixture['schema']) is int and fixture['schema'] == 1 and
        fixture['kind'] == 'PUBLIC_CURRENT_RUNTIME_SERVICE_TEST_FIXTURE' and
        fixture['host_evidence'] == 'NONE_SYNTHETIC_TESTS_ONLY' and
        fixture['production_admission'] is False and
        all(fixture[key] == value[key] for key in ('runtime_manifest_sha256',
            'runtime_source_commit', 'runtime_source_tree')) and
        type(fixture['runtime_manifest_raw']) is str and
        fixture['runtime_manifest_raw'].encode('utf-8') == cache[RUNTIME + 'deploy/integration-manifest.json'],
        'PUBLIC_FIXTURE_RUNTIME')
    need(type(fixture['units']) is dict and set(fixture['units']) == set(PUBLIC_SERVICE_UNITS),
         'PUBLIC_FIXTURE_UNITS')
    digest = value['runtime_manifest_sha256']
    for target, source in PUBLIC_SERVICE_UNITS.items():
        row = fixture['units'][target]
        need(type(row) is dict and set(row) == {'source', 'source_sha256', 'template', 'rendered'} and
             row['source'] == source, 'PUBLIC_FIXTURE_ROW')
        original = cache[RUNTIME + source]
        need(type(row['template']) is str and row['template'].encode('utf-8') == original and
             row['source_sha256'] == sha(original), 'PUBLIC_FIXTURE_SOURCE')
        rendered = row['template'].replace('@@RELEASE_DIRECTORY@@', 'integration-' + digest[:16]).replace(
            '@@RELEASE@@', '/opt/xuanjun-control-releases/integration-' + digest[:16]).replace('@@ARTIFACT_SHA256@@', digest)
        need(row['rendered'] == rendered, 'PUBLIC_FIXTURE_RENDERED')


def validate_public_openclaw_fixture(cache):
    """Review-only public bytes; parse literal pins without importing the recipe."""
    names = {PUBLIC_OPENCLAW_FIXTURE, PUBLIC_OPENCLAW_LICENSE, PUBLIC_OPENCLAW_NOTICES}
    if not (names | {PUBLIC_OPENCLAW_DIRECT_FIXTURE}).intersection(cache): return
    need(names <= set(cache) and 'helpers/epoch7_openclaw_recipe.py' in cache,
         'PUBLIC_OPENCLAW_COMPLETE_SET')
    import ast
    import base64
    constants = {}
    wanted = {'VERSION', 'UPSTREAM', 'TARBALL', 'SOURCE_HASHES'}
    for node in ast.parse(cache['helpers/epoch7_openclaw_recipe.py']).body:
        if isinstance(node, ast.Assign):
            matched = [target.id for target in node.targets if isinstance(target, ast.Name) and target.id in wanted]
            if matched:
                need(len(matched) == 1 and len(node.targets) == 1 and matched[0] not in constants,
                     'PUBLIC_OPENCLAW_LITERAL_PINS')
                constants[matched[0]] = ast.literal_eval(node.value)
                if matched[0] == 'SOURCE_HASHES':
                    need(isinstance(node.value, ast.Dict) and len(node.value.keys) == 31,
                         'PUBLIC_OPENCLAW_EXACT_SOURCE_COUNT')
    need(set(constants) == wanted and constants['VERSION'] == '2026.9.9' and
         constants['UPSTREAM'] == 'bcfc88812a35243893585dbeca87ca41b48272ca' and
         constants['TARBALL'] == 'a46df5fc5e4d73837d5b3eeebc286e64a85dffc429c30f3a07f6398e2a9423f7',
         'PUBLIC_OPENCLAW_OFFICIAL_PROFILE')
    pins = constants['SOURCE_HASHES']
    need(type(pins) is dict and len(pins) == 31, 'PUBLIC_OPENCLAW_EXACT_SOURCE_COUNT')
    for name, pin in pins.items():
        relative(name)
        need(type(pin) is str and SHA.fullmatch(pin), 'PUBLIC_OPENCLAW_SOURCE_PIN')
    fixture = decode(cache[PUBLIC_OPENCLAW_FIXTURE])
    need(type(fixture) is dict and set(fixture) == {'schema', 'fixture_scope', 'version',
         'upstream_commit', 'npm_tar_sha256', 'files'} and type(fixture['schema']) is int and
         fixture['schema'] == 1 and fixture['fixture_scope'] == 'OFFICIAL_SOURCE_BYTES_ONLY_NOT_UK_EVIDENCE' and
         fixture['version'] == constants['VERSION'] and fixture['upstream_commit'] == constants['UPSTREAM'] and
         fixture['npm_tar_sha256'] == constants['TARBALL'] and type(fixture['files']) is dict and
         set(fixture['files']) == set(pins), 'PUBLIC_OPENCLAW_FIXTURE_SCHEMA')
    total = 0
    for name, row in fixture['files'].items():
        need(type(row) is dict and set(row) == {'content_base64', 'sha256'} and
             type(row['content_base64']) is str and len(row['content_base64']) <= 2 * 1024 * 1024 and
             row['sha256'] == pins[name], 'PUBLIC_OPENCLAW_SOURCE_ROW')
        data = base64.b64decode(row['content_base64'].encode('ascii'), validate=True)
        total += len(data)
        need(total <= 1024 * 1024 and base64.b64encode(data).decode('ascii') == row['content_base64'] and
             sha(data) == pins[name], 'PUBLIC_OPENCLAW_SOURCE_BYTES')
    need(sha(cache[PUBLIC_OPENCLAW_LICENSE]) ==
         '73571b25326281d369087f469842c02444fe39faaecebda4d82ed21ff3a1c29d',
         'PUBLIC_OPENCLAW_LICENSE')
    need(sha(cache[PUBLIC_OPENCLAW_NOTICES]) ==
         'c1d1bbc550feee74853eba104e347341569cbbbe37a9f77659993ca0766277d5',
         'PUBLIC_OPENCLAW_NOTICES')
    if PUBLIC_OPENCLAW_DIRECT_FIXTURE in cache:
        extension={PUBLIC_OPENCLAW_DIRECT_PATH:PUBLIC_OPENCLAW_DIRECT_SHA}
        assignments=[node for node in ast.parse(cache['helpers/epoch7_openclaw_recipe.py']).body
            if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='DIRECT_SOURCE_HASHES'
                                                  for target in node.targets)]
        need(len(assignments)==1,'PUBLIC_OPENCLAW_DIRECT_ASSIGNMENT')
        node=assignments[0];call=node.value
        need(len(node.targets)==1 and isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and
             call.func.id=='dict' and len(call.args)==1 and isinstance(call.args[0],ast.Name) and
             call.args[0].id=='SOURCE_HASHES' and len(call.keywords)==1 and call.keywords[0].arg is None and
             isinstance(call.keywords[0].value,ast.Dict) and len(call.keywords[0].value.keys)==1 and
             ast.literal_eval(call.keywords[0].value)==extension,'PUBLIC_OPENCLAW_DIRECT_LITERAL_PIN')
        direct=decode(cache[PUBLIC_OPENCLAW_DIRECT_FIXTURE])
        need(type(direct) is dict and set(direct)=={'extends','fixture_scope','npm_tar_sha256','files'} and
             direct['extends']=='openclaw-source-profile.json' and direct['fixture_scope']==fixture['fixture_scope'] and
             direct['npm_tar_sha256']==constants['TARBALL'] and type(direct['files']) is dict and
             set(direct['files'])=={PUBLIC_OPENCLAW_DIRECT_PATH},'PUBLIC_OPENCLAW_DIRECT_SCHEMA')
        row=direct['files'][PUBLIC_OPENCLAW_DIRECT_PATH]
        need(type(row) is dict and set(row)=={'content_base64','sha256'} and row['sha256']==PUBLIC_OPENCLAW_DIRECT_SHA and
             type(row['content_base64']) is str and len(row['content_base64'])==1948,'PUBLIC_OPENCLAW_DIRECT_ROW')
        content=base64.b64decode(row['content_base64'].encode('ascii'),validate=True)
        need(len(content)==1461 and base64.b64encode(content).decode('ascii')==row['content_base64'] and
             sha(content)==PUBLIC_OPENCLAW_DIRECT_SHA,'PUBLIC_OPENCLAW_DIRECT_BYTES')


def validate_runtime(value, cache):
    """Pure package/provenance linkage; no network provenance claim."""
    runtime_raw = cache[RUNTIME + 'deploy/integration-manifest.json']
    need(sha(runtime_raw) == value['runtime_manifest_sha256'], 'RUNTIME_MANIFEST')
    runtime = decode(runtime_raw)
    need(type(runtime) is dict and type(runtime.get('files')) is dict and
         len(runtime['files']) == 107, 'RUNTIME_COUNT')
    runtime_names = set(runtime['files']) | {'deploy/integration-manifest.json',
        'P2_PACKAGE_PROVENANCE.json', 'tools/p2-package-freeze.py'}
    need({name[len(RUNTIME):] for name in cache if name.startswith(RUNTIME)} ==
         runtime_names, 'RUNTIME_EXACT_FILES')
    for name, wanted in runtime['files'].items():
        relative(name)
        need(value['files'].get(RUNTIME + name) == wanted, 'RUNTIME_FILE')
    provenance = decode(cache[RUNTIME + 'P2_PACKAGE_PROVENANCE.json'])
    need(type(provenance) is dict and type(provenance.get('schema')) is int and
         provenance['schema'] == 2 and
         provenance.get('source_commit') == value['runtime_source_commit'] and
         provenance.get('source_tree') == value['runtime_source_tree'] and
         provenance.get('runtime_manifest_sha256') == value['runtime_manifest_sha256'] and
         provenance.get('runtime_manifest_path') == 'deploy/integration-manifest.json' and
         provenance.get('runtime_files') == runtime['files'] and
         provenance.get('verifier_path') == 'tools/p2-package-freeze.py' and
         provenance.get('verifier_sha256') == sha(cache[RUNTIME + 'tools/p2-package-freeze.py']),
         'RUNTIME_PROVENANCE_LINKAGE')
    validate_public_service_fixture(value, cache)
    validate_public_openclaw_fixture(cache)
    return runtime


def _verify(root, expected_sha, owners):
    need(type(expected_sha) is str and SHA.fullmatch(expected_sha), 'SHA_REQUIRED')
    with DescriptorTree(root, owners) as tree:
        raw = tree.read(MANIFEST)
        need(sha(raw) == expected_sha, 'MANIFEST_CHANGED')
        value = validate_manifest(decode(raw))
        expected = set(value['files']) | {MANIFEST}
        before = tree.inventory()
        need(before == (expected, directories(expected)), 'EXTRA_OR_MISSING_CONTENT')
        cache, total = {}, len(raw)
        for name, wanted in sorted(value['files'].items()):
            data = tree.read(name)
            need(sha(data) == wanted, 'FILE_CHANGED')
            total += len(data); need(total <= MAX_TOTAL, 'TOTAL_BOUND')
            cache[name] = data
        validate_runtime(value, cache)
        need(tree.inventory() == before, 'INVENTORY_CHANGED')
        tree.recheck()
    return VerifiedKit(root, value, cache, expected_sha, owners, raw)


def verify_kit(root, expected_sha):
    need(os.geteuid() == 0, 'ROOT_REQUIRED')
    return _verify(root, expected_sha, ((0, 0),))


class CachedSources(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Exact verified Python bytes; no source/bytecode reopen by importer."""
    def __init__(self, root, cache, modules, safe_path):
        self.root, self.cache, self.modules = root, cache, dict(modules)
        self.safe_path = tuple(safe_path)
        self.package_bases = tuple(os.path.realpath(base) for base in self.safe_path
            if os.path.isdir(base) or (base.endswith('.zip') and os.path.isfile(base)))
        self.loaded = set()

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.modules:
            return importlib.util.spec_from_loader(fullname, self,
                    origin=self.root + '/' + self.modules[fullname])
        # Tests may alter sys.path. They cannot extend the startup stdlib path.
        if path is not None:
            need(all(type(p) is str and os.path.isabs(p) and os.path.normpath(p) == p and
                     any(os.path.commonpath((os.path.realpath(p), base)) == base
                         for base in self.package_bases) for p in path), 'UNTRUSTED_IMPORT_PATH')
        spec = importlib.machinery.PathFinder.find_spec(fullname,
                list(self.safe_path) if path is None else path)
        if spec is not None: return spec
        # Let only builtin/frozen loaders continue; never PathFinder fallback.
        for finder in (importlib.machinery.BuiltinImporter, importlib.machinery.FrozenImporter):
            spec = finder.find_spec(fullname, path, target)
            if spec is not None: return spec
        # Match Python import semantics: stdlib platform probes (notably
        # subprocess on Python 3.12) catch ModuleNotFoundError specifically.
        # This still terminates lookup and never falls through to another path.
        raise ModuleNotFoundError('EPOCH7_KIT_UNDECLARED_IMPORT:' + fullname, name=fullname)

    def create_module(self, spec): return None

    def exec_module(self, module):
        name = module.__name__
        source = self.modules[name]
        module.__file__ = self.root + '/' + source
        module.__cached__ = None
        exec(compile(self.cache[source], module.__file__, 'exec', dont_inherit=True),
             module.__dict__)
        self.loaded.add(name)


class VerifiedKit(object):
    def __init__(self, root, manifest, cache, digest, owners=((0, 0),), raw_manifest=None):
        self.root, self.manifest, self.cache, self.digest = root, manifest, cache, digest
        self.owners, self.raw_manifest = owners, raw_manifest

    def report(self):
        return {'operation': 'verify-only', 'epoch': 7, 'verified_files': len(self.cache),
                'kit_manifest_sha256': self.digest, 'runtime_manifest_sha256': self.manifest['runtime_manifest_sha256'],
                'production_resume': self.manifest['production_resume'], 'install_admission': 'NOT_GRANTED',
                'runtime_source_commit': self.manifest['runtime_source_commit'],
                'runtime_source_tree': self.manifest['runtime_source_tree'],
                'kit_source_commit': self.manifest['kit_source_commit'],
                'kit_source_tree': self.manifest['kit_source_tree'],
                'available_test_suites': sorted(name for name, row in self.manifest['test_suites'].items()
                                               if row['enabled']),
                'unavailable_test_suites': {name: row['reason'] for name, row in
                    self.manifest['test_suites'].items() if not row['enabled']}}

    @contextlib.contextmanager
    def imports(self, extra=None):
        """One authenticated module namespace; also used by future composition."""
        need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
             'ISOLATED_NO_BYTECODE_REQUIRED')
        startup_path = list(sys.path)
        need(tuple(startup_path) == BOOTSTRAP_PATH and all(BOOTSTRAP_PATH),
             'BOOTSTRAP_IMPORT_PATH_CHANGED')
        modules = dict(self.manifest['modules'])
        extra = extra or {}
        need(not set(modules) & set(extra), 'TEST_MODULE_COLLISION')
        modules.update(extra)
        need(not set(modules) & set(sys.modules), 'PRELOADED_CANDIDATE_MODULE')
        importer = CachedSources(self.root, self.cache, modules, BOOTSTRAP_PATH)
        sys.meta_path.insert(0, importer)
        try:
            yield importer
        finally:
            sys.meta_path.remove(importer)
            for module in modules: sys.modules.pop(module, None)
            sys.path[:] = startup_path

    def _private_resume_inputs(self, plan_path, plan_sha, seed_path, seed_sha):
        """Only two exact, hash-bound private JSON files outside the public kit."""
        need(all(type(value) is str and SHA.fullmatch(value) for value in (plan_sha, seed_sha)),
             'PRIVATE_INPUT_SHA_REQUIRED')
        for path, prefix in ((plan_path, 'epoch7-approved-plan-'), (seed_path, 'epoch7-resume-inputs-')):
            need(type(path) is str and os.path.dirname(path) == CANDIDATE_PARENT and
                 re.fullmatch(prefix + r'[0-9a-f]{16}\.private\.json', os.path.basename(path)),
                 'PRIVATE_INPUT_PATH')
        with DescriptorTree(CANDIDATE_PARENT, self.owners) as tree:
            plan_raw = tree.read(os.path.basename(plan_path), 2 * 1024 * 1024, private=True)
            seed_raw = tree.read(os.path.basename(seed_path), MAX_PRIVATE_SEED, private=True)
            need(sha(plan_raw) == plan_sha and sha(seed_raw) == seed_sha, 'PRIVATE_INPUT_CHANGED')
            tree.recheck()
        plan, envelope = decode(plan_raw), decode(seed_raw)
        need(type(plan) is dict and type(envelope) is dict and set(envelope) == {'schema', 'seed'} and
             type(envelope['schema']) is int and envelope['schema'] == 1 and
             type(envelope['seed']) is dict and set(envelope['seed']) == PRIVATE_SEED_FIELDS,
             'PRIVATE_SEED_SCHEMA')
        return plan_raw, plan, envelope['seed']

    def _hydrate_seed(self, private, factory):
        """Fixed UTF-8 fields only; no generic sentinel, path resolver or code input."""
        need(type(private) is dict and set(private) == PRIVATE_SEED_FIELDS,
             'PRIVATE_SEED_SCHEMA')
        seed = dict(private)
        for name in PRIVATE_RAW_FIELDS:
            need(type(seed[name]) is str, 'PRIVATE_RAW_UTF8_REQUIRED')
            seed[name] = seed[name].encode('utf-8')
        identities = seed['identity_payloads']
        need(type(identities) is dict and set(identities) == IDENTITY_PATHS and
             all(type(value) is str for value in identities.values()), 'PRIVATE_IDENTITY_UTF8_REQUIRED')
        seed['identity_payloads'] = {name: value.encode('utf-8') for name, value in identities.items()}
        need(type(seed['activate_retained_renewal_timer']) is bool, 'EXPLICIT_TIMER_DECISION')
        seed['compiled'] = factory.compiled_bytes(seed['compiled'])
        manifest_raw = self.cache[RUNTIME + 'deploy/integration-manifest.json']
        source = decode(manifest_raw)
        runtime_root = self.root + '/xuanjun-p2-package'
        seed.update(installer_source=self.cache[RUNTIME + 'scripts/uk-integration-install.py'],
            source_manifest_raw=manifest_raw,
            source_payloads={name: self.cache[RUNTIME + name] for name in source['files']},
            kit_manifest_sha256=self.digest,
            artifact={'root': runtime_root, 'manifest': runtime_root + '/deploy/integration-manifest.json',
                'releases': '/opt/xuanjun-control-releases',
                'source_commit': self.manifest['runtime_source_commit'],
                'source_tree': self.manifest['runtime_source_tree'],
                'manifest_sha256': self.manifest['runtime_manifest_sha256']})
        need(set(seed) == PRIVATE_SEED_FIELDS | CACHE_SEED_FIELDS == factory.INPUTS - factory.DERIVED_INPUTS,
             'FACTORY_SEED_INTERFACE_CHANGED')
        return seed

    def _authenticate_probe_receipt(self, observation):
        """Root the original probe policy in its existing protected nonce receipt.

        Read-only: never creates a receipt, imports a package, reruns a probe,
        substitutes an observation or treats caller hash equality as authority.
        """
        need(self.manifest['modules'].get('node_sqlite_probe') == 'helpers/node_sqlite_probe.py',
             'PROBE_RECEIPT_MODULE_REQUIRED')
        need(type(observation) is dict and type(observation.get('finite_probe')) is dict,
             'PROBE_RECEIPT_ATTEMPT_REQUIRED')
        attempt = observation['finite_probe']
        nonce = attempt.get('nonce')
        need(type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}', nonce), 'PROBE_RECEIPT_NONCE')
        result = attempt.get('result')
        need(type(result) is dict and type(result.get('created_receipt')) is dict, 'PROBE_RECEIPT_BINDING')
        receipt = result['created_receipt']
        root = PROBE_RECEIPT_PARENT + '/xj-p2-proof-' + nonce
        need(receipt.get('path') == root + '/created-receipt.json' and
             type(receipt.get('sha256')) is str and SHA.fullmatch(receipt['sha256']), 'PROBE_RECEIPT_PATH')
        with DescriptorTree(root, self.owners) as tree:
            before = os.stat('created-receipt.json', dir_fd=tree.fd, follow_symlinks=False)
            data = tree.read('created-receipt.json', MAX_PROBE_RECEIPT, private=True)
            after = os.stat('created-receipt.json', dir_fd=tree.fd, follow_symlinks=False)
            need(stamp(before) == stamp(after), 'PROBE_RECEIPT_READ_RACE')
            metadata = {'dev': after.st_dev, 'ino': after.st_ino, 'mode': stat.S_IMODE(after.st_mode),
                'uid': after.st_uid, 'gid': after.st_gid, 'nlink': after.st_nlink, 'size': after.st_size,
                'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns}
            need(sha(data) == receipt['sha256'] and same_json(metadata, receipt.get('metadata')),
                 'PROBE_RECEIPT_CHANGED')
            tree.recheck()
        helper = importlib.import_module('node_sqlite_probe')
        proof = helper.authenticate_receipt_binding(data, metadata, observation)
        need(type(proof) is dict, 'PROBE_RECEIPT_RESULT')
        return {'receipt_sha256': sha(data), 'metadata': metadata,
                'proof_sha256': sha(json.dumps(proof, sort_keys=True, separators=(',', ':'),
                    ensure_ascii=True, allow_nan=False).encode('ascii'))}

    def resume(self, plan_path, plan_sha, seed_path, seed_sha, review_id, review_body_sha):
        """One complete cached import scope and one coordinator-owned attempt.

        No approval fetcher/runner override, snapshot refresh, claim creation,
        retry, or cleanup occurs in the loader. The coordinator owns them.
        """
        need(self.manifest['production_resume'] == RESUME_COMPOSED, 'RESUME_REFUSED_UNCOMPOSED')
        need(os.geteuid() == 0 and os.uname().nodename.split('.')[0] == FIXED_HOST and
             self.root == CANDIDATE_PARENT + '/epoch7-recovery-candidate-r7-resourcebind', 'RESUME_FIXED_HOST_ROOT')
        need(type(review_id) is int and review_id > 0 and type(review_body_sha) is str and
             SHA.fullmatch(review_body_sha), 'FRESH_REVIEW_ARGUMENTS_REQUIRED')
        need(all(type(value) is str and SHA.fullmatch(value) for value in (plan_sha, seed_sha)),
             'PRIVATE_INPUT_SHA_REQUIRED')
        result = {'operation': 'resume', 'kit_manifest_sha256': self.digest,
            'approved_plan_sha256': plan_sha, 'private_seed_sha256': seed_sha,
            'production_acceptance': 'PENDING', 'success': False, 'exit_code': 2,
            'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED',
            'stage': 'COMPOSITION_HOLD'}
        started = False
        try:
            plan_raw, plan, private = self._private_resume_inputs(plan_path, plan_sha, seed_path, seed_sha)
            with self.imports():
                factory = importlib.import_module('epoch7_host_factory')
                sequence = importlib.import_module('epoch7_recovery_sequence')
                seed = self._hydrate_seed(private, factory)
                probe_receipt = self._authenticate_probe_receipt(seed['observation'])
                prepared = factory.prepare_host_inputs(seed)
                need(type(prepared) is dict and prepared.get('state') == 'COMPILED_NOT_ADMITTED' and
                     prepared.get('install_admission') is False and prepared.get('unresolved') == [] and
                     type(prepared.get('inputs')) is dict, 'HOST_INPUTS_UNRESOLVED')
                inputs = prepared['inputs']
                contract = factory.compile_host_contract(inputs)
                need(type(contract) is dict and set(contract) == {'host_contract', 'resource_observer', 'live_controls'} and
                     all(name in plan and same_json(plan[name], value) for name, value in contract.items()),
                     'APPROVED_COMPONENTS_MISMATCH')
                # Verify identical sources/private buffers before constructing
                # the real driver; never replace the approved observation.
                _verify(self.root, self.digest, self.owners)
                self._private_resume_inputs(plan_path, plan_sha, seed_path, seed_sha)
                need(same_json(self._authenticate_probe_receipt(seed['observation']), probe_receipt),
                     'PROBE_RECEIPT_RECHECK')
                driver = factory.assemble_host_driver(plan_raw, inputs, review_id, review_body_sha)
                started = True
                try:
                    state = sequence.resume_once(driver)
                except (sequence.RecoveryHold, sequence.RecoveryInterrupted, sequence.RecoveryExited) as error:
                    state = error.state
                    result['stage'] = ('INTERRUPTED_HOLD' if isinstance(error, sequence.RecoveryInterrupted)
                                       else 'COORDINATOR_HOLD')
                    result['exit_code'] = 130 if isinstance(error, sequence.RecoveryInterrupted) else 2
                else:
                    need(type(state) is dict and state.get('stage') == 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE' and
                         state.get('production_acceptance') == 'PENDING' and state.get('admission') == 'ADMITTED' and
                         state.get('completed') == list(sequence.PHASES), 'COORDINATOR_RESULT')
                    result.update(stage='COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE', success=True, exit_code=0)
                need(type(state) is dict, 'COORDINATOR_STATE')
                result['coordinator_state_sha256'] = sha(sequence.packed(state))
                result['install_admission'] = state.get('admission') if state.get('admission') in (
                    'NOT_GRANTED', 'ADMITTED', 'UNKNOWN') else 'UNKNOWN'
                result['production_resume'] = 'COORDINATOR_ATTEMPTED_ONCE'
        except (KeyboardInterrupt, SystemExit) as error:
            result.update(stage='INTERRUPTED_HOLD', success=False, exit_code=130 if isinstance(error, KeyboardInterrupt) else 2)
            if started: result.update(install_admission='UNKNOWN', production_resume='COORDINATOR_OUTCOME_UNKNOWN')
        except Exception:
            # Never stringify private buffers, command output or exception data.
            result.update(success=False, exit_code=2)
            if started: result.update(stage='COORDINATOR_OUTCOME_UNKNOWN', install_admission='UNKNOWN',
                                      production_resume='COORDINATOR_OUTCOME_UNKNOWN')
        return result

    def observe(self, output, nonce=None, execute_reviewed_probe=False):
        """Fixed observation, optionally followed by one explicitly reviewed probe.

        The operator flag acknowledges external Owner consent. It never creates
        approval, independent acceptance, or any production resume authority.
        """
        need(type(output) is str, 'OBSERVATION_OUTPUT_REQUIRED')
        need(type(execute_reviewed_probe) is bool and
             ((nonce is None and not execute_reviewed_probe) or
              (type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}', nonce) and execute_reviewed_probe)),
             'EXPLICIT_REVIEWED_PROBE_SCOPE')
        need(self.manifest['modules'].get('observe_epoch7') == 'helpers/observe_epoch7.py',
             'OBSERVATION_MODULE_REQUIRED')
        probe_state = 'NOT_REQUESTED'
        probe_observed = False
        with self.imports():
            observer = importlib.import_module('observe_epoch7')
            observer.c.path(output)
            need(os.path.dirname(output) == observer.c.CAND and re.fullmatch(
                 r'epoch7-observation-[0-9a-f]{16}\.private\.json', os.path.basename(output)),
                 'OBSERVATION_OUTPUT_SCOPE')
            need(self.root == observer.c.CAND + '/epoch7-recovery-candidate-r7',
                 'OBSERVATION_EXACT_STAGED_KIT')
            # Refuse existing output before observation/probe effects. Final
            # writer still uses O_EXCL, no-follow ancestry and private readback.
            with observer.ObservationReader({}).parent(output) as (parent, leaf):
                try: os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError: pass
                else: need(False, 'OBSERVATION_OUTPUT_EXISTS')
            candidate_root = self.root + '/xuanjun-p2-package'
            value = observer.observe_host(candidate_root=candidate_root)
            need(type(value) is dict and value.get('kind') in
                 ('EPOCH7_OBSERVATION_ONLY_UNREVIEWED', 'EPOCH7_OBSERVATION_ONLY_HOLD'),
                 'OBSERVATION_RESULT_SCHEMA')
            for key in ('snapshot_sha256', 'policy_sha256'):
                need(value.get(key) is None or (type(value[key]) is str and SHA.fullmatch(value[key])),
                     'OBSERVATION_PUBLIC_DIGEST')
            if execute_reviewed_probe:
                # Failures stay private; do not lose the completed observation.
                probe_state = 'HOLD_NOT_EXECUTED'
                attempt = {'schema': 1, 'nonce': nonce, 'stage': probe_state,
                           'operator_acknowledgement_is_external_approval_proof': False,
                           'resume_authority': False}
                probe_attempted = False
                try:
                    need(value.get('kind') == 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
                         'PROBE_REFUSED_ON_SNAPSHOT_HOLD')
                    metadata = value.get('probe_metadata', {})
                    need(metadata.get('ingredient_state') == 'COMPLETE_UNREVIEWED',
                         'PROBE_INGREDIENTS_INCOMPLETE')
                    need(self.manifest['modules'].get('probe_driver') == 'helpers/probe_driver.py' and
                         self.manifest['modules'].get('probe_helpers') == 'helpers/probe_helpers.py' and
                         self.manifest['modules'].get('node_sqlite_probe') == 'helpers/node_sqlite_probe.py',
                         'PROBE_MODULES_REQUIRED')
                    driver = importlib.import_module('probe_driver')
                    node_probe = importlib.import_module('node_sqlite_probe')
                    source_hashes = {name: sha(self.cache[RUNTIME + name]) for name in driver.CANDIDATE_SOURCES}
                    evidence = metadata.get('candidate_source_evidence')
                    need(type(evidence) is dict and evidence.get('root') == candidate_root and
                         evidence.get('runtime_manifest_sha256') == self.manifest['runtime_manifest_sha256'] and
                         evidence.get('candidate_sources') == source_hashes, 'PROBE_STAGED_SOURCE_EVIDENCE')
                    helper = self.cache['helpers/probe_helpers.py']
                    offline = {'nonce': nonce, 'driver_sha256': sha(self.cache['helpers/probe_driver.py']),
                        'helper_sha256': sha(helper), 'candidate_sources': source_hashes,
                        'ledger_capability_reviewed': True, 'cleanup_reviewed': True, 'node_sqlite_reviewed': True}
                    # Derive from the completed original observation before
                    # attaching this attempt/result to its private envelope.
                    policy = driver.compile_policy(metadata['ingredients'], offline, value)
                    policy_sha = sha(driver.canonical(policy) + b'\n')
                    attempt.update(policy=policy, policy_sha256=policy_sha)
                    # Re-read only for source integrity. No observer/phase retry.
                    _verify(self.root, self.digest, self.owners)
                    probe_state = 'ATTEMPT_STARTED'
                    attempt['stage'] = probe_state
                    probe_attempted = True
                    result = driver.execute_reviewed_probe(policy, policy_sha, candidate_root, helper, True)
                    need(type(result) is dict and result.get('resume_authority') is False,
                         'PROBE_RESULT_SCHEMA')
                    probe_state = 'RESULT_RECORDED'
                    attempt.update(stage=probe_state, result=result)
                    node_probe.validate_node_sqlite_proof(result['node_sqlite'], policy['node_sqlite']['node'],
                        policy_sha, policy['node_sqlite']['probe_input_sha256'])
                    cleanup = result.get('cleanup')
                    probe_observed = (result.get('failure') is None and
                        result.get('incomplete_case') is None and
                        len(result.get('cases', [])) == len(driver.CASES) and
                        type(cleanup) is list and bool(cleanup) and all(type(row) is dict and
                        not any(type(v) is str and (v == 'UNKNOWN' or v.startswith('RETAINED'))
                                for v in row.values()) for row in cleanup))
                except (KeyboardInterrupt, SystemExit): raise
                except Exception as error:
                    # The watchdog wrapper owns cleanup after an actual attempt.
                    # Preserve the stage to distinguish preflight from uncertainty.
                    attempt['failure_code'] = (error.args[0] if type(error) is ValueError and
                        len(error.args) == 1 and type(error.args[0]) is str and
                        re.fullmatch(r'[A-Z0-9_]{1,128}', error.args[0]) else 'PROBE_RESULT_UNAVAILABLE')
                    probe_state = 'HOLD_AFTER_ATTEMPT' if probe_attempted else 'HOLD_NOT_EXECUTED'
                    attempt['stage'] = probe_state
                value['finite_probe'] = attempt
            digest = observer.persist_private(output, value)
            need(type(digest) is str and SHA.fullmatch(digest), 'OBSERVATION_PERSIST_DIGEST')
        return {'operation': 'observe-and-probe' if execute_reviewed_probe else 'observe-only',
                'kind': value['kind'], 'private_file_sha256': digest,
                'snapshot_sha256': value.get('snapshot_sha256'), 'policy_sha256': value.get('policy_sha256'),
                'kit_manifest_sha256': self.digest, 'probe_stage': probe_state,
                'probe_observations_complete': probe_observed,
                'independent_acceptance': 'PENDING', 'install_admission': 'NOT_GRANTED',
                'production_resume': 'NOT_EXECUTED',
                'success': (value['kind'] == 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED' and
                            (probe_state == 'NOT_REQUESTED' or probe_observed))}

    @contextlib.contextmanager
    def test_workspace(self):
        """Verified byte-identical disposable copy for confined filesystem suites."""
        import tempfile
        need(type(self.raw_manifest) is bytes and sha(self.raw_manifest) == self.digest,
             'WORKSPACE_MANIFEST_REQUIRED')
        with tempfile.TemporaryDirectory(prefix='.epoch7-unit-workspace-',
                dir=os.path.dirname(self.root)) as root:
            files = dict(self.cache); files[MANIFEST] = self.raw_manifest
            for name in sorted(directories(files), key=lambda p: (p.count('/'), p)):
                os.mkdir(root + '/' + name, 0o700)
            for name, data in sorted(files.items()):
                fd = os.open(root + '/' + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                try:
                    offset = 0
                    while offset < len(data):
                        count = os.write(fd, data[offset:]); need(count > 0, 'WORKSPACE_SHORT_WRITE')
                        offset += count
                    os.fchmod(fd, 0o444)
                finally: os.close(fd)
            workspace = _verify(root, self.digest, self.owners)
            # These test-only roots remain inside the verified disposable copy.
            # Production fixture-root confinement in each helper is unchanged.
            fixtures = root + '/helpers/fixtures'
            os.mkdir(fixtures, 0o700)
            try: yield workspace
            finally:
                # Empty-only removal refuses leaked fixtures. TemporaryDirectory
                # still removes this private disposable copy on any exception.
                os.rmdir(fixtures)
                _verify(root, self.digest, self.owners)

    def _execute_tests(self, names):
        import unittest
        results = []
        for name in names:
            row = self.manifest['test_suites'][name]
            with self.imports(row['imports']):
                suite = unittest.TestSuite()
                for path in row['tests']:
                    alias = next(alias for alias, source in row['imports'].items() if source == path)
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(alias)))
                result = unittest.TextTestRunner(verbosity=2).run(suite)
                results.append({'suite': name, 'tests': result.testsRun, 'success': result.wasSuccessful(),
                                'skipped': len(result.skipped)})
        return {'operation': 'test-only', 'suites': results,
                'success': all(row['success'] for row in results),
                'kit_manifest_sha256': self.digest, 'production_resume': 'NOT_EXECUTED',
                'install_admission': 'NOT_GRANTED'}

    def tests(self, names):
        suites = self.manifest['test_suites']
        need(type(names) is list and names and len(set(names)) == len(names) and
             all(name in suites for name in names), 'EXACT_TEST_SUITES_REQUIRED')
        need(all(suites[name]['enabled'] for name in names), 'NONPORTABLE_TEST_SUITE')
        filesystem_suites = {'host_filesystem', 'host_observer', 'resource_plan', 'recovery_filesystem'}
        try:
            if set(names) & filesystem_suites:
                with self.test_workspace() as workspace: result = workspace._execute_tests(names)
                result['test_workspace'] = 'AUTHENTICATED_DISPOSABLE_COPY_REMOVED'
            else:
                result = self._execute_tests(names)
                result['test_workspace'] = 'AUTHENTICATED_SOURCE_CACHE'
            return result
        finally:
            # Also verify the protected source after test/import/cleanup failure.
            _verify(self.root, self.digest, self.owners)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit-manifest-sha256', required=True)
    parser.add_argument('--operation', required=True,
                        choices=('verify-only', 'test-only', 'observe-only', 'observe-and-probe', 'resume'))
    parser.add_argument('--output')
    parser.add_argument('--nonce')
    parser.add_argument('--execute-reviewed-probe', action='store_true')
    parser.add_argument('--suite', action='append', default=[])
    parser.add_argument('--approved-plan')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--private-seed')
    parser.add_argument('--private-seed-sha256')
    parser.add_argument('--review-id', type=int)
    parser.add_argument('--review-body-sha256')
    args = parser.parse_args(argv)
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'ISOLATED_NO_BYTECODE_REQUIRED')
    resume_args = (args.approved_plan, args.approved_plan_sha256, args.private_seed,
                   args.private_seed_sha256, args.review_id, args.review_body_sha256)
    need(all(value is not None for value in resume_args) if args.operation == 'resume' else
         all(value is None for value in resume_args), 'RESUME_INPUTS_REQUIRED_OR_OUT_OF_SCOPE')
    need(args.operation == 'test-only' or not args.suite, 'TEST_SCOPE_ONLY')
    need((args.operation in ('observe-only', 'observe-and-probe')) ==
         (args.output is not None), 'OBSERVATION_OUTPUT_SCOPE')
    if args.operation == 'observe-and-probe':
        need(args.execute_reviewed_probe and type(args.nonce) is str and
             re.fullmatch(r'[0-9a-f]{32}', args.nonce), 'EXPLICIT_REVIEWED_PROBE_SCOPE')
    else:
        need(not args.execute_reviewed_probe and args.nonce is None, 'PROBE_SCOPE_ONLY')
    root = os.path.dirname(os.path.abspath(__file__))
    kit = verify_kit(root, args.kit_manifest_sha256)
    if args.operation == 'verify-only': result = kit.report()
    elif args.operation in ('observe-only', 'observe-and-probe'):
        result = kit.observe(args.output, args.nonce, args.execute_reviewed_probe)
    elif args.operation == 'resume': result = kit.resume(*resume_args)
    else: result = kit.tests(args.suite)
    print(json.dumps(result, sort_keys=True))
    return result.get('exit_code', 0 if result.get('success', True) else 1)


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError):
        # No sensitive path or exception payload is printed by the entry.
        print(json.dumps({'stage': 'HOLD', 'reason': 'EPOCH7_KIT_VERIFICATION_OR_SCOPE_FAILED',
                          'production_resume': 'NOT_EXECUTED', 'install_admission': 'NOT_GRANTED'}, sort_keys=True))
        sys.exit(2)
