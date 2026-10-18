"""Real private release/data generations and loopback health; no live deployment."""
import copy
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import test_community_mini_center_identity as fixture
import scripts.community_release_candidate as release_module
from scripts.community_mini_application import MiniApplication
from scripts.community_order_store import create_order
from scripts.community_release_candidate import (OfflineReleases, container_candidate,
    inspect_generation, inspect_package, verify_center_backup, probe_original_health)
from scripts.community_stage_package import build

ROOT = Path(__file__).resolve().parents[1]


def contract():
    return dict(service='uk-community-payment', image='python@sha256:' + 'a' * 64,
        python_version='3.12.14', uid=1000, gid=1000, nginx_uid=101, nginx_gid=101,
        cpu_millis=500, memory_bytes=256 * 1024**2, pids=64, disk_bytes=1024**3,
        log_bytes=1024**2, network='uk-community-payment-isolated',
        volumes={k: 'uk-community-payment-' + k for k in ('release', 'business', 'objects', 'socket')},
        secret_ref='uk-community-payment-existing-runtime', https_origin='https://community.example.org',
        socket_path='/run/community/mini.sock', privileged=False, host_network=False,
        docker_socket=False, center_mode='EXISTING_CENTER_IN_PROCESS')


class ContainerAndSourceContract(unittest.TestCase):
    def test_isolated_stopped_container_has_no_host_mount_ports_or_secrets(self):
        result = container_candidate(contract())
        service = result['compose']['services']['uk-community-payment']
        self.assertEqual(service['network_mode'], 'none')
        self.assertEqual(service['restart'], 'no')
        self.assertTrue(service['read_only'])
        self.assertNotIn('ports', service)
        self.assertNotIn('secrets', service)
        self.assertNotIn('environment', service)
        self.assertFalse(result['production_enabled'])
        self.assertFalse(result['image_contents_and_target_runtime_verified'])

    def test_unsafe_or_unspecified_container_fields_fail_closed(self):
        bad = [('privileged', True), ('host_network', True), ('docker_socket', True),
               ('uid', 0), ('cpu_millis', 0), ('pids', True), ('image', 'python:latest'),
               ('network', 'existing-control-network'), ('secret_ref', 'plaintext-secret-value'),
               ('center_mode', 'COPY_CENTER_DATABASE'), ('python_version', '3.6.8')]
        for key, value in bad:
            with self.subTest(key=key):
                candidate = contract(); candidate[key] = value
                with self.assertRaises(ValueError): container_candidate(candidate)
        candidate = contract(); candidate['volumes']['business'] = '/var/lib/control'
        with self.assertRaises(ValueError): container_candidate(candidate)
        candidate = contract(); candidate.pop('disk_bytes')
        with self.assertRaises(ValueError): container_candidate(candidate)
        candidate = contract(); candidate['app_secret'] = 'not-allowed'
        with self.assertRaises(ValueError): container_candidate(candidate)

    def test_actual_source_package_has_all_six_pins_and_existing_wheel_sbom(self):
        raw, digest = build(ROOT)
        blobs, sbom = inspect_package(raw, digest)
        self.assertIn('scripts/community_mini_application.py', blobs)
        self.assertEqual(len(sbom['original_center_dependencies']), 6)
        self.assertEqual(len(sbom['existing_cp311_wheel_pins']), 3)
        self.assertEqual(sbom['wheel_target_compatibility'], 'NOT_INFERRED_FOR_UK_CONTAINER')
        with self.assertRaises(ValueError): inspect_package(raw, '0' * 64)

    def test_duplicate_and_traversal_archive_members_rejected(self):
        for names in (['../escape'], ['same', 'same']):
            with self.subTest(names=names):
                out = io.BytesIO()
                with zipfile.ZipFile(out, 'w') as archive:
                    for name in names:
                        entry = zipfile.ZipInfo(name); entry.external_attr = 0o100600 << 16
                        archive.writestr(entry, b'x')
                raw = out.getvalue()
                with self.assertRaises(ValueError): inspect_package(raw, hashlib.sha256(raw).hexdigest())


