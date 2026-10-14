"""Local integration only; no service, host, credentials or privilege changes."""
import errno
import hashlib
import json
import os
import socket
import sqlite3
import struct
import tempfile
import threading
import types
import unittest
from unittest import mock

import owner_dashboard
import root_broker
import uk_owner_callback_core as core
from ledger_read_client import BrokerObservationClient, dashboard_read
from ledger_read_projection import BINDING_KEYS, GATE_KEYS, project
from ledger_read_transport import AuthenticatedLedgerReadTransport, PinnedPeerCredentials

# Staged-kit adapter: disposable SQLite/socket fixtures stay outside the kit.
TEST_DIR = tempfile.gettempdir()


class FakeConnection(object):
    def __init__(self, uid, request=None, raw=None, pid=100):
        self.uid, self.pid = uid, pid
        self.raw = (json.dumps(request) + '\n').encode() if raw is None else raw
        self.sent = b''
        self.received = False
        self.timeout = None
        self.timeouts = []
    def gettimeout(self):
        return self.timeout
    def settimeout(self, value):
        self.timeout = value
        self.timeouts.append(value)
    def getsockopt(self, *args):
        return struct.pack('3i', self.pid, self.uid, self.uid)
    def recv(self, maximum):
        self.received = True
        result, self.raw = self.raw[:maximum], self.raw[maximum:]
        return result
    def sendall(self, value):
        self.sent += value


class Fixture(unittest.TestCase):
    def setUp(self):
        self.active = {'ledger_uuid': 'u', 'generation': 1, 'epoch': 8,
                       'instance': 'i', 'db_path': '/private/never-open.sqlite',
                       'ledger_socket': '/run/unused.sock'}
        self.store = mock.Mock()
        self.store.read.side_effect = lambda **kwargs: dict(self.active)
        self.ledger = mock.Mock()
        self.ledger.observation.return_value = {'task_id': 'task', 'state': 'RUNNING',
            'fence': 3, 'checkpoint': {}, 'generation': 1, 'epoch': 8, 'instance': 'i'}
        self.callback_uid = 1004
        self.owner_verifier = mock.Mock(return_value=True)
        self.server = core.LedgerOwnerDecisionServer(self.store, self.ledger, self.callback_uid,
            owner_process_verifier=self.owner_verifier)
    def request(self, operation='BROKER_OBSERVATION', payload=None):
        value = {key: self.active[key] for key in BINDING_KEYS}
        value.update(operation=operation, payload={'task_id': 'task'} if payload is None else payload)
        return value
    def owner_request(self):
        value = {key: self.active[key] for key in BINDING_KEYS}
        value.update(operation='OWNER_DECISION', event={
            'request_id': 'request', 'task_id': 'task', 'fence': 3,
            'owner_user_id': 'owner', 'owner_chat_id': 'chat',
            'update_id': 1, 'decision': 'APPROVE'})
        return value


