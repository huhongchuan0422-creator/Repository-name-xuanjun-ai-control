"""R1: finite Accept=no lifecycle, with saved UK dynamic-property inputs only.

The fixture replays already-published observations; it is not a fresh UK test.
Policy/endpoint/peer inputs remain independent synthetic exact-pin fixtures.
"""
import copy
import json
import os
import unittest
from unittest import mock

import ledger_server_identity as identity
from ledger_read_transport import MonotonicIODeadline
from test_ledger_server_identity import Backend, fixture


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.p, contents = fixture()
        self.b = Backend(self.p, contents)
        self.store = mock.Mock()
        self.store.read.side_effect = lambda **kw: copy.deepcopy(self.b.active)
        self.verifier = identity.load_server_verifier(self.store, _backend=self.b)

    def session(self):
        return self.verifier.session(identity.SOCKET_PATH, MonotonicIODeadline(5))

    def idle(self):
        self.b.units[identity.SOCKET_UNIT].update(ActiveState='active', SubState='listening')
        self.b.units[identity.SERVICE_UNIT].update(ActiveState='inactive', SubState='dead',
            MainPID='0', InvocationID='')

    def running(self, pid='80', invocation='e'*32):
        self.b.units[identity.SOCKET_UNIT].update(ActiveState='active', SubState='running')
        self.b.units[identity.SERVICE_UNIT].update(ActiveState='active', SubState='running',
            MainPID=pid, InvocationID=invocation)

    def test_saved_case_states_replay_without_relabeling_expected_denials(self):
        path = os.path.join(os.path.dirname(__file__), 'saved_socket_states.json')
        with open(path) as stream: saved = json.load(stream)
        self.assertEqual(len(saved['cases']), 8)
        for row in saved['cases']:
            with self.subTest(case=row['case']):
                self.b.units[identity.SOCKET_UNIT].update(row['units']['socket'])
                self.b.units[identity.SERVICE_UNIT].update(row['units']['service'])
                session = self.session()
                self.assertIs(session.verify((1, 0, 0)), True)
                if row['case'] == 8:
                    with self.assertRaisesRegex(ValueError, 'SERVICE_NOT_ACTIVE'):
                        session.finish((1, 0, 0))
                else:
                    self.assertIs(session.finish((1, 0, 0)), True)
        # Case 6's original refusal was a separate connected identity mutation;
        # replaying its initial active properties does not relabel that outcome.

    def test_same_request_idle_listening_to_running_activation(self):
        self.idle(); session = self.session()
        self.assertIs(session.verify((1, 0, 0)), True)
        self.running()
        self.assertIs(session.finish((1, 0, 0)), True)

    def test_activation_before_verify_binds_first_running_invocation(self):
        self.idle(); session = self.session(); self.running()
        self.assertIs(session.verify((1, 0, 0)), True)
        self.assertIs(session.finish((1, 0, 0)), True)

    def test_restart_after_activation_before_verify_is_not_unbound(self):
        self.idle(); session = self.session(); self.running()
        session.verify((1, 0, 0)); self.running(pid='81', invocation='f'*32)
        with self.assertRaisesRegex(ValueError, 'SERVICE_RESTART'):
            session.finish((1, 0, 0))

    def test_pid_or_invocation_restart_rejected_before_send_and_after_response(self):
        for when in ('verify', 'finish'):
            for field, value in (('MainPID', '81'), ('InvocationID', 'f'*32)):
                with self.subTest(when=when, field=field):
                    self.running(); session = self.session()
                    if when == 'finish': session.verify((1, 0, 0))
                    self.b.units[identity.SERVICE_UNIT][field] = value
                    with self.assertRaisesRegex(ValueError, 'SERVICE_RESTART'):
                        getattr(session, when)((1, 0, 0))

    def test_only_exact_paired_states_are_accepted_at_every_checkpoint(self):
        mutations = [
            (identity.SOCKET_UNIT, 'ActiveState', 'inactive'),
            (identity.SOCKET_UNIT, 'ActiveState', 'failed'),
            (identity.SOCKET_UNIT, 'SubState', 'listening'),
            (identity.SOCKET_UNIT, 'SubState', 'dead'),
            (identity.SOCKET_UNIT, 'SubState', 'unknown'),
            (identity.SERVICE_UNIT, 'ActiveState', 'inactive'),
            (identity.SERVICE_UNIT, 'ActiveState', 'failed'),
            (identity.SERVICE_UNIT, 'ActiveState', 'activating'),
            (identity.SERVICE_UNIT, 'SubState', 'exited'),
            (identity.SERVICE_UNIT, 'SubState', 'start'),
            (identity.SERVICE_UNIT, 'MainPID', '0'),
            (identity.SERVICE_UNIT, 'MainPID', '-1'),
            (identity.SERVICE_UNIT, 'MainPID', '\u0661'),
            (identity.SERVICE_UNIT, 'InvocationID', ''),
            (identity.SERVICE_UNIT, 'InvocationID', 'g'*32)]
        for when in ('session', 'verify', 'finish'):
            for unit, field, value in mutations:
                with self.subTest(when=when, unit=unit, field=field, value=value):
                    self.running()
                    session = None if when == 'session' else self.session()
                    if when == 'finish': session.verify((1, 0, 0))
                    self.b.units[unit][field] = value
                    with self.assertRaises(ValueError):
                        if when == 'session': self.session()
                        else: getattr(session, when)((1, 0, 0))

    def test_idle_requires_zero_pid_and_well_formed_prior_invocation(self):
        for field, value in (('MainPID', '80'), ('InvocationID', 'invalid')):
            self.idle(); self.b.units[identity.SERVICE_UNIT][field] = value
            with self.assertRaises(ValueError): self.session()
        self.idle(); self.b.units[identity.SOCKET_UNIT]['SubState'] = 'running'
        with self.assertRaisesRegex(ValueError, 'SOCKET_SERVICE_STATE'): self.session()

    def test_observed_running_cannot_return_to_idle(self):
        session = self.session(); self.idle()
        with self.assertRaisesRegex(ValueError, 'SERVICE_RESTART'): session.verify((1, 0, 0))
        self.running(); session = self.session(); session.verify((1, 0, 0)); self.idle()
        with self.assertRaisesRegex(ValueError, 'SERVICE_NOT_ACTIVE'): session.finish((1, 0, 0))

    def test_idle_invocation_change_is_not_ignored(self):
        self.idle(); session = self.session()
        self.b.units[identity.SERVICE_UNIT]['InvocationID'] = 'a'*32
        with self.assertRaisesRegex(ValueError, 'SERVICE_RESTART'): session.verify((1, 0, 0))

    def test_loaded_association_remains_exact_at_connect_and_response(self):
        for when in ('verify', 'finish'):
            for unit, field in ((identity.SOCKET_UNIT, 'Triggers'),
                                (identity.SERVICE_UNIT, 'TriggeredBy')):
                with self.subTest(when=when, unit=unit):
                    old = self.b.units[unit][field]
                    session = self.session()
                    if when == 'finish': session.verify((1, 0, 0))
                    self.b.units[unit][field] = 'other.unit'
                    with self.assertRaisesRegex(ValueError, 'LOADED_UNIT_CHANGED'):
                        getattr(session, when)((1, 0, 0))
                    self.b.units[unit][field] = old

    def test_activation_does_not_excuse_endpoint_or_activation_replacement(self):
        for mutation in ('inode', 'acl', 'activation'):
            self.setUp(); self.idle(); session = self.session(); session.verify((1, 0, 0))
            self.running()
            if mutation == 'inode': self.b.endpoint_value['inode'] += 1
            elif mutation == 'acl': self.b.endpoint_value['acl_sha256'] = 'f'*64
            else: self.b.active['epoch'] += 1
            with self.assertRaises(ValueError): session.finish((1, 0, 0))


if __name__ == '__main__': unittest.main()
