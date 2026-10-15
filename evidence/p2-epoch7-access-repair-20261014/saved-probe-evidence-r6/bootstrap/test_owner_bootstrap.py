"""Local compile/fixture tests only. Never run the shell or contact a host."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import time
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
COMMIT = '1' * 40  # Synthetic immutable reference for mocked downloads only.


def source(name=None):
    if name is None:
        name = 'OWNER_COMMAND_FOR_REVIEW.txt' if (HERE/'OWNER_COMMAND_FOR_REVIEW.txt').exists() else 'OWNER_COMMAND_NOT_READY.txt'
    text = (HERE/name).read_text()
    prefix, body = text.split("sudo /usr/libexec/platform-python3.6 -I -B -S - <<'PY'\n", 1)
    assert body.endswith('\nPY\n')
    return body[:-4]


def module():
    result = types.ModuleType('reviewed_bootstrap_test')
    exec(compile(source(), '<bootstrap-compile-fixture>', 'exec'), result.__dict__)
    result.WRAPPER_COMMIT = COMMIT
    return result


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.d = module(); self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(self.d.os, 'geteuid', return_value=0))
        self.stack.enter_context(mock.patch.object(self.d.os, 'getegid', return_value=0))
        self.stack.enter_context(mock.patch.object(self.d.socket, 'gethostname', return_value=self.d.HOST))
        self.stack.enter_context(mock.patch.object(self.d.sys, 'flags', types.SimpleNamespace(isolated=1,no_site=1)))
        self.stack.enter_context(mock.patch.object(self.d.sys, 'dont_write_bytecode', True))
        self.raw = b'# synthetic verified wrapper\n'
        self.d.WRAPPER_BYTES = len(self.raw); self.d.WRAPPER_SHA256 = hashlib.sha256(self.raw).hexdigest()
        self.fetch = self.stack.enter_context(mock.patch.object(self.d, 'fetch_wrapper', return_value=self.raw))
        self.invoke = self.stack.enter_context(mock.patch.object(self.d, 'invoke_verified', return_value=0))
        self.random = self.stack.enter_context(mock.patch.object(self.d.os, 'urandom', side_effect=[b'a'*8,b'b'*16]))
    def run_main(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output): code = self.d.main()
        return code, [json.loads(row) for row in output.getvalue().splitlines()]
    def test_one_invocation_without_nonce_or_probe_flags(self):
        code,rows=self.run_main();self.assertEqual(code,0);self.random.assert_not_called()
        self.assertEqual(rows[0]['wrapper_commit'],COMMIT);self.invoke.assert_called_once_with(self.raw)
    def test_wrong_host_stops_before_download(self):
        with mock.patch.object(self.d.socket, 'gethostname', return_value='wrong'):
            self.assertEqual(self.run_main()[0], 2)
        self.fetch.assert_not_called(); self.random.assert_not_called()
    def test_nonroot_stops_before_download(self):
        with mock.patch.object(self.d.os, 'geteuid', return_value=1000): self.assertEqual(self.run_main()[0], 2)
        self.fetch.assert_not_called()
    def test_wrong_group_stops_before_download(self):
        with mock.patch.object(self.d.os, 'getegid', return_value=1000): self.assertEqual(self.run_main()[0], 2)
        self.fetch.assert_not_called()
    def test_nonisolated_stops_before_download(self):
        with mock.patch.object(self.d.sys, 'flags', types.SimpleNamespace(isolated=0,no_site=1)):
            self.assertEqual(self.run_main()[0], 2)
        self.fetch.assert_not_called()
    def test_unresolved_commit_stops_before_download(self):
        self.d.WRAPPER_COMMIT = 'REPLACE_WITH_VERIFIED_IMMUTABLE_WRAPPER_COMMIT'
        code, rows = self.run_main(); self.assertEqual(code, 2)
        self.assertEqual(rows[-1]['failure_code'], 'IMMUTABLE_COMMIT_NOT_SET'); self.fetch.assert_not_called()
    def test_wrong_wrapper_hash_never_executes_or_allocates_identifiers(self):
        self.fetch.return_value = b'changed'
        self.assertEqual(self.run_main()[0], 2); self.invoke.assert_not_called(); self.random.assert_not_called()
    def test_network_failure_is_static_and_never_retried(self):
        self.fetch.side_effect = OSError('PRIVATE exception response')
        code, rows = self.run_main(); self.assertEqual(code, 2)
        self.assertNotIn('PRIVATE', repr(rows)); self.fetch.assert_called_once(); self.invoke.assert_not_called()
    def test_wrapper_nonzero_preserved_without_retry(self):
        self.invoke.return_value = 2
        self.assertEqual(self.run_main()[0], 2); self.invoke.assert_called_once()
    def test_partial_interruption_is_hold(self):
        self.invoke.side_effect = KeyboardInterrupt()
        code, rows = self.run_main(); self.assertEqual(code, 2)
        self.assertEqual(rows[-1]['stage'], 'WRAPPER_DIAGNOSTIC'); self.assertEqual(rows[-1]['failure_code'], 'INTERRUPTED')


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.d = module(); self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.url = self.d.RAW_PREFIX + COMMIT + '/' + self.d.WRAPPER_PATH
        self.response = mock.Mock(status=200, headers={'Content-Length':str(self.d.WRAPPER_BYTES)})
        self.response.geturl.return_value = self.url; self.response.read.return_value = b'fixed bytes'
        self.response.__enter__ = mock.Mock(return_value=self.response); self.response.__exit__ = mock.Mock(return_value=False)
        self.opener = mock.Mock(); self.opener.open.return_value = self.response
        self.build = self.stack.enter_context(mock.patch.object(self.d.urllib.request, 'build_opener', return_value=self.opener))
    def test_read_cap_no_proxy_alarm_cleared(self):
        before = signal.getsignal(signal.SIGALRM)
        self.assertEqual(self.d.fetch_wrapper(), b'fixed bytes')
        self.response.read.assert_called_once_with(self.d.WRAPPER_BYTES+1)
        self.assertEqual(self.opener.open.call_args[1]['timeout'], 10)
        self.assertEqual(self.opener.open.call_args[0][0].full_url, self.url)
        self.assertEqual(self.build.call_args[0][0].proxies, {})
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0,0.0)); self.assertEqual(signal.getsignal(signal.SIGALRM), before)
    def test_redirect_handler_refuses(self):
        with self.assertRaises(self.d.Hold): self.d.NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid')
    def test_response_url_refused(self):
        self.response.geturl.return_value = 'https://other.invalid'
        with self.assertRaises(self.d.Hold): self.d.fetch_wrapper()
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0,0.0))
    def test_bad_status_refused(self):
        self.response.status = 404
        with self.assertRaises(self.d.Hold): self.d.fetch_wrapper()
    def test_content_encoding_refused(self):
        self.response.headers['Content-Encoding'] = 'gzip'
        with self.assertRaises(self.d.Hold): self.d.fetch_wrapper()
    def test_content_length_refused_before_read(self):
        self.response.headers['Content-Length'] = str(self.d.WRAPPER_BYTES+1)
        with self.assertRaises(self.d.Hold): self.d.fetch_wrapper()
        self.response.read.assert_not_called()
    def test_existing_timer_refused_without_changing_it(self):
        with mock.patch.object(self.d.signal, 'getitimer', return_value=(5.0,0.0)), mock.patch.object(self.d.signal, 'setitimer') as timer:
            with self.assertRaises(self.d.Hold): self.d.fetch_wrapper()
            timer.assert_not_called(); self.opener.open.assert_not_called()
    def test_real_timeout_unwinds_and_clears_alarm(self):
        self.response.read.side_effect = lambda *unused: time.sleep(0.3)
        actual = signal.setitimer
        def short(which, seconds, interval=0): return actual(which, 0.02 if seconds else 0, 0.02 if interval else 0)
        with mock.patch.object(self.d.signal, 'setitimer', side_effect=short):
            with self.assertRaises(self.d.DownloadTimeout): self.d.fetch_wrapper()
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0,0.0)); self.response.__exit__.assert_called_once()


class VerifiedExecutionTests(unittest.TestCase):
    def setUp(self): self.d = module()
    def test_no_temp_file_or_main_autorun_and_only_diagnostic_flags(self):
        raw = b'''assert __name__ != "__main__"
assert __file__.startswith("<verified-owner-diagnostic-")
def main():
    return 0
'''
        self.d.WRAPPER_BYTES = len(raw); self.d.WRAPPER_SHA256 = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self.d.invoke_verified(raw), 0)
    def test_unverified_bytes_never_compile_or_execute(self):
        with self.assertRaises(self.d.Hold): self.d.invoke_verified(b'raise RuntimeError("EXECUTED")')
    def test_armed_alarm_blocks_verified_execution(self):
        raw=b'raise RuntimeError("EXECUTED")'; self.d.WRAPPER_BYTES=len(raw); self.d.WRAPPER_SHA256=hashlib.sha256(raw).hexdigest()
        with mock.patch.object(self.d.signal, 'getitimer', return_value=(1.0,0.0)):
            with self.assertRaisesRegex(self.d.Hold, 'TIMER_NOT_CLEARED'): self.d.invoke_verified(raw)
    def test_actual_frozen_wrapper_size_hash_and_compile_only(self):
        raw=(HERE.parent/'export_saved_evidence.py').read_bytes()
        self.assertEqual(len(raw),29149); self.assertEqual(hashlib.sha256(raw).hexdigest(),self.d.WRAPPER_SHA256)
        compile(raw,'<frozen-wrapper-compile-only>','exec')
    def test_immutable_reference_and_placeholder_versions_compile(self):
        self.assertEqual(self.d.WRAPPER_COMMIT, COMMIT)
        self.assertEqual(self.d.WRAPPER_PATH,'evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/export_saved_evidence.py')
        compile(source('OWNER_COMMAND_NOT_READY.txt'), '<placeholder-compile-only>', 'exec')


if __name__ == '__main__': unittest.main()
