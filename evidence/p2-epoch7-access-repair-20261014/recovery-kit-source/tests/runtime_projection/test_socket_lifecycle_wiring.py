"""Actual client entrypoint wiring with fake sockets; never starts a service."""
import copy
import json
import socket
import sqlite3
import types
import unittest
from unittest import mock

import ledger_server_identity as identity
import native_ledger_bridge as native
import owner_dashboard as dashboard
import root_broker as broker
from ledger_read_projection import BINDING_KEYS
from ledger_read_transport import AuthenticatedLedgerReadTransport
from test_ledger_server_identity import fixture, Backend
from test_read_transport import Connection


class WiringTests(unittest.TestCase):
    def setUp(self):
        policy, contents = fixture()
        self.backend = Backend(policy, contents)
        self.store = mock.Mock()
        self.store.read.side_effect = lambda **kw: copy.deepcopy(self.backend.active)
        self.verifier = identity.load_server_verifier(self.store, _backend=self.backend)
        self.transports = []

    def caller(self, role):
        if role == 'native':
            self.assertIs(native.load_server_verifier, identity.load_server_verifier)
            return lambda: native.socket_call({'socket_path': identity.SOCKET_PATH,
                'server_identity_policy': identity.POLICY_PATH},
                {'operation': 'observation', 'request': {'task_id': 'task'}})
        if role == 'broker':
            self.assertIs(broker.load_server_verifier, identity.load_server_verifier)
            config = dict(dispatcher_user='dispatcher', worker_user='xj_worker',
                activation_descriptor='/unused/active', activation_epoch_journal='/unused/journal',
                activation_lock='/unused/lock', codex_bin='/opt/codex', codex_sha256='a'*64,
                task_root='/work/tasks', worker_home='/work/worker', codex_home='/work/codex',
                broker_socket='/run/broker.sock', repositories=['org/repo'])
            def account(name): return types.SimpleNamespace(pw_uid=1003 if name == 'dispatcher' else 1007)
            with mock.patch.object(broker, 'load_server_verifier', return_value=self.verifier) as load, \
                    mock.patch.object(broker, 'ActivationStore', return_value=self.store), \
                    mock.patch.object(broker.pwd, 'getpwnam', side_effect=account):
                client = broker.build(config).policy.ledger
            load.assert_called_once_with()
            self.transports.append(client.transport)
            return lambda: client.observation('task')
        self.assertIs(dashboard.load_server_verifier, identity.load_server_verifier)
        def handler(store, token, page, transport):
            self.assertIs(store, self.store)
            self.transports.append(transport)
            return object()
        with mock.patch.object(dashboard, 'load_server_verifier', return_value=self.verifier) as load, \
                mock.patch.object(dashboard, 'ActivationStore', return_value=self.store), \
                mock.patch.object(dashboard, 'read_token', return_value='fixture'), \
                mock.patch.object(dashboard, 'handler', side_effect=handler), \
                mock.patch('builtins.open', mock.mock_open(read_data=b'fixture html')), \
                mock.patch('http.server.HTTPServer'):
            dashboard.main(argv=['--activation-descriptor', '/unused/active',
                '--activation-epoch-journal', '/unused/journal', '--activation-lock',
                '/unused/lock', '--token-file', '/unused/token'])
        load.assert_called_once_with()
        return lambda: dashboard.active_snapshot(self.store, transport=self.transports[-1])

    def exchange(self, role, initially_idle=False, after_send=None):
        if initially_idle:
            self.backend.units[identity.SOCKET_UNIT]['SubState'] = 'listening'
            self.backend.units[identity.SERVICE_UNIT].update(ActiveState='inactive',
                SubState='dead', MainPID='0', InvocationID='')
        invoke = self.caller(role)
        for transport in self.transports:
            self.assertIsInstance(transport, AuthenticatedLedgerReadTransport)
            self.assertIs(transport.server_verifier, self.verifier)
        response = {'accepted': True, 'result': {'measured': True}}
        if role != 'native':
            response.update({key: self.backend.active[key] for key in BINDING_KEYS})
            response['operation'] = 'BROKER_OBSERVATION' if role == 'broker' else 'DASHBOARD_SNAPSHOT'
        connection = Connection((json.dumps(response) + '\n').encode(), creds=(1, 0, 0))
        send = connection.sendall
        def sendall(raw):
            send(raw)
            if initially_idle:
                self.backend.units[identity.SOCKET_UNIT]['SubState'] = 'running'
                self.backend.units[identity.SERVICE_UNIT].update(ActiveState='active',
                    SubState='running', MainPID='80', InvocationID='e'*32)
            if after_send is not None: after_send(self.backend)
        connection.sendall = sendall
        with mock.patch.object(socket, 'socket', return_value=connection) as create, \
                mock.patch.object(native, 'load_server_verifier', return_value=self.verifier) as native_load, \
                mock.patch.object(sqlite3, 'connect', side_effect=AssertionError('client DB access')):
            if after_send is None:
                self.assertEqual(invoke(), {'measured': True})
            else:
                with self.assertRaises(ValueError): invoke()
            create.assert_called_once_with(socket.AF_UNIX, socket.SOCK_STREAM)
            if role == 'native': native_load.assert_called_once_with()
        self.assertTrue(connection.closed)
        self.assertEqual(len([row for row in connection.actions if row[0] == 'connect']), 1)
        self.assertEqual(len([row for row in connection.actions if row[0] == 'send']), 1)
        self.assertTrue(connection.sent)
        self.assertEqual(len([row for row in self.backend.calls if row[0] == 'unit']), 6)

    def test_all_entrypoints_use_running_session_and_idle_activation(self):
        for role in ('broker', 'dashboard', 'native'):
            for idle in (False, True):
                with self.subTest(role=role, idle=idle):
                    self.setUp(); self.exchange(role, initially_idle=idle)

    def test_post_send_restart_result_remains_unknown_without_reconnect_or_retry(self):
        for role in ('broker', 'dashboard', 'native'):
            with self.subTest(role=role):
                self.setUp()
                self.exchange(role, after_send=lambda b: b.units[identity.SERVICE_UNIT].update(
                    MainPID='81', InvocationID='f'*32))

    def test_native_recreated_listener_does_not_turn_unknown_into_success(self):
        def recreate(backend):
            backend.units[identity.SOCKET_UNIT]['SubState'] = 'listening'
            backend.units[identity.SERVICE_UNIT].update(ActiveState='inactive',
                SubState='dead', MainPID='0', InvocationID='')
        self.exchange('native', after_send=recreate)


if __name__ == '__main__': unittest.main()
