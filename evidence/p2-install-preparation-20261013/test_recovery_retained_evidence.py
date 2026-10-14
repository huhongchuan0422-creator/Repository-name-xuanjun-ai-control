"""Python 3.6 isolated regressions for exact retained evidence admission.

No host services, production SQLite, credentials or model endpoints are used.
Run in a root-mapped user namespace; this is not UK acceptance.
"""
import hashlib
import importlib.util
import io
import json
import marshal
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recover_exact_hold as recovery


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.relative = 'stage1/cache_probe.py'
        self.filename = '/opt/xuanjun-control-releases/.integration-0123456789abcdef/' + self.relative
        self.source = b'raise RuntimeError("must never execute cache")\ndef f(x):\n    return x + 1\n'
        self.path = self.root / self.relative
        self.path.parent.mkdir()
        self.path.write_bytes(self.source)
        self.info = self.path.stat()
        self.data = self.make_cache()
        self.cache_relative = 'stage1/__pycache__/cache_probe.cpython-36.pyc'
        self.cache = self.root / self.cache_relative
        self.cache.parent.mkdir()
        self.cache.write_bytes(self.data)
        self.cache.chmod(0o444)

    def tearDown(self):
        self.tmp.cleanup()

    def make_cache(self, source=None, filename=None):
        code = compile(self.source if source is None else source,
                       self.filename if filename is None else filename,
                       'exec', dont_inherit=True, optimize=0)
        return (importlib.util.MAGIC_NUMBER +
                struct.pack('<II', int(self.info.st_mtime) & 0xffffffff, len(self.source)) +
                marshal.dumps(code))

    def verify(self, data=None):
        return recovery.verify_cache_bytes(self.data if data is None else data,
                                           self.source, self.relative, self.info)

    def test_exact_cache_reproduces_without_execution(self):
        self.assertEqual(self.verify(), self.filename.rsplit('/stage1/', 1)[0])

    def test_changed_code_with_valid_header_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_CODE_MISMATCH'):
            self.verify(self.make_cache(source=b'pass\n'))

    def test_trailing_marshal_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CODE_BOUNDARY'):
            self.verify(self.data + b'append')

    def test_wrong_magic_and_source_metadata_rejected(self):
        for data in (b'BAD!' + self.data[4:], self.data[:4] + b'\0' * 8 + self.data[12:]):
            with self.assertRaises(ValueError):
                self.verify(data)

    def test_wrong_staging_or_source_name_rejected(self):
        for name in ('/tmp/rogue/' + self.relative, self.filename + '.other'):
            with self.assertRaises(ValueError):
                self.verify(self.make_cache(filename=name))

    def test_non_code_marshal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CODE_BOUNDARY'):
            self.verify(self.data[:12] + marshal.dumps({'not': 'code'}))

    def test_full_cache_set_and_hash_binding(self):
        payloads = {str(self.path): (self.source, self.source)}
        pinned = {self.cache_relative: recovery.sha(self.data)}
        with mock.patch.object(recovery, 'RETAINED_CACHE_HASHES', pinned):
            result = recovery.validate_retained_caches(str(self.root), payloads)
            self.assertEqual(set(result), set(pinned))
            self.assertEqual(result[self.cache_relative]['source_sha256'], recovery.sha(self.source))
            self.cache.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'HASH_AUTHORITY'):
                recovery.validate_retained_caches(str(self.root), payloads)

    def test_missing_or_additional_cache_rejected(self):
        payloads = {str(self.path): (self.source, self.source)}
        with mock.patch.object(recovery, 'RETAINED_CACHE_HASHES', {}):
            with self.assertRaisesRegex(ValueError, 'UNCLASSIFIED_CACHE'):
                recovery.validate_retained_caches(str(self.root), payloads)
        self.cache.unlink()
        with mock.patch.object(recovery, 'RETAINED_CACHE_HASHES', {self.cache_relative: recovery.sha(self.data)}):
            with self.assertRaisesRegex(ValueError, 'SET_MISMATCH'):
                recovery.validate_retained_caches(str(self.root), payloads)

    def test_cache_drift_or_symlink_rejected(self):
        payloads = {str(self.path): (self.source, self.source)}
        with mock.patch.object(recovery, 'RETAINED_CACHE_HASHES', {self.cache_relative: recovery.sha(self.data)}):
            self.cache.unlink(); self.cache.symlink_to(self.path)
            with self.assertRaises(ValueError):
                recovery.validate_retained_caches(str(self.root), payloads)

    def test_unknown_native_module_is_rejected(self):
        allowed = {self.relative, self.cache_relative}
        recovery.validate_file_inventory(str(self.root), allowed)
        (self.root / 'stage1/activation_control.so').write_bytes(b'not accepted')
        with self.assertRaisesRegex(ValueError, 'UNCLASSIFIED_RELEASE_FILE'):
            recovery.validate_file_inventory(str(self.root), allowed)

    def test_source_package_caches_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BYTECODE_PRESENT'):
            recovery.validate_directories(str(self.root))


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'scripts').mkdir()
        self.exe = self.root / 'scripts/xj-root-broker-client'
        self.data = self.root / 'INTEGRATION_MANIFEST.json'
        self.exe.write_bytes(b'fixture'); self.exe.chmod(0o555)
        self.data.write_bytes(b'fixture'); self.data.chmod(0o444)
        (self.root / 'scripts').chmod(0o555); self.root.chmod(0o555)

    def tearDown(self):
        self.root.chmod(0o700); (self.root / 'scripts').chmod(0o700)
        self.tmp.cleanup()

    def test_original_exact_modes_pass(self):
        recovery.validate_release_metadata(str(self.root))

    def test_non_executable_or_private_mode_rejected(self):
        for path, mode, original in ((self.exe, 0o444, 0o555), (self.data, 0o400, 0o444)):
            path.chmod(mode)
            with self.assertRaisesRegex(ValueError, 'FILE_METADATA'):
                recovery.validate_release_metadata(str(self.root))
            path.chmod(original)

    def test_directory_mode_drift_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'DIRECTORY_METADATA'):
            recovery.validate_release_metadata(str(self.root))


