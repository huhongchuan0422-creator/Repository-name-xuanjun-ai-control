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

if __name__ == "__main__":
    unittest.main()
