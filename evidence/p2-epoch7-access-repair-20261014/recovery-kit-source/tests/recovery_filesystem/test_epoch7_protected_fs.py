"""Actual filesystem tests confined to candidate/fixtures temporary trees."""
import copy
import hashlib
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

import epoch7_delta as d
import epoch7_additive_identity as additive
import epoch7_protected_fs as fs


class FixtureAuthority(object):
    def __init__(self): self.allowed = True; self.calls = 0
    def check(self):
        self.calls += 1
        if not self.allowed: raise ValueError('FIXTURE_APPROVAL_OR_LOCK_DENIED')
    def journal_binding(self):
        return {'fixture_only': True, 'review_id': 7000000000, 'delta_sha256': '1' * 64}


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        base = pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent / 'fixtures'
        base.mkdir(exist_ok=True, mode=0o700)
        self.temp = tempfile.TemporaryDirectory(prefix='recovery-fs-', dir=str(base))
        self.root = pathlib.Path(self.temp.name)
        self.auth = FixtureAuthority()
        self.uid, self.gid = os.geteuid(), os.getegid()
        self.path = '/etc/xuanjun-development/dispatcher.json'
        self.mask = sorted(d.OWNER_MASKS)[0]
        for parent in (os.path.dirname(self.path), os.path.dirname(self.mask),
                       fs.TRANSACTION, d.GENERATION):
            self.local(parent).mkdir(parents=True, exist_ok=True, mode=0o755)
        os.chmod(str(self.local(fs.TRANSACTION)), 0o700)
        os.chmod(str(self.local(d.GENERATION)), 0o750)
        self.local(self.path).write_bytes(b'old protected bytes')
        os.chmod(str(self.local(self.path)), 0o640)
        os.symlink('/dev/null', str(self.local(self.mask)))
        self.io = fs.ProtectedFilesystem(self.auth, fixture_root=str(self.root))

    def tearDown(self): self.temp.cleanup()
    def local(self, logical): return self.root / logical.lstrip('/')

    def journal(self, name, state):
        value = {'schema': 1, 'name': name, 'transaction_id': d.TX,
                 'binding': self.auth.journal_binding(), 'state': state}
        raw = d.canonical(value) + b'\n'
        if self.io.journal_exists(name):
            self.io.replace_exact(name, self.io.read_journal(name), raw, self.uid, self.gid, 0o600)
        else:
            self.io.create_exclusive(name, raw, self.uid, self.gid, 0o600)

    def intent(self, path=None):
        path = path or self.path
        before = self.io.read_target(path)
        raw = b'new reviewed bytes'
        after = {'kind': 'FILE', 'sha256': fs.raw_sha(raw), 'uid': self.uid,
                 'gid': self.gid, 'mode': 0o644 if path in d.OWNER_MASKS else 0o640}
        self.journal('epoch7-recovery-execution.json', {'stage': 'TARGET_DELTA_INTENT'})
        row = {'path': path, 'before': before, 'after': after, 'state': 'BACKUP_INTENT'}
        self.journal('epoch8-runtime-provisioning.json', {'stage': 'TARGET_DELTA_INTENT', 'targets': [row]})
        name = 'epoch7-target-before-' + hashlib.sha256(path.encode()).hexdigest() + '.private'
        backup = self.io.backup_target_exact(path, before, name)
        row.update(state='REPLACE_INTENT', backup=backup)
        self.journal('epoch8-runtime-provisioning.json', {'stage': 'TARGET_DELTA_INTENT', 'targets': [row]})
        return before, raw, after, name

    def generation_intent(self):
        before = self.io.read_generation()
        after = {k: v for k, v in before.items() if k not in d.DIRECTORY_STAMP_KEYS}
        after.update(mode=0o700, access_acl='user::rwx\ngroup::---\nother::---\n')
        self.journal('epoch7-recovery-execution.json', {'stage': 'GENERATION_ACCESS_INTENT'})
        self.journal('epoch7-generation-access.json',
                     {'stage': 'GENERATION_ACCESS_INTENT', 'before': before, 'after': after})
        return before, after

    def additive_intent(self):
        before = self.io.read_additive_absence(); raw = b'{"fixture":"nonsecret"}\n'
        after = {'kind': 'FILE', 'uid': self.uid, 'gid': self.gid, 'mode': 0o644, 'sha256': fs.raw_sha(raw)}
        self.journal('epoch7-recovery-execution.json', {'stage': 'ADDITIVE_PUBLICATION_INTENT'})
        self.journal('epoch7-owner-identity-publication.json',
                     {'stage': 'ADDITIVE_PUBLICATION_INTENT', 'before': before, 'after': after})
        return before, raw, after

    def test_second_identity_path_uses_own_durable_intent(self):
        import epoch7_additive_server as server
        before = self.io.read_additive_absence(server.PATH); raw = b'{"synthetic":"server"}'
        after = {'kind': 'FILE', 'uid': self.uid, 'gid': self.gid, 'mode': 0o644, 'sha256': fs.raw_sha(raw)}
        self.journal('epoch7-recovery-execution.json', {'stage': 'ADDITIVE_PUBLICATION_INTENT'})
        self.journal('epoch7-server-identity-publication.json',
                     {'stage': 'ADDITIVE_PUBLICATION_INTENT', 'before': before, 'after': after})
        observed = self.io.publish_additive_exact(before, raw, after)
        self.assertEqual(observed['nlink'], 1)
        self.assertEqual(self.local(server.PATH).read_bytes(), raw)
        self.assertFalse(self.local(additive.PATH).exists())

    def test_one_pin_intent_cannot_authorize_other_pin(self):
        import epoch7_additive_server as server
        before, raw, after = self.additive_intent()
        before = self.io.read_additive_absence(server.PATH)
        with self.assertRaises(FileNotFoundError): self.io.publish_additive_exact(before, raw, after)
        self.assertFalse(self.local(server.PATH).exists())

    def test_missing_attempt_intent_prevents_generation_chmod(self):
        before, after = self.generation_intent()
        self.journal('epoch7-recovery-execution.json', {'stage': 'ADMITTED'})
        with self.assertRaisesRegex(ValueError, 'DURABLE_PHASE_INTENT'):
            self.io.chmod_generation_exact(before, after)
        self.assertEqual(self.io.read_generation()['mode'], 0o750)

    def test_partial_before_metadata_rejected(self):
        before, raw, after, unused = self.intent()
        del before['ctime_ns']
        # A matching partial journal must not weaken the filesystem CAS.
        name = 'epoch7-target-before-' + hashlib.sha256(self.path.encode()).hexdigest() + '.private'
        row = {'path': self.path, 'before': before, 'after': after, 'state': 'REPLACE_INTENT',
               'backup': {'name': name, 'sha256': before['sha256'], 'kind': 'FILE'}}
        self.journal('epoch8-runtime-provisioning.json', {'stage': 'TARGET_DELTA_INTENT', 'targets': [row]})
        with self.assertRaisesRegex(ValueError, 'EXACT_BEFORE_STATE'):
            self.io.replace_target_exact(self.path, before, raw, after)

    def test_production_effect_checker_rejects_unreviewed_target_metadata(self):
        from test_epoch7_injected_recovery import prepared
        unused, unused2, ops, verifier, gate, payloads = prepared()
        adapter = object.__new__(fs.ProtectedFilesystem)
        adapter.fixture = False; adapter.gate = gate
        row = next(x for x in gate.delta['changes'] if x['operation'] == 'REPLACE_EXACT_FILE')
        adapter._approved_effect('retained', row['path'], row['before'], row['after'])
        with self.assertRaisesRegex(ValueError, 'REVIEWED_RETAINED_EFFECT'):
            adapter._approved_effect('retained', row['path'], row['before'], dict(row['after'], mode=0o600))

    def test_metadata_includes_exact_inode_size_and_nanosecond_times(self):
        row = self.io.read_target(self.path); actual = os.stat(str(self.local(self.path)))
        self.assertEqual((row['dev'], row['ino'], row['size'], row['mtime_ns'], row['ctime_ns']),
            (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns))
        self.assertEqual(row['sha256'], fs.raw_sha(b'old protected bytes'))

    def test_retained_file_replaced_with_private_original_backup(self):
        before, raw, after, backup = self.intent()
        self.io.replace_target_exact(self.path, before, raw, after)
        now = self.io.read_target(self.path)
        self.assertNotEqual(now['ino'], before['ino'])
        self.assertEqual(self.local(self.path).read_bytes(), raw)
        self.assertEqual(self.local(fs.TRANSACTION + '/' + backup).read_bytes(), b'old protected bytes')
        self.assertEqual(os.stat(str(self.local(fs.TRANSACTION + '/' + backup))).st_mode & 0o777, 0o600)

    def test_exact_owner_mask_can_be_replaced_without_following_dev_null(self):
        before, raw, after, backup = self.intent(self.mask)
        self.assertEqual(before['kind'], 'MASK')
        self.io.replace_target_exact(self.mask, before, raw, after)
        self.assertFalse(self.local(self.mask).is_symlink())
        self.assertEqual(self.local(self.mask).read_bytes(), raw)
        self.assertEqual(self.local(fs.TRANSACTION + '/' + backup).read_bytes(), d.canonical(before))

    def test_target_effect_requires_durable_intent(self):
        before = self.io.read_target(self.path)
        after = {'kind': 'FILE', 'sha256': fs.raw_sha(b'new'), 'uid': self.uid, 'gid': self.gid, 'mode': 0o640}
        with self.assertRaises(FileNotFoundError): self.io.replace_target_exact(self.path, before, b'new', after)
        self.assertEqual(self.local(self.path).read_bytes(), b'old protected bytes')

    def test_private_backup_cannot_be_reused_or_overwritten(self):
        before, raw, after, name = self.intent()
        # Reset only the synthetic INTENT, never a production journal.
        row = {'path': self.path, 'before': before, 'after': after, 'state': 'BACKUP_INTENT'}
        self.journal('epoch8-runtime-provisioning.json', {'stage': 'TARGET_DELTA_INTENT', 'targets': [row]})
        with self.assertRaises(FileExistsError): self.io.backup_target_exact(self.path, before, name)

    def test_backup_byte_drift_blocks_replacement(self):
        before, raw, after, name = self.intent()
        self.local(fs.TRANSACTION + '/' + name).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'BACKUP_CHANGED'):
            self.io.replace_target_exact(self.path, before, raw, after)

    def test_inode_replacement_even_with_same_bytes_is_rejected(self):
        before, raw, after, unused = self.intent()
        replacement = self.local(self.path + '.other'); replacement.write_bytes(b'old protected bytes')
        os.chmod(str(replacement), 0o640); os.replace(str(replacement), str(self.local(self.path)))
        with self.assertRaisesRegex(ValueError, 'EXACT_BEFORE_STATE'):
            self.io.replace_target_exact(self.path, before, raw, after)

    def test_timestamp_drift_even_with_same_bytes_is_rejected(self):
        before, raw, after, unused = self.intent()
        os.utime(str(self.local(self.path)), ns=(before['mtime_ns'] + 1, before['mtime_ns'] + 1))
        with self.assertRaisesRegex(ValueError, 'EXACT_BEFORE_STATE'):
            self.io.replace_target_exact(self.path, before, raw, after)

    def test_nonowner_target_symlink_rejected(self):
        self.local(self.path).unlink(); os.symlink('/etc/passwd', str(self.local(self.path)))
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_TARGET_SYMLINK'): self.io.read_target(self.path)

    def test_owner_mask_other_destination_rejected(self):
        self.local(self.mask).unlink(); os.symlink('/etc/passwd', str(self.local(self.mask)))
        with self.assertRaisesRegex(ValueError, 'EXACT_STABLE_OWNER_MASK'): self.io.read_target(self.mask)

    def test_hardlink_rejected(self):
        os.link(str(self.local(self.path)), str(self.local(self.path + '.hardlink')))
        with self.assertRaisesRegex(ValueError, 'PROTECTED_REGULAR'): self.io.read_target(self.path)

    def test_fifo_rejected_without_read_blocking(self):
        self.local(self.path).unlink(); os.mkfifo(str(self.local(self.path)), 0o600)
        with self.assertRaisesRegex(ValueError, 'PROTECTED_REGULAR'): self.io.read_target(self.path)

    def test_world_writable_file_and_parent_rejected(self):
        os.chmod(str(self.local(self.path)), 0o666)
        with self.assertRaisesRegex(ValueError, 'PROTECTED_REGULAR'): self.io.read_target(self.path)
        os.chmod(str(self.local(self.path)), 0o640)
        os.chmod(str(self.local(os.path.dirname(self.path))), 0o777)
        with self.assertRaisesRegex(ValueError, 'UNSAFE_ROOT_PROTECTED_PARENT'): self.io.read_target(self.path)

    def test_symlink_ancestor_rejected(self):
        parent = self.local('/etc/xuanjun-development')
        moved = self.local('/etc/moved'); os.rename(str(parent), str(moved))
        os.symlink(str(moved), str(parent))
        with self.assertRaises(OSError): self.io.read_target(self.path)

    def test_arbitrary_or_parent_traversal_target_rejected(self):
        for target in ('/etc/passwd', '/etc/../passwd', '/tmp/arbitrary'):
            with self.assertRaisesRegex(ValueError, 'TARGET_SCOPE'): self.io.read_target(target)

    def test_fixture_root_cannot_point_at_real_host_or_tmp(self):
        for target in ('/', '/tmp', '/etc'):
            with self.assertRaisesRegex(ValueError, 'FIXTURE_ROOT_CONFINEMENT'):
                fs.ProtectedFilesystem(self.auth, fixture_root=target)

    def test_production_mode_has_no_nonroot_fallback(self):
        if os.geteuid() == 0: self.skipTest('nonroot boundary case')
        with self.assertRaisesRegex(ValueError, 'PRODUCTION_ROOT_REQUIRED'):
            fs.ProtectedFilesystem(self.auth)

    def test_journal_creation_is_exclusive_and_private(self):
        self.journal('epoch7-recovery-execution.json', {'stage': 'ADMITTED'})
        info = self.io.read_journal('epoch7-recovery-execution.json')
        self.assertEqual(info['mode'], 0o600)
        with self.assertRaises(FileExistsError):
            self.io.create_exclusive('epoch7-recovery-execution.json', b'other', self.uid, self.gid, 0o600)

    def test_historical_journal_name_cannot_be_written(self):
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_JOURNAL'):
            self.io.create_exclusive('epoch5-recovery-execution.json', b'reset', self.uid, self.gid, 0o600)

    def test_journal_cas_rejects_stale_bytes(self):
        self.journal('epoch7-recovery-execution.json', {'stage': 'ADMITTED'})
        old = self.io.read_journal('epoch7-recovery-execution.json')
        self.journal('epoch7-recovery-execution.json', {'stage': 'NEXT'})
        with self.assertRaisesRegex(ValueError, 'EXACT_BEFORE_STATE'):
            self.io.replace_exact('epoch7-recovery-execution.json', old, b'bad', self.uid, self.gid, 0o600)

    def test_journal_fsync_failure_leaves_existing_evidence(self):
        with mock.patch.object(fs.os, 'fsync', side_effect=OSError('fixture fsync failure')):
            with self.assertRaises(OSError):
                self.io.create_exclusive('epoch7-recovery-execution.json', b'partial intent', self.uid, self.gid, 0o600)
        self.assertTrue(self.io.journal_exists('epoch7-recovery-execution.json'))

    def test_failed_atomic_replace_leaves_original_and_intent(self):
        before, raw, after, unused = self.intent()
        with mock.patch.object(fs.os, 'replace', side_effect=OSError('fixture replace failure')):
            with self.assertRaises(OSError): self.io.replace_target_exact(self.path, before, raw, after)
        self.assertEqual(self.local(self.path).read_bytes(), b'old protected bytes')
        self.assertEqual(list(self.local('/etc/xuanjun-development').glob('.epoch7-recovery-*')), [])

    def test_gate_denial_prevents_effect(self):
        before, raw, after, unused = self.intent(); self.auth.allowed = False
        with self.assertRaisesRegex(ValueError, 'APPROVAL_OR_LOCK_DENIED'):
            self.io.replace_target_exact(self.path, before, raw, after)
        self.assertEqual(self.local(self.path).read_bytes(), b'old protected bytes')

    def test_default_acl_is_not_silently_inherited(self):
        original = fs.os.getxattr
        def added_acl(fd, name):
            if name == 'system.posix_acl_default': return b'fixture ACL'
            return original(fd, name)
        with mock.patch.object(fs.os, 'getxattr', side_effect=added_acl):
            with self.assertRaisesRegex(ValueError, 'DEFAULT_ACL_REQUIRES_REVIEW'):
                self.io.read_target(self.path)

    def test_additive_publication_is_exact_no_overwrite_single_link(self):
        before, raw, after = self.additive_intent()
        observed = self.io.publish_additive_exact(before, raw, after)
        self.assertEqual(observed['nlink'], 1); self.assertEqual(observed['mode'], 0o644)
        self.assertEqual(self.local(additive.PATH).read_bytes(), raw)
        with self.assertRaisesRegex(ValueError, 'ALREADY_EXISTS'):
            self.io.publish_additive_exact(before, raw, after)

    def test_additive_preexisting_symlink_never_followed(self):
        before, raw, after = self.additive_intent()
        os.symlink('/etc/passwd', str(self.local(additive.PATH)))
        with self.assertRaisesRegex(ValueError, 'ALREADY_EXISTS'):
            self.io.publish_additive_exact(before, raw, after)
        self.assertTrue(self.local(additive.PATH).is_symlink())

    def test_additive_missing_intent_blocks(self):
        before = self.io.read_additive_absence(); raw = b'{}'
        after = {'kind': 'FILE', 'uid': self.uid, 'gid': self.gid, 'mode': 0o644, 'sha256': fs.raw_sha(raw)}
        with self.assertRaises(FileNotFoundError): self.io.publish_additive_exact(before, raw, after)
        self.assertFalse(self.local(additive.PATH).exists())

    def test_generation_chmod_preserves_exact_inode_owner_and_mtime(self):
        before, after = self.generation_intent()
        result = self.io.chmod_generation_exact(before, after)
        self.assertEqual(result['mode'], 0o700)
        for key in ('dev', 'ino', 'uid', 'gid', 'size', 'nlink', 'mtime_ns'):
            self.assertEqual(result[key], before[key])
        self.assertGreaterEqual(result['ctime_ns'], before['ctime_ns'])

    def test_generation_missing_intent_blocks(self):
        before = self.io.read_generation()
        after = {k: v for k, v in before.items() if k not in d.DIRECTORY_STAMP_KEYS}
        after.update(mode=0o700, access_acl='user::rwx\ngroup::---\nother::---\n')
        with self.assertRaises(FileNotFoundError): self.io.chmod_generation_exact(before, after)
        self.assertEqual(os.stat(str(self.local(d.GENERATION))).st_mode & 0o777, 0o750)

    def test_generation_inode_change_rejected(self):
        before, after = self.generation_intent()
        old = self.local(d.GENERATION); os.rename(str(old), str(old) + '.old')
        old.mkdir(mode=0o750)
        with self.assertRaisesRegex(ValueError, 'EXACT_BEFORE_STATE'):
            self.io.chmod_generation_exact(before, after)

    def test_generation_failure_keeps_intent_and_no_chown(self):
        before, after = self.generation_intent()
        with mock.patch.object(fs.os, 'fchmod', side_effect=OSError('fixture chmod failure')):
            with self.assertRaises(OSError): self.io.chmod_generation_exact(before, after)
        self.assertEqual(os.stat(str(self.local(d.GENERATION))).st_mode & 0o777, 0o750)
        self.assertTrue(self.io.journal_exists('epoch7-generation-access.json'))

    def test_generation_identity_change_not_bundled_into_chmod(self):
        before, after = self.generation_intent(); after['uid'] += 1
        with self.assertRaisesRegex(ValueError, 'CHMOD_ONLY'):
            self.io.chmod_generation_exact(before, after)

    def test_generation_symlink_rejected(self):
        before, after = self.generation_intent()
        old = self.local(d.GENERATION); moved = str(old) + '.old'
        os.rename(str(old), moved); os.symlink(moved, str(old))
        with self.assertRaises(OSError): self.io.chmod_generation_exact(before, after)


if __name__ == '__main__': unittest.main()