class ReleasePairing(unittest.TestCase):
    def setUp(self):
        self.fx = fixture.ExistingCenterComposition(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.compose(self.fx.center, self.root / 'original')
        self.addCleanup(self.app.close)
        self.scope = self.fx.stage.api.bindings[self.fx.stage.customer]
        create_order(self.app.stage.demo.db, self.scope, 'order1', 101)
        self.fx.center.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
        self.backup = self.root / 'center-backup'; self.backup.mkdir(mode=0o700)
        saved = sqlite3.connect(self.backup / 'center.sqlite')
        self.fx.center.db.backup(saved); saved.close()
        (self.backup / 'center.sqlite').chmod(0o600)
        shutil.copytree(self.fx.center.objects, self.backup / 'objects')
        self.evidence = {'database': self.backup / 'center.sqlite', 'objects': self.backup / 'objects',
            'database_sha256': hashlib.sha256((self.backup / 'center.sqlite').read_bytes()).hexdigest()}
        self.workspace = self.root / 'rehearsal'
        self.releases = OfflineReleases(self.workspace, create=True)
        self.raw, self.digest = build(ROOT)
        # Any actual network provider call would fail this test, including a
        # hypothetical accidental call from a newly configured application.
        for target in ('scripts.community_mini_login.WechatCodeClient.exchange',
                       'scripts.community_wechat_sp_readonly.PartnerOrderReader._fetch',
                       'http.client.HTTPSConnection.connect'):
            guard = patch(target, side_effect=AssertionError('NO_EXTERNAL_NETWORK'))
            guard.start(); self.addCleanup(guard.stop)

    def compose(self, center, path):
        return MiniApplication(center, path, self.fx.stage.api.bindings, self.scope if hasattr(self, 'scope')
            else self.fx.stage.api.bindings[self.fx.stage.customer], self.fx.scenes, self.fx.identity.appid, 'a' * 32)

    def install(self, name='first', compose=None, evidence=None):
        return self.releases.install(name, self.raw, self.digest, 'a' * 40, self.app,
            compose or self.compose, evidence or self.evidence, contract())

    def select(self, target, expected=None, transaction='select-first', rollback=None):
        return self.releases.select(target, expected, transaction, self.fx.center, self.evidence, rollback_of=rollback)

    def test_real_install_restores_six_stores_and_http_health_without_changing_original(self):
        before = verify_center_backup(self.fx.center, self.evidence)
        target = self.install()
        root = self.workspace / 'generations' / 'first'
        record, digest = inspect_generation(root, target['ready_sha256'])
        self.assertEqual(record['health']['health']['status'], 'MAINTENANCE')
        self.assertEqual(record['center_backup'], before)
        self.assertEqual(verify_center_backup(self.fx.center, self.evidence), before)
        self.assertEqual(set(p.stem for p in (root / 'state').glob('*.sqlite')), set(('orders', 'merchants', 'ads', 'refunds', 'modules', 'saas-orders')))
        saved = sqlite3.connect(root / 'state/orders.sqlite')
        self.assertEqual(saved.execute('SELECT amount_minor FROM orders').fetchone()[0], 101); saved.close()
        self.assertIsNone(self.releases.current())
        self.assertTrue((root / 'source/scripts/community_mini_application.py').is_file())
        self.assertEqual(len(json.loads((root / 'sbom.json').read_bytes())['original_center_dependencies']), 6)
        self.assertFalse(record['production_installed'])
        self.assertEqual(self.fx.center.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0], '1')

    def test_two_generations_select_and_rollback_always_pair_source_and_data(self):
        first = self.install('first'); self.select(first)
        create_order(self.app.stage.demo.db, self.scope, 'order2', 202)
        second = self.install('second')
        self.select(second, first, 'upgrade')
        result = self.select(first, second, 'rollback', 'upgrade')
        self.assertEqual(result['state'], 'COMMITTED')
        self.assertEqual(self.releases.current(), first)
        reopened = OfflineReleases(self.workspace)
        self.assertEqual(reopened.current(), first)
        for name, count in (('first', 1), ('second', 2)):
            db = sqlite3.connect(self.workspace / 'generations' / name / 'state/orders.sqlite')
            self.assertEqual(db.execute('SELECT count(*) FROM orders').fetchone()[0], count); db.close()
        # Neither pointer change touched the original running data directory.
        self.assertEqual(self.app.stage.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0], 2)

    def test_wrong_generation_digest_and_stale_cas_cannot_select(self):
        first = self.install('first'); second = self.install('second')
        mixed = {'generation': first['generation'], 'ready_sha256': second['ready_sha256']}
        with self.assertRaises(ValueError): self.select(mixed)
        self.select(first)
        with self.assertRaisesRegex(ValueError, 'CAS_MISMATCH'): self.select(second)
        self.assertEqual(self.releases.current(), first)

    def test_wrong_rollback_history_is_rejected(self):
        first = self.install('first'); second = self.install('second')
        self.select(first); self.select(second, first, 'upgrade')
        with self.assertRaisesRegex(ValueError, 'PREVIOUS_PAIR'):
            self.select(first, second, 'bad-rollback', 'select-first')

    def test_arbitrary_backup_id_is_not_evidence(self):
        with self.assertRaises(ValueError): self.install(evidence={'id': 'whatever'})
        self.assertEqual(list((self.workspace / 'generations').iterdir()), [])

    def test_center_backup_must_match_actual_database_bytes_and_live_generation(self):
        evidence = dict(self.evidence); evidence['database_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'DIGEST'): self.install(evidence=evidence)
        self.fx.center.db.execute("UPDATE settings SET v='99' WHERE k='authority_revision'")
        with self.assertRaisesRegex(ValueError, 'SAME_GENERATION'): self.install()

    def test_current_center_change_blocks_rollback_even_with_old_good_backup(self):
        first = self.install('first'); self.select(first)
        second = self.install('second'); self.select(second, first, 'upgrade')
        self.fx.center.db.execute("UPDATE settings SET v='99' WHERE k='authority_revision'")
        with self.assertRaisesRegex(ValueError, 'SAME_GENERATION'):
            self.select(first, second, 'rollback', 'upgrade')
        self.assertEqual(self.releases.current(), second)

    def test_missing_or_changed_encrypted_object_backup_is_rejected(self):
        path = self.fx.center.objects / 'synthetic-opaque-object'
        path.write_bytes(b'fixture-ciphertext'); path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'OBJECT_BACKUP'): self.install()

    def test_existing_target_and_symlink_workspace_are_not_reused(self):
        self.install()
        with self.assertRaises(FileExistsError): self.install()
        alias = self.root / 'alias'; alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(ValueError): OfflineReleases(alias)

    def test_corrupt_staged_source_or_data_invalidates_selection(self):
        target = self.install()
        path = self.workspace / 'generations/first/state/orders.sqlite'
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'FILE_CHANGED'): self.select(target)
        self.assertIsNone(self.releases.current())

    def test_failed_health_leaves_unready_generation_and_keeps_original_data(self):
        def broken_probe(app):
            app.stage.demo.ad_db.close()
            return probe_original_health(app)
        with patch('scripts.community_release_candidate.probe_original_health', side_effect=broken_probe):
            with self.assertRaisesRegex(ValueError, 'HEALTH'): self.install()
        root = self.workspace / 'generations/first'
        self.assertTrue((root / 'HOLD').exists()); self.assertFalse((root / 'READY').exists())
        self.assertIsNone(self.releases.current())
        self.assertEqual(self.app.stage.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0], 1)

    def test_wrong_restored_directory_cannot_be_attested(self):
        def wrong(center, path): return self.compose(center, self.root / 'different')
        with self.assertRaisesRegex(ValueError, 'RESTORED_SIX'): self.install(compose=wrong)
        self.assertFalse((self.workspace / 'generations/first/READY').exists())

    def test_original_center_must_remain_in_maintenance(self):
        self.fx.center.db.execute("UPDATE settings SET v='0' WHERE k='maintenance'")
        with self.assertRaises(PermissionError): self.install()

    def test_live_listener_rejects_install_before_creating_generation(self):
        self.app.listen()
        with self.assertRaises(PermissionError): self.install()
        self.assertEqual(list((self.workspace / 'generations').iterdir()), [])

    def test_exclusive_release_lock_blocks_competing_selection(self):
        target = self.install(); other = OfflineReleases(self.workspace)
        with self.releases._lock():
            with self.assertRaises(BlockingIOError):
                other.select(target, None, 'competing', self.fx.center, self.evidence)
        self.assertIsNone(self.releases.current())

    def test_before_pointer_crash_is_explicitly_aborted_without_replaying_selection(self):
        target = self.install()
        with patch.object(self.releases, '_before_select', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.select(target)
        reopened = OfflineReleases(self.workspace)
        self.assertEqual(reopened.transaction('select-first')['state'], 'NOT_SELECTED_HOLD')
        with self.assertRaisesRegex(ValueError, 'UNRESOLVED'):
            reopened.select(target, None, 'new-attempt', self.fx.center, self.evidence)
        self.assertEqual(reopened.resolve_transaction('select-first', self.fx.center, self.evidence)['state'], 'RECOVERED_ABORTED')
        self.assertIsNone(reopened.current())
        reopened.select(target, None, 'explicit-new-selection', self.fx.center, self.evidence)

    def test_hard_process_exit_after_atomic_selection_is_reconciled_without_replay(self):
        target = self.install()
        def child():
            from scripts.pr122_customer_core import Center
            center = Center(self.fx.tmp.name, {'testkey': b'k' * 32}, 'testkey', clock=lambda: self.fx.stage.now, mail_ready=True)
            releases = OfflineReleases(self.workspace)
            releases._after_select = lambda: os._exit(71)
            releases.select(target, None, 'hard-exit', center, self.evidence)
        process = multiprocessing.get_context('fork').Process(target=child)
        process.start(); process.join(10)
        if process.is_alive(): process.kill(); process.join(); self.fail('bounded child did not exit')
        self.assertEqual(process.exitcode, 71)
        reopened = OfflineReleases(self.workspace)
        self.assertEqual(reopened.current(), target)
        self.assertEqual(reopened.transaction('hard-exit')['state'], 'SELECTED_RECEIPT_PENDING_HOLD')
        result = reopened.resolve_transaction('hard-exit', self.fx.center, self.evidence)
        self.assertEqual(result['state'], 'RECOVERED_COMMITTED')
        self.assertFalse(result['original_call_success_proven'])
        self.assertEqual(reopened.current(), target)
        with self.assertRaises(ValueError): reopened.resolve_transaction('hard-exit', self.fx.center, self.evidence)

    def test_completion_directory_sync_failure_stays_hold_after_reopen_and_blocks_next_select(self):
        first = self.install('first'); second = self.install('second')
        real_sync = release_module._sync
        failed = []
        def sync(path):
            if Path(path).name == 'select-first' and (Path(path) / 'COMMITTED').exists() and not failed:
                failed.append(True); raise OSError('synthetic directory fsync failure')
            return real_sync(path)
        with patch.object(release_module, '_sync', side_effect=sync):
            with self.assertRaises(OSError): self.select(first)
        path = self.workspace / 'transactions/select-first'
        self.assertTrue((path / 'COMMITTED').exists()); self.assertTrue((path / 'HOLD').exists())
        reopened = OfflineReleases(self.workspace)
        report = reopened.transaction('select-first')
        self.assertEqual(report['state'], 'SELECTED_RECEIPT_PENDING_HOLD')
        self.assertEqual(report['observed_durability'], 'UNKNOWN')
        self.assertFalse(report['original_call_success_proven'])
        with self.assertRaisesRegex(ValueError, 'UNRESOLVED'):
            reopened.select(second, first, 'next', self.fx.center, self.evidence)
        report = reopened.resolve_transaction('select-first', self.fx.center, self.evidence)
        self.assertEqual(report['state'], 'RECOVERED_COMMITTED')
        self.assertFalse(report['original_call_success_proven'])
        reopened.select(second, first, 'explicit-next', self.fx.center, self.evidence)

    def test_recovery_marker_sync_failure_cannot_override_old_hold_or_claim_success(self):
        target = self.install()
        with patch.object(self.releases, '_after_select', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.select(target)
        real_sync = release_module._sync
        def sync(path):
            # Persistent failure: even attempts to fsync HOLD fail. Observation
            # must remain UNKNOWN; this does not simulate actual power loss.
            if Path(path).name == 'select-first' and (Path(path) / 'RECOVERED.json').exists():
                raise OSError('persistent synthetic fsync failure')
            return real_sync(path)
        with patch.object(release_module, '_sync', side_effect=sync):
            with self.assertRaises(OSError):
                self.releases.resolve_transaction('select-first', self.fx.center, self.evidence)
        reopened = OfflineReleases(self.workspace)
        report = reopened.transaction('select-first')
        self.assertEqual(report['state'], 'SELECTED_RECEIPT_PENDING_HOLD')
        self.assertFalse(report['original_call_success_proven'])
        self.assertEqual(report['observed_durability'], 'UNKNOWN')
        self.assertEqual(reopened.resolve_transaction('select-first', self.fx.center, self.evidence)['state'], 'RECOVERED_COMMITTED')

    def test_existing_completion_file_is_resynced_before_explicit_recovery(self):
        target = self.install()
        marker = self.workspace / 'transactions/select-first/COMMITTED'
        original_fsync = os.fsync
        attempts = []
        def fsync(fd):
            if marker.exists() and os.fstat(fd).st_ino == marker.stat().st_ino:
                attempts.append(fd)
                raise OSError('synthetic completion file fsync failure')
            return original_fsync(fd)
        with patch.object(release_module.os, 'fsync', side_effect=fsync):
            with self.assertRaises(OSError): self.select(target)
            self.assertTrue(marker.exists())
            self.assertEqual(OfflineReleases(self.workspace).transaction('select-first')['state'],
                             'SELECTED_RECEIPT_PENDING_HOLD')
            with self.assertRaises(OSError):
                self.releases.resolve_transaction('select-first', self.fx.center, self.evidence)
        # First write and explicit recovery each fsync the actual marker file.
        self.assertEqual(len(attempts), 2)
        reopened = OfflineReleases(self.workspace)
        self.assertEqual(reopened.transaction('select-first')['observed_durability'], 'UNKNOWN')
        result = reopened.resolve_transaction('select-first', self.fx.center, self.evidence)
        self.assertEqual(result['state'], 'RECOVERED_COMMITTED')
        self.assertFalse(result['original_call_success_proven'])

    def test_recovery_record_file_sync_failure_stays_hold_and_is_resynced(self):
        target = self.install()
        with patch.object(self.releases, '_after_select', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.select(target)
        marker = self.workspace / 'transactions/select-first/RECOVERED.json'
        original_fsync = os.fsync
        attempts = []
        def fsync(fd):
            if marker.exists() and os.fstat(fd).st_ino == marker.stat().st_ino:
                attempts.append(fd)
                raise OSError('synthetic recovery record file fsync failure')
            return original_fsync(fd)
        with patch.object(release_module.os, 'fsync', side_effect=fsync):
            for _ in range(2):
                with self.assertRaises(OSError):
                    self.releases.resolve_transaction('select-first', self.fx.center, self.evidence)
        self.assertEqual(len(attempts), 2)
        reopened = OfflineReleases(self.workspace)
        self.assertEqual(reopened.transaction('select-first')['state'], 'SELECTED_RECEIPT_PENDING_HOLD')
        self.assertEqual(reopened.resolve_transaction('select-first', self.fx.center, self.evidence)['state'],
                         'RECOVERED_COMMITTED')

    def test_hold_removal_directory_sync_failure_recreates_conservative_hold(self):
        target = self.install()
        with patch.object(self.releases, '_after_select', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.select(target)
        real_sync = release_module._sync
        failed = []
        def sync(path):
            path = Path(path)
            if (path.name == 'select-first' and (path / 'RECOVERED.json').exists()
                    and (path / 'COMMITTED').exists() and not (path / 'HOLD').exists() and not failed):
                failed.append(True); raise OSError('synthetic HOLD removal directory fsync failure')
            return real_sync(path)
        with patch.object(release_module, '_sync', side_effect=sync):
            with self.assertRaises(OSError):
                self.releases.resolve_transaction('select-first', self.fx.center, self.evidence)
        reopened = OfflineReleases(self.workspace)
        report = reopened.transaction('select-first')
        self.assertTrue(failed)
        self.assertEqual(report['state'], 'SELECTED_RECEIPT_PENDING_HOLD')
        self.assertEqual(report['observed_durability'], 'UNKNOWN')
        self.assertEqual(reopened.resolve_transaction('select-first', self.fx.center, self.evidence)['state'],
                         'RECOVERED_COMMITTED')

    def test_center_backup_wal_or_journal_sidecar_is_rejected_even_when_main_hash_matches(self):
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = Path(str(self.evidence['database']) + suffix)
            sidecar.write_bytes(b'fixture pending sidecar'); sidecar.chmod(0o600)
            try:
                with self.assertRaisesRegex(ValueError, 'CLOSED_STANDALONE'):
                    verify_center_backup(self.fx.center, self.evidence)
            finally: sidecar.unlink()

    def test_foreign_import_origin_cannot_attest_same_named_source(self):
        import scripts.community_mini_application as application_module
        other = self.root / 'same-name.py'
        other.write_bytes(Path(application_module.__file__).read_bytes())
        with patch.object(application_module, '__file__', str(other)):
            with self.assertRaisesRegex(ValueError, 'IMPORTED_SOURCE_ORIGIN'): self.install()
        self.assertEqual(list((self.workspace / 'generations').iterdir()), [])

    def test_composition_cannot_probe_original_db_instead_of_restored_db(self):
        def mixed(center, path):
            app = self.compose(center, path)
            app.stage.runtime.saas.orders = self.app.stage.runtime.saas.orders
            return app
        with self.assertRaisesRegex(ValueError, 'RUNTIME_CONNECTIONS'): self.install(compose=mixed)
        self.assertFalse((self.workspace / 'generations/first/READY').exists())

    def test_current_json_rejects_unknown_fields_and_broken_symlink(self):
        path = self.workspace / 'current.json'
        path.write_text(json.dumps({'generation': 'first', 'ready_sha256': 'a' * 64, 'extra': True})); path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'EXACT_GENERATION_PAIR'): self.releases.current()
        path.unlink(); path.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.releases.current()

    def test_select_cannot_cover_up_corrupt_current_source_data_pair(self):
        first = self.install('first'); second = self.install('second'); self.select(first)
        (self.workspace / 'generations/first/state/orders.sqlite').write_bytes(b'corrupt prior data')
        with self.assertRaises(ValueError):
            self.releases.select(second, first, 'cover-corrupt', self.fx.center, self.evidence)
        self.assertEqual(self.releases.current(), first)
        self.assertFalse((self.workspace / 'transactions/cover-corrupt').exists())

    def test_select_rejects_missing_or_ready_mismatched_current_generation(self):
        first = self.install('first'); second = self.install('second'); self.select(first)
        path = self.workspace / 'current.json'
        for altered in ({'generation': 'missing', 'ready_sha256': first['ready_sha256']},
                        {'generation': 'first', 'ready_sha256': 'f' * 64}):
            path.write_bytes(release_module._json(altered))
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.releases.select(second, altered, 'cover-missing', self.fx.center, self.evidence)
            self.assertEqual(self.releases.current(), altered)
            self.assertFalse((self.workspace / 'transactions/cover-missing').exists())

    def test_symlink_transaction_parent_is_rejected_before_any_outside_write(self):
        target = self.install()
        outside = self.root / 'outside'; outside.mkdir(mode=0o700)
        parent = self.workspace / 'transactions'; parent.rmdir(); parent.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.select(target)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertIsNone(self.releases.current())
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): OfflineReleases(self.workspace)

    def test_symlink_generation_parent_is_rejected_before_any_outside_write(self):
        outside = self.root / 'outside'; outside.mkdir(mode=0o700)
        parent = self.workspace / 'generations'; parent.rmdir(); parent.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.install()
        self.assertEqual(list(outside.iterdir()), [])
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): OfflineReleases(self.workspace)

    def test_generation_json_rejects_unknown_fields_even_with_rehashed_ready(self):
        target = self.install(); root = self.workspace / 'generations/first'
        record = json.loads((root / 'generation.json').read_bytes()); record['unexpected'] = True
        raw = json.dumps(record).encode(); (root / 'generation.json').write_bytes(raw)
        (root / 'READY').write_text(hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError, 'OFFLINE_GENERATION'): inspect_generation(root)

    def test_transaction_json_rejects_unknown_fields_and_unknown_objects(self):
        target = self.install(); self.select(target)
        root = self.workspace / 'transactions/select-first'
        original = (root / 'intent.json').read_bytes()
        record = json.loads(original); record['unexpected'] = True
        (root / 'intent.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'EXACT_TRANSACTION'): self.releases.transaction('select-first')
        (root / 'intent.json').write_bytes(original)
        (root / 'unknown').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'FILE_SET'): self.releases.transaction('select-first')


if __name__ == '__main__':
    unittest.main()
