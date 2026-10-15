"""R7-pinned pure data-layer regression tests; synthetic host facts only.

The public cache is authenticated before importing its helper/test closure.
No retained host files, private observation, private plan or approval is used.
Run directly with Python -I -S -B, or through the preparation test harness.
"""
import copy
import hashlib
import json
import os
import pathlib
import sys
import unittest
from unittest import mock


KIT_SHA = '7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
KIT_SOURCE = 'dc18f73e67818dc59f5acea247dbf05443bde10d'
KIT_TREE = '860d1a126b3a447c60079e315ebb549fcf5333aa'
RUNTIME_SHA = '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c'
RUNTIME_SOURCE = '4ed2f5114e2f065266af26eedd8d62aebdbf0957'
RUNTIME_TREE = '0c2cbcb0f898331865bbdfdf39f2c85ef675a88a'
DEFAULT_KIT = '/workspace/shared/r7-artifact-dc18f73e/python312/build-a/epoch7-recovery-candidate-r7'
HERE = pathlib.Path(__file__).resolve().parent
KIT = pathlib.Path(os.environ.get('EPOCH7_PREP_TEST_KIT_ROOT', DEFAULT_KIT)).resolve()


def authenticate_public_cache():
    raw = (KIT / 'recovery-kit-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != KIT_SHA:
        raise ValueError('TEST_R7_KIT_MANIFEST_PIN')
    manifest = json.loads(raw.decode('utf-8'))
    expected = {'kit_source_commit': KIT_SOURCE, 'kit_source_tree': KIT_TREE,
                'runtime_source_commit': RUNTIME_SOURCE, 'runtime_source_tree': RUNTIME_TREE,
                'runtime_manifest_sha256': RUNTIME_SHA}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('TEST_R7_SOURCE_PINS')
    for name, pin in manifest['files'].items():
        if (name.startswith('/') or '\\' in name or '\0' in name or
                any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError('TEST_R7_FINITE_SOURCE_PATH')
        if hashlib.sha256((KIT / name).read_bytes()).hexdigest() != pin:
            raise ValueError('TEST_R7_SOURCE_BYTES_PIN')
    runtime = KIT / 'xuanjun-p2-package/deploy/integration-manifest.json'
    if hashlib.sha256(runtime.read_bytes()).hexdigest() != RUNTIME_SHA:
        raise ValueError('TEST_R7_RUNTIME_MANIFEST_PIN')
    return manifest


KIT_MANIFEST = authenticate_public_cache()
sys.path[:0] = [str(HERE), str(KIT / 'helpers'), str(KIT / 'xuanjun-p2-package/stage1')] + [
    str(path) for path in sorted((KIT / 'tests').iterdir()) if path.is_dir()]

import epoch7_prepare_data as data
import epoch7_host_factory as factory
import epoch7_acceptance_rows as acceptance
import epoch7_additive_identity as owner
import epoch7_additive_server as server
import unit_metadata
from test_epoch7_full_factory_fixture import make_seed, native_pins, meta, directory


class R7DataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = make_seed()

    def test_authenticated_r7_module_and_runtime_interfaces(self):
        self.assertEqual(factory.SOURCE, RUNTIME_SOURCE)
        self.assertEqual(factory.SOURCE_TREE, RUNTIME_TREE)
        self.assertEqual(factory.MANIFEST, RUNTIME_SHA)
        self.assertEqual(data.sha(self.seed['source_manifest_raw']), RUNTIME_SHA)
        self.assertEqual(len(self.seed['source_payloads']), 107)
        self.assertEqual(len(KIT_MANIFEST['files']), 252)
        for module in (factory, acceptance, owner, server, unit_metadata):
            relative = KIT_MANIFEST['modules'][module.__name__]
            self.assertEqual(pathlib.Path(module.__file__).resolve(), KIT / relative)
            self.assertEqual(data.sha((KIT / relative).read_bytes()), KIT_MANIFEST['files'][relative])
        self.assertEqual(pathlib.Path(data.__file__).resolve(), HERE / 'epoch7_prepare_data.py')
        contract = factory.host_input_contract()
        self.assertEqual(contract['source_commit'], RUNTIME_SOURCE)
        self.assertEqual(contract['runtime_manifest_sha256'], RUNTIME_SHA)
        self.assertEqual(len(contract['private_fields']), 11)
        self.assertEqual(set(contract['private_utf8_byte_fields']), set(data.RAW_PATHS))
        self.assertIs(contract['install_admission'], False)

    def test_r7_observation_validates_actual_acceptance_and_probe_without_io(self):
        observation = copy.deepcopy(self.seed['observation'])
        before = copy.deepcopy(observation)
        with native_pins(self.seed), \
             mock.patch('os.open', side_effect=AssertionError('NO_HOST_READS')), \
             mock.patch('pathlib.Path.read_bytes', side_effect=AssertionError('NO_FILE_READS')):
            self.assertIs(data.validate_observation(observation, factory), observation)
            facts = acceptance.acceptance_facts_from_observation(observation)
            factory.validated_finite_probe(observation)
        self.assertEqual(observation, before)
        self.assertEqual(set(facts['unit_dropins']), {row[0] for row in acceptance.ROLES.values()})

    def test_exact_eleven_r7_units_before_six_role_projection(self):
        observation = self.seed['observation']
        units = observation['unit_metadata']['sections']['dropins']['evidence']['units']
        self.assertEqual(len(unit_metadata.UNITS), 8)
        self.assertEqual(len(unit_metadata.SOCKET_UNITS), 3)
        self.assertEqual(set(units), set(unit_metadata.DROPIN_UNITS))
        self.assertEqual(len(units), 11)

    def test_missing_or_extra_socket_rejected_by_actual_data_validation(self):
        for unit in unit_metadata.SOCKET_UNITS + ('unexpected.socket',):
            value = copy.deepcopy(self.seed['observation'])
            units = value['unit_metadata']['sections']['dropins']['evidence']['units']
            if unit == 'unexpected.socket':
                units[unit] = {}
            else:
                del units[unit]
            value['unit_metadata_sha256'] = factory.d.digest(value['unit_metadata'])
            with self.subTest(unit=unit), native_pins(self.seed), \
                 self.assertRaisesRegex(ValueError, 'COMPLETE_ELEVEN_UNIT_INVENTORY'):
                data.validate_observation(value, factory)

    def test_unknown_socket_root_rejected_before_projection(self):
        value = copy.deepcopy(self.seed['observation'])
        units = value['unit_metadata']['sections']['dropins']['evidence']['units']
        unit = 'xuanjun-ledger.socket'
        units[unit]['/etc/systemd/system/' + unit + '.d']['state'] = 'UNKNOWN'
        value['unit_metadata_sha256'] = factory.d.digest(value['unit_metadata'])
        with native_pins(self.seed), self.assertRaisesRegex(ValueError, 'MEASURED_DROPIN_ROOT'):
            data.validate_observation(value, factory)

    def test_incomplete_or_finite_probe_digest_drift_rejected(self):
        for kind in ('report', 'unit', 'retained', 'probe', 'probe_digest'):
            value = copy.deepcopy(self.seed['observation'])
            if kind == 'report':
                value['kind'] = 'EPOCH7_OBSERVATION_ONLY_HOLD'
            elif kind == 'unit':
                value['unit_metadata']['state'] = 'INCOMPLETE'
                value['unit_metadata_sha256'] = factory.d.digest(value['unit_metadata'])
            elif kind == 'retained':
                value['evidence']['retained']['policy_sha256'] = '1' * 64
            elif kind == 'probe':
                del value['finite_probe']
            else:
                value['finite_probe']['policy_sha256'] = '1' * 64
            with self.subTest(kind=kind), native_pins(self.seed), self.assertRaises(ValueError):
                data.validate_observation(value, factory)

    def test_seed_wire_matches_exact_r7_loader_contract_and_utf8_bytes(self):
        seed = copy.deepcopy(self.seed)
        before = copy.deepcopy(seed)
        raw = data.seed_wire(seed)
        value = data.parse(raw, 64 * 1024 * 1024)
        self.assertEqual(seed, before)
        self.assertEqual(set(value), {'schema', 'seed'})
        self.assertEqual(value['schema'], 1)
        private = value['seed']
        self.assertEqual(set(private), set(factory.host_input_contract()['private_fields']))
        self.assertEqual(len(private), 11)
        self.assertEqual(raw, data.canonical(value) + b'\n')
        for key in data.RAW_PATHS:
            self.assertEqual(private[key].encode('utf-8'), seed[key])
        for key in ('rendered_targets', 'old_rendered_targets'):
            for path, source in seed['compiled'][key].items():
                self.assertEqual(private['compiled'][key][path].encode('utf-8'), source)
        self.assertEqual(private['compiled']['tls_config_bytes'].encode('utf-8'), seed['compiled']['tls_config_bytes'])
        for path, source in seed['identity_payloads'].items():
            self.assertEqual(private['identity_payloads'][path].encode('utf-8'), source)

    def test_seed_wire_missing_extra_nonboolean_or_invalid_utf8_rejects(self):
        for mutation in ('missing', 'extra', 'timer_int', 'timer_none', 'utf8', 'raw_type'):
            seed = copy.deepcopy(self.seed)
            if mutation == 'missing':
                del seed['compiled']
            elif mutation == 'extra':
                seed['authority'] = True
            elif mutation == 'timer_int':
                seed['activate_retained_renewal_timer'] = 1
            elif mutation == 'timer_none':
                seed['activate_retained_renewal_timer'] = None
            elif mutation == 'utf8':
                seed['native_before'] = b'\xff'
            else:
                seed['native_before'] = '{}'
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, UnicodeError)):
                data.seed_wire(seed)

    def test_owner_policy_uses_r7_manifest_and_real_rendered_callback_unit(self):
        observation = copy.deepcopy(self.seed['observation'])
        retained = observation['evidence']['retained']
        retained['additive_paths_absent'] = sorted((owner.PATH, server.PATH))
        retained['prerequisites']['directories'][owner.PARENT] = directory()
        with mock.patch('os.open', side_effect=AssertionError('NO_HOST_READS')):
            raw, addition = data.owner_policy(observation, self.seed['compiled'], self.seed['source_manifest_raw'])
            owner.validate_compiled(addition, RUNTIME_SHA)
        policy = data.parse(raw)
        self.assertEqual(policy['release_sha256'], RUNTIME_SHA)
        self.assertEqual(policy['script'], '/opt/xuanjun-control-releases/integration-' + RUNTIME_SHA[:16] + '/' + owner.SCRIPT_REL)
        self.assertEqual(policy['script_sha256'], data.sha(self.seed['source_payloads'][owner.SCRIPT_REL]))
        self.assertEqual(policy['unit_sha256'], data.sha(self.seed['compiled']['rendered_targets'][owner.UNIT]))
        self.assertEqual(addition['path'], owner.PATH)

    def test_additive_absence_requires_measured_parent_authority(self):
        value = {'evidence': {'retained': {'additive_paths_absent': [owner.PATH, server.PATH],
                 'prerequisites': {'directories': {owner.PARENT: directory()}}}}}
        self.assertEqual(data.additive_absence(value, owner.PATH)['kind'], 'ABSENT')
        self.assertEqual(data.additive_absence(value, server.PATH)['path'], server.PATH)
        for field, changed in (('uid', 1), ('gid', 1), ('mode', 0o777),
                               ('default_acl', 'group:fixture:rwx\n'), ('access_acl', '')):
            invalid = copy.deepcopy(value)
            invalid['evidence']['retained']['prerequisites']['directories'][owner.PARENT][field] = changed
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'ADDITIVE_PARENT_AUTHORITY'):
                data.additive_absence(invalid, owner.PATH)
        with self.assertRaisesRegex(ValueError, 'ADDITIVE_PATH'):
            data.additive_absence(value, '/unexpected')

    def test_retained_six_exact_raws_and_metadata_preserve_whitespace(self):
        files, measured = {}, {}
        for key, path in data.RAW_PATHS.items():
            raw = ('  ' + key + '\n\n').encode('utf-8')
            row = meta(raw)
            files[path] = row
            measured[key] = {'raw': raw, 'metadata': copy.deepcopy(row)}
        observation = {'evidence': {'retained': {'files': files}}}
        self.assertEqual(data.retained_buffers(observation, measured),
                         {key: row['raw'] for key, row in measured.items()})
        for field in data.STAT_FIELDS:
            invalid = copy.deepcopy(measured)
            invalid['native_before']['metadata'][field] += 1
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'RETAINED_BUFFER_CHANGED'):
                data.retained_buffers(observation, invalid)
        for mutation in ('extra', 'missing', 'raw', 'kind', 'bool_metadata'):
            invalid = copy.deepcopy(measured)
            if mutation == 'extra':
                invalid['extra'] = {}
            elif mutation == 'missing':
                del invalid['native_before']
            elif mutation == 'raw':
                invalid['native_before']['raw'] += b' '
            elif mutation == 'kind':
                invalid['native_before']['metadata']['kind'] = 'SYMLINK'
            else:
                invalid['native_before']['metadata']['uid'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                data.retained_buffers(observation, invalid)

    def test_strict_json_and_cached_path_remain_fail_closed(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'', b'[]' * 200):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                data.parse(raw, 64)
        path = data.CachedPath('/fixed', {'/fixed/one': b'value'})
        self.assertEqual((path / 'one').read_bytes(), b'value')
        self.assertIs(path.resolve(), path)
        for child in ('../other', '/other', 'a//b', 'a\\b', 'a\0b'):
            with self.subTest(child=child), self.assertRaises(ValueError):
                path / child
        with self.assertRaisesRegex(ValueError, 'UNDECLARED_HISTORICAL_READ'):
            (path / 'two').read_bytes()

    def test_historical_exact102_package_validation_is_not_weakened_for_r7(self):
        payloads = {'source-' + str(index): b'public-synthetic' for index in range(102)}
        raw = data.canonical({'files': {key: data.sha(value) for key, value in payloads.items()}})
        result = data.package(raw, payloads, data.sha(raw))
        self.assertEqual(result[data.MANIFEST_PATH], raw)
        for mutation in ('manifest_pin', 'payload_pin', 'missing', 'extra'):
            changed = dict(payloads)
            expected = data.sha(raw)
            if mutation == 'manifest_pin':
                expected = '0' * 64
            elif mutation == 'payload_pin':
                changed['source-0'] = b'changed'
            elif mutation == 'missing':
                del changed['source-0']
            else:
                changed['extra'] = b'extra'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                data.package(raw, changed, expected)

    def test_historical_plan_pin_rejects_before_supplied_source_execution(self):
        with mock.patch('builtins.compile', side_effect=AssertionError('NO_EXECUTION')):
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_PLAN_PIN'):
                data.reproduce_v4(b'{}', b'', {}, b'', {}, b'', {})

    def test_renderer_pin_rejects_before_supplied_source_execution(self):
        old = {'runtime': {'publisher': {}, 'provisioning': [
            {'target': factory.bindings.DISPATCHER}]}}
        with mock.patch('builtins.compile', side_effect=AssertionError('NO_EXECUTION')):
            with self.assertRaisesRegex(ValueError, 'RENDERER_PIN'):
                data.compile_bindings(data.canonical(old), b'{}',
                    {factory.bindings.RENDERER_PATH: b'not-authenticated'}, b'{}', {}, {}, factory)


if __name__ == '__main__':
    unittest.main(verbosity=2)
