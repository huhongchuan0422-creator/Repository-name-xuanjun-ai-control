"""Verify-only successor provenance fixture must accompany pinned OCR tests."""
import hashlib
import json
from pathlib import Path
import unittest


class VerifySuccessorFixture(unittest.TestCase):
    def test_exact_fixture_only_in_verify_stage(self):
        docker = Path('deploy/community-preview/Dockerfile').read_text()
        runtime, remainder = docker.split('FROM runtime AS verify\n', 1)
        verify, release = remainder.split('FROM runtime AS release\n', 1)
        copy = 'COPY deploy/community-preview/ocr-bank-card-successor.patch /app/deploy/community-preview/ocr-bank-card-successor.patch'
        self.assertEqual(verify.count(copy), 1)
        self.assertNotIn(copy, runtime)
        self.assertNotIn(copy, release)
        self.assertLess(verify.index(copy), verify.index('RUN COMMUNITY_TEST_PINNED_OCR_DIR='))
        self.assertIn('test_community_h5_bank_ocr.BankOcr', verify)
        self.assertIn('COPY --chown=10001:1008 verification-upstream/ /opt/verification-upstream/', verify)

    def test_fixture_and_successor_bytes_keep_original_pins(self):
        lock = json.loads(Path('scripts/community_ocr_dependency.json').read_text())
        successor = lock['local_successor']
        self.assertEqual(hashlib.sha256(Path(successor['patch_path']).read_bytes()).hexdigest(), successor['patch_sha256'])
        for name, path in successor['source_files'].items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), lock['files'][name])
