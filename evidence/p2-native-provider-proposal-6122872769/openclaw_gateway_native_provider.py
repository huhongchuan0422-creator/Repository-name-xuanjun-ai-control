"""Fail-closed OpenClaw Gateway provider for NativeChildAdapter.

The installed 2026.9.9 Gateway does not expose the trusted execution-controller
methods named below.  This module is therefore inert by default.  It is a
reviewable adapter for the smallest proposed controller extension; it must not
translate NativeChildAdapter's internal method names into Gateway RPC names.
"""


class GatewayCapabilityUnavailable(RuntimeError):
    """Raised before any RPC when the reviewed controller boundary is absent."""


class GatewayContractError(ValueError):
    """Raised for a malformed local request before any RPC."""


class OpenClawGatewayNativeProvider(object):
    START_METHOD = 'xuanjun.execution.start'
    INSPECT_METHOD = 'xuanjun.execution.inspect'
    REQUIRED_METHODS = frozenset([START_METHOD, INSPECT_METHOD])
    VERIFIED_READ_ONLY_METHODS = frozenset(
        ['agent.wait', 'sessions.list', 'sessions.get'])
    FORBIDDEN_GATEWAY_METHODS = frozenset(
        ['spawn', 'status', 'reconcile_spawn', 'recover_report',
         'sessions.spawn', 'subagents.list'])

    def __init__(self, gateway, installed_methods, activation_reviewed=False):
        self.gateway = gateway
        self.installed_methods = frozenset(installed_methods or [])
        self.activation_reviewed = activation_reviewed is True

    def _require_controller(self):
        missing = self.REQUIRED_METHODS - self.installed_methods
        if not self.activation_reviewed or missing:
            detail = ','.join(sorted(missing)) if missing else 'activation review'
            raise GatewayCapabilityUnavailable(
                'trusted execution controller unavailable: ' + detail)

    def _call(self, method, params):
        if method in self.FORBIDDEN_GATEWAY_METHODS:
            raise GatewayContractError('internal/nonexistent Gateway method rejected')
        if method not in self.REQUIRED_METHODS:
            raise GatewayContractError('unreviewed Gateway method rejected')
        return self.gateway.call(method, params)

    @staticmethod
    def _nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def spawn(self, binding, idempotency_key):
        """Start only through an installed, reviewed execution controller.

        Capability and immutable request checks happen before the first RPC.
        A malformed response is returned unchanged so NativeChildAdapter records
        UNKNOWN_SIDE_EFFECT_HOLD instead of retrying the possible effect.
        """
        self._require_controller()
        if not isinstance(binding, dict) or not self._nonempty(idempotency_key):
            raise GatewayContractError('binding and idempotency key required')
        request = {'binding': dict(binding),
                   'idempotency_key': idempotency_key}
        return self._call(self.START_METHOD, request)

    def reconcile_spawn(self, idempotency_key):
        """Inspect the original attempt; never start a replacement to discover it."""
        self._require_controller()
        if not self._nonempty(idempotency_key):
            raise GatewayContractError('idempotency key required')
        value = self._call(self.INSPECT_METHOD,
                           {'idempotency_key': idempotency_key})
        if not isinstance(value, dict):
            return None
        receipt = value.get('start_receipt')
        return receipt if isinstance(receipt, dict) else None

    def status(self, run_id, session_id):
        """Return UNKNOWN unless the controller identifies the exact execution."""
        self._require_controller()
        if not self._nonempty(run_id) or not self._nonempty(session_id):
            raise GatewayContractError('run and session required')
        value = self._call(self.INSPECT_METHOD,
                           {'run_id': run_id, 'session_id': session_id})
        if (not isinstance(value, dict) or value.get('run_id') != run_id
                or value.get('session_id') != session_id
                or value.get('authoritative') is not True
                or value.get('source') != 'canonical_execution_controller'):
            return {'run_id': run_id, 'session_id': session_id,
                    'state': 'unknown', 'process_alive': None,
                    'unit_active': None, 'last_progress_at': None}
        result = {'run_id': run_id, 'session_id': session_id,
                  'state': value.get('state', 'unknown'),
                  'process_alive': value.get('process_alive'),
                  'unit_active': value.get('unit_active'),
                  'last_progress_at': value.get('last_progress_at')}
        report = value.get('report')
        if isinstance(report, dict):
            result['report'] = report
        return result

    def recover_report(self, run_id, session_id):
        """Accept only a controller-bound durable report, never model text."""
        status = self.status(run_id, session_id)
        report = status.get('report')
        return report if isinstance(report, dict) else None
