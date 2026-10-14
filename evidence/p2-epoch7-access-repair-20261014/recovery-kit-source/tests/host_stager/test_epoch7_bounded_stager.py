import os
import pathlib
import stat
import subprocess
import types
import unittest
from unittest import mock

import epoch7_bounded_stager as s
from epoch7_recovery_sequence import BoundedDiagnostics


class Runner(object):
    calls = []
    fail = False
    def __init__(self, contract, check, diagnostics):
        self.contract, self.check = contract, check
    def run(self, key):
        if self.fail: raise ValueError('BOUNDED_FAILURE')
        self.calls.append(self.contract[key])
        return subprocess.CompletedProcess(None, 0, b'bounded', b'')


class StagerTests(unittest.TestCase):
    def setUp(self):
        Runner.calls, Runner.fail = [], False
        self.diag = BoundedDiagnostics(lambda evidence: None)
        self.proxy = s.BoundedStagerSubprocess('/protected/package', '/usr/bin/python3',
            lambda: True, lambda exe: exe in ('/usr/bin/python3', '/usr/bin/git'), self.diag, Runner)
        self.stage = '/opt/xuanjun-control-releases/.integration-' + 'a' * 16
    def smoke(self, index=0):
        return self.proxy.run(['/usr/bin/python3', self.stage + '/' + s.SMOKES[index], '--help'],
            cwd=self.stage + '/stage1', stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=10, check=False)
    def test_all_six_commands_have_exact_bounded_contract(self):
        info = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_dev=1, st_ino=7)
        with mock.patch.object(s.os, 'lstat', return_value=info), mock.patch.object(s.os.path, 'realpath', side_effect=lambda p: p):
            for index in range(6): self.smoke(index)
        self.assertEqual(len(Runner.calls), 6)
        for row in Runner.calls:
            self.assertEqual((row['timeout'], row['accepted_returncodes'], row['operation']), (10, [0], 'stage_smoke_check'))
            self.assertEqual(row['env'], s.SMOKE_ENV)
    def test_out_of_order_or_wrong_argument_refused_before_spawn(self):
        with self.assertRaisesRegex(ValueError, 'FIXED_ORDER'): self.smoke(1)
        with self.assertRaisesRegex(ValueError, 'EXACT_ARGV'):
            self.proxy.run(['/bin/sh', '-c', 'true'], timeout=10, check=False)
        self.assertEqual(Runner.calls, [])
    def test_mismatched_option_refused_before_spawn(self):
        with self.assertRaisesRegex(ValueError, 'EXACT_CALL'):
            self.proxy.run(['/usr/bin/python3', self.stage + '/' + s.SMOKES[0], '--help'],
                cwd=self.stage + '/stage1', stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=60, check=False)
        self.assertEqual(Runner.calls, [])
    def test_failure_poisons_proxy_no_second_command(self):
        Runner.fail = True
        info = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_dev=1, st_ino=7)
        with mock.patch.object(s.os, 'lstat', return_value=info), mock.patch.object(s.os.path, 'realpath', side_effect=lambda p: p):
            with self.assertRaisesRegex(ValueError, 'BOUNDED_FAILURE'): self.smoke()
            with self.assertRaisesRegex(ValueError, 'NO_RETRY'): self.smoke(1)
    def test_source_git_query_pins_cwd_env_and_output(self):
        argv = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'rev-parse', 'HEAD', 'HEAD^{tree}', 'HEAD^']
        kwargs = {'cwd': '/protected/package', 'stdout': subprocess.PIPE, 'stderr': subprocess.DEVNULL,
                  'timeout': 10, 'check': False, 'env': s.GIT_ENV}
        self.proxy.run(argv, **kwargs)
        self.assertEqual(Runner.calls[0]['operation'], 'stage_source_verify')
        kwargs['cwd'] = '/tmp/unreviewed'
        with self.assertRaisesRegex(ValueError, 'GIT_EXACT'): self.proxy.run(argv, **kwargs)
    def test_helper_hash_and_namespace_isolation(self):
        import activation_control
        source = pathlib.Path(activation_control.__file__).resolve().parent.parent / 'scripts/uk-integration-install.py'
        raw = source.read_bytes()
        installer = s.FrozenBoundedInstaller(raw, '/protected/package', '/usr/bin/python3',
            lambda: True, lambda exe: True, self.diag, Runner)
        self.assertIs(installer.namespace['subprocess'], installer.proxy)
        self.assertIsNot(installer.namespace['subprocess'], subprocess)
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH'):
            s.FrozenBoundedInstaller(raw + b'\n', '/protected/package', '/usr/bin/python3',
                lambda: True, lambda exe: True, self.diag)
    def test_staging_replacement_refused_between_smokes(self):
        one = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_dev=1, st_ino=7)
        two = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0, st_dev=1, st_ino=8)
        with mock.patch.object(s.os.path, 'realpath', side_effect=lambda p: p):
            with mock.patch.object(s.os, 'lstat', return_value=one): self.smoke()
            with mock.patch.object(s.os, 'lstat', return_value=two):
                with self.assertRaisesRegex(ValueError, 'DIRECTORY_CHANGED'): self.smoke(1)

if __name__ == '__main__': unittest.main()
