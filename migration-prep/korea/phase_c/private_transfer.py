"""Single-shot closed snapshot transfer on an explicitly provisioned mTLS channel.

No listener, credentials, DNS lookup, SSH/tunnel change or production endpoint is
created by importing this module. Both certificate chain AND exact peer leaf DER
pin are checked before frames. Source signature is independently checked before
receiver publication. Missing ACK is UNKNOWN, never an instruction to resend.
Only private receipts are returned; business bytes never go to logs/GitHub.
"""
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import struct
import time

from gate_common import canonical_bytes, require
from korea.phase_c.security import digest, identifier, read_file, strict_json, trusted_directory, write_once
from korea.phase_c.snapshots import GENERATION_FILES, collect_generation, receive_generation

PROTOCOL = "PR99_PRIVATE_SNAPSHOT_MTLS_V1"
MAX_DATABASE = 64 * 1024 * 1024  # Explicit 2GiB-host budget; growth fails closed.
MAX_METADATA = 16384
MAX_HEADER = 8192


def sha_field(value):
    require(type(value) is str and len(value) == 64 and
            all(c in "0123456789abcdef" for c in value), "C_TRANSFER_SHA256")
    return value


def tls_context(material, server=False):
    require(type(material) is dict and set(material) == {
        "ca", "certificate", "private_key", "ca_sha256", "certificate_sha256", "private_key_sha256"},
        "C_TLS_MATERIAL_FIELDS")
    for name in ("ca", "certificate", "private_key"):
        raw = read_file(material[name], modes=(0o400, 0o600) if name == "private_key" else (0o400, 0o444, 0o644))
        require(digest(raw) == sha_field(material[name + "_sha256"]), "C_TLS_MATERIAL_PIN")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = not server
    context.load_verify_locations(cafile=material["ca"])
    context.load_cert_chain(material["certificate"], material["private_key"])
    return context


def verify_peer(channel, expected_der_sha256):
    require(isinstance(channel, ssl.SSLSocket) and channel.context.verify_mode == ssl.CERT_REQUIRED and
            channel.version() in ("TLSv1.2", "TLSv1.3") and
            digest(channel.getpeercert(binary_form=True) or b"") == sha_field(expected_der_sha256),
            "C_TLS_PEER_NOT_AUTHENTICATED")
    channel.settimeout(min(channel.gettimeout() or 10, 10))


def connect_pinned(address, port, server_name, material, peer_sha256, timeout=10):
    # The caller's separately approved root plan supplies this precise endpoint.
    ip = ipaddress.ip_address(address)
    require(str(ip) == address and not ip.is_unspecified and not ip.is_multicast and
            type(port) is int and 1 <= port <= 65535 and type(server_name) is str and
            1 <= len(server_name) <= 253 and type(timeout) is int and 1 <= timeout <= 30,
            "C_TRANSFER_ENDPOINT")
    context = tls_context(material)
    family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
    raw = socket.socket(family, socket.SOCK_STREAM)
    try:
        raw.settimeout(timeout)
        raw.connect((address, port))  # Numeric IP, no DNS/proxy/redirect/retry.
        channel = context.wrap_socket(raw, server_hostname=server_name)
        try:
            verify_peer(channel, peer_sha256)
            return channel
        except BaseException:
            channel.close()
            raise
    except BaseException:
        raw.close()
        raise


def _exact(channel, size, expires_at_ms=None, clock_ms=None):
    require(type(size) is int and 0 < size <= MAX_DATABASE, "C_TRANSFER_READ_BOUND")
    parts = bytearray()
    clock = clock_ms or (lambda: int(time.time() * 1000))
    expires = expires_at_ms if expires_at_ms is not None else clock() + 30000
    while len(parts) < size:
        remaining = (expires - clock()) / 1000.0
        require(remaining > 0, "C_TRANSFER_READ_EXPIRED")
        channel.settimeout(min(remaining, channel.gettimeout() or 10, 10))
        block = channel.recv(min(65536, size - len(parts)))
        require(bool(block), "C_TRANSFER_TRUNCATED_UNKNOWN_ACK")
        parts.extend(block)
    return bytes(parts)


def _json_read(channel, expires_at_ms=None, clock_ms=None):
    clock = clock_ms or (lambda: int(time.time() * 1000))
    expires = expires_at_ms if expires_at_ms is not None else clock() + 30000
    size = struct.unpack("!I", _exact(channel, 4, expires, clock))[0]
    require(0 < size <= MAX_HEADER, "C_TRANSFER_HEADER_SIZE")
    return strict_json(_exact(channel, size, expires, clock))


def _json_send(channel, value):
    raw = canonical_bytes(value)
    require(0 < len(raw) <= MAX_HEADER, "C_TRANSFER_HEADER_SIZE")
    channel.sendall(struct.pack("!I", len(raw)) + raw)


def _context(value, now_ms):
    require(type(value) is dict and set(value) == {"window_id", "generation_id", "nonce", "expires_at_ms"},
            "C_TRANSFER_CONTEXT_FIELDS")
    for name in ("window_id", "generation_id", "nonce"):
        identifier(value[name])
    require(type(value["expires_at_ms"]) is int and now_ms < value["expires_at_ms"] <= now_ms + 300000,
            "C_TRANSFER_CONTEXT_EXPIRED")