class ServerRoutingTests(Fixture):
    def test_broker_observation_only(self):
        connection = FakeConnection(0, self.request())
        self.server.serve_connection(connection)
        response = json.loads(connection.sent.decode())
        self.assertEqual(response['result'], self.ledger.observation.return_value)
        self.assertEqual(set(response), set(BINDING_KEYS + ('accepted', 'operation', 'result')))
        self.assertEqual(self.ledger.method_calls, [mock.call.observation('task')])

    def test_callback_dashboard_uses_only_server_selected_database(self):
        connection = FakeConnection(self.callback_uid, self.request('DASHBOARD_SNAPSHOT', {'limit': 2}))
        with mock.patch.object(owner_dashboard, 'snapshot', return_value={'tasks': []}) as snapshot:
            self.server.serve_connection(connection)
            snapshot.assert_called_once_with(self.active['db_path'], limit=2,
                activation={key: self.active[key] for key in BINDING_KEYS})
        self.assertEqual(self.ledger.method_calls, [])

    def test_wrong_uid_rejected_before_request(self):
        connection = FakeConnection(2000, self.request())
        with self.assertRaises(PermissionError): self.server.serve_connection(connection)
        self.assertFalse(connection.received)
        self.assertEqual(self.ledger.method_calls, [])

    def test_cross_role_and_root_mutations_rejected(self):
        for uid, request in ((self.callback_uid, self.request()),
                (0, self.request('DASHBOARD_SNAPSHOT', {'limit': 1})),
                (0, self.owner_request()),
                (0, {'operation': 'NATIVE_GATEWAY', 'payload': {'operation': 'cas'}})):
            with self.subTest(uid=uid, request=request):
                connection = FakeConnection(uid, request)
                with self.assertRaises(PermissionError): self.server.serve_connection(connection)
                self.assertEqual(connection.sent, b'')
        self.assertEqual(self.ledger.method_calls, [])

    def test_unknown_operation_rejected(self):
        for uid in (0, self.callback_uid):
            with self.assertRaises((ValueError, PermissionError)):
                self.server.serve_connection(FakeConnection(uid, self.request('SQL', {})))
        self.assertEqual(self.ledger.method_calls, [])

    def test_no_path_or_sql_parameters(self):
        for payload in ({'limit': 1, 'db_path': '/other'}, {'sql': 'SELECT 1'},
                        {'limit': 1, 'now': 0}):
            with self.assertRaises(ValueError):
                self.server.serve_connection(FakeConnection(self.callback_uid,
                    self.request('DASHBOARD_SNAPSHOT', payload)))
        self.assertEqual(self.ledger.method_calls, [])

    def test_stale_and_type_confused_activation(self):
        for key, value in (('epoch', 7), ('generation', True), ('instance', 3), ('ledger_uuid', 'other')):
            request = self.request(); request[key] = value
            with self.assertRaises(PermissionError):
                self.server.serve_connection(FakeConnection(0, request))
        self.assertEqual(self.ledger.method_calls, [])

    def test_post_read_all_activation_gates_fail_closed(self):
        for key in GATE_KEYS:
            with self.subTest(key=key):
                before = dict(self.active)
                after = dict(before)
                after[key] = before[key] + 1 if type(before[key]) is int else before[key] + '-other'
                self.store.read.side_effect = [before, after]
                connection = FakeConnection(0, self.request())
                with self.assertRaises(RuntimeError): self.server.serve_connection(connection)
                self.assertEqual(connection.sent, b'')

    def test_post_read_boolean_binding_is_rejected(self):
        self.store.read.side_effect = [dict(self.active), dict(self.active, generation=True)]
        with self.assertRaises(RuntimeError): self.server.serve_connection(FakeConnection(0, self.request()))

    def test_oversized_duplicate_and_multiple_frames_rejected(self):
        frames = [b'x' * 8192, b'{"operation":"a","operation":"b"}\n',
                  b'{"value":NaN}\n', b'{"value":1e999}\n', b'{}\n{}\n', b'{}']
        for raw in frames:
            with self.subTest(raw=raw[:40]):
                connection = FakeConnection(0, raw=raw)
                with self.assertRaises(ValueError): self.server.serve_connection(connection)
                self.assertEqual(connection.sent, b'')
        self.assertEqual(self.ledger.method_calls, [])

    def test_oversized_response_not_sent(self):
        self.ledger.observation.return_value = {'oversized': 'x' * 1048576}
        connection = FakeConnection(0, self.request())
        with self.assertRaises(ValueError): self.server.serve_connection(connection)
        self.assertEqual(connection.sent, b'')

    def test_real_sqlite_server_projection_is_readonly_and_sanitized(self):
        with tempfile.TemporaryDirectory(prefix='db-tests-', dir=TEST_DIR) as directory:
            path = os.path.join(directory, 'fixture.sqlite')
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE tasks(id TEXT,state TEXT,fence INTEGER,updated REAL,depends TEXT,checkpoint TEXT)')
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?)',
                ('task', 'PENDING', 1, 1.0, '[]', '{"phase":"READY","prompt":"omit-me"}'))
            db.commit(); db.close()
            self.active['db_path'] = path
            with open(path, 'rb') as stream: before = hashlib.sha256(stream.read()).hexdigest()
            connection = FakeConnection(self.callback_uid,
                self.request('DASHBOARD_SNAPSHOT', {'limit': 1}))
            original_connect = sqlite3.connect
            modes = []
            def connect(*args, **kwargs):
                modes.append(args[0])
                self.assertIn('?mode=ro', args[0])
                return original_connect(*args, **kwargs)
            with mock.patch.object(sqlite3, 'connect', side_effect=connect):
                self.server.serve_connection(connection)
            result = json.loads(connection.sent.decode())['result']
            self.assertEqual(len(modes), 1)
            self.assertEqual(result['source'], 'CANONICAL_LEDGER_READ_ONLY')
            self.assertEqual(result['tasks'][0]['checkpoint'], {'phase': 'READY'})
            self.assertNotIn('omit-me', json.dumps(result))
            with open(path, 'rb') as stream:
                self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), before)
            self.assertEqual(os.listdir(directory), ['fixture.sqlite'])

    def test_slow_root_callback_and_owner_frames_expire_before_actions(self):
        for uid, request in ((0, self.request()),
                (self.callback_uid, self.request('DASHBOARD_SNAPSHOT', {'limit': 1})),
                (self.callback_uid, self.owner_request())):
            now = [100.0]
            connection = FakeConnection(uid, request)
            connection.timeout = 0.75
            recv = connection.recv
            calls = []
            def trickle(maximum):
                calls.append(maximum)
                now[0] += 2
                return recv(1)
            connection.recv = trickle
            with mock.patch('ledger_read_transport.time.monotonic', lambda: now[0]):
                with self.assertRaises(socket.timeout): self.server.serve_connection(connection)
            self.assertEqual(len(calls), 3)
            self.assertEqual(connection.timeouts, [5.0, 3.0, 1.0, 0.75])
            self.assertEqual(connection.gettimeout(), 0.75)
            self.assertEqual(connection.sent, b'')
        self.store.read.assert_not_called()
        self.assertEqual(self.ledger.method_calls, [])

    def test_slow_read_provider_cannot_send_after_deadline(self):
        now = [100.0]
        connection = FakeConnection(self.callback_uid,
            self.request('DASHBOARD_SNAPSHOT', {'limit': 1}))
        def snapshot(*args, **kwargs):
            now[0] += 5
            return {'tasks': []}
        with mock.patch('ledger_read_transport.time.monotonic', lambda: now[0]), \
                mock.patch.object(owner_dashboard, 'snapshot', side_effect=snapshot):
            with self.assertRaises(socket.timeout): self.server.serve_connection(connection)
        self.assertEqual(connection.sent, b'')
        self.assertEqual(self.ledger.method_calls, [])

    def test_owner_frame_restores_original_socket_timeout(self):
        self.ledger.owner_decision.return_value = {
            'accepted': True, 'state': 'PENDING', 'task_id': 'task', 'fence': 3}
        connection = FakeConnection(self.callback_uid, self.owner_request())
        connection.timeout = 0.75
        self.server.serve_connection(connection)
        self.assertEqual(connection.gettimeout(), 0.75)
        self.assertIs(json.loads(connection.sent.decode())['accepted'], True)

    def test_native_branch_does_not_change_timeout_or_deadline_behavior(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger,
            self.callback_uid, native_identity={'uid': 1002})
        connection = FakeConnection(1002,
            {'operation': 'NATIVE_GATEWAY', 'payload': {'operation': 'read'}})
        with mock.patch('ledger_read_transport.time.monotonic', side_effect=AssertionError('new native deadline')), \
                mock.patch.object(core, 'verify_native_gateway_peer', return_value=True), \
                mock.patch('native_ledger_operations.execute', return_value={}):
            server.serve_connection(connection)
        self.assertEqual(connection.timeouts, [])
        self.assertIs(json.loads(connection.sent.decode())['accepted'], True)

    def test_owner_original_authorization_and_response_preserved(self):
        self.ledger.owner_decision.return_value = {
            'accepted': True, 'state': 'PENDING', 'task_id': 'task', 'fence': 3}
        connection = FakeConnection(self.callback_uid, self.owner_request())
        self.server.serve_connection(connection)
        self.ledger.owner_decision.assert_called_once_with('task', 3, 'APPROVE',
            'request', 1, 'owner', 'chat', 'owner-callback:1004', True)
        self.assertEqual(set(json.loads(connection.sent.decode())), core.RESPONSE_KEYS)
        self.ledger.observation.assert_not_called()

    def test_native_process_verifier_cannot_be_bypassed_for_reads(self):
        identity = {'uid': 1002}
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger,
                                              self.callback_uid, native_identity=identity)
        connection = FakeConnection(1002, self.request())
        with mock.patch.object(core, 'verify_native_gateway_peer', return_value=False) as verify:
            with self.assertRaises(PermissionError): server.serve_connection(connection)
            verify.assert_called_once_with(100, 1002, identity)
        self.assertFalse(connection.received)
        with mock.patch.object(core, 'verify_native_gateway_peer', return_value=True):
            with self.assertRaises(PermissionError): server.serve_connection(FakeConnection(1002, self.request()))
        self.assertEqual(self.ledger.method_calls, [])

    def test_native_original_verified_operation_preserved(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger,
                                               self.callback_uid, native_identity={'uid': 1002})
        connection = FakeConnection(1002, {'operation': 'NATIVE_GATEWAY', 'payload': {'operation': 'read'}})
        with mock.patch.object(core, 'verify_native_gateway_peer', return_value=True), \
                mock.patch('native_ledger_operations.execute', return_value={'native': True}) as execute:
            server.serve_connection(connection)
            execute.assert_called_once_with(self.ledger, {'operation': 'read'})
        self.assertEqual(json.loads(connection.sent.decode()), {'accepted': True, 'result': {'native': True}})


