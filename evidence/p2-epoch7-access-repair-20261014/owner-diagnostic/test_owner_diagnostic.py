"""Local fixture/mocked boundary tests. No network or UK execution."""
import contextlib
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import types
import unittest
from unittest import mock

import owner_diagnostic as d

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ARCHIVE = TOOLS / 'build-3b87d10b-a/epoch7-recovery-kit.tar.gz'
EXTRACTED = TOOLS / 'verified-3b87d10b/epoch7-recovery-candidate'


@contextlib.contextmanager
def no_alarm(unused):
    yield


def observation(probe=False, success=True):
    return {'operation': 'observe-and-probe' if probe else 'observe-only',
        'kind': 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED' if success else 'EPOCH7_OBSERVATION_ONLY_HOLD',
        'probe_stage': 'RESULT_RECORDED' if probe else 'NOT_REQUESTED',
        'independent_acceptance': 'PENDING', 'install_admission': 'NOT_GRANTED',
        'production_resume': 'NOT_EXECUTED', 'private_file_sha256': '1' * 64,
        'snapshot_sha256': '2' * 64 if success else None, 'policy_sha256': '3' * 64 if success else None,
        'kit_manifest_sha256': d.MANIFEST_SHA, 'success': success, 'probe_observations_complete': probe}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.host = self.stack.enter_context(mock.patch.object(d, 'host_boundary'))
        self.download = self.stack.enter_context(mock.patch.object(d, 'download', return_value=b'checked'))
        self.extractor = object()
        self.module = self.stack.enter_context(mock.patch.object(d, 'authenticated_module', return_value=self.extractor))
        self.outputs = self.stack.enter_context(mock.patch.object(d, 'check_outputs'))
        self.entry = mock.Mock(); self.kit = mock.Mock()
        self.kit.observe.return_value = observation()
        self.stage = self.stack.enter_context(mock.patch.object(d, 'stage_kit', return_value=(self.entry, self.kit, 'VERIFIED_EXISTING')))
        self.acl = self.stack.enter_context(mock.patch.object(d, 'exact_uid_test', return_value={'success': True, 'tests': 1, 'skipped': 0}))
        self.receipt = self.stack.enter_context(mock.patch.object(d, 'write_receipt', return_value='4' * 64))
    def run_once(self, **kwargs):
        return d.run('a' * 16, execute_reviewed_diagnostic=True, **kwargs)
    def test_no_ack_means_no_host_or_network(self):
        result = d.run('a' * 16)
        self.assertFalse(result['success']); self.host.assert_not_called(); self.download.assert_not_called()
    def test_bad_identifier_stops_before_host(self):
        for value in ('../bad', 'a' * 15, 'A' * 16, None, 123):
            self.assertFalse(d.run(value, execute_reviewed_diagnostic=True)['success'])
        self.host.assert_not_called()
    def test_nonce_without_probe_ack_refused(self):
        self.assertFalse(self.run_once(nonce='b' * 32)['success']); self.host.assert_not_called()
    def test_probe_ack_without_nonce_refused(self):
        self.assertFalse(self.run_once(execute_reviewed_probe=True)['success']); self.host.assert_not_called()
    def test_bad_nonce_refused(self):
        self.assertFalse(self.run_once(nonce='../x', execute_reviewed_probe=True)['success']); self.host.assert_not_called()
    def test_default_observation_is_one_call_without_probe(self):
        result = self.run_once(); self.assertTrue(result['success'])
        self.kit.observe.assert_called_once_with(d.BASE + '/epoch7-observation-' + 'a' * 16 + '.private.json', None, False)
        self.assertEqual(result['production_resume'], 'NOT_EXECUTED'); self.entry.verify_kit.assert_called_once_with(d.KIT, d.MANIFEST_SHA)
        self.receipt.assert_called_once()
    def test_explicit_probe_one_call(self):
        self.kit.observe.return_value = observation(True)
        result = self.run_once(nonce='b' * 32, execute_reviewed_probe=True)
        self.assertTrue(result['success']); self.assertFalse(result['approval_obtained_by_wrapper'])
        self.kit.observe.assert_called_once_with(d.BASE + '/epoch7-observation-' + 'a' * 16 + '.private.json', 'b' * 32, True)
    def test_acl_failure_keeps_observation_but_blocks_probe(self):
        self.acl.return_value = {'success': False, 'tests': 1, 'skipped': 1}
        result = self.run_once(nonce='b' * 32, execute_reviewed_probe=True)
        self.assertFalse(result['success']); self.assertTrue(result['probe_blocked_by_acl'])
        self.assertEqual(self.kit.observe.call_args[0][1:], (None, False))
        self.receipt.assert_called_once()
    def test_snapshot_hold_is_preserved(self):
        self.kit.observe.return_value = observation(success=False)
        result = self.run_once(); self.assertFalse(result['success']); self.assertEqual(result['stage'], 'HOLD_RECORDED')
    def test_consumed_nonce_stops_before_staging(self):
        self.outputs.side_effect = d.DiagnosticHold('OUTPUT_OR_NONCE_ALREADY_EXISTS')
        result = self.run_once(nonce='b' * 32, execute_reviewed_probe=True)
        self.assertEqual(result['failure_code'], 'OUTPUT_OR_NONCE_ALREADY_EXISTS'); self.stage.assert_not_called()
        self.kit.observe.assert_not_called()
    def test_source_failure_stops_before_tests_or_observe(self):
        self.stage.side_effect = ValueError('untrusted source path')
        self.assertFalse(self.run_once()['success']); self.acl.assert_not_called(); self.kit.observe.assert_not_called()
    def test_fixture_boundary_exception_stops_observation(self):
        self.acl.side_effect = OSError('secret')
        self.assertFalse(self.run_once()['success']); self.kit.observe.assert_not_called()
    def test_reverify_after_observation_exception_and_no_retry(self):
        self.kit.observe.side_effect = ValueError('PRIVATE SECRET')
        result = self.run_once(); self.assertFalse(result['success']); self.assertNotIn('SECRET', json.dumps(result))
        self.entry.verify_kit.assert_called_once(); self.kit.observe.assert_called_once(); self.receipt.assert_not_called()
    def test_post_observation_integrity_failure_is_hold(self):
        self.entry.verify_kit.side_effect = ValueError('changed kit')
        self.assertFalse(self.run_once()['success']); self.receipt.assert_not_called()
    def test_interruption_is_non_success_and_no_resume(self):
        self.kit.observe.side_effect = KeyboardInterrupt()
        result = self.run_once(); self.assertFalse(result['success']); self.assertEqual(result['failure_code'], 'INTERRUPTED')
        self.entry.verify_kit.assert_called_once(); self.kit.resume.assert_not_called()
    def test_primary_interrupt_survives_failed_reverification(self):
        self.kit.observe.side_effect = KeyboardInterrupt()
        self.entry.verify_kit.side_effect = ValueError('secondary secret')
        result = self.run_once()
        self.assertEqual(result['failure_code'], 'INTERRUPTED')
        self.assertEqual(result['reverification'], 'FAILED_OR_INTERRUPTED')
        self.assertFalse(result['success']); self.assertNotIn('secret', repr(result))
    def test_primary_error_survives_failed_reverification(self):
        self.kit.observe.side_effect = d.DiagnosticHold('PRIMARY_ERROR')
        self.entry.verify_kit.side_effect = ValueError('secondary secret')
        result = self.run_once()
        self.assertEqual(result['failure_code'], 'PRIMARY_ERROR')
        self.assertEqual(result['reverification'], 'FAILED_OR_INTERRUPTED')
    def test_unexpected_private_error_never_echoed(self):
        self.receipt.side_effect = RuntimeError('token PRIVATE_EXCEPTION_BYTES')
        result = self.run_once(); self.assertFalse(result['success']); self.assertNotIn('PRIVATE', json.dumps(result))
    def test_observation_cannot_override_fixed_public_status(self):
        self.kit.observe.return_value['production_resume'] = 'PRIVATE_SECRET'
        result = self.run_once(); self.assertFalse(result['success']); self.assertNotIn('SECRET', json.dumps(result))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.raw = b'fixed public object'
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.multiple(d, EXTRACTOR_SIZE=len(self.raw), EXTRACTOR_SHA=d.sha(self.raw)))
        self.stack.enter_context(mock.patch.object(d, 'bounded_stage', no_alarm))
        self.response = mock.Mock(status=200, headers={'Content-Length': str(len(self.raw))})
        self.response.geturl.return_value = d.EXTRACTOR_URL; self.response.read.return_value = self.raw
        self.response.__enter__ = mock.Mock(return_value=self.response); self.response.__exit__ = mock.Mock(return_value=False)
        self.opener = mock.Mock(); self.opener.open.return_value = self.response
        self.build = self.stack.enter_context(mock.patch.object(d.urllib.request, 'build_opener', return_value=self.opener))
    def get(self): return d.download(d.EXTRACTOR_URL, d.EXTRACTOR_SIZE, d.EXTRACTOR_SHA)
    def test_fixed_hash_and_bound(self):
        self.assertEqual(self.get(), self.raw); self.response.read.assert_called_once_with(len(self.raw) + 1)
        self.opener.open.assert_called_once(); self.assertEqual(self.opener.open.call_args[1]['timeout'], 10)
        self.assertEqual(self.build.call_args[0][0].proxies, {})
    def test_arbitrary_network_target_refused(self):
        with self.assertRaises(d.DiagnosticHold): d.download('https://other.invalid/a', d.EXTRACTOR_SIZE, d.EXTRACTOR_SHA)
        self.opener.open.assert_not_called()
    def test_redirect_refused(self):
        with self.assertRaises(d.DiagnosticHold): d.NoRedirect().redirect_request(None, None, 302, 'x', {}, 'https://other.invalid')
    def test_response_url_mismatch(self):
        self.response.geturl.return_value = 'https://other.invalid'
        with self.assertRaises(d.DiagnosticHold): self.get()
    def test_status_mismatch(self):
        self.response.status = 403
        with self.assertRaises(d.DiagnosticHold): self.get()
    def test_encoding_refused(self):
        self.response.headers['Content-Encoding'] = 'gzip'
        with self.assertRaises(d.DiagnosticHold): self.get()
    def test_length_mismatch(self):
        self.response.headers['Content-Length'] = '99999999'
        with self.assertRaises(d.DiagnosticHold): self.get()
        self.response.read.assert_not_called()
    def test_oversize_bytes(self):
        self.response.read.return_value += b'x'
        with self.assertRaises(d.DiagnosticHold): self.get()
    def test_wrong_hash(self):
        self.response.read.return_value = b'X' * len(self.raw)
        with self.assertRaises(d.DiagnosticHold): self.get()
    def test_failure_not_retried(self):
        self.opener.open.side_effect = OSError('network unavailable')
        with self.assertRaises(OSError): self.get()
        self.opener.open.assert_called_once()


