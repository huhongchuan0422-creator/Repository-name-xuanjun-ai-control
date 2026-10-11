import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('work_collect', os.path.join(
    os.path.dirname(__file__), '..', 'scripts', 'uk-work-result-collect.py'))
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)

PATCH = b'diff --git a/stage1/owner_dashboard.py b/stage1/owner_dashboard.py\n--- a/stage1/owner_dashboard.py\n+++ b/stage1/owner_dashboard.py\n@@ -1 +1 @@\n-old\n+new\n'


class WorkCollectTest(unittest.TestCase):
    def test_real_filesystem_reads_patch_without_changing_it_or_claiming_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'candidate.patch')
            with open(path, 'wb') as stream:
                stream.write(PATCH)
            before = os.stat(path).st_mtime_ns
            result = c.collect(directory, 'B', {0, os.getuid()}, 'a' * 40)
            self.assertEqual(result['status'], 'CANDIDATE_PATCH_COLLECTED')
            self.assertEqual(result['expected_base_commit'], c.BASE_COMMIT)
            self.assertFalse(result['production_pass'])
            self.assertFalse(result['base_context_verified'])
            self.assertEqual(result['actual_model'], 'NOT_VERIFIED')
            self.assertEqual(os.stat(path).st_mtime_ns, before)
            with open(path, 'rb') as stream:
                self.assertEqual(stream.read(), PATCH)

    def test_symlink_is_not_read_and_ambiguity_never_selects_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, 'first.patch'), 'wb') as stream:
                stream.write(PATCH)
            os.symlink(os.path.join(directory, 'first.patch'), os.path.join(directory, 'alias.diff'))
            result = c.collect(directory, 'B', {0, os.getuid()}, 'a' * 40)
            self.assertEqual(result['status'], 'AMBIGUOUS_PATCH_REQUIRES_SELECTION')
            with self.assertRaises(ValueError):
                c.read_patch(os.path.join(directory, 'alias.diff'), {0, os.getuid()})

    def test_scope_traversal_header_and_symlink_modes_rejected(self):
        for raw in [PATCH.replace(b'owner_dashboard.py', b'../escape.py'),
                    PATCH.replace(b'owner_dashboard.py', b'execution_ledger.py'),
                    PATCH.replace(b'+++ b/stage1/owner_dashboard.py', b'+++ b/.env'),
                    PATCH.replace(b'--- a/', b'new file mode 120000\n--- a/')]:
            with self.assertRaises(ValueError):
                c.validate_patch(raw, 'B')

    def test_potential_secret_or_oversized_output_not_exposed(self):
        for raw in [PATCH + b'+ghp_' + b'a' * 30 + b'\n', b'x' * (c.MAX_PATCH + 1)]:
            with self.assertRaises(ValueError):
                c.validate_patch(raw, 'B')

    def test_empty_workdir_is_not_a_running_or_complete_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            result = c.collect(directory, 'A', {0, os.getuid()}, 'a' * 40)
            self.assertEqual(result['status'], 'NO_ROOT_LEVEL_PATCH')
            self.assertFalse(result['production_pass'])

    def test_host_guard_prevents_any_workdir_read(self):
        with patch.object(c.socket, 'gethostname', return_value='wrong'), patch.object(c, 'collect') as read:
            with self.assertRaises(SystemExit):
                c.main()
            read.assert_not_called()

    def test_frozen_patch_hash_mismatch_rejected_before_returning_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, 'candidate.patch'), 'wb') as stream:
                stream.write(PATCH)
            with self.assertRaises(ValueError):
                c.collect(directory, 'B', {0, os.getuid()}, 'a' * 40, '0' * 64)
