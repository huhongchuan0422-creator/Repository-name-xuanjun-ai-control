"""Fenced Owner decisions over the canonical ledger socket. Python 3.6."""
import hashlib
import hmac
import json
import math
import os
import socket
import sqlite3
from native_peer_identity import verify_native_gateway_peer
from ledger_read_transport import MonotonicIODeadline
import struct


CALLBACK_SCHEMAS = {
    'owner_callback_requests': {'request_id', 'task_id', 'fence', 'owner_id',
                                'owner_chat', 'expires_at', 'consumed'},
    'owner_callback_replays': {'update_id', 'request_id'},
}
ACTIVATION_KEYS = ('ledger_uuid', 'generation', 'epoch', 'instance')
REQUEST_KEYS = frozenset(['operation', 'ledger_uuid', 'generation', 'epoch',
                          'instance', 'event'])
RESPONSE_KEYS = frozenset(['accepted', 'state', 'task_id', 'fence',
                           'ledger_uuid', 'generation', 'epoch', 'instance'])
EVENT_KEYS = frozenset(['request_id', 'task_id', 'fence', 'owner_user_id',
                        'owner_chat_id', 'update_id', 'decision'])


def validate_schema_connection(db):
    core = {
        'tasks': {'id', 'state', 'fence'},
        'approvals': {'task_id', 'decision'},
        'events': {'task_id', 'event', 'created', 'details'},
    }
    for table, required in dict(core, **CALLBACK_SCHEMAS).items():
        columns = {row[1] for row in db.execute('PRAGMA table_info(%s)' % table)}
        if not required.issubset(columns):
            raise ValueError('SCHEMA_MISMATCH_' + table.upper())
    return True


def validate_schema(dbpath):
    db = sqlite3.connect('file:' + dbpath + '?mode=ro', uri=True)
    try:
        return validate_schema_connection(db)
    finally:
        db.close()


def _validate_event_shape(event):
    if not isinstance(event, dict) or set(event) != EVENT_KEYS:
        raise ValueError('bad event keys')
    if event['decision'] not in ('APPROVE', 'REJECT'):
        raise ValueError('bad decision')
    if (type(event['fence']) is not int or event['fence'] < 1
            or type(event['update_id']) is not int):
        raise ValueError('bad fence/update')
    if (not isinstance(event['request_id'], str) or not event['request_id']
            or not isinstance(event['task_id'], str) or not event['task_id']):
        raise ValueError('bad request')
    return event


def _event(body, auth, signature, expected_token, secret, owner_id,
           owner_chat_id):
    if not hmac.compare_digest(auth or '', 'Bearer ' + expected_token):
        raise ValueError('bad service auth')
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or '', expected):
        raise ValueError('bad signature')
    event = _validate_event_shape(json.loads(body.decode('utf-8')))
    if str(event['owner_user_id']) != str(owner_id):
        raise ValueError('bad owner')
    if str(event['owner_chat_id']) != str(owner_chat_id):
        raise ValueError('bad owner chat')
    return event


