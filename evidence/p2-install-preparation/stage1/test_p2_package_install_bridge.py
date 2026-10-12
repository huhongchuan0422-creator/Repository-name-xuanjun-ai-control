import hashlib
import importlib.util
import json
import os
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
PATH = os.path.join(ROOT, 'scripts', 'uk-integration-install.py')
SPEC = importlib.util.spec_from_file_location('package_install_bridge', PATH)
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class PackageInstallBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        os.mkdir(os.path.join(self.root, 'deploy'))
        os.mkdir(os.path.join(self.root, 'tools'))
        self.verifier = b'fixed verifier\n'
        with open(os.path.join(self.root, 'tools', 'p2-package-freeze.py'), 'wb') as stream:
            stream.write(self.verifier)
        self.manifest = {
            'schema': 2,
            'source_parent': '1' * 40,
            'files': {'stage1/example.py': 'a' * 64},
        }
        self.manifest_bytes = (json.dumps(self.manifest, sort_keys=True) + '\n').encode('utf-8')
        self.manifest_path = os.path.join(self.root, 'deploy', 'integration-manifest.json')
        with open(self.manifest_path, 'wb') as stream:
            stream.write(self.manifest_bytes)
        self.provenance = {
            'schema': 1,
            'source_repository': 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control',
            'source_commit': '2' * 40,
            'source_tree': '3' * 40,
            'runtime_manifest_path': 'deploy/integration-manifest.json',
            'runtime_manifest_sha256': hashlib.sha256(self.manifest_bytes).hexdigest(),
            'runtime_files': self.manifest['files'],
            'verifier_path': 'tools/p2-package-freeze.py',
            'verifier_sha256': hashlib.sha256(self.verifier).hexdigest(),
            'oauth_content_included': False,
            'tls_private_key_included': False,
            'new_paid_api_usage': 'NONE',
        }
        self.write_provenance()

    def write_provenance(self):
        with open(os.path.join(self.root, 'P2_PACKAGE_PROVENANCE.json'), 'w') as stream:
            json.dump(self.provenance, stream, sort_keys=True)

    def test_data_only_package_identity_is_bound_without_git_metadata(self):
        self.assertEqual(
            INSTALLER._artifact_identity(self.root, self.manifest_path,
                                         self.manifest_bytes, self.manifest),
            ('2' * 40, '3' * 40, '1' * 40))

    def test_provenance_drift_fails_closed(self):
        for key, value in (
                ('source_repository', 'other/repository'),
                ('runtime_manifest_sha256', '0' * 64),
                ('oauth_content_included', True),
                ('new_paid_api_usage', 'UNKNOWN')):
            original = self.provenance[key]
            self.provenance[key] = value
            self.write_provenance()
            with self.assertRaisesRegex(ValueError, 'PACKAGE_PROVENANCE_BINDING_MISMATCH'):
                INSTALLER._package_identity(self.root, self.manifest_path,
                                            self.manifest_bytes, self.manifest)
            self.provenance[key] = original

    def test_live_dashboard_renders_full_wake_contract(self):
        with open(os.path.join(ROOT, 'stage1', 'owner_dashboard.html')) as stream:
            html = stream.read()
        for token in ('wake_timeline', 'threshold_seconds', 'task_id', 'attempt',
                      'run_id', 'session_id', 'last_progress', 'checkpoint',
                      'result', 'error', 'next_check', '5/10/15'):
            self.assertIn(token, html)
        self.assertIn('@media(max-width:700px)', html)


if __name__ == '__main__':
    unittest.main()
