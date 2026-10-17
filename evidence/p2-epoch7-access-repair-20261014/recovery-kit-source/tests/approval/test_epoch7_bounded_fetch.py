"""Offline subprocess tests, including simulated DNS/TLS/read stalls.

No network access, genuine review, host install, or production admission occurs.
The worker subprocesses use this test runner's explicit Python executable, while
production fetch's fixed interpreter/isolated command is checked separately.
"""
import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import epoch7_approval as s


class BoundedFetchTests(unittest.TestCase):
    def setUp(self):
        self.review_id = 7000000000
        self.wanted = s.expected('a' * 64, 'b' * 64, 'c' * 64, 'd' * 64)
        self.url = ('https://api.github.com/repos/' + s.REPO +
                    '/issues/comments/' + str(self.review_id))
        self.raw = json.dumps({'id': self.review_id,
            'user': {'id': 95597695, 'login': '18598789888'},
            'issue_url': 'https://api.github.com/repos/' + s.REPO + '/issues/58',
            'body': s.MARKER + json.dumps(self.wanted)}).encode()
        self.children = []
        self.real_popen = subprocess.Popen

    def tearDown(self):
        for child in self.children:
            self.assertIsNotNone(child.returncode, 'worker not reaped')
            self.assertTrue(child.stdout.closed, 'worker pipe left open')
            with self.assertRaises(ChildProcessError):
                os.waitpid(child.pid, os.WNOHANG)

    def spawn(self, *args, **kwargs):
        child = self.real_popen(*args, **kwargs)
        self.children.append(child)
        return child

    def run_source(self, source, timeout=0.8, cleanup=0.2):
        command = [sys.executable, '-I', '-B', '-S', '-c', source, self.url]
        with mock.patch.object(s.subprocess, 'Popen', side_effect=self.spawn):
            return s._run_worker(command, timeout, cleanup)

    def assert_timeout(self, source):
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'APPROVAL_FETCH_TIMEOUT'):
            self.run_source(source)
        # Loose scheduler tolerance; the 5-second fake waits must never finish.
        self.assertLess(time.monotonic() - start, 1.5)

    def response_fixture(self, body=None, read_code=None, close_code=None,
                         status=200, url=None):
        if body is None:
            body = self.raw
        return '''
import os, sys, time, urllib.request
class Response:
    def __enter__(self): return self
    def __exit__(self, *args):
        {close_code}
    def getcode(self): return {status}
    def geturl(self): return {url}
    def read(self, size):
        assert size == 65537
        {read_code}
class Opener:
    def open(self, request, timeout):
        assert request.full_url == sys.argv[1]
        assert timeout == 20
        assert request.get_header('Accept') == 'application/vnd.github+json'
        return Response()
def fake_build(*handlers):
    assert len(handlers) == 2
    assert isinstance(handlers[0], urllib.request.ProxyHandler)
    assert handlers[0].proxies == {{}}
    try:
        handlers[1].redirect_request(None, None, 302, '', {{}}, 'https://other')
    except ValueError:
        pass
    else:
        raise AssertionError('redirect accepted')
    return Opener()
urllib.request.build_opener = fake_build
'''.format(close_code=close_code or 'return None', status=repr(status),
           url='sys.argv[1]' if url is None else repr(url),
           read_code=read_code or 'return ' + repr(body)) + s._FETCH_WORKER

    def test_worker_success_reaped_and_validated(self):
        raw = self.run_source(self.response_fixture())
        self.assertEqual(s.validate(raw, self.review_id, self.wanted)['approval'],
                         self.wanted)

    def test_fixed_isolated_production_command(self):
        with mock.patch.object(s, '_run_worker', return_value=self.raw) as run:
            self.assertEqual(s.fetch(self.review_id, self.wanted)['approval'], self.wanted)
        command = run.call_args[0][0]
        self.assertEqual(command[:5], ['/usr/bin/python3', '-I', '-B', '-S', '-c'])
        self.assertEqual(command[5], s._FETCH_WORKER)
        self.assertEqual(command[6:], [self.url])

    def test_worker_environment_does_not_inherit_secrets_or_pythonpath(self):
        source = "import os; assert dict(os.environ) == {'PATH':'/usr/bin:/bin','LC_ALL':'C'}; os._exit(0)"
        with mock.patch.dict(os.environ, {'HTTPS_PROXY': 'https://not-used',
                'PYTHONPATH': '/not-used', 'GITHUB_TOKEN': 'fixture-not-a-token'}):
            self.assertEqual(self.run_source(source), b'')

    def test_child_stall_including_ignored_sigterm(self):
        self.assert_timeout('import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(5)')
        self.assertEqual(self.children[-1].returncode, -signal.SIGKILL)

    def test_simulated_dns_stall(self):
        # Real urllib reaches getaddrinfo; the stub prevents any real DNS/socket.
        prefix = '''
import socket,time
def dns(*args, **kwargs): time.sleep(5); raise AssertionError('late DNS')
def no_connect(*args, **kwargs): raise AssertionError('network forbidden')
socket.getaddrinfo = dns
socket.socket.connect = no_connect
'''
        self.assert_timeout(prefix + s._FETCH_WORKER)

    def test_simulated_tls_stall(self):
        # urllib reaches HTTPSConnection.connect; fake handshake never opens TCP.
        prefix = '''
import http.client, ssl, time
class FakeContext:
    def wrap_socket(self, *args, **kwargs): time.sleep(5); raise AssertionError('late TLS')
def handshake(self): FakeContext().wrap_socket(None)
http.client.HTTPSConnection.connect = handshake
'''
        self.assert_timeout(prefix + s._FETCH_WORKER)

    def test_simulated_read_stall(self):
        self.assert_timeout(self.response_fixture(read_code="time.sleep(5); return b'{}'"))

    def test_simulated_drip_read_exceeds_whole_request_budget(self):
        # Each individual read step is short; the aggregate request still expires.
        self.assert_timeout(self.response_fixture(read_code=
            "exec('for unused in range(100):\\n time.sleep(0.03)'); return b'{}'"))

    def test_response_context_close_stall_is_bounded(self):
        self.assert_timeout(self.response_fixture(close_code='time.sleep(5)'))

    def test_drip_stdout_is_bounded_by_total_deadline(self):
        self.assert_timeout("import os,time\nfor unused in range(100):\n os.write(1,b'x'); time.sleep(0.03)\n")

    def test_stdout_eof_without_exit_does_not_count_as_success(self):
        self.assert_timeout('import os,time; os.close(1); time.sleep(5)')

    def test_output_limit_accepts_exact_limit(self):
        self.assertEqual(len(self.run_source(self.response_fixture(b'x' * 65536))), 65536)

    def test_output_limit_rejects_limit_plus_one(self):
        with self.assertRaisesRegex(ValueError, 'APPROVAL_RESPONSE_BOUND'):
            self.run_source(self.response_fixture(b'x' * 65537))

    def test_output_flood_never_waits_for_pipe_cleanup(self):
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'APPROVAL_RESPONSE_BOUND'):
            self.run_source("import os\nwhile True: os.write(1,b'x'*8192)\n")
        self.assertLess(time.monotonic() - start, 1.5)

    def test_stderr_is_not_captured_or_allowed_to_block(self):
        self.assertEqual(self.run_source("import os; os.write(2,b'x'*1000000); os.write(1,b'{}'); os._exit(0)"), b'{}')

    def test_nonzero_worker_with_valid_body_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'APPROVAL_FETCH_FAILED'):
            self.run_source('import os; os.write(1,' + repr(self.raw) + '); os._exit(2)')

    def test_redirected_response_origin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'APPROVAL_FETCH_FAILED'):
            self.run_source(self.response_fixture(url='https://other'))

    def test_non_200_response_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'APPROVAL_FETCH_FAILED'):
            self.run_source(self.response_fixture(status=206))

    def test_malformed_json_or_utf8_fail_after_worker_cleanup(self):
        for body in (b'{', b'\xff', b'{"id":1,"id":2}', b'NaN'):
            raw = self.run_source(self.response_fixture(body))
            with mock.patch.object(s, '_run_worker', return_value=raw):
                with self.assertRaises(ValueError):
                    s.fetch(self.review_id, self.wanted)

    def test_empty_response_fails_closed_after_cleanup(self):
        raw = self.run_source(self.response_fixture(b''))
        with mock.patch.object(s, '_run_worker', return_value=raw):
            with self.assertRaises(ValueError):
                s.fetch(self.review_id, self.wanted)

    def test_provenance_stays_in_parent(self):
        value = json.loads(self.raw.decode())
        value['user']['id'] = 123
        with mock.patch.object(s, '_run_worker', return_value=json.dumps(value).encode()):
            with self.assertRaisesRegex(ValueError, 'APPROVAL_AUTHOR'):
                s.fetch(self.review_id, self.wanted)

    def test_invalid_ids_never_spawn(self):
        with mock.patch.object(s, '_run_worker') as run:
            for review in tuple(s.CONSUMED) + (True, '7000000000', 0, -1):
                with self.assertRaisesRegex(ValueError, 'APPROVAL_FRESH_ID_REQUIRED'):
                    s.fetch(review, self.wanted)
            run.assert_not_called()

    def test_spawn_time_counts_toward_total_deadline(self):
        def slow_spawn(*args, **kwargs):
            child = self.spawn(*args, **kwargs)
            time.sleep(0.3)
            return child
        command = [sys.executable, '-I', '-B', '-S', '-c', 'import time; time.sleep(5)']
        start = time.monotonic()
        with mock.patch.object(s.subprocess, 'Popen', side_effect=slow_spawn):
            with self.assertRaisesRegex(ValueError, 'APPROVAL_FETCH_TIMEOUT'):
                s._run_worker(command, timeout=0.5, cleanup_seconds=0.25)
        self.assertLess(time.monotonic() - start, 0.7)

    def test_select_error_still_closes_and_reaps(self):
        with mock.patch.object(s.selectors, 'DefaultSelector', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                self.run_source('import time; time.sleep(5)')

    def test_keyboard_interrupt_still_closes_and_reaps(self):
        with mock.patch.object(s.selectors, 'DefaultSelector', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_source('import time; time.sleep(5)')

    def test_pipe_held_by_descendant_is_killed_without_hanging(self):
        # Become a subreaper just for this test so killed fixture grandchildren
        # are also reaped here, rather than leaving zombies with container PID 1.
        libc = ctypes.CDLL(None, use_errno=True)
        old = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(old), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        descendant = None
        try:
            with tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)) as root:
                pidfile = os.path.join(root, 'descendant.pid')
                source = '''
import os,time
child = os.fork()
if child == 0:
    time.sleep(5)
    os._exit(0)
with open({pidfile}, 'w') as stream: stream.write(str(child))
os._exit(0)
'''.format(pidfile=repr(pidfile))
                self.assert_timeout(source)
                with open(pidfile) as stream:
                    descendant = int(stream.read())
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    waited, status = os.waitpid(descendant, os.WNOHANG)
                    if waited:
                        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
                        descendant = None
                        break
                    time.sleep(0.01)
                self.assertIsNone(descendant, 'descendant survived process-group cleanup')
        finally:
            if descendant is not None:
                os.kill(descendant, signal.SIGKILL)
                os.waitpid(descendant, 0)
            self.assertEqual(libc.prctl(36, old.value, 0, 0, 0), 0)

    def test_no_unbounded_wait_or_communicate_in_adapter(self):
        # Exercise the real cleanup and record its wait timeout explicitly.
        original = subprocess.Popen.wait
        waits = []
        def bounded_wait(process, timeout=None):
            waits.append(timeout)
            self.assertIsNotNone(timeout)
            return original(process, timeout=timeout)
        with mock.patch.object(subprocess.Popen, 'wait', bounded_wait):
            with mock.patch.object(subprocess.Popen, 'communicate', side_effect=AssertionError('unbounded drain')):
                self.run_source("import os; os.write(1,b'{}'); os._exit(0)")
        self.assertTrue(waits)
        self.assertTrue(all(0 <= value <= 0.8 for value in waits))

    def test_invalid_timeout_contract_never_spawns(self):
        with mock.patch.object(s.subprocess, 'Popen') as spawn:
            for timeout, cleanup in ((float('inf'), 1), (float('nan'), 1),
                    (1, float('nan')), (1, 1), (1, 0), (True, 0.1), ('1', 0.1)):
                with self.assertRaisesRegex(ValueError, 'APPROVAL_TIMEOUT_CONTRACT'):
                    s._run_worker([], timeout, cleanup)
            spawn.assert_not_called()

    def test_pipe_close_error_still_reaps(self):
        process = mock.Mock(pid=12345)
        process.stdout.close.side_effect = OSError('fixture close')
        with mock.patch.object(s.os, 'killpg'):
            with self.assertRaises(OSError):
                s._cleanup_worker(process, time.monotonic() + 0.1)
        process.wait.assert_called_once()
        self.assertGreaterEqual(process.wait.call_args[1]['timeout'], 0)

    def test_cleanup_timeout_cannot_grant_approval(self):
        class Process:
            pid = 12345
            stdout = mock.Mock()
            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired('fixture', timeout)
        process = Process()
        with mock.patch.object(s.os, 'killpg') as kill:
            with self.assertRaisesRegex(ValueError, 'APPROVAL_WORKER_CLEANUP_FAILED'):
                s._cleanup_worker(process, time.monotonic() + 0.1)
        kill.assert_called_once_with(process.pid, signal.SIGKILL)
        process.stdout.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
