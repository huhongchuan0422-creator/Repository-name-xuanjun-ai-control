from __future__ import absolute_import

import json
import hashlib
import sqlite3
from unittest import mock
import os
import shutil
import tempfile
import unittest

from install import p3_carrier_install as installer
from src.p3_operation_kernel import RunnerOperationStore, MIGRATION


def write_json(path, value, mode=0o600):
    with open(path, "w") as output:
        json.dump(value, output, sort_keys=True, separators=(",", ":"))
        output.write("\n")
    os.chmod(path, mode)


class CarrierInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="p3-installer-"))
        self.root = os.path.join(self.tmp, "carrier")
        self.releases = os.path.join(self.tmp, "releases")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(os.path.join(self.root, "src"))
        self.member = os.path.join(self.root, "src", "module.py")
        with open(self.member, "wb") as output:
            output.write(b"default_off = True\n")
        member_sha = installer._digest(self.member)
        self.archive = os.path.join(self.root, 'archive.tar')
        with open(self.archive, 'wb') as output: output.write(b'TEST_ONLY_ARCHIVE')
        self.archive_sha = hashlib.sha256(b'TEST_ONLY_ARCHIVE').hexdigest()
        self.dbpath = os.path.join(self.tmp, 'operations.sqlite')
        def connect(): return sqlite3.connect(self.dbpath, timeout=10)
        db = connect(); db.execute(MIGRATION); db.commit(); db.close()
        self.store = RunnerOperationStore(connect)
        self.manifest = {
            "schema": 1,
            "artifact_digest": self.archive_sha,
            "kind": "P3_IMMUTABLE_DEFAULT_OFF_INSTALL_CARRIER",
            "source_commit": "1" * 40,
            "source_tree": "2" * 40,
            "default_off": True,
            "execution_enabled": False,
            "notifications_enabled": False,
            "files": {"src/module.py": member_sha},
            "release_files": ["src/module.py"],
            "base_reviews": {"qa": "PASS", "security": "PASS"},
        }
        self.manifest_path = os.path.join(self.root, "CARRIER_MANIFEST.json")
        write_json(self.manifest_path, self.manifest)
        self.manifest_sha = installer._digest(self.manifest_path)

    def install(self, *args, **kwargs):
        kwargs.update(operation_store=self.store, archive_path=self.archive)
        return installer.install(*args, **kwargs)

    def recover(self, *args, **kwargs):
        stage = self.store.get('p3-stage:install-attempt-01')
        kwargs.setdefault('owner_fence', stage['adapter_correlation'] if stage else None)
        kwargs.update(operation_store=self.store)
        return installer.recover(*args, **kwargs)

    def rollback(self, *args, **kwargs):
        kwargs.update(operation_store=self.store, original_install_attempt='install-attempt-01')
        return installer.rollback(*args, **kwargs)

    def test_install_rejects_symlink_source_ancestor(self):
        original = os.path.join(self.root, 'src')
        moved = os.path.join(self.root, 'actual')
        os.rename(original, moved)
        os.symlink('actual', original)
        with self.assertRaises((OSError, ValueError, PermissionError)):
            self.install(self.root, self.manifest_path, self.manifest_sha,
                              self.archive_sha, self.releases, self.state,
                              'install-attempt-01', lambda: True, enforce_root=False)
        self.assertFalse(os.path.exists(self.releases))

    def _install_receipt_path(self):
        return os.path.join(
            self.releases, "p3-" + self.archive_sha[:20],
            "INSTALL_RECEIPT.json")

    def _rewrite_install_receipt(self, path, value):
        os.chmod(path, 0o600)
        write_json(path, value)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_install_is_default_off_idempotent_and_recoverable(self):
        first = self.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        self.assertEqual("INSTALLED_DEFAULT_OFF_NOT_BOUND", first["state"])
        second = self.install(self.root, self.manifest_path, self.manifest_sha,
                         self.archive_sha, self.releases, self.state,
                         "install-attempt-01", lambda: True, enforce_root=False)
        self.assertEqual("IN_PROGRESS_OR_HOLD", second["state"])
        recovered = self.recover(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state,
            "install-attempt-01")
        self.assertEqual("INSTALLED_EFFECT_RECOVERED_NO_REPLAY",
                         recovered["recovery"])

    def test_bound_or_executed_receipt_never_reads_back_idempotent_or_recovered(self):
        mutations = (
            {"host_bound": True},
            {"real_task_executed": True},
            {"host_bound": True, "real_task_executed": True},
        )
        for number, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                if number:
                    shutil.rmtree(self.releases)
                    if os.path.exists(self.state): shutil.rmtree(self.state)
                    db=self.store.connect(); db.execute('DELETE FROM p3_effect_operations'); db.commit(); db.close()
                self.install(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases, self.state,
                    "install-attempt-01", lambda: True,
                    enforce_root=False)
                receipt_path = self._install_receipt_path()
                with open(receipt_path) as source:
                    receipt = json.load(source)
                receipt.update(mutation)
                self._rewrite_install_receipt(receipt_path, receipt)

                observed = installer.readback(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases)
                self.assertEqual("CONFLICT", observed["state"])
                self.assertIn(observed["field"], mutation)

                duplicate = self.install(
                        self.root, self.manifest_path, self.manifest_sha,
                        self.archive_sha, self.releases, self.state,
                        "install-attempt-01", lambda: True,
                        enforce_root=False)
                self.assertEqual("IN_PROGRESS_OR_HOLD", duplicate["state"])

                recovered = self.recover(
                    self.root, self.manifest_path, self.manifest_sha,
                    self.archive_sha, self.releases, self.state,
                    "install-attempt-01")
                self.assertEqual("UNKNOWN", recovered["state"])
                self.assertEqual("RESULT_MISSING_HOLD_NO_REPLAY",
                                 recovered["recovery"])

    def test_install_receipt_requires_exact_keys_and_valid_attempt(self):
        self.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state,
            "install-attempt-01", lambda: True, enforce_root=False)
        receipt_path = self._install_receipt_path()
        with open(receipt_path) as source:
            receipt = json.load(source)
        receipt["unexpected"] = True
        self._rewrite_install_receipt(receipt_path, receipt)
        observed = installer.readback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases)
        self.assertEqual("receipt_keys", observed["field"])

        del receipt["unexpected"]
        receipt["attempt_id"] = "invalid attempt"
        self._rewrite_install_receipt(receipt_path, receipt)
        observed = installer.readback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases)
        self.assertEqual("attempt_id", observed["field"])

    def test_missing_current_controlled_authority_fails_before_effect(self):
        with self.assertRaisesRegex(PermissionError,
                                    "CURRENT_CONTROLLED_ENTRY_AUTHORITY_REQUIRED"):
            self.install(
                self.root, self.manifest_path, self.manifest_sha,
                self.archive_sha, self.releases, self.state,
                "install-attempt-01", lambda: False, enforce_root=False)
        self.assertFalse(os.path.exists(self.releases))
        self.assertFalse(os.path.exists(self.state))

    def test_rollback_only_quarantines_unbound_default_off_release(self):
        self.install(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "install-attempt-01",
            lambda: True, enforce_root=False)
        result = self.rollback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases, self.state, "rollback-attempt-01",
            lambda: True, enforce_root=False)
        self.assertEqual("ROLLED_BACK_DEFAULT_OFF_QUARANTINED", result["state"])
        self.assertIsNotNone(self.store.get('p3-rollback:rollback-attempt-01'))
        self.assertEqual("ABSENT", installer.readback(
            self.root, self.manifest_path, self.manifest_sha,
            self.archive_sha, self.releases)["state"])

    def test_interrupted_rollback_recovers_receipt_without_rename_replay(self):
        self.install(self.root, self.manifest_path, self.manifest_sha, self.archive_sha,
                     self.releases, self.state, 'install-attempt-01', lambda:True, enforce_root=False)
        def interrupt(phase):
            if phase == 'after_rename': raise RuntimeError('SIMULATED_INTERRUPT_AFTER_ROLLBACK_RENAME')
        with self.assertRaisesRegex(RuntimeError, 'SIMULATED_INTERRUPT_AFTER_ROLLBACK_RENAME'):
            self.rollback(self.root, self.manifest_path, self.manifest_sha, self.archive_sha,
                          self.releases, self.state, 'rollback-attempt-01', lambda:True,
                          enforce_root=False, fault_hook=interrupt)
        fence=self.store.get('p3-rollback-owner:install-attempt-01')['adapter_correlation']
        result=installer.recover_rollback(self.releases, 'rollback-attempt-01', 'install-attempt-01',
                                           operation_store=self.store, owner_fence=fence)
        self.assertEqual('ROLLBACK_EFFECT_RECOVERED_NO_REPLAY',result['recovery'])
        self.assertEqual('ROLLED_BACK_DEFAULT_OFF_QUARANTINED',result['state'])

    def test_interrupted_rollback_rejects_changed_quarantine_checkpoint(self):
        self.install(self.root, self.manifest_path, self.manifest_sha, self.archive_sha,
                     self.releases, self.state, 'install-attempt-01', lambda:True, enforce_root=False)
        def interrupt(phase):
            if phase == 'after_rename': raise RuntimeError('crash')
        with self.assertRaises(RuntimeError):
            self.rollback(self.root, self.manifest_path, self.manifest_sha, self.archive_sha,
                          self.releases, self.state, 'rollback-attempt-01', lambda:True,
                          enforce_root=False, fault_hook=interrupt)
        path=os.path.join(self.releases,'.p3-stage-install-attempt-01','src','module.py')
        os.chmod(path,0o600)
        with open(path,'ab') as output: output.write(b'changed')
        fence=self.store.get('p3-rollback-owner:install-attempt-01')['adapter_correlation']
        result=installer.recover_rollback(self.releases,'rollback-attempt-01','install-attempt-01',
                                           operation_store=self.store,owner_fence=fence)
        self.assertEqual('UNKNOWN',result['state'])

    def test_archive_tampering_rejected_before_journal_or_effect(self):
        with open(self.archive,'ab') as f: f.write(b'tampered')
        with self.assertRaises(ValueError):
            self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                         self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False)
        self.assertIsNone(self.store.get('p3-stage:install-attempt-01'))
        self.assertFalse(os.path.exists(self.releases))

    def test_integrated_install_crash_windows_reconcile_without_replay(self):
        for point in ('before_rename','after_rename','after_fsync'):
            with self.subTest(point=point):
                if os.path.isdir(self.releases): shutil.rmtree(self.releases)
                db=self.store.connect(); db.execute('DELETE FROM p3_effect_operations'); db.commit(); db.close()
                def crash(phase):
                    if phase==point: raise RuntimeError('simulated-crash')
                with self.assertRaisesRegex(RuntimeError,'simulated-crash'):
                    self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                 self.releases,self.state,'install-attempt-01',lambda:True,
                                 enforce_root=False,fault_hook=crash)
                result=self.recover(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                    self.releases,self.state,'install-attempt-01')
                self.assertEqual('NOT_SWITCHED_HOLD' if point=='before_rename' else 'SWITCHED',result['state'])
                duplicate=self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                 self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False)
                self.assertEqual('IN_PROGRESS_OR_HOLD',duplicate['state'])

    def test_staging_receipt_crash_is_durable_unknown_and_no_replay(self):
        def crash(phase):
            if phase=='after_receipt': raise RuntimeError('staging-crash')
        with self.assertRaisesRegex(RuntimeError,'staging-crash'):
            self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                         self.releases,self.state,'install-attempt-01',lambda:True,
                         enforce_root=False,fault_hook=crash)
        self.assertEqual('UNKNOWN',self.store.get('p3-stage:install-attempt-01')['state'])
        self.assertIsNone(self.store.get('p3-install:install-attempt-01'))
        self.assertEqual('UNKNOWN',self.recover(self.root,self.manifest_path,self.manifest_sha,
                         self.archive_sha,self.releases,self.state,'install-attempt-01')['state'])
        duplicate=self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                         self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False)
        self.assertEqual('IN_PROGRESS_OR_HOLD',duplicate['state'])

    def test_replaced_target_before_rename_yields_unknown_not_replay(self):
        target=os.path.join(self.releases,'p3-'+self.archive_sha[:20])
        def replace(phase):
            if phase=='before_rename':
                os.mkdir(target,0o700)
                with open(os.path.join(target,'other'),'wb') as f:f.write(b'other')
        with self.assertRaises(RuntimeError):
            self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                         self.releases,self.state,'install-attempt-01',lambda:True,
                         enforce_root=False,fault_hook=replace)
        state=self.recover(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                           self.releases,self.state,'install-attempt-01')
        self.assertEqual('UNKNOWN',state['state'])
        with open(os.path.join(target,'other'),'rb') as f:self.assertEqual(b'other',f.read())

    def test_repeated_rollback_is_idempotent(self):
        self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                     self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False)
        for _ in range(2):
            result=self.rollback(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                 self.releases,self.state,'rollback-attempt-01',lambda:True,enforce_root=False)
            self.assertIn(result['state'],('ROLLED_BACK_DEFAULT_OFF_QUARANTINED','IN_PROGRESS_OR_HOLD'))

    def test_cross_device_staging_is_rejected_and_journaled_unknown(self):
        original=installer.os.fstat
        class Altered:
            def __init__(self, real): self.real=real
            def __getattr__(self,name):
                return self.real.st_dev+1 if name=='st_dev' else getattr(self.real,name)
        def fake(fd):
            info=original(fd)
            try: link=os.readlink('/proc/self/fd/'+str(fd))
            except OSError: return info
            return Altered(info) if link.endswith('.p3-stage-install-attempt-01') else info
        with mock.patch.object(installer.os,'fstat',side_effect=fake):
            with self.assertRaisesRegex(ValueError,'CROSS_FILESYSTEM_REFUSED'):
                self.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                             self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False)
        self.assertEqual('UNKNOWN',self.store.get('p3-stage:install-attempt-01')['state'])
        self.assertIsNone(self.store.get('p3-install:install-attempt-01'))

    def test_changed_member_is_rejected(self):
        with open(self.member, "ab") as output:
            output.write(b"changed")
        with self.assertRaisesRegex(ValueError,
                                    "CARRIER_MEMBER_MISMATCH:src/module.py"):
            installer.verify_carrier(
                self.root, self.manifest_path, self.manifest_sha)


if __name__ == "__main__":
    unittest.main()
