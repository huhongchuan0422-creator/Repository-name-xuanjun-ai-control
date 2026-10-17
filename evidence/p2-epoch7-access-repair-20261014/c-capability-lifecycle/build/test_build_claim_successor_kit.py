"""Real immutable archive + exact overlays; zero identities are fixture-only.

No production archive, host observation, host installation or resume is produced.
"""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('claim_successor_builder', str(HERE / 'build_claim_successor_kit.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def baseline_path():
    override = os.environ.get('CLAIM_SUCCESSOR_BASELINE_ARCHIVE')
    candidates = [Path(override)] if override else [
        ROOT.parent / 'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz',
        ROOT.parent / 'evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz']
    for path in candidates:
        if path.is_file():
            return path
    raise ValueError('Exact baseline archive missing; set CLAIM_SUCCESSOR_BASELINE_ARCHIVE')


def read_output(raw):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive.getmembers():
            if member.isreg():
                files[member.name.split('/', 1)[1]] = archive.extractfile(member).read()
    return files


class BuildClaimSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = builder.read_regular(baseline_path(), builder.ARCHIVE_SIZE)
        cls.map_raw = (HERE / 'OVERLAY_INPUTS.json').read_bytes()
        cls.sources = {source: (ROOT / source).read_bytes() for source in builder.OVERLAY_SOURCES.values()}
        cls.baseline, cls.old_manifest = builder.authenticate_archive(cls.archive)
        cls.output, cls.metadata = cls.compile_fixture()
        cls.files = read_output(cls.output)
        cls.manifest = json.loads(cls.files[builder.MANIFEST].decode())

    @classmethod
    def compile_fixture(cls, **changes):
        args = {'archive_raw': cls.archive, 'map_raw': cls.map_raw, 'sources': cls.sources,
                'source_commit': '0' * 40, 'source_tree': '0' * 40, 'fixture_source': True}
        args.update(changes)
        return builder.compile_artifact(**args)

    def test_actual_archive_and_map_pins(self):
        self.assertEqual(builder.sha(self.archive), builder.ARCHIVE_SHA256)
        self.assertEqual(len(self.baseline), 256)
        self.assertEqual(builder.sha(self.baseline[builder.MANIFEST]), builder.MANIFEST_SHA256)
        mapping = builder.authenticate_map(self.map_raw)
        self.assertEqual(len(mapping['files']), 16)
        self.assertEqual(mapping['baseline_archive_sha256'], builder.ARCHIVE_SHA256)
        self.assertEqual(len(self.archive), 1056853)
        self.assertEqual(builder.ARCHIVE_SHA256,
                         '6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e')
        self.assertFalse(any(row['source'].startswith('/') for row in mapping['files']))

    def test_actual_archive_positive_exact_file_closure(self):
        self.assertEqual(len(self.files), 257)
        self.assertEqual(len(self.manifest['files']), 256)
        self.assertEqual(set(self.files), set(self.manifest['files']) | {builder.MANIFEST})
        for name, pin in self.manifest['files'].items():
            self.assertEqual(builder.sha(self.files[name]), pin, name)
        self.assertEqual(set(self.files) - set(self.baseline), builder.NEW_FILES)
        changed = {name for name in self.baseline if self.baseline[name] != self.files[name]}
        self.assertEqual(changed, (set(builder.OVERLAY_SOURCES) - builder.NEW_FILES) | {builder.MANIFEST})

    def test_runtime_107_and_all_110_package_files_preserved(self):
        names = [name for name in self.baseline if name.startswith(builder.RUNTIME)]
        self.assertEqual(len(names), 110)
        for name in names:
            self.assertEqual(self.files[name], self.baseline[name], name)
        runtime = json.loads(self.files[builder.RUNTIME + 'deploy/integration-manifest.json'].decode())
        self.assertEqual(len(runtime['files']), 107)
        for name, pin in runtime['files'].items():
            self.assertEqual(builder.sha(self.files[builder.RUNTIME + name]), pin)

    def test_manifest_policy_changes_only_intended_successor_modes(self):
        for key in self.old_manifest:
            if key not in ('files', 'kit_source_commit', 'kit_source_tree', 'modules',
                           'status', 'production_resume'):
                self.assertEqual(self.manifest[key], self.old_manifest[key], key)
        self.assertEqual(self.manifest['status'],
                         'CLAIM_SUCCESSOR_CANDIDATE_REQUIRES_NEW_EXACT_APPROVAL')
        self.assertEqual(self.manifest['production_resume'],
                         'AUTHENTICATED_CLAIM_SUCCESSOR_APPROVAL_GATED_SINGLE_ATTEMPT')
        self.assertNotEqual(self.manifest['status'], self.old_manifest['status'])
        self.assertNotEqual(self.manifest['production_resume'], self.old_manifest['production_resume'])
        expected = copy.deepcopy(self.old_manifest['test_suites'])
        self.assertEqual(self.manifest['test_suites'], expected)

    def test_canonical_manifest_and_fixture_provenance(self):
        self.assertEqual(self.files[builder.MANIFEST], builder.canonical(self.manifest))
        self.assertEqual(self.metadata['source_identity'], 'SYNTHETIC_TEST_FIXTURE_NOT_PUBLISHED')
        self.assertFalse(self.metadata['production_resume_authorized'])
        self.assertEqual(self.metadata['output']['source_commit'], '0' * 40)
        self.assertEqual(self.metadata['baseline']['source_commit'], self.old_manifest['kit_source_commit'])
        self.assertEqual(len(self.metadata['unchanged_files']), 240)
        self.assertEqual(self.metadata['output']['files'], {name: builder.sha(raw) for name, raw in self.files.items()})

    def test_byte_determinism(self):
        archive, metadata = self.compile_fixture()
        self.assertEqual(archive, self.output)
        self.assertEqual(builder.canonical(metadata), builder.canonical(self.metadata))

    def test_canonical_tar_and_gzip_headers(self):
        self.assertEqual(self.output[4:8], b'\0' * 4)
        self.assertEqual(self.output[3] & 8, 0)  # no original gzip filename
        with tarfile.open(fileobj=io.BytesIO(self.output), mode='r:gz') as archive:
            members = archive.getmembers()
            self.assertEqual([m.name for m in members], sorted(m.name for m in members))
            self.assertEqual(len(members), 299)
            for member in members:
                self.assertTrue(member.name == builder.OUTPUT_ROOT or member.name.startswith(builder.OUTPUT_ROOT + '/'))
                self.assertEqual((member.uid, member.gid, member.mtime, member.uname, member.gname), (0, 0, 0, '', ''))
                self.assertEqual(member.mode, 0o700 if member.isdir() else 0o444)
                self.assertTrue(member.isdir() or member.isreg())
                self.assertFalse(member.pax_headers)

    def test_reject_missing_overlay_source(self):
        sources = dict(self.sources)
        sources.pop(next(iter(sources)))
        with self.assertRaisesRegex(ValueError, 'OVERLAY_SOURCE_CLOSURE'):
            self.compile_fixture(sources=sources)

    def test_reject_extra_overlay_source(self):
        sources = dict(self.sources, unexpected=b'no')
        with self.assertRaisesRegex(ValueError, 'OVERLAY_SOURCE_CLOSURE'):
            self.compile_fixture(sources=sources)

    def test_reject_changed_overlay_hash(self):
        sources = dict(self.sources)
        key = next(iter(sources))
        sources[key] = sources[key][:-1] + b'!'
        with self.assertRaisesRegex(ValueError, 'OVERLAY_SOURCE_PIN'):
            self.compile_fixture(sources=sources)

    def test_reject_missing_extra_or_changed_overlay_map(self):
        for mutate in ('missing', 'extra', 'path', 'hash'):
            mapping = json.loads(self.map_raw.decode())
            if mutate == 'missing':
                mapping['files'].pop()
            elif mutate == 'extra':
                mapping['files'].append(mapping['files'][0])
            elif mutate == 'path':
                mapping['files'][0]['source'] = '../escape.py'
            else:
                mapping['files'][0]['sha256'] = '0' * 64
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, 'OVERLAY_MAP_PIN'):
                self.compile_fixture(map_raw=builder.canonical(mapping))

    def test_reject_archive_hash(self):
        with self.assertRaisesRegex(ValueError, 'BASELINE_ARCHIVE_PIN'):
            self.compile_fixture(archive_raw=self.archive[:-1] + bytes([self.archive[-1] ^ 1]))

    def test_reject_missing_baseline_file(self):
        files = dict(self.baseline)
        files.pop('epoch7_recovery_entry.py')
        with self.assertRaisesRegex(ValueError, 'BASELINE_FILE_CLOSURE'):
            builder.validate_file_closure(files, self.old_manifest)

    def test_reject_extra_baseline_file(self):
        files = dict(self.baseline, unexpected=b'no')
        with self.assertRaisesRegex(ValueError, 'BASELINE_FILE_CLOSURE'):
            builder.validate_file_closure(files, self.old_manifest)

    def test_reject_baseline_file_hash(self):
        files = dict(self.baseline)
        files['epoch7_recovery_entry.py'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'BASELINE_FILE_HASH'):
            builder.validate_file_closure(files, self.old_manifest)

    def test_reject_unsafe_relative_paths(self):
        for path in ('/absolute', '../escape', 'a/../b', 'a//b', './a', 'a\\b', 'a\0b', ''):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'UNSAFE_RELATIVE_PATH'):
                builder.relative(path)

    def mutated_archive(self, mutate):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(self.archive), mode='r:gz') as source:
            with tarfile.open(fileobj=buffer, mode='w:gz', format=tarfile.USTAR_FORMAT) as dest:
                for index, member in enumerate(source.getmembers()):
                    data = source.extractfile(member).read() if member.isreg() else b''
                    changed = copy.copy(member)
                    if index == 1:
                        mutate(changed)
                    dest.addfile(changed, io.BytesIO(data) if changed.isreg() else None)
        return buffer.getvalue()

    def test_reject_archive_traversal(self):
        raw = self.mutated_archive(lambda member: setattr(member, 'name', builder.BASELINE_ROOT + '/../escape'))
        with self.assertRaisesRegex(ValueError, 'UNSAFE_RELATIVE_PATH'):
            builder._archive_files(raw)

    def test_reject_archive_symlink(self):
        def mutate(member):
            member.type, member.linkname, member.size = tarfile.SYMTYPE, '/etc/passwd', 0
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_EXTENDED_OR_LINK'):
            builder._archive_files(self.mutated_archive(mutate))

    def test_reject_archive_duplicate_name(self):
        raw = self.mutated_archive(lambda member: setattr(member, 'name', builder.BASELINE_ROOT))
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_DUPLICATE_PATH'):
            builder._archive_files(raw)

    def test_reject_malformed_commit_or_tree(self):
        for bad in (None, '', True, 'None', 'a' * 39, 'g' * 40, 'A' * 40, 'a' * 41):
            for field in ('source_commit', 'source_tree'):
                with self.subTest(value=bad, field=field), self.assertRaisesRegex(ValueError, 'SOURCE_IDENTITY_FORMAT'):
                    self.compile_fixture(**{field: bad})

    def test_reject_zero_identity_outside_fixture(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_IDENTITY_UNPUBLISHED'):
            self.compile_fixture(fixture_source=False)
        with self.assertRaisesRegex(ValueError, 'FIXTURE_REQUIRES_EXPLICIT_ZERO_IDENTITIES'):
            self.compile_fixture(source_commit=self.old_manifest['kit_source_commit'])

    def test_reject_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            builder.strict_json(b'{"x":1,"x":2}')

    def test_no_overwrite_or_symlink_file_io(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            root = Path(tmp)
            output = root / 'existing'
            output.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                builder.write_new(output, b'changed')
            self.assertEqual(output.read_bytes(), b'original')
            (root / 'alias').symlink_to(output)
            with self.assertRaisesRegex(ValueError, 'INPUT_PATH_SYMLINK'):
                builder.read_regular(root / 'alias', 100)

    def test_new_helper_exact_pin_and_module_authority_only(self):
        self.assertEqual(builder.NEW_FILES, {'helpers/epoch7_claim_successor.py'})
        target = next(iter(builder.NEW_FILES))
        self.assertEqual(self.files[target], self.sources[builder.OVERLAY_SOURCES[target]])
        self.assertEqual(self.manifest['files'][target], builder.sha(self.files[target]))
        self.assertEqual(self.manifest['modules'], dict(self.old_manifest['modules'],
            epoch7_claim_successor=target))
        self.assertEqual(len(self.manifest['modules']), 111)
        self.assertEqual(self.metadata['module_added'], 'epoch7_claim_successor')
        self.assertFalse(self.metadata['existing_modules_unchanged'])
        self.assertEqual(self.metadata['test_suite_imports_added'], {})
        self.assertTrue(self.metadata['test_suites_unchanged'])
        self.assertEqual(self.metadata['new_test_execution'],
                         'EXPLICIT_AUTHENTICATED_CI_HARNESS_NOT_VERIFIEDKIT_TESTS')

    def test_static_inherited_import_closure_rejects_missing_authority(self):
        manifest = copy.deepcopy(self.manifest)
        del manifest['test_suites']['host_factory']['imports']['test_epoch7_live_controls']
        with self.assertRaisesRegex(ValueError, 'UNDECLARED_STATIC_TEST_IMPORT'):
            builder.validate_test_suites(manifest, self.files)
        self.assertEqual(self.manifest['test_suites'], self.old_manifest['test_suites'])

    def test_archive_header_count_independent_of_digest(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz', format=tarfile.USTAR_FORMAT):
            pass
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_HEADER_COUNT'):
            builder._archive_files(buffer.getvalue())

    def test_reject_archive_hardlink(self):
        def mutate(member):
            member.type, member.linkname, member.size = tarfile.LNKTYPE, builder.BASELINE_ROOT, 0
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_EXTENDED_OR_LINK'):
            builder._archive_files(self.mutated_archive(mutate))

    def test_reject_archive_device(self):
        def mutate(member):
            member.type, member.size = tarfile.CHRTYPE, 0
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_FILE_TYPE_OR_SIZE'):
            builder._archive_files(self.mutated_archive(mutate))

    def test_cli_rejects_fixture_identity_before_output(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            output, metadata = Path(tmp) / 'must-not-exist.tar.gz', Path(tmp) / 'must-not-exist.json'
            result = subprocess.run([sys.executable, '-I', '-S', '-B',
                str(HERE / 'build_claim_successor_kit.py'), '--archive', str(baseline_path()),
                '--source-commit', '0' * 40, '--source-tree', '0' * 40,
                '--output', str(output), '--metadata', str(metadata)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'SOURCE_IDENTITY_UNPUBLISHED', result.stderr)
            self.assertFalse(output.exists() or metadata.exists())

    def test_exact_resourcebind_baseline_identity_is_retained(self):
        self.assertEqual(self.old_manifest['kit_source_commit'], 'ef21ca95331769622c294c65bb60ec7ceed0c392')
        self.assertEqual(self.old_manifest['kit_source_tree'], '5a70c5627afe75fcd475c20e71ee9bfb0b6a156d')
        self.assertEqual(self.metadata['baseline']['source_commit'], self.old_manifest['kit_source_commit'])
        self.assertEqual(self.metadata['baseline']['source_tree'], self.old_manifest['kit_source_tree'])
        self.assertEqual(self.metadata['output']['source_commit'], '0' * 40)
        self.assertEqual(self.metadata['output']['source_tree'], '0' * 40)

    def test_python36_syntax_only_for_builder_and_overlays(self):
        # Newer Python selects 3.6 grammar; Python 3.6 uses its native parser.
        # This check never launches a separate interpreter.
        bodies = dict(self.sources)
        bodies['build/build_claim_successor_kit.py'] = (HERE / 'build_claim_successor_kit.py').read_bytes()
        bodies['build/test_build_claim_successor_kit.py'] = Path(__file__).read_bytes()
        for name, raw in bodies.items():
            with self.subTest(path=name):
                if sys.version_info >= (3, 8):
                    ast.parse(raw, filename=name, feature_version=(3, 6))
                else:
                    ast.parse(raw, filename=name)

    def test_authenticated_cached_production_imports_and_real_loader_validation(self):
        # Authenticate exact fixture bytes, then delete Python source files before
        # imports. No legacy suite discovery or test bodies are executed.
        script = r'''
import hashlib, importlib, importlib.util, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
raw = (root / 'recovery-kit-manifest.json').read_bytes()
manifest = json.loads(raw.decode())
cache = {name: (root / name).read_bytes() for name in manifest['files']}
assert len(cache) == 256
assert all(hashlib.sha256(cache[name]).hexdigest() == pin for name, pin in manifest['files'].items())
spec = importlib.util.spec_from_file_location('fixture_entry', str(root / 'epoch7_recovery_entry.py'))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
entry.validate_manifest(manifest)
entry.validate_runtime(manifest, cache)
kit = entry.VerifiedKit(str(root), manifest, cache, hashlib.sha256(raw).hexdigest(), raw_manifest=raw)
for path in root.rglob('*.py'):
    path.unlink()
requested = json.loads(sys.argv[2])
with kit.imports() as loader:
    for alias in requested:
        module = importlib.import_module(alias)
        assert module.__loader__ is loader
        assert module.__cached__ is None
        assert alias in loader.loaded
        assert not pathlib.Path(module.__file__).exists()
    successor = sys.modules['epoch7_claim_successor']
    assert successor.__loader__ is loader
    assert len(sys.modules['epoch7_recovery_sequence'].PHASES) == 16
    assert not any(alias.startswith('test_') for alias in loader.loaded)
    assert all(alias not in loader.modules for alias in ('resource_aggregate_fixture', 'test_resource_aggregate_closure'))
    for alias in ('resource_aggregate_fixture', 'test_resource_aggregate_closure'):
        try:
            importlib.import_module(alias)
        except ModuleNotFoundError as error:
            assert str(error) == 'EPOCH7_KIT_UNDECLARED_IMPORT:' + alias
        else:
            raise AssertionError('Unrequested import authority was granted: ' + alias)
assert all(alias not in sys.modules for alias in requested)
invalid = json.loads(raw.decode())
del invalid['modules']['epoch7_claim_successor']
try:
    entry.validate_manifest(invalid)
except ValueError as error:
    assert 'EXACT_IMPORTABLE_MODULE_SET' in str(error)
else:
    raise AssertionError('Missing helper module was accepted')
invalid = json.loads(raw.decode())
invalid['test_suites']['host_factory']['imports']['resource_aggregate_fixture'] = 'tests/host_factory/resource_aggregate_fixture.py'
try:
    entry.validate_manifest(invalid)
except ValueError as error:
    assert 'TEST_IMPORT' in str(error)
else:
    raise AssertionError('Frozen non-test alias policy was widened')
print('AUTHENTICATED_SUCCESSOR_CACHED_IMPORTS_15_PASS; LEGACY_SUITES_NOT_RUN')
'''
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            root = Path(tmp) / builder.OUTPUT_ROOT
            for name, body in self.files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            aliases = sorted(path.rsplit('/', 1)[1][:-3]
                for path in builder.OVERLAY_SOURCES if path.startswith('helpers/'))
            self.assertEqual(len(aliases), 15)
            result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', script,
                                     str(root), json.dumps(aliases)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertIn(b'AUTHENTICATED_SUCCESSOR_CACHED_IMPORTS_15_PASS', result.stdout)


    def test_exact_overlay_target_source_and_git_blob_closure(self):
        mapping = builder.authenticate_map(self.map_raw)
        self.assertEqual(self.map_raw, builder.canonical(mapping))
        self.assertEqual({row['kit_target']: row['source'] for row in mapping['files']},
                         builder.OVERLAY_SOURCES)
        self.assertEqual(len({row['source'] for row in mapping['files']}), 16)
        for row in mapping['files']:
            body = self.sources[row['source']]
            blob = hashlib.sha1(('blob %d\0' % len(body)).encode('ascii') + body).hexdigest()
            self.assertEqual((len(body), builder.sha(body), blob),
                             (row['bytes'], row['sha256'], row['git_blob_sha1']))
            self.assertEqual(row['baseline_sha256'], None if row['kit_target'] in
                             builder.NEW_FILES else builder.sha(self.baseline[row['kit_target']]))
        self.assertEqual(self.metadata['overlays'], mapping['files'])
        self.assertEqual(self.metadata['added_files'], ['helpers/epoch7_claim_successor.py'])
        self.assertEqual(len(self.metadata['modified_files']), 16)

    def test_all_legacy_tests_and_suite_policy_remain_byte_identical(self):
        inherited = {name for name in self.baseline if name.startswith('tests/')}
        self.assertTrue(inherited)
        self.assertEqual(inherited, {name for name in self.files if name.startswith('tests/')})
        for name in inherited:
            self.assertEqual(self.files[name], self.baseline[name], name)
        self.assertEqual(self.manifest['test_suites'], self.old_manifest['test_suites'])
        self.assertFalse(any(name.startswith('tests/') for name in builder.OVERLAY_SOURCES))

    def test_exact_static_module_index(self):
        builder.validate_module_closure(self.manifest, self.files)
        candidates = {path for path in self.files if path.endswith('.py') and
                      (path.startswith('helpers/') or path.startswith(builder.RUNTIME + 'stage1/'))}
        self.assertEqual(set(self.manifest['modules'].values()), candidates)
        self.assertEqual(set(self.manifest['modules']) - set(self.old_manifest['modules']),
                         {'epoch7_claim_successor'})

    def test_reject_missing_successor_module_authority(self):
        manifest = copy.deepcopy(self.manifest)
        del manifest['modules']['epoch7_claim_successor']
        with self.assertRaisesRegex(ValueError, 'EXACT_IMPORTABLE_MODULE_SET'):
            builder.validate_module_closure(manifest, self.files)

    def test_reject_alias_mismatch_or_duplicate_module_authority(self):
        for duplicate in (False, True):
            manifest = copy.deepcopy(self.manifest)
            path = manifest['modules']['epoch7_claim_successor']
            if not duplicate:
                del manifest['modules']['epoch7_claim_successor']
            manifest['modules']['unauthorized_alias'] = path
            expected = 'EXACT_IMPORTABLE_MODULE_SET' if duplicate else 'MODULE_ALIAS_PATH'
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(ValueError, expected):
                builder.validate_module_closure(manifest, self.files)

    def test_reject_unindexed_helper_file(self):
        files = dict(self.files, **{'helpers/epoch7_extra.py': b'pass\n'})
        with self.assertRaisesRegex(ValueError, 'EXACT_IMPORTABLE_MODULE_SET'):
            builder.validate_module_closure(self.manifest, files)

    def test_reject_static_unresolved_production_import(self):
        for extra in (b'\nimport epoch7_missing\n', b'\nfrom epoch3_missing import x\n'):
            files = dict(self.files)
            files['helpers/epoch7_claim_successor.py'] += extra
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'UNDECLARED_STATIC_MODULE_IMPORT'):
                builder.validate_module_closure(self.manifest, files)

    def test_exact_16_business_phase_invariants(self):
        builder.validate_business_invariants(self.baseline, self.files)
        path = 'helpers/epoch7_recovery_sequence.py'
        trees = [ast.parse(values[path], filename=path) for values in (self.baseline, self.files)]
        phases = []
        for tree in trees:
            row = next(node for node in tree.body if isinstance(node, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id == 'PHASES' for target in node.targets))
            phases.append(ast.literal_eval(row.value))
        self.assertEqual(phases[0], phases[1])
        self.assertEqual(len(phases[1]), 16)
        self.assertEqual(self.metadata['business_phases_preserved'], 16)
        self.assertTrue(self.metadata['phase_logic_unchanged'])

    def test_reject_modified_business_phase_constants(self):
        path = 'helpers/epoch7_recovery_sequence.py'
        for before, after in ((b"'stage_exact_release'", b"'unreviewed_release'"),
                              (b"'xuanjun-p2-tls-renew.timer'", b"'other.timer'"),
                              (b"CLEANUP = (('fence', None),)", b"CLEANUP = (('other', None),)")):
            files = dict(self.files)
            self.assertIn(before, files[path])
            files[path] = files[path].replace(before, after, 1)
            with self.subTest(before=before), self.assertRaisesRegex(ValueError, 'BUSINESS_PHASE_CONSTANT_CHANGED'):
                builder.validate_business_invariants(self.baseline, files)

    def test_reject_modified_phase_or_cleanup_logic(self):
        path = 'helpers/epoch7_recovery_sequence.py'
        for before, after in ((b'    def phase(self, name):\n', b'    def phase(self, name):\n        return None\n'),
                              (b'def _cleanup(driver, state):\n', b'def _cleanup(driver, state):\n    return None\n')):
            files = dict(self.files)
            self.assertIn(before, files[path])
            files[path] = files[path].replace(before, after, 1)
            with self.subTest(before=before), self.assertRaisesRegex(ValueError, 'BUSINESS_PHASE_LOGIC_CHANGED'):
                builder.validate_business_invariants(self.baseline, files)

    def test_reject_modified_successor_business_loop(self):
        files = dict(self.files)
        path = 'helpers/epoch7_recovery_sequence.py'
        before = b'        for phase in PHASES:\n'
        self.assertEqual(files[path].count(before), 1)
        files[path] = files[path].replace(before, before + b'            break\n')
        with self.assertRaisesRegex(ValueError, 'BUSINESS_PHASE_LOOP_CHANGED'):
            builder.validate_business_invariants(self.baseline, files)

    def test_reject_wrong_fixture_flag_and_half_zero_identities(self):
        with self.assertRaisesRegex(ValueError, 'FIXTURE_FLAG'):
            self.compile_fixture(fixture_source=1)
        for field in ('source_commit', 'source_tree'):
            args = {'source_commit': self.old_manifest['kit_source_commit'],
                    'source_tree': self.old_manifest['kit_source_tree'], 'fixture_source': False}
            args[field] = '0' * 40
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'SOURCE_IDENTITY_UNPUBLISHED'):
                self.compile_fixture(**args)

    def test_reject_nonfinite_json(self):
        for value in (b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'NONFINITE_JSON'):
                builder.strict_json(value)

    def test_reject_overlay_structure_even_with_explicit_test_pin(self):
        # The temporary digest override is confined to these malformed-map tests;
        # production code never bypasses the frozen map pin.
        for mutation, expected in (('scope', 'OVERLAY_MAP_SCOPE'),
                                   ('missing', 'OVERLAY_ROW_COUNT'),
                                   ('duplicate', 'OVERLAY_TARGET_CLOSURE'),
                                   ('path', 'UNSAFE_RELATIVE_PATH'),
                                   ('source', 'OVERLAY_SOURCE_PATH'),
                                   ('size', 'OVERLAY_SIZE'),
                                   ('hash', 'OVERLAY_HASH_SHAPE'),
                                   ('baseline', 'OVERLAY_BASELINE_HASH')):
            mapping = json.loads(self.map_raw.decode())
            row = mapping['files'][0]
            if mutation == 'scope': mapping['compiler_root_leaf'] = 'wrong-root'
            elif mutation == 'missing': mapping['files'].pop()
            elif mutation == 'duplicate': mapping['files'][-1] = dict(row)
            elif mutation == 'path': row['source'] = '../escape.py'
            elif mutation == 'source': row['source'] = 'kit-overlay/not-the-target.py'
            elif mutation == 'size': row['bytes'] = True
            elif mutation == 'hash': row['git_blob_sha1'] = 'g' * 40
            else: row['baseline_sha256'] = None
            raw = builder.canonical(mapping)
            with self.subTest(mutation=mutation), mock.patch.object(builder, 'OVERLAY_MAP_SHA256', builder.sha(raw)):
                with self.assertRaisesRegex(ValueError, expected):
                    builder.authenticate_map(raw)

    def test_reject_overlay_git_blob_or_baseline_pin(self):
        for field, expected, length in (('git_blob_sha1', 'OVERLAY_GIT_BLOB_PIN', 40),
                                        ('baseline_sha256', 'OVERLAY_BASELINE_PIN', 64)):
            mapping = json.loads(self.map_raw.decode())
            mapping['files'][0][field] = '0' * length
            raw = builder.canonical(mapping)
            with self.subTest(field=field), mock.patch.object(builder, 'OVERLAY_MAP_SHA256', builder.sha(raw)):
                with self.assertRaisesRegex(ValueError, expected):
                    self.compile_fixture(map_raw=raw)

    def test_cli_success_uses_actual_disposable_git_commit_and_tree(self):
        # A real local Git fixture supplies exact nonzero identities. It is never
        # presented as a published candidate and is removed after the assertion.
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            root = Path(tmp)
            repository = root / 'source'
            (repository / 'build').mkdir(parents=True)
            builder_path = repository / 'build/build_claim_successor_kit.py'
            builder_path.write_bytes((HERE / 'build_claim_successor_kit.py').read_bytes())
            (repository / 'build/OVERLAY_INPUTS.json').write_bytes(self.map_raw)
            for source, body in self.sources.items():
                target = repository / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            def git(*args):
                result = subprocess.run(['git', '-C', str(repository)] + list(args),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                return result.stdout.decode().strip()
            git('init', '--quiet')
            git('add', '.')
            git('-c', 'user.name=Offline Builder Test', '-c', 'user.email=offline@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Exact local compiler fixture')
            commit, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
            self.assertNotEqual(commit, '0' * 40)
            self.assertNotEqual(tree, '0' * 40)
            output, metadata = root / 'compiled.tar.gz', root / 'compiled.json'
            command = [sys.executable, '-I', '-S', '-B', str(builder_path),
                '--archive', str(baseline_path()), '--source-commit', commit, '--source-tree', tree,
                '--output', str(output), '--metadata', str(metadata)]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            observed = json.loads(metadata.read_text())
            expected_raw, expected_meta = self.compile_fixture(source_commit=commit, source_tree=tree, fixture_source=False)
            self.assertEqual(output.read_bytes(), expected_raw)
            self.assertEqual(observed, expected_meta)
            self.assertEqual(observed['source_identity'],
                'CALLER_SUPPLIED_PUBLICATION_IDENTITY_EXTERNAL_VERIFICATION_REQUIRED')
            self.assertEqual(observed['output']['source_commit'], commit)
            self.assertEqual(observed['output']['source_tree'], tree)
            self.assertFalse(observed['production_resume_authorized'])
            self.assertEqual(json.loads(result.stdout.decode())['archive_sha256'], builder.sha(expected_raw))
            again = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.assertNotEqual(again.returncode, 0)
            self.assertIn(b'OUTPUT_ALREADY_EXISTS', again.stderr)
            self.assertEqual(output.read_bytes(), expected_raw)
            self.assertEqual(metadata.read_bytes(), builder.canonical(expected_meta))

    def test_cli_refuses_collision_before_any_output(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as tmp:
            output = Path(tmp) / 'same-path'
            result = subprocess.run([sys.executable, '-I', '-S', '-B',
                str(HERE / 'build_claim_successor_kit.py'), '--archive', str(baseline_path()),
                '--source-commit', self.old_manifest['kit_source_commit'],
                '--source-tree', self.old_manifest['kit_source_tree'],
                '--output', str(output), '--metadata', str(output)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'OUTPUT_PATH_COLLISION', result.stderr)
            self.assertFalse(output.exists())

    def test_cli_has_no_fixture_identity_escape_hatch(self):
        result = subprocess.run([sys.executable, '-I', '-S', '-B',
            str(HERE / 'build_claim_successor_kit.py'), '--help'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(b'--fixture', result.stdout)
        self.assertIn(b'--source-commit', result.stdout)
        self.assertIn(b'--source-tree', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
