"""Project-isolated first trust root and real host principal bindings.

The Owner decision (2026-11-27, original task only) authorizes 小维ed43 to
custody the FIRST project trust root on the protected host. The private key is
never read, generated into, or printed by model context, chat, or this
repository: only the public key and its SHA256 fingerprint cross the boundary
as SecretRef-style metadata. Developer code verifies; it never self-signs.

An agent name inside plain JSON is not an authenticated principal. Every
developer/independent-reviewer/product-acceptance-ai binding must be a bounded
Ed25519 attestation that verifies against the pinned trust anchor, names the
single approved task, and is not expired. Expired attestations are never
reusable and permanent (open-ended) validity is never accepted.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from development_authority import canonical_bytes, load_public_key
from secure_file_input import read_owned_secret_file

KIND = 'HOST_PRINCIPAL_BINDING_V1'
CALLER_KIND = 'HOST_CALLER_CONTEXT_V1'
ALGORITHM = 'Ed25519'
ROLES = ('developer', 'independent-reviewer', 'product-acceptance-ai')
# Lease protocol rule (unchanged from the original contract semantics): the
# expiry is a finite future epoch; expired leases are never reusable and
# open-ended/permanent epochs are never accepted. The ACTUAL duration/renewal
# value comes from the approved original-task grant (decision
# caller.grant_or_lease_valid_until) and is enforced at handoff time; this
# module deliberately does not invent its own maximum term.
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}$')
BINDING_SIGNED_FIELDS = ('kind', 'role', 'subject', 'tenant_id', 'principal_id',
                         'task_id', 'trust_root_fingerprint', 'expires_at')
CALLER_SIGNED_FIELDS = ('kind', 'caller_id', 'run_id', 'session_id',
                        'gateway_id', 'task_id', 'trust_root_fingerprint',
                        'issued_at', 'expires_at')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def _epoch(value):
    return (isinstance(value, (int, float)) and value == value
            and abs(value) != float('inf'))


def fingerprint_of(public_key):
    der = public_key.public_bytes(serialization.Encoding.DER,
                                  serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def _checked_id(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('HOST_PRINCIPAL_%s_INVALID' % label)
    return value


def load_anchor(path):
    """Trust anchor is public material: regular file, exact fingerprint bound."""
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('ANCHOR_PUBLIC_KEY_REGULAR_FILE_REQUIRED')
    with open(path, 'rb') as stream:
        key = load_public_key(stream.read())
    return key, fingerprint_of(key)


def provision_trust_root(root_dir):
    """One-time first project trust root, executed by the lawful custodian.

    Refuses to overwrite or rotate: a second provisioning must be a separate
    Owner decision, not a silent re-run. Private key bytes stay in the 0600
    file in the caller-owned protected directory; only the public side and the
    fingerprint are returned.
    """
    if not isinstance(root_dir, str) or not os.path.isabs(root_dir):
        raise ValueError('TRUST_ROOT_ABSOLUTE_DIRECTORY_REQUIRED')
    info = os.lstat(root_dir)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError('UNSAFE_TRUST_ROOT_DIRECTORY')
    private = os.path.join(root_dir, 'project_trust_root.key.pem')
    public = os.path.join(root_dir, 'project_trust_root.pub.pem')
    fingerprint = os.path.join(root_dir, 'project_trust_root.fingerprint')
    if any(os.path.lexists(path) for path in (private, public, fingerprint)):
        raise ValueError('TRUST_ROOT_ALREADY_PROVISIONED')
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(private_pem)
    except Exception:
        os.unlink(private)
        raise
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)
    for path, payload in ((public, public_pem),
                          (fingerprint, (fingerprint_of(key.public_key()) + '\n').encode())):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
    return {'state': 'PROVISIONED', 'kind': 'PROJECT_TRUST_ROOT_V1',
            'algorithm': ALGORITHM, 'fingerprint': fingerprint_of(key.public_key()),
            'private_key_file': private, 'public_key_file': public,
            'private_key_exposed': False, 'custody_owner': 'designated project custodian (小维ed43)'}


def sign_principal_binding(private_key_file, role, subject, tenant_id,
                           principal_id, task_id, expires_at, now=None):
    """Custodian-side bounded attestation; key file never leaves the host."""
    if role not in ROLES:
        raise ValueError('HOST_PRINCIPAL_ROLE_NOT_APPROVED')
    now = time.time() if now is None else now
    if not _epoch(expires_at) or expires_at <= now:
        raise ValueError('HOST_PRINCIPAL_EXPIRY_REQUIRED')
    key_text = read_owned_secret_file(private_key_file, 'TRUST_ROOT_PRIVATE_KEY')
    key = serialization.load_pem_private_key(key_text.encode('ascii'), None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('ED25519_TRUST_ROOT_REQUIRED')
    anchor = key.public_key()
    body = {'kind': KIND, 'role': _checked_id(role, 'ROLE'),
            'subject': _checked_id(subject, 'SUBJECT'),
            'tenant_id': _checked_id(tenant_id, 'TENANT'),
            'principal_id': _checked_id(principal_id, 'PRINCIPAL'),
            'task_id': _checked_id(task_id, 'TASK'),
            'trust_root_fingerprint': fingerprint_of(anchor),
            'expires_at': float(expires_at)}
    signature = base64.b64encode(key.sign(canonical_bytes(body))).decode('ascii')
    return dict(body, signature=signature)


def verify_principal_binding(binding, anchor, anchor_fingerprint, task_id,
                             now=None):
    if not isinstance(binding, dict) or set(binding) != set(BINDING_SIGNED_FIELDS) | {'signature'}:
        raise ValueError('HOST_PRINCIPAL_BINDING_FIELDS_EXACT')
    now = time.time() if now is None else now
    if binding['kind'] != KIND or binding['role'] not in ROLES:
        raise ValueError('HOST_PRINCIPAL_ROLE_NOT_APPROVED')
    if binding['task_id'] != task_id:
        raise ValueError('HOST_PRINCIPAL_TASK_SCOPE_MISMATCH')
    if binding['trust_root_fingerprint'] != anchor_fingerprint:
        raise ValueError('HOST_PRINCIPAL_ANCHOR_MISMATCH')
    expires = binding['expires_at']
    if not _epoch(expires) or expires <= now:
        raise ValueError('HOST_PRINCIPAL_EXPIRY_INVALID')
    for name in ('subject', 'tenant_id', 'principal_id'):
        _checked_id(binding[name], name.upper())
    body = {name: binding[name] for name in BINDING_SIGNED_FIELDS}
    try:
        anchor.verify(base64.b64decode(binding['signature'], validate=True),
                      canonical_bytes(body))
    except Exception:
        raise ValueError('HOST_PRINCIPAL_ATTESTATION_INVALID')
    return dict(body, fingerprint=anchor_fingerprint)


def verify_caller_context(caller, anchor, anchor_fingerprint, task_id, now=None):
    """Caller approval arrives as a host-signed real-context attestation.

    Arbitrary caller strings in a JSON file are not facts: each caller quad is
    authenticated by the trusted host that maintains the task-scoped runtime
    context, and carries the actual lease/expiry protocol values.
    """
    if not isinstance(caller, dict) or set(caller) != set(CALLER_SIGNED_FIELDS) | {'signature'}:
        raise ValueError('HOST_CALLER_FIELDS_EXACT')
    now = time.time() if now is None else now
    if caller['kind'] != CALLER_KIND or caller['task_id'] != task_id:
        raise ValueError('HOST_CALLER_TASK_SCOPE_MISMATCH')
    if caller['trust_root_fingerprint'] != anchor_fingerprint:
        raise ValueError('HOST_CALLER_ANCHOR_MISMATCH')
    issued, expires = caller['issued_at'], caller['expires_at']
    for value in (issued, expires):
        if not _epoch(value):
            raise ValueError('HOST_CALLER_TIME_REQUIRED')
    # Expired lease reuse and permanent (open-ended) caller epochs are rejected;
    # the approved grant value bounds the actual duration at handoff time.
    if not issued <= now < expires:
        raise ValueError('HOST_CALLER_LEASE_INVALID')
    for name in ('caller_id', 'run_id', 'session_id', 'gateway_id'):
        _checked_id(caller[name], name)
    body = {name: caller[name] for name in CALLER_SIGNED_FIELDS}
    try:
        anchor.verify(base64.b64decode(caller['signature'], validate=True),
                      canonical_bytes(body))
    except Exception:
        raise ValueError('HOST_CALLER_ATTESTATION_INVALID')
    return dict(body, fingerprint=anchor_fingerprint)


def require_task_bindings(bindings, anchor, anchor_fingerprint, task_id, now=None):
    """Exact three approved posts, cryptographically distinct principals."""
    if not isinstance(bindings, dict) or set(bindings) != set(ROLES):
        raise ValueError('HOST_PRINCIPAL_POSTS_EXACT')
    verified = {role: verify_principal_binding(doc, anchor, anchor_fingerprint,
                                               task_id, now)
                for role, doc in bindings.items()}
    if len({value['subject'] for value in verified.values()}) != len(ROLES):
        raise ValueError('HOST_PRINCIPAL_SUBJECTS_DISTINCT')
    if len({value['principal_id'] for value in verified.values()}) != len(ROLES):
        raise ValueError('HOST_PRINCIPAL_PRINCIPALS_DISTINCT')
    return verified


def sign_caller_context(private_key_file, caller_id, run_id, session_id,
                        gateway_id, task_id, expires_at, issued_at=None,
                        now=None):
    """Custodian-side signed caller context for the approved task lease."""
    now = time.time() if now is None else now
    issued = now if issued_at is None else float(issued_at)
    if (not _epoch(expires_at) or not _epoch(issued)
            or not issued <= now < expires_at):
        raise ValueError('HOST_CALLER_LEASE_INVALID')
    key_text = read_owned_secret_file(private_key_file, 'TRUST_ROOT_PRIVATE_KEY')
    key = serialization.load_pem_private_key(key_text.encode('ascii'), None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('ED25519_TRUST_ROOT_REQUIRED')
    body = {'kind': CALLER_KIND, 'caller_id': _checked_id(caller_id, 'CALLER'),
            'run_id': _checked_id(run_id, 'RUN'), 'session_id': _checked_id(session_id, 'SESSION'),
            'gateway_id': _checked_id(gateway_id, 'GATEWAY'),
            'task_id': _checked_id(task_id, 'TASK'),
            'trust_root_fingerprint': fingerprint_of(key.public_key()),
            'issued_at': float(issued), 'expires_at': float(expires_at)}
    return dict(body, signature=base64.b64encode(
        key.sign(canonical_bytes(body))).decode('ascii'))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Project trust root and host attestations (custodian side)')
    sub = parser.add_subparsers(dest='cmd')
    p = sub.add_parser('provision-trust-root'); p.add_argument('--root-dir', required=True)
    a = sub.add_parser('attest-principal')
    a.add_argument('--private-key-file', required=True); a.add_argument('--role', required=True)
    a.add_argument('--subject', required=True); a.add_argument('--tenant-id', required=True)
    a.add_argument('--principal-id', required=True); a.add_argument('--task-id', required=True)
    a.add_argument('--expires-at', type=float, required=True)
    c = sub.add_parser('attest-caller')
    c.add_argument('--private-key-file', required=True); c.add_argument('--caller-id', required=True)
    c.add_argument('--run-id', required=True); c.add_argument('--session-id', required=True)
    c.add_argument('--gateway-id', required=True); c.add_argument('--task-id', required=True)
    c.add_argument('--issued-at', type=float, default=None); c.add_argument('--expires-at', type=float, required=True)
    v = sub.add_parser('verify'); v.add_argument('--anchor-public-key-file', required=True)
    v.add_argument('--task-id', required=True); v.add_argument('--binding-file', required=True)
    x = parser.parse_args(argv)
    try:
        if x.cmd == 'provision-trust-root':
            out = provision_trust_root(x.root_dir)
        elif x.cmd == 'attest-principal':
            out = sign_principal_binding(x.private_key_file, x.role, x.subject,
                                         x.tenant_id, x.principal_id, x.task_id, x.expires_at)
        elif x.cmd == 'attest-caller':
            out = sign_caller_context(x.private_key_file, x.caller_id, x.run_id,
                                      x.session_id, x.gateway_id, x.task_id,
                                      x.expires_at, x.issued_at)
        elif x.cmd == 'verify':
            anchor, fp = load_anchor(x.anchor_public_key_file)
            with open(x.binding_file, encoding='utf-8') as stream:
                value = json.load(stream)
            out = (require_task_bindings(value, anchor, fp, x.task_id)
                   if isinstance(value, dict) and set(value) == set(ROLES)
                   else verify_caller_context(value, anchor, fp, x.task_id))
        else:
            parser.error('a command is required')
        print(canonical(out))
        return 0
    except Exception as exc:
        code = str(exc)
        if not code or len(code) > 160 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in code):
            code = 'HOST_PRINCIPAL_REJECTED'
        sys.stderr.write(code + '\n')
        return 69


if __name__ == '__main__':
    raise SystemExit(main())