class PostcheckerTests(unittest.TestCase):
    def test_missing_postchecker_fails_before_any_snapshot_host_work(self):
        with mock.patch.object(recovery, 'verified_postchecker', side_effect=FileNotFoundError('fixture')), \
             mock.patch.object(recovery, 'read') as read:
            with self.assertRaises(FileNotFoundError): recovery.snapshot()
            read.assert_not_called()

    def test_drifted_postchecker_rejected(self):
        with mock.patch.object(recovery, 'read', return_value=(b'drift', types.SimpleNamespace(st_gid=0))):
            with self.assertRaisesRegex(ValueError, 'POSTCHECK_HASH'):
                recovery.verified_postchecker()


class DatabaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.main = b'exact main database fixture'
        self.shm = b'known shm fixture'
        self.path = '/not-a-production-path/state.sqlite'
        self.values = {self.path: self.main, self.path + '-wal': b'', self.path + '-shm': self.shm}
        self.calls = []
        self.meta = types.SimpleNamespace(st_gid=1002, st_mode=0o100644)
        self.patches = [
            mock.patch.object(recovery, 'DB_SHA', recovery.sha(self.main)),
            mock.patch.object(recovery, 'RETAINED_SIDECARS', {
                '-wal': (0, recovery.sha(b'')), '-shm': (len(self.shm), recovery.sha(self.shm))}),
            mock.patch.object(recovery.os.path, 'lexists', side_effect=lambda p: p in self.values),
            mock.patch.object(recovery, 'read', side_effect=self.fake_read)]
        for patch in self.patches: patch.start()

    def tearDown(self):
        for patch in reversed(self.patches): patch.stop()

    def fake_read(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return self.values[path], self.meta

    def observe(self):
        return recovery.database_file_set(self.path, 1002, retained_source=True)

    def test_exact_empty_wal_and_pinned_shm_are_observations_only(self):
        evidence, data = self.observe()
        self.assertEqual(data, self.main)
        self.assertEqual(evidence['sidecars']['-wal']['size'], 0)
        self.assertEqual(len(self.calls), 3)

    def test_nonempty_wal_rejected_even_when_main_unchanged(self):
        self.values[self.path + '-wal'] = b'committed or unknown data'
        with self.assertRaisesRegex(ValueError, 'SIDECAR_DRIFT'): self.observe()

    def test_changed_shm_or_main_rejected(self):
        for path in (self.path, self.path + '-shm'):
            original = self.values[path]; self.values[path] = original + b'!'
            with self.assertRaises(ValueError): self.observe()
            self.values[path] = original

    def test_journal_and_missing_retained_sidecar_rejected(self):
        self.values[self.path + '-journal'] = b''
        with self.assertRaisesRegex(ValueError, 'DATABASE_SIDECAR'): self.observe()
        del self.values[self.path + '-journal']
        del self.values[self.path + '-wal']
        with self.assertRaisesRegex(ValueError, 'RETAINED_DATABASE_SET'): self.observe()

    def test_backup_generation_do_not_inherit_source_exception(self):
        with self.assertRaisesRegex(ValueError, 'DATABASE_SIDECAR'):
            recovery.database_file_set(self.path, 0)

    def test_sidecar_permissions_remain_bounded(self):
        self.meta.st_mode = 0o100666
        with self.assertRaisesRegex(ValueError, 'SIDECAR_DRIFT'): self.observe()


class CopyInspectionTests(unittest.TestCase):
    def test_manifest_only_opens_temporary_copy_and_cleans_it(self):
        data = b'fixture'; paths = []
        def inspector(path):
            paths.append(path)
            self.assertEqual(Path(path).read_bytes(), data)
            return {'sha256': recovery.sha(data), 'size': len(data)}
        recovery.manifest_from_copy(data, inspector)
        self.assertFalse(os.path.exists(paths[0]))

    def test_inspection_cannot_silently_change_copy(self):
        def inspector(path):
            return {'sha256': recovery.sha(b'different'), 'size': 9}
        with self.assertRaisesRegex(ValueError, 'CHANGED_COPY'):
            recovery.manifest_from_copy(b'fixture', inspector)


class ApprovalBoundaryTests(unittest.TestCase):
    def test_state_change_during_github_read_blocks_all_resume_effects(self):
        self.run_main(changed=True)

    def test_stable_state_rechecked_before_resume(self):
        self.run_main(changed=False)

    def test_verify_only_does_not_fetch_approval_or_resume(self):
        self.run_main(verify=True)

    def run_main(self, changed=False, verify=False):
        first = {'fixture': 'before'}
        second = {'fixture': 'after'} if changed else dict(first)
        digest = recovery.sha(recovery.canonical(first))
        with tempfile.TemporaryDirectory() as directory:
            lock = directory + '/lock'
            with open(lock, 'wb'): pass
            os.chmod(lock, 0o600)
            original_open = os.open
            def open_lock(path, *args, **kwargs):
                if path == '/run/xuanjun-p2-install.lock': path = lock
                return original_open(path, *args, **kwargs)
            argv = ['recover_exact_hold.py', '--operation', 'verify-only' if verify else 'resume']
            if not verify: argv += ['--review-id', '999', '--snapshot-sha256', digest]
            with mock.patch.object(sys, 'argv', argv), \
                 mock.patch.object(recovery.socket, 'gethostname', return_value='iZd7oeikknn1z21sq6ji6zZ'), \
                 mock.patch.object(recovery.os, 'open', side_effect=open_lock), \
                 mock.patch.object(recovery, 'snapshot', side_effect=[(first, ('first',)), (second, ('fresh',))]) as snapshots, \
                 mock.patch.object(recovery, 'approval', return_value={'review_id': 999}) as approve, \
                 mock.patch.object(recovery, 'resume', return_value={'stage': 'fixture'}) as resume, \
                 mock.patch('sys.stdout', new_callable=io.StringIO):
                if changed:
                    with self.assertRaisesRegex(ValueError, 'STATE_CHANGED_DURING_APPROVAL'):
                        recovery.main()
                    resume.assert_not_called()
                else:
                    recovery.main()
                    if verify:
                        approve.assert_not_called(); resume.assert_not_called()
                    else:
                        resume.assert_called_once_with(second, ('fresh',), {'review_id': 999})
                self.assertEqual(snapshots.call_count, 1 if verify else 2)

    def test_exact_recovery_approval_must_be_on_pr58(self):
        body = recovery.MARKER + '{}'
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = recovery.canonical({
            'id': 999, 'user': {'id': 332398908, 'login': 'huhongchuan0422-creator'},
            'issue_url': 'https://api.github.com/repos/' + recovery.REPO + '/issues/17',
            'body': body})
        opener = mock.Mock(); opener.open.return_value = response
        with mock.patch.object(recovery.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'REVIEW_DESTINATION'):
                recovery.approval(999, '0' * 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
