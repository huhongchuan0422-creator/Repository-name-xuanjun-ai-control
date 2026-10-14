import json
import os
import socket
import struct
import unittest
from unittest import mock

from ledger_read_projection import BINDING_KEYS
from ledger_read_transport import AuthenticatedLedgerReadTransport, PinnedPeerCredentials


class Connection(object):
    def __init__(self, raw, creds=(100, 200, 300), fragment=65536):
        self.raw, self.creds, self.fragment = raw, creds, fragment
        self.sent, self.closed = b'', False
        self.actions = []
    def settimeout(self, value): self.actions.append(('timeout', value))
    def connect(self, value): self.actions.append(('connect', value))
    def getsockopt(self, *args):
        self.actions.append(('credentials', self.creds))
        return struct.pack('3i', *self.creds)
    def sendall(self, value):
        self.actions.append(('send', value))
        self.sent += value
    def recv(self, maximum):
        count = min(maximum, self.fragment)
        value, self.raw = self.raw[:count], self.raw[count:]
        return value
    def close(self): self.closed = True


class FakeClock(object):
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class TransportFixtureTests(unittest.TestCase):
    def setUp(self):
        self.request = {'ledger_uuid': 'u', 'generation': 1, 'epoch': 8,
            'instance': 'i', 'operation': 'DASHBOARD_SNAPSHOT', 'payload': {'limit': 1}}
        self.response = {key: self.request[key] for key in BINDING_KEYS}
        self.response.update(accepted=True, operation='DASHBOARD_SNAPSHOT', result={'tasks': []})
        self.pin = PinnedPeerCredentials(100, 200, 300)
    def invoke(self, raw, verifier=None, creds=(100, 200, 300), fragment=65536):
        connection = Connection(raw, creds=creds, fragment=fragment)
        with mock.patch.object(socket, 'socket', return_value=connection):
            result = AuthenticatedLedgerReadTransport(verifier or self.pin)('/run/test.sock', self.request)
        return result, connection
    def test_valid_fragmented_response(self):
        result, connection = self.invoke((json.dumps(self.response) + '\n').encode(), fragment=1)
        self.assertEqual(result, self.response)
        self.assertEqual(json.loads(connection.sent.decode()), self.request)
        self.assertTrue(connection.closed)
        self.assertEqual([a[0] for a in connection.actions if a[0] != 'timeout'],
                         ['connect', 'credentials', 'send', 'credentials'])
        timeouts = [a[1] for a in connection.actions if a[0] == 'timeout']
        self.assertTrue(all(0 < value <= 5 for value in timeouts))
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
    def test_wrong_pid_uid_gid_fail_before_send(self):
        for creds in ((101, 200, 300), (100, 201, 300), (100, 200, 301), (0, 200, 300)):
            connection = Connection(b'', creds=creds)
            with mock.patch.object(socket, 'socket', return_value=connection):
                with self.assertRaises(PermissionError):
                    AuthenticatedLedgerReadTransport(self.pin)('/run/test.sock', self.request)
            self.assertTrue(connection.closed)
            self.assertEqual(connection.sent, b'')
    def test_verifier_must_return_exact_true(self):
        for value in (False, None, 1, {}, 'yes'):
            connection = Connection(b'')
            with mock.patch.object(socket, 'socket', return_value=connection):
                with self.assertRaises(PermissionError):
                    AuthenticatedLedgerReadTransport(lambda *args: value)('/run/test.sock', self.request)
            self.assertEqual(connection.sent, b'')
            self.assertTrue(connection.closed)
    def test_verifier_exception_fails_before_send(self):
        connection = Connection(b'')
        with mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(OSError):
                AuthenticatedLedgerReadTransport(mock.Mock(side_effect=OSError('verification unavailable')))(
                    '/run/test.sock', self.request)
        self.assertEqual(connection.sent, b'')
        self.assertTrue(connection.closed)
    def test_oversized_truncated_duplicate_and_multiple_response_frames(self):
        for raw in (b'x' * 1048576, b'{}', b'', b'{}\n{}\n',
                    b'{"accepted":true,"accepted":false}\n',
                    b'{"value":NaN}\n', b'{"value":1e999}\n',
                    b'{"prototype":{}}\n', b'\xff\n'):
            with self.subTest(prefix=raw[:40]):
                with self.assertRaises(ValueError): self.invoke(raw)
    def test_second_frame_in_a_later_chunk_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'MULTIPLE_RESPONSES'):
            self.invoke(b'{}\n{}\n', fragment=3)

    def test_peer_must_close_after_one_frame_within_existing_deadline(self):
        connection = Connection(b'{}\n')
        original = connection.recv
        def recv(maximum):
            if not connection.raw: raise socket.timeout('peer did not close')
            return original(maximum)
        connection.recv = recv
        with mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin)('/run/test.sock', self.request)
        self.assertTrue(connection.closed)

    def test_large_request_fails_before_connect(self):
        request = dict(self.request, instance='i' * 8192)
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('socket creation')):
            with self.assertRaises(ValueError):
                AuthenticatedLedgerReadTransport(self.pin)('/run/test.sock', request)
    def test_invalid_paths_fail_before_connect(self):
        for path in ('relative.sock', '/run/../tmp/socket', '/run/x\x00y'):
            with mock.patch.object(socket, 'socket', side_effect=AssertionError('socket creation')):
                with self.assertRaises(ValueError):
                    AuthenticatedLedgerReadTransport(self.pin)(path, self.request)
    def test_invalid_timeout_fails_closed(self):
        for timeout in (True, 0, -1, 31, float('nan'), float('inf'), '1'):
            with self.assertRaises(ValueError): AuthenticatedLedgerReadTransport(self.pin, timeout=timeout)
    def test_receive_timeout_propagates_and_closes(self):
        connection = Connection(b'')
        connection.recv = mock.Mock(side_effect=socket.timeout('expired'))
        with mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin)('/run/test.sock', self.request)
        self.assertTrue(connection.closed)
    def test_socket_error_propagates_and_closes(self):
        connection = Connection(b'')
        connection.connect = mock.Mock(side_effect=OSError('offline'))
        with mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(OSError):
                AuthenticatedLedgerReadTransport(self.pin)('/run/test.sock', self.request)
        self.assertTrue(connection.closed)
        self.assertEqual(connection.sent, b'')


    def test_slow_trickle_cannot_refresh_total_deadline(self):
        clock = FakeClock()
        connection = Connection(b'{}\n', fragment=1)
        recv = connection.recv
        calls = []
        def trickle(maximum):
            calls.append(maximum)
            clock.advance(0.9)
            return recv(maximum)
        connection.recv = trickle
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin, timeout=2)('/run/test.sock', self.request)
        self.assertEqual(len(calls), 3)
        timeouts = [a[1] for a in connection.actions if a[0] == 'timeout']
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
        self.assertAlmostEqual(timeouts[-1], 0.2)
        self.assertTrue(connection.closed)

    def test_connect_credentials_verifier_send_and_read_share_one_budget(self):
        clock = FakeClock()
        connection = Connection((json.dumps(self.response) + '\n').encode())
        for method, delay in (('connect', 0.4), ('getsockopt', 0.3), ('sendall', 0.1), ('recv', 0.2)):
            function = getattr(connection, method)
            def delayed(*args, function=function, delay=delay):
                clock.advance(delay)
                return function(*args)
            setattr(connection, method, delayed)
        def verify(*args):
            clock.advance(0.2)
            return self.pin(*args)
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', return_value=connection):
            result = AuthenticatedLedgerReadTransport(verify, timeout=2)('/run/test.sock', self.request)
        self.assertEqual(result, self.response)
        timeouts = [a[1] for a in connection.actions if a[0] == 'timeout']
        self.assertEqual(len(timeouts), 6)
        for observed, expected in zip(timeouts, (2, 1.6, 1.1, 1.0, 0.8, 0.6)):
            self.assertAlmostEqual(observed, expected)

    def test_connect_expiry_prevents_credentials_and_send(self):
        clock = FakeClock(); connection = Connection(b'{}\n')
        connection.connect = lambda path: clock.advance(2)
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin, timeout=2)('/run/test.sock', self.request)
        self.assertFalse(any(a[0] == 'credentials' for a in connection.actions))
        self.assertEqual(connection.sent, b'')
        self.assertTrue(connection.closed)

    def test_credentials_expiry_prevents_verification_and_send(self):
        clock = FakeClock(); connection = Connection(b'{}\n')
        def credentials(*args):
            clock.advance(2)
            return struct.pack('3i', 100, 200, 300)
        connection.getsockopt = credentials
        verify = mock.Mock(return_value=True)
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(verify, timeout=2)('/run/test.sock', self.request)
        verify.assert_not_called()
        self.assertEqual(connection.sent, b'')
        self.assertTrue(connection.closed)

    def test_verifier_elapsed_time_prevents_send_after_expiry(self):
        clock = FakeClock(); connection = Connection(b'{}\n')
        def verify(*args):
            clock.advance(2)
            return True
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(verify, timeout=2)('/run/test.sock', self.request)
        self.assertEqual(connection.sent, b'')
        self.assertTrue(connection.closed)

    def test_send_expiry_prevents_receive(self):
        clock = FakeClock(); connection = Connection(b'{}\n')
        connection.sendall = lambda raw: clock.advance(2)
        connection.recv = mock.Mock(side_effect=AssertionError('recv after expiry'))
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin, timeout=2)('/run/test.sock', self.request)
        connection.recv.assert_not_called()
        self.assertTrue(connection.closed)

    def test_response_parse_expiry_rejects_late_result(self):
        clock = FakeClock(); connection = Connection(b'{}\n')
        def parse(raw):
            clock.advance(2)
            return self.response
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch('ledger_read_transport._strict_json', side_effect=parse), \
                mock.patch.object(socket, 'socket', return_value=connection):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin, timeout=2)('/run/test.sock', self.request)
        self.assertTrue(connection.closed)

    def test_expiry_before_connect_does_not_send_request(self):
        clock = FakeClock(); connection = Connection(b'{}\n')
        def socket_factory(*args):
            clock.advance(2)
            return connection
        with mock.patch('ledger_read_transport.time.monotonic', clock), \
                mock.patch.object(socket, 'socket', side_effect=socket_factory):
            with self.assertRaises(socket.timeout):
                AuthenticatedLedgerReadTransport(self.pin, timeout=2)('/run/test.sock', self.request)
        self.assertEqual(connection.actions, [])
        self.assertEqual(connection.sent, b'')
        self.assertTrue(connection.closed)


if __name__ == '__main__': unittest.main()
