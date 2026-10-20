import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'production/p2_install/b3_contracts.py'
spec = importlib.util.spec_from_file_location('contracts', SOURCE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class Contracts(unittest.TestCase):
    def test_read_preserves_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'receipt'; p.write_bytes(b'original')
            before = p.stat()
            for _ in range(2):
                self.assertEqual(c.pinned_file(p, hashlib.sha256(b'original').hexdigest()), b'original')
            after = p.stat()
            for key in ('st_ino', 'st_mtime_ns', 'st_mode', 'st_nlink'):
                self.assertEqual(getattr(before, key), getattr(after, key))

    def test_changed_source_hold(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'receipt'; p.write_bytes(b'changed')
            with self.assertRaisesRegex(c.Hold, 'SOURCE_SHA'):
                c.pinned_file(p, hashlib.sha256(b'original').hexdigest())

    def test_link_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p/'real').mkdir(); (p/'real'/'x').write_bytes(b'x')
            (p/'alias').symlink_to(p/'real', target_is_directory=True)
            with self.assertRaises(OSError):
                c.pinned_file(p/'alias'/'x', hashlib.sha256(b'x').hexdigest())

    def test_identity_without_fake_pid(self):
        expected = dict.fromkeys(c.IDENTITY, 'fixed')
        result = c.identity(expected, {'identity': expected, 'process':
                            {'state': 'NOT_STARTED', 'pid': None, 'peer_uid': None}})
        self.assertFalse(result['live_process_verified'])

    def test_identity_conflict(self):
        expected = dict.fromkeys(c.IDENTITY, 'fixed')
        with self.assertRaisesRegex(c.Hold, 'IDENTITY_CONFLICT'):
            c.identity(expected, {'identity': {}, 'process': {}})

    def test_fake_pid_rejected(self):
        expected = dict.fromkeys(c.IDENTITY, 'fixed')
        with self.assertRaisesRegex(c.Hold, 'B3_PROCESS_NOT_STARTED'):
            c.identity(expected, {'identity': expected, 'process': {'pid': 123}})

    def test_exact_path_scope(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{'path': d+'/'+n, 'uid': os.geteuid(), 'gid': os.getegid(),
                     'mode': 0o700, 'purpose': purpose} for n, purpose in
                    [('data', 'RESERVED_DATABASE'), ('run', 'RESERVED_SOCKET')]]
            self.assertTrue(c.path_contract(d, rows, os.geteuid(), os.getegid()))
            rows[1]['path'] = '/etc/run'
            with self.assertRaisesRegex(c.Hold, 'PATH_SCOPE'):
                c.path_contract(d, rows, os.geteuid(), os.getegid())

    def test_effective_access_is_not_denial_proof(self):
        with tempfile.TemporaryDirectory() as d:
            result = c.effective_access(d, os.geteuid(), os.getegid())
            self.assertEqual(result['unauthorized_denial'], 'NOT_EXECUTED')
            with self.assertRaisesRegex(c.Hold, 'PROBE_SUBJECT'):
                c.effective_access(d, os.geteuid()+1, os.getegid())

    def test_unknown_runtime_cannot_exempt_tls(self):
        with self.assertRaisesRegex(c.Hold, 'RUNTIME_UNAVAILABLE'):
            c.tls_applicability({'status': 'UNAVAILABLE'})

    def test_unix_only_scoped_exemption(self):
        cfg = {'status': 'BOUND', 'listeners': [{'transport': 'unix', 'address': '/x/app.sock'}],
               'outbound': [], 'tls_required': False}
        self.assertEqual(c.tls_applicability(cfg)['status'], 'NOT_APPLICABLE')
        cfg['outbound'] = [{'transport': 'tcp', 'address': 'example:443'}]
        self.assertEqual(c.tls_applicability(cfg)['status'], 'HOLD')

    def test_empty_transport_unknown(self):
        with self.assertRaisesRegex(c.Hold, 'TRANSPORT_UNKNOWN'):
            c.tls_applicability({'status': 'BOUND', 'listeners': [], 'outbound': [], 'tls_required': False})

    @unittest.skipUnless(os.geteuid() == 0, 'independent UID requires privileged local runner')
    def test_unauthorized_probe_reports_actual_capability(self):
        with tempfile.TemporaryDirectory() as d:
            result = c.unauthorized_access(d, 0, os.getegid(), 65534, 65534)
            self.assertIn(result['status'], ('PASS','UNAVAILABLE'))
            if result['status'] == 'UNAVAILABLE':
                self.assertEqual(result['reason'],'INDEPENDENT_SUBJECT_REQUIRED')


if __name__ == '__main__':
    unittest.main()
