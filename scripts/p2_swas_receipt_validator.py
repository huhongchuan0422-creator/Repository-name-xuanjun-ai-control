"""Strict public transport receipt validation. No private P2 material accepted."""
import json
import re

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
INSTANCE = '40dfc6a47d5e4363b9da7d0d6ab01cb1'
REGION = 'eu-west-1'
SCOPE = 'UK_TRANSPORT_IDENTITY_ONLY_NOT_P2_ACCEPTANCE'


class Hold(ValueError):
    pass


def need(ok):
    if not ok:
        raise Hold('RECEIPT_REJECTED')


def token(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def validate(detail, invoke_id, nonce):
    """Return only a whitelist; never include remote output/errors in failures."""
    try:
        need(token(invoke_id) and token(nonce))
        need(type(detail) is dict and detail.get('InvokeId') == invoke_id
             and detail.get('InstanceId') == INSTANCE
             and detail.get('InvocationStatus') == 'Success'
             and type(detail.get('ExitCode')) is int and detail['ExitCode'] == 0)
        raw = detail.get('Output')
        need(type(raw) is str and len(raw.encode('utf-8')) <= 2048)
        # No permissive base64 fallback: the new public protocol is plaintext JSON.
        body = json.loads(raw, object_pairs_hook=unique)
        need(type(body) is dict and set(body) == {'hostname', 'uid', 'python', 'nonce', 'private_inputs_read'})
        need(body['hostname'] == HOST and type(body['uid']) is int and body['uid'] == 0
             and body['nonce'] == nonce and body['private_inputs_read'] is False)
        v = body['python']
        need(type(v) is list and len(v) == 3
             and all(type(n) is int and 0 <= n <= 100 for n in v)
             and v[:2] == [3, 6])
        return {'scope': SCOPE, 'invoke_id': invoke_id, 'instance_id': INSTANCE,
                'region': REGION, 'hostname': HOST, 'uid': 0, 'python': v,
                'private_inputs_read': False, 'p2_accepted': False,
                'production_changes': 0, 'state': 'TRANSPORT_VERIFIED'}
    except Exception:
        raise Hold('RECEIPT_REJECTED') from None
