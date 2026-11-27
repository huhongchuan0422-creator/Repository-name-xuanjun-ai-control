"""Host trust root + provenance source against the real consumer, no fakes.

Synthetic fixture keys only. GuardedProvenanceConsumer, SessionStore and the
attestation verifiers are the shipped implementations; formal status here
never claims live principal registration for the real task.
"""
import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from host_principal_bindings import (ROLES, load_anchor, provision_trust_root,
                                     require_task_bindings,
                                     sign_principal_binding,
                                     verify_principal_binding)
from task_center_provenance_source import HostPrincipalMapper, HostProvenanceSource
from task_center_provenance_consumer import GuardedProvenanceConsumer
from task_center_session_auth import SessionStore

TASK = 'tc-real-development-20261123-4d99c26f2b07'
PRINCIPALS = {'developer': ('host-developer', 'developer-principal', 'dev', 'pw-dev'),
              'independent-reviewer': ('host-reviewer', 'reviewer-principal', 'rev', 'pw-rev'),
              'product-acceptance-ai': ('host-acceptance', 'acceptance-principal', 'acc', 'pw-acc')}


class TrustRootTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.dir = self.root / 'custody'
        self.dir.mkdir()
        self.dir.chmod(0o700)

    def test_first_trust_root_is_one_shot_and_public_only(self):
        receipt = provision_trust_root(str(self.dir))
        self.assertEqual(receipt['state'], 'PROVISIONED')
        self.assertFalse(receipt['private_key_exposed'])
        text = json.dumps(receipt)
        private_pem = Path(receipt['private_key_file']).read_bytes()
        self.assertNotIn('PRIVATE KEY', text)
        self.assertEqual(len(receipt['fingerprint']), 64)
        with self.assertRaises(ValueError) as caught:
            provision_trust_root(str(self.dir))
        self.assertEqual(str(caught.exception), 'TRUST_ROOT_ALREADY_PROVISIONED')
        self.assertEqual(Path(receipt['private_key_file']).read_bytes(), private_pem)
        import stat as stat_module
        self.assertFalse(self.dir.stat().st_mode & 0o077)
        self.assertEqual(stat_module.S_IMODE(
            Path(receipt['private_key_file']).stat().st_mode), 0o600)

    def test_unbound_world_writable_directory_is_refused(self):
        open_dir = self.root / 'open'
        open_dir.mkdir()
        open_dir.chmod(0o777)
        with self.assertRaises(ValueError) as caught:
            provision_trust_root(str(open_dir))
        self.assertEqual(str(caught.exception), 'UNSAFE_TRUST_ROOT_DIRECTORY')

    def test_attestation_rules_follow_the_original_lease_protocol(self):
        provision_trust_root(str(self.dir))
        private_file = str(self.dir / 'project_trust_root.key.pem')
        anchor, fingerprint = load_anchor(str(self.dir / 'project_trust_root.pub.pem'))
        doc = sign_principal_binding(private_file, 'developer', 'host-developer',
                                     'tenant-a', 'developer-principal', TASK,
                                     time.time() + 600)
        verified = verify_principal_binding(doc, anchor, fingerprint, TASK)
        self.assertEqual(verified['role'], 'developer')
        self.assertEqual(verified['trust_root_fingerprint'], fingerprint)
        # another task cannot reuse the attestation
        with self.assertRaises(ValueError) as caught:
            verify_principal_binding(doc, anchor, fingerprint, 'other-task')
        self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_TASK_SCOPE_MISMATCH')
        # unapproved role labels (installer/admin/model/agent names) are refused
        for role in ('repair-installer', 'TASK_CENTER_ADMIN', 'developer-agent'):
            with self.assertRaises(ValueError) as caught:
                sign_principal_binding(private_file, role, 'x', 'tenant-a', 'p', TASK,
                                       time.time() + 600)
            self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_ROLE_NOT_APPROVED')
        # only the finite-future-epoch rule is self-added: no permanent epoch,
        # no past lease reuse. Actual duration comes from the approved grant.
        for bad in (time.time() - 1, float('inf'), float('nan')):
            with self.assertRaises(ValueError) as caught:
                sign_principal_binding(private_file, 'developer', 'host-developer',
                                       'tenant-a', 'developer-principal', TASK, bad)
            self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_EXPIRY_REQUIRED')
        self.assertEqual(set(ROLES), set(PRINCIPALS))


class ProvenanceConsumerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.private = Ed25519PrivateKey.generate()
        self.private_file = self.root / 'trust_root.key.pem'
        self.private_file.write_bytes(self.private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        self.private_file.chmod(0o600)
        self.anchor_file = self.root / 'trust_root.pub.pem'
        self.anchor_file.write_bytes(self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        from host_principal_bindings import fingerprint_of
        self.fingerprint = fingerprint_of(self.private.public_key())
        self.config_file = self.root / 'provenance.json'
        self.session_path = str(self.root / 'sessions.sqlite')

        def connect():
            db = sqlite3.connect(self.session_path)
            db.row_factory = sqlite3.Row
            return db
        self.connect = connect
        self.write_config()

    def write_config(self, expires_offset=3600):
        principals = []
        for role, (subject, principal, username, password) in PRINCIPALS.items():
            doc = sign_principal_binding(str(self.private_file), role, subject,
                                         'tenant-a', principal, TASK,
                                         time.time() + expires_offset)
            principals.append({'username': username,
                'secret_sha256': hashlib.sha256(password.encode()).hexdigest(),
                'role': role, 'binding': doc})
        self.config_file.write_text(json.dumps({'kind': 'TC_HOST_PROVENANCE_CONFIG_V1',
            'tenant_id': 'tenant-a', 'task_id': TASK,
            'trust_root_fingerprint': self.fingerprint, 'principals': principals}))
        self.config_file.chmod(0o600)

    def build(self, clock=time.time):
        source = HostProvenanceSource(str(self.anchor_file), str(self.config_file), clock=clock)
        mapper = HostPrincipalMapper(source)
        sessions = SessionStore(self.connect, 'tenant-a', ttl_seconds=600, clock=clock)
        consumer = GuardedProvenanceConsumer(sessions, source, mapper, clock=clock)
        return source, mapper, sessions, consumer

    def test_signed_login_roles_come_from_the_attestation_not_the_request(self):
        source, mapper, sessions, consumer = self.build()
        identity, (token, csrf, expires) = consumer.guarded_login(sessions, 'dev', 'pw-dev')
        self.assertEqual(identity, {'tenant_id': 'tenant-a',
            'principal_id': 'developer-principal', 'roles': ['developer']})
        session = sessions.get(token)
        self.assertTrue(consumer.is_formal_session(session))
        self.assertEqual(session['roles'], ['developer'])
        # the reviewer post maps to its own signed role, never the developer's
        identity2, (token2, _, _) = consumer.guarded_login(sessions, 'rev', 'pw-rev')
        self.assertEqual(identity2['roles'], ['independent-reviewer'])
        # a request-side role list is never an identity fact
        with self.assertRaises(ValueError):
            mapper(dict({'source_ref': 'project-trust-root', 'subject': 'host-developer',
                    'incarnation': 'z' * 64, 'tenant_id': 'tenant-a',
                    'principal_id': 'developer-principal',
                    'source_version': 'HOST_PRINCIPAL_BINDING_V1',
                    'expires_at': time.time() + 60}, roles=['TASK_CENTER_ADMIN']))
        # unknown source_ref (plain JSON identity) is refused
        with self.assertRaises(ValueError):
            mapper({'source_ref': 'agent-name-json', 'subject': 'x', 'incarnation': 'y',
                    'tenant_id': 'tenant-a', 'principal_id': 'developer-principal',
                    'source_version': 'v', 'expires_at': time.time() + 60})

    def test_wrong_secret_and_plain_json_identity_are_refused(self):
        source, mapper, sessions, consumer = self.build()
        with self.assertRaisesRegex(ValueError, 'FORMAL_PROVENANCE_UNAVAILABLE'):
            consumer.guarded_login(sessions, 'dev', 'wrong-password')
        with self.assertRaisesRegex(ValueError, 'FORMAL_PROVENANCE_UNAVAILABLE'):
            consumer.guarded_login(sessions, 'unknown-agent', 'pw-dev')
        # agent-name JSON without any signature cannot even load the source
        config = json.loads(self.config_file.read_text())
        config['principals'][0]['binding'] = {'role': 'developer', 'subject': 'developer-agent',
            'tenant_id': 'tenant-a', 'principal_id': 'developer-principal',
            'task_id': TASK, 'expires_at': time.time() + 600}
        self.config_file.write_text(json.dumps(config))
        self.config_file.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'HOST_PRINCIPAL'):
            self.build()

    def test_rotation_drops_formal_status_immediately(self):
        source, mapper, sessions, consumer = self.build()
        identity, (token, _, _) = consumer.guarded_login(sessions, 'dev', 'pw-dev')
        self.assertTrue(consumer.is_formal_session(sessions.get(token)))
        # protected rotation changes the live host context identity
        self.write_config()
        self.assertFalse(consumer.is_formal_session(sessions.get(token)))

    def test_expired_binding_cannot_login(self):
        # signed as a valid finite future lease, then time passes: an expired
        # lease is never reusable (the signer itself refuses past epochs).
        self.write_config(expires_offset=1)
        time.sleep(1.2)
        with self.assertRaisesRegex(ValueError, 'HOST_PRINCIPAL_EXPIRY_INVALID'):
            self.build()

    def test_consumer_rejects_source_without_the_three_protocol_methods(self):
        source, mapper, sessions, consumer = self.build()

        class Partial(object):
            def verify_login(self, username, password):
                return None
        with self.assertRaises(ValueError) as caught:
            GuardedProvenanceConsumer(sessions, Partial(), mapper)
        self.assertEqual(str(caught.exception), 'FORMAL_PROVENANCE_UNAVAILABLE')
        with self.assertRaises(ValueError):
            GuardedProvenanceConsumer(sessions, source, None)


if __name__ == '__main__':
    unittest.main()
