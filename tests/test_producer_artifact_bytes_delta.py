"""Local runner byte-recovery contract; mocked runtime is not an attestation."""
import hashlib
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import producer_http_runner as runner


class ArtifactBytesTest(unittest.TestCase):
    def test_exact_stdout_bytes_and_legacy_shape(self):
        output = b'{"state":"PASS", "detail":"HTTP_PUBLIC_CONTRACT"}\n'
        source = b'# candidate\n'
        def fake_run(*args, **kwargs):
            kwargs['stdout'].write(output)
            return type('Result', (), {'returncode': 0})()
        with patch.object(runner.subprocess, 'run', side_effect=fake_run):
            observation, artifact = runner.run_producer_http_with_artifact(source)
            legacy = runner.run_producer_http(source)
        self.assertEqual(artifact, output)
        self.assertEqual(observation['artifact_sha256'], hashlib.sha256(artifact).hexdigest())
        self.assertEqual(observation['source_sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(legacy, observation)

    def test_oversize_output_is_not_returned(self):
        def fake_run(*args, **kwargs):
            kwargs['stdout'].write(b'x' * 1025)
            return type('Result', (), {'returncode': 0})()
        with patch.object(runner.subprocess, 'run', side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, 'PRODUCER_HTTP_TEST_UNAVAILABLE'):
                runner.run_producer_http_with_artifact(b'# candidate\n')

if __name__ == '__main__':
    unittest.main()
