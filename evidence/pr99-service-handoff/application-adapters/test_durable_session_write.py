import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import durable_session_write as d
from credential_key_binding import CredentialBindingHold


class DurableSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'session.json'
        self.payload = {'status': 'USED', 'used_forms': {'synthetic': 'VALID'}}
        self.digest = hashlib.sha256(d.encoded(self.payload)).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_durable_save_and_query(self):
        self.assertEqual(d.save_session(self.path, self.payload, lambda: True), self.digest)
        self.assertEqual(d.query_session(self.path, self.digest, lambda: True), 'DURABLE_MATCH')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_unknown_does_not_create_file(self):
        self.assertEqual(d.query_session(self.path, self.digest, lambda: True), 'UNKNOWN_QUERY_ONLY')
        self.assertFalse(self.path.exists())

    def test_lost_ack_queries_without_replacement(self):
        original = d.os.fsync
        calls = []
        def fail_once(fd):
            calls.append(fd)
            if len(calls) == 2:
                raise OSError('synthetic directory fsync failure')
            return original(fd)
        with patch.object(d.os, 'fsync', fail_once):
            with self.assertRaises(CredentialBindingHold):
                d.save_session(self.path, self.payload, lambda: True)
        with patch.object(d.os, 'replace', side_effect=AssertionError('must query only')):
            self.assertEqual(d.query_session(self.path, self.digest, lambda: True), 'DURABLE_MATCH')

    def test_lock_loss_blocks_replacement(self):
        held = iter([True, False])
        with self.assertRaises(CredentialBindingHold):
            d.save_session(self.path, self.payload, lambda: next(held))
        self.assertFalse(self.path.exists())

    def test_symlink_query_rejected(self):
        target = Path(self.temp.name) / 'other'
        target.write_bytes(b'private-fixture')
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            d.query_session(self.path, self.digest, lambda: True)