class ClientIntegrationTests(Fixture):
    def response(self, request):
        response = {key: self.active[key] for key in BINDING_KEYS}
        response.update(accepted=True, operation=request['operation'], result={'tasks': []})
        return response

    def test_dashboard_active_snapshot_never_accesses_database(self):
        def transport(path, request):
            self.assertEqual(path, self.active['ledger_socket'])
            self.assertEqual(request['operation'], 'DASHBOARD_SNAPSHOT')
            self.assertNotIn('db_path', request)
            return self.response(request)
        with mock.patch.object(sqlite3, 'connect', side_effect=AssertionError('client DB open')), \
                mock.patch.object(owner_dashboard, 'snapshot', side_effect=AssertionError('client snapshot')):
            self.assertEqual(owner_dashboard.active_snapshot(self.store, limit=3, transport=transport), {'tasks': []})

    def test_dashboard_no_transport_and_client_clock_fail_closed(self):
        with self.assertRaises(ValueError): owner_dashboard.active_snapshot(self.store)
        with self.assertRaises(ValueError): owner_dashboard.active_snapshot(self.store, now=0, transport=lambda *_: {})

    def test_exact_response_contract(self):
        request = self.request('DASHBOARD_SNAPSHOT', {'limit': 1})
        base = self.response(request)
        variants = [dict(base, accepted=1), dict(base, extra=True),
            dict(base, operation='BROKER_OBSERVATION'), dict(base, generation=True),
            dict(base, epoch=7), {key: value for key, value in base.items() if key != 'instance'}]
        for response in variants:
            with self.subTest(response=response):
                with self.assertRaises(RuntimeError): dashboard_read(self.store, lambda *_: response, limit=1)

    def test_client_post_read_all_activation_gates(self):
        for key in GATE_KEYS:
            before = dict(self.active)
            after = dict(before)
            after[key] = before[key] + 1 if type(before[key]) is int else before[key] + '-other'
            self.store.read.side_effect = [before, after]
            response = self.response(self.request('DASHBOARD_SNAPSHOT', {'limit': 1}))
            with self.assertRaises(RuntimeError): dashboard_read(self.store, lambda *_: response, limit=1)

    def test_broker_build_never_constructs_writable_ledger_or_opens_database(self):
        config = dict(dispatcher_user='dispatcher', worker_user='xj_worker',
            activation_descriptor='/config/activation', activation_epoch_journal='/config/epochs',
            activation_lock='/config/lock', codex_bin='/opt/codex', codex_sha256='a' * 64,
            task_root='/work/tasks', worker_home='/work/worker', codex_home='/work/codex',
            broker_socket='/run/broker.sock', repositories=['org/repo'])
        def account(name): return types.SimpleNamespace(pw_uid=1002 if name == 'dispatcher' else 1003)
        verifier = PinnedPeerCredentials(os.getpid(), os.getuid(), os.getgid())
        with mock.patch.object(root_broker, 'ActivationStore', return_value=self.store), \
                mock.patch.object(root_broker.pwd, 'getpwnam', side_effect=account), \
                mock.patch.object(sqlite3, 'connect', side_effect=AssertionError('DB open')), \
                mock.patch('execution_ledger.ExecutionLedger.__init__', side_effect=AssertionError('writable ledger')):
            broker = root_broker.build(config, server_verifier=verifier)
        self.assertIsInstance(broker.policy.ledger, BrokerObservationClient)
        self.assertFalse(hasattr(broker.policy.ledger, 'claim'))
        self.assertFalse(hasattr(broker.policy.ledger, 'owner_decision'))
        self.assertFalse(hasattr(broker.policy.ledger, 'launch'))
        request = dict(operation='launch', task_id='task', fence=3, generation=1,
                       epoch=8, instance='i', role='DEVELOPMENT', artifact_sha=None)
        with self.assertRaises(PermissionError): broker.policy.authorize(1002, request)

    def test_service_startup_missing_verifier_fails_before_effects(self):
        with mock.patch.object(root_broker, 'ActivationStore', side_effect=AssertionError('activation opened')), \
                mock.patch.object(root_broker, 'load_server_verifier', side_effect=ValueError('missing measured policy')):
            with self.assertRaises(ValueError): root_broker.build({})
        with mock.patch.object(owner_dashboard, 'ActivationStore', side_effect=AssertionError('activation opened')), \
                mock.patch.object(owner_dashboard, 'load_server_verifier', side_effect=ValueError('missing measured policy')):
            with self.assertRaises(ValueError):
                owner_dashboard.main(argv=['--activation-descriptor', '/unused/active',
                    '--activation-epoch-journal', '/unused/journal',
                    '--activation-lock', '/unused/lock', '--token-file', '/unused/token'])

    def test_systemd_launch_remains_prohibited(self):
        run = mock.Mock()
        handler = root_broker.Systemd239Handler('/worker', '/codex', run=run)
        with self.assertRaises(RuntimeError): handler({'operation': 'launch', 'unit': 'x'})
        with self.assertRaises(RuntimeError): handler.serve_launch({}, None)
        run.assert_not_called()


