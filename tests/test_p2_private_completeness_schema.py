"""New local tests only: real pure factories, wholly synthetic private objects."""
import copy
import ast
import base64
import gzip
import hashlib
import io
import importlib.util
import inspect
import json
import pathlib
import sys
import subprocess
import tarfile
import unittest
from unittest import mock

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

class ExactPathScopeTests(unittest.TestCase):
    """Local-only regression: authenticated synthetic paths, no private Packet.

    The public kit is authenticated before its entry constants are read with
    ast.literal_eval; its source is never imported or executed by these helpers.
    Every additional transaction leaf and content hash below is synthetic.
    """

    FILE_ACL = 'user::rw-\ngroup::---\nother::---\n'
    DIRECTORY_ACL = 'user::rwx\ngroup::---\nother::---\n'
    PUBLIC_ALIASES = ('/usr/bin/python3.6', '/etc/alternatives/python3',
        '/usr/libexec/platform-python', '/usr/bin/runuser', '/usr/bin/nginx')
    CONTEXT = {'session_nonce': '1' * 32, 'new_seed_sha256': '2' * 64,
        'old_seed_sha256': '3' * 64}

    @classmethod
    def setUpClass(cls):
        cls.packet = cls.synthetic_packet()
        cls.scope = cls.authenticated_scope(cls.packet)
        cls.profiles, cls.public_constants = cls.public_openclaw_profiles()

    @classmethod
    def synthetic_packet(cls):
        paths = [schema.TRANSACTION] + [schema.TRANSACTION +
            '/synthetic-pathscope-directory-%02d' % index for index in range(8)]
        directories = {path: {'path': path, 'kind': 'DIRECTORY', 'uid': 0,
            'gid': 0, 'mode': 0o700, 'dev': 8, 'ino': 80000 + index,
            'nlink': 2, 'size': 4096, 'mtime_ns': 10000 + index,
            'ctime_ns': 20000 + index, 'access_acl': cls.DIRECTORY_ACL,
            'default_acl': ''} for index, path in enumerate(paths)}
        inventory = {paths[1 + index % 8] +
            '/SYNTHETIC_PATH_SCOPE_SECRET_%02d.private' % index:
            hashlib.sha256(('SYNTHETIC_PATH_SCOPE_CONTENT_%02d' % index).encode()).hexdigest()
            for index in range(47)}
        return {'measured_predecessor': {
            'measurement': {'schema': 1, 'record': {}, 'ancestors': {}, 'absent': {}},
            'transaction_inventory': inventory,
            'transaction_directories': directories,
            'transaction_parent_delta': {key: {'historical': 1, 'live': 2}
                for key in ('size', 'mtime_ns', 'ctime_ns')}}}

    @staticmethod
    def authenticated_scope(packet):
        # Patching both pins is confined to wholly synthetic test bytes. The
        # production authenticated Packet is never opened by this test class.
        raw = schema.canonical(packet, schema.MAX_BYTES) + b'\n'
        with mock.patch.object(schema, 'PACKET_SIZE', len(raw)), \
                mock.patch.object(schema, 'PACKET_SHA256', hashlib.sha256(raw).hexdigest()):
            return schema.path_scope_from_packet(packet)

    @staticmethod
    def public_openclaw_profiles():
        path = HERE.parent / 'c-capability-lifecycle-candidate/artifact/epoch7-kit-claim-lifecycle.tar.gz'
        raw = path.read_bytes()
        if len(raw) != 1074448 or hashlib.sha256(raw).hexdigest() != \
                'bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3':
            raise AssertionError('PUBLIC_KIT_AUTHENTICATION_FAILED')
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            names = archive.getnames()
            entries = [name for name in names if name.endswith('/epoch7_recovery_entry.py')]
            if len(entries) != 1:
                raise AssertionError('PUBLIC_ENTRY_NOT_UNIQUE')
            entry = entries[0]
            prefix = entry.rsplit('/', 1)[0] + '/'
            wanted = {'PUBLIC_OPENCLAW_FIXTURE', 'PUBLIC_OPENCLAW_DIRECT_FIXTURE',
                'PUBLIC_OPENCLAW_DIRECT_PATH', 'PUBLIC_OPENCLAW_DIRECT_SHA'}
            constants = {}
            for node in ast.parse(archive.extractfile(entry).read()).body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in wanted:
                            constants[target.id] = ast.literal_eval(node.value)
            if set(constants) != wanted:
                raise AssertionError('PUBLIC_CONSTANTS_INCOMPLETE')
            profiles = []
            for key in ('PUBLIC_OPENCLAW_FIXTURE', 'PUBLIC_OPENCLAW_DIRECT_FIXTURE'):
                name = prefix + constants[key]
                if names.count(name) != 1:
                    raise AssertionError('PUBLIC_PROFILE_NOT_UNIQUE')
                profile = json.loads(archive.extractfile(name).read())
                for row in profile['files'].values():
                    content = base64.b64decode(row['content_base64'], validate=True)
                    if hashlib.sha256(content).hexdigest() != row['sha256']:
                        raise AssertionError('PUBLIC_PROFILE_CONTENT_MISMATCH')
                profiles.append(profile)
        return profiles, constants

    def held(self, operation):
        with self.assertRaises(schema.StaticHold) as caught:
            operation()
        self.assertRegex(str(caught.exception), r'^PREIMAGE_[A-Z_]+_HOLD$')
        self.assertNotIn('SYNTHETIC_PATH_SCOPE', str(caught.exception))
        self.assertNotIn('SECRETSENTINEL', str(caught.exception))
        self.assertLess(len(str(caught.exception)), 128)

    @classmethod
    def private_file(cls, path, content_hash):
        return {'path': path, 'kind': 'FILE', 'uid': 0, 'gid': 0, 'mode': 0o600,
            'sha256': content_hash, 'access_acl': cls.FILE_ACL}

    @staticmethod
    def directory_projection(metadata, inode=True):
        fields = ('uid', 'gid', 'mode', 'access_acl', 'default_acl')
        if inode:
            fields += ('dev', 'ino')
        return {key: metadata[key] for key in fields}

    @classmethod
    def scoped_fixture(cls):
        unused_preimages, plan, body, fixture, inputs, proposal, timer = prepared_preimages()
        measured = cls.packet['measured_predecessor']
        directories = measured['transaction_directories']
        extra_files = [cls.private_file(path, content_hash)
            for path, content_hash in measured['transaction_inventory'].items()]
        for view in inputs['resource_views']:
            for rows in view.values():
                for row in rows:
                    if row['path'] in directories and row['kind'] == 'DIRECTORY':
                        expected = directories[row['path']]
                        row.update({key: expected[key] for key in row})
            view['historical'].extend(copy.deepcopy(extra_files))
        for path, metadata in directories.items():
            inputs['resource_directories'][path] = [cls.directory_projection(metadata)]
        preimages = schema.build_preimages(fixture.factory, inputs, proposal, timer,
            path_scope=cls.scope)
        # Bind the enlarged public synthetic fixture with the genuine factory's
        # original digest routines, not a second implementation of those roots.
        observer = plan['resource_observer']
        observer['views_sha256'] = fixture.factory.resource_views_digest(inputs['resource_views'])
        observer['directories_sha256'] = fixture.factory.resource_directories_digest(inputs['resource_directories'])
        for checkpoint, view in zip(plan['live_controls']['checkpoints'], inputs['resource_views']):
            checkpoint['resources'] = {name: fixture.delta.digest(view[name]) for name in schema.SECTIONS}
        return preimages, plan, body, fixture, inputs, proposal, timer

    def test_optional_scope_api_is_explicit_and_legacy_default_preserved(self):
        self.assertEqual(list(inspect.signature(schema.path_scope_from_packet).parameters), ['packet'])
        for name in ('build_preimages', 'verify_preimages', 'privacy_project',
                'verify_projected_preimages', '_validate', '_resources', '_resource',
                '_path', '_visible_directory_digest', '_validate_projected'):
            with self.subTest(api=name):
                parameters = list(inspect.signature(getattr(schema, name)).parameters.values())
                self.assertEqual(parameters[-1].name, 'path_scope')
                self.assertIsNone(parameters[-1].default)
        preimages, plan, body, unused_fixture, unused_inputs, unused_proposal, unused_timer = prepared_preimages()
        self.assertEqual(schema.verify_preimages(preimages, plan, body),
            schema.verify_preimages(preimages, plan, body, path_scope=None))
        self.assertEqual(schema.PACKET_SIZE, 29665)
        self.assertRegex(schema.PACKET_SHA256, r'^[0-9a-f]{64}$')

    def test_public_aliases_accept_only_files_or_links(self):
        for path in self.PUBLIC_ALIASES:
            file = dict(self.private_file(path, 'a' * 64), mode=0o755,
                access_acl='user::rwx\ngroup::r-x\nother::r-x\n')
            link = {'path': path, 'kind': 'LINK', 'uid': 0, 'gid': 0, 'sha256': 'b' * 64}
            with self.subTest(path=path):
                schema._resource(file)
                schema._resource(link)
                for row in ({'path': path, 'kind': 'ABSENT'},
                        {'path': path, 'kind': 'TREE_INVENTORY', 'sha256': 'b' * 64},
                        {'path': path, 'kind': 'MASK', 'uid': 0, 'gid': 0, 'link': '/dev/null'},
                        dict(path=path, kind='DIRECTORY', uid=0, gid=0, mode=0o700,
                            access_acl=self.DIRECTORY_ACL, default_acl='')):
                    self.held(lambda row=row: schema._resource(row))
                for nearby in (path + '.nearby', path + '/child', path + '/', path + '/../SECRETSENTINEL'):
                    self.held(lambda nearby=nearby: schema._path(nearby))
                directory = dict(uid=0, gid=0, mode=0o700,
                    access_acl=self.DIRECTORY_ACL, default_acl='')
                self.held(lambda: schema._visible_directory_digest({'/': [directory], path: [directory]}))

    def test_two_authenticated_public_openclaw_profiles_and_direct_leaf(self):
        self.assertEqual([len(profile['files']) for profile in self.profiles], [31, 1])
        root = schema.NODE_ROOT + '/lib/node_modules/openclaw/'
        for profile in self.profiles:
            for relative, source in profile['files'].items():
                row = dict(self.private_file(root + relative, source['sha256']), uid=1002,
                    gid=1002, mode=0o644, access_acl='user::rw-\ngroup::r--\nother::r--\n')
                with self.subTest(relative=relative):
                    schema._resource(row)
        relative = self.public_constants['PUBLIC_OPENCLAW_DIRECT_PATH']
        pin = self.public_constants['PUBLIC_OPENCLAW_DIRECT_SHA']
        self.assertEqual(self.profiles[1]['files'][relative]['sha256'], pin)
        row = dict(self.private_file(root + relative, pin), uid=1002, gid=1002,
            mode=0o644, access_acl='user::rw-\ngroup::r--\nother::r--\n')
        for mutation in ({'sha256': '0' * 64}, {'kind': 'SANDBOX_STABLE'},
                {'path': root + relative + '.nearby'},
                {'path': root + relative.replace('dist/', 'dist/../dist/')},
                {'path': root.replace('node-v24.21.0', 'node-v24.21.1') + relative}):
            self.held(lambda mutation=mutation: schema._resource(dict(row, **mutation)))
        for replacement in ({'path': row['path'], 'kind': 'ABSENT'},
                {'path': row['path'], 'kind': 'LINK', 'uid': 1002, 'gid': 1002, 'sha256': pin},
                {'path': row['path'], 'kind': 'TREE_INVENTORY', 'sha256': pin}):
            self.held(lambda replacement=replacement: schema._resource(replacement))

    def test_whole_packet_bytes_and_newline_are_authenticated_before_scope(self):
        packet = copy.deepcopy(self.packet)
        raw = schema.canonical(packet, schema.MAX_BYTES) + b'\n'
        self.assertEqual(len(packet['measured_predecessor']['transaction_inventory']), 47)
        self.assertEqual(len(packet['measured_predecessor']['transaction_directories']), 9)
        self.held(lambda: schema.path_scope_from_packet(packet))
        for size, pin in ((len(raw) - 1, hashlib.sha256(raw).hexdigest()),
                (len(raw) + 1, hashlib.sha256(raw).hexdigest()),
                (len(raw), '0' * 64),
                (len(raw) - 1, hashlib.sha256(raw[:-1]).hexdigest())):
            with self.subTest(size=size, pin=pin), mock.patch.object(schema, 'PACKET_SIZE', size), \
                    mock.patch.object(schema, 'PACKET_SHA256', pin):
                self.held(lambda: schema.path_scope_from_packet(packet))
        with mock.patch.object(schema, 'PACKET_SIZE', len(raw)), \
                mock.patch.object(schema, 'PACKET_SHA256', hashlib.sha256(raw).hexdigest()):
            packet['measured_predecessor']['measurement']['record']['SECRETSENTINEL'] = 1
            self.held(lambda: schema.path_scope_from_packet(packet))
            for value in (raw, raw.decode(), [], True, None):
                self.held(lambda value=value: schema.path_scope_from_packet(value))

    def test_authenticated_packet_nested_schema_count_and_type_fail_closed(self):
        def measured(packet): return packet['measured_predecessor']
        first_file = next(iter(self.packet['measured_predecessor']['transaction_inventory']))
        first_directory = next(iter(self.packet['measured_predecessor']['transaction_directories']))
        mutations = [
            lambda p: p.pop('measured_predecessor'),
            lambda p: measured(p).update(extra='SECRETSENTINEL'),
            lambda p: measured(p).pop('measurement'),
            lambda p: measured(p).update(measurement=[]),
            lambda p: measured(p)['measurement'].update(schema=True),
            lambda p: measured(p)['measurement'].update(schema=2),
            lambda p: measured(p)['measurement'].update(extra='SECRETSENTINEL'),
            lambda p: measured(p)['measurement'].pop('record'),
            lambda p: measured(p)['measurement'].update(record=[]),
            lambda p: measured(p)['measurement'].update(ancestors=[]),
            lambda p: measured(p)['measurement'].update(absent=[]),
            lambda p: measured(p).update(transaction_inventory=[]),
            lambda p: measured(p)['transaction_inventory'].pop(first_file),
            lambda p: measured(p)['transaction_inventory'].update({schema.TRANSACTION + '/SYNTHETIC_EXTRA.private': 'a' * 64}),
            lambda p: measured(p)['transaction_inventory'].update({first_file: True}),
            lambda p: measured(p)['transaction_inventory'].update({first_file: 'A' * 64}),
            lambda p: measured(p).update(transaction_directories=[]),
            lambda p: measured(p)['transaction_directories'].pop(first_directory),
            lambda p: measured(p)['transaction_directories'][first_directory].pop('path'),
            lambda p: measured(p)['transaction_directories'][first_directory].update(path=first_directory + '/other'),
            lambda p: measured(p)['transaction_directories'][first_directory].update(extra='SECRETSENTINEL'),
            lambda p: measured(p)['transaction_directories'][first_directory].update(kind='FILE'),
            lambda p: measured(p)['transaction_directories'][first_directory].update(uid=1),
            lambda p: measured(p)['transaction_directories'][first_directory].update(gid=1),
            lambda p: measured(p)['transaction_directories'][first_directory].update(mode=0o755),
            lambda p: measured(p)['transaction_directories'][first_directory].update(access_acl='user::rwx\ngroup::r-x\nother::---\n'),
            lambda p: measured(p)['transaction_directories'][first_directory].update(default_acl='default:user::rwx\n'),
            lambda p: measured(p)['transaction_parent_delta'].pop('size'),
            lambda p: measured(p)['transaction_parent_delta'].update(extra={}),
            lambda p: measured(p)['transaction_parent_delta']['size'].pop('historical'),
            lambda p: measured(p)['transaction_parent_delta']['size'].update(extra=1),
            lambda p: measured(p)['transaction_parent_delta']['size'].update(live=-1),
            lambda p: measured(p)['transaction_parent_delta']['size'].update(live=True)]
        for field in ('uid', 'gid', 'mode', 'dev', 'ino', 'nlink', 'size', 'mtime_ns', 'ctime_ns'):
            mutations.append(lambda p, field=field: measured(p)['transaction_directories'][first_directory].update({field: True}))
            mutations.append(lambda p, field=field: measured(p)['transaction_directories'][first_directory].update({field: -1}))
        for mutate in mutations:
            packet = copy.deepcopy(self.packet)
            mutate(packet)
            with self.subTest(mutation=mutate):
                self.held(lambda packet=packet: self.authenticated_scope(packet))

    def test_authenticated_scope_rejects_path_escape_overlap_and_missing_parents(self):
        measured = self.packet['measured_predecessor']
        first_file = next(iter(measured['transaction_inventory']))
        first_child = next(path for path in measured['transaction_directories'] if path != schema.TRANSACTION)
        invalid_files = (schema.TRANSACTION + '-nearby/SYNTHETIC.private',
            schema.TRANSACTION + '/../SYNTHETIC.private',
            schema.TRANSACTION + '/./SYNTHETIC.private',
            schema.TRANSACTION + '//SYNTHETIC.private',
            schema.TRANSACTION + '/SYNTHETIC_ORPHAN/file.private',
            schema.TRANSACTION + '/SYNTHETIC\x00.private', first_child,
            '/tmp/SYNTHETIC_PATH_SCOPE_SECRET.private', 7)
        for path in invalid_files:
            packet = copy.deepcopy(self.packet)
            inventory = packet['measured_predecessor']['transaction_inventory']
            content_hash = inventory.pop(first_file); inventory[path] = content_hash
            with self.subTest(kind='file', path=path):
                self.held(lambda packet=packet: self.authenticated_scope(packet))
        for path in (schema.TRANSACTION + '/SYNTHETIC_ORPHAN/child',
                schema.TRANSACTION + '/../SYNTHETIC_DIRECTORY',
                schema.TRANSACTION + '/./SYNTHETIC_DIRECTORY',
                schema.TRANSACTION + '//SYNTHETIC_DIRECTORY',
                schema.TRANSACTION + '-nearby', first_file):
            packet = copy.deepcopy(self.packet)
            directories = packet['measured_predecessor']['transaction_directories']
            row = directories.pop(first_child); row['path'] = path; directories[path] = row
            with self.subTest(kind='directory', path=path):
                self.held(lambda packet=packet: self.authenticated_scope(packet))
        packet = copy.deepcopy(self.packet)
        extra = schema.TRANSACTION + '/SYNTHETIC_TENTH_DIRECTORY'
        row = copy.deepcopy(packet['measured_predecessor']['transaction_directories'][first_child])
        row['path'] = extra
        packet['measured_predecessor']['transaction_directories'][extra] = row
        self.held(lambda: self.authenticated_scope(packet))

    def test_exact_private_file_pins_permissions_and_kinds(self):
        inventory = self.packet['measured_predecessor']['transaction_inventory']
        for path, content_hash in inventory.items():
            row = self.private_file(path, content_hash)
            with self.subTest(path=path):
                schema._path(path, path_scope=self.scope)
                schema._resource(row, path_scope=self.scope)
                self.held(lambda: schema._resource(row))
        path, content_hash = next(iter(inventory.items()))
        row = self.private_file(path, content_hash)
        mutations = ({'uid': 1}, {'gid': 1}, {'mode': 0o640}, {'mode': 0o400},
            {'sha256': '0' * 64}, {'uid': False}, {'gid': False},
            {'access_acl': 'user::rw-\ngroup::r--\nother::---\n'},
            {'access_acl': self.FILE_ACL + 'user:1002:r--\n'},
            {'access_acl': 'group::---\nuser::rw-\nother::---\n'},
            {'kind': 'SANDBOX_STABLE'}, {'extra': 'SECRETSENTINEL'})
        for mutation in mutations:
            self.held(lambda mutation=mutation: schema._resource(dict(row, **mutation), path_scope=self.scope))
        for replacement in ({'path': path, 'kind': 'ABSENT'},
                {'path': path, 'kind': 'LINK', 'uid': 0, 'gid': 0, 'sha256': content_hash},
                {'path': path, 'kind': 'TREE_INVENTORY', 'sha256': content_hash},
                dict(path=path, kind='DIRECTORY', uid=0, gid=0, mode=0o700,
                    access_acl=self.DIRECTORY_ACL, default_acl='')):
            self.held(lambda replacement=replacement: schema._resource(replacement, path_scope=self.scope))
        for unknown in (path + '.nearby', str(pathlib.PurePosixPath(path).parent) + '/SYNTHETIC_UNKNOWN.private',
                path + '/child', path.replace('/SYNTHETIC_', '/../SYNTHETIC_')):
            self.held(lambda unknown=unknown: schema._resource(dict(row, path=unknown), path_scope=self.scope))

    def test_directory_projections_match_every_present_packet_field(self):
        directories = self.packet['measured_predecessor']['transaction_directories']
        for path, metadata in directories.items():
            for inode in (False, True):
                projection = self.directory_projection(metadata, inode=inode)
                row = dict(projection, path=path, kind='DIRECTORY')
                with self.subTest(path=path, inode=inode):
                    schema._resource(row, path_scope=self.scope)
                    # The existing public transaction root keeps its legacy
                    # policy; exact Packet metadata binds newly added paths.
                    if path == schema.TRANSACTION:
                        continue
                    for key, value in projection.items():
                        wrong = value + 1 if type(value) is int else value + 'SECRETSENTINEL'
                        self.held(lambda key=key, wrong=wrong: schema._resource(
                            dict(row, **{key: wrong}), path_scope=self.scope))
        path = next(path for path in directories if path != schema.TRANSACTION)
        metadata = directories[path]
        self.held(lambda: schema._resource(self.private_file(path, 'a' * 64), path_scope=self.scope))
        self.held(lambda: schema._resource({'path': path, 'kind': 'ABSENT'}, path_scope=self.scope))
        safe_root = {'uid': 0, 'gid': 0, 'mode': 0o755,
            'access_acl': 'user::rwx\ngroup::r-x\nother::r-x\n', 'default_acl': ''}
        projected = {'/': [safe_root], path: [self.directory_projection(metadata)]}
        schema._visible_directory_digest(projected, path_scope=self.scope)
        self.held(lambda: schema._visible_directory_digest(projected))
        for key in self.directory_projection(metadata):
            changed = copy.deepcopy(projected)
            value = changed[path][0][key]
            changed[path][0][key] = value + 1 if type(value) is int else value + 'SECRETSENTINEL'
            self.held(lambda changed=changed: schema._visible_directory_digest(changed, path_scope=self.scope))

    def test_scope_is_copied_immutable_and_self_supplied_dict_is_not_authority(self):
        packet = copy.deepcopy(self.packet)
        scope = self.authenticated_scope(packet)
        measured = packet['measured_predecessor']
        path, content_hash = next(iter(measured['transaction_inventory'].items()))
        directory = str(pathlib.PurePosixPath(path).parent)
        old_directory = copy.deepcopy(measured['transaction_directories'][directory])
        measured['transaction_inventory'][path] = '0' * 64
        measured['transaction_directories'][directory]['ino'] += 1
        injected_path = directory + '/SYNTHETIC_INJECTED.private'
        measured['transaction_inventory'][injected_path] = 'a' * 64
        schema._resource(self.private_file(path, content_hash), path_scope=scope)
        schema._resource(dict(self.directory_projection(old_directory), path=directory,
            kind='DIRECTORY'), path_scope=scope)
        self.held(lambda: schema._resource(self.private_file(path, '0' * 64), path_scope=scope))
        self.held(lambda: schema._resource(self.private_file(injected_path, 'a' * 64), path_scope=scope))
        with self.assertRaises((AttributeError, TypeError, schema.StaticHold)):
            scope.synthetic_override = True
        self.held(lambda: type(scope)(object(), {}, {}))
        with self.assertRaises(TypeError):
            scope.files[path] = '0' * 64
        with self.assertRaises(TypeError):
            scope.directories[directory]['ino'] = 0
        self.held(lambda: setattr(scope, 'files', {}))
        self.held(lambda: delattr(scope, 'directories'))
        for impostor in (packet, measured, measured['transaction_inventory'], {}, [], True, object()):
            self.held(lambda impostor=impostor: schema._path(path, path_scope=impostor))
            self.held(lambda impostor=impostor: schema._resource(
                self.private_file(path, content_hash), path_scope=impostor))

    def test_scope_threads_through_build_verify_and_hmac_only_projection(self):
        preimages, plan, body, fixture, inputs, proposal, timer = self.scoped_fixture()
        checks = schema.verify_preimages(preimages, plan, body, path_scope=self.scope)
        self.assertTrue(checks['resource_views'])
        self.assertTrue(checks['resource_directories'])
        views, info = schema._resources(preimages['resources'], path_scope=self.scope)
        self.assertEqual(views, inputs['resource_views'])
        self.assertEqual(info['directories_sha256'], plan['resource_observer']['directories_sha256'])
        projected = schema.privacy_project(preimages, b'k' * 32, self.CONTEXT, path_scope=self.scope)
        visible = schema.verify_projected_preimages(projected, plan, body, path_scope=self.scope)
        self.assertTrue(visible['resource_directories'])
        self.assertFalse(visible['hidden_commitments_independently_verified'])
        self.assertEqual(projected['visible']['resource_directories'], inputs['resource_directories'])
        raw = schema.canonical(projected, schema.MAX_BYTES)
        for path, content_hash in self.packet['measured_predecessor']['transaction_inventory'].items():
            self.assertNotIn(path.encode(), raw)
            self.assertNotIn(content_hash.encode(), raw)
        for forbidden in (b'transaction_inventory', b'transaction_parent_delta', b'measured_predecessor',
                b'path_scope', b'ordered_index', b'"records"', b'kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk',
                plan['resource_observer']['views_sha256'].encode()):
            self.assertNotIn(forbidden, raw)
        for operation in (
                lambda: schema.build_preimages(fixture.factory, inputs, proposal, timer),
                lambda: schema.verify_preimages(preimages, plan, body),
                lambda: schema.privacy_project(preimages, b'k' * 32, self.CONTEXT),
                lambda: schema.verify_projected_preimages(projected, plan, body)):
            self.held(operation)
        for operation in (
                lambda: schema.build_preimages(fixture.factory, inputs, proposal, timer, path_scope={}),
                lambda: schema.verify_preimages(preimages, plan, body, path_scope={}),
                lambda: schema.privacy_project(preimages, b'k' * 32, self.CONTEXT, path_scope={}),
                lambda: schema.verify_projected_preimages(projected, plan, body, path_scope={})):
            self.held(operation)
        changed_packet = copy.deepcopy(self.packet)
        path = next(iter(changed_packet['measured_predecessor']['transaction_inventory']))
        new_hash = hashlib.sha256(b'SYNTHETIC_CHANGED_PRIVATE_CONTENT').hexdigest()
        changed_packet['measured_predecessor']['transaction_inventory'][path] = new_hash
        changed_scope = self.authenticated_scope(changed_packet)
        changed_preimages = copy.deepcopy(preimages)
        next(row for row in changed_preimages['resources']['records'] if row['path'] == path)['sha256'] = new_hash
        changed = schema.privacy_project(changed_preimages, b'k' * 32, self.CONTEXT, path_scope=changed_scope)
        self.assertNotEqual(projected['withheld']['resource_views']['commitment'],
            changed['withheld']['resource_views']['commitment'])
        self.assertNotIn(new_hash.encode(), schema.canonical(changed, schema.MAX_BYTES))
        for name in set(schema.PRIVATE_SEGMENTS) - {'resource_views'}:
            self.assertEqual(projected['withheld'][name], changed['withheld'][name])
        tampered = copy.deepcopy(projected)
        tampered['withheld']['resource_views']['commitment'] = 'f' * 64
        self.assertFalse(schema.verify_projected_preimages(tampered, plan, body,
            path_scope=self.scope)['hidden_commitments_independently_verified'])


if __name__ == '__main__':
    unittest.main()
