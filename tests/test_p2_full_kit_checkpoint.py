"""Real exact-checkout full-kit gate; synthetic offline tests, no host operation."""
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import unittest


class P2FullKitCheckpoint(unittest.TestCase):
    def test_exact_published_recovery_kit(self):
        repository = pathlib.Path(__file__).resolve().parents[1]
        prefix = 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source'
        generator = repository / prefix / 'tools/run_published_kit_ci.py'
        self.assertTrue(generator.is_file(), 'required full-kit generator missing')
        head = subprocess.check_output(
            ['/usr/bin/git', '-C', str(repository), 'rev-parse', '--verify', 'HEAD'],
            timeout=15).decode('ascii').strip()
        self.assertRegex(head, r'^[0-9a-f]{40}$')
        parent = os.environ.get('RUNNER_TEMP') or tempfile.gettempdir()
        with tempfile.TemporaryDirectory(prefix='p2-full-kit-', dir=parent) as root:
            output = os.path.join(root, 'result')
            env = dict(os.environ, RUNNER_TEMP=root, PYTHONDONTWRITEBYTECODE='1')
            command = [sys.executable, '-I', '-B', '-S', str(generator),
                '--repository', str(repository), '--source-index', prefix + '/public-source-index.json',
                '--runtime-dir', 'evidence/p2-epoch7-access-repair-20261014/runtime',
                '--output', output, '--expected-head', head]
            process = subprocess.Popen(command, cwd=str(repository), env=env, start_new_session=True)
            try:
                status = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                # The unreaped child still owns this process-group identifier.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.fail('FULL_KIT_TIMEOUT_CLEANUP_UNKNOWN')
                self.fail('FULL_KIT_OVERALL_TIMEOUT')
            except BaseException:
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    finally:
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            print('FULL_KIT_INTERRUPTED_CLEANUP_UNKNOWN', flush=True)
                raise
            finally:
                for name in ('mandatory-tests.log', 'bootstrap-tests.log'):
                    log_path = pathlib.Path(output) / name
                    if log_path.is_file():
                        with log_path.open('rb') as stream:
                            stream.seek(0, os.SEEK_END)
                            stream.seek(max(0, stream.tell() - 65536))
                            tail = stream.read(65536)
                        print('FULL_KIT_BOUNDED_SYNTHETIC_LOG_BEGIN ' + name, flush=True)
                        print(tail.decode('utf-8', 'replace'), flush=True)
                        print('FULL_KIT_BOUNDED_SYNTHETIC_LOG_END ' + name, flush=True)
            self.assertEqual(status, 0, 'full-kit source/build/test gate failed')
            summary = pathlib.Path(output) / 'ci-summary.json'
            self.assertTrue(summary.is_file(), 'full-kit summary missing')
            with summary.open('rb') as stream:
                raw = stream.read(1048577)
            self.assertLessEqual(len(raw), 1048576)
            report = json.loads(raw.decode('utf-8'))
            self.assertIs(report.get('success'), True)
            self.assertEqual(report.get('kit_source_commit'), head)
            self.assertIs(report.get('reproducible_build'), True)
            self.assertIs(report.get('verified_archive_roundtrip'), True)
            self.assertEqual(report.get('test_exit_code'), 0)
            self.assertEqual(report.get('host_operations'), 'NOT_RUN')
            bootstrap = report.get('bootstrap_tests')
            self.assertIsInstance(bootstrap, dict)
            self.assertEqual(bootstrap.get('kind'), 'EXACT_PUBLISHED_BOOTSTRAP_UNIT_EVIDENCE_ONLY')
            self.assertIs(bootstrap.get('success'), True)
            self.assertIs(type(bootstrap.get('tests')), int)
            self.assertGreater(bootstrap['tests'], 0)
            for key in ('failures', 'errors', 'skipped', 'exit_code'):
                self.assertIs(type(bootstrap.get(key)), int)
                self.assertEqual(bootstrap[key], 0)
            for key in ('source_map_sha256', 'log_sha256'):
                self.assertRegex(bootstrap.get(key, ''), r'^[0-9a-f]{64}$')
            print('FULL_KIT_CHECKPOINT_PASS_NO_UK_OR_PRODUCTION_ACCEPTANCE', flush=True)


if __name__ == '__main__':
    unittest.main()
