import copy
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import tempfile
import types
import unittest
from unittest import mock
import install_received_services as m


class InstallTests(unittest.TestCase):
    def fixture(self):
        files = {entry: ('# synthetic ' + role + '\n').encode() for role, (entry, _) in m.ROLES.items()}
        facts = {role: {'entry': entry, 'closure_sha256': digest} for role, (entry, digest) in m.ROLES.items()}
        raw = m.package_bytes(files, facts)
        return files, raw

    def test_package_digest_and_source_digest_are_checked(self):
        files, raw = self.fixture()
        with mock.patch.object(m, 'PORTAL_SHA', m.sha(files[m.ROLES['portal'][0]])):
            self.assertEqual(set(m.unpack(raw, m.sha(raw))[1]), set(files))
            with self.assertRaisesRegex(m.Hold, 'PACKAGE_DIGEST'):
                m.unpack(raw, '0' * 64)
            obj = json.loads(raw); obj['files'][m.ROLES['portal'][0]]['sha256'] = '0' * 64
            bad = m.encoded(obj)
            with self.assertRaisesRegex(m.Hold, 'PACKAGE_MEMBER_HASH'):
                m.unpack(bad, m.sha(bad))

    def test_r4_pin_and_wrong_scope_refuse_before_install(self):
        _, raw = self.fixture()
        with self.assertRaisesRegex(m.Hold, 'R4_PORTAL_SOURCE_REQUIRED'):
            m.unpack(raw, m.sha(raw))
        bad = json.loads(raw); bad['requirements']['requests'] = '0.0'
        raw = m.encoded(bad)
        with self.assertRaisesRegex(m.Hold, 'PACKAGE_SCOPE'):
            m.unpack(raw, m.sha(raw))

    def test_traversal_and_non_source_files_rejected(self):
        for name in ('../escape.py', '/etc/evil.py', 'a/../evil.py', 'private.env', 'a\\b.py'):
            with self.assertRaisesRegex(m.Hold, 'SOURCE_PACKAGE_PATH'):
                m.package_bytes({name: b'x'}, {})

    def test_wrong_role_closure_is_not_accepted(self):
        files, raw = self.fixture()
        bad = json.loads(raw); bad['roles']['portal']['closure_sha256'] = '0' * 64
        raw = m.encoded(bad)
        with mock.patch.object(m, 'PORTAL_SHA', m.sha(files[m.ROLES['portal'][0]])):
            with self.assertRaisesRegex(m.Hold, 'ROLE_CLOSURE_BINDING'):
                m.unpack(raw, m.sha(raw))

    def test_private_write_never_overwrites_symlink_or_existing_file(self):
        with tempfile.TemporaryDirectory(dir='/root') as d:
            p = Path(d); old = p / 'old'; old.write_bytes(b'kept'); link = p / 'link'; link.symlink_to(old)
            for path in (link, old):
                with self.assertRaises(FileExistsError):
                    m.write(path, b'not-kept')
            self.assertEqual(old.read_bytes(), b'kept')

    def setup_receive(self, root):
        files, raw = self.fixture()
        base, attempt = root / 'new-prefix', root / 'new-attempt'
        def process(args, log, timeout):
            log.write_bytes(b'synthetic command model\n')
        patches = [mock.patch.object(m, 'BASE', base), mock.patch.object(m, 'ATTEMPT', attempt),
                   mock.patch.object(m, 'PORTAL_SHA', m.sha(files[m.ROLES['portal'][0]])),
                   mock.patch.object(m.os, 'uname', return_value=types.SimpleNamespace(nodename=m.DOMESTIC)),
                   mock.patch.object(m.sys, 'version_info', (3, 11, 6, 'final', 0)),
                   mock.patch.object(m, 'protected_snapshot', return_value={'units': 'fixed', 'current': 'fixed', 'index_sha256': 'fixed'}),
                   mock.patch.object(m, 'process', side_effect=process),
                   mock.patch.object(m.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=json.dumps(m.PINS)))]
        return files, raw, base, attempt, patches

    def run_receive(self, root, override=None):
        from contextlib import ExitStack
        files, raw, base, attempt, patches = self.setup_receive(root)
        previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
        try:
            with ExitStack() as stack:
                for p in patches: stack.enter_context(p)
                if override: override(stack)
                with contextlib.redirect_stdout(io.StringIO()):
                    m.receive(raw, m.sha(raw))
        finally:
            for s, h in previous.items(): signal.signal(s, h)
        return files, raw, base, attempt

    def test_actual_new_private_source_writes_with_synthetic_dependency_model(self):
        with tempfile.TemporaryDirectory(dir='/root') as d:
            files, raw, base, attempt = self.run_receive(Path(d))
            receipt = json.loads((attempt / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 'DOMESTIC_S07_PRIVATE_CODE_AND_ENV_INSTALLED_PASS')
            self.assertFalse(receipt['services_installed'])
            self.assertFalse(receipt['production_cutover'])
            self.assertEqual(stat.S_IMODE(base.stat().st_mode), 0o700)
            for name, data in files.items():
                self.assertEqual((base / 'app' / name).read_bytes(), data)
                self.assertEqual(stat.S_IMODE((base / 'app' / name).stat().st_mode), 0o400)

    def test_dependency_failure_preserves_partial_prefix_and_receipt(self):
        with tempfile.TemporaryDirectory(dir='/root') as d:
            root = Path(d)
            with self.assertRaisesRegex(m.Hold, 'SYNTHETIC_DEPENDENCY_FAILURE'):
                self.run_receive(root, lambda s: s.enter_context(mock.patch.object(m, 'process', side_effect=m.Hold('SYNTHETIC_DEPENDENCY_FAILURE'))))
            self.assertTrue((root / 'new-prefix/app').is_dir())
            self.assertTrue((root / 'new-attempt/failure.json').is_file())
            self.assertFalse((root / 'new-attempt/receipt.json').exists())

    def test_shared_state_drift_is_hold_without_deletion_or_false_pass(self):
        with tempfile.TemporaryDirectory(dir='/root') as d:
            root = Path(d)
            with self.assertRaisesRegex(m.Hold, 'PROTECTED_STATE_CHANGED'):
                self.run_receive(root, lambda s: s.enter_context(mock.patch.object(m, 'protected_snapshot', side_effect=[{'pid': 1}, {'pid': 2}])))
            self.assertTrue((root / 'new-prefix/app').is_dir())
            self.assertTrue((root / 'new-attempt/failure.json').is_file())
            self.assertFalse((root / 'new-attempt/receipt.json').exists())

    def test_existing_target_refused_and_original_kept(self):
        with tempfile.TemporaryDirectory(dir='/root') as d:
            root = Path(d); base = root / 'new-prefix'; base.mkdir(); (base / 'original').write_bytes(b'kept')
            with self.assertRaisesRegex(m.Hold, 'EXISTING_TARGET_OR_ATTEMPT'):
                self.run_receive(root)
            self.assertEqual((base / 'original').read_bytes(), b'kept')
            self.assertFalse((root / 'new-attempt').exists())

    def test_source_stable_reader_rejects_changed_identity_and_public_mode(self):
        with tempfile.TemporaryDirectory(dir='/root') as d:
            p = Path(d) / 'x'; p.write_bytes(b'private'); p.chmod(0o600)
            self.assertEqual(m.stable(p, 100), b'private')
            p.chmod(0o644)
            with self.assertRaisesRegex(m.Hold, 'FILE_NOT_PRIVATE'):
                m.stable(p, 100)


if __name__ == '__main__':
    unittest.main()
