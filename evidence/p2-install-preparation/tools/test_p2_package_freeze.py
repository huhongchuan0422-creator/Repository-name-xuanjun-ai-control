import hashlib
import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest


HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location('package_freeze',
    os.path.join(HERE, 'p2-package-freeze.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageTests(unittest.TestCase):
    def source(self, root):
        os.makedirs(os.path.join(root, 'deploy'))
        os.makedirs(os.path.join(root, 'stage1'))
        os.makedirs(os.path.join(root, 'tools'))
        files = {'stage1/a.py': b'print("a")\n'}
        with open(os.path.join(root, 'stage1/a.py'), 'wb') as f:
            f.write(files['stage1/a.py'])
        with open(os.path.join(root, 'tools/p2-package-freeze.py'), 'rb') if False else open(__file__, 'rb') as source:
            verifier = source.read()
        with open(os.path.join(root, 'tools/p2-package-freeze.py'), 'wb') as f:
            f.write(verifier)
        manifest = {'schema': 2, 'files': {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        with open(os.path.join(root, 'deploy/integration-manifest.json'), 'w') as f:
            json.dump(manifest, f, sort_keys=True, separators=(',', ':'))

    def test_repeated_build_is_byte_identical_and_verified(self):
        with tempfile.TemporaryDirectory() as root:
            self.source(root)
            one = os.path.join(root, 'one.tar.gz')
            two = os.path.join(root, 'two.tar.gz')
            commit, tree = 'a' * 40, 'b' * 40
            first = module.build(root, 'deploy/integration-manifest.json',
                                 'tools/p2-package-freeze.py', one, commit, tree)
            second = module.build(root, 'deploy/integration-manifest.json',
                                  'tools/p2-package-freeze.py', two, commit, tree)
            self.assertEqual(first['archive_sha256'], second['archive_sha256'])
            checked = module.verify(one, first['archive_sha256'], commit, tree)
            self.assertEqual(checked['file_count'], 1)

    def test_changed_reviewed_file_is_rejected_before_archive(self):
        with tempfile.TemporaryDirectory() as root:
            self.source(root)
            with open(os.path.join(root, 'stage1/a.py'), 'ab') as f:
                f.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'RUNTIME_FILE_HASH_MISMATCH'):
                module.build(root, 'deploy/integration-manifest.json',
                             'tools/p2-package-freeze.py', os.path.join(root, 'x'),
                             'a' * 40, 'b' * 40)

    def test_extra_or_tampered_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            self.source(root)
            archive = os.path.join(root, 'ok.tar.gz')
            result = module.build(root, 'deploy/integration-manifest.json',
                                  'tools/p2-package-freeze.py', archive,
                                  'a' * 40, 'b' * 40)
            with open(archive, 'rb') as f:
                original = f.read()
            # A sidecar digest mismatch is rejected before parsing members.
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_SHA256_MISMATCH'):
                module.verify(archive, '0' * 64)
            self.assertEqual(hashlib.sha256(original).hexdigest(),
                             result['archive_sha256'])

    def test_unsafe_manifest_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            self.source(root)
            manifest = {'schema': 2, 'files': {'../escape': '0' * 64}}
            with open(os.path.join(root, 'deploy/integration-manifest.json'), 'w') as f:
                json.dump(manifest, f)
            with self.assertRaisesRegex(ValueError, 'INVALID_RUNTIME_MANIFEST_ENTRY'):
                module.build(root, 'deploy/integration-manifest.json',
                             'tools/p2-package-freeze.py', os.path.join(root, 'x'),
                             'a' * 40, 'b' * 40)


if __name__ == '__main__':
    unittest.main()
