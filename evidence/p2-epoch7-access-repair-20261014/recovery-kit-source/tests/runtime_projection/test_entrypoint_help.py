"""Inert frozen-installer help smoke checks under the running interpreter."""
import os
import subprocess
import sys
import unittest

# Staged-kit adapter: the authenticated runtime import identifies the script directory.
import owner_dashboard as staged_dashboard
BASE = os.path.dirname(staged_dashboard.__file__)


class EntrypointHelpTests(unittest.TestCase):
    def test_dashboard_help_is_inert_without_verifier(self):
        self.check_help('owner_dashboard.py', '--activation-descriptor')

    def test_root_broker_help_is_inert_without_verifier_or_root(self):
        self.check_help('root_broker.py', '--config')

    def check_help(self, name, expected):
        result = subprocess.run([sys.executable, '-B', os.path.join(BASE, name), '--help'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertLess(len(result.stdout), 8192)
        self.assertIn(expected.encode(), result.stdout)
        self.assertNotIn(b'AUTHENTICATED_SERVER_VERIFIER_REQUIRED', result.stdout)


if __name__ == '__main__': unittest.main()
