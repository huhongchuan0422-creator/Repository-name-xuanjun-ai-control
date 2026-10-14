"""Offline process fixtures only. No UK/systemctl/network/model calls occur."""
import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import ledger_server_identity as subject


class OwnedChildFixture(object):
    def setUp(self):
        self.children = []
        self.real_popen = subprocess.Popen
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.previous_subreaper = ctypes.c_int()
        self.assertEqual(self.libc.prctl(37, ctypes.byref(self.previous_subreaper), 0, 0, 0), 0)
        self.assertEqual(self.libc.prctl(36, 1, 0, 0, 0), 0)
        self.descendants = []
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        try:
            for child in self.children:
                # Check the function, then clean up even if an assertion fails.
                checked = child.returncode is not None and child.stdout.closed and child.stderr.closed
                if child.poll() is None:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                child.wait(timeout=2)
                child.stdout.close(); child.stderr.close()
                self.assertTrue(checked, 'runtime command left an owned child or pipe open')
                with self.assertRaises(ChildProcessError): os.waitpid(child.pid, os.WNOHANG)
        finally:
            for pid in self.descendants:
                try: os.kill(pid, signal.SIGKILL)
                except ProcessLookupError: pass
                try: os.waitpid(pid, 0)
                except ChildProcessError: pass
            self.directory.cleanup()
            self.assertEqual(self.libc.prctl(36, self.previous_subreaper.value, 0, 0, 0), 0)

    def spawn(self, *args, **kwargs):
        child = self.real_popen(*args, **kwargs)
        self.children.append(child)
        return child

    def invoke(self, source, timeout=.4, maximum=1024):
        with mock.patch.object(subject.subprocess, 'Popen', side_effect=self.spawn):
            return subject._bounded_owned_command([sys.executable, '-B', '-c', source],
                {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout, maximum)

    def pipe_holder(self, before_capture=False, invoke=None):
        pidfile = self.directory.name + '/descendant.pid'
        source = '''import os,time
child=os.fork()
if child==0:
 time.sleep(10)
 os._exit(0)
with open(%r,'w') as stream:stream.write(str(child))
os._exit(0)
''' % pidfile
        original_spawn = self.spawn
        def delayed(*args, **kwargs):
            child = original_spawn(*args, **kwargs)
            if before_capture:
                until = time.monotonic() + 1
                while time.monotonic() < until:
                    row = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if row is not None: break
                    time.sleep(.005)
                self.assertIsNotNone(row)
            return child
        self.spawn = delayed
        start = time.monotonic()
        try:
            with self.assertRaises(ValueError):
                (invoke or self.invoke)(source)
        finally:
            self.spawn = original_spawn
            if os.path.exists(pidfile):
                with open(pidfile) as stream: pid = int(stream.read())
                self.descendants.append(pid)
        self.assertLess(time.monotonic() - start, 1.2)
        self.assertEqual(self.children[-1].returncode, 0)
        until = time.monotonic() + 1
        while True:
            found, status = os.waitpid(pid, os.WNOHANG)
            if found: break
            self.assertLess(time.monotonic(), until, 'pipe-holder survived group cleanup')
            time.sleep(.005)
        self.descendants.remove(pid)
        self.assertTrue(os.WIFSIGNALED(status))
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)


