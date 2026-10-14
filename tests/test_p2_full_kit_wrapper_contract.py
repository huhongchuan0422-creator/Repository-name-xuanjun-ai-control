"""Synthetic wrapper-contract checks; these do not replace actual kit CI."""
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

SOURCE = pathlib.Path(__file__).with_name('test_p2_full_kit_checkpoint.py')
spec = importlib.util.spec_from_file_location('p2_full_kit_wrapper_under_test', str(SOURCE))
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
HEAD = 'a' * 40


class WrapperContractTests(unittest.TestCase):
    def exercise(self, changes=None, exit_code=0, missing=False, timeout=False):
        with tempfile.TemporaryDirectory(prefix='wrapper-contract-') as root:
            repo = pathlib.Path(root)
            generator = repo / 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/run_published_kit_ci.py'
            generator.parent.mkdir(parents=True)
            if not missing:
                generator.write_text('# synthetic; never executed\n')
            report = dict(success=True, kit_source_commit=HEAD, reproducible_build=True,
                          verified_archive_roundtrip=True, test_exit_code=0, host_operations='NOT_RUN')
            report['bootstrap_tests'] = dict(kind='EXACT_PUBLISHED_BOOTSTRAP_UNIT_EVIDENCE_ONLY',
                success=True, tests=134, failures=0, errors=0, skipped=0, exit_code=0,
                source_map_sha256='b'*64, log_sha256='c'*64)
            report.update(changes or {})
            child = mock.Mock()
            child.returncode = None
            child.pid = 99999999
            child.wait.side_effect = [subprocess.TimeoutExpired('synthetic', 600), 0] if timeout else None
            child.wait.return_value = exit_code
            calls = []
            def spawn(command, **kwargs):
                calls.append((command, kwargs))
                output = pathlib.Path(command[command.index('--output') + 1])
                output.mkdir()
                (output / 'ci-summary.json').write_text(json.dumps(report))
                return child
            with mock.patch.object(wrapper, '__file__', str(repo / 'tests/test_p2_full_kit_checkpoint.py')), \
                 mock.patch.object(wrapper.subprocess, 'check_output', return_value=(HEAD+'\n').encode()), \
                 mock.patch.object(wrapper.subprocess, 'Popen', side_effect=spawn), \
                 mock.patch.object(wrapper.os, 'killpg') as kill:
                try:
                    wrapper.P2FullKitCheckpoint().test_exact_published_recovery_kit()
                finally:
                    if timeout:
                        kill.assert_called_once_with(child.pid, wrapper.signal.SIGKILL)
                        self.assertEqual(child.wait.call_count, 2)
                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0][1]['start_new_session'])
                self.assertEqual(calls[0][1]['env']['PYTHONDONTWRITEBYTECODE'], '1')
                kill.assert_not_called()
    def test_exact_success_is_required(self): self.exercise()
    def test_failure_status_rejected(self):
        with self.assertRaises(AssertionError): self.exercise(exit_code=1)
    def test_wrong_commit_rejected(self):
        with self.assertRaises(AssertionError): self.exercise({'kit_source_commit':'b'*40})
    def test_missing_required_generator_rejected(self):
        with self.assertRaises(AssertionError): self.exercise(missing=True)
    def test_false_success_rejected(self):
        with self.assertRaises(AssertionError): self.exercise({'success':False})
    def test_non_reproducible_result_rejected(self):
        with self.assertRaises(AssertionError): self.exercise({'reproducible_build':False})
    def test_host_effect_claim_rejected(self):
        with self.assertRaises(AssertionError): self.exercise({'host_operations':'RUN'})
    def test_missing_bootstrap_rejected(self):
        with self.assertRaises(AssertionError): self.exercise({'bootstrap_tests':None})
    def test_bootstrap_skip_rejected(self):
        invalid=dict(kind='EXACT_PUBLISHED_BOOTSTRAP_UNIT_EVIDENCE_ONLY',success=True,
                     tests=134,failures=0,errors=0,skipped=1,exit_code=0)
        with self.assertRaises(AssertionError): self.exercise({'bootstrap_tests':invalid})
    def test_timeout_is_failure(self):
        with self.assertRaises(AssertionError): self.exercise(timeout=True)


if __name__ == '__main__': unittest.main()
