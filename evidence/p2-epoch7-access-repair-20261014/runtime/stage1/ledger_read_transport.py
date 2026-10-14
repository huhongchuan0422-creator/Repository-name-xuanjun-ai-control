"""Bounded read-only Unix transport with mandatory server authentication.

Production clients load an explicit protected root-manager policy; no UID is inferred.
SO_PEERCRED may identify systemd's socket creator rather than the service user.
The shared ledger_server_identity verifier requires measured, approved pins.
This module does not alter permissions, start services, or open a database.
"""
import json
import math
import os
import socket
import struct
import time

MAX_REQUEST = 8192
MAX_RESPONSE = 1048576


class MonotonicIODeadline(object):
    """One total I/O budget; a trickle never refreshes the deadline.

    Checks after I/O/parsing also reject operations that return after expiry.
    Arbitrary verifier/provider code is not preempted; it must independently
    avoid blocking indefinitely. Its elapsed time consumes this same budget.
    """
    def __init__(self, timeout, message='READ_TRANSPORT_DEADLINE_EXCEEDED'):
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 30):
            raise ValueError('READ_TRANSPORT_TIMEOUT')
        self.expires = time.monotonic() + timeout
        self.message = message

    def check(self):
        remaining = self.expires - time.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise socket.timeout(self.message)
        return remaining

    def arm(self, connection):
        connection.settimeout(self.check())


class PinnedPeerCredentials(object):
    """Explicit process/UID/GID pin for a verified socket creator lifetime.

    Not a persistent deployment identity: PID reuse/restarts and inherited
    systemd sockets require independently reviewed provisioning and attestation.
    A UID alone is deliberately insufficient to construct this verifier.
    """
    def __init__(self, pid, uid, gid):
        if (type(pid) is not int or pid < 1 or type(uid) is not int or uid < 0
                or type(gid) is not int or gid < 0):
            raise ValueError('EXACT_SERVER_CREDENTIAL_PIN_REQUIRED')
        self.expected = (pid, uid, gid)

    def __call__(self, pid, uid, gid, socket_path):
        return (pid, uid, gid) == self.expected


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result or key in ('__proto__', 'constructor', 'prototype'):
                raise ValueError('READ_TRANSPORT_JSON_KEYS')
            result[key] = value
        return result

    def finite(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError('READ_TRANSPORT_NONFINITE')
        return value

    def constant(unused):
        raise ValueError('READ_TRANSPORT_NONFINITE')

    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_float=finite, parse_constant=constant)


def _read_response(connection, deadline):
    payload = bytearray()
    while b'\n' not in payload:
        deadline.arm(connection)
        chunk = connection.recv(min(65536, MAX_RESPONSE - len(payload)))
        deadline.check()
        if not chunk:
            raise ValueError('READ_TRANSPORT_TRUNCATED')
        payload.extend(chunk)
        if len(payload) >= MAX_RESPONSE:
            raise ValueError('READ_TRANSPORT_RESPONSE_BOUND')
    line, remainder = bytes(payload).split(b'\n', 1)
    if remainder:
        raise ValueError('READ_TRANSPORT_MULTIPLE_RESPONSES')
    # The existing ledger service closes each accepted connection after one
    # response. Require EOF so extra frames split across recv boundaries cannot
    # evade the one-response gate. An idle peer consumes the same deadline.
    deadline.arm(connection)
    trailing = connection.recv(1)
    deadline.check()
    if trailing:
        raise ValueError('READ_TRANSPORT_MULTIPLE_RESPONSES')
    result = _strict_json(line)
    deadline.check()
    return result


class CallableServerSession(object):
    """Explicit test/custom verifier injection, checked before and after data."""
    def __init__(self, verifier, path, deadline):
        self.verifier, self.path, self.deadline = verifier, path, deadline
    def verify(self, credentials):
        self.deadline.check()
        result = self.verifier(*(tuple(credentials) + (self.path,)))
        self.deadline.check()
        return result is True
    finish = verify


def server_session(verifier, path, deadline):
    if not callable(verifier): raise ValueError('AUTHENTICATED_SERVER_VERIFIER_REQUIRED')
    # Look on the type, so generic mocks/callables cannot accidentally create a
    # permissive dynamic session attribute. Production class has explicit API.
    factory = getattr(type(verifier), 'session', None)
    result = factory(verifier, path, deadline) if callable(factory) else CallableServerSession(verifier, path, deadline)
    deadline.check()
    return result


def peer_credentials(connection, deadline):
    deadline.arm(connection)
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    deadline.check()
    value = struct.unpack('3i', raw)
    if value[0] < 1 or value[1] < 0 or value[2] < 0:
        raise PermissionError('READ_TRANSPORT_SERVER_IDENTITY_REJECTED')
    return value


class AuthenticatedLedgerReadTransport(object):
    def __init__(self, server_verifier, timeout=5):
        if not callable(server_verifier):
            raise ValueError('AUTHENTICATED_SERVER_VERIFIER_REQUIRED')
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 30):
            raise ValueError('READ_TRANSPORT_TIMEOUT')
        self.server_verifier, self.timeout = server_verifier, timeout

    def __call__(self, socket_path, request):
        deadline = MonotonicIODeadline(self.timeout)
        if (not isinstance(socket_path, str) or '\x00' in socket_path
                or not os.path.isabs(socket_path)
                or os.path.realpath(socket_path) != socket_path):
            raise ValueError('READ_TRANSPORT_CANONICAL_SOCKET_REQUIRED')
        # The transport cannot be reused as a privileged generic request proxy.
        from ledger_read_projection import validate_request
        validate_request(request)
        packed = (json.dumps(request, sort_keys=True, separators=(',', ':'),
                             allow_nan=False) + '\n').encode('utf-8')
        if len(packed) >= MAX_REQUEST:
            raise ValueError('READ_TRANSPORT_REQUEST_BOUND')
        session = server_session(self.server_verifier, socket_path, deadline)
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            deadline.arm(connection)
            connection.connect(socket_path)
            credentials = peer_credentials(connection, deadline)
            if session.verify(credentials) is not True:
                raise PermissionError('READ_TRANSPORT_SERVER_IDENTITY_REJECTED')
            # Do not disclose the request, even its task ID, before verification.
            deadline.arm(connection)
            connection.sendall(packed)
            deadline.check()
            result = _read_response(connection, deadline)
            if session.finish(peer_credentials(connection, deadline)) is not True:
                raise PermissionError('READ_TRANSPORT_SERVER_IDENTITY_REJECTED')
            deadline.check()
            return result
        finally:
            connection.close()