class BoundaryTests(unittest.TestCase):
    def test_root_hostname_and_isolation(self):
        with mock.patch.object(d.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(d.DiagnosticHold, 'FIXED_ROOT_HOST_REQUIRED'): d.host_boundary()
        with mock.patch.object(d.os, 'geteuid', return_value=0), mock.patch.object(d.os, 'getegid', return_value=0), mock.patch.object(d.socket, 'gethostname', return_value='wrong'):
            with self.assertRaisesRegex(d.DiagnosticHold, 'FIXED_ROOT_HOST_REQUIRED'): d.host_boundary()
        with mock.patch.object(d.os, 'geteuid', return_value=0), mock.patch.object(d.os, 'getegid', return_value=0), mock.patch.object(d.socket, 'gethostname', return_value=d.HOST), mock.patch.object(d.sys, 'flags', types.SimpleNamespace(isolated=0,no_site=1)):
            with self.assertRaisesRegex(d.DiagnosticHold, 'ISOLATED'): d.host_boundary()
    def test_existing_alarm_refused(self):
        with mock.patch.object(d.signal, 'getitimer', return_value=(1.0, 0.0)):
            with self.assertRaisesRegex(d.DiagnosticHold, 'EXISTING_TIMER'):
                with d.bounded_stage(1): pass
    def test_alarm_restored_and_disarmed_on_error(self):
        prior = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(ValueError):
            with d.bounded_stage(10): raise ValueError('fixture')
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0)); self.assertEqual(signal.getsignal(signal.SIGALRM), prior)
    def test_timer_expiry_is_explicit(self):
        with mock.patch.object(d.signal, 'signal') as handler, mock.patch.object(d.signal, 'setitimer'):
            with d.bounded_stage(10):
                callback = handler.call_args[0][1]
                with self.assertRaises(d.StageTimeout): callback(None, None)
    def test_bad_bootstrap_bytes_never_execute(self):
        with self.assertRaisesRegex(d.DiagnosticHold, 'BOOTSTRAP_HASH'):
            d.authenticated_module(b'raise RuntimeError("EXECUTED")', '0' * 64, 'bad', 'bad')
    def test_silent_result_drops_tracebacks(self):
        result = d.SilentResult(); test = mock.Mock(); test.id.return_value = d.UK_CASE
        result.addError(test, (ValueError, ValueError('SECRET'), None)); result.addFailure(test, (ValueError, ValueError('SECRET'), None))
        result.addSkip(test, 'SECRET'); self.assertNotIn('SECRET', repr((result.errors, result.failures, result.skipped)))
    def test_public_schema_refuses_unknown_digest(self):
        value = observation(); value['private_file_sha256'] = 'SECRET'
        with self.assertRaises(d.DiagnosticHold): d.public_observation(value)
    def test_no_resume_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(d.main(['--observation-id', 'a' * 16, '--operation', 'resume']), 2)
        self.assertEqual(json.loads(output.getvalue())['failure_code'], 'CLI_SCOPE')
    def test_bad_cli_does_not_echo_arbitrary_private_arguments(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(d.main(['--unrecognized', 'PRIVATE_SECRET_BYTES']), 2)
        self.assertNotIn('PRIVATE_SECRET_BYTES', output.getvalue() + errors.getvalue())


class ActualFrozenInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor_raw = (TOOLS / 'extract_epoch7_kit.py').read_bytes()
        cls.extractor = d.authenticated_module(cls.extractor_raw, d.EXTRACTOR_SHA, 'checked_extractor', str(TOOLS / 'extract_epoch7_kit.py'))
        cls.archive = ARCHIVE.read_bytes()
    def test_real_frozen_archive_all233_files(self):
        self.assertEqual(len(self.extractor_raw), d.EXTRACTOR_SIZE)
        self.assertEqual(len(self.archive), d.ARCHIVE_SIZE)
        files, dirs = self.extractor.inspect_archive(self.archive, d.ARCHIVE_SHA, d.ENTRY_SHA, d.MANIFEST_SHA)
        self.assertEqual(len(files), 233); self.assertEqual(d.sha(files[d.UK_TEST]), d.UK_TEST_SHA)
    def test_real_archive_truncation_refused(self):
        with self.assertRaises(ValueError):
            self.extractor.inspect_archive(self.archive[:-1], d.ARCHIVE_SHA, d.ENTRY_SHA, d.MANIFEST_SHA)
    def test_fixed_input_sources_unchanged(self):
        self.assertEqual(d.sha((TOOLS / 'epoch7_recovery_entry.py').read_bytes()), d.ENTRY_SHA)
        self.assertEqual(d.sha((TOOLS / 'public-source-index.json').read_bytes()), '4b69ab76e3c1538a0325a7c3df0d938284965463c04657814d7d9e780e9241e6')
    def test_existing_output_or_nonce_rejected_without_following(self):
        tree = types.SimpleNamespace(fd=17)
        with mock.patch.object(d.os, 'stat', return_value=object()) as stat_call:
            with self.assertRaises(d.DiagnosticHold): d.absent(tree, 'fixed')
            stat_call.assert_called_once_with('fixed', dir_fd=17, follow_symlinks=False)


class ExactSelectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(d, 'bounded_stage', no_alarm))
        self.raw = b'fixture source'
        self.stack.enter_context(mock.patch.object(d, 'UK_TEST_SHA', d.sha(self.raw)))
        self.kit = mock.Mock(cache={d.UK_TEST: self.raw}, manifest={'test_suites': {'uk_exact_uid_acl': {
            'tests': [d.UK_TEST], 'imports': {d.UK_ALIAS: d.UK_TEST}, 'enabled': False}}})
        self.entry = mock.Mock()
        @contextlib.contextmanager
        def workspace(): yield self.kit
        self.kit.test_workspace = workspace
        @contextlib.contextmanager
        def imports(unused): yield
        self.kit.imports = imports
        self.stack.enter_context(mock.patch.object(d.importlib, 'import_module', return_value=object()))
        self.loader = self.stack.enter_context(mock.patch.object(d.unittest.defaultTestLoader, 'loadTestsFromModule'))
    def case(self, behavior='pass', identity=None):
        class Case(unittest.TestCase):
            def id(inner): return identity or d.UK_CASE
            def runTest(inner):
                if behavior == 'skip': inner.skipTest('SECRET')
                if behavior == 'fail': inner.fail('SECRET')
                if behavior == 'error': raise ValueError('SECRET')
        return Case()
    def test_exact_case_passes_without_enabling_manifest(self):
        self.loader.return_value = unittest.TestSuite([self.case()])
        self.assertTrue(d.exact_uid_test(self.entry, self.kit)['success'])
        self.assertFalse(self.kit.manifest['test_suites']['uk_exact_uid_acl']['enabled'])
        self.entry.verify_kit.assert_called_once_with(d.KIT, d.MANIFEST_SHA)
    def test_exact_case_skipped_is_not_success(self):
        self.loader.return_value = unittest.TestSuite([self.case('skip')])
        result = d.exact_uid_test(self.entry, self.kit)
        self.assertFalse(result['success']); self.assertEqual(result['skipped'], 1)
    def test_assertion_failure_does_not_disclose(self):
        self.loader.return_value = unittest.TestSuite([self.case('fail')])
        result = d.exact_uid_test(self.entry, self.kit)
        self.assertFalse(result['success']); self.assertNotIn('SECRET', repr(result))
    def test_fixture_error_does_not_disclose(self):
        self.loader.return_value = unittest.TestSuite([self.case('error')])
        result = d.exact_uid_test(self.entry, self.kit)
        self.assertFalse(result['success']); self.assertEqual(result['errors'], 1)
    def test_zero_cases_refused_and_original_reverified(self):
        self.loader.return_value = unittest.TestSuite([])
        with self.assertRaises(d.DiagnosticHold): d.exact_uid_test(self.entry, self.kit)
        self.entry.verify_kit.assert_called_once()
    def test_extra_case_refused(self):
        self.loader.return_value = unittest.TestSuite([self.case(), self.case()])
        with self.assertRaises(d.DiagnosticHold): d.exact_uid_test(self.entry, self.kit)
    def test_different_case_refused(self):
        self.loader.return_value = unittest.TestSuite([self.case(identity='other.test')])
        with self.assertRaises(d.DiagnosticHold): d.exact_uid_test(self.entry, self.kit)
    def test_changed_source_refused_before_workspace(self):
        self.kit.cache[d.UK_TEST] = b'changed'
        with self.assertRaises(d.DiagnosticHold): d.exact_uid_test(self.entry, self.kit)
        self.loader.assert_not_called()


