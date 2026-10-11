"""No root effects/network. Hash/policy/token and fixed install plan tests."""
import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('uk_bootstrap', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'uk-dev-bootstrap.py'))
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


class BootstrapTest(unittest.TestCase):
    def test_actual_dashboard_manifest_hashes(self):
        for name, digest in b.MANIFEST.items():
            with open(os.path.join(os.path.dirname(__file__), name), 'rb') as stream:
                self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), digest)
    def test_unpinned_commit_rejected_before_source_reads(self):
        with self.assertRaises(ValueError):
            b.build_plan('REVIEWER_MUST_PIN_COMMIT', {0})
    def test_fixed_plan_dry_run_has_no_effects_or_general_sudo(self):
        with patch.object(b, 'source_bytes', return_value=b'checked') as read:
            plan = b.build_plan('a' * 40, {0, 123})
        self.assertEqual(read.call_count, 2)
        self.assertIn(b'xuanjun-uk-owner-audit ""', plan['sudoers'])
        self.assertNotIn(b'ALL\n', plan['sudoers'])
        self.assertIn(b'User=xuanjun_dev', plan['unit'])
        self.assertIn(b'--port 18556', plan['unit'])
        self.assertIn(b'ProtectSystem=full', plan['unit'])
        self.assertNotIn(b'ExecStartPre=', plan['unit'])
    def test_symlink_and_wrong_hash_sources_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            name = os.path.join(temp, 'source')
            with open(name, 'wb') as stream:
                stream.write(b'content')
            digest = hashlib.sha256(b'content').hexdigest()
            self.assertEqual(b.source_bytes(name, {0, os.getuid()}, digest), b'content')
            with self.assertRaises(ValueError):
                b.source_bytes(name, {0, os.getuid()}, '0' * 64)
            os.symlink(name, os.path.join(temp, 'link'))
            with self.assertRaises(ValueError):
                b.source_bytes(os.path.join(temp, 'link'), {0, os.getuid()}, digest)
    def test_existing_token_is_preserved_and_never_returned(self):
        with tempfile.TemporaryDirectory() as temp:
            token = os.path.join(temp, 'token')
            with open(token, 'w') as stream:
                stream.write('a' * 48)
            os.chmod(token, 0o600)
            self.assertIsNone(b.ensure_token(token, os.getuid(), os.getgid()))
            with open(token) as stream:
                self.assertEqual(stream.read(), 'a' * 48)
            os.chmod(token, 0o644)
            with self.assertRaises(ValueError):
                b.ensure_token(token, os.getuid(), os.getgid())
    def test_audit_source_compiles_and_has_no_inference(self):
        compile(b.AUDIT_PROGRAM, '<audit>', 'exec')
        self.assertIn("('models',['models','--help'])", b.AUDIT_PROGRAM)
        self.assertNotIn('ProxyCommand', b.AUDIT_PROGRAM)
        self.assertNotIn('agent --', b.AUDIT_PROGRAM)
        self.assertNotIn('codex exec', b.AUDIT_PROGRAM)
        self.assertIn('xj-uk-domestic-customer-tunnel.service', b.AUDIT_PROGRAM)
        self.assertIn('xj-uk-owner-notify.timer', b.AUDIT_PROGRAM)
    def test_main_wrong_host_fails_without_mutation(self):
        with patch.object(b.socket, 'gethostname', return_value='wrong-host'), patch.object(b.os, 'geteuid', return_value=0), patch.object(b, 'build_plan') as plan:
            with self.assertRaises(SystemExit):
                b.main()
            plan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
