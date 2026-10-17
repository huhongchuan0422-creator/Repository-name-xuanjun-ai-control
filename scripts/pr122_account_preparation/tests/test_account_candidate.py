import copy
import importlib.util
from pathlib import Path
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('candidate', Path(__file__).parents[1] / 'account_candidate.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def fixture():
    dirs = set(c.DIRECTORIES) | {'/home', '/var', '/var/mail', '/var/spool', '/var/spool/mail'}
    def lookup(path):
        if path in c.ABSENT_PATHS:
            raise FileNotFoundError()
        mode = stat.S_IFDIR | 0o755 if path in dirs else stat.S_IFREG | 0o755
        return SimpleNamespace(st_uid=0, st_gid=0, st_mode=mode, st_nlink=1)
    return SimpleNamespace(host=c.HOST, uid=0, euid=0,
                           getpwnam=Mock(side_effect=KeyError()),
                           getgrnam=Mock(side_effect=KeyError()), lstat=Mock(side_effect=lookup))


class CandidateTests(unittest.TestCase):
    def setUp(self):
        # Accidental subprocess execution fails every test, including fixtures.
        self.patcher = patch('subprocess.Popen', side_effect=AssertionError('NO_PROCESS'))
        self.process = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.a = fixture()
        self.obs = c.collect_fixture(self.a)

    def test_favorable_fixture_still_hold(self):
        result = c.plan(self.obs)
        self.assertEqual([], result['precondition_failures'])
        self.assertFalse(result['execution_authorized'])
        self.assertTrue(result['missing_execution_inputs'])
        self.assertEqual('HOLD_PLAN_ONLY', result['state'])
        self.process.assert_not_called()

    def test_execution_always_denied_including_forged_approval(self):
        for value in ({}, self.obs, {'approved': True, 'binding': 'verified'}):
            with self.subTest(value=value), self.assertRaises(c.Denied):
                c.execute(value, approved=True)
        self.process.assert_not_called()

    def test_wrong_root_host_and_boolean_uid(self):
        for key, value in [('host', 'other'), ('uid', 1002), ('euid', 1002), ('uid', False)]:
            o = copy.deepcopy(self.obs); o[key] = value
            self.assertTrue(c.plan(o)['precondition_failures'])

    def test_account_group_partial_or_unknown(self):
        for key in ('account', 'group'):
            for value in ('PRESENT', 'UNKNOWN', None):
                o = copy.deepcopy(self.obs); o[key] = value
                self.assertTrue(c.plan(o)['precondition_failures'])

    def test_existing_home_and_spool_all_denied(self):
        for path in c.ABSENT_PATHS:
            o = copy.deepcopy(self.obs); o['paths'][path] = {'state': 'PRESENT'}
            self.assertTrue(c.plan(o)['precondition_failures'])

    def test_executable_symlink_writable_foreign_hardlinked_nonexec(self):
        for key, value in [('mode', stat.S_IFLNK | 0o777), ('mode', stat.S_IFREG | 0o777),
                           ('mode', stat.S_IFREG | 0o644), ('mode', stat.S_IFREG | 0o4755),
                           ('uid', 1002), ('gid', 1002), ('nlink', 2)]:
            o = copy.deepcopy(self.obs); o['paths']['/usr/sbin/useradd'][key] = value
            self.assertTrue(c.plan(o)['precondition_failures'])

    def test_directory_foreign_or_unknown(self):
        for path in c.DIRECTORIES:
            o = copy.deepcopy(self.obs); o['paths'][path] = {'state': 'UNKNOWN'}
            self.assertTrue(c.plan(o)['precondition_failures'])

    def test_no_symlink_parent_traversal(self):
        original = self.a.lstat.side_effect
        def altered(path):
            if path == '/usr':
                return SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFLNK | 0o777, st_nlink=1)
            return original(path)
        self.a.lstat.reset_mock(); self.a.lstat.side_effect = altered
        o = c.collect_fixture(self.a)
        called = [call.args[0] for call in self.a.lstat.call_args_list]
        self.assertNotIn('/usr/sbin', called)
        self.assertNotIn('/usr/sbin/useradd', called)
        self.assertEqual('UNKNOWN', o['paths']['/usr/sbin/useradd']['state'])

    def test_nss_exception_no_private_exception_or_row_output(self):
        self.a.getpwnam.side_effect = PermissionError('PRIVATE_SENTINEL')
        self.a.getgrnam.side_effect = None
        self.a.getgrnam.return_value = SimpleNamespace(gr_passwd='PRIVATE_SENTINEL')
        o = c.collect_fixture(self.a)
        self.assertEqual('UNKNOWN', o['account'])
        self.assertEqual('PRESENT', o['group'])
        self.assertNotIn('PRIVATE_SENTINEL', repr(o) + repr(c.plan(o)))

    def test_filesystem_denial_is_unknown(self):
        self.a.lstat.side_effect = PermissionError('PRIVATE_SENTINEL')
        o = c.collect_fixture(self.a)
        self.assertEqual('UNKNOWN', o['paths']['/']['state'])
        self.assertTrue(c.plan(o)['precondition_failures'])
        self.assertNotIn('PRIVATE_SENTINEL', repr(o))

    def test_command_fixed_no_sudo_home_or_password_argument(self):
        self.assertEqual(c.PROPOSED_ARGV[-1], 'xuanjun-customer')
        self.assertEqual(c.PROPOSED_ARGV[:4], ('/usr/sbin/useradd', '-r', '-U', '-M'))
        self.assertEqual('!', c.PROPOSED_ARGV[c.PROPOSED_ARGV.index('--password') + 1])
        self.assertNotIn('-F', c.PROPOSED_ARGV)
        self.assertNotIn('-G', c.PROPOSED_ARGV)
        self.assertNotIn('-K', c.PROPOSED_ARGV)

    def test_invalid_observations_fail_closed(self):
        for value in (None, [], {}, {'paths': None}):
            self.assertTrue(c.plan(value)['precondition_failures'])