class RuntimeCommandLifetimeTests(OwnedChildFixture, unittest.TestCase):
    def test_success_has_exact_isolated_launch_contract(self):
        self.assertEqual(self.invoke("import os;os.write(1,b'ok')"), b'ok')
        process = self.children[-1]
        self.assertEqual(process.returncode, 0)

    def test_timeout_and_pipe_eof_without_exit(self):
        for source in ('import time;time.sleep(10)',
                'import os,time;os.close(1);os.close(2);time.sleep(10)'):
            started = time.monotonic()
            with self.assertRaisesRegex(ValueError, 'COMMAND_DEADLINE'):
                self.invoke(source, timeout=.2)
            self.assertLess(time.monotonic() - started, .8)
            self.assertEqual(self.children[-1].returncode, -signal.SIGKILL)

    def test_drip_output_uses_whole_request_deadline(self):
        with self.assertRaisesRegex(ValueError, 'COMMAND_DEADLINE'):
            self.invoke("import os,time\nfor i in range(100):\n os.write(1,b'x');time.sleep(.02)", timeout=.2)

    def test_output_bound_both_streams_and_exact_limit(self):
        self.assertEqual(len(self.invoke("import os;os.write(1,b'x'*1024)")), 1024)
        for fd in (1, 2):
            with self.assertRaisesRegex(ValueError, 'COMMAND_OUTPUT_BOUND'):
                self.invoke("import os;os.write(%d,b'x'*1025)" % fd)

    def test_nonzero_exit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'COMMAND_FAILED'):
            self.invoke('raise SystemExit(3)')

    def test_selector_constructor_failure_still_cleans(self):
        with mock.patch.object(subject.selectors, 'DefaultSelector', side_effect=OSError('setup')):
            with self.assertRaisesRegex(OSError, 'setup'): self.invoke('import time;time.sleep(10)')

    def test_selector_registration_failure_still_cleans(self):
        selector = subject.selectors.DefaultSelector()
        with mock.patch.object(subject.selectors, 'DefaultSelector', return_value=selector), \
                mock.patch.object(selector, 'register', side_effect=OSError('register')):
            with self.assertRaisesRegex(OSError, 'register'): self.invoke('import time;time.sleep(10)')
        self.assertIsNone(selector.get_map())

    def test_nonblocking_setup_failure_still_cleans(self):
        with mock.patch.object(subject.os, 'set_blocking', side_effect=OSError('blocking')):
            with self.assertRaisesRegex(OSError, 'blocking'): self.invoke('import time;time.sleep(10)')

    def test_setup_interrupt_still_cleans(self):
        for error in (KeyboardInterrupt, SystemExit):
            with mock.patch.object(subject.selectors, 'DefaultSelector', side_effect=error):
                with self.assertRaises(error): self.invoke('import time;time.sleep(10)')

    def test_spawn_failure_does_not_invent_process(self):
        with mock.patch.object(subject.subprocess, 'Popen', side_effect=OSError('spawn')):
            with self.assertRaisesRegex(OSError, 'spawn'):
                subject._bounded_owned_command(['/fixture'], {}, .2)
        self.assertEqual(self.children, [])

    def test_startup_is_charged_to_deadline(self):
        original = self.spawn
        def delayed(*args, **kwargs):
            child = original(*args, **kwargs); time.sleep(.18); return child
        self.spawn = delayed
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'COMMAND_DEADLINE'):
            self.invoke('import time;time.sleep(10)', timeout=.2)
        self.assertLess(time.monotonic() - started, .5)

    def test_primary_failure_survives_cleanup_failure(self):
        with mock.patch.object(subject.selectors, 'DefaultSelector', side_effect=OSError('primary')), \
                mock.patch.object(subject.os, 'killpg', side_effect=PermissionError('signal')):
            with self.assertRaisesRegex(OSError, 'primary') as raised:
                self.invoke('import time;time.sleep(.05)')
        self.assertRegex(str(raised.exception.__cause__), 'COMMAND_CLEANUP_UNKNOWN')

    def test_selector_close_error_still_closes_pipes_and_reaps(self):
        selector = subject.selectors.DefaultSelector(); close = selector.close
        def broken_close(): close(); raise OSError('close')
        with mock.patch.object(subject.selectors, 'DefaultSelector', return_value=selector), \
                mock.patch.object(selector, 'close', side_effect=broken_close):
            with self.assertRaisesRegex(ValueError, 'COMMAND_CLEANUP_UNKNOWN'):
                self.invoke('pass')

    def test_every_cleanup_step_is_attempted_after_secondary_errors(self):
        process = mock.Mock(returncode=None)
        process.stdout.close.side_effect = OSError('stdout')
        selector = mock.Mock()
        selector.close.side_effect = OSError('selector')
        with mock.patch.object(subject, '_owned_command_signal', side_effect=PermissionError('signal')) as signal_step, \
                mock.patch.object(subject, '_owned_command_reap', return_value=False) as reap:
            with self.assertRaisesRegex(ValueError, 'COMMAND_CLEANUP_UNKNOWN'):
                subject._owned_command_cleanup(process, selector, time.monotonic())
        signal_step.assert_called_once_with(process)
        selector.close.assert_called_once_with()
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()
        reap.assert_called_once()

    def test_cleanup_interrupt_is_propagated_only_after_all_steps(self):
        process = mock.Mock(returncode=None)
        selector = mock.Mock()
        selector.close.side_effect = KeyboardInterrupt
        with mock.patch.object(subject, '_owned_command_signal', return_value=True), \
                mock.patch.object(subject, '_owned_command_reap', return_value=True) as reap:
            with self.assertRaises(KeyboardInterrupt):
                subject._owned_command_cleanup(process, selector, time.monotonic())
        process.stdout.close.assert_called_once_with()
        process.stderr.close.assert_called_once_with()
        reap.assert_called_once()

    def test_exited_leader_pipe_holder_before_capture(self): self.pipe_holder(True)
    def test_exited_leader_pipe_holder_during_capture(self): self.pipe_holder(False)

    def test_reaped_child_cannot_authorize_signal_even_with_stale_returncode(self):
        process = self.real_popen([sys.executable, '-c', 'pass'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
        process.wait(timeout=2); actual = process.returncode; process.returncode = None
        try:
            with mock.patch.object(subject.os, 'killpg') as kill, \
                    mock.patch.object(subject.os, 'getpgid', return_value=process.pid), \
                    mock.patch.object(subject.os, 'getsid', return_value=process.pid):
                self.assertFalse(subject._owned_command_signal(process)); kill.assert_not_called()
        finally:
            process.returncode = actual; process.stdout.close(); process.stderr.close()

    def test_no_communicate_wait_or_poll(self):
        with mock.patch.object(subprocess.Popen, 'communicate', side_effect=AssertionError('communicate')), \
                mock.patch.object(subprocess.Popen, 'wait', side_effect=AssertionError('wait')), \
                mock.patch.object(subprocess.Popen, 'poll', side_effect=AssertionError('poll')):
            self.assertEqual(self.invoke('print("ok")'), b'ok\n')

    def test_invalid_bounds_never_spawn(self):
        with mock.patch.object(subject.subprocess, 'Popen') as spawn:
            for timeout, maximum in ((0, 1), (True, 1), (31, 1), (float('nan'), 1),
                    (float('inf'), 1), (.2, 0), (.2, True), (.2, 1048577)):
                with self.assertRaises(ValueError): subject._bounded_owned_command([], {}, timeout, maximum)
            spawn.assert_not_called()

    def test_manager_unit_setup_failure_reaps_real_worker(self):
        backend = subject.OSBackend()
        class Deadline:
            def check(self): return .3
        original = self.spawn
        def simulated_manager(argv, **kwargs):
            self.assertEqual(argv[:4], ['/usr/bin/systemctl', '--system', 'show', '--no-pager'])
            self.assertEqual(kwargs['env'], {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'SYSTEMD_PAGER': ''})
            self.assertTrue(kwargs['start_new_session']); self.assertEqual(kwargs['cwd'], '/')
            return original([sys.executable, '-c', 'import time;time.sleep(10)'], **kwargs)
        with mock.patch.object(backend, 'manager_channel', return_value=()), \
                mock.patch.object(subject.subprocess, 'Popen', side_effect=simulated_manager), \
                mock.patch.object(subject.selectors, 'DefaultSelector', side_effect=OSError('setup')):
            with self.assertRaisesRegex(OSError, 'setup'): backend.unit(subject.SOCKET_UNIT, Deadline())


if __name__ == '__main__': unittest.main()
