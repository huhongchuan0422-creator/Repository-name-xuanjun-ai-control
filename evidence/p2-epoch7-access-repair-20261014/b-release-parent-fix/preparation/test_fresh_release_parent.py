"""LOCAL-only B release-parent preparation tests, compatible with Python 3.6.

Successful authority snapshots use genuine temporary-directory descriptors and
unmodified authenticated DescriptorTree code. The sole success-path authority
normalization maps the executor's UID/GID to root at an explicit OS boundary;
logical '/' is redirected to the temporary fixture. This is NOT a host probe,
root-authority proof, artifact binding, publication, or install admission.
Fault injection is explicit and restricted to this temporary OS adapter.
"""
import contextlib
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent.parent
PARENT = '/opt/xuanjun-control-releases'
STAT_KEYS = frozenset(('dev', 'ino', 'uid', 'gid', 'mode', 'nlink', 'size',
                       'mtime_ns', 'ctime_ns'))
ROW_KEYS = STAT_KEYS | frozenset(('kind', 'access_acl', 'default_acl'))
PROOF_KEYS = frozenset(('schema', 'kind', 'path', 'observation_sha256',
                        'policy_sha256', 'metadata', 'ancestors', 'recheck'))


def load_module(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def acl(mode):
    def rights(bits):
        return ''.join(letter if bits & bit else '-'
                       for bit, letter in ((4, 'r'), (2, 'w'), (1, 'x')))
    return 'user::%s\ngroup::%s\nother::%s\n' % (
        rights(mode >> 6 & 7), rights(mode >> 3 & 7), rights(mode & 7))


class StatView(object):
    def __init__(self, value, replacements):
        self.value = value
        self.replacements = replacements

    def __getattr__(self, name):
        if name in self.replacements:
            return self.replacements[name]
        return getattr(self.value, name)


class LocalReadOnlyOS(object):
    """Real openat/stat/fstat with fixed logical-root and UID/GID adaptation."""
    forbidden = frozenset(('mkdir', 'makedirs', 'write', 'pwrite', 'chmod',
        'fchmod', 'chown', 'fchown', 'lchown', 'unlink', 'remove', 'rmdir',
        'rename', 'replace', 'link', 'symlink', 'truncate', 'ftruncate',
        'setxattr', 'removexattr', 'system'))

    def __init__(self, root):
        self.root = str(root)
        self.fds = {}
        self.open_log = []
        self.stat_log = []
        self.closed_log = []
        self.mutations = []
        self.faults = {}
        self.xattrs = {}
        self.close_fault = False
        self.after_stat = None

    def __getattr__(self, name):
        if name in self.forbidden:
            def denied(*args, **kwargs):
                self.mutations.append((name, args, kwargs))
                raise AssertionError('Capture attempted mutation: ' + name)
            return denied
        return getattr(os, name)

    def logical(self, path, dir_fd=None):
        if isinstance(path, int):
            return self.fds[path]
        if path.startswith('/'):
            if path != '/':
                raise AssertionError('Unexpected absolute host path: ' + path)
            return '/'
        if dir_fd not in self.fds:
            raise AssertionError('Descriptor was not opened by the fixture')
        result = os.path.normpath(os.path.join(self.fds[dir_fd], path))
        if result not in ('/', '/opt', PARENT, '/opt/retained.txt'):
            raise AssertionError('Capture escaped fixed scope: ' + result)
        return result

    def normalized(self, value, logical):
        # Explicit synthetic root ownership only. All identity/timestamp/mode
        # values otherwise come from the genuine stat_result of a local FD.
        changes = {'st_uid': 0 if value.st_uid == os.getuid() else value.st_uid,
                   'st_gid': 0 if value.st_gid == os.getgid() else value.st_gid}
        changes.update(self.faults.get(logical, {}))
        return StatView(value, changes)

    def open(self, path, flags, mode=0o777, dir_fd=None):
        logical = self.logical(path, dir_fd)
        if flags & (os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_RDWR | os.O_APPEND):
            self.mutations.append(('open', path, flags))
            raise AssertionError('Capture requested a writable descriptor')
        if not flags & os.O_NOFOLLOW:
            raise AssertionError('Capture omitted O_NOFOLLOW')
        self.open_log.append((logical, flags, dir_fd))
        actual = self.root if path == '/' else path
        fd = os.open(actual, flags, mode, dir_fd=dir_fd)
        self.fds[fd] = logical
        return fd

    def fstat(self, fd):
        return self.normalized(os.fstat(fd), self.fds[fd])

    def stat(self, path, dir_fd=None, follow_symlinks=True):
        logical = self.logical(path, dir_fd)
        if follow_symlinks:
            raise AssertionError('Capture followed a symlink')
        actual = self.root if path == '/' else path
        value = self.normalized(os.stat(actual, dir_fd=dir_fd,
                                        follow_symlinks=False), logical)
        self.stat_log.append(logical)
        if self.after_stat is not None:
            self.after_stat(logical)
        return value

    def getxattr(self, fd, name):
        logical = self.fds[fd]
        fault = self.xattrs.get((logical, name))
        if isinstance(fault, BaseException):
            raise fault
        if fault is not None:
            return fault
        return os.getxattr(fd, name)

    def close(self, fd):
        os.close(fd)
        self.closed_log.append(fd)
        self.fds.pop(fd)
        if self.close_fault:
            self.close_fault = False
            raise OSError(errno.EIO, 'injected close failure after real close')


class ParentFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fresh-b-parent-local-')
        self.root = Path(self.temp.name)
        os.chmod(str(self.root), 0o755)
        (self.root / 'opt').mkdir(mode=0o755)
        (self.root / 'opt/xuanjun-control-releases').mkdir(mode=0o750)
        self.boundary = LocalReadOnlyOS(self.root)
        self.prep = load_module(HERE / 'epoch7_prepare.py', 'local_prepare_test')
        self.entry = load_module(STAGE / 'kit/epoch7-recovery-candidate-r7/epoch7_recovery_entry.py',
                                 'local_original_entry_test')
        self.prep.os = self.boundary
        self.entry.os = self.boundary
        self.gather = self.prep.Gatherer(self.entry, time.monotonic() + 90)
        self.observation = {'schema': 1, 'policy': {'directories': {
            '/': {'uid': 0, 'gid': 0, 'mode': 0o755},
            '/opt': {'uid': 0, 'gid': 0, 'mode': 0o755},
            PARENT: {'uid': 0, 'gid': 0, 'mode': 0o750}}},
            'evidence': {'retained': {'files': {}, 'directories': {}}},
            'private_fixture_marker': 'LOCAL_SYNTHETIC_OBSERVATION'}
        self.observation['policy_sha256'] = digest(self.observation['policy'])

    def tearDown(self):
        try:
            self.gather.close()
        finally:
            # Fixture leak cleanup also permits asserting all owned FDs close
            # on failing paths without touching any host descriptor.
            for fd in list(self.boundary.fds):
                try:
                    os.close(fd)
                except OSError:
                    pass
                self.boundary.fds.pop(fd, None)
            self.temp.cleanup()

    def capture(self):
        return self.gather.release_parent(self.observation)

    def reset_gather(self):
        self.gather.close()
        self.gather = self.prep.Gatherer(self.entry, time.monotonic() + 90)

    def reject(self, operation=None):
        with self.assertRaises((ValueError, OSError, TypeError, KeyError)):
            (operation or self.capture)()

    def test_real_descriptor_snapshot_exact_schema_and_bindings(self):
        before = copy.deepcopy(self.observation)
        proof = self.capture()
        self.assertEqual(set(proof), PROOF_KEYS)
        self.assertIs(type(proof['schema']), int)
        self.assertEqual(proof['schema'], 1)
        self.assertEqual(proof['kind'], 'FRESH_B_RELEASE_PARENT_AUTHORITY')
        self.assertEqual(proof['path'], PARENT)
        self.assertEqual(proof['observation_sha256'], digest(before))
        self.assertEqual(proof['policy_sha256'], before['policy_sha256'])
        self.assertEqual(proof['recheck'], 'PRECOMPILE_MATCHED_FINAL_RECHECK_REQUIRED')
        self.assertEqual(set(proof['ancestors']), {'/', '/opt'})
        rows = dict(proof['ancestors'])
        rows[PARENT] = proof['metadata']
        for logical, row in rows.items():
            local = self.root if logical == '/' else self.root / logical[1:]
            actual = os.stat(str(local), follow_symlinks=False)
            self.assertEqual(set(row), ROW_KEYS)
            self.assertTrue(all(type(row[k]) is int for k in STAT_KEYS))
            self.assertEqual(row['kind'], 'DIRECTORY')
            self.assertEqual((row['uid'], row['gid']), (0, 0))
            self.assertEqual(row['mode'], stat.S_IMODE(actual.st_mode))
            for name in STAT_KEYS - {'uid', 'gid', 'mode'}:
                self.assertEqual(row[name], getattr(actual, 'st_' + name))
            self.assertEqual(row['access_acl'], acl(row['mode']))
            self.assertEqual(row['default_acl'], '')
        self.assertEqual(self.observation, before)
        self.assertEqual(self.gather.rows, {})
        self.assertEqual(set(self.boundary.fds.values()), {'/', '/opt', PARENT})
        self.assertEqual(self.boundary.mutations, [])

    def test_repeat_is_independent_and_does_not_rewrite_retained_observation(self):
        before = canonical(self.observation)
        first = self.capture()
        first['metadata']['ino'] += 1
        first['ancestors']['/']['mode'] = 0
        second = self.capture()
        self.assertNotEqual(first, second)
        self.assertEqual(canonical(self.observation), before)
        self.assertEqual(self.gather.rows, {})
        self.gather.recheck()

    def test_saved_policy_not_live_row_is_required(self):
        for logical in ('/', '/opt', PARENT):
            with self.subTest(path=logical):
                self.reset_gather()
                original = copy.deepcopy(self.observation)
                del self.observation['policy']['directories'][logical]
                self.observation['policy_sha256'] = digest(self.observation['policy'])
                self.reject()
                self.observation = original

    def test_saved_policy_hash_must_be_authentic(self):
        self.observation['policy_sha256'] = 'f' * 64
        self.reject()

    def test_saved_policy_uid_gid_mode_are_exact_typed_integers(self):
        for path in ('/', '/opt', PARENT):
            for field, value in (('uid', False), ('gid', False), ('mode', True),
                                 ('uid', 1), ('gid', 1), ('mode', 0o700)):
                with self.subTest(path=path, field=field, value=value):
                    self.reset_gather()
                    old = copy.deepcopy(self.observation)
                    self.observation['policy']['directories'][path][field] = value
                    self.observation['policy_sha256'] = digest(self.observation['policy'])
                    self.reject()
                    self.observation = old

    def test_saved_policy_rejects_unknown_metadata_authority(self):
        for logical in ('/', '/opt', PARENT):
            with self.subTest(path=logical):
                self.reset_gather()
                original = copy.deepcopy(self.observation)
                self.observation['policy']['directories'][logical]['ino'] = 10
                self.observation['policy_sha256'] = digest(self.observation['policy'])
                self.reject()
                self.observation = original

    def test_missing_parent_is_not_created(self):
        (self.root / PARENT[1:]).rmdir()
        self.reject()
        self.assertFalse((self.root / PARENT[1:]).exists())
        self.assertEqual(self.boundary.mutations, [])

    def test_regular_file_is_not_a_parent_directory(self):
        path = self.root / PARENT[1:]
        path.rmdir()
        path.write_bytes(b'local invalid parent')
        self.reject()
        self.assertEqual(self.boundary.mutations, [])

    def test_symlink_parent_is_never_followed(self):
        path = self.root / PARENT[1:]
        path.rmdir()
        path.symlink_to(self.root / 'opt', target_is_directory=True)
        self.reject()
        self.assertTrue(path.is_symlink())

    def test_wrong_parent_mode_is_not_repaired(self):
        path = self.root / PARENT[1:]
        for mode in (0o700, 0o755, 0o770, 0o1750, 0o4750):
            with self.subTest(mode=oct(mode)):
                self.reset_gather()
                os.chmod(str(path), mode)
                self.reject()
                self.assertEqual(stat.S_IMODE(os.stat(str(path)).st_mode), mode)
        self.assertEqual(self.boundary.mutations, [])

    def test_wrong_parent_owner_or_group_rejected(self):
        for field in ('st_uid', 'st_gid'):
            with self.subTest(field=field):
                self.reset_gather()
                self.boundary.faults[PARENT] = {field: 12345}
                self.reject()
        self.boundary.faults.clear()

    def test_ancestors_must_be_protected_root_and_saved_mode(self):
        for logical in ('/', '/opt'):
            for field, value in (('st_uid', 12345), ('st_gid', 12345),
                                 ('st_mode', stat.S_IFDIR | 0o775),
                                 ('st_mode', stat.S_IFDIR | 0o700)):
                with self.subTest(path=logical, field=field, value=value):
                    self.reset_gather()
                    self.boundary.faults[logical] = {field: value}
                    self.reject()
                    self.boundary.faults.clear()

    def test_root_owned_ancestor_group_must_match_saved_nonzero_group(self):
        # Explicit injected GID response exercises a legal saved ancestor pin;
        # no chown or host group modification is performed.
        self.boundary.faults['/opt'] = {'st_gid': 4242}
        self.observation['policy']['directories']['/opt']['gid'] = 4242
        self.observation['policy_sha256'] = digest(self.observation['policy'])
        proof = self.capture()
        self.assertEqual(proof['ancestors']['/opt']['gid'], 4242)
        self.assertEqual(proof['metadata']['gid'], 0)
        self.gather.recheck()

    def test_descriptor_scope_cannot_include_an_extra_logical_path(self):
        self.capture()
        tree = self.gather.trees[PARENT]
        tree.by_path['/opt/not-authorized'] = tree.fd
        self.reject()

    def test_descriptor_scope_cannot_rename_parent_logical_path(self):
        self.capture()
        self.gather.trees[PARENT].opened[-1][3] = '/opt/not-authorized'
        self.reject()

    def test_ancestor_symlink_is_never_followed(self):
        opt = self.root / 'opt'
        other = self.root / 'renamed-opt'
        opt.rename(str(other))
        opt.symlink_to(other, target_is_directory=True)
        self.reject()

    def test_successful_capture_ignores_unrelated_children(self):
        (self.root / PARENT[1:] / 'unrelated-private-file').write_bytes(b'not read')
        self.capture()
        self.assertEqual(set(row[0] for row in self.boundary.open_log), {'/', '/opt', PARENT})
        self.assertEqual(self.boundary.mutations, [])

    def test_acl_and_capability_presence_fail_closed(self):
        for logical in ('/', '/opt', PARENT):
            for name in ('system.posix_acl_access', 'system.posix_acl_default',
                         'security.capability'):
                with self.subTest(path=logical, xattr=name):
                    self.reset_gather()
                    self.boundary.xattrs[(logical, name)] = b'injected-present-xattr'
                    self.reject()
                    self.boundary.xattrs.clear()

    def test_unreadable_acl_fails_closed(self):
        self.boundary.xattrs[(PARENT, 'system.posix_acl_access')] = OSError(errno.EACCES, 'local fault')
        self.reject()

    def test_boolean_metadata_never_equals_root_zero_or_identity_one(self):
        for field in ('st_uid', 'st_gid', 'st_dev', 'st_ino', 'st_nlink',
                      'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            with self.subTest(field=field):
                self.reset_gather()
                self.boundary.faults[PARENT] = {field: False if field != 'st_nlink' else True}
                self.reject()
                self.boundary.faults.clear()

    def test_invalid_numeric_metadata_rejected(self):
        for field, value in (('st_dev', -1), ('st_ino', 0), ('st_nlink', 0),
                             ('st_size', -1), ('st_mtime_ns', -1),
                             ('st_ctime_ns', 2 ** 64)):
            with self.subTest(field=field, value=value):
                self.reset_gather()
                self.boundary.faults[PARENT] = {field: value}
                self.reject()
                self.boundary.faults.clear()

    def test_collection_rejects_real_parent_mode_race(self):
        def change_once(logical):
            if logical == PARENT:
                self.boundary.after_stat = None
                os.chmod(str(self.root / PARENT[1:]), 0o700)
        self.boundary.after_stat = change_once
        self.reject()
        self.assertIsNone(self.gather.release_evidence)

    def test_collection_rejects_real_parent_replacement_race(self):
        def replace_once(logical):
            if logical == PARENT:
                self.boundary.after_stat = None
                path = self.root / PARENT[1:]
                path.rename(str(path) + '.retired')
                path.mkdir(mode=0o750)
        self.boundary.after_stat = replace_once
        self.reject()
        self.assertIsNone(self.gather.release_evidence)

    def test_boolean_saved_observation_drift_cannot_equal_integer(self):
        self.observation['numeric_marker'] = 1
        self.capture()
        self.observation['numeric_marker'] = True
        self.reject(self.gather.recheck)

    def test_recheck_detects_actual_parent_mode_change(self):
        self.capture()
        os.chmod(str(self.root / PARENT[1:]), 0o700)
        self.reject(self.gather.recheck)

    def test_recheck_detects_actual_parent_replacement(self):
        self.capture()
        path = self.root / PARENT[1:]
        path.rename(str(path) + '.retired')
        path.mkdir(mode=0o750)
        self.reject(self.gather.recheck)

    def test_recheck_detects_acl_and_metadata_drift(self):
        self.capture()
        self.boundary.xattrs[(PARENT, 'system.posix_acl_default')] = b'injected-acl'
        self.reject(self.gather.recheck)
        self.boundary.xattrs.clear()
        actual = os.stat(str(self.root / PARENT[1:]))
        self.boundary.faults[PARENT] = {'st_ino': actual.st_ino + 1}
        self.reject(self.gather.recheck)

    def test_recheck_rejects_observation_or_policy_mutation(self):
        self.capture()
        original = copy.deepcopy(self.observation)
        self.observation['private_fixture_marker'] = 'changed full observation'
        self.reject(self.gather.recheck)
        self.observation.clear()
        self.observation.update(original)
        self.observation['policy']['directories']['/opt']['mode'] = 0o700
        self.observation['policy_sha256'] = digest(self.observation['policy'])
        self.reject(self.gather.recheck)

    def test_recheck_retained_file_reads_are_real_and_unchanged(self):
        path = self.root / 'opt/retained.txt'
        path.write_bytes(b'LOCAL retained bytes\n')
        os.chmod(str(path), 0o600)
        first, unused = self.gather.read('/opt/retained.txt', 1024, private=True)
        self.capture()
        self.gather.recheck()
        self.assertEqual(self.gather.rows['/opt/retained.txt'][0], first)
        path.write_bytes(b'LOCAL modified bytes\n')
        self.reject(self.gather.recheck)
        self.assertEqual(self.gather.rows['/opt/retained.txt'][0], first)
        self.assertNotIn(PARENT, self.gather.rows)

    def test_close_releases_every_owned_real_descriptor(self):
        self.capture()
        held = tuple(self.boundary.fds)
        self.assertTrue(held)
        self.gather.close()
        self.assertEqual(self.boundary.fds, {})
        self.assertEqual(self.gather.trees, {})
        for fd in held:
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.gather.close()

    def test_constructor_failure_does_not_leak_descriptors(self):
        self.boundary.faults[PARENT] = {'st_uid': 12345}
        self.reject()
        self.gather.close()
        self.assertEqual(self.boundary.fds, {})

    def test_close_failure_marks_primary_and_continues_cleanup(self):
        self.capture()
        primary = ValueError('local primary failure')
        self.boundary.close_fault = True
        self.gather.close(primary)
        self.assertTrue(primary.preparation_cleanup_failed)
        self.assertEqual(self.boundary.fds, {})

    def test_close_failure_without_primary_is_explicit(self):
        self.capture()
        self.boundary.close_fault = True
        with self.assertRaises(self.prep.CleanupError):
            self.gather.close()
        self.assertEqual(self.boundary.fds, {})

    def test_full_observation_hash_rejects_nonfinite_json(self):
        self.observation['nonfinite'] = float('nan')
        self.reject()


class CompileAndOrderingTests(unittest.TestCase):
    def setUp(self):
        self.prep = load_module(HERE / 'epoch7_prepare.py', 'local_prepare_wiring_test')

    def test_original_saved_sources_and_review_authority_unchanged(self):
        baseline = load_module(HERE.parent / 'baseline-preparation/epoch7_prepare.py',
                               'local_baseline_prepare_test')
        for name in ('PREPARATION_SOURCES', 'SAVED_PROJECTION_SOURCES',
                     'SAVED_PROJECTION_MANIFEST_SHA', 'EXPECTED_REVIEW_BODY_SHA',
                     'OBSERVATION_PATH', 'OBSERVATION_SHA'):
            self.assertEqual(getattr(self.prep, name), getattr(baseline, name), name)
        for name in ('epoch7_prepare_data.py', 'epoch7_topology_projection.py'):
            self.assertEqual((HERE / name).read_bytes(),
                             (HERE.parent / 'baseline-preparation' / name).read_bytes())

    def test_target_artifact_is_explicitly_unbound_before_bootstrap(self):
        self.prep.require_binding()  # Original A source is still bound.
        self.assertEqual(self.prep.COMPILER_KIT_ROOT,
                         self.prep.CAND + '/epoch7-recovery-candidate-r7-parentfix')
        for name in ('COMPILER_KIT_SHA', 'COMPILER_ENTRY_SHA'):
            self.assertIsNone(getattr(self.prep, name))
        with self.assertRaisesRegex(ValueError, 'COMPILER_ARTIFACT_UNBOUND'):
            self.prep.require_compiler_binding()
        with mock.patch.object(self.prep, 'bootstrap_entry') as bootstrap:
            with self.assertRaisesRegex(ValueError, 'COMPILER_ARTIFACT_UNBOUND'):
                self.prep.run_preparation(types.SimpleNamespace(), time.monotonic() + 30)
            bootstrap.assert_not_called()

    def test_original_cachedsources_loads_preparation_in_clean_isolated_context(self):
        script = r"""
import contextlib, hashlib, importlib, json, sys, types
from pathlib import Path
here = Path(sys.argv[1])
stage = here.parent.parent
root = stage / 'kit/epoch7-recovery-candidate-r7'
def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module
entry = load(root / 'epoch7_recovery_entry.py', 'isolated_original_entry')
prep = load(here / 'epoch7_prepare.py', 'isolated_preparation')
raw_manifest = (root / 'recovery-kit-manifest.json').read_bytes()
assert hashlib.sha256(raw_manifest).hexdigest() == prep.KIT_SHA
manifest = json.loads(raw_manifest.decode('ascii'))
cache = {}
for name, pin in manifest['files'].items():
    raw = (root / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin, name
    cache[name] = raw
kit = entry.VerifiedKit(str(root), manifest, cache, prep.KIT_SHA, raw_manifest=raw_manifest)
preparation_cache = {name: (here / (name + '.py')).read_bytes() for name in prep.PREPARATION_SOURCES}
assert not set(manifest['modules']).intersection(sys.modules)
assert 'epoch7_prepare_data' not in sys.modules
assert 'epoch7_topology_projection' not in sys.modules
with contextlib.ExitStack() as preparation_scope:
    with kit.imports() as importer:
        data, topology = preparation_scope.enter_context(prep.preparation_modules(preparation_cache))
        assert 'epoch7_approval' in importer.loaded
        assert 'node_sqlite_probe' in importer.loaded
        assert 'probe_driver' in importer.loaded
        assert 'probe_helpers' in importer.loaded
        assert sys.modules['epoch7_prepare_data'] is data
        assert sys.modules['epoch7_topology_projection'] is topology
    assert not set(manifest['modules']).intersection(sys.modules)
    assert sys.modules['epoch7_prepare_data'] is data
    assert sys.modules['epoch7_topology_projection'] is topology
    # Enter an independent candidate namespace after the saved-A namespace
    # exits. This checks real CachedSources cleanup, without invented pins.
    target_cache = dict(cache)
    overlay = here.parent / 'kit-overlay'
    for file in overlay.rglob('*.py'):
        relative = str(file.relative_to(overlay))
        target_cache[relative] = file.read_bytes()
    target = entry.VerifiedKit(str(overlay), manifest, target_cache, 'LOCAL_UNBOUND')
    with target.imports():
        factory = importlib.import_module('epoch7_host_factory')
        assert 'fresh_release_parent' in factory.INPUTS
        assert sys.modules['epoch7_prepare_data'] is data
assert 'epoch7_prepare_data' not in sys.modules
assert 'epoch7_topology_projection' not in sys.modules
assert not set(manifest['modules']).intersection(sys.modules)
print('LOCAL_CLEAN_CACHEDSOURCES_OK')
"""
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', script, str(HERE)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'LOCAL_CLEAN_CACHEDSOURCES_OK')

    def test_private_seed_attaches_only_independent_fresh_field(self):
        observed = {}
        modules = {
            'epoch7_additive_identity': types.SimpleNamespace(PATH='/identity-owner'),
            'epoch7_additive_server': types.SimpleNamespace(PATH='/identity-server'),
            'epoch7_complete_approval': types.SimpleNamespace(expected_complete_from_inputs=lambda *a: {}),
            'epoch7_injected_recovery': types.SimpleNamespace(required_authorization=lambda *a: {}),
        }
        def hydrate(value, factory):
            observed['wire'] = copy.deepcopy(value)
            return copy.deepcopy(value)
        def prepare(seed):
            observed['seed'] = copy.deepcopy(seed)
            return {'state': 'COMPILED_NOT_ADMITTED', 'unresolved': [], 'install_admission': False,
                    'inputs': {'snapshot': {}, 'candidate': {}, 'access_rows': []}}
        modules['epoch7_host_factory'] = types.SimpleNamespace(
            prepare_host_inputs=prepare, compile_host_contract=lambda inputs: {},
            d=types.SimpleNamespace(digest=digest, build_delta=lambda *a: {}))
        data = types.SimpleNamespace(RAW_PATHS={}, canonical=canonical,
            owner_policy=lambda *a: (b'owner', {'path': '/identity-owner'}),
            seed_wire=lambda seed: canonical(seed))
        fresh = {'fixture': 'independent fresh parent', 'metadata': {'ino': 123}}
        collected = {'observation': {'snapshot_sha256': 'a' * 64, 'evidence': {'retained': {}}},
            'compiled': {'rendered_targets': {}, 'old_rendered_targets': {}, 'tls_config_bytes': b'tls'},
            'manifest_raw': b'{}', 'source_payloads': {}, 'tool_sources': {},
            'socket_dropins': {}, 'fresh_unit_authority': {'saved_unit_dropins_sha256': digest({})},
            'fresh_release_parent': fresh, 'buffers': {}}
        before = copy.deepcopy(collected)
        kit = types.SimpleNamespace(digest='b' * 64, _hydrate_seed=hydrate)
        with mock.patch.object(self.prep.importlib, 'import_module', side_effect=lambda name: modules[name]), \
             mock.patch.object(self.prep, 'server_policy', return_value=(b'server', {'path': '/identity-server'})):
            bundle = self.prep.compile_private_bundle(kit, collected, b'{}', {}, True, data)
        self.assertEqual(observed['wire']['fresh_release_parent'], fresh)
        self.assertEqual(observed['seed']['fresh_release_parent'], fresh)
        self.assertEqual(json.loads(bundle['seed_raw'].decode('ascii'))['fresh_release_parent'], fresh)
        self.assertEqual(set(observed['wire']), {'observation', 'compiled', 'additive_deltas',
            'identity_payloads', 'activate_retained_renewal_timer', 'fresh_release_parent'})
        self.assertEqual(collected, before)
        self.assertEqual(observed['wire']['observation'], before['observation'])
        self.assertNotIn('fresh_release_parent', observed['wire']['observation'])

    def test_run_captures_before_compile_and_rechecks_before_after_output(self):
        events = []
        prep = self.prep
        observation = {'fixture': 'saved unmodified'}
        fresh = {'fixture': 'independent parent'}
        collected = {'observation': observation, 'manifest_raw': b'{}', 'source_payloads': {},
                     'receipt_raw': b'{}', 'receipt_metadata': {}}
        proposal = {'topology_raw': b'{}', 'expected_review_body': {}}
        data = types.SimpleNamespace(MANIFEST_PATH='deploy/integration-manifest.json')
        topology = types.SimpleNamespace(project_saved_unit_dropins=lambda o: {},
            project_topology=lambda *a: proposal, canonical=canonical,
            fetch_topology_review=lambda *a: {})
        @contextlib.contextmanager
        def kit_imports():
            events.append('original_imports_enter')
            yield
            events.append('original_imports_exit')
        @contextlib.contextmanager
        def compiler_imports():
            events.append('compiler_imports_enter')
            yield
            events.append('compiler_imports_exit')
        @contextlib.contextmanager
        def prep_imports(cache):
            yield data, topology
        kit = types.SimpleNamespace(digest='b' * 64, raw_manifest=b'{}',
            manifest={'modules': {name: name for name in
                ('probe_driver', 'probe_helpers', 'node_sqlite_probe', 'unit_metadata', 'snapshot_io')}},
            cache={name: b'' for name in
                ('probe_driver', 'probe_helpers', 'node_sqlite_probe', 'unit_metadata', 'snapshot_io')},
            imports=kit_imports, _authenticate_probe_receipt=lambda o: events.append('receipt'))
        compiler_kit = copy.copy(kit)
        compiler_kit.digest = 'c' * 64
        compiler_kit.cache = dict(kit.cache)
        compiler_kit.cache['xuanjun-p2-package/' + data.MANIFEST_PATH] = b'{}'
        compiler_kit.imports = compiler_imports
        def verify_kit(*args):
            events.append('verify_original_kit')
            return kit
        def verify_compiler_kit(*args):
            events.append('verify_compiler_kit')
            return compiler_kit
        entry = types.SimpleNamespace(verify_kit=verify_kit)
        compiler_entry = types.SimpleNamespace(verify_kit=verify_compiler_kit)
        class Gather(object):
            def __init__(self, *args):
                pass
            def saved_unit_dropins(self, *args):
                events.append('fresh_units')
                return {}
            def release_parent(self, value):
                self_value = copy.deepcopy(value)
                if self_value != observation:
                    raise AssertionError('Observation was replaced')
                events.append('fresh_parent')
                return fresh
            def check(self):
                pass
            def recheck(self):
                events.append('recheck')
            def accept_owned_publication(self, outputs):
                events.append('owned_output')
            def close(self, primary):
                events.append('close')
        def compile_bundle(kit, value, *args):
            self.assertIs(kit, compiler_kit)
            self.assertIs(value['fresh_release_parent'], fresh)
            self.assertEqual(value['observation'], {'fixture': 'saved unmodified'})
            events.append('compile')
            return {'summary': {}, 'unsigned_approval': {}}
        def publish(*args):
            events.append('publish')
            return []
        args = types.SimpleNamespace(observation=prep.OBSERVATION_PATH,
            observation_sha256=prep.OBSERVATION_SHA, operation='prepare',
            topology_review_id=1, retained_renewal_timer='enable-after-reviewed-checks')
        with contextlib.ExitStack() as stack:
            replacements = {'require_binding': lambda: None, 'require_compiler_binding': lambda: None,
                'bootstrap_entry': lambda compiler=False: compiler_entry if compiler else entry,
                'Gatherer': Gather, 'preparation_sources': lambda gather: ({}, {}),
                'preparation_modules': prep_imports, 'collect_inputs': lambda *a: collected,
                'compile_private_bundle': compile_bundle, 'publish_bundle': publish,
                'verify_publication': lambda *a: events.append('verify_output'),
                'EXPECTED_REVIEW_BODY_SHA': digest({})}
            for name, value in replacements.items():
                stack.enter_context(mock.patch.object(prep, name, value))
            stack.enter_context(mock.patch.object(prep.os, 'geteuid', return_value=0))
            stack.enter_context(mock.patch('socket.gethostname', return_value=prep.HOST))
            prep.run_preparation(args, time.monotonic() + 30)
        self.assertLess(events.index('original_imports_exit'), events.index('compiler_imports_enter'))
        self.assertLess(events.index('fresh_parent'), events.index('compile'))
        self.assertLess(events.index('fresh_parent'), events.index('original_imports_exit'))
        compile_index, publish_index = events.index('compile'), events.index('publish')
        self.assertIn('recheck', events[compile_index + 1:publish_index])
        self.assertIn('recheck', events[publish_index + 1:])
        self.assertEqual(events[-1], 'close')
        self.assertEqual(observation, {'fixture': 'saved unmodified'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