def _strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result or key in ('__proto__', 'constructor', 'prototype'):
                raise ValueError('duplicate or unsafe JSON key')
            result[key] = value
        return result
    def finite(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError('nonfinite JSON number')
        return value
    def constant(unused):
        raise ValueError('nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite, parse_constant=constant)


def _read_line(connection, maximum=8192, deadline=None):
    payload = bytearray()
    while b'\n' not in payload:
        if deadline is not None:
            deadline.arm(connection)
        chunk = connection.recv(maximum - len(payload))
        if deadline is not None:
            deadline.check()
        if not chunk:
            raise ValueError('truncated ledger response')
        payload.extend(chunk)
        if len(payload) >= maximum:
            raise ValueError('oversized ledger message')
    line, remainder = bytes(payload).split(b'\n', 1)
    if remainder:
        raise ValueError('multiple ledger messages rejected')
    result = _strict_json(line.decode('utf-8'))
    if deadline is not None:
        deadline.check()
    return result


def send_ledger_request(socket_path, request, timeout=5):
    """Send one bounded request to the descriptor-selected Unix socket."""
    if (not isinstance(socket_path, str) or not os.path.isabs(socket_path)
            or os.path.realpath(socket_path) != socket_path):
        raise ValueError('ledger socket is not canonical')
    packed = (json.dumps(request, sort_keys=True, separators=(',', ':'),
                         allow_nan=False) + '\n').encode('utf-8')
    if len(packed) >= 8192:
        raise ValueError('oversized ledger request')
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout)
        connection.connect(socket_path)
        connection.sendall(packed)
        return _read_line(connection)
    finally:
        connection.close()


def apply(activation_store, body, auth, signature, expected_token, secret,
          owner_id, owner_chat_id, now=None, connector=send_ledger_request):
    """Authenticate an Owner event and route it to the one active ledger."""
    del now  # Expiry is checked in the authoritative atomic transaction.
    event = _event(body, auth, signature, expected_token, secret, owner_id,
                   owner_chat_id)
    active = activation_store.read(require_active=True)
    request = {'operation': 'OWNER_DECISION', 'event': event}
    request.update({key: active[key] for key in ACTIVATION_KEYS})
    result = connector(active['ledger_socket'], request)
    if (not isinstance(result, dict) or set(result) != RESPONSE_KEYS
            or result.get('accepted') is not True
            or result.get('task_id') != event['task_id']
            or result.get('fence') != event['fence']
            or any(result.get(key) != active[key] for key in ACTIVATION_KEYS)):
        raise RuntimeError('invalid ledger response')
    after = activation_store.read(require_active=True)
    if any(after[key] != active[key]
           for key in ACTIVATION_KEYS + ('ledger_socket',)):
        raise RuntimeError('activation changed during Owner decision')
    return {'accepted': True}


class LedgerOwnerDecisionServer(object):
    """Bounded ledger-service adapter; exposes no SQL or arbitrary operation."""

    def __init__(self, activation_store, ledger, callback_uid, native_identity=None,
                 owner_process_verifier=None):
        if type(callback_uid) is not int or callback_uid < 1:
            raise ValueError('callback UID must be unprivileged')
        self.activation_store = activation_store
        self.ledger = ledger
        self.callback_uid = callback_uid
        if native_identity is not None and (
                not isinstance(native_identity, dict)
                or type(native_identity.get('uid')) is not int
                or native_identity['uid'] < 1
                or native_identity['uid'] == callback_uid):
            raise ValueError('narrow native Gateway identity required')
        self.native_identity = native_identity
        if owner_process_verifier is not None and not callable(owner_process_verifier):
            raise ValueError('OWNER_PROCESS_VERIFIER_REQUIRED')
        # Callback and dashboard share a UID. That UID is not mutation authority.
        # No production process verifier is inferred from the UID or script name.
        self.owner_process_verifier = owner_process_verifier

    def serve_connection(self, connection):
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                             struct.calcsize('3i'))
        peer_pid, peer_uid, unused_gid = struct.unpack('3i', credentials)
        if self.native_identity is not None and peer_uid == self.native_identity['uid']:
            if not verify_native_gateway_peer(peer_pid, peer_uid, self.native_identity):
                raise PermissionError('native Gateway process identity rejected')
            request = _read_line(connection, maximum=1048576)
            if not isinstance(request, dict) or set(request) != {'operation', 'payload'} or request['operation'] != 'NATIVE_GATEWAY':
                raise PermissionError('native socket role rejected')
            from native_ledger_operations import execute
            result = execute(self.ledger, request['payload'])
            packed = (json.dumps({'accepted':True, 'result':result}, sort_keys=True,
                                 separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')
            if len(packed) >= 1048576:
                raise ValueError('native response limit')
            connection.sendall(packed)
            return
        # Native peers retain their exact pinned-process authentication above.
        # Root receives only the broker observation operation; callback keeps
        # its original Owner decision role and gains the sanitized snapshot.
        if peer_uid not in (0, self.callback_uid):
            raise PermissionError('ledger socket peer rejected')
        # The operation is not known until the shared root/callback frame has
        # been parsed. Bound that initial read for both roles, before mutations.
        # Restore the prior timeout so Owner response behavior is unchanged.
        deadline = MonotonicIODeadline(5, 'LEDGER_REQUEST_DEADLINE_EXCEEDED')
        prior_timeout = connection.gettimeout()
        try:
            request = _read_line(connection, deadline=deadline)
        finally:
            connection.settimeout(prior_timeout)
        if isinstance(request, dict) and request.get('operation') in (
                'BROKER_OBSERVATION', 'DASHBOARD_SNAPSHOT'):
            from ledger_read_projection import project
            from owner_dashboard import snapshot
            packed = project(request, peer_uid, self.callback_uid,
                             self.activation_store, self.ledger, snapshot)
            deadline.arm(connection)
            connection.sendall(packed)
            deadline.check()
            return
        # Root must never reach Owner mutation authorization.
        if peer_uid != self.callback_uid:
            raise PermissionError('ledger socket peer rejected')
        if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
            raise ValueError('ledger request keys mismatch')
        if request['operation'] != 'OWNER_DECISION':
            raise ValueError('unsupported ledger operation')
        if self.owner_process_verifier is None:
            raise PermissionError('OWNER_PROCESS_VERIFIER_REQUIRED')
        deadline.check()
        if self.owner_process_verifier(peer_pid, peer_uid) is not True:
            raise PermissionError('OWNER_PROCESS_IDENTITY_REJECTED')
        deadline.check()
        active = self.activation_store.read(require_active=True)
        if any(request[key] != active[key] for key in ACTIVATION_KEYS):
            raise PermissionError('stale Owner activation')
        event = request['event']
        _validate_event_shape(event)
        result = self.ledger.owner_decision(
            event.get('task_id'), event.get('fence'), event.get('decision'),
            event.get('request_id'), event.get('update_id'),
            event.get('owner_user_id'), event.get('owner_chat_id'),
            'owner-callback:%d' % peer_uid, True)
        after = self.activation_store.read(require_active=True)
        if any(after[key] != active[key] for key in ACTIVATION_KEYS):
            raise RuntimeError('activation changed during Owner transaction')
        response = dict(result)
        response.update({key: active[key] for key in ACTIVATION_KEYS})
        if set(response) != RESPONSE_KEYS:
            raise RuntimeError('unexpected ledger decision result')
        connection.sendall((json.dumps(response, sort_keys=True,
                                       separators=(',', ':')) + '\n').encode('utf-8'))


def install_schema(dbpath):
    """Offline staged-generation migration helper; never used by callback."""
    db = sqlite3.connect(dbpath, isolation_level=None)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute("""CREATE TABLE IF NOT EXISTS owner_callback_requests(
          request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,fence INTEGER NOT NULL,
          owner_id TEXT NOT NULL,owner_chat TEXT NOT NULL,expires_at REAL NOT NULL,
          consumed INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS owner_callback_replays(
          update_id INTEGER PRIMARY KEY,request_id TEXT NOT NULL UNIQUE)""")
        columns = {row[1] for row in db.execute(
            'PRAGMA table_info(owner_callback_requests)')}
        if 'owner_chat' not in columns:
            db.execute('ALTER TABLE owner_callback_requests ADD COLUMN owner_chat TEXT')
        validate_schema_connection(db)
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
    finally:
        db.close()