class RealTimeoutTests(unittest.TestCase):
    def test_alarm_escapes_unittest_before_teardown(self):
        events = []
        class Slow(unittest.TestCase):
            def runTest(inner):
                events.append('body'); time.sleep(0.3); events.append('body_finished')
            def tearDown(inner): events.append('teardown')
        result = d.SilentResult()
        with self.assertRaises(d.StageTimeout):
            with d.bounded_stage(0.02): unittest.TestSuite([Slow()]).run(result)
        self.assertEqual(events, ['body'])
        self.assertEqual(result.errors, [])
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
    def test_periodic_alarm_interrupts_slow_cleanup_and_preserves_primary(self):
        events = []; seen = []
        @contextlib.contextmanager
        def slow_cleanup():
            try: yield
            finally:
                seen.append(signal.getitimer(signal.ITIMER_REAL))
                events.append('cleanup_entered'); time.sleep(0.3); events.append('cleanup_finished')
        with mock.patch.object(d, 'ALARM_CLEANUP_INTERVAL', 0.02):
            with self.assertRaises(d.StageTimeout) as caught:
                with d.bounded_stage(0.02):
                    with d.preserve_cleanup(slow_cleanup(), 'workspace_cleanup'):
                        time.sleep(0.3)
        self.assertEqual(events, ['cleanup_entered'])
        self.assertGreater(seen[0][0], 0); self.assertEqual(seen[0][1], 0.02)
        self.assertTrue(caught.exception.diagnostic_workspace_cleanup_failed)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
    def test_final_reverify_has_a_real_deadline(self):
        entry = mock.Mock(); entry.verify_kit.side_effect = lambda *unused: time.sleep(0.3)
        actual = d.bounded_stage
        with mock.patch.object(d, 'bounded_stage', side_effect=lambda unused: actual(0.02)):
            with self.assertRaises(d.StageTimeout) as caught: d.bounded_reverify(entry)
        self.assertTrue(caught.exception.diagnostic_reverification_failed)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
    def test_cleanup_failure_preserves_original_object(self):
        primary = KeyboardInterrupt()
        @contextlib.contextmanager
        def broken():
            try: yield
            finally: raise ValueError('secondary')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with d.preserve_cleanup(broken(), 'import_cleanup'): raise primary
        self.assertIs(caught.exception, primary); self.assertTrue(primary.diagnostic_import_cleanup_failed)


class ProtectedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory(dir=str(HERE)))
        owners = tuple(sorted(set(((0,0), (os.geteuid(),os.getegid())))))
        self.stack.enter_context(mock.patch.multiple(d, BASE=self.temp, OWNERS=owners))
        self.extractor = d.authenticated_module((TOOLS/'extract_epoch7_kit.py').read_bytes(), d.EXTRACTOR_SHA,
                                               'fixture_extractor', str(TOOLS/'extract_epoch7_kit.py'))
        self.entry = d.authenticated_module((TOOLS/'epoch7_recovery_entry.py').read_bytes(), d.ENTRY_SHA,
                                           'fixture_entry', str(TOOLS/'epoch7_recovery_entry.py'))
        actual = self.entry.DescriptorTree
        self.entry.DescriptorTree = lambda path: actual(path, owners)
        self.path = Path(self.temp)/('epoch7-diagnostic-' + 'a'*16 + '.private.json')
    def write(self): return d.write_receipt(self.extractor, self.entry, 'a'*16, {'schema':1,'success':False})
    def test_real_private_receipt_exclusive_hash_readback(self):
        digest = self.write()
        self.assertEqual(digest, d.sha(self.path.read_bytes())); self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        with self.assertRaises(FileExistsError): self.write()
    def test_symlink_receipt_is_not_followed(self):
        other = Path(self.temp)/'unrelated'; other.write_bytes(b'unchanged')
        self.path.symlink_to(other)
        with self.assertRaises(FileExistsError): self.write()
        self.assertEqual(other.read_bytes(), b'unchanged')
    def test_zero_write_refuses_and_retains_partial_for_review(self):
        with mock.patch.object(d.os, 'write', return_value=0):
            with self.assertRaisesRegex(d.DiagnosticHold, 'SHORT_WRITE'): self.write()
        self.assertTrue(self.path.is_file()); self.assertEqual(self.path.read_bytes(), b'')
    def test_readback_failure_never_reports_digest(self):
        with mock.patch.object(self.entry, 'DescriptorTree', side_effect=ValueError('unknown')):
            with self.assertRaises(ValueError): self.write()
        self.assertTrue(self.path.exists())
    def test_group_writable_ancestry_refused(self):
        os.chmod(self.temp, 0o770)
        with self.assertRaises(ValueError): self.write()
        self.assertFalse(self.path.exists())
    def test_preexisting_output_refused(self):
        (Path(self.temp)/('epoch7-observation-'+'a'*16+'.private.json')).write_bytes(b'prior')
        with self.assertRaises(d.DiagnosticHold): d.check_outputs(self.extractor, 'a'*16, None)
    def test_new_identifiers_pass_without_creating_files(self):
        d.check_outputs(self.extractor, 'a'*16, None)
        self.assertEqual(list(Path(self.temp).iterdir()), [])


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(d, 'bounded_stage', no_alarm))
        self.extractor = mock.Mock()
        self.tree = types.SimpleNamespace(fd=19, check=mock.Mock())
        @contextlib.contextmanager
        def directory(*unused): yield self.tree
        self.extractor.ProtectedDirectory = directory
        self.stat = self.stack.enter_context(mock.patch.object(d.os, 'stat', return_value=object()))
        self.download = self.stack.enter_context(mock.patch.object(d, 'download', return_value=b'archive'))
        self.extractor.read_archive.return_value = b'entry'
        self.kit = types.SimpleNamespace(manifest={'kit_source_commit':d.SOURCE, 'kit_source_tree':d.TREE},
                                         cache={str(i):b'' for i in range(232)})
        self.entry = mock.Mock(); self.entry.verify_kit.return_value = self.kit
        self.module = self.stack.enter_context(mock.patch.object(d, 'authenticated_module', return_value=self.entry))
    def test_existing_candidate_verified_without_download_or_overwrite(self):
        entry, kit, state = d.stage_kit(self.extractor)
        self.assertEqual(state, 'VERIFIED_EXISTING'); self.download.assert_not_called(); self.extractor.extract.assert_not_called()
        self.entry.verify_kit.assert_called_once_with(d.KIT, d.MANIFEST_SHA)
        self.module.assert_called_once_with(b'entry', d.ENTRY_SHA, 'reviewed_epoch7_entry', d.KIT+'/epoch7_recovery_entry.py')
    def test_new_candidate_uses_frozen_safe_extractor_exact_pins(self):
        self.stat.side_effect = FileNotFoundError()
        self.assertEqual(d.stage_kit(self.extractor)[2], 'EXTRACTED_AND_VERIFIED')
        self.download.assert_called_once_with(d.ARCHIVE_URL, d.ARCHIVE_SIZE, d.ARCHIVE_SHA)
        self.extractor.extract.assert_called_once_with(b'archive', d.KIT, d.ARCHIVE_SHA, d.ENTRY_SHA, d.MANIFEST_SHA)
    def test_failed_existing_candidate_never_repaired(self):
        self.extractor.read_archive.side_effect = ValueError('partial or symlink')
        with self.assertRaises(ValueError): d.stage_kit(self.extractor)
        self.download.assert_not_called(); self.extractor.extract.assert_not_called()
    def test_wrong_source_commit_refused(self):
        self.kit.manifest['kit_source_commit'] = '0'*40
        with self.assertRaises(d.DiagnosticHold): d.stage_kit(self.extractor)
    def test_failed_extract_never_retried_or_cleaned(self):
        self.stat.side_effect = FileNotFoundError(); self.extractor.extract.side_effect = OSError('interrupted')
        with self.assertRaises(OSError): d.stage_kit(self.extractor)
        self.extractor.extract.assert_called_once(); self.extractor.read_archive.assert_not_called()


if __name__ == '__main__': unittest.main()