def _claim(root, name, value):
    root = trusted_directory(root, exact_mode=0o700)
    write_once(root / identifier(name), canonical_bytes(value))


def send_generation(channel, peer_sha256, generation, transfer, attempts, clock_ms=None):
    """One generation, one peer, one durable attempt, one ACK; no automatic retry."""
    clock = clock_ms or (lambda: int(time.time() * 1000))
    verify_peer(channel, peer_sha256)
    _context(transfer, clock())
    path = trusted_directory(generation, exact_mode=0o755)
    require(path.name == transfer["generation_id"] and set(p.name for p in path.iterdir()) == GENERATION_FILES,
            "C_TRANSFER_SOURCE_FILE_SET")
    files = {name: read_file(path / name, modes=(0o400, 0o444),
              limit=MAX_DATABASE if name == "business-snapshot.sqlite" else MAX_METADATA)
             for name in sorted(GENERATION_FILES)}
    receipt = strict_json(files["receipt.json"])
    require(receipt["snapshot_generation_id"] == transfer["generation_id"] and
            receipt["database_sha256"] == digest(files["business-snapshot.sqlite"]), "C_TRANSFER_SOURCE_BINDING")
    header = dict(protocol=PROTOCOL, transfer=transfer,
                  files={name: {"size": len(raw), "sha256": digest(raw)} for name, raw in files.items()})
    _claim(attempts, "send-" + transfer["generation_id"], header)
    _json_send(channel, header)
    for name in sorted(files):
        require(clock() < transfer["expires_at_ms"], "C_TRANSFER_EXPIRED_DURING_SEND")
        channel.sendall(files[name])
    ack = _json_read(channel, transfer["expires_at_ms"], clock)
    require(clock() < transfer["expires_at_ms"] and ack == {
        "protocol": PROTOCOL, "transfer": transfer, "status": "GENERATION_COMMITTED",
        "receipt_sha256": digest(files["receipt.json"]),
        "database_sha256": receipt["database_sha256"]}, "C_TRANSFER_ACK_UNKNOWN_OR_MISMATCH")
    return {"status": "PRIVATE_TRANSFER_ACKNOWLEDGED", "generation_id": transfer["generation_id"],
            "retry_allowed": False}


def receive_one(channel, peer_sha256, transfer, attempts, root, config, source_verifier, clock_ms=None):
    clock = clock_ms or (lambda: int(time.time() * 1000))
    verify_peer(channel, peer_sha256)
    _context(transfer, clock())
    header = _json_read(channel, transfer["expires_at_ms"], clock)
    require(type(header) is dict and set(header) == {"protocol", "transfer", "files"} and
            header["protocol"] == PROTOCOL and header["transfer"] == transfer and
            type(header["files"]) is dict and set(header["files"]) == GENERATION_FILES,
            "C_TRANSFER_HEADER_BINDING")
    for name, row in header["files"].items():
        require(type(row) is dict and set(row) == {"size", "sha256"} and type(row["size"]) is int and
                0 < row["size"] <= (MAX_DATABASE if name == "business-snapshot.sqlite" else MAX_METADATA),
                "C_TRANSFER_MEMBER_SIZE")
        sha_field(row["sha256"])
    # Consume before reading body: a disconnect/partial transfer never gives a new attempt.
    _claim(attempts, "receive-" + transfer["generation_id"], header)
    files = {}
    for name in sorted(header["files"]):
        require(clock() < transfer["expires_at_ms"], "C_TRANSFER_EXPIRED_DURING_RECEIVE")
        raw = _exact(channel, header["files"][name]["size"], transfer["expires_at_ms"], clock)
        require(digest(raw) == header["files"][name]["sha256"], "C_TRANSFER_MEMBER_HASH")
        files[name] = raw
    require(clock() < transfer["expires_at_ms"], "C_TRANSFER_EXPIRED_BEFORE_PUBLISH")
    result = receive_generation(root, transfer["generation_id"], files, config, source_verifier, clock())
    _json_send(channel, {"protocol": PROTOCOL, "transfer": transfer, "status": result["status"],
                        "receipt_sha256": digest(files["receipt.json"]),
                        "database_sha256": result["database_sha256"]})
    return {"status": "PRIVATE_TRANSFER_COMMITTED", "generation_id": transfer["generation_id"],
            "retry_allowed": False}


def collect_private(source, staging, generation_id, config, signer, now_ms):
    """Privileged caller supplies source identity after separate export admission.

    Closed source bytes stay UID0 even if Korea's worker UID already belongs to
    a different Tokyo user. The signed receipt names the exact Korea destination.
    No database is opened until this explicit function is called by an authorized
    source collector. No default path/account or automatic collector is provided.
    """
    require(os.geteuid() == 0, "C_TRANSFER_SOURCE_CUSTODIAN_ROOT")
    local = dict(config, snapshot_reader_uid=0)
    return collect_generation(source, staging, generation_id, local, signer, now_ms)
