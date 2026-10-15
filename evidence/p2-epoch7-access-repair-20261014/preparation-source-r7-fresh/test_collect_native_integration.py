"""Public, local collect_inputs -> Gatherer.read regression, without host access.

The frozen public full-factory fixture supplies synthetic observation/retained
bytes. Real frozen validators check that observation. All collected files live
in a disposable local filesystem. Only paths and portable UID/GID observations
are mapped; opens, fstats, stat stamps, no-follow, nlink, reads, hashes, xattrs,
and rechecks are real. See README.md for the unrelated synthetic seams.
"""
import copy
import hashlib
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
REPAIR = HERE.parent
FROZEN = HERE / 'test_fixtures'
KIT = pathlib.Path(os.environ.get('EPOCH7_PREP_TEST_KIT_ROOT','/workspace/shared/r7-artifact-dc18f73e/python312/build-a/epoch7-recovery-candidate-r7'))
sys.path[:0] = [str(HERE), str(KIT / 'helpers')] + [
    str(path) for path in sorted((KIT / 'tests').iterdir()) if path.is_dir()
] + [str(KIT / 'xuanjun-p2-package/stage1')]

import epoch7_prepare_data as data
import epoch7_host_factory as factory
import test_epoch7_prepare as public_fixture


def load_source(name, path, expected_sha256=None):
    raw = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('PUBLIC_FIXTURE_SOURCE_PIN')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


fixed = load_source('contract_fixed_candidate', HERE / 'epoch7_prepare.py')
frozen = load_source('native_frozen_candidate', FROZEN / 'epoch7_prepare_frozen_r6.py',
                     '83c218fc10d19094446494e10767be58593f09dbc92866cbc8779d9a0e776ebc')
# TEST_ONLY_NEVER_HOST_DELIVERED: byte-identical, pinned intermediate baseline.
native_only = load_source('native_only_candidate', HERE / 'test_fixtures/epoch7_prepare_native_only.py',
                          'e4b377b9b4913f72e79a940ce39890d5512db6792b68c6da81f4e8756e375510')
entry = fixed.load_entry((KIT / 'epoch7_recovery_entry.py').read_bytes())
NATIVE = data.RAW_PATHS['native_before']


class CollectNativeIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='public-native-', dir=str(HERE))
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.seed, self.tools = public_fixture.seed_fixture()
        self.observation = self.seed['observation']
        self.native_gid = 0
        self.mutate_during_read = False
        self.mutate_before_recheck = False
        self.native_reads = 0
        self.native_identity = None
        self.paths_read = []
        self.tool_identities = {}
        self.tool_reads = {}
        self.tool_mutate_during_read = None
        self.tool_mutate_before_recheck = None

        for key, logical in data.RAW_PATHS.items():
            expected = self.observation['evidence']['retained']['files'][logical]
            mode = 0o644 if logical == NATIVE else expected['mode']
            self.write(logical, self.seed[key], mode)
            self.observation['evidence']['retained']['files'][logical] = self.row(logical)
        self.native_identity = self.identity(os.stat(str(self.local(NATIVE))))
        # Native mode/owner are also validated by frozen snapshot.validate_policy.
        self.assertEqual(tuple(self.row(NATIVE)[key] for key in ('uid', 'gid', 'mode', 'nlink')),
                         (0, 0, 0o644, 1))

        self.original = b'{"fixture":"public original plan seam"}\n'
        self.write(fixed.CAND + '/protected-core-install-plan.json', self.original, 0o600)
        oldkit = fixed.CAND + '/epoch5-recovery-candidate-v4'
        self.write(oldkit + '/recovery-kit-manifest.json', b'{"fixture":"public historical kit"}\n')
        for name in data.V4_ORDER:
            self.write(oldkit + '/helpers/' + name + '.py', b'# Public historical helper placeholder. Never executed.\n')
        historical = {'stage1/public_fixture_%03d.py' % index:
                      ('# public source %d\n' % index).encode('ascii') for index in range(102)}
        self.historical_manifest = fixed.packed({'files': {name: fixed.sha(raw) for name, raw in historical.items()}})
        for root in (data.ORIGINAL_ROOT, data.V4_ROOT):
            self.write(root + '/deploy/integration-manifest.json', self.historical_manifest)
            for name, raw in historical.items():
                self.write(root + '/' + name, raw)
        for path, raw in self.tools.items():
            self.write(path, raw, 0o755)
            self.observation['evidence']['retained']['files'][path] = self.row(path)
            self.tool_identities[path] = self.identity(os.stat(str(self.local(path))))
            self.tool_reads[path] = 0
        manager = self.observation['evidence']['writers']['manager']
        manager_row = self.observation['evidence']['retained']['files'][manager['binary_path']]
        manager['binary_identity'] = [manager_row['dev'], manager_row['ino']]

        attempt = self.observation['finite_probe']
        self.receipt_raw = fixed.packed({'schema': 1, 'nonce': attempt['nonce'],
            'policy_sha256': attempt['policy_sha256'],
            'events': [{'event': 'NODE_SQLITE_OBSERVED', 'detail': attempt['result']['node_sqlite']}]})
        receipt = attempt['result']['created_receipt']
        self.write(receipt['path'], self.receipt_raw, 0o600)
        receipt['sha256'] = fixed.sha(self.receipt_raw)
        receipt['metadata'] = {key: self.row(receipt['path'])[key] for key in data.STAT_FIELDS}

        self.source_cache = {'xuanjun-p2-package/' + name: raw
                            for name, raw in self.seed['source_payloads'].items()}
        self.source_cache['xuanjun-p2-package/' + data.MANIFEST_PATH] = self.seed['source_manifest_raw']

        self.refresh_observation()

    def refresh_observation(self):
        attempt = self.observation['finite_probe']
        receipt = attempt['result']['created_receipt']
        # Recompute only synthetic fixture bindings after replacing its invented
        # retained stamps with the real disposable-file stamps.
        observation = self.observation
        support = observation['evidence']['retained']
        writers = observation['evidence']['writers']
        manager_digest = factory.d.digest(writers['manager'])
        observation['openclaw_profile']['recipe_evidence']['quiet_bootstrap']['manager_sha256'] = manager_digest
        observation['openclaw_profile_sha256'] = factory.d.digest(observation['openclaw_profile'])
        observation['unit_metadata']['sections']['command_resolutions']['evidence']['provenance']['manager_sha256'] = manager_digest
        observation['snapshot']['writer_exclusion']['evidence_sha256'] = factory.d.digest(writers)
        observation['evidence']['writer_observation_comparison'] = factory.snap.validate_writer_transition(writers, writers)
        support['policy_sha256'] = factory.d.digest(observation['policy'])
        observation['snapshot']['retained_resource_sha256'] = factory.d.digest(support)
        observation['evidence']['snapshot_sha256'] = factory.d.digest(observation['snapshot'])
        for key in ('snapshot', 'evidence', 'policy', 'unit_metadata', 'probe_metadata'):
            observation[key + '_sha256'] = factory.d.digest(observation[key])
        # The synthetic finite-probe proof binds the updated observation. Rebuild
        # it through the frozen public proof fixture, without running a probe.
        probe_policy = attempt['policy']
        probe_policy['node_sqlite'] = public_fixture.node.binding_from_observation(observation)
        probe_pin = fixed.sha(fixed.packed(probe_policy))
        binding = probe_policy['node_sqlite']
        proof = public_fixture.fixture_proof(binding['node'], probe_policy['nonce'], probe_pin,
                                             binding['probe_input_sha256'])
        attempt['policy_sha256'] = probe_pin
        attempt['result']['node_sqlite'] = proof
        receipt['node_sqlite_event_sha256'] = factory.d.digest(proof)
        self.receipt_raw = fixed.packed({'schema': 1, 'nonce': attempt['nonce'],
            'policy_sha256': probe_pin, 'events': [{'event': 'NODE_SQLITE_OBSERVED', 'detail': proof}]})
        self.write(receipt['path'], self.receipt_raw, 0o600)
        receipt['sha256'] = fixed.sha(self.receipt_raw)
        receipt['metadata'] = {key: self.row(receipt['path'])[key] for key in data.STAT_FIELDS}
        self.observation_path = fixed.CAND + '/epoch7-observation-' + 'a' * 16 + '.private.json'
        self.observation_raw = fixed.packed(observation)
        self.write(self.observation_path, self.observation_raw, 0o600)

    def assert_frozen_validation_accepts(self):
        with public_fixture.native_pins(self.seed):
            self.assertIs(data.validate_observation(self.observation, factory), self.observation)

    def local(self, logical):
        self.assertTrue(logical.startswith('/'))
        return self.root / logical.lstrip('/')

    def write(self, logical, raw, mode=0o644):
        path = self.local(logical)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        os.chmod(str(path), mode)

    @staticmethod
    def identity(info):
        return info.st_dev, info.st_ino

    def mapped_info(self, info):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        values.update(st_uid=0, st_gid=(self.native_gid if self.identity(info) == self.native_identity else 0))
        return types.SimpleNamespace(**values)

    def row(self, logical):
        raw = self.local(logical).read_bytes()
        return dict(fixed.stamps(self.mapped_info(os.stat(str(self.local(logical))))),
                    kind='FILE', sha256=fixed.sha(raw))

    def run_collect(self, module=fixed):
        fixture = self
        class MappedTree(entry.DescriptorTree):
            def __init__(self, root):
                # Only the root route and offline owner allowlist differ from
                # production. The authenticated DescriptorTree remains real.
                super(MappedTree, self).__init__(str(fixture.local(root)),
                    owners=((0, 0), (os.getuid(), os.getgid())))
        mapped_entry = types.SimpleNamespace(DescriptorTree=MappedTree, decode=entry.decode, relative=entry.relative)
        proxy = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if not name.startswith('__')})
        proxy.stat = lambda *args, **kwargs: self.mapped_info(os.stat(*args, **kwargs))
        proxy.fstat = lambda *args, **kwargs: self.mapped_info(os.fstat(*args, **kwargs))
        def read(fd, maximum):
            native = self.identity(os.fstat(fd)) == self.native_identity
            tool = next((path for path, identity in self.tool_identities.items()
                         if identity == self.identity(os.fstat(fd))), None)
            raw = os.read(fd, maximum)
            if tool is not None:
                self.tool_reads[tool] += 1
                if self.tool_mutate_during_read == tool and raw:
                    self.tool_mutate_during_read = None
                    with self.local(tool).open('ab') as stream:
                        stream.write(b' ')
            if native:
                self.native_reads += 1
                if self.mutate_during_read and raw:
                    self.mutate_during_read = False
                    with self.local(NATIVE).open('ab') as stream:
                        stream.write(b' ')
            return raw
        proxy.read = read

        def receipt_fixture(observation):
            # This public receipt deliberately represents the fixture proof,
            # not a host-created proof. The real collect read still follows.
            self.assertEqual(observation['finite_probe']['result']['created_receipt']['sha256'],
                             fixed.sha(self.receipt_raw))
        kit = types.SimpleNamespace(cache=self.source_cache, _authenticate_probe_receipt=receipt_fixture)
        def reproduce(original, oldmanifest, oldpayloads, v4manifest, v4payloads, kitraw, helpers):
            self.assertEqual(original, self.original)
            self.assertEqual(oldmanifest, self.historical_manifest)
            self.assertEqual(v4manifest, self.historical_manifest)
            self.assertEqual(len(oldpayloads), 102)
            self.assertEqual(len(v4payloads), 102)
            self.assertEqual(set(helpers), set(data.V4_ORDER))
            return b'{"fixture":"public reproduced v4 plan seam"}\n'

        gather = module.Gatherer(mapped_entry, time.monotonic() + 60)
        # Socket drop-in collection is outside this native-file regression.
        original_recheck=gather.recheck
        mutated=[False]
        def before_recheck():
            if mutated[0]:return original_recheck()
            mutated[0]=True
            if self.tool_mutate_before_recheck is not None:
                with self.local(self.tool_mutate_before_recheck).open('ab') as stream:
                    stream.write(b' ')
            if self.mutate_before_recheck:
                with self.local(NATIVE).open('ab') as stream:
                    stream.write(b' ')
            return original_recheck()
        gather.recheck=before_recheck
        gather.socket_dropins=lambda:copy.deepcopy(public_fixture.topology_fixture()['dropins'])
        primary = None
        try:
            with mock.patch.object(module, 'os', proxy), \
                    mock.patch.object(data, 'ORIGINAL_PLAN', fixed.sha(self.original)), \
                    mock.patch.object(data, 'ORIGINAL_MANIFEST', fixed.sha(self.historical_manifest)), \
                    mock.patch.object(data, 'V4_MANIFEST', fixed.sha(self.historical_manifest)), \
                    mock.patch.object(data, 'reproduce_v4', side_effect=reproduce), \
                    mock.patch.object(data, 'compile_bindings', return_value=copy.deepcopy(self.seed['compiled'])), \
                    public_fixture.native_pins(self.seed):
                result = module.collect_inputs(gather, kit, data, self.observation_path,
                                               fixed.sha(self.observation_raw))
            self.paths_read = sorted(gather.rows)
            return result
        except BaseException as error:
            primary = error
            raise
        finally:
            gather.close(primary)

    def test_frozen_wrapper_reproduces_native_authority_failure(self):
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY'):
            self.run_collect(frozen)
        self.assertEqual(self.native_reads, 0)

    def test_fixed_wrapper_collects_six_buffers_and_rechecks_native(self):
        result = self.run_collect()
        self.assertEqual(set(result['buffers']), set(data.RAW_PATHS))
        self.assertEqual(result['buffers']['native_before'], self.seed['native_before'])
        self.assertIn(NATIVE, self.paths_read)
        self.assertGreaterEqual(self.native_reads, 4)  # read+EOF, then final read+EOF
        self.assertEqual(len(self.paths_read), 222)
        self.assertEqual(result['tool_sources'], self.tools)
        for path in self.tools:
            self.assertGreaterEqual(self.tool_reads[path], 4)

    def test_wrong_native_gid_refuses(self):
        self.native_gid = 1002
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_FILE_AUTHORITY'):
            self.run_collect()

    def test_wrong_native_mode_refuses(self):
        os.chmod(str(self.local(NATIVE)), 0o640)
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_GATHER_OBSERVATION_DRIFT'):
            self.run_collect()

    def test_native_mutation_since_observation_refuses(self):
        with self.local(NATIVE).open('ab') as stream:
            stream.write(b' ')
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_GATHER_OBSERVATION_DRIFT'):
            self.run_collect()

    def test_native_mutation_during_real_fd_read_refuses(self):
        self.mutate_during_read = True
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_GATHER_FD_RACE'):
            self.run_collect()
        self.assertGreater(self.native_reads, 0)

    def test_native_mutation_before_final_recheck_refuses(self):
        self.mutate_before_recheck = True
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_GATHER_OBSERVATION_DRIFT'):
            self.run_collect()
        self.assertGreaterEqual(self.native_reads, 4)

    def test_native_second_hardlink_refuses(self):
        os.link(str(self.local(NATIVE)), str(self.local(NATIVE)) + '.alias')
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_FILE_AUTHORITY'):
            self.run_collect()

    def test_native_symlink_refuses(self):
        native = self.local(NATIVE)
        replacement = native.with_name('synthetic-native-target.json')
        native.rename(replacement)
        os.symlink(str(replacement), str(native))
        with self.assertRaises(OSError):
            self.run_collect()


