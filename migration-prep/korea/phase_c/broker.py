"""Fixed read-only collector, separated from the reconciliation worker by UID.

The worker cannot supply a URL, method, HTTP header, key, receipt or signing key.
The broker performs the allowlisted GET itself and signs that actual result.
No daemon is started on import. Deployment requires a separate exact approval.
"""
import os
import socket
import struct
import time
import uuid

from final_snapshot import REQUIRED_SURFACES
from gate_common import canonical_bytes, require
from korea.migration_shadow_entry import SignedReadonlyTransport, _hard_deadline
from korea.phase_c.network import ApprovedPinnedTransport, validate_policy
from korea.phase_c.security import hash_value, identifier, strict_json
from readonly_reconciliation_adapter import SYMBOLS

MAX_PACKET = 20 * 1024 * 1024
REQUEST_FIELDS = {"surface", "symbol", "cursor", "account_id", "snapshot_id", "run_id", "nonce"}


def _receive(connection, limit):
    def exact(count):
        result = bytearray()
        while len(result) < count:
            chunk = connection.recv(count - len(result))
            require(chunk, "C_BROKER_TRUNCATED_PACKET")
            result.extend(chunk)
        return bytes(result)
    size = struct.unpack("!I", exact(4))[0]
    require(0 < size <= limit, "C_BROKER_PACKET_SIZE")
    return strict_json(exact(size))


def _send(connection, value):
    raw = canonical_bytes(value)
    require(0 < len(raw) <= MAX_PACKET, "C_BROKER_PACKET_SIZE")
    connection.sendall(struct.pack("!I", len(raw)) + raw)


class ReadonlyBroker:
    def __init__(self, policy, account_id, api_key, api_secret, signer, window_id,
                 credential_expires_at_ms, transport=None, clock_ms=None):
        self.clock = clock_ms or (lambda: int(time.time() * 1000))
        validate_policy(policy, self.clock())
        identifier(account_id); identifier(window_id)
        self.policy, self.account = policy, account_id
        self.key, self.secret, self.signer = api_key, api_secret, signer
        self.window = window_id
        require(type(credential_expires_at_ms) is int and credential_expires_at_ms > self.clock(),
                "C_BROKER_CREDENTIAL_EXPIRED")
        self.credential_expires_at_ms = credential_expires_at_ms
        self.transport = transport or ApprovedPinnedTransport(policy, self.clock)
        self.seen = set()

    def handle(self, request, peer_uid):
        require(peer_uid == self.policy["worker_uid"], "C_BROKER_PEER_UID")
        validate_policy(self.policy, self.clock())
        require(self.clock() < self.credential_expires_at_ms, "C_BROKER_CREDENTIAL_EXPIRED")
        require(isinstance(request, dict) and set(request) == REQUEST_FIELDS, "C_BROKER_REQUEST_FIELDS")
        require(request["account_id"] == self.account and request["surface"] in REQUIRED_SURFACES,
                "C_BROKER_ACCOUNT_SURFACE")
        require(request["symbol"] is None or request["symbol"] in SYMBOLS, "C_BROKER_SYMBOL")
        cursor = request["cursor"]
        require(cursor is None or (isinstance(cursor, str) and cursor.isdigit() and
                                  0 < len(cursor) <= 20), "C_BROKER_CURSOR")
        for field in ("snapshot_id", "run_id", "nonce"):
            identifier(request[field])
        require(request["nonce"] not in self.seen and len(self.seen) < 100000,
                "C_BROKER_REPLAY_OR_REQUEST_BUDGET")
        # Claim before performing GET. Unknown result is not automatically retried.
        self.seen.add(request["nonce"])
        remaining = min(30, (min(self.policy["expires_at_ms"], self.credential_expires_at_ms) - self.clock()) / 1000.0)
        require(remaining > 0, "C_BROKER_DEADLINE")
        adapter = SignedReadonlyTransport(self.transport, self.key, self.secret,
                                         request["run_id"], time.monotonic() + remaining,
                                         clock_ms=self.clock)
        with _hard_deadline(remaining):
            response, receipt = adapter(request["surface"], request["symbol"], request["cursor"],
                                        self.account, request["snapshot_id"])
        validate_policy(self.policy, self.clock())
        require(self.clock() < self.credential_expires_at_ms, "C_BROKER_CREDENTIAL_EXPIRED")
        attestation = {"kind": "PR99_INDEPENDENT_GET_BROKER_V1", "window_id": self.window,
                       "request": request, "receipt": receipt, "response_sha256": hash_value(response),
                       "network_policy_sha256": hash_value(self.policy),
                       "signer_identity_sha256": self.signer.identity,
                       "expires_at_ms": min(self.policy["expires_at_ms"], self.clock() + 30000)}
        return {"response": response, "receipt": receipt, "attestation": attestation,
                "signature": self.signer.sign(attestation)}

    def serve_one(self, listener):
        """SO_PEERCRED is read from the accepted socket, never a caller header."""
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(35)
            _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            try:
                response = self.handle(_receive(connection, 8192), uid)
            except Exception:
                response = {"status": "HOLD_BROKER_REJECTED"}
            _send(connection, response)


class VerifiedBrokerClient:
    def __init__(self, socket_path, broker_uid, public_verifier, policy, account_id, window_id,
                 run_id, exchange=None, clock_ms=None):
        self.socket_path, self.broker_uid, self.verifier = str(socket_path), broker_uid, public_verifier
        self.policy, self.account, self.window, self.run_id = policy, account_id, window_id, run_id
        self.clock = clock_ms or (lambda: int(time.time() * 1000))
        self.exchange = exchange or self._exchange
        self.verified_receipts = {}

    def _exchange(self, request):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(35)
            connection.connect(self.socket_path)
            _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(uid == self.broker_uid, "C_BROKER_SERVER_UID")
            _send(connection, request)
            return _receive(connection, MAX_PACKET)

    def __call__(self, surface, symbol, cursor, account_id, snapshot_id):
        validate_policy(self.policy, self.clock())
        require(account_id == self.account, "C_CLIENT_ACCOUNT")
        request = dict(surface=surface, symbol=symbol, cursor=cursor, account_id=account_id,
                       snapshot_id=snapshot_id, run_id=self.run_id, nonce=uuid.uuid4().hex)
        packet = self.exchange(request)
        require(isinstance(packet, dict) and set(packet) == {
            "response", "receipt", "attestation", "signature"}, "C_BROKER_RESPONSE_FIELDS")
        attestation = packet["attestation"]
        expected = {"kind": "PR99_INDEPENDENT_GET_BROKER_V1", "window_id": self.window,
                    "request": request, "receipt": packet["receipt"],
                    "response_sha256": hash_value(packet["response"]),
                    "network_policy_sha256": hash_value(self.policy),
                    "signer_identity_sha256": self.verifier.identity,
                    "expires_at_ms": attestation.get("expires_at_ms")}
        require(attestation == expected and type(attestation["expires_at_ms"]) is int and
                self.clock() < attestation["expires_at_ms"] <= self.policy["expires_at_ms"] and
                self.verifier.verify(attestation, packet["signature"]), "C_BROKER_SIGNATURE_OR_BINDING")
        self.verified_receipts[hash_value(packet["receipt"])] = hash_value(packet["response"])
        return packet["response"], packet["receipt"]

    def verify_receipt(self, receipt, response):
        return self.verified_receipts.pop(hash_value(receipt), None) == hash_value(response)
