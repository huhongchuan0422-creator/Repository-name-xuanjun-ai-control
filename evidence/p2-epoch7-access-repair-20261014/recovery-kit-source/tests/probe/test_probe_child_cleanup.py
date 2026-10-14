"""Only local harmless Python children; never systemctl, host units or sockets."""
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock
import probe_driver as driver
import probe_helpers as helper
from test_probe_driver import fixture


class ChildCleanupTests(unittest.TestCase):
    def run_setup_failure(self,module,register=False,kill_failure=False):
        launched=[];original=subprocess.Popen;real_kill=os.killpg
        def launch(unused_argv,**kwargs):
            kwargs.pop('cwd',None)
            process=original([sys.executable,'-B','-c','import time;time.sleep(60)'],**kwargs)
            launched.append(process);return process
        def signal_child(pid,sig):
            real_kill(pid,sig)
            if kill_failure:raise PermissionError('SYNTHETIC_SIGNAL_RESULT_UNKNOWN')
        selector=mock.Mock();selector.register.side_effect=OSError('SETUP_FAILURE')
        selector_factory=mock.Mock(return_value=selector) if register else mock.Mock(side_effect=OSError('SETUP_FAILURE'))
        policy,unused,unused2,unused3=fixture()
        ops=driver.HostOps(policy,'1'*64)
        try:
            with mock.patch.object(module.subprocess,'Popen',side_effect=launch), \
                 mock.patch.object(module.selectors,'DefaultSelector',selector_factory), \
                 mock.patch.object(module.os,'killpg',side_effect=signal_child):
                with self.assertRaisesRegex(OSError,'SETUP_FAILURE'):
                    if module is driver:ops.command(['--version'],mutating=False)
                    else:
                        with mock.patch.object(helper,'emit'):
                            helper.show({'nonce':policy['nonce'],'systemctl':'/usr/bin/systemctl'},
                                'xj-p2-proof-'+policy['nonce']+'.socket','socket',time.monotonic()+2)
            self.assertEqual(len(launched),1);process=launched[0]
            self.assertIsNotNone(process.returncode)
            self.assertTrue(process.stdout.closed and process.stderr.closed)
            with self.assertRaises(ChildProcessError):os.waitpid(process.pid,os.WNOHANG)
            if module is driver and kill_failure:
                self.assertIn('CHILD_SIGNAL_UNCONFIRMED',ops.last_command_cleanup)
            if register:selector.close.assert_called_once_with()
        finally:
            for process in launched:
                if process.returncode is None:
                    try:real_kill(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=2)
                process.stdout.close();process.stderr.close()
    def test_spawn_time_consumes_absolute_command_deadline(self):
        for module in (driver,helper):
            policy,unused,unused2,unused3=fixture();ops=driver.HostOps(policy,'1'*64)
            ops.deadline=mock.Mock();ops.deadline.remaining.return_value=10
            clock=[10.0];process=mock.Mock();selector=mock.Mock();selector.get_map.return_value={'fd':1}
            def launch(*args,**kwargs):clock[0]=12.0;return process
            with mock.patch.object(module.time,'monotonic',side_effect=lambda:clock[0]), \
                 mock.patch.object(module.subprocess,'Popen',side_effect=launch), \
                 mock.patch.object(module.selectors,'DefaultSelector',return_value=selector), \
                 mock.patch.object(module,'cleanup_owned_child',return_value=[]) as cleanup:
                with self.assertRaises((TimeoutError,ValueError)):
                    if module is driver:ops.command(['--version'],mutating=False,timeout=1)
                    else:helper.show({'nonce':policy['nonce'],'systemctl':'/usr/bin/systemctl'},
                        'xj-p2-proof-'+policy['nonce']+'.socket','socket',20)
            selector.select.assert_not_called();cleanup.assert_called_once_with(process)
    def test_driver_selector_constructor_failure_reaps_actual_child(self):self.run_setup_failure(driver)
    def test_driver_selector_register_failure_reaps_actual_child(self):self.run_setup_failure(driver,register=True)
    def test_helper_selector_constructor_failure_reaps_actual_child(self):self.run_setup_failure(helper)
    def test_helper_selector_register_failure_reaps_actual_child(self):self.run_setup_failure(helper,register=True)
    def test_driver_signal_error_still_closes_both_and_reaps(self):self.run_setup_failure(driver,kill_failure=True)
    def test_helper_signal_error_still_closes_both_and_reaps(self):self.run_setup_failure(helper,kill_failure=True)
    def test_unreaped_zombie_identity_is_preserved_until_cleanup(self):
        for module in (driver,helper):
            process=subprocess.Popen([sys.executable,'-B','-c','pass'],stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,start_new_session=True)
            try:
                self.assertEqual(module.wait_owned_child(process,time.monotonic()+2),0)
                self.assertIsNone(process.returncode)
                observed=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                self.assertEqual(observed.si_pid,process.pid)
                self.assertEqual(module.cleanup_owned_child(process),[])
                self.assertEqual(process.returncode,0)
                with self.assertRaises(ChildProcessError):os.waitpid(process.pid,os.WNOHANG)
            finally:
                if process.returncode is None:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)
                process.stdout.close();process.stderr.close()
    def test_unowned_stale_pid_never_signalled_and_all_cleanup_attempted(self):
        for module in (driver,helper):
            process=mock.Mock(pid=123456,returncode=None)
            process._waitpid_lock.acquire.return_value=True
            process.stdout.close.side_effect=OSError('CLOSE_FAILURE')
            with mock.patch.object(module.os,'waitid',side_effect=ChildProcessError()), \
                 mock.patch.object(module.os,'killpg') as kill:
                errors=module.cleanup_owned_child(process)
            kill.assert_not_called();process.stderr.close.assert_called_once();process.wait.assert_called_once_with(timeout=.2)
            self.assertIn('CHILD_OWNERSHIP_UNCONFIRMED',errors);self.assertIn('STDOUT_CLOSE_UNCONFIRMED',errors)
    def test_fork_target_cleanup_reaps_actual_harmless_child(self):
        pid=os.fork()
        if pid==0:
            time.sleep(60);os._exit(0)
        try:
            self.assertEqual(helper.cleanup_fork_child(pid,[]),[])
            with self.assertRaises(ChildProcessError):os.waitpid(pid,os.WNOHANG)
        finally:
            try:
                row=os.waitid(os.P_PID,pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            except ChildProcessError:pass
    def test_fork_cleanup_signal_close_failures_do_not_skip_bounded_reap(self):
        with mock.patch.object(helper.os,'waitid',return_value=None), \
             mock.patch.object(helper.os,'kill',side_effect=OSError('SIGNAL_FAIL')), \
             mock.patch.object(helper.os,'close',side_effect=[OSError('CLOSE_FAIL'),None]) as closes, \
             mock.patch.object(helper.os,'waitpid',return_value=(123456,0)) as reap:
            result=helper.cleanup_fork_child(123456,[10,11])
        self.assertEqual(closes.call_count,2);reap.assert_called_once_with(123456,os.WNOHANG)
        self.assertEqual(result,['FORK_SIGNAL_UNCONFIRMED','FORK_FD_CLOSE_UNCONFIRMED'])
    def test_fork_cleanup_never_blocks_on_waitpid(self):
        with mock.patch.object(helper.os,'waitid',return_value=None),mock.patch.object(helper.os,'kill'), \
             mock.patch.object(helper.os,'waitpid',return_value=(0,0)) as reap, \
             mock.patch.object(helper.time,'monotonic',side_effect=[0,.01,.3]),mock.patch.object(helper.time,'sleep'):
            result=helper.cleanup_fork_child(123456,[])
        self.assertIn('FORK_REAP_UNCONFIRMED',result);reap.assert_called_once_with(123456,os.WNOHANG)


if __name__=='__main__':unittest.main()
