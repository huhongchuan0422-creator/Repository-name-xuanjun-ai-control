#!/usr/bin/env python3
"""Offline pin-only regression. No host reads, extraction or candidate imports.

The initial published preparer is recovered only by reversing the two exact
binding literals, then authenticated against its fixed byte count and SHA-256.
This does not require a sibling baseline, Git history or network access.
EPOCH7_PREP_TEST_KIT_ROOT supplies the preserved original A evidence kit.
EPOCH7_COMPILER_TEST_ARCHIVE supplies the selected published resourcebind archive.
Only authenticated entry bytes are loaded in memory; host entrypoints never run.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import types
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OLD_KIT = Path(os.environ.get('EPOCH7_PREP_TEST_KIT_ROOT', str(ROOT.parent/'kit'/'epoch7-recovery-candidate-r7')))
ARCHIVE = Path(os.environ.get('EPOCH7_COMPILER_TEST_ARCHIVE', str(ROOT/'artifact'/'epoch7-kit-resourcebind.tar.gz')))
MANIFEST_SHA = '6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
ENTRY_SHA = '071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5'
OLD_WRAPPER_SHA = '0320bf16a5059e3a1b73a120e316b264543f55740779d38df945324d422867dc'
BOUND_WRAPPER_SHA = '18d3c459bc14f4a3c00317c5a407d18178059209830763564dced41d9af945fd'
SOURCE_COMMIT = 'ef21ca95331769622c294c65bb60ec7ceed0c392'
SOURCE_TREE = '5a70c5627afe75fcd475c20e71ee9bfb0b6a156d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module(raw, name, path):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


class CompilerBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bound = (HERE/'epoch7_prepare.py').read_bytes()
        cls.original = cls.bound
        for name, pin in (('COMPILER_KIT_SHA', MANIFEST_SHA), ('COMPILER_ENTRY_SHA', ENTRY_SHA)):
            literal = (name+' = '+repr(pin)).encode('ascii')
            if cls.original.count(literal) != 1:
                raise ValueError('TEST_EXACT_BINDING_LITERAL')
            cls.original = cls.original.replace(literal, (name+' = None').encode('ascii'))
        if (len(cls.original) != 55709 or sha(cls.original) != OLD_WRAPPER_SHA or
                sha(cls.bound) != BOUND_WRAPPER_SHA):
            raise ValueError('TEST_WRAPPER_PIN')
        cls.p = module(cls.bound, 'bound_preparer_pin_test', HERE/'epoch7_prepare.py')
        raw = ARCHIVE.read_bytes()
        if len(raw) != 1056853 or sha(raw) != '6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e':
            raise ValueError('TEST_ARCHIVE_PIN')
        prefix = 'epoch7-recovery-candidate-r7-resourcebind/'
        cls.files = {}
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            members = archive.getmembers()
            if len(members) != 298:
                raise ValueError('TEST_ARCHIVE_COUNT')
            for item in members:
                if item.name in seen or item.pax_headers or item.linkname:
                    raise ValueError('TEST_ARCHIVE_MEMBER')
                seen.add(item.name)
                if item.name != prefix[:-1] and not item.name.startswith(prefix):
                    raise ValueError('TEST_ARCHIVE_ROOT')
                if item.isdir():
                    continue
                if not item.isreg() or not 0 < item.size <= 16*1024*1024:
                    raise ValueError('TEST_ARCHIVE_TYPE')
                name = item.name[len(prefix):]
                if any(part in ('', '.', '..') for part in name.split('/')):
                    raise ValueError('TEST_ARCHIVE_PATH')
                with archive.extractfile(item) as stream:
                    body = stream.read(item.size+1)
                if len(body) != item.size:
                    raise ValueError('TEST_ARCHIVE_SIZE')
                cls.files[name] = body
        cls.manifest_raw = cls.files.pop('recovery-kit-manifest.json')
        if sha(cls.manifest_raw) != MANIFEST_SHA:
            raise ValueError('TEST_MANIFEST_PIN')
        cls.manifest = json.loads(cls.manifest_raw.decode('ascii'))
        if len(cls.files) != 255 or set(cls.files) != set(cls.manifest['files']):
            raise ValueError('TEST_ARCHIVE_CLOSURE')
        for name, pin in cls.manifest['files'].items():
            if sha(cls.files[name]) != pin:
                raise ValueError('TEST_ARCHIVE_FILE_PIN')
        cls.entry = cls.p.load_entry(cls.files['epoch7_recovery_entry.py'], compiler=True)
        old_raw = (OLD_KIT/'recovery-kit-manifest.json').read_bytes()
        if sha(old_raw) != cls.p.KIT_SHA:
            raise ValueError('TEST_ORIGINAL_MANIFEST_PIN')
        cls.old_manifest = json.loads(old_raw.decode('ascii'))

    def test_only_two_literal_assignments_changed(self):
        expected = self.original
        for name, pin in (('COMPILER_KIT_SHA', MANIFEST_SHA), ('COMPILER_ENTRY_SHA', ENTRY_SHA)):
            old = (name+' = None').encode('ascii')
            self.assertEqual(expected.count(old), 1)
            literal = (name+' = '+repr(pin)).encode('ascii')
            self.assertEqual(self.bound.count(literal), 1)
            expected = expected.replace(old, literal)
        self.assertEqual(self.bound, expected)
        self.assertEqual(len(self.bound), 55833)

    def test_both_pure_dependencies_unchanged(self):
        self.assertEqual(self.p.PREPARATION_SOURCES, {
            'epoch7_prepare_data': '71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1',
            'epoch7_topology_projection': '0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6'})
        for name, pin in self.p.PREPARATION_SOURCES.items():
            raw = (HERE/(name+'.py')).read_bytes()
            self.assertEqual(sha(raw), pin)

    def test_saved_a_provenance_is_separate(self):
        self.p.require_binding()
        self.p.require_compiler_binding()
        self.assertEqual(self.p.KIT_SHA, '7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4')
        self.assertEqual(self.p.ENTRY_SHA, '1be06802e012b5747f837af02ff8746fec9864ef94715b561f67c39be95e0948')
        self.assertEqual(self.p.SAVED_PROJECTION_MANIFEST_SHA, '311c5150f628c0232298bc62d233d2eccf26681d1d0fdfa379b4cab8d242f1d3')
        self.assertEqual(self.p.EXPECTED_REVIEW_BODY_SHA, '37ee583dfda581361caf38e8cccf5ffb9b25f28c8f732e17e0cbf6e72982c9b7')
        self.assertEqual(self.p.OBSERVATION_SHA, 'a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68')
        self.assertEqual(self.p.KIT_ROOT, self.p.CAND+'/epoch7-recovery-candidate-r7')
        self.assertEqual(self.p.COMPILER_KIT_ROOT, self.p.CAND+'/epoch7-recovery-candidate-r7-resourcebind')
        self.assertEqual(self.p.PREP_ROOT, self.p.CAND+'/epoch7-preparation-candidate-r7-resourcebind')
        self.assertNotEqual(self.p.KIT_SHA, self.p.COMPILER_KIT_SHA)

    def test_actual_manifest_and_runtime_pass_original_pure_validators(self):
        value = self.entry.validate_manifest(self.entry.decode(self.manifest_raw))
        runtime = self.entry.validate_runtime(value, self.files)
        self.assertEqual(len(runtime['files']), 107)
        self.assertEqual(value['kit_source_commit'], SOURCE_COMMIT)
        self.assertEqual(value['kit_source_tree'], SOURCE_TREE)

    def test_all_110_runtime_package_files_equal_original_a(self):
        names = {name for name in self.files if name.startswith('xuanjun-p2-package/')}
        self.assertEqual(len(names), 110)
        self.assertEqual(names, {name for name in self.old_manifest['files'] if name.startswith('xuanjun-p2-package/')})
        for name in names:
            original = (OLD_KIT/name).read_bytes()
            self.assertEqual(sha(original), self.old_manifest['files'][name])
            self.assertEqual(self.files[name], original)
        self.assertEqual(self.manifest['runtime_manifest_sha256'], self.old_manifest['runtime_manifest_sha256'])

    def test_actual_entry_binds_new_root_and_digest_without_admission(self):
        self.assertEqual(sha(self.files['epoch7_recovery_entry.py']), ENTRY_SHA)
        self.assertEqual(self.entry.__file__, self.p.COMPILER_KIT_ROOT+'/epoch7_recovery_entry.py')
        kit = self.entry.VerifiedKit(self.p.COMPILER_KIT_ROOT, self.manifest, self.files, MANIFEST_SHA, raw_manifest=self.manifest_raw)
        report = kit.report()
        self.assertEqual(report['kit_manifest_sha256'], MANIFEST_SHA)
        self.assertEqual(report['verified_files'], 255)
        self.assertEqual(report['install_admission'], 'NOT_GRANTED')
        self.assertIn('fresh_release_parent', self.entry.PRIVATE_SEED_FIELDS)

    def test_original_entry_cannot_be_loaded_as_compiler(self):
        raw = (OLD_KIT/'epoch7_recovery_entry.py').read_bytes()
        self.assertEqual(sha(raw), self.p.ENTRY_SHA)
        with self.assertRaisesRegex(ValueError, '^EPOCH7_PREP_ENTRY_PIN$'):
            self.p.load_entry(raw, compiler=True)

    def test_compiler_entry_cannot_be_loaded_as_original_a(self):
        with self.assertRaisesRegex(ValueError, '^EPOCH7_PREP_ENTRY_PIN$'):
            self.p.load_entry(self.files['epoch7_recovery_entry.py'], compiler=False)

    def test_changed_entry_bytes_fail_before_execution(self):
        with self.assertRaisesRegex(ValueError, '^EPOCH7_PREP_ENTRY_PIN$'):
            self.p.load_entry(self.files['epoch7_recovery_entry.py']+b'\n', compiler=True)

    def test_missing_malformed_or_wrong_root_binding_refuses(self):
        for name, invalid in (('COMPILER_KIT_SHA', None), ('COMPILER_KIT_SHA', True),
                              ('COMPILER_ENTRY_SHA', ''), ('COMPILER_ENTRY_SHA', 'x'*64),
                              ('COMPILER_KIT_ROOT', self.p.KIT_ROOT)):
            before = getattr(self.p, name)
            try:
                setattr(self.p, name, invalid)
                with self.assertRaisesRegex(ValueError, '^EPOCH7_PREP_COMPILER_ARTIFACT_UNBOUND$'):
                    self.p.require_compiler_binding()
            finally:
                setattr(self.p, name, before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