if __name__ == '__main__':
    unittest.main()

class CreationCoreTests(unittest.TestCase):
    def setup_ops(self):
        from contextlib import nullcontext
        a = fixture()
        a.lock_existing = Mock(return_value=nullcontext())
        platform = {key: True for key in ('fixed_useradd_flags_supported', 'mail_spool_suppressed',
            'no_subid_allocation', 'no_account_creation_hooks', 'locked_password_explicit',
            'no_supplementary_group_defaults', 'no_privilege_policy_changes')}
        platform.update(uid_min=1, uid_max=999, gid_min=1, gid_max=999)
        a.platform_preconditions = Mock(return_value=platform)
        a.reserve_original_evidence = Mock()
        a.record_original_evidence = Mock()
        a.run_fixed_useradd = Mock(return_value=0)
        a.private_postcheck = Mock(return_value={'name': c.ACCOUNT, 'uid': 997, 'gid': 997,
            'group_gid': 997, 'primary_group': c.ACCOUNT, 'home': '/nonexistent',
            'shell': '/usr/sbin/nologin', 'supplementary_groups': [], 'password_locked': True,
            'home_absent': True, 'mail_spool_absent': True, 'no_subids': True, 'no_sudo_grants': True})
        return a

    def test_creation_fixed_one_command(self):
        a = self.setup_ops()
        self.assertEqual('ACCOUNT_CREATED_VERIFIED', c.create_once(a)['state'])
        a.lock_existing.assert_called_once_with(c.ORIGINAL_LOCK)
        a.reserve_original_evidence.assert_called_once_with(c.ACCOUNT_RECEIPT)
        a.run_fixed_useradd.assert_called_once_with(c.PROPOSED_ARGV)
        self.assertEqual(2, a.getpwnam.call_count)
        self.assertEqual(2, a.platform_preconditions.call_count)

    def test_partial_attempt_never_mutates(self):
        a = self.setup_ops(); a.reserve_original_evidence.side_effect = c.Denied('EXISTS')
        with self.assertRaises(c.Denied): c.create_once(a)
        a.run_fixed_useradd.assert_not_called()

    def test_unknown_platform_never_mutates(self):
        for key in self.setup_ops().platform_preconditions.return_value:
            a = self.setup_ops(); a.platform_preconditions.return_value[key] = None
            with self.assertRaises(c.Denied): c.create_once(a)
            a.reserve_original_evidence.assert_not_called()
            a.run_fixed_useradd.assert_not_called()

    def test_collision_during_fresh_recheck_no_mutation(self):
        a = self.setup_ops(); a.getpwnam.side_effect = [KeyError(), SimpleNamespace()]
        with self.assertRaises(c.Denied): c.create_once(a)
        a.run_fixed_useradd.assert_not_called()
        a.record_original_evidence.assert_called_with(c.ACCOUNT_RECEIPT, 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY')

    def test_command_failure_or_timeout_no_retry(self):
        for failure in (1, TimeoutError('PRIVATE_SENTINEL')):
            a = self.setup_ops()
            if isinstance(failure, Exception): a.run_fixed_useradd.side_effect = failure
            else: a.run_fixed_useradd.return_value = failure
            with self.assertRaises(c.Denied) as ctx: c.create_once(a)
            self.assertNotIn('PRIVATE_SENTINEL', str(ctx.exception))
            self.assertEqual(1, a.run_fixed_useradd.call_count)
            a.private_postcheck.assert_not_called()
            a.record_original_evidence.assert_called_with(c.ACCOUNT_RECEIPT, 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY')

    def test_every_postcondition_enforced_no_repair(self):
        good = self.setup_ops().private_postcheck.return_value
        for key in good:
            a = self.setup_ops(); a.private_postcheck.return_value[key] = None
            with self.assertRaises(c.Denied): c.create_once(a)
            self.assertEqual(1, a.run_fixed_useradd.call_count)
            a.record_original_evidence.assert_called_with(c.ACCOUNT_RECEIPT, 'ACCOUNT_RESULT_UNKNOWN_NO_RETRY')

class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.modules['account_candidate'] = c
        spec = importlib.util.spec_from_file_location('account_os', Path(__file__).parents[1] / 'account_os.py')
        cls.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.m)

    def test_only_apply_mode(self):
        with patch.object(self.m, 'OS') as constructor:
            for argv in ([], ['--help'], ['--apply', '--force'], ['--execute']):
                with self.assertRaises(c.Denied): self.m.main(argv)
            constructor.assert_not_called()

    def test_wrong_host_before_operations(self):
        with patch.object(self.m.os, 'uname', return_value=SimpleNamespace(nodename='other')), \
             patch.object(self.m.os, 'getuid', return_value=0), \
             patch.object(self.m.os, 'geteuid', return_value=0), \
             patch.object(self.m.subprocess, 'run') as run:
            with self.assertRaises(c.Denied): self.m.OS()
            run.assert_not_called()

    def test_useradd_exact_args_and_reserved_required(self):
        obj = object.__new__(self.m.OS); obj.reserved = False
        with patch.object(obj, 'command', return_value=SimpleNamespace(returncode=0)) as command:
            with self.assertRaises(c.Denied): obj.run_fixed_useradd(c.PROPOSED_ARGV)
            obj.reserved = True
            with self.assertRaises(c.Denied): obj.run_fixed_useradd(('/bin/sh',))
            self.assertEqual(0, obj.run_fixed_useradd(c.PROPOSED_ARGV))
            command.assert_called_once_with(c.PROPOSED_ARGV)

    def test_fixed_command_options(self):
        with patch.object(self.m, 'secure'), patch.object(self.m.subprocess, 'run',
                return_value=SimpleNamespace(returncode=0, stdout=b'', stderr=b'')) as run:
            self.m.OS.command(c.PROPOSED_ARGV)
            self.assertIs(run.call_args.kwargs['shell'], False)
            self.assertEqual(30, run.call_args.kwargs['timeout'])
            self.assertEqual({'PATH': '/usr/sbin:/usr/bin', 'LANG': 'C', 'LC_ALL': 'C'}, run.call_args.kwargs['env'])

    def test_missing_platform_documentation_denies(self):
        with patch.object(self.m, 'secure', side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                self.m.read_public_config('/usr/share/man/man8/useradd.8')

    def test_wrong_receipt_path_rejected_without_writes(self):
        obj = object.__new__(self.m.OS); obj.reserved = False
        with patch.object(self.m.os, 'mkdir') as mkdir:
            with self.assertRaises(c.Denied): obj.reserve_original_evidence('/tmp/other')
            mkdir.assert_not_called()

class SudoPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        AdapterTests.setUpClass()
        cls.m = AdapterTests.m

    def test_sudo_known_denial(self):
        obj = object.__new__(self.m.OS)
        for terminal in ('', '.'):
            result = SimpleNamespace(returncode=1,
              stdout=('User '+c.ACCOUNT+' is not allowed to run sudo on '+c.HOST+terminal+'\n').encode(), stderr=b'')
            with patch.object(obj, 'command', return_value=result) as command:
                self.assertIs(True, obj.sudo_denied())
                command.assert_called_once_with(('/usr/bin/sudo', '-n', '-l', '-U', c.ACCOUNT))

    def test_sudo_allow_and_unknown_never_pass(self):
        obj = object.__new__(self.m.OS)
        for rc, output in ((0, b'ALL'), (1, b'unknown user'), (1, b'password required'),
                           (2, b'policy parse failure'), (1, b'User other is not allowed')):
            with patch.object(obj, 'command', return_value=SimpleNamespace(returncode=rc, stdout=output, stderr=b'')):
                self.assertIsNot(True, obj.sudo_denied())

    def test_trusted_sudo_setuid_supported_without_real_process(self):
        row = SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFREG | 0o4755, st_nlink=1)
        with patch.object(self.m, 'secure'), patch.object(self.m.os, 'lstat', return_value=row), \
             patch.object(self.m.subprocess, 'run', return_value=SimpleNamespace(stdout=b'', stderr=b'', returncode=1)) as run:
            self.m.OS.command(('/usr/bin/sudo', '-n', '-l', '-U', c.ACCOUNT))
            run.assert_called_once()

    def test_sudo_foreign_or_writable_denied(self):
        for uid, mode in ((1002, 0o4755), (0, 0o4777), (0, 0o6755)):
            row = SimpleNamespace(st_uid=uid, st_gid=0, st_mode=stat.S_IFREG | mode, st_nlink=1)
            with patch.object(self.m, 'secure'), patch.object(self.m.os, 'lstat', return_value=row), \
                 patch.object(self.m.subprocess, 'run') as run:
                with self.assertRaises(c.Denied): self.m.OS.command(('/usr/bin/sudo', '-n', '-l', '-U', c.ACCOUNT))
                run.assert_not_called()

class NormalPlatformTests(unittest.TestCase):
    def test_normal_shadow_supports_F_without_local_man_or_nss_restriction(self):
        AdapterTests.setUpClass(); m = AdapterTests.m
        obj = object.__new__(m.OS)
        docs = {'/etc/login.defs': 'SYS_UID_MIN 1\nSYS_UID_MAX 999\nSYS_GID_MIN 1\nSYS_GID_MAX 999\n',
                '/etc/default/useradd': 'GROUP=100\nHOME=/home\nCREATE_MAIL_SPOOL=yes\n'}
        flags = b'--system --user-group --no-create-home --home-dir --shell --key --password --add-subids-for-system'
        with patch.object(m, 'secure_postcheck_tool') as precheck, \
             patch.object(obj, 'command', return_value=SimpleNamespace(returncode=0, stdout=flags)), \
             patch.object(m, 'read_public_config', side_effect=lambda p: docs[p]) as read, \
             patch.object(m.os.path, 'lexists', return_value=False):
            result = obj.platform_preconditions()
            self.assertTrue(result['no_subid_allocation'])
            self.assertTrue(result['locked_password_explicit'])
            self.assertEqual(['/usr/bin/passwd', '/usr/bin/sudo'], [call.args[0] for call in precheck.call_args_list])
            self.assertEqual({'/etc/login.defs', '/etc/default/useradd'}, {call.args[0] for call in read.call_args_list})

class StandaloneTests(unittest.TestCase):
    def load_payload(self):
        spec = importlib.util.spec_from_file_location('account_prepare', Path(__file__).parents[1] / 'account_prepare.py')
        module = importlib.util.module_from_spec(spec)
        with patch('os.uname', side_effect=AssertionError('NO_HOST_PROBE')), \
             patch('subprocess.run', side_effect=AssertionError('NO_PROCESS')):
            spec.loader.exec_module(module)
        return module

    def test_standalone_import_has_no_host_or_process_operations(self):
        m = self.load_payload()
        self.assertEqual(c.PROPOSED_ARGV, m.PROPOSED_ARGV)
        self.assertEqual(c.ORIGINAL_LOCK, m.ORIGINAL_LOCK)
        self.assertEqual(c.ACCOUNT_RECEIPT, m.ACCOUNT_RECEIPT)

    def test_standalone_exact_apply_only(self):
        m = self.load_payload()
        with patch.object(m, 'OS') as constructor:
            for args in ([], ['--plan'], ['--apply', '--force']):
                with self.assertRaises(m.Denied): m.main(args)
            constructor.assert_not_called()

    def test_standalone_creation_mocked(self):
        m = self.load_payload()
        a = CreationCoreTests().setup_ops()
        result = m.create_once(a)
        self.assertEqual('ACCOUNT_CREATED_VERIFIED', result['state'])
        a.run_fixed_useradd.assert_called_once_with(m.PROPOSED_ARGV)
        self.assertEqual('NOT_AUDITED', result['polkit_global_policy'])

    def test_standalone_no_local_imports(self):
        import ast
        source = (Path(__file__).parents[1] / 'account_prepare.py').read_text()
        tree = ast.parse(source)
        self.assertFalse(any(isinstance(n, ast.Import) and any(x.name in ('account_os', 'account_candidate')
                          for x in n.names) for n in ast.walk(tree)))
        compile(source, 'account_prepare.py', 'exec')

class PostcheckToolPreflightTests(unittest.TestCase):
    def test_both_tools_exact_safe_modes(self):
        AdapterTests.setUpClass(); m = AdapterTests.m
        for path in ('/usr/bin/passwd', '/usr/bin/sudo'):
            for mode in (0o755, 0o4755, 0o6755, 0o775, 0o4777, 0o4711):
                row = SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFREG | mode, st_nlink=1)
                with patch.object(m, 'secure'), patch.object(m.os, 'lstat', return_value=row):
                    if mode in (0o755, 0o4755): m.secure_postcheck_tool(path)
                    else:
                        with self.assertRaises(c.Denied): m.secure_postcheck_tool(path)

    def test_missing_tool_blocks_before_commands(self):
        AdapterTests.setUpClass(); m = AdapterTests.m
        obj = object.__new__(m.OS)
        with patch.object(m, 'secure_postcheck_tool', side_effect=FileNotFoundError), \
             patch.object(obj, 'command') as command:
            with self.assertRaises(FileNotFoundError): obj.platform_preconditions()
            command.assert_not_called()

    def test_no_arbitrary_setuid_path(self):
        AdapterTests.setUpClass(); m = AdapterTests.m
        with patch.object(m.os, 'lstat') as probe:
            with self.assertRaises(c.Denied): m.secure_postcheck_tool('/usr/bin/other')
            probe.assert_not_called()
