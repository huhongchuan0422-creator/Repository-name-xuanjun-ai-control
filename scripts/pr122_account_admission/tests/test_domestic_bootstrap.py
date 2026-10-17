"""Offline filesystem fixtures only. Never invoke real sudo or visudo."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'domestic_bootstrap.py'
spec = importlib.util.spec_from_file_location('bootstrap_test', SOURCE)
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in {'BASE': root / 'base', 'EXEC': root / 'bin' / 'wrapper', 'POLICY': root / 'etc' / 'policy', 'INPUT': root / 'input', 'OLD_CODE': b.sha(b'original channel')}.items():
            p = patch.object(b, name, value); p.start(); self.addCleanup(p.stop)
        for name, value in {'CONTROL': b.BASE / 'readonly-bootstrap-20261017', 'HELPER': b.BASE / 'readonly-admission.py'}.items():
            p = patch.object(b, name, value); p.start(); self.addCleanup(p.stop)
        for path in (b.BASE, b.EXEC.parent, b.POLICY.parent, b.INPUT): path.mkdir(mode=0o700)
        self.owner = patch.object(b, 'owner'); self.owner.start(); self.addCleanup(self.owner.stop)
        # /tmp is intentionally not a trusted production ancestor. Fixtures bypass only
        # ancestor checks; mode/hash/transaction/lock/fsync behavior remains real.
        self.security = patch.object(b, 'secure', side_effect=lambda path, directory=False: Path(path)); self.security.start(); self.addCleanup(self.security.stop)
        self.fdcheck = patch.object(b, 'file_stat'); self.fdcheck.start(); self.addCleanup(self.fdcheck.stop)
        self.check = patch.object(b, 'policy_check'); self.visudo = self.check.start(); self.addCleanup(self.check.stop)
        self.put(b.BASE / 'channel.py', b'original channel', 0o444)
        self.put(b.BASE / 'grant-state.json', b'{"state":"GRANTED"}', 0o600)
        self.put(b.BASE / '.upgrade-lock', b'', 0o600)
        self.put(b.EXEC, b.expected_wrapper(), 0o755); self.put(b.POLICY, b.expected_policy(), 0o440)
        helper = b'# fixed fixture helper\n'
        self.put(b.INPUT / 'domestic-readonly-helper.py', helper, 0o400)
        files = {'domestic-readonly-helper.py': helper, 'wrapper': b.new_wrapper(), 'sudoers': b.new_policy(), 'domestic_bootstrap.py': SOURCE.read_bytes()}
        manifest = {'schema': 1, 'scope': 'DOMESTIC_READONLY_BOOTSTRAP_20261017', 'files': {n: {'sha256': b.sha(v), 'size': len(v)} for n, v in files.items()}}
        self.put(b.INPUT / 'domestic-bootstrap-manifest.json', b.canonical(manifest), 0o400)
    def put(self, path, raw, mode):
        if path.exists(): path.chmod(0o600)
        path.write_bytes(raw); path.chmod(mode)
    def test_full_roundtrip_preserves_original_inode(self):
        inode = (b.BASE / 'channel.py').stat().st_ino
        self.assertFalse(b.plan()['trust_enrolled']); b.install(); b.verify()
        self.assertEqual(b.rollback()['state'], 'ROLLED_BACK')
        self.assertEqual((b.BASE / 'channel.py').stat().st_ino, inode)
        self.assertEqual(b.EXEC.read_bytes(), b.expected_wrapper()); self.assertTrue(b.HELPER.exists())
    def test_forward_retry_denied(self):
        b.install()
        with self.assertRaisesRegex(RuntimeError, 'TRANSACTION'): b.install()
    def test_rollback_retry_denied(self):
        b.install(); b.rollback()
        with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_ALREADY'): b.rollback()
    def test_drift_denied_before_mutation(self):
        self.put(b.EXEC, b'unknown', 0o755)
        with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_WRAPPER'): b.install()
        self.assertFalse(b.CONTROL.exists())
    def test_manifest_drift(self):
        self.put(b.INPUT / 'domestic-readonly-helper.py', b'changed', 0o400)
        with self.assertRaisesRegex(RuntimeError, 'MANIFEST_BINDING'): b.install()
    def test_mode_drift(self):
        b.POLICY.chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'MODE_DRIFT'): b.install()
    def test_visudo_failure_has_no_privilege_change(self):
        self.visudo.side_effect = RuntimeError('HOLD:VISUDO_REJECTED')
        with self.assertRaisesRegex(RuntimeError, 'VISUDO'): b.install()
        self.assertEqual(b.EXEC.read_bytes(), b.expected_wrapper()); self.assertFalse(b.HELPER.exists())
        self.assertTrue(b.CONTROL.exists())
    def test_partial_wrapper_install_rollback(self):
        original = b.replace
        def fail_policy(path, raw, mode):
            if path == b.POLICY: raise RuntimeError('interrupted')
            original(path, raw, mode)
        with patch.object(b, 'replace', side_effect=fail_policy):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'): b.install()
        with self.assertRaisesRegex(RuntimeError, 'PARTIAL'): b.verify()
        self.assertEqual(b.rollback()['state'], 'ROLLED_BACK')
    def test_unknown_state_rollback_denied(self):
        b.install(); self.put(b.POLICY, b'unknown', 0o440)
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN'): b.rollback()
    def test_original_inode_replaced_denied(self):
        b.install(); path = b.BASE / 'channel.py'; other = b.BASE / 'other'
        self.put(other, path.read_bytes(), 0o444); os.replace(other, path)
        with self.assertRaisesRegex(RuntimeError, 'INODE'): b.rollback()
    def test_existing_helper_denied(self):
        self.put(b.HELPER, b'unknown', 0o400)
        with self.assertRaisesRegex(RuntimeError, 'HELPER_EXISTS'): b.install()
    def test_missing_upgrade_lock_created_only_install(self):
        (b.BASE / '.upgrade-lock').unlink()
        b.plan(); self.assertFalse((b.BASE / '.upgrade-lock').exists())
        b.install(); self.assertEqual((b.BASE / '.upgrade-lock').stat().st_mode & 0o777, 0o600)
    def test_busy_canonical_lock(self):
        import fcntl
        with (b.BASE / 'channel.py').open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError): b.install()
        self.assertFalse(b.CONTROL.exists())
    def test_pending_replace_blocks_rollback(self):
        b.install(); self.put(b.EXEC.parent / ('.' + b.EXEC.name + '.readonly-bootstrap-pending'), b.new_wrapper(), 0o755)
        with self.assertRaisesRegex(RuntimeError, 'PARTIAL_STAGING'): b.rollback()
    def test_no_trust_enrollment(self):
        b.install(); self.assertFalse((b.BASE / 'READONLY_ADMISSION_TRUST.json').exists())
    def test_original_actions_fallback_exact(self):
        self.assertTrue(b.new_wrapper().endswith(b.expected_wrapper().split(b'exec /usr/bin/env', 1)[1]))
        self.assertEqual(b.new_policy().count(b'inspect-account-once'), 1)
    def test_owner_runner_denied(self):
        self.owner.stop()
        with patch.object(b.os, 'getuid', return_value=0), patch.object(b.os, 'geteuid', return_value=0), patch.object(b.os, 'uname') as uname, patch.dict(os.environ, {'SUDO_UID': '1002'}):
            uname.return_value.nodename = b.HOST
            with self.assertRaisesRegex(RuntimeError, 'OWNER_HOST'): b.owner()
    def test_preexisting_pin_or_receipt_denied(self):
        for name in ('READONLY_ADMISSION_TRUST.json', 'readonly-admission-20261017'):
            p = b.BASE / name; self.put(p, b'unknown', 0o600)
            with self.assertRaisesRegex(RuntimeError, 'PREEXISTING_ADMISSION_STATE'): b.install()
            p.unlink()
        self.assertFalse(b.CONTROL.exists())
    def test_pin_appears_before_policy_publish_denied(self):
        original = b.record
        def inject(state):
            original(state)
            if state == 'WRAPPER_INSTALLED': self.put(b.BASE / 'READONLY_ADMISSION_TRUST.json', b'unknown', 0o600)
        with patch.object(b, 'record', side_effect=inject):
            with self.assertRaisesRegex(RuntimeError, 'PREEXISTING_ADMISSION_STATE'): b.install()
        self.assertEqual(b.POLICY.read_bytes(), b.expected_policy())
    def test_verify_discloses_pin_and_receipt_presence(self):
        b.install()
        self.assertEqual(b.verify()['state'], 'INSTALLED_AWAITING_OWNER_PIN')
        self.put(b.BASE / 'READONLY_ADMISSION_TRUST.json', b'unknown', 0o600)
        (b.BASE / 'readonly-admission-20261017').mkdir(mode=0o700)
        result = b.verify()
        self.assertEqual(result['state'], 'INSTALLED_PIN_PRESENT_NOT_VALIDATED')
        self.assertTrue(result['trust_enrolled']); self.assertTrue(result['receipt_present'])
        self.assertFalse(result['trust_validated'])
    def test_descriptor_owner_and_links_rejected(self):
        from types import SimpleNamespace
        self.fdcheck.stop()
        for uid, mode, links in ((1002, 0o100444, 1), (0, 0o040700, 1), (0, 0o100444, 2), (0, 0o100666, 1)):
            with self.assertRaisesRegex(RuntimeError, 'UNSAFE_FILE_DESCRIPTOR'):
                b.file_stat(SimpleNamespace(st_uid=uid, st_mode=mode, st_nlink=links))
    def test_symlink_read_nofollow(self):
        p = b.BASE / 'link'; p.symlink_to(b.BASE / 'channel.py')
        with self.assertRaises(OSError): b.read(p)
    def test_busy_upgrade_lock(self):
        import fcntl
        with (b.BASE / '.upgrade-lock').open('rb') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError): b.install()
        self.assertFalse(b.CONTROL.exists())
    def test_extra_grant_metadata_preserved(self):
        raw = b'{"state":"GRANTED","grant_id":"fixture"}'
        self.put(b.BASE / 'grant-state.json', raw, 0o600)
        b.install(); b.rollback()
        self.assertEqual((b.BASE / 'grant-state.json').read_bytes(), raw)
    def test_secure_rejects_untrusted_ancestor(self):
        self.security.stop()
        with self.assertRaisesRegex(RuntimeError, 'ROOT_PRIVATE_PATH'): b.secure(b.BASE)

if __name__ == '__main__': unittest.main()