def tool_regression(label, scenario):
    """Each generated test receives its own disposable full collection fixture."""
    def test(self):
        path = (self.observation['evidence']['writers']['manager']['binary_path']
                if label == 'systemd' else '/usr/bin/systemctl')
        target = self.local(path)
        failure = 'EPOCH7_PREP_GATHER_OBSERVATION_DRIFT'
        if scenario == 'changed_bytes':
            raw = target.read_bytes()
            target.write_bytes(b'X' + raw[1:])
        elif scenario == 'same_bytes_new_inode':
            replacement = target.with_name(target.name + '.replacement')
            replacement.write_bytes(target.read_bytes())
            os.chmod(str(replacement), 0o755)
            os.replace(str(replacement), str(target))
            self.assertNotEqual(self.identity(os.stat(str(target))), self.tool_identities[path])
        elif scenario == 'mode_drift':
            os.chmod(str(target), 0o644)
        elif scenario == 'during_read_mutation':
            self.tool_mutate_during_read = path
            failure = 'EPOCH7_PREP_GATHER_FD_RACE'
        elif scenario == 'final_reread_mutation':
            self.tool_mutate_before_recheck = path
        elif scenario == 'wrong_policy_path':
            other = '/usr/bin/systemctl' if label == 'systemd' else self.observation['evidence']['writers']['manager']['binary_path']
            self.observation['policy']['executables'][label] = {
                'path': other, 'sha256': self.observation['policy']['files'][other]['sha256']}
            self.refresh_observation()
            self.assert_frozen_validation_accepts()
            failure = 'EPOCH7_PREP_TOOL_OBSERVATION_BINDING'
        elif scenario == 'wrong_policy_digest':
            self.observation['policy']['executables'][label]['sha256'] = '0' * 64
            self.observation['policy']['files'][path]['sha256'] = '0' * 64
            self.refresh_observation()
            self.assert_frozen_validation_accepts()
            failure = 'EPOCH7_PREP_TOOL_OBSERVATION_BINDING'
        elif scenario == 'bool_retained_nlink':
            self.observation['evidence']['retained']['files'][path]['nlink'] = True
            self.refresh_observation()
            self.assert_frozen_validation_accepts()
        else:
            raise AssertionError('Unknown public tool test scenario')
        with self.assertRaisesRegex(ValueError, failure):
            self.run_collect()
        if scenario == 'during_read_mutation':
            self.assertGreater(self.tool_reads[path], 0)
        if scenario == 'final_reread_mutation':
            self.assertGreaterEqual(self.tool_reads[path], 4)
    return test


