"""Native envelope, shared authentication and fail-closed entrypoint fixtures."""
import json
import os
import socket
import subprocess
import sys
import unittest
from unittest import mock

import native_ledger_bridge as bridge
import ledger_read_transport as transport
from test_read_transport import Connection, FakeClock
from test_ledger_server_identity import fixture, Backend
from ledger_server_identity import load_server_verifier


class NativeServerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.config = {'socket_path': bridge.SOCKET_PATH, 'server_identity_policy': bridge.POLICY_PATH}
        self.payload = {'operation': 'observation', 'request': {'task_id': 't'}}
        self.pin = transport.PinnedPeerCredentials(1, 0, 0)
    def invoke(self, raw=b'{"accepted":true,"result":{"x":1}}\n', verifier=None):
        connection = Connection(raw, creds=(1, 0, 0))
        with mock.patch.object(socket, 'socket', return_value=connection):
            result = bridge.socket_call(self.config, self.payload, server_verifier=verifier or self.pin)
        return result, connection
    def test_native_wire_envelope_unchanged(self):
        result, connection = self.invoke()
        self.assertEqual(json.loads(connection.sent.decode()), {'operation': 'NATIVE_GATEWAY', 'payload': self.payload})
        self.assertEqual(result, {'x': 1}); self.assertTrue(connection.closed)
    def test_full_shared_root_manager_verifier_used_for_native(self):
        policy, contents = fixture(); backend = Backend(policy, contents)
        store = mock.Mock(); store.read.return_value = backend.active
        verifier = load_server_verifier(store, _backend=backend)
        result, connection = self.invoke(verifier=verifier)
        self.assertEqual(result, {'x': 1})
        self.assertEqual(len([c for c in backend.calls if c[0] == 'unit']), 6)
    def test_missing_policy_fails_before_socket_creation(self):
        with mock.patch.object(bridge, 'load_server_verifier', side_effect=ValueError('missing policy')), \
                mock.patch.object(socket, 'socket', side_effect=AssertionError('socket creation')):
            with self.assertRaises(ValueError): bridge.socket_call(self.config, self.payload)
    def test_legacy_uid_configuration_has_no_fallback(self):
        for config in ({'socket_path': bridge.SOCKET_PATH, 'server_uid': 1002},
                       dict(self.config, server_uid=0), dict(self.config, server_identity_policy='/tmp/pin'),
                       dict(self.config, socket_path='/tmp/socket')):
            with mock.patch.object(socket, 'socket', side_effect=AssertionError('socket creation')):
                with self.assertRaises(ValueError): bridge.socket_call(config, self.payload, self.pin)
    def test_wrong_creator_before_send_denied(self):
        connection = Connection(b'', creds=(1, 1002, 1002))
        with mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(ValueError): bridge.socket_call(self.config, self.payload, self.pin)
        self.assertEqual(connection.sent, b''); self.assertTrue(connection.closed)
    def test_post_response_gate_must_return_literal_true(self):
        for result in (False, 1, None):
            verify = mock.Mock(side_effect=[True, result])
            with self.assertRaises(ValueError): self.invoke(verifier=verify)
            self.assertEqual(verify.call_count, 2)
    def test_native_response_exact_gate_retained(self):
        for raw in (b'{"accepted":false,"result":{}}\n', b'{"accepted":1,"result":{}}\n',
                    b'{"accepted":true,"result":{},"extra":1}\n', b'[]\n',
                    b'{"accepted":true,"accepted":true,"result":{}}\n', b'{}\n{}\n'):
            with self.assertRaises(ValueError): self.invoke(raw)
    def test_native_wire_and_response_bounds_retained(self):
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('socket creation')):
            with self.assertRaises(ValueError): bridge.socket_call(self.config, {'value':'x'*1048576}, self.pin)
        with self.assertRaises(ValueError): self.invoke(b'x'*1048576)
    def test_native_slow_trickle_has_absolute_deadline(self):
        clock = FakeClock(); connection = Connection(b'{}\n', creds=(1, 0, 0), fragment=1)
        recv = connection.recv
        def trickle(maximum): clock.advance(4); return recv(maximum)
        connection.recv = trickle
        with mock.patch.object(socket, 'socket', return_value=connection), \
                mock.patch.object(transport.time, 'monotonic', clock):
            with self.assertRaises(socket.timeout): bridge.socket_call(self.config, self.payload, self.pin)
        self.assertTrue(connection.closed)
    def test_native_help_needs_no_policy_or_socket(self):
        result = subprocess.run([sys.executable, '-B', bridge.__file__, '--help'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'--config', result.stdout)
        self.assertEqual(result.stderr, b'')


if __name__ == '__main__': unittest.main()
