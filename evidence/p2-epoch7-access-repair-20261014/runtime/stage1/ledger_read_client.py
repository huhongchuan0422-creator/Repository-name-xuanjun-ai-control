"""Read-only clients; services must inject authenticated ledger transport.

No default transport and no database open, task creation, or execution grant.
The service entrypoints use AuthenticatedLedgerReadTransport, whose mandatory
server verifier requires a protected measured policy; no permissive default exists.
"""
from ledger_read_projection import BINDING_KEYS, GATE_KEYS, same_binding, validate_request


def read_projection(store, transport, operation, payload):
    if not callable(transport):
        raise ValueError('AUTHENTICATED_TRANSPORT_REQUIRED')
    before = dict(store.read(require_active=True))
    request = {k: before[k] for k in BINDING_KEYS}
    request.update(operation=operation, payload=payload)
    validate_request(request)
    response = transport(before['ledger_socket'], request)
    required = set(BINDING_KEYS + ('accepted', 'operation', 'result'))
    if (not isinstance(response, dict) or set(response) != required
            or response.get('accepted') is not True or response.get('operation') != operation
            or not same_binding(response, before, BINDING_KEYS)):
        raise RuntimeError('READ_PROJECTION_RESPONSE_MISMATCH')
    after = store.read(require_active=True)
    if not same_binding(after, before, GATE_KEYS):
        raise RuntimeError('READ_PROJECTION_ACTIVATION_CHANGED')
    return response['result']


class BrokerObservationClient(object):
    def __init__(self, activation, transport):
        if not callable(transport):
            raise ValueError('AUTHENTICATED_TRANSPORT_REQUIRED')
        self.activation, self.transport = activation, transport

    def observation(self, task_id):
        if not isinstance(task_id, str) or not 1 <= len(task_id) <= 256 or '\x00' in task_id:
            raise ValueError('TASK_ID_REQUIRED')
        return read_projection(self.activation, self.transport,
                               'BROKER_OBSERVATION', {'task_id': task_id})


def dashboard_read(activation, transport, limit=200):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('DASHBOARD_LIMIT')
    return read_projection(activation, transport, 'DASHBOARD_SNAPSHOT', {'limit': limit})
