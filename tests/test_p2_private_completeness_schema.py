"""New local tests only: real pure factories, wholly synthetic private objects."""
import copy
import gzip
import hashlib
import io
import importlib.util
import json
import pathlib
import sys
import subprocess
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evidence_schema as schema

_FIXTURE = None

def prepared_preimages():
    """No old suite execution; reuse only genuine public fixture definitions."""
    global _FIXTURE
    if _FIXTURE is None:
        path = HERE.parent / 'c-capability-lifecycle-candidate/tests/test_successor_approval_factory_entry.py'
        spec = importlib.util.spec_from_file_location('completeness_synthetic_factory', path)
        fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
        original, seed, inputs, plan = fixture.prepared_fixture()
        with fixture.native_pins(seed):
            proposal = fixture.factory._proposal(inputs)
        timer = fixture.factory.compile_timer_contract(inputs['timer_raw_baseline'])
        body = fixture.approval.expected_complete_from_inputs('c' * 64, proposal[1], proposal[2])
        preimages = schema.build_preimages(fixture.factory, inputs, proposal, timer)
        _FIXTURE = (preimages, plan, body, fixture, inputs, proposal, timer)
    preimages, plan, body, fixture, inputs, proposal, timer = _FIXTURE
    return copy.deepcopy(preimages), copy.deepcopy(plan), copy.deepcopy(body), fixture, copy.deepcopy(inputs), copy.deepcopy(proposal), copy.deepcopy(timer)


class PreimageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preimages, cls.plan, cls.body, cls.fixture, cls.inputs, cls.proposal, cls.timer = prepared_preimages()

    def held(self, mutate):
        value = copy.deepcopy(self.preimages); mutate(value)
        with self.assertRaises(schema.StaticHold) as caught:
            schema.verify_preimages(value, self.plan, self.body)
        self.assertRegex(str(caught.exception), r'^PREIMAGE_[A-Z_]+_HOLD$')
        self.assertNotIn('SECRETSENTINEL', str(caught.exception))

    def test_real_factory_complete_lossless_roundtrip_and_size(self):
        checks = schema.verify_preimages(self.preimages, self.plan, self.body)
        views, info = schema._resources(self.preimages['resources'])
        self.assertEqual(views, self.inputs['resource_views'])
        self.assertEqual(self.preimages['resources']['directories'], self.inputs['resource_directories'])
        self.assertEqual(info['views_sha256'], self.fixture.factory.resource_views_digest(self.inputs['resource_views']))
        self.assertEqual(info['directories_sha256'], self.fixture.factory.resource_directories_digest(self.inputs['resource_directories']))
        self.assertEqual(checks['retained_target_count'], 24)
        self.assertEqual(checks['additive_target_count'], 2)
        self.assertEqual(checks['section_count'], 255)
        raw = schema.canonical(self.preimages, schema.MAX_BYTES)
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as stream: stream.write(raw)
        self.assertLess(len(compressed.getvalue()), 48000)
        self.assertFalse(checks['hidden_input_root_independently_recomputed'])

    def test_unknown_nested_keys_fail_before_output(self):
        mutations = [lambda p: p.update(secret='SECRETSENTINEL'),
            lambda p: p['retained_delta']['changes'][0]['before'].update(token='SECRETSENTINEL'),
            lambda p: p['additive_targets'][0]['provenance'].update(token='SECRETSENTINEL'),
            lambda p: p['access_rows'][0]['proposal'].update(token='SECRETSENTINEL'),
            lambda p: p['acceptance_contract']['access'][0]['identity'].update(argv=['SECRETSENTINEL']),
            lambda p: p['timer_contract']['baseline'].update(env={'TOKEN': 'SECRETSENTINEL'}),
            lambda p: p['resources']['records'][0].update(value={'password': 'SECRETSENTINEL'}),
            lambda p: next(r for r in p['resources']['records'] if r['kind'] == 'NSS_BINDINGS')['accounts']['root'].update(password='SECRETSENTINEL'),
            lambda p: next(r for r in p['resources']['records'] if r['kind'] == 'EPOCH_CHAIN')['descriptor'].update(config='SECRETSENTINEL')]
        for mutation in mutations:
            with self.subTest(mutation=mutation): self.held(mutation)

    def test_unknown_values_paths_acl_and_timer_rejected(self):
        mutations = [lambda p: p['retained_delta'].update(kind='SECRETSENTINEL'),
            lambda p: p['resources']['records'][0].update(path='/tmp/SECRETSENTINEL'),
            lambda p: p['access_rows'][0]['before_binding'].update(access_acl='user:SECRETSENTINEL:rwx\n'),
            lambda p: p['timer_saved_baseline'].update({schema.TIMER: 'TOKEN=SECRETSENTINEL\n'}),
            lambda p: p['acceptance_contract']['access'][0]['identity'].update(user='SECRETSENTINEL'),
            lambda p: p['resources']['records'][0].update(mode=0o7777),
            lambda p: p['resources']['records'][0].update(uid=True)]
        for mutation in mutations:
            with self.subTest(mutation=mutation): self.held(mutation)

    def test_ordered_index_and_hash_tampering_rejected(self):
        def change_index(p):
            rows = p['resources']['ordered_index'][0]['historical']; rows[0], rows[1] = rows[1], rows[0]
        def change_hash(p):
            row = next(r for r in p['resources']['records'] if r['kind'] == 'FILE'); row['sha256'] = 'f' * 64
        def change_directory(p): p['resources']['directories']['/'][0]['mode'] ^= 0o100
        def duplicate_record(p): p['resources']['records'].append(copy.deepcopy(p['resources']['records'][0]))
        for mutation in [change_index, change_hash, change_directory, duplicate_record,
                lambda p: p['resources']['ordered_index'][0]['historical'].__setitem__(0, True),
                lambda p: p['resources']['ordered_index'].pop(),
                lambda p: p['retained_delta']['changes'].pop(),
                lambda p: p['additive_targets'].pop(),
                lambda p: p['timer_saved_baseline'].__setitem__(schema.TIMER, p['timer_saved_baseline'][schema.TIMER].replace('NextElapseUSecMonotonic=0', 'NextElapseUSecMonotonic=1s'))]:
            with self.subTest(mutation=mutation): self.held(mutation)

    def test_onsite_preimages_preserve_original_projection_fields_and_digest_only(self):
        for row in self.preimages['resources']['records']:
            if row['kind'].startswith('JSON_'):
                self.assertIn('fields', row); self.assertIn('sha256', row)
                self.assertNotIn('value', row)
        forbidden = {'observation', 'compiled', 'identity_payloads', 'acceptance_facts', 'service_facts', 'argv', 'env', 'input_children', 'sandbox_candidate_raw'}
        def walk(node):
            if isinstance(node, dict):
                self.assertFalse(set(node) & forbidden)
                for value in node.values(): walk(value)
            elif isinstance(node, list):
                for value in node: walk(value)
        walk(self.preimages)

    def test_build_never_mutates_or_trusts_unknown_nested_source(self):
        inputs = copy.deepcopy(self.inputs); before = self.fixture.factory.input_digest(inputs)
        schema.build_preimages(self.fixture.factory, inputs, self.proposal, self.timer)
        self.assertEqual(before, self.fixture.factory.input_digest(inputs))
        inputs['resource_views'][0]['historical'][0]['secret'] = 'SECRETSENTINEL'
        with self.assertRaises(schema.StaticHold):
            schema.build_preimages(self.fixture.factory, inputs, self.proposal, self.timer)

    def test_closed_nested_python_node_nss_and_activation_schemas(self):
        def metadata(kind, ino, mode, uid=0, gid=0, nlink=1, size=10):
            return dict(kind=kind, uid=uid, gid=gid, mode=mode, dev=8, ino=ino,
                nlink=nlink, size=size, mtime_ns=11, ctime_ns=12)
        def attrs(row):
            return dict(row, access_acl=False, default_acl=False, capability=False)
        py = {'schema': 1, 'kind': 'EXACT_RETAINED_PYTHON_TWO_NAME_V1',
            'retained_sha256': 'ba19929d7038d0c2304f528213fa11e5f10c1ce65f0a891afa459bd167c7e5f6',
            'owner_report_sha256': '88cc60f8c3bc465c4025eeda297f98a0b00d5ca5e0a80d3266e52e00f997e2f3',
            'package_claim_sha256': '36aa67e302e6c0b3a9494128aa184a46ba06edbfbf3828209682caa7c7559b8d',
            'package_signature_authenticity': 'NOT_VERIFIED', 'reread': 'EXACT_PRE_POST'}
        file = attrs(metadata('FILE', 100, 0o755, nlink=2, size=15352))
        file.update(sha256=py['retained_sha256'], elf_header=True)
        py['sample'] = {'files': {p: copy.deepcopy(file) for p in schema.PYTHON_PATHS},
            'ancestors': {p: attrs(metadata('DIRECTORY', 200 + i, 0o555 if p == '/' else 0o755))
                for i, p in enumerate(('/', '/usr', '/usr/libexec'))}}
        schema._python_identity(py)
        pyrow = dict(path=schema.PYTHON_PATHS[0], kind='FILE', uid=0, gid=0, mode=0o755,
            sha256=py['retained_sha256'], access_acl='user::rwx\ngroup::r-x\nother::r-x\n', python_identity=py)
        schema._resource(pyrow)
        node = {'schema': 1, 'kind': 'FIXED_NODE_DIRECTORY_ALIAS',
            'reference_path': '/home/xuanjun_dev/.openclaw/tools/node/bin/node', 'reread': 'EXACT_PRE_POST',
            'link': {'path': '/home/xuanjun_dev/.openclaw/tools/node', 'target': 'node-v24.21.0',
                'metadata': metadata('SYMLINK', 300, 0o777, size=len('node-v24.21.0'))},
            'final': {'path': schema.NODE_ROOT + '/bin/node', 'sha256': 'a' * 64,
                'metadata': dict(attrs(metadata('FILE', 301, 0o755, uid=1002, gid=1002)), sha256='a' * 64, elf_header=True)},
            'ancestors': {p: attrs(metadata('DIRECTORY', 400 + i, 0o755)) for i, p in enumerate(schema.NODE_ANCESTORS)}}
        schema._node_reference(node)
        noderow = dict(path=schema.NODE_ROOT + '/bin/node', kind='FILE', uid=1002, gid=1002, mode=0o755,
            sha256='a' * 64, access_acl='user::rwx\ngroup::r-x\nother::r-x\n', node_reference=node)
        schema._resource(noderow)
        nss = copy.deepcopy(next(r for r in self.preimages['resources']['records'] if r['kind'] == 'NSS_BINDINGS'))
        nss['prerequisites'] = {'group:xuanjun-control-db': {'gid': 1006, 'members': ['xuanjun-callback', 'xuanjun-dispatcher']},
            'user:xuanjun-dispatcher': {'uid': 1003, 'gid': 1003, 'groups': [1003, 1006]}}
        schema._nss(nss)
        cases = [(pyrow, lambda v: v['python_identity']['sample']['files'][schema.PYTHON_PATHS[0]].update(secret='SECRETSENTINEL')),
            (pyrow, lambda v: v['python_identity']['sample']['ancestors']['/usr'].update(env={'TOKEN': 'SECRETSENTINEL'})),
            (noderow, lambda v: v['node_reference']['final']['metadata'].update(argv=['SECRETSENTINEL'])),
            (noderow, lambda v: v['node_reference']['link'].update(target='SECRETSENTINEL')),
            (noderow, lambda v: v['node_reference']['ancestors']['/'].update(secret='SECRETSENTINEL')),
            (nss, lambda v: v['prerequisites']['group:xuanjun-control-db']['members'].append('SECRETSENTINEL')),
            (nss, lambda v: v['nss_by_primary']['root'].update(secret=[1]))]
        for original, mutate in cases:
            value = copy.deepcopy(original); mutate(value)
            with self.subTest(value=original['kind']), self.assertRaises(schema.StaticHold): schema._resource(value)

    def test_cold_import_has_no_process_or_temporary_file_side_effects(self):
        script = """import importlib.util, subprocess, tempfile, os, sys

def denied(*args, **kwargs):
    raise AssertionError('SIDE_EFFECT_FORBIDDEN')
subprocess.Popen = denied
os.system = denied
os.popen = denied
for name in ('mkstemp', 'mkdtemp', 'NamedTemporaryFile', 'TemporaryFile', 'TemporaryDirectory'):
    setattr(tempfile, name, denied)
spec = importlib.util.spec_from_file_location('cold_schema', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert 'uuid' not in sys.modules
assert not any(name.startswith('epoch7_') for name in sys.modules)
print('COLD_IMPORT_OK')
"""
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', script, str(HERE / 'evidence_schema.py')],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
        self.assertEqual(result.stdout, b'COLD_IMPORT_OK\n')

    def test_ordered_additions_follow_original_factory_sort(self):
        inputs = copy.deepcopy(self.inputs)
        inputs['additive_deltas'].reverse()
        value = schema.build_preimages(self.fixture.factory, inputs, self.proposal, self.timer)
        self.assertEqual(value, self.preimages)
        self.assertTrue(schema.verify_preimages(value, self.plan, self.body)['additive_targets'])

    def test_known_public_cache_paths_only_and_complete_checkpoints(self):
        schema._path('/opt/xuanjun-control-releases/integration-153653ebc48d6b20/stage1/__pycache__/activation_control.cpython-36.pyc')
        for path in ('/opt/xuanjun-control-releases/integration-153653ebc48d6b20/stage1/__pycache__/SECRETSENTINEL.cpython-36.pyc',
                '/opt/xuanjun-control-releases/integration-153653ebc48d6b20/stage1/__pycache__/activation_control.cpython-312.pyc'):
            with self.assertRaises(schema.StaticHold): schema._path(path)
        for mutate in (lambda p: p.pop('live_controls'),
                lambda p: p['live_controls'].pop('checkpoints'),
                lambda p: p['live_controls']['checkpoints'][0].pop('resources'),
                lambda p: p['live_controls']['checkpoints'][0]['resources'].pop(schema.SECTIONS[0])):
            plan = copy.deepcopy(self.plan); mutate(plan)
            with self.assertRaises(schema.StaticHold): schema.verify_preimages(self.preimages, plan, self.body)

    def test_privacy_whole_segments_visible_roots_and_no_raw_sensitive_hashes(self):
        schema.verify_preimages(self.preimages, self.plan, self.body)
        context = {'session_nonce': '1' * 32, 'new_seed_sha256': '2' * 64, 'old_seed_sha256': '3' * 64}
        projected = schema.privacy_project(self.preimages, b'k' * 32, context)
        checks = schema.verify_projected_preimages(projected, self.plan, self.body)
        self.assertEqual(projected['visible']['additive_targets'], self.preimages['additive_targets'])
        self.assertEqual(projected['visible']['resource_directories'], self.inputs['resource_directories'])
        self.assertTrue(checks['additive_targets']); self.assertTrue(checks['timer_contract'])
        self.assertTrue(checks['resource_directories'])
        for name in ('retained_delta', 'access_rows', 'acceptance_contract', 'resource_views'):
            self.assertFalse(checks[name])
        self.assertTrue(checks['coverage_inventory_only'])
        self.assertFalse(checks['hidden_commitments_independently_verified'])
        self.assertEqual(checks['onsite_only_roots'], list(schema.ONSITE_ONLY_ROOTS))
        raw = schema.canonical(projected, schema.MAX_BYTES)
        forbidden = [self.preimages['retained_delta']['sandbox_change']['expected_profile_sha256'],
            self.preimages['access_rows'][1]['before_binding']['sha256'],
            self.preimages['acceptance_contract']['tls']['config_sha256'],
            self.preimages['retained_delta']['preserve']['database']['sha256'],
            self.preimages['retained_delta']['preserve']['database']['logical_manifest_sha256']]
        for row in self.preimages['resources']['records']:
            if row['kind'] == 'SANDBOX_STABLE' or row['path'].startswith('/etc/xuanjun-owner-callback/'):
                if 'sha256' in row: forbidden.append(row['sha256'])
        for pin in forbidden: self.assertNotIn(pin.encode('ascii'), raw)
        self.assertNotIn(b'ordered_index', raw); self.assertNotIn(b'"records"', raw)
        self.assertEqual(len(projected['coverage']['targets']), 24)
        for index, row in enumerate(projected['coverage']['targets']):
            self.assertEqual(row['index'], index)
            self.assertEqual(row['content_sha256'], schema.TARGET_CONTENT)
            self.assertNotIn('sha256', row['before']); self.assertNotIn('sha256', row['after'])

    def test_privacy_domain_binding_and_hidden_digest_injection(self):
        context = {'session_nonce': '1' * 32, 'new_seed_sha256': '2' * 64, 'old_seed_sha256': '3' * 64}
        a = schema.privacy_project(self.preimages, b'k' * 32, context)
        b = schema.privacy_project(self.preimages, b'l' * 32, context)
        c = schema.privacy_project(self.preimages, b'k' * 32, dict(context, session_nonce='4' * 32))
        for name in schema.PRIVATE_SEGMENTS:
            self.assertNotEqual(a['withheld'][name]['commitment'], b['withheld'][name]['commitment'])
            self.assertNotEqual(a['withheld'][name]['commitment'], c['withheld'][name]['commitment'])
        secret_digest = hashlib.sha256(b'SYNTHETIC_LOW_ENTROPY_PRIVATE_SENTINEL').hexdigest()
        value = copy.deepcopy(self.preimages)
        value['retained_delta']['sandbox_change']['expected_profile_sha256'] = secret_digest
        value['access_rows'][1]['before_binding']['sha256'] = secret_digest
        value['acceptance_contract']['tls']['config_sha256'] = secret_digest
        next(row for row in value['resources']['records'] if row['path'].endswith('/owner-dashboard-token'))['sha256'] = secret_digest
        changed = schema.privacy_project(value, b'k' * 32, context)
        self.assertNotIn(secret_digest.encode(), schema.canonical(changed, schema.MAX_BYTES))
        for name in schema.PRIVATE_SEGMENTS:
            self.assertNotEqual(a['withheld'][name]['commitment'], changed['withheld'][name]['commitment'])
        with self.assertRaises(schema.StaticHold): schema.privacy_project(self.preimages, b'bad', context)

    def test_projected_mutations_and_missing_safe_preimages_hold(self):
        context = {'session_nonce': '1' * 32, 'new_seed_sha256': '2' * 64, 'old_seed_sha256': '3' * 64}
        projected = schema.privacy_project(self.preimages, b'k' * 32, context)
        mutations = [lambda p: p['visible'].update(access_rows=self.preimages['access_rows']),
            lambda p: p['withheld']['retained_delta'].update(original_preimage=self.preimages['retained_delta']),
            lambda p: p['withheld']['access_rows'].update(commitment='SECRETSENTINEL'),
            lambda p: p['onsite_only_roots'].remove('security_delta_sha256'),
            lambda p: p['coverage']['targets'][0]['before'].update(sha256='f' * 64),
            lambda p: p['coverage']['targets'][0].update(path='/tmp/SECRETSENTINEL'),
            lambda p: p['coverage']['resource_section_counts'][0].pop(schema.SECTIONS[0]),
            lambda p: p['visible']['additive_targets'][0]['after'].update(sha256='f' * 64),
            lambda p: p['visible']['timer_contract'].update(tail_seconds=61),
            lambda p: p['visible']['resource_directories']['/'][0].update(mode=0o700)]
        for mutate in mutations:
            value = copy.deepcopy(projected); mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(schema.StaticHold):
                schema.verify_projected_preimages(value, self.plan, self.body)
        # Valid-shaped HMAC replacement cannot be independently detected: this
        # limitation must remain explicit rather than yielding a false promise.
        value = copy.deepcopy(projected); value['withheld']['retained_delta']['commitment'] = 'f' * 64
        checks = schema.verify_projected_preimages(value, self.plan, self.body)
        self.assertFalse(checks['hidden_commitments_independently_verified'])

    def test_full_stamp_variants_are_preserved_and_typed(self):
        value = copy.deepcopy(self.preimages)
        row = value['retained_delta']['changes'][14]['before']
        row.update(mode=0o777, nlink=1, size=9, mtime_ns=100, ctime_ns=100)
        schema._validate(value)
        row['mtime_ns'] = 'SECRETSENTINEL'
        with self.assertRaises(schema.StaticHold): schema._validate(value)

if __name__ == '__main__':
    unittest.main()
