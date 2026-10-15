"""Synthetic PUBLIC test data, real frozen pure validators, no host effects.

Fixture values are invented to exercise schema checks and carry no observation
or approval authority. No test invokes a collection, probe, host, or network API.
"""
import copy
import hashlib
import importlib
import os
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
REPAIR = HERE.parent
KIT = REPAIR / 'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'
PREP = REPAIR / 'r6-preparation-contract-fix-candidate'
sys.path[:0] = [str(HERE), str(PREP), str(KIT / 'helpers'), str(KIT / 'xuanjun-p2-package/stage1'),
    str(KIT / 'tests/probe')]

import export_schema as s
import epoch7_topology_projection as t
import test_epoch7_topology_projection as old
import test_node_sqlite_probe as node_fixture
import test_probe_driver as probe_fixture


def fixture(topology=None):
    """Expand public synthetic fixture to the exact full successful r6 shape.

    ``topology`` may be the loader's authenticated frozen module. Its tests must
    have corresponding frozen probe/helper/node modules on the import path.
    """
    module = t if topology is None else topology
    original_policy = old.policy_fixture
    original_node = node_fixture.fixture_node

    def public_node():
        row = original_node()
        row['path'] = s.NODE_PATH
        return row

    def public_policy(root):
        policy, helper, manifest, files = original_policy(root)
        policy['nonce'] = s.NONCE
        template = policy['sdk_bindings'][0]
        policy['sdk_bindings'] = [dict(template, path=path) for path in sorted(s.SDK_PATHS)]
        identity = module.probe.epoch7_python_identity
        stamp = dict(original_node()['metadata'], uid=0, gid=0, mode=0o755, nlink=2,
            size=identity.RETAINED_SIZE, ino=100, access_acl=False, default_acl=False, capability=False)
        sample = {'files': {path: dict(stamp, kind='FILE', sha256=identity.RETAINED_SHA256,
            elf_header=True) for path in identity.PYTHON_PATHS}, 'ancestors': {
                path: dict(stamp, kind='DIRECTORY', mode=0o555 if path == '/' else 0o755, ino=101+i)
                for i, path in enumerate(identity.ANCESTOR_PATHS)}}
        policy['python']['sha256'] = identity.RETAINED_SHA256
        policy['python']['python_identity'] = identity.build_pair_proof(sample, copy.deepcopy(sample), identity.package_claim())
        return policy, helper, manifest, files

    with mock.patch.object(old, 't', module), mock.patch.object(old, 'policy_fixture', public_policy), \
            mock.patch.object(node_fixture, 'fixture_node', public_node):
        value = old.fixture()
    attempt = value['observation']['finite_probe']
    policy = attempt['policy']
    paths, files, units = s.resources_for(policy, module.probe)
    result = attempt['result']
    result.update(schema=1, incomplete_case=None,
        intentionally_retained=[paths['root'], paths['receipt']],
        production_acceptance='NOT_VERIFIED', operator_acknowledgement_is_external_approval_proof=False)
    for number in (6, 8):
        result['cases'][number - 1]['reason'] = 'BrokenPipeError:[Errno 32] Broken pipe'
    receipt = value['receipt']
    resources = {row['path']: row for row in receipt['resources']}
    standard = dict(original_node()['metadata'], uid=0, gid=0, mode=0o644, nlink=1, size=0)
    empty = hashlib.sha256(b'').hexdigest()
    for path in files:
        if path not in resources:
            resources[path] = {'path': path, 'kind': 'FILE', 'identity': dict(standard), 'sha256': empty}
        resources[path]['identity']['mode'] = 0o600 if path.endswith('/connection-budget.json') else 0o644
    resources[paths['root']] = {'path': paths['root'], 'kind': 'DIRECTORY',
        'identity': dict(standard, mode=0o755, nlink=2, size=4096)}
    receipt['resources'] = [resources[path] for path in sorted(resources)]
    cleanup = [{'unit': unit, 'status': 'STOPPED_AND_EMPTY'} for unit in sorted(units)]
    cleanup += [{'path': path, 'status': 'REMOVED'} for path in sorted(files)]
    receipt['cleanup'] = cleanup
    result['cleanup'] = copy.deepcopy(cleanup)
    proof = result['node_sqlite']
    events = [{'event': 'CREATE_INTENT', 'detail': {'path': path, 'sha256': resources[path]['sha256']}}
        for path in sorted(files)]
    events += [{'event': 'UNITS_LOADED', 'detail': None}, {'event': 'NODE_SQLITE_INTENT', 'detail': {
        'diagnostic_sha256': proof['diagnostic_sha256'], 'node_sha256': proof['node']['sha256'],
        'probe_input_sha256': proof['probe_input_sha256']}}, {'event': 'NODE_SQLITE_OBSERVED', 'detail': copy.deepcopy(proof)}]
    for number, role, kind in module.probe.CASES:
        events += [{'event': 'CASE_INTENT', 'detail': {'case': number, 'role': role, 'kind': kind}},
            {'event': 'CLIENT_START_INTENT', 'detail': {'case': number, 'unit': paths['client_units'][role]}}]
        if number in (7, 8):
            events.append({'event': 'SOCKET_RECREATED' if number == 7 else 'SOCKET_RECREATED_DURING',
                'detail': {'before': dict(receipt['socket_identity'], ino=33), 'after': dict(receipt['socket_identity'])}})
        events.append({'event': 'CASE_OBSERVED', 'detail': copy.deepcopy(result['cases'][number - 1])})
    records = copy.deepcopy(result['server_observations'])
    output = b''.join(s.canonical(row) + b'\n' for row in records)
    events.append({'event': 'OUTPUT_CAPTURED', 'detail': {'path': paths['root'] + '/output-ledger.jsonl',
        'sha256': hashlib.sha256(output).hexdigest(), 'bytes': len(output), 'observations': records}})
    receipt['events'] = events
    bind(value)
    return value