def native_only_gap(label):
    def test(self):
        path = (self.observation['evidence']['writers']['manager']['binary_path']
                if label == 'systemd' else '/usr/bin/systemctl')
        raw = self.local(path).read_bytes()
        self.local(path).write_bytes(b'X' + raw[1:])
        result = self.run_collect(native_only)
        self.assertNotEqual(fixed.sha(result['tool_sources'][path]),
                            self.observation['evidence']['retained']['files'][path]['sha256'])
    return test


def manager_regression(field):
    def test(self):
        manager = self.observation['evidence']['writers']['manager']
        if field == 'sha256':
            manager['binary_sha256'] = '0' * 64
        elif field in ('dev', 'ino'):
            manager['binary_identity'][0 if field == 'dev' else 1] += 1
        elif field == 'bool_identity':
            manager['binary_identity'][0] = True
        else:
            raise AssertionError('Unknown public manager test field')
        self.refresh_observation()
        self.assert_frozen_validation_accepts()
        with self.assertRaisesRegex(ValueError, 'EPOCH7_PREP_MANAGER_OBSERVATION_BINDING'):
            self.run_collect()
    return test


for tool_label in ('systemd', 'systemctl'):
    for tool_scenario in ('changed_bytes', 'same_bytes_new_inode', 'mode_drift',
                          'during_read_mutation', 'final_reread_mutation',
                          'wrong_policy_path', 'wrong_policy_digest', 'bool_retained_nlink'):
        setattr(CollectNativeIntegration, 'test_' + tool_label + '_' + tool_scenario + '_refuses',
                tool_regression(tool_label, tool_scenario))
    setattr(CollectNativeIntegration, 'test_native_only_' + tool_label + '_gap_reproduces',
            native_only_gap(tool_label))
for manager_field in ('sha256', 'dev', 'ino', 'bool_identity'):
    setattr(CollectNativeIntegration, 'test_manager_' + manager_field + '_binding_refuses',
            manager_regression(manager_field))


if __name__ == '__main__':
    unittest.main(verbosity=2)
