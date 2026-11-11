"""Detached authenticated binding for an existing encrypted archive.

The signature and pinned public-key fingerprint must be stored in a different
trust domain from the archive.  The module does not encrypt, decrypt or copy the
archive and therefore cannot repeat the preserved backup work.
"""
from __future__ import print_function

import base64
import hashlib
import os
import subprocess
import tempfile

from gate_common import canonical_bytes, require


def subject(artifact_id, sha256, size_bytes, source_host, replica_host, evidence_ids):
    require(len(sha256) == 64 and all(ch in "0123456789abcdef" for ch in sha256), "BIND_SHA256_INVALID")
    require(isinstance(size_bytes, int) and size_bytes > 0, "BIND_SIZE_INVALID")
    require(source_host != replica_host, "BIND_REPLICA_MUST_BE_OFF_HOST")
    return {
        "schema_version": 1,
        "artifact_id": artifact_id,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "source_host": source_host,
        "replica_host": replica_host,
        "evidence_ids": list(evidence_ids),
        "statement": "EXISTING_ARCHIVE_IDENTITY_ONLY_NOT_FINAL_SNAPSHOT"
    }


def key_fingerprint(public_key_path):
    with open(public_key_path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def _openssl(args, stdin=None):
    result = subprocess.run(["openssl"] + args, input=stdin, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=20)
    require(result.returncode == 0, "BIND_OPENSSL_FAILED")
    return result.stdout


def sign(statement, private_key_path, key_id):
    require(os.path.isfile(private_key_path), "BIND_PRIVATE_KEY_REQUIRED")
    descriptor, statement_path = tempfile.mkstemp(prefix="xj-statement-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(statement))
            descriptor = None
        signature = _openssl(["pkeyutl", "-sign", "-rawin", "-inkey", private_key_path,
                              "-in", statement_path])
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(statement_path)
        except OSError:
            pass
    return {"algorithm": "ED25519", "key_id": key_id,
            "signature_b64": base64.b64encode(signature).decode("ascii")}


def verify(statement, binding, public_key_path, pinned_public_key_sha256):
    require(binding.get("algorithm") == "ED25519", "BIND_ALGORITHM_INVALID")
    require(key_fingerprint(public_key_path) == pinned_public_key_sha256, "BIND_TRUST_ANCHOR_MISMATCH")
    signature = base64.b64decode(binding["signature_b64"].encode("ascii"), validate=True)
    descriptor, signature_path = tempfile.mkstemp(prefix="xj-binding-")
    statement_descriptor, statement_path = tempfile.mkstemp(prefix="xj-statement-")
    try:
        os.write(descriptor, signature)
        os.close(descriptor)
        descriptor = None
        os.write(statement_descriptor, canonical_bytes(statement))
        os.close(statement_descriptor)
        statement_descriptor = None
        _openssl(["pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", public_key_path,
                  "-sigfile", signature_path, "-in", statement_path])
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if statement_descriptor is not None:
            os.close(statement_descriptor)
        try:
            os.unlink(signature_path)
        except OSError:
            pass
        try:
            os.unlink(statement_path)
        except OSError:
            pass
    return {"status": "AUTHENTICATED_BINDING_PASS", "key_id": binding["key_id"],
            "public_key_sha256": pinned_public_key_sha256,
            "statement_sha256": hashlib.sha256(canonical_bytes(statement)).hexdigest()}
