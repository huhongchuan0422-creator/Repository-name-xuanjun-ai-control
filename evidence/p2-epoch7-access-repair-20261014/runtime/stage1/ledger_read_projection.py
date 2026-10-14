"""Typed read projections on the existing canonical ledger socket.

Local integration candidate only. No SQL/path input, task creation, lease
mutation, alternate database, queue, permission grant, or worker launch.
"""
import json

BINDING_KEYS = ('ledger_uuid', 'generation', 'epoch', 'instance')
GATE_KEYS = BINDING_KEYS + ('db_path', 'ledger_socket')
MAX_RESPONSE = 1048576


def validate_request(request):
    if not isinstance(request, dict) or set(request) != set(BINDING_KEYS + ('operation', 'payload')):
        raise ValueError('READ_PROJECTION_SCHEMA')
    operation, payload = request['operation'], request['payload']
    if operation == 'BROKER_OBSERVATION':
        if (not isinstance(payload, dict) or set(payload) != {'task_id'}
                or not isinstance(payload['task_id'], str)
                or not 1 <= len(payload['task_id']) <= 256 or '\x00' in payload['task_id']):
            raise ValueError('BROKER_READ_PAYLOAD')
    elif operation == 'DASHBOARD_SNAPSHOT':
        if (not isinstance(payload, dict) or set(payload) != {'limit'}
                or type(payload['limit']) is not int or not 1 <= payload['limit'] <= 500):
            raise ValueError('DASHBOARD_READ_PAYLOAD')
    else:
        raise PermissionError('UNSUPPORTED_READ_OPERATION')
    return operation, payload


def same_binding(left, right, keys):
    return all(key in left and key in right and type(left[key]) is type(right[key])
               and left[key] == right[key] for key in keys)


def _pack_bounded(response):
    # Bound the accumulated serialized frame; provider reads and individual
    # encoder chunks retain their existing memory/data-read semantics.
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), allow_nan=False)
    packed = bytearray()
    for part in encoder.iterencode(response):
        raw = part.encode('utf-8')
        if len(packed) + len(raw) + 1 >= MAX_RESPONSE:
            raise ValueError('READ_PROJECTION_RESPONSE_BOUND')
        packed.extend(raw)
    packed.extend(b'\n')
    return bytes(packed)


def project(request, peer_uid, callback_uid, activation_store, ledger, dashboard_snapshot):
    if (type(peer_uid) is not int or peer_uid < 0
            or type(callback_uid) is not int or callback_uid <= 0):
        raise PermissionError('READ_PROJECTION_IDENTITY')
    operation, payload = validate_request(request)
    if operation == 'BROKER_OBSERVATION' and peer_uid != 0:
        raise PermissionError('BROKER_READ_ROLE')
    if operation == 'DASHBOARD_SNAPSHOT' and peer_uid != callback_uid:
        raise PermissionError('DASHBOARD_READ_ROLE')
    before = dict(activation_store.read(require_active=True))
    if not same_binding(request, before, BINDING_KEYS):
        raise PermissionError('STALE_READ_ACTIVATION')
    if operation == 'BROKER_OBSERVATION':
        result = ledger.observation(payload['task_id'])
    else:
        result = dashboard_snapshot(before['db_path'], limit=payload['limit'],
                                    activation={k: before[k] for k in BINDING_KEYS})
    response = {'accepted': True, 'operation': operation, 'result': result}
    response.update({k: before[k] for k in BINDING_KEYS})
    packed = _pack_bounded(response)
    # Recheck after data collection AND serialization, immediately before return.
    after = activation_store.read(require_active=True)
    if not same_binding(after, before, GATE_KEYS):
        raise RuntimeError('READ_ACTIVATION_CHANGED')
    return packed
