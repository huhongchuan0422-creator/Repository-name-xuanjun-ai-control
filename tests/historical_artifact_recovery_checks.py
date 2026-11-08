"""Exact historical fixture transport recovery, with no production execution."""
import hashlib
import os
import unittest
from unittest.mock import patch
from scripts import community_historical_artifact_recovery as r


class HistoricalArtifactRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exact = {label: r.recover_artifact(label) for label in ('old', 'new')}

    def test_both_original_outer_inner_and_manifest_digests_are_unchanged(self):
        for label, body in self.exact.items():
            with self.subTest(label=label):
                self.assertEqual(hashlib.sha256(body).hexdigest(), r.SPECS[label][1])
                r.validate(label, body)
        self.assertEqual(len(self.exact['old']), 107650)
        self.assertEqual(len(self.exact['new']), 117926)

    def test_current_ci_sha_cannot_change_historical_builder_identity(self):
        with patch.dict(os.environ, {'GITHUB_SHA': 'f' * 40}):
            for label in ('old', 'new'):
                self.assertEqual(r.recover_artifact(label), self.exact[label])
            self.assertEqual(os.environ['GITHUB_SHA'], 'f' * 40)

    def test_original_archive_corruption_is_rejected(self):
        for label, body in self.exact.items():
            bad = body[:100] + bytes([body[100] ^ 1]) + body[101:]
            with self.assertRaisesRegex(ValueError, 'OUTER_ARTIFACT_SHA_MISMATCH'):
                r.validate(label, bad)

    def test_cross_version_substitution_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'OUTER_ARTIFACT_SHA_MISMATCH'):
            r.validate('old', self.exact['new'])

    def test_unknown_label_does_not_start_worktree_or_process(self):
        with patch.object(r.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'UNREGISTERED'):
                r.recover_artifact('../other')
            run.assert_not_called()

    def test_incomplete_or_extra_member_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'WRAPPER_MEMBER_SET'):
            r.wrapper('old', {})
        with self.assertRaisesRegex(ValueError, 'WRAPPER_MEMBER_SET'):
            r.wrapper('old', {'not-an-original-member': b'content'})

    def test_compressor_difference_cannot_silently_repin_outer(self):
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(self.exact['old'])) as z:
            files = {n: z.read(n) for n in z.namelist()}
        with patch.object(r.subprocess, 'run') as run:
            run.return_value.stdout = b'not-original-compression'
            with self.assertRaisesRegex(ValueError, 'OUTER_ARTIFACT_SHA_MISMATCH'):
                r.wrapper('old', files)

    def test_workflow_retains_all_original_checks_and_only_recovers_404(self):
        text = (r.ROOT / '.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        self.assertIn('if error.code != 404:', text)
        self.assertIn('body = recover_artifact(label)', text)
        self.assertIn("hashlib.sha256(body).hexdigest()!=outer_sha", text)
        self.assertIn("hashlib.sha256(archive).hexdigest()!=archive_sha", text)
        self.assertIn("hashlib.sha256(manifest).hexdigest()!=manifest_sha", text)
        self.assertIn('Complete Phase1 and Phase2 source regression', text)
        self.assertIn('tests/test_community_historical_fixtures.py --verify-inputs', text)


if __name__ == '__main__':
    unittest.main()
