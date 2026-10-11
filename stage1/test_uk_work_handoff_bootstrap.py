import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('handoff_bootstrap', os.path.join(
    os.path.dirname(__file__), '..', 'scripts', 'uk-work-handoff-bootstrap.py'))
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)
SPEC_C = importlib.util.spec_from_file_location('handoff_collector', os.path.join(
    os.path.dirname(__file__), '..', 'scripts', 'uk-work-result-collect.py'))
c = importlib.util.module_from_spec(SPEC_C)
SPEC_C.loader.exec_module(c)


class HandoffBootstrapTest(unittest.TestCase):
    def test_collector_and_copy_bind_same_second_candidate(self):
        self.assertEqual(b.FROZEN_COMMIT, c.INTEGRATED_FROZEN_COMMIT)
        self.assertEqual(b.PATCH_HASH, c.INTEGRATED_PATCH_HASH)
        self.assertEqual(b.OWNER_REPORTED_MANIFEST_HASH, c.OWNER_REPORTED_MANIFEST_HASH)

    def test_atomic_write_is_idempotent_and_never_overwrites_changed_result(self):
        with tempfile.TemporaryDirectory() as directory:
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                b.write_once(fd, b'checked-patch', os.getuid(), os.getgid())
                path = os.path.join(directory, 'candidate.patch')
                before = os.stat(path).st_mtime_ns
                b.write_once(fd, b'checked-patch', os.getuid(), os.getgid())
                self.assertEqual(os.stat(path).st_mtime_ns, before)
                with self.assertRaises(ValueError):
                    b.write_once(fd, b'different-patch', os.getuid(), os.getgid())
                with open(path, 'rb') as stream:
                    self.assertEqual(stream.read(), b'checked-patch')
                self.assertEqual(os.listdir(directory), ['candidate.patch'])
            finally:
                os.close(fd)

    def test_existing_symlink_cannot_redirect_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, 'target')
            with open(target, 'wb') as stream:
                stream.write(b'preserve')
            os.symlink(target, os.path.join(directory, 'candidate.patch'))
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(OSError):
                    b.write_once(fd, b'new', os.getuid(), os.getgid())
            finally:
                os.close(fd)
            with open(target, 'rb') as stream:
                self.assertEqual(stream.read(), b'preserve')

    def test_source_hash_and_symlink_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'patch')
            with open(path, 'wb') as stream:
                stream.write(b'fixed')
            digest = hashlib.sha256(b'fixed').hexdigest()
            self.assertEqual(b.read_frozen_source(path, {0, os.getuid()}, digest), b'fixed')
            with self.assertRaises(ValueError):
                b.read_frozen_source(path, {0, os.getuid()}, '0' * 64)
            os.symlink(path, os.path.join(directory, 'link'))
            with self.assertRaises(OSError):
                b.read_frozen_source(os.path.join(directory, 'link'), {0, os.getuid()}, digest)

    def test_world_writable_root_parent_is_refused(self):
        with self.assertRaises(ValueError):
            b.open_root_directory('/tmp/must-not-create-work-handoff', os.getgid())

    def test_wrong_host_guard_runs_before_any_read_or_privileged_action(self):
        with patch.object(b.socket, 'gethostname', return_value='wrong'), patch.object(b.os, 'geteuid', return_value=0), patch.object(b, 'read_frozen_source') as read:
            with self.assertRaises(SystemExit):
                b.main()
            read.assert_not_called()

    def test_bad_candidate_cannot_initialize_any_bridge(self):
        with patch.object(b.socket, 'gethostname', return_value=b.HOST), patch.object(b.os, 'geteuid', return_value=0), patch.object(b.sys, 'argv', ['script']), patch.object(b.pwd, 'getpwnam') as user, patch.object(b, 'read_frozen_source', side_effect=ValueError('FROZEN_PATCH_HASH_MISMATCH')), patch.object(b, 'open_root_directory') as directory:
            user.return_value.pw_uid = os.getuid()
            user.return_value.pw_gid = os.getgid()
            with self.assertRaises(ValueError):
                b.main()
            directory.assert_not_called()