def bind(value):
    receipt = value['receipt']
    result = value['observation']['finite_probe']['result']
    raw = s.canonical(receipt) + b'\n'
    result['created_receipt']['sha256'] = hashlib.sha256(raw).hexdigest()
    result['created_receipt']['metadata']['size'] = len(raw)
    return raw, copy.deepcopy(result['created_receipt']['metadata'])


def validate(value, module=t, full=False):
    raw, metadata = bind(value)
    if full:
        module.project_topology(value['observation'], raw, metadata, value['kit_sha'],
            value['sources'], value['dropins'], 'd' * 64)
    return s.validate_export(value['observation']['finite_probe'], value['receipt'], metadata, module)


class ExportSchemaTests(unittest.TestCase):
    def test_complete_public_fixture_passes_real_projection_and_schema(self):
        value = fixture()
        before = copy.deepcopy(value)
        self.assertIsNone(validate(value, full=True))
        self.assertEqual(value, before)
        self.assertEqual(len(value['receipt']['resources']), 35)

    def test_no_io_or_effect_adapter_called_by_validation(self):
        value = fixture()
        with mock.patch('builtins.open', side_effect=AssertionError('IO_FORBIDDEN')), \
             mock.patch.object(t.probe.HostOps, '__init__', side_effect=AssertionError('HOST_FORBIDDEN')), \
             mock.patch.object(t.approval, 'fetch', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            self.assertIsNone(validate(value, full=True))

    def test_legacy_missing_incomplete_fields_and_explicit_none(self):
        for include in (False, True):
            value = fixture()
            result = value['observation']['finite_probe']['result']
            if include:
                value['receipt']['incomplete_case'] = None
            else:
                result.pop('incomplete_case')
            self.assertIsNone(validate(value, full=True))

    def test_unknown_fields_at_every_export_container_are_rejected(self):
        value = fixture()
        paths = []
        def walk(obj, path):
            if type(obj) is dict:
                paths.append(path)
                for key, child in obj.items():
                    walk(child, path + (key,))
            elif type(obj) is list:
                for i, child in enumerate(obj):
                    walk(child, path + (i,))
        for root in ('attempt', 'receipt', 'metadata'):
            roots = {'attempt': value['observation']['finite_probe'], 'receipt': value['receipt'],
                'metadata': value['observation']['finite_probe']['result']['created_receipt']['metadata']}
            paths = []
            walk(roots[root], ())
            for path in paths:
                changed = fixture()
                target = {'attempt': changed['observation']['finite_probe'], 'receipt': changed['receipt'],
                    'metadata': changed['observation']['finite_probe']['result']['created_receipt']['metadata']}[root]
                for key in path:
                    target = target[key]
                target['unexpected_private_payload'] = 'private config material must never leave'
                with self.subTest(root=root, path=path), self.assertRaises((ValueError, TypeError)):
                    validate(changed)

    def test_private_strings_rejected_in_ignored_runtime_fields(self):
        for field, bad in (('ActiveState', 'secret-data'), ('SubState', 'private'),
            ('ExecStart', 'start_time=[]'), ('InvocationID', 'private')):
            value = fixture()
            unit = next(row['evidence'] for row in value['observation']['finite_probe']['result']['cases'][0]['readpaths']
                if row['path_class'] == 'manager-unit:service')
            if field == 'ExecStart':
                unit[field] = unit[field].replace(bad, 'start_time=[private-secret]')
            else:
                unit[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(value)

    def test_known_systemd_timestamp_suffix_is_retained(self):
        value = fixture()
        for case in value['observation']['finite_probe']['result']['cases']:
            unit = next(row['evidence'] for row in case['readpaths'] if row['path_class'] == 'manager-unit:service')
            unit['ExecStart'] = unit['ExecStart'].replace('start_time=[]', 'start_time=[Thu 2026-10-15 17:18:00 CST]')
        for event in value['receipt']['events']:
            if event['event'] == 'CASE_OBSERVED':
                event['detail'] = copy.deepcopy(value['observation']['finite_probe']['result']['cases'][event['detail']['case'] - 1])
        self.assertIsNone(validate(value, full=True))

    def test_bounded_systemd_status_pairs_are_retained(self):
        for status in ('0/0', '0/SUCCESS', '15/TERM', '9/KILL', '255/255'):
            value = fixture()
            for case in value['observation']['finite_probe']['result']['cases']:
                unit = next(row['evidence'] for row in case['readpaths'] if row['path_class'] == 'manager-unit:service')
                unit['ExecStart'] = unit['ExecStart'].replace('status=0 }', 'status=' + status + ' }')
            for event in value['receipt']['events']:
                if event['event'] == 'CASE_OBSERVED':
                    event['detail'] = copy.deepcopy(value['observation']['finite_probe']['result']['cases'][event['detail']['case'] - 1])
            with self.subTest(status=status): self.assertIsNone(validate(value, full=True))
        for status in ('0/private', '0/9999', '9999/0', '0/0/private', '0/0\nsecret'):
            value = fixture()
            unit = next(row['evidence'] for row in value['observation']['finite_probe']['result']['cases'][0]['readpaths']
                if row['path_class'] == 'manager-unit:service')
            unit['ExecStart'] = unit['ExecStart'].replace('status=0 }', 'status=' + status + ' }')
            with self.subTest(status=status), self.assertRaises(ValueError): validate(value)

    def test_race_reasons_are_exact_enumeration(self):
        for reason in ('ConnectionResetError', 'ValueError:PRIVATE_TOKEN', '/etc/private',
            'BrokenPipeError:[Errno 32] Broken pipe: /etc/private', 'a' * 2049):
            value = fixture()
            value['observation']['finite_probe']['result']['cases'][5]['reason'] = reason
            with self.subTest(reason=reason[:50]), self.assertRaises(ValueError):
                validate(value)

    def test_path_smuggling_rejected(self):
        for target in ('sdk', 'node', 'resource', 'cleanup', 'capture', 'replace', 'create', 'retained'):
            value = fixture()
            attempt = value['observation']['finite_probe']
            path = '/home/xuanjun_dev/.openclaw/tools/private-config.json'
            if target == 'sdk': attempt['policy']['sdk_bindings'][0]['path'] = path
            elif target == 'node': attempt['policy']['node_sqlite']['node']['path'] = path
            elif target == 'resource': value['receipt']['resources'][0]['path'] = path
            elif target == 'cleanup': value['receipt']['cleanup'][-1]['path'] = path
            elif target == 'capture': value['receipt']['events'][-1]['detail']['path'] = path
            elif target == 'create': value['receipt']['events'][0]['detail']['path'] = path
            elif target == 'replace': value['receipt']['events'].append({'event': 'REPLACE_INTENT',
                'detail': {'path': path, 'before_sha256': '1'*64, 'after_sha256': '2'*64}})
            else: attempt['result']['intentionally_retained'].append(path)
            with self.subTest(target=target), self.assertRaises(ValueError): validate(value)

    def test_types_nonfinite_overflow_bool_as_int(self):
        for bad in (True, False, 1.0, float('nan'), float('inf'), -1, 2**65, '1', [], {}):
            value = fixture()
            value['receipt']['connections_reserved'] = bad
            with self.subTest(kind=type(bad).__name__), self.assertRaises((ValueError, TypeError)):
                validate(value)
        value = fixture()
        value['observation']['finite_probe']['policy']['sdk_bindings'][0]['uid'] = True
        with self.assertRaises(ValueError): validate(value)

    def test_bounds_on_lists_strings_and_metadata(self):
        for change in ('events', 'cases', 'groups', 'metadata', 'dict', 'depth'):
            value = fixture()
            attempt = value['observation']['finite_probe']
            if change == 'events': value['receipt']['events'] = [None] * 513
            elif change == 'cases': attempt['result']['cases'] *= 64
            elif change == 'metadata': value['receipt']['resources'][0]['identity']['size'] = 2**65
            elif change == 'groups':
                row = next(x for x in attempt['result']['cases'][0]['readpaths'] if x['path_class'] == 'manager-process')
                row['evidence']['status']['Groups'] = '1 ' * 100
            elif change == 'dict': attempt['result'].update({str(i): None for i in range(65)})
            else:
                nested = None
                for unused in range(30): nested = [nested]
                attempt['result']['extra'] = nested
            with self.subTest(change=change), self.assertRaises(ValueError): validate(value)

    def test_unknown_events_nulls_cleanup_diagnostics_rejected(self):
        for change in ('unknown_event', 'null_detail', 'event_private', 'cleanup_reason',
            'result_failure', 'pending', 'last_command', 'count', 'diagnostic', 'duplicate'):
            value = fixture()
            result = value['observation']['finite_probe']['result']
            if change == 'unknown_event': value['receipt']['events'].append({'event': 'PRIVATE_NOTE', 'detail': 'secret'})
            elif change == 'null_detail': value['receipt']['events'][0]['detail'] = None
            elif change == 'event_private': next(e for e in value['receipt']['events'] if e['event'] == 'UNITS_LOADED')['detail'] = 'secret'
            elif change == 'cleanup_reason': value['receipt']['cleanup'][0]['reason'] = 'secret'
            elif change == 'result_failure': result['failure'] = 'private traceback'
            elif change == 'pending': result['incomplete_case'] = {}
            elif change == 'last_command': result['last_command_cleanup'] = ['CHILD_REAP_UNCONFIRMED']
            elif change == 'count': value['receipt']['accepted_connections'] = 7
            elif change == 'diagnostic': value['receipt']['events'][-1]['detail']['non_json_diagnostic'] = {'private': 'secret'}
            else: value['receipt']['resources'][0] = copy.deepcopy(value['receipt']['resources'][1])
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)): validate(value)

    def test_rejection_labels_never_include_private_input(self):
        value = fixture()
        value['receipt']['events'].append({'event': 'VERY_PRIVATE_VALUE_DO_NOT_PRINT', 'detail': None})
        with self.assertRaises(ValueError) as caught: validate(value)
        self.assertNotIn('VERY_PRIVATE', str(caught.exception))

    def test_subset_mechanism_binding_checks_are_independent(self):
        for change in ('manager', 'boot', 'source', 'node_script', 'candidate'):
            value = fixture()
            attempt = value['observation']['finite_probe']
            if change in ('manager', 'boot'):
                target = 'manager-process' if change == 'manager' else 'boot-id'
                item = next(row['evidence'] for row in attempt['result']['cases'][1]['readpaths'] if row['path_class'] == target)
                if change == 'manager': item['starttime'] += 1
                else: item['sha256'] = '0' * 64
            elif change in ('source', 'node_script'):
                leaf = '/probe_helpers.py' if change == 'source' else '/node-sqlite-probe.cjs'
                next(row for row in value['receipt']['resources'] if row['path'].endswith(leaf))['sha256'] = '0' * 64
            else:
                attempt['policy']['candidate_sources']['stage1/ledger_service.py'] = '0' * 64
            with self.subTest(change=change), self.assertRaises(ValueError): validate(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
