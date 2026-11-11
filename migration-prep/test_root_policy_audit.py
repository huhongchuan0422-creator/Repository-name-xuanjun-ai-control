import unittest
from root_policy_audit import parsed_sources, effective_policy, HELPER

class PolicyTests(unittest.TestCase):
    def test_all_parsed_sources(self):
        self.assertEqual(parsed_sources("/etc/sudoers: parsed OK\n/etc/sudoers.d/xj: parsed OK"), ["/etc/sudoers", "/etc/sudoers.d/xj"])
    def test_sources_missing_or_ambiguous(self):
        for value in ("", "/tmp/x: parsed OK", "/etc/sudoers: parsed OK\nWARNING", "/etc/sudoers: parsed OK\n/etc/sudoers: parsed OK"):
            with self.assertRaises(ValueError):
                parsed_sources(value)
    def test_fixed_grant(self):
        self.assertEqual(effective_policy('Defaults env_reset, secure_path=/usr/bin\n(root) NOPASSWD: ' + HELPER + ' ""'), "FIXED_HELPER_ONLY")
    def test_broad_or_multiple_grants(self):
        for grant in ('(ALL) NOPASSWD: ALL', '(root) NOPASSWD: ' + HELPER, '(root) NOPASSWD: ' + HELPER + ' ""\n(root) NOPASSWD: /bin/bash'):
            with self.assertRaises(ValueError):
                effective_policy("env_reset,\n" + grant)
    def test_dangerous_environment(self):
        for defaults in ("!env_reset,", "env_reset, SETENV:", "env_reset, env_keep=BASH_ENV", "env_reset, env_keep=LD_PRELOAD"):
            with self.assertRaises(ValueError):
                effective_policy(defaults + '\n(root) NOPASSWD: ' + HELPER + ' ""')


class DescriptorTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        from unittest.mock import patch
        self.os = os
        self.temp = tempfile.TemporaryDirectory()
        self.base = self.temp.name
        original = os.open
        def redirected(path, flags, **kwargs):
            return original(self.base if path == '/' else path, flags, **kwargs)
        self.patch = patch('root_policy_audit.os.open', side_effect=redirected)
        self.patch.start()
    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()
    def test_regular_file_digest(self):
        import hashlib
        from root_policy_audit import protected_digest
        with open(self.base + '/policy', 'wb') as out:
            out.write(b'policy')
        self.assertEqual(protected_digest('/policy', self.os.getuid()), hashlib.sha256(b'policy').hexdigest())
    def test_symlink_and_writable_file_rejected(self):
        from root_policy_audit import protected_digest
        with open(self.base + '/policy', 'w') as out:
            out.write('policy')
        self.os.symlink('policy', self.base + '/link')
        with self.assertRaises(OSError):
            protected_digest('/link', self.os.getuid())
        self.os.chmod(self.base + '/policy', 0o666)
        with self.assertRaises(ValueError):
            protected_digest('/policy', self.os.getuid())
    def test_symlink_parent_and_writable_parent_rejected(self):
        from root_policy_audit import protected_digest
        self.os.mkdir(self.base + '/dir')
        with open(self.base + '/dir/policy', 'w') as out:
            out.write('policy')
        self.os.symlink('dir', self.base + '/link')
        with self.assertRaises(OSError):
            protected_digest('/link/policy', self.os.getuid())
        self.os.chmod(self.base + '/dir', 0o777)
        with self.assertRaises(ValueError):
            protected_digest('/dir/policy', self.os.getuid())
    def test_invalid_paths_and_wrong_owner(self):
        from root_policy_audit import protected_digest
        for path in ('relative', '/a/../b', '/a//b', '/'):
            with self.assertRaises(ValueError):
                protected_digest(path, self.os.getuid())
        with self.assertRaises(ValueError):
            protected_digest('/missing', self.os.getuid() + 1)

class CommandTests(unittest.TestCase):
    def test_failure_and_timeout_rejected(self):
        from unittest.mock import patch
        import subprocess
        from root_policy_audit import run
        with patch('root_policy_audit.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'private')):
            with self.assertRaises(ValueError):
                run(['/usr/bin/false'])
        with patch('root_policy_audit.subprocess.run', side_effect=subprocess.TimeoutExpired('private', 20)):
            with self.assertRaises(subprocess.TimeoutExpired):
                run(['/usr/bin/false'])

if __name__ == "__main__":
    unittest.main()
