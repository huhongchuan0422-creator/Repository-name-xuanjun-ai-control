from __future__ import print_function

import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
APP = os.path.join(ROOT, 'scripts', 'task_center_app.py')
CLI = os.path.join(ROOT, 'scripts', 'reusable_scheduler_cli.py')
KEY = '0123456789abcdef0123456789abcdef'


class AuthorityKeyFileTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, 'state.sqlite3')
        self.key_file = os.path.join(self.root, 'authority.key')
        with open(self.key_file, 'w') as stream:
            stream.write(KEY + '\n')
        os.chmod(self.key_file, 0o600)

    def tearDown(self):
        shutil.rmtree(self.root)

    def command(self, entry, key_arguments):
        if entry == 'app':
            return [sys.executable, APP, '--db', self.db] + key_arguments + [
                '--tenant', 'tenant-key-file', '--port', '0']
        return [sys.executable, CLI, '--db', self.db] + key_arguments + [
            'project', '--tenant', 'tenant-key-file']

    def run_rejected(self, entry, key_arguments, marker):
        result = subprocess.run(self.command(entry, key_arguments), cwd=ROOT,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn(marker, combined)
        self.assertNotIn(KEY, combined)

    def test_cli_accepts_secure_key_file_and_does_not_put_key_in_argv(self):
        result = subprocess.run(self.command(
            'cli', ['--test-authority-key-file', self.key_file]), cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(KEY, ' '.join(self.command(
            'cli', ['--test-authority-key-file', self.key_file])))

    def test_both_entrypoints_reject_argument_conflict(self):
        for entry in ('app', 'cli'):
            self.run_rejected(entry, ['--test-authority-key', KEY,
                '--test-authority-key-file', self.key_file],
                'not allowed with argument')

    def test_both_entrypoints_reject_wrong_mode(self):
        os.chmod(self.key_file, 0o640)
        for entry in ('app', 'cli'):
            self.run_rejected(entry,
                ['--test-authority-key-file', self.key_file],
                'TEST_AUTHORITY_KEY_FILE_MODE_0600_REQUIRED')

    def test_both_entrypoints_reject_symbolic_link(self):
        link = os.path.join(self.root, 'authority-link.key')
        os.symlink(self.key_file, link)
        for entry in ('app', 'cli'):
            self.run_rejected(entry, ['--test-authority-key-file', link],
                              'OWNED_REGULAR_TEST_AUTHORITY_KEY_FILE_REQUIRED')


if __name__ == '__main__':
    unittest.main()
