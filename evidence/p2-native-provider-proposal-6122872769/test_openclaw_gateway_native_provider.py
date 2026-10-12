import unittest

from openclaw_gateway_native_provider import (
    GatewayCapabilityUnavailable, GatewayContractError,
    OpenClawGatewayNativeProvider)


class Gateway(object):
    def __init__(self):
        self.calls = []
        self.responses = {}

    def call(self, method, params):
        self.calls.append((method, params))
        value = self.responses.get(method)
        if callable(value):
            return value(params)
        return value


class Tests(unittest.TestCase):
    def setUp(self):
        self.gateway = Gateway()
        self.methods = ['xuanjun.execution.start', 'xuanjun.execution.inspect']
        self.provider = OpenClawGatewayNativeProvider(
            self.gateway, self.methods, activation_reviewed=True)
        self.binding = {'task_id': 'task', 'executor_id': 'developer',
                        'artifact_commit': 'a' * 40, 'artifact_tree': 'b' * 40,
                        'epoch': 'epoch-1', 'fence': 4}

    def test_default_is_inert_before_any_rpc(self):
        provider = OpenClawGatewayNativeProvider(self.gateway, self.methods)
        with self.assertRaises(GatewayCapabilityUnavailable):
            provider.spawn(self.binding, 'key-1')
        self.assertEqual(self.gateway.calls, [])

    def test_missing_controller_method_fails_before_any_rpc(self):
        provider = OpenClawGatewayNativeProvider(
            self.gateway, ['xuanjun.execution.start'], activation_reviewed=True)
        with self.assertRaises(GatewayCapabilityUnavailable):
            provider.spawn(self.binding, 'key-1')
        self.assertEqual(self.gateway.calls, [])

    def test_internal_or_nonexistent_method_names_are_never_sent(self):
        for method in OpenClawGatewayNativeProvider.FORBIDDEN_GATEWAY_METHODS:
            with self.assertRaises(GatewayContractError):
                self.provider._call(method, {})
        self.assertEqual(self.gateway.calls, [])

    def test_start_uses_only_reviewed_controller_method(self):
        receipt = {'accepted': True, 'run_id': 'run-1',
                   'session_id': 'session-1'}
        self.gateway.responses['xuanjun.execution.start'] = receipt
        self.assertEqual(self.provider.spawn(self.binding, 'key-1'), receipt)
        self.assertEqual(self.gateway.calls, [
            ('xuanjun.execution.start',
             {'binding': self.binding, 'idempotency_key': 'key-1'})])

    def test_malformed_local_start_is_rejected_before_rpc(self):
        with self.assertRaises(GatewayContractError):
            self.provider.spawn(self.binding, '')
        self.assertEqual(self.gateway.calls, [])

    def test_reconcile_unknown_does_not_start_or_replay(self):
        self.gateway.responses['xuanjun.execution.inspect'] = {
            'state': 'unknown'}
        self.assertIsNone(self.provider.reconcile_spawn('key-1'))
        self.assertEqual([call[0] for call in self.gateway.calls],
                         ['xuanjun.execution.inspect'])

    def test_reconcile_returns_only_structured_original_receipt(self):
        receipt = {'accepted': True, 'run_id': 'run-1',
                   'session_id': 'session-1'}
        self.gateway.responses['xuanjun.execution.inspect'] = {
            'start_receipt': receipt}
        self.assertEqual(self.provider.reconcile_spawn('key-1'), receipt)

    def test_unbound_status_is_unknown_even_if_text_says_running(self):
        self.gateway.responses['xuanjun.execution.inspect'] = {
            'run_id': 'run-1', 'session_id': 'session-1',
            'state': 'running', 'text': 'I am active'}
        result = self.provider.status('run-1', 'session-1')
        self.assertEqual(result['state'], 'unknown')
        self.assertIsNone(result['process_alive'])

    def test_authoritative_exact_status_is_preserved(self):
        self.gateway.responses['xuanjun.execution.inspect'] = {
            'authoritative': True, 'source': 'canonical_execution_controller',
            'run_id': 'run-1', 'session_id': 'session-1',
            'state': 'running', 'process_alive': True, 'unit_active': True,
            'last_progress_at': 1010}
        result = self.provider.status('run-1', 'session-1')
        self.assertEqual(result['state'], 'running')
        self.assertTrue(result['process_alive'])

    def test_model_text_is_not_a_recovered_report(self):
        self.gateway.responses['xuanjun.execution.inspect'] = {
            'authoritative': True, 'source': 'canonical_execution_controller',
            'run_id': 'run-1', 'session_id': 'session-1',
            'state': 'completed', 'text': '{"outcome":"ok"}'}
        self.assertIsNone(self.provider.recover_report('run-1', 'session-1'))

    def test_structured_controller_report_can_be_recovered(self):
        report = {'run_id': 'run-1', 'session_id': 'session-1',
                  'outcome': 'ok'}
        self.gateway.responses['xuanjun.execution.inspect'] = {
            'authoritative': True, 'source': 'canonical_execution_controller',
            'run_id': 'run-1', 'session_id': 'session-1',
            'state': 'completed', 'process_alive': False,
            'unit_active': False, 'report': report}
        self.assertEqual(
            self.provider.recover_report('run-1', 'session-1'), report)


if __name__ == '__main__':
    unittest.main()
