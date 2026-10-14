import ast
import base64
import ctypes
from contextlib import ExitStack
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

import protected_command_evidence as evidence


PHASE = 'provision_from_retained_resources'
OP = 'plugin_install'


class CaptureTests(unittest.TestCase):
    def capture(self, code, timeout=.5, cleanup=.15, limit=1024, read_error=None,
                kill_error=None, close_error=False, selector_error=False):
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', code],
                                   stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=0, start_new_session=True)
        try:
            with ExitStack() as stack:
                if read_error is not None:
                    stack.enter_context(patch.object(evidence.os, 'read', side_effect=read_error))
                if kill_error is not None:
                    stack.enter_context(patch.object(evidence.os, 'killpg', side_effect=kill_error))
                if selector_error:
                    stack.enter_context(patch.object(evidence.selectors, 'DefaultSelector',
                                                     side_effect=OSError('SECRET-selector')))
                if close_error:
                    original_close = process.stdout.close
                    def fail_after_close():
                        original_close()
                        raise OSError('SECRET-close-error')
                    stack.enter_context(patch.object(process.stdout, 'close', side_effect=fail_after_close))
                return evidence.capture_owned_process(process, PHASE, OP, 7, 1,
                                                      timeout, cleanup, limit)
        finally:
            # Bounded test-harness cleanup, independent of helper assertions.
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)

    @staticmethod
    def raw(value, stream):
        return base64.b64decode(value[stream]['prefix_b64'])

    def test_success_retains_binary_exactly(self):
        r = self.capture("import os;os.write(1,b'out\\x00\\xff');os.write(2,b'err')")
        self.assertEqual(r['reason'], 'SUCCESS')
        self.assertEqual(self.raw(r, 'stdout'), b'out\x00\xff')
        self.assertEqual(r['cleanup']['direct_process'], 'EXITED')
        self.assertEqual(r['cleanup']['output'], 'COMPLETE')
        self.assertEqual(r['cleanup']['descendants'], 'UNKNOWN')

    def test_failed_operation_and_stderr_survive(self):
        r = self.capture("import os,sys;os.write(2,b'EACCES source');sys.exit(23)")
        self.assertEqual((r['reason'], r['returncode']), ('EXIT_NONZERO', 23))
        p = evidence.failure_patch(r)
        self.assertEqual(p['stage'], 'HOLD')
        self.assertEqual(p['failed_stage'], PHASE + '_INTENT')
        self.assertEqual(p['failed_operation'], OP)
        self.assertEqual(self.raw(r, 'stderr'), b'EACCES source')

    def test_secrets_never_enter_public_summary_or_error_patch(self):
        secret = 'Bearer ghp_NOT_A_REAL_SECRET_abc123'
        r = self.capture("import os,sys;os.write(1,%r);os.write(2,%r);sys.exit(1)" %
                         (secret.encode(), secret.encode()))
        r['cmd'] = ['do-not-copy', secret]
        r['exception_message'] = secret
        r['env'] = {'TOKEN': secret}
        public = json.dumps(evidence.failure_patch(r))
        self.assertNotIn(secret, public)
        self.assertNotIn('prefix_b64', public)
        self.assertNotIn('prefix_sha256', public)
        self.assertNotIn('exception_message', public)

    def test_timeout_retains_partial_output(self):
        r = self.capture("import os,time;os.write(2,b'prefix');time.sleep(5)", timeout=.08)
        self.assertEqual(r['reason'], 'TIMEOUT')
        self.assertEqual(self.raw(r, 'stderr'), b'prefix')
        self.assertEqual(r['cleanup']['group_signal'], 'SENT')
        self.assertEqual(r['cleanup']['direct_process'], 'EXITED')

    def test_inherited_pipe_holder_does_not_extend_deadline(self):
        # Escaped child self-terminates. Parent helper must return before it does.
        code = ("import os,time\np=os.fork()\nif p==0:\n os.setsid()\n"
                " os.write(2,b'escaped pipe holder')\n time.sleep(.8)\n os._exit(0)\n"
                "time.sleep(5)")
        start = time.monotonic()
        r = self.capture(code, timeout=.08, cleanup=.08)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, .65)
        self.assertEqual(r['reason'], 'TIMEOUT')
        self.assertEqual(r['cleanup']['output'], 'INCOMPLETE')
        self.assertEqual(r['cleanup']['descendants'], 'UNKNOWN')
        self.assertIn(b'escaped pipe holder', self.raw(r, 'stderr'))

    def _exited_leader_with_owned_pipe_holder(self, before_capture):
        # The local test process temporarily adopts the fixture grandchild, so
        # all fixture processes can be reaped without leaving container zombies.
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        process = None
        child = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                pidfile = os.path.join(directory, 'child.pid')
                code = ("import os,time\nchild=os.fork()\nif child==0:\n"
                        " os.write(2,b'owned pipe holder')\n time.sleep(5)\n os._exit(0)\n"
                        "with open(%r,'w') as stream:stream.write(str(child))\n"
                        "os.replace(%r,%r)\n"
                        "time.sleep(%r)\nos._exit(0)\n" %
                        (pidfile + '.pending', pidfile + '.pending', pidfile,
                         0 if before_capture else 0.05))
                process = subprocess.Popen([sys.executable, '-I', '-B', '-c', code],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, bufsize=0, start_new_session=True)
                deadline = time.monotonic() + 1
                while not os.path.exists(pidfile) and time.monotonic() < deadline:
                    time.sleep(0.005)
                with open(pidfile) as stream:
                    child = int(stream.read())
                self.assertEqual(os.getpgid(child), process.pid)
                if before_capture:
                    exited = None
                    while exited is None and time.monotonic() < deadline:
                        exited = os.waitid(os.P_PID, process.pid,
                            os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        if exited is None:time.sleep(0.005)
                    self.assertIsNotNone(exited)
                original_poll, original_kill = process.poll, os.killpg
                signalled = []
                def only_poll_after_signal():
                    self.assertTrue(signalled, 'leader reaped before owned group signal')
                    return original_poll()
                def signal_group(pid, sig):
                    self.assertEqual((pid, sig), (process.pid, signal.SIGKILL))
                    result = original_kill(pid, sig)
                    signalled.append(pid)
                    return result
                start = time.monotonic()
                with patch.object(process, 'poll', side_effect=only_poll_after_signal), \
                        patch.object(evidence.os, 'killpg', side_effect=signal_group):
                    result = evidence.capture_owned_process(process, PHASE, OP, 7, 1,
                                                            0.2, 0.3, 1024)
                self.assertLess(time.monotonic() - start, 0.9)
                self.assertEqual(result['reason'], 'TIMEOUT')
                self.assertEqual(result['returncode'], 0)
                self.assertEqual(result['cleanup']['group_signal'], 'SENT')
                self.assertEqual(result['cleanup']['direct_process'], 'EXITED')
                self.assertEqual(result['cleanup']['output'], 'COMPLETE')
                self.assertEqual(result['cleanup']['descendants'], 'UNKNOWN')
                self.assertTrue(process.stdout.closed and process.stderr.closed)
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    waited, status = os.waitpid(child, os.WNOHANG)
                    if waited:
                        self.assertTrue(os.WIFSIGNALED(status))
                        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
                        child = None
                        break
                    time.sleep(0.005)
                self.assertIsNone(child, 'same-group pipe holder survived cleanup')
                with self.assertRaises(ChildProcessError):
                    os.waitpid(process.pid, os.WNOHANG)
        finally:
            if child is not None:
                try:os.kill(child, signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(child, 0)
            if process is not None:
                if process.returncode is None:
                    process.kill();process.wait(timeout=1)
                process.stdout.close();process.stderr.close()
            self.assertEqual(libc.prctl(36, previous.value, 0, 0, 0), 0)

    def test_already_exited_unreaped_leader_pipe_holder_is_killed(self):
        self._exited_leader_with_owned_pipe_holder(True)

    def test_leader_exiting_during_capture_pipe_holder_is_killed(self):
        self._exited_leader_with_owned_pipe_holder(False)

    def test_stdout_overflow_is_stopped_while_running(self):
        r = self.capture("import os,time\nwhile True:os.write(1,b'x'*4096)", limit=127)
        self.assertEqual(r['reason'], 'OUTPUT_LIMIT')
        self.assertEqual(len(self.raw(r, 'stdout')), 127)
        self.assertTrue(r['stdout']['truncated'])
        self.assertEqual(r['cleanup']['direct_process'], 'EXITED')

    def test_stderr_overflow_is_stopped_while_running(self):
        r = self.capture("import os\nwhile True:os.write(2,b'y'*4096)", limit=63)
        self.assertEqual(r['reason'], 'OUTPUT_LIMIT')
        self.assertEqual(len(self.raw(r, 'stderr')), 63)
        self.assertTrue(r['stderr']['truncated'])

    def test_both_streams_exact_limit_not_falsely_truncated(self):
        r = self.capture("import os;os.write(1,b'x'*127);os.write(2,b'y'*127)", limit=127)
        self.assertEqual(r['reason'], 'SUCCESS')
        self.assertFalse(r['stdout']['truncated'])
        self.assertFalse(r['stderr']['truncated'])

    def test_prefix_hash_describes_only_retained_bytes(self):
        r = self.capture("import os;os.write(2,b'0123456789')", limit=5)
        self.assertEqual(r['stderr']['prefix_sha256'], hashlib.sha256(b'01234').hexdigest())

    def test_close_pipes_without_exit_still_times_out(self):
        r = self.capture("import os,time;os.close(1);os.close(2);time.sleep(5)", timeout=.08)
        self.assertEqual(r['reason'], 'TIMEOUT')
        self.assertEqual(r['cleanup']['output'], 'COMPLETE')

    def test_capture_exception_text_not_retained(self):
        r = self.capture("import os,time;os.write(2,b'data');time.sleep(5)",
                         read_error=OSError('SECRET-error-message'))
        self.assertEqual(r['reason'], 'CAPTURE_ERROR')
        self.assertNotIn('SECRET-error-message', json.dumps(r))
        self.assertEqual(r['failure_class'], 'OSError')

    def test_selector_setup_failure_still_stops_and_reaps(self):
        r = self.capture("import time;time.sleep(5)", selector_error=True)
        self.assertEqual(r['reason'], 'CAPTURE_ERROR')
        self.assertEqual(r['cleanup']['group_signal'], 'SENT')
        self.assertEqual(r['cleanup']['direct_process'], 'EXITED')
        self.assertNotIn('SECRET-selector', json.dumps(r))

    def test_keyboard_interrupt_is_failure_and_requires_propagation(self):
        r = self.capture("import os,time;os.write(1,b'data');time.sleep(5)",
                         read_error=KeyboardInterrupt('SECRET'))
        self.assertEqual(r['reason'], 'INTERRUPTED')
        self.assertTrue(r['interruption_requires_propagation'])
        self.assertEqual(r['cleanup']['direct_process'], 'EXITED')
        self.assertNotIn('SECRET', json.dumps(r))

    def test_signal_denied_is_unknown_and_does_not_reset_cleanup_deadline(self):
        start = time.monotonic()
        r = self.capture("import time;time.sleep(5)", timeout=.06, cleanup=.06,
                         kill_error=PermissionError('SECRET'))
        self.assertLess(time.monotonic() - start, .65)
        self.assertEqual(r['cleanup']['group_signal'], 'FAILED')
        self.assertEqual(r['cleanup']['direct_process'], 'UNKNOWN')
        self.assertEqual(r['cleanup']['descendants'], 'UNKNOWN')
        self.assertNotIn('SECRET', json.dumps(r))

    def test_signal_exit_race_is_not_claimed_contained(self):
        r = self.capture("import time;time.sleep(.12)", timeout=.05, cleanup=.15,
                         kill_error=ProcessLookupError('gone'))
        self.assertEqual(r['cleanup']['group_signal'], 'NOT_FOUND')
        self.assertEqual(r['cleanup']['descendants'], 'UNKNOWN')

    def test_interruption_during_cleanup_is_not_silently_lost(self):
        r = self.capture("import time;time.sleep(5)", timeout=.05, cleanup=.05,
                         kill_error=KeyboardInterrupt('SECRET'))
        self.assertEqual(r['reason'], 'TIMEOUT')
        self.assertTrue(r['interruption_requires_propagation'])
        self.assertEqual(r['cleanup']['signal_error_class'], 'KeyboardInterrupt')
        self.assertNotIn('SECRET', json.dumps(r))

    def test_close_error_still_reaps_and_suppresses_message(self):
        r = self.capture("import time;time.sleep(5)", timeout=.05, close_error=True)
        self.assertEqual(r['cleanup']['stdout_close_error_class'], 'OSError')
        self.assertEqual(r['cleanup']['direct_process'], 'EXITED')
        self.assertNotIn('SECRET-close-error', json.dumps(r))

    def test_non_session_process_rejected_without_signalling_it(self):
        p = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(.2)'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        try:
            with patch.object(evidence.os, 'killpg') as kill:
                with self.assertRaisesRegex(evidence.EvidenceError, 'OWNED_GROUP'):
                    evidence.capture_owned_process(p, PHASE, OP, 7, 1, .05)
                kill.assert_not_called()
        finally:
            p.wait(timeout=1)
            p.stdout.close()
            p.stderr.close()

    def test_reaped_parent_with_escaped_pipe_and_reused_pgid_never_signalled(self):
        code = ("import os,time\np=os.fork()\nif p==0:\n os.setsid()\n"
                " os.write(2,b'escaped pipe holder')\n time.sleep(.6)\n os._exit(0)\n"
                "os._exit(0)")
        p = subprocess.Popen([sys.executable, '-I', '-B', '-c', code],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, bufsize=0, start_new_session=True)
        p.wait(timeout=1)  # Deliberately free its numeric PID before capture.
        with patch.object(evidence.os, 'getpgid', return_value=p.pid) as pgid, \
                patch.object(evidence.os, 'getsid', return_value=p.pid) as sid, \
                patch.object(evidence.os, 'killpg') as kill:
            r = evidence.capture_owned_process(p, PHASE, OP, 7, 1, .05, .05, 1024)
        kill.assert_not_called()
        pgid.assert_not_called()
        sid.assert_not_called()
        self.assertEqual(r['reason'], 'TIMEOUT')
        self.assertEqual(r['cleanup']['group_signal'], 'SKIPPED_UNPROVEN')
        self.assertEqual(r['cleanup']['descendants'], 'UNKNOWN')
        self.assertEqual(r['cleanup']['output'], 'INCOMPLETE')

    def test_reaped_child_with_stale_returncode_never_signalled(self):
        p = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'pass'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             bufsize=0, start_new_session=True)
        p.wait(timeout=1)
        try:
            p.returncode = None  # Stale caller state cannot replace waitid proof.
            with patch.object(p, 'poll', side_effect=AssertionError('must not reap')), \
                    patch.object(evidence.os, 'getpgid', return_value=p.pid), \
                    patch.object(evidence.os, 'getsid', return_value=p.pid), \
                    patch.object(evidence.os, 'killpg') as kill:
                self.assertEqual(evidence._signal_owned_group(p), 'SKIPPED_UNPROVEN')
            kill.assert_not_called()
        finally:
            p.returncode = 0
            p.stdout.close()
            p.stderr.close()

    def test_no_child_waitability_beats_reused_group_identity(self):
        p = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'pass'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             bufsize=0, start_new_session=True)
        p.wait(timeout=1)
        try:
            p.returncode = None
            with patch.object(p, 'poll', return_value=None), \
                    patch.object(evidence.os, 'waitid', side_effect=ChildProcessError('SECRET')), \
                    patch.object(evidence.os, 'getpgid', return_value=p.pid), \
                    patch.object(evidence.os, 'getsid', return_value=p.pid), \
                    patch.object(evidence.os, 'killpg') as kill:
                self.assertEqual(evidence._signal_owned_group(p), 'SKIPPED_UNPROVEN')
            kill.assert_not_called()
        finally:
            p.returncode = 0
            p.stdout.close()
            p.stderr.close()

    def test_unavailable_wait_owner_lock_skips_signal(self):
        p = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(.15)'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             bufsize=0, start_new_session=True)
        lock = threading.Lock()
        lock.acquire()
        try:
            with patch.object(p, '_waitpid_lock', lock), \
                    patch.object(p, 'poll', return_value=None), \
                    patch.object(evidence.os, 'killpg') as kill:
                self.assertEqual(evidence._signal_owned_group(p), 'SKIPPED_UNPROVEN')
            kill.assert_not_called()
        finally:
            lock.release()
            p.wait(timeout=1)
            p.stdout.close()
            p.stderr.close()

    def test_invalid_process_lookup_handoff_never_signals(self):
        p = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(.15)'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             bufsize=0, start_new_session=True)
        try:
            with patch.object(evidence.os, 'getpgid', side_effect=ProcessLookupError('SECRET')), \
                    patch.object(p, 'poll', return_value=None), \
                    patch.object(evidence.os, 'killpg') as kill:
                with self.assertRaisesRegex(evidence.EvidenceError, '^EVIDENCE_OWNED_GROUP$'):
                    evidence.capture_owned_process(p, PHASE, OP, 7, 1, .05)
            kill.assert_not_called()
        finally:
            p.wait(timeout=1)
            p.stdout.close()
            p.stderr.close()

    def test_invalid_label_rejected_before_process_access(self):
        for phase, operation in ((PHASE, 'Bearer-secret'), ('SECRET', OP)):
            with self.assertRaises(evidence.EvidenceError):
                evidence.capture_owned_process(None, phase, operation, 7, 1, 1)

    def test_invalid_limits_rejected(self):
        for timeout in (0, -1, float('inf'), float('nan'), True, 601):
            with self.assertRaises(evidence.EvidenceError):
                evidence.capture_owned_process(None, PHASE, OP, 7, 1, timeout)
        for limit in (0, -1, True, 1048577):
            with self.assertRaises(evidence.EvidenceError):
                evidence.capture_owned_process(None, PHASE, OP, 7, 1, 1, 1, limit)
        for cleanup in (0, -1, 2.1, float('nan'), True):
            with self.assertRaises(evidence.EvidenceError):
                evidence.capture_owned_process(None, PHASE, OP, 7, 1, 1, cleanup)

    def test_no_communicate_launcher_or_unbounded_wait(self):
        tree = ast.parse(pathlib.Path(evidence.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ('communicate', 'Popen', 'run', 'system'))
                if node.func.attr == 'wait':
                    self.assertTrue(any(k.arg == 'timeout' for k in node.keywords))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.chmod(self.temp.name, 0o700)
        self.uid, self.gid = os.geteuid(), os.getegid()
        self.value = dict(schema=1, failed_stage=PHASE + '_INTENT', operation=OP,
                          epoch=7, sequence=1, reason='EXIT_NONZERO', returncode=1,
                          stderr={'prefix_b64': base64.b64encode(b'SECRET').decode()})

    def tearDown(self):
        self.temp.cleanup()

    def publish(self):
        return evidence.publish_protected(self.temp.name, self.value, self.uid, self.gid)

    def test_private_fsync_publication_and_safe_reference(self):
        ref = self.publish()
        path = pathlib.Path(self.temp.name) / ref['name']
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.stat().st_nlink, 1)
        public = evidence.failure_patch(self.value, ref)
        self.assertEqual(public['command_failure']['diagnostic_state'], 'PERSISTED_PRIVATE')
        self.assertNotIn('SECRET', json.dumps(public))

    def test_existing_evidence_never_overwritten(self):
        ref = self.publish()
        before = (pathlib.Path(self.temp.name) / ref['name']).read_bytes()
        self.value['returncode'] = 99
        with self.assertRaisesRegex(evidence.EvidenceError, 'PERSISTENCE_UNCONFIRMED'):
            self.publish()
        self.assertEqual((pathlib.Path(self.temp.name) / ref['name']).read_bytes(), before)

    def test_evidence_symlink_rejected(self):
        target = pathlib.Path(self.temp.name) / 'other'
        target.write_text('unchanged')
        os.symlink(str(target), self.temp.name + '/command-e7-n0001.json')
        with self.assertRaises(evidence.EvidenceError):
            self.publish()
        self.assertEqual(target.read_text(), 'unchanged')

    def test_directory_permissions_rejected(self):
        os.chmod(self.temp.name, 0o750)
        with self.assertRaises(evidence.EvidenceError):
            self.publish()
        self.assertEqual(os.listdir(self.temp.name), [])

    def test_directory_alias_rejected(self):
        alias = self.temp.name + '/alias'
        os.symlink(self.temp.name, alias)
        with self.assertRaises(evidence.EvidenceError):
            evidence.publish_protected(alias, self.value, self.uid, self.gid)

    def test_write_failure_keeps_partial_private_receipt_and_public_unavailable(self):
        with patch.object(evidence.os, 'write', side_effect=OSError('SECRET')):
            with self.assertRaisesRegex(evidence.EvidenceError, '^EVIDENCE_PERSISTENCE_UNCONFIRMED$'):
                self.publish()
        path = pathlib.Path(self.temp.name) / 'command-e7-n0001.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_bytes(), b'')
        self.assertEqual(evidence.public_summary(self.value)['diagnostic_state'], 'UNAVAILABLE')

    def test_failed_directory_fsync_does_not_claim_durability(self):
        with patch.object(evidence.os, 'fsync', side_effect=OSError('disk')):
            with self.assertRaises(evidence.EvidenceError):
                self.publish()
        self.assertTrue(os.path.isfile(self.temp.name + '/command-e7-n0001.json'))

    def test_mismatched_reference_rejected(self):
        for ref in ({'name': '../../leak', 'sha256': 'a' * 64},
                    {'name': 'command-e7-n0001.json', 'sha256': 'SECRET'},
                    {'name': 'command-e7-n0001.json', 'sha256': 'a' * 64, 'stderr': 'SECRET'}):
            with self.assertRaises(evidence.EvidenceError):
                evidence.public_summary(self.value, ref)

    def test_success_cannot_form_failure_patch(self):
        self.value['reason'] = 'SUCCESS'
        with self.assertRaises(evidence.EvidenceError):
            evidence.failure_patch(self.value)

    def test_stage_suffix_and_schema_cannot_smuggle_content(self):
        self.value['failed_stage'] = PHASE + '_SECRET'
        with self.assertRaises(evidence.EvidenceError):
            evidence.public_summary(self.value)
        self.value['failed_stage'] = PHASE + '_INTENT'
        self.value['schema'] = {'secret': 'SECRET'}
        with self.assertRaises(evidence.EvidenceError):
            evidence.public_summary(self.value)

    def test_reference_is_not_available_after_failed_write(self):
        with patch.object(evidence.os, 'write', return_value=0):
            with self.assertRaises(evidence.EvidenceError):
                self.publish()
        patch_value = evidence.failure_patch(self.value)
        self.assertEqual(patch_value['failed_stage'], PHASE + '_INTENT')
        self.assertEqual(patch_value['command_failure']['diagnostic_state'], 'UNAVAILABLE')
        self.assertNotIn('diagnostic_reference', patch_value['command_failure'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