class SocketProtocolTests(Fixture):
    def setUp(self):
        super(SocketProtocolTests, self).setUp()
        self.temp = tempfile.TemporaryDirectory(prefix='socket-tests-', dir=TEST_DIR)
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, 'ledger.sock')
        self.active['ledger_socket'] = self.path
        self.peer_pin = PinnedPeerCredentials(os.getpid(), os.getuid(), os.getgid())

    def launch(self, action):
        try:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except PermissionError as error:
            if error.errno in (errno.EPERM, errno.EACCES):
                self.skipTest('environment blocks AF_UNIX creation: errno=%d' % error.errno)
            raise
        listener.bind(self.path); listener.listen(1); listener.settimeout(2)
        outcome = []
        def run():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2)
                    try: action(connection)
                    except Exception as error:
                        outcome.append(error)
                        try: connection.sendall(b'{"accepted":false}\n')
                        except OSError: pass
            except Exception as error: outcome.append(error)
            finally: listener.close()
        thread = threading.Thread(target=run)
        thread.daemon = True; thread.start()
        def stop():
            thread.join(3)
            self.assertFalse(thread.is_alive(), 'test socket thread did not terminate')
        self.addCleanup(stop)
        return outcome, thread

    def test_real_socket_dashboard_authenticated_roundtrip(self):
        # This process uses its actual non-root local UID, with no impersonation.
        self.assertGreater(os.getuid(), 0)
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, os.getuid())
        with mock.patch.object(owner_dashboard, 'snapshot', return_value={'tasks': [], 'model': 'UNKNOWN'}):
            errors, thread = self.launch(server.serve_connection)
            result = owner_dashboard.active_snapshot(self.store,
                transport=AuthenticatedLedgerReadTransport(self.peer_pin))
            thread.join(3)
        self.assertEqual(result, {'tasks': [], 'model': 'UNKNOWN'})
        self.assertEqual(errors, [])
        self.assertEqual(self.ledger.method_calls, [])

    def test_real_socket_dashboard_existing_readonly_projection(self):
        # Only the server calls SQLite. The database is a local canonical test fixture.
        path = os.path.join(self.temp.name, 'fixture.sqlite')
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE tasks(id TEXT,state TEXT,fence INTEGER,updated REAL,depends TEXT,checkpoint TEXT)')
        db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?)',
                   ('task', 'PENDING', 1, 1.0, '[]', '{"phase":"READY","prompt":"omit-me"}'))
        db.commit(); db.close()
        self.active['db_path'] = path
        with open(path, 'rb') as stream: before = hashlib.sha256(stream.read()).hexdigest()
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, os.getuid())
        errors, thread = self.launch(server.serve_connection)
        original_connect = sqlite3.connect
        server_threads = []
        def connect(*args, **kwargs):
            self.assertNotEqual(threading.current_thread(), threading.main_thread())
            server_threads.append(threading.current_thread())
            self.assertIn('?mode=ro', args[0])
            return original_connect(*args, **kwargs)
        with mock.patch.object(sqlite3, 'connect', side_effect=connect):
            result = owner_dashboard.active_snapshot(self.store,
                transport=AuthenticatedLedgerReadTransport(self.peer_pin))
            thread.join(3)
        self.assertEqual(errors, [])
        self.assertEqual(len(server_threads), 1)
        self.assertEqual(result['source'], 'CANONICAL_LEDGER_READ_ONLY')
        self.assertEqual(result['tasks'][0]['checkpoint'], {'phase': 'READY'})
        self.assertNotIn('omit-me', json.dumps(result))
        with open(path, 'rb') as stream: self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), before)

    def test_real_socket_wrong_server_uid_rejected_before_transmission(self):
        received = []
        errors, thread = self.launch(lambda connection: received.append(connection.recv(8192)))
        verifier = PinnedPeerCredentials(os.getpid(), os.getuid() + 1, os.getgid())
        with self.assertRaises(PermissionError):
            dashboard_read(self.store, AuthenticatedLedgerReadTransport(verifier))
        thread.join(3)
        self.assertEqual(received, [b''])
        self.assertEqual(errors, [])

    def test_real_socket_wrong_client_uid_rejected(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, os.getuid() + 1)
        errors, thread = self.launch(server.serve_connection)
        with self.assertRaises((RuntimeError, OSError)):
            dashboard_read(self.store, AuthenticatedLedgerReadTransport(self.peer_pin))
        thread.join(3)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], PermissionError)
        self.assertEqual(self.ledger.method_calls, [])

    def test_real_socket_nonroot_cannot_read_broker_observation(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, os.getuid())
        errors, thread = self.launch(server.serve_connection)
        with self.assertRaises(RuntimeError):
            BrokerObservationClient(self.store, AuthenticatedLedgerReadTransport(self.peer_pin)).observation('task')
        thread.join(3)
        self.assertIsInstance(errors[0], PermissionError)
        self.ledger.observation.assert_not_called()

    def test_real_socket_stale_request_rejected(self):
        server = core.LedgerOwnerDecisionServer(self.store, self.ledger, os.getuid())
        request = self.request('DASHBOARD_SNAPSHOT', {'limit': 1}); request['epoch'] = 7
        errors, thread = self.launch(server.serve_connection)
        result = AuthenticatedLedgerReadTransport(self.peer_pin)(self.path, request)
        thread.join(3)
        self.assertEqual(result, {'accepted': False})
        self.assertIsInstance(errors[0], PermissionError)

    def test_real_socket_oversized_response_rejected(self):
        def action(connection):
            connection.recv(8192)
            connection.sendall(b'x' * 1048576)
        errors, thread = self.launch(action)
        with self.assertRaises(ValueError):
            dashboard_read(self.store, AuthenticatedLedgerReadTransport(self.peer_pin))
        thread.join(3)
        self.assertEqual(errors, [])

    def test_real_socket_malformed_response_rejected(self):
        def action(connection):
            connection.recv(8192)
            connection.sendall(b'{"accepted":true,"accepted":false}\n')
        errors, thread = self.launch(action)
        with self.assertRaises(ValueError):
            dashboard_read(self.store, AuthenticatedLedgerReadTransport(self.peer_pin))
        thread.join(3)
        self.assertEqual(errors, [])

    def test_transport_no_verifier_and_invalid_pins_fail_closed(self):
        for verifier in (None, False, 1, object()):
            with self.assertRaises(ValueError): AuthenticatedLedgerReadTransport(verifier)
        for args in ((0, 1, 1), (1, -1, 1), (1, 1, -1), (True, 1, 1)):
            with self.assertRaises(ValueError): PinnedPeerCredentials(*args)

    def test_transport_rejects_unknown_operations_before_connect(self):
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('connected')):
            for operation in ('OWNER_DECISION', 'NATIVE_GATEWAY', 'SQL', 'LAUNCH'):
                with self.assertRaises(PermissionError):
                    AuthenticatedLedgerReadTransport(self.peer_pin)(self.path, self.request(operation, {}))

    def test_transport_verifier_must_return_literal_true(self):
        received = []
        errors, thread = self.launch(lambda connection: received.append(connection.recv(8192)))
        with self.assertRaises(PermissionError):
            dashboard_read(self.store, AuthenticatedLedgerReadTransport(lambda *args: 1))
        thread.join(3)
        self.assertEqual(received, [b''])
        self.assertEqual(errors, [])


if __name__ == '__main__': unittest.main()
