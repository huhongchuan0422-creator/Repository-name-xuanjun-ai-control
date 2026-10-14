"""Harmless local child fixtures; no UK commands or external connections."""
import ctypes
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate')]
import snapshot_io as io

class QueryTests(unittest.TestCase):
    def setUp(self):self.children=[];self.original=subprocess.Popen
    def spawn(self,args,**kwargs):
        child=self.original(args,**kwargs);self.children.append(child);return child
    def tearDown(self):
        for child in self.children:
            if child.returncode is None:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                child.wait(timeout=2)
            for name in ('stdout','stderr'):
                stream=getattr(child,name,None)
                if stream is not None and not stream.closed:stream.close()
    def run_source(self,source,timeout=0.8,maximum=4096):
        with mock.patch.object(io.subprocess,'Popen',side_effect=self.spawn):
            return io.bounded_query([sys.executable,'-B','-c',source],timeout=timeout,maximum=maximum)
    def assert_clean(self):
        self.assertTrue(self.children)
        for child in self.children:
            self.assertIsNotNone(child.returncode)
            self.assertTrue(child.stdout.closed);self.assertTrue(child.stderr.closed)
            with self.assertRaises(ChildProcessError):os.waitpid(child.pid,os.WNOHANG)
    def test_success_reaps_without_poll_wait_communicate(self):
        with mock.patch.object(subprocess.Popen,'poll',side_effect=AssertionError('poll forbidden')), \
             mock.patch.object(subprocess.Popen,'wait',side_effect=AssertionError('wait forbidden')), \
             mock.patch.object(subprocess.Popen,'communicate',side_effect=AssertionError('communicate forbidden')):
            # This verifies success/ownership, not a sub-second scheduling SLA.
            # Keep a finite startup budget under loaded aggregate runners; the
            # independent explicit0.3s deadline test remains unchanged.
            self.assertEqual(self.run_source("import os; os.write(1,b'fixture'); os._exit(0)",timeout=5.0),b'fixture')
        self.assert_clean()
    def test_success_budget_handles_finite_scheduler_delay(self):
        original=io.selectors.DefaultSelector
        def delayed_selector():
            time.sleep(0.9)  # exceeds the former0.64s capture budget
            return original()
        with mock.patch.object(io.selectors,'DefaultSelector',side_effect=delayed_selector), \
             mock.patch.object(subprocess.Popen,'poll',side_effect=AssertionError('poll forbidden')), \
             mock.patch.object(subprocess.Popen,'wait',side_effect=AssertionError('wait forbidden')), \
             mock.patch.object(subprocess.Popen,'communicate',side_effect=AssertionError('communicate forbidden')):
            self.assertEqual(self.run_source("import os; os.write(1,b'fixture'); os._exit(0)",timeout=5.0),b'fixture')
        self.assert_clean()
    def test_selector_construction_failure_still_cleans(self):
        with mock.patch.object(io.selectors,'DefaultSelector',side_effect=OSError('selector setup')):
            with self.assertRaises(OSError):self.run_source('import time; time.sleep(60)')
        self.assert_clean()
    def test_first_capture_failure_preserved_with_cleanup_unknown_cause(self):
        cleanup=io._query_cleanup
        def failed_cleanup(*args):
            cleanup(*args)
            raise OSError('secondary cleanup diagnostic')
        with mock.patch.object(io.selectors,'DefaultSelector',side_effect=OSError('first capture failure')), \
             mock.patch.object(io,'_query_cleanup',side_effect=failed_cleanup):
            with self.assertRaisesRegex(OSError,'first capture failure') as caught:
                self.run_source('import time; time.sleep(60)')
        self.assertIsInstance(caught.exception.__cause__,ValueError)
        self.assertEqual(str(caught.exception.__cause__),'READ_ONLY_COMMAND_CLEANUP_UNKNOWN')
        self.assert_clean()
    def test_selector_registration_failure_still_cleans(self):
        selector=mock.Mock();selector.register.side_effect=OSError('register')
        with mock.patch.object(io.selectors,'DefaultSelector',return_value=selector):
            with self.assertRaises(OSError):self.run_source('import time; time.sleep(60)')
        selector.close.assert_called_once();self.assert_clean()
    def test_set_blocking_failure_still_cleans(self):
        with mock.patch.object(io.os,'set_blocking',side_effect=OSError('set blocking')):
            with self.assertRaises(OSError):self.run_source('import time; time.sleep(60)')
        self.assert_clean()
    def test_timeout_deadline_includes_cleanup(self):
        started=time.monotonic()
        with self.assertRaisesRegex(ValueError,'DEADLINE') as caught:
            self.run_source('import time; time.sleep(60)',timeout=0.3)
        self.assertLess(time.monotonic()-started,0.7)
        if self.children[0].returncode is None:
            # Scheduler delay may exhaust the shared reap budget. That outcome
            # must remain explicit UNKNOWN, never a fabricated cleanup success.
            self.assertEqual(str(caught.exception.__cause__),'READ_ONLY_COMMAND_CLEANUP_UNKNOWN')
            self.assertTrue(self.children[0].stdout.closed);self.assertTrue(self.children[0].stderr.closed)
        else:self.assert_clean()
    def test_output_limit_stops_and_reaps(self):
        with self.assertRaisesRegex(ValueError,'OUTPUT_BOUND'):
            self.run_source("import os,time; os.write(1,b'x'*8192); time.sleep(60)",maximum=64)
        self.assert_clean()
    def test_nonzero_exit_does_not_succeed(self):
        with self.assertRaisesRegex(ValueError,'COMMAND_FAILED'):self.run_source('import os; os._exit(3)')
        self.assert_clean()
    def test_interrupt_waits_until_independent_cleanup_done(self):
        with mock.patch.object(io.selectors,'DefaultSelector',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.run_source('import time; time.sleep(60)')
        self.assert_clean()
    def test_invalid_bounds_no_spawn(self):
        with mock.patch.object(io.subprocess,'Popen') as spawn:
            for timeout in (0,-1,float('nan'),float('inf'),True,61):
                with self.assertRaisesRegex(ValueError,'BOUNDS'):io.bounded_query([],timeout=timeout)
            spawn.assert_not_called()
    def test_exited_leader_pipe_holder_killed_and_reaped(self):
        libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
        self.assertEqual(libc.prctl(37,ctypes.byref(old),0,0,0),0)
        self.assertEqual(libc.prctl(36,1,0,0,0),0)
        descendant=None
        try:
            with tempfile.TemporaryDirectory(prefix='epoch7-query-fixture-') as root:
                pidfile=root+'/child.pid'
                source="""import os,time
child=os.fork()
if child==0:
 time.sleep(60)
 os._exit(0)
with open(%r,'w') as stream:stream.write(str(child))
os._exit(0)
"""%pidfile
                with self.assertRaisesRegex(ValueError,'DEADLINE'):self.run_source(source,timeout=0.4)
                descendant=int(pathlib.Path(pidfile).read_text());deadline=time.monotonic()+1
                while time.monotonic()<deadline:
                    pid,status=os.waitpid(descendant,os.WNOHANG)
                    if pid:
                        self.assertTrue(os.WIFSIGNALED(status));self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
                        descendant=None;break
                    time.sleep(0.01)
                self.assertIsNone(descendant);self.assert_clean()
        finally:
            if descendant is not None:
                os.kill(descendant,signal.SIGKILL);os.waitpid(descendant,0)
            self.assertEqual(libc.prctl(36,old.value,0,0,0),0)

class CleanupTests(unittest.TestCase):
    def process(self):return types.SimpleNamespace(pid=123456,returncode=None,_waitpid_lock=threading.Lock(),
                                                   stdout=mock.Mock(),stderr=mock.Mock())
    def test_each_cleanup_attempt_independent(self):
        child=self.process();selector=mock.Mock()
        child.stdout.close.side_effect=OSError('stdout');selector.close.side_effect=OSError('selector')
        with mock.patch.object(io,'_query_group_signal',side_effect=OSError('signal')), \
             mock.patch.object(io,'_query_reap',return_value=True) as reap:
            with self.assertRaisesRegex(ValueError,'CLEANUP_UNKNOWN'):io._query_cleanup(child,selector,time.monotonic()+1)
        child.stdout.close.assert_called_once();child.stderr.close.assert_called_once();selector.close.assert_called_once();reap.assert_called_once()
    def test_cleanup_interrupt_does_not_skip_remaining_steps(self):
        child=self.process()
        with mock.patch.object(io,'_query_group_signal',side_effect=KeyboardInterrupt), \
             mock.patch.object(io,'_query_reap',return_value=True) as reap:
            with self.assertRaises(KeyboardInterrupt):io._query_cleanup(child,None,time.monotonic()+1)
        child.stdout.close.assert_called_once();child.stderr.close.assert_called_once();reap.assert_called_once()
    def test_unproven_reaped_pid_never_signalled(self):
        child=self.process()
        with mock.patch.object(io.os,'waitid',side_effect=ChildProcessError),mock.patch.object(io.os,'killpg') as signal_group:
            self.assertFalse(io._query_group_signal(child));signal_group.assert_not_called()
    def test_reaped_returncode_does_not_probe_or_signal(self):
        child=self.process();child.returncode=0
        with mock.patch.object(io.os,'waitid') as wait,mock.patch.object(io.os,'killpg') as signal_group:
            self.assertFalse(io._query_group_signal(child));wait.assert_not_called();signal_group.assert_not_called()
    def test_group_and_session_must_both_match(self):
        child=self.process()
        with mock.patch.object(io.os,'waitid',return_value=None),mock.patch.object(io.os,'getpgid',return_value=child.pid), \
             mock.patch.object(io.os,'getsid',return_value=1),mock.patch.object(io.os,'killpg') as signal_group:
            self.assertFalse(io._query_group_signal(child));signal_group.assert_not_called()
    def test_unreaped_zombie_is_valid_group_pin(self):
        child=self.process()
        with mock.patch.object(io.os,'waitid',return_value=types.SimpleNamespace(si_pid=child.pid)), \
             mock.patch.object(io.os,'getpgid',return_value=child.pid),mock.patch.object(io.os,'getsid',return_value=child.pid), \
             mock.patch.object(io.os,'killpg') as signal_group:
            self.assertTrue(io._query_group_signal(child));signal_group.assert_called_once_with(child.pid,signal.SIGKILL)
    def test_waitpid_is_always_nonblocking_even_expired_budget(self):
        child=self.process()
        with mock.patch.object(io.os,'waitpid',return_value=(0,0)) as wait:
            self.assertFalse(io._query_reap(child,time.monotonic()-1))
        wait.assert_called_once_with(child.pid,os.WNOHANG)
    def test_wait_lock_contention_is_bounded(self):
        child=self.process();child._waitpid_lock.acquire()
        try:
            started=time.monotonic()
            with mock.patch.object(io.os,'waitpid') as wait:
                self.assertFalse(io._query_reap(child,time.monotonic()+0.02));wait.assert_not_called()
            self.assertLess(time.monotonic()-started,0.1)
        finally:child._waitpid_lock.release()

if __name__=='__main__':unittest.main()
