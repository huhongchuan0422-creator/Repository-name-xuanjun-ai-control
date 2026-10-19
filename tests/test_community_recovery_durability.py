"""Offline recovery durability barriers; no HTTP listener or external transport."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts import community_stage_recovery as recovery
from scripts import community_release_candidate as release


class RestoredStoreDurability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir(mode=0o700)
        files = {}
        for name in recovery.NAMES:
            path = self.source / (name + '.sqlite')
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE original(value TEXT)')
            db.execute('INSERT INTO original VALUES(?)', (name,))
            db.commit()
            db.close()
            path.chmod(0o600)
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        raw = json.dumps(dict(format=1, purpose='OFFLINE_RESTORE_CANDIDATE',
            cross_database_atomic=False, center_backup='EXISTING_CENTER_OWNER_REQUIRED',
            payment_enabled=False, files=files), sort_keys=True, separators=(',', ':')).encode()
        (self.source / 'snapshot.json').write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.before = {p.name: p.read_bytes() for p in self.source.iterdir()}

    def assert_source_unchanged(self):
        self.assertEqual(self.before, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_restore_cannot_succeed_when_every_data_sync_fails(self):
        target = self.root / 'restored'
        with patch.object(recovery.os, 'fsync', side_effect=OSError('synthetic persistence failure')):
            with self.assertRaises(OSError):
                recovery.restore(self.source, self.digest, target)
        self.assertFalse(target.exists())
        self.assert_source_unchanged()

    def test_restore_syncs_all_six_files_before_target_and_parent_directories(self):
        target = self.root / 'restored'
        calls = []
        original = os.fsync
        def track(fd):
            calls.append(Path(os.readlink('/proc/self/fd/' + str(fd))))
            original(fd)
        with patch.object(recovery.os, 'fsync', side_effect=track):
            self.assertTrue(recovery.restore(self.source, self.digest, target)['restored'])
        self.assertEqual(calls, [target / name for name in sorted(self.before) if name.endswith('.sqlite')]
            + [target, self.root])
        self.assert_source_unchanged()

    def test_each_file_or_directory_sync_failure_removes_only_new_target(self):
        original = os.fsync
        for failed_index in range(8):
            with self.subTest(failed_index=failed_index):
                target = self.root / ('failed-' + str(failed_index))
                index = 0
                def fail(fd):
                    nonlocal index
                    current = index
                    index += 1
                    if current == failed_index:
                        raise OSError('synthetic persistence failure')
                    original(fd)
                with patch.object(recovery.os, 'fsync', side_effect=fail):
                    with self.assertRaises(OSError):
                        recovery.restore(self.source, self.digest, target)
                self.assertFalse(target.exists())
                self.assert_source_unchanged()
        self.assertTrue(recovery.restore(self.source, self.digest, self.root / 'fresh')['restored'])


class GenerationDurability(unittest.TestCase):
    def setUp(self):
        # Existing real Center/MiniApplication fixture, but stop before any HTTP.
        from test_community_release_candidate import ReleasePairing
        self.fx = ReleasePairing()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def test_snapshot_syncs_databases_manifest_and_both_directories(self):
        target = self.fx.root / 'durable-snapshot'
        calls = []
        original = os.fsync
        def track(fd):
            calls.append(Path(os.readlink('/proc/self/fd/' + str(fd))))
            original(fd)
        with patch.object(recovery.os, 'fsync', side_effect=track):
            recovery.snapshot(self.fx.app, target)
        self.assertEqual(calls, [target / (name + '.sqlite') for name in recovery.NAMES]
            + [target / 'snapshot.json', target, self.fx.root])
        self.assertIsNone(self.fx.app.server)

    def test_snapshot_each_persistence_failure_removes_unfinished_candidate(self):
        original = os.fsync
        for failed_index in range(9):
            with self.subTest(failed_index=failed_index):
                target = self.fx.root / ('snapshot-failed-' + str(failed_index))
                index = 0
                def fail(fd):
                    nonlocal index
                    current = index
                    index += 1
                    if current == failed_index:
                        raise OSError('synthetic persistence failure')
                    original(fd)
                with patch.object(recovery.os, 'fsync', side_effect=fail):
                    with self.assertRaises(OSError):
                        recovery.snapshot(self.fx.app, target)
                self.assertFalse(target.exists())
                self.assertEqual(self.fx.app.stage.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0], 1)

    def test_release_stops_before_health_or_ready_when_restored_database_sync_fails(self):
        original = os.fsync
        def fail(fd):
            path = Path(os.readlink('/proc/self/fd/' + str(fd)))
            if path.name == 'orders.sqlite' and path.parent.name == 'state':
                raise OSError('synthetic restored database sync failure')
            original(fd)
        with patch.object(recovery.os, 'fsync', side_effect=fail), \
                patch.object(release, 'probe_original_health', side_effect=AssertionError('MUST_NOT_START_HTTP')) as health:
            with self.assertRaises(OSError):
                self.fx.install('failed-restore-sync')
        root = self.fx.workspace / 'generations' / 'failed-restore-sync'
        self.assertTrue((root / 'HOLD').is_file())
        self.assertFalse((root / 'READY').exists())
        self.assertFalse((root / 'state').exists())
        self.assertIsNone(self.fx.releases.current())
        health.assert_not_called()

    def test_post_composition_files_must_sync_before_ready(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        original = os.fsync
        def fail(fd):
            path = Path(os.readlink('/proc/self/fd/' + str(fd)))
            if path.name == 'runtime.lock' and path.parent.name == 'state':
                raise OSError('synthetic post-composition persistence failure')
            original(fd)
        # Only this failure-path test supplies health; it never claims real HTTP PASS.
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release.os, 'fsync', side_effect=fail):
            with self.assertRaises(OSError):
                self.fx.install('failed-final-sync')
        root = self.fx.workspace / 'generations' / 'failed-final-sync'
        self.assertTrue((root / 'HOLD').is_file())
        self.assertFalse((root / 'READY').exists())
        self.assertIsNone(self.fx.releases.current())

    def test_final_file_and_directory_syncs_precede_ready_marker(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        root = self.fx.workspace / 'generations' / 'sync-order'
        events = []
        sync_file, sync_directory, write = release._sync_file, release._sync, release._write
        def track_file(path, raw):
            sync_file(path, raw)
            events.append(('file', Path(path)))
        def track_directory(path):
            sync_directory(path)
            events.append(('directory', Path(path)))
        def track_write(path, raw):
            events.append(('write', Path(path)))
            write(path, raw)
        # The synthetic health result permits only a deterministic ordering test.
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release, '_sync_file', side_effect=track_file), \
                patch.object(release, '_sync', side_effect=track_directory), \
                patch.object(release, '_write', side_effect=track_write):
            target = self.fx.install('sync-order')
        record, _ = release.inspect_generation(root, target['ready_sha256'])
        ready_at = events.index(('write', root / 'READY'))
        before = events[:ready_at]
        self.assertEqual({path.relative_to(root).as_posix() for kind, path in before if kind == 'file'},
            set(record['files']))
        self.assertTrue({path for path in root.rglob('*') if path.is_dir()}.issubset(
            {path for kind, path in before if kind == 'directory'}))
        self.assertIn(('write', root / 'generation.json'), before)
        self.assertEqual(events[ready_at + 1:], [('directory', root), ('directory', root.parent),
            ('directory', root)])
        self.assertFalse((root / 'INSTALLING').exists())
        self.assertIsNone(self.fx.app.server)
        self.assertIsNone(self.fx.releases.current())

    def test_ready_sync_failure_with_unwritable_hold_removes_ready_and_preserves_error(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        root = self.fx.workspace / 'generations' / 'ready-hold-failure'
        original_sync, original_write = os.fsync, release._write
        failure = OSError('original READY persistence failure')
        def fail_sync(fd):
            if Path(os.readlink('/proc/self/fd/' + str(fd))) == root / 'READY':
                raise failure
            original_sync(fd)
        def fail_hold(path, raw):
            if path == root / 'HOLD':
                raise PermissionError('HOLD cannot be written')
            original_write(path, raw)
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release.os, 'fsync', side_effect=fail_sync), \
                patch.object(release, '_write', side_effect=fail_hold):
            with self.assertRaises(OSError) as caught:
                self.fx.install('ready-hold-failure')
        self.assertIs(caught.exception, failure)
        self.assertFalse((root / 'READY').exists())
        self.assertFalse((root / 'HOLD').exists())
        self.assertTrue((root / 'INSTALLING').is_file())
        with self.assertRaises((OSError, ValueError)):
            release.inspect_generation(root)
        self.assertIsNone(self.fx.releases.current())

    def test_unlink_failure_still_records_hold_without_masking_original_error(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        root = self.fx.workspace / 'generations' / 'ready-unlink-failure'
        original_sync, original_unlink = os.fsync, Path.unlink
        failure = OSError('original READY persistence failure')
        def fail_sync(fd):
            if Path(os.readlink('/proc/self/fd/' + str(fd))) == root / 'READY':
                raise failure
            original_sync(fd)
        def fail_unlink(path, *args, **kwargs):
            if path == root / 'READY':
                raise PermissionError('READY cannot be removed')
            return original_unlink(path, *args, **kwargs)
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release.os, 'fsync', side_effect=fail_sync), \
                patch.object(Path, 'unlink', fail_unlink):
            with self.assertRaises(OSError) as caught:
                self.fx.install('ready-unlink-failure')
        self.assertIs(caught.exception, failure)
        self.assertTrue((root / 'HOLD').is_file())
        with self.assertRaises(ValueError):
            release.inspect_generation(root)
        self.assertIsNone(self.fx.releases.current())

    def test_cleanup_sync_and_hold_failure_do_not_mask_original_failure(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        root = self.fx.workspace / 'generations' / 'cleanup-sync-failure'
        original_sync, original_write = os.fsync, release._write
        failure = OSError('original READY persistence failure')
        def fail_sync(fd):
            path = Path(os.readlink('/proc/self/fd/' + str(fd)))
            if path == root / 'READY':
                raise failure
            if path == root and (root / 'generation.json').exists():
                raise OSError('cleanup directory sync unavailable')
            original_sync(fd)
        def fail_hold(path, raw):
            if path == root / 'HOLD':
                raise PermissionError('HOLD cannot be written')
            original_write(path, raw)
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release.os, 'fsync', side_effect=fail_sync), \
                patch.object(release, '_write', side_effect=fail_hold):
            with self.assertRaises(OSError) as caught:
                self.fx.install('cleanup-sync-failure')
        self.assertIs(caught.exception, failure)
        self.assertFalse((root / 'READY').exists())
        with self.assertRaises((OSError, ValueError)):
            release.inspect_generation(root)

    def test_persisted_installing_marker_blocks_ready_when_cleanup_and_hold_both_fail(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        root = self.fx.workspace / 'generations' / 'triple-failure'
        original_sync, original_write, original_unlink = os.fsync, release._write, Path.unlink
        failure = OSError('original READY persistence failure')
        def fail_sync(fd):
            if Path(os.readlink('/proc/self/fd/' + str(fd))) == root / 'READY':
                raise failure
            original_sync(fd)
        def fail_hold(path, raw):
            if path == root / 'HOLD':
                raise PermissionError('HOLD cannot be written')
            original_write(path, raw)
        def fail_unlink(path, *args, **kwargs):
            if path == root / 'READY':
                raise PermissionError('READY cannot be removed')
            return original_unlink(path, *args, **kwargs)
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release.os, 'fsync', side_effect=fail_sync), \
                patch.object(release, '_write', side_effect=fail_hold), \
                patch.object(Path, 'unlink', fail_unlink):
            with self.assertRaises(OSError) as caught:
                self.fx.install('triple-failure')
        self.assertIs(caught.exception, failure)
        self.assertTrue((root / 'READY').exists())
        self.assertTrue((root / 'INSTALLING').is_file())
        self.assertFalse((root / 'HOLD').exists())
        with self.assertRaisesRegex(ValueError, 'GENERATION_INSTALLATION_INCOMPLETE'):
            release.inspect_generation(root)
        self.assertIsNone(self.fx.releases.current())

    def test_installing_marker_persistence_failure_prevents_source_and_ready(self):
        root = self.fx.workspace / 'generations' / 'installing-sync-failure'
        original_sync = os.fsync
        failure = OSError('INSTALLING persistence failure')
        def fail_sync(fd):
            if Path(os.readlink('/proc/self/fd/' + str(fd))) == root / 'INSTALLING':
                raise failure
            original_sync(fd)
        with patch.object(release.os, 'fsync', side_effect=fail_sync), \
                patch.object(release, 'probe_original_health', side_effect=AssertionError('MUST_NOT_START_HTTP')) as health:
            with self.assertRaises(OSError) as caught:
                self.fx.install('installing-sync-failure')
        self.assertIs(caught.exception, failure)
        self.assertFalse((root / 'source').exists())
        self.assertFalse((root / 'READY').exists())
        health.assert_not_called()

    def test_last_marker_removal_sync_failure_revokes_ready_without_success_receipt(self):
        health = {'http_status': 503, 'health': {'status': 'MAINTENANCE',
            'scope': 'PROCESS_AND_DATABASE_CONNECTIVITY', 'production_acceptance': False}}
        root = self.fx.workspace / 'generations' / 'last-sync-failure'
        original_sync = os.fsync
        failure = OSError('last marker removal persistence failure')
        fired = False
        def fail_sync(fd):
            nonlocal fired
            path = Path(os.readlink('/proc/self/fd/' + str(fd)))
            if path == root and (root / 'READY').exists() and not (root / 'INSTALLING').exists():
                fired = True
                raise failure
            original_sync(fd)
        with patch.object(release, 'probe_original_health', return_value=health), \
                patch.object(release.os, 'fsync', side_effect=fail_sync):
            with self.assertRaises(OSError) as caught:
                self.fx.install('last-sync-failure')
        self.assertTrue(fired)
        self.assertIs(caught.exception, failure)
        self.assertFalse((root / 'READY').exists())
        self.assertTrue((root / 'HOLD').exists())
        with self.assertRaises((ValueError, OSError)):
            release.inspect_generation(root)
        self.assertIsNone(self.fx.releases.current())


if __name__ == '__main__':
    unittest.main()
