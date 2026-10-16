#!/usr/bin/env python3
"""Offline pin-only regression. No host reads, extraction or candidate imports."""
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
ARCHIVE = Path(os.environ.get('EPOCH7_COMPILER_TEST_ARCHIVE', str(ROOT/'artifact'/'epoch7-kit-parentfix-dacd45a2.tar.gz')))
MANIFEST_SHA = 'b33b365ef1fd18458d85bcbbec44d883f3cc33bf859064cbdca6bfc3fad7d571'
ENTRY_SHA = '33e4ad415c9496feb72a9e151603dcb808714e84d9af0d60b39542d92e967180'
OLD_WRAPPER_SHA = '1c2f09c0e8b1c7397ce35fc72da9c199df564a2dc6c458eebc0fac7ba6ea9b69'
BOUND_WRAPPER_SHA = 'd32b55ab2164965b486dbe2d834281c5404d59fb454278e67ec32c306f34deb9'
SOURCE_COMMIT = 'dacd45a2f6888cae7b751cae5becacd3099c1ed2'
SOURCE_TREE = 'f31ae40b6f7c48f09846f6d70f5bb599f4980fe1'


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
        cls.original = (ROOT/'preparation'/'epoch7_prepare.py').read_bytes()
        cls.bound = (HERE/'epoch7_prepare.py').read_bytes()
        if sha(cls.original) != OLD_WRAPPER_SHA or sha(cls.bound) != BOUND_WRAPPER_SHA:
            raise ValueError('TEST_WRAPPER_PIN')
        cls.p = module(cls.bound, 'bound_preparer_pin_test', HERE/'epoch7_prepare.py')
        raw = ARCHIVE.read_bytes()
        if len(raw) != 1045651 or sha(raw) != '6553938a56b882e17d13029fa9a06787131bb55a5c55bc1138e2b825277b7307':
            raise ValueError('TEST_ARCHIVE_PIN')
        prefix = 'epoch7-recovery-candidate-r7-parentfix/'
        cls.files = {}
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            members = archive.getmembers()
            if len(members) != 296:
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
        if len(cls.files) != 253 or set(cls.files) != set(cls.manifest['files']):
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
            expected = expected.replace(old, (name+' = '+repr(pin)).encode('ascii'))
        self.assertEqual(self.bound, expected)
        self.assertEqual(len(self.bound), 55827)

    def test_both_pure_dependencies_unchanged(self):
        for name, pin in self.p.PREPARATION_SOURCES.items():
            raw = (HERE/(name+'.py')).read_bytes()
            self.assertEqual(raw, (ROOT/'preparation'/(name+'.py')).read_bytes())
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
        self.assertEqual(self.p.COMPILER_KIT_ROOT, self.p.CAND+'/epoch7-recovery-candidate-r7-parentfix')
        self.assertEqual(self.p.PREP_ROOT, self.p.CAND+'/epoch7-preparation-candidate-r7-fresh-parent')
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
        self.assertEqual(report['verified_files'], 253)
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
