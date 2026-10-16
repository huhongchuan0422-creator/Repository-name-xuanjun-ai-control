"""Atomic pair delivery from an already authorized SecretRef provider.

No environment/argv/HTTP source is supported.  The provider is injected by the
trusted custodian; the worker has no access to the delivered generation.
"""
import os
from pathlib import Path

from gate_common import canonical_bytes, require
from korea.phase_c.security import fsync_dir, identifier, read_file, rename_new, trusted_directory, write_once


ROLE = "BINANCE_ACCOUNT_READONLY"


def validate_attestation(record, expected, now_ms):
    require(set(record) == {"account_id", "role", "secret_ref", "read_only_verified",
                            "trading_enabled", "withdrawal_enabled", "expires_at_ms"},
            "C_SECRET_ATTESTATION_FIELDS")
    require(all(record[key] == expected[key] for key in ("account_id", "role", "secret_ref")) and
            record["role"] == ROLE and record["read_only_verified"] is True and
            record["trading_enabled"] is False and record["withdrawal_enabled"] is False and
            type(record["expires_at_ms"]) is int and record["expires_at_ms"] > now_ms,
            "C_READONLY_ATTESTATION_REQUIRED")


def deliver_pair(root, generation_id, uid, gid, expected, provider, verify_attestation, now_ms):
    """Provider returns one key/secret/attestation tuple; publish whole directory once.

    A crash leaves a private .pending directory. It is preserved, never retried or
    cleaned automatically. Source SecretRef and old generations are untouched.
    """
    root = trusted_directory(root, exact_mode=0o711)
    require(os.geteuid() == 0 and uid == 986 and gid == 986, "C_CUSTODIAN_ROOT_UID")
    identifier(generation_id)
    require(expected["role"] == ROLE and isinstance(expected["secret_ref"], str) and
            expected["secret_ref"] and "TRADING" not in expected["secret_ref"].upper(),
            "C_SECRET_REFERENCE")
    pending = root / (".pending-" + generation_id)
    destination = root / generation_id
    require(not os.path.lexists(destination), "C_CREDENTIAL_GENERATION_EXISTS")
    pending.mkdir(mode=0o700)  # O_EXCL directory is also the once/concurrency claim.
    os.chmod(pending, 0o700)
    key, secret, attestation = provider(expected["secret_ref"])
    validate_attestation(attestation, expected, now_ms)
    require(verify_attestation(attestation) is True, "C_SECRET_ATTESTATION_UNVERIFIED")
    for name, value in (("api_key", key), ("api_secret", secret)):
        require(type(value) is bytes and 1 <= len(value) <= 4096 and value == value.strip() and
                b"\x00" not in value and b"\n" not in value, "C_SECRET_VALUE")
        write_once(pending / name, value, mode=0o400, uid=uid, gid=gid)
    write_once(pending / "custody.json", canonical_bytes(attestation), mode=0o444)
    # Root owns directory: broker can read but cannot replace either file.
    os.chmod(pending, 0o711)
    fsync_dir(pending)
    rename_new(pending, destination)
    return {"generation_id": generation_id, "credential_role": ROLE,
            "account_id": expected["account_id"], "plaintext_exported": False}


def load_pair(generation, expected, verify_attestation, now_ms):
    path = trusted_directory(generation, exact_mode=0o711)
    require(not path.name.startswith("."), "C_PENDING_CREDENTIALS_FORBIDDEN")
    from korea.phase_c.security import strict_json
    attestation = strict_json(read_file(path / "custody.json", modes=(0o444,)))
    validate_attestation(attestation, expected, now_ms)
    require(verify_attestation(attestation) is True, "C_SECRET_ATTESTATION_UNVERIFIED")
    return (read_file(path / "api_key", owner=986, modes=(0o400,), limit=4096),
            read_file(path / "api_secret", owner=986, modes=(0o400,), limit=4096))
