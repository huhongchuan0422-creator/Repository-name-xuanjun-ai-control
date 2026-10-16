"""Real immutable archive + exact overlays; zero identities are fixture-only.

No production archive, host observation, host installation or resume is produced.
"""
import copy
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('parentfix_builder', str(HERE / 'build_parentfix_kit.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def baseline_path():
    relative = 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz'
    candidates = [Path(os.environ['PARENTFIX_BASELINE_ARCHIVE'])] if os.environ.get('PARENTFIX_BASELINE_ARCHIVE') else [ROOT.parent / relative, ROOT.parent / 'baseline' / relative]
    for path in candidates:
        if path.is_file():
            return path
    raise ValueError('Exact baseline archive missing; set PARENTFIX_BASELINE_ARCHIVE')


def read_output(raw):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive.getmembers():
            if member.isreg():
                files[member.name.split('/', 1)[1]] = archive.extractfile(member).read()
    return files


class BuildParentfixTests(unittest.TestCase):
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
        self.assertEqual(len(self.baseline), 253)
        self.assertEqual(builder.sha(self.baseline[builder.MANIFEST]), builder.MANIFEST_SHA256)
        mapping = builder.authenticate_map(self.map_raw)
        self.assertEqual(len(mapping['files']), 9)
        self.assertEqual(mapping['original_overlay_map_sha256'], builder.ORIGINAL_MAP_SHA256)
        self.assertFalse(any(row['source'].startswith('/') for row in mapping['files']))

    def test_actual_archive_positive_exact_file_closure(self):
        self.assertEqual(len(self.files), 254)
        self.assertEqual(len(self.manifest['files']), 253)
        self.assertEqual(set(self.files), set(self.manifest['files']) | {builder.MANIFEST})
        for name, pin in self.manifest['files'].items():
            self.assertEqual(builder.sha(self.files[name]), pin, name)
        self.assertEqual(set(self.files) - set(self.baseline), {builder.NEW_TEST})
        changed = {name for name in self.baseline if self.baseline[name] != self.files[name]}
        self.assertEqual(changed, (set(builder.OVERLAY_SOURCES) - {builder.NEW_TEST}) | {builder.MANIFEST})

    def test_runtime_107_and_all_110_package_files_preserved(self):
        names = [name for name in self.baseline if name.startswith(builder.RUNTIME)]
        self.assertEqual(len(names), 110)
        for name in names:
            self.assertEqual(self.files[name], self.baseline[name], name)
        runtime = json.loads(self.files[builder.RUNTIME + 'deploy/integration-manifest.json'].decode())
        self.assertEqual(len(runtime['files']), 107)
        for name, pin in runtime['files'].items():
            self.assertEqual(builder.sha(self.files[builder.RUNTIME + name]), pin)

    def test_manifest_policy_and_modules_unchanged(self):
        for key in self.old_manifest:
            if key not in ('files', 'kit_source_commit', 'kit_source_tree', 'test_suites'):
                self.assertEqual(self.manifest[key], self.old_manifest[key], key)
        expected = copy.deepcopy(self.old_manifest['test_suites'])
        expected['host_factory']['tests'].append(builder.NEW_TEST)
        expected['host_factory']['imports']['test_fresh_release_parent'] = builder.NEW_TEST
        self.assertEqual(self.manifest['test_suites'], expected)

    def test_canonical_manifest_and_fixture_provenance(self):
        self.assertEqual(self.files[builder.MANIFEST], builder.canonical(self.manifest))
        self.assertEqual(self.metadata['source_identity'], 'SYNTHETIC_TEST_FIXTURE_NOT_PUBLISHED')
        self.assertFalse(self.metadata['production_resume_authorized'])
        self.assertEqual(self.metadata['output']['source_commit'], '0' * 40)
        self.assertEqual(self.metadata['baseline']['source_commit'], self.old_manifest['kit_source_commit'])
        self.assertEqual(len(self.metadata['unchanged_files']), 244)
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
            self.assertEqual(len(members), 296)
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'existing'
            output.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                builder.write_new(output, b'changed')
            self.assertEqual(output.read_bytes(), b'original')
            (root / 'alias').symlink_to(output)
            with self.assertRaisesRegex(ValueError, 'INPUT_PATH_SYMLINK'):
                builder.read_regular(root / 'alias', 100)

    def test_authenticated_cached_sources_new_test_discovery(self):
        # Exercise actual strict loader imports, not sys.path-based test loading.
        # The zero-ID archive is an explicit fixture, never a production identity.
        script = r'''
import hashlib, importlib, importlib.util, json, pathlib, sys, unittest
root = pathlib.Path(sys.argv[1])
raw = (root / 'recovery-kit-manifest.json').read_bytes()
manifest = json.loads(raw.decode())
cache = {name: (root / name).read_bytes() for name in manifest['files']}
assert all(hashlib.sha256(cache[name]).hexdigest() == pin for name, pin in manifest['files'].items())
spec = importlib.util.spec_from_file_location('fixture_entry', str(root / 'epoch7_recovery_entry.py'))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
entry.validate_manifest(manifest)
entry.validate_runtime(manifest, cache)
kit = entry.VerifiedKit(str(root), manifest, cache, hashlib.sha256(raw).hexdigest(), raw_manifest=raw)
with kit.imports(manifest['test_suites']['host_factory']['imports']) as loader:
    test = importlib.import_module('test_fresh_release_parent')
    assert test.__loader__ is loader
    assert unittest.defaultTestLoader.loadTestsFromModule(test).countTestCases() == 23
    assert 'test_fresh_release_parent' in loader.loaded
print('AUTHENTICATED_CACHED_SOURCES_DISCOVERY_23_PASS; TEST_BODIES_NOT_RUN')
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / builder.OUTPUT_ROOT
            for name, body in self.files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', script, str(root)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertIn(b'AUTHENTICATED_CACHED_SOURCES_DISCOVERY_23_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
