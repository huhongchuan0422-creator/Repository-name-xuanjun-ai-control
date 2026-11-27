"""Modern TEST_ONLY -> project-isolated FORMAL handoff: real channels only.

All identities/keys here are synthetic fixtures for an isolated project root;
they are not live authority claims. The positive end-to-end proves the already
installed F4 assembly can register and claim the SAME task on the handoff
target; it is not a claim that the real task is RECEIVED.
"""
import base64
import copy
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import task_center_authority_handoff as handoff
from development_identity_adapter import TrustedRegistrationVerifier
from execution_policy_gateway import ExecutionPolicyGateway
from host_principal_bindings import (require_task_bindings, sign_caller_context,
                                     sign_principal_binding)
from model_orchestration import ModelControl
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_center_first_claim import FirstClaimAssembly
from task_center_mcp_claim import ClaimHost
from task_center_mcp_development import DevelopmentHost
from task_supervisor import Supervisor, canonical

KEY = b'0123456789abcdef0123454f89abcdef'
TASK = handoff.ORIGINAL_TASK_ID
SPEC = handoff.ORIGINAL_SPEC
CHECKPOINT = handoff.ORIGINAL_CHECKPOINT
FILES = ['scripts/development_entry_intake.py', 'tests/test_development_entry_intake.py']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class HandoffFixture(unittest.TestCase):
    def build_source(self, grant_history=False, resources=None):
        self.source = str(self.root / 'source.sqlite')
        s = Supervisor(self.source)  # no verifier -> TEST_ONLY, like the real ledger
        g = GatewayKernel(s, TestTenantAuthority(KEY))
        ctx = g.tenants.issue('tenant-a', 'admin:fixture')
        graph = demo_graph('tenant-a')
        graph['graph_id'] = 'tc-handoff-graph'
        graph['project_id'] = 'project-mcp'
        task = graph['tasks'][0]
        task.update(task_id=TASK, node_id='node-tc', stage='DEVELOPMENT',
                    owner='developer', entry='CHATGPT', checkpoint_sha256=CHECKPOINT,
                    spec_sha256=SPEC, board_id='acceptance-delivery',
                    resources=list(resources or ['fake:tc-1', 'fake:tc-2']), dependencies=[],
                    completion_evidence=[{'evidence_ref': 'evid-tc'}])
        graph['tasks'] = [task]
        g.register_graph(ctx, graph)
        control = ModelControl(g, ctx, Fernet.generate_key())
        control.create_role(dict(role_id='developer', version='v1', phase='EXECUTOR',
                                 capabilities=['code'], writer_allowed=True,
                                 enabled=True, review_kind=None))
        control.record_task_spec(TASK, 'deliver approved intake delta', FILES, ['tests'])
        policy = ExecutionPolicyGateway(g, ctx)
        policy.record_unit(dict(task_id=TASK, delivery_stage='implementation',
            feature_unit='claim', goal='deliver approved intake delta',
            scope=['WRITE_SOURCE'], acceptance=['tests'], dependencies=['NONE'],
            asset_version='v1', responsible_party='developer'))
        observed = {'matches': []}
        policy.record_asset_query(TASK, 'query', 'CANONICAL_DB', 'v1',
            {'lookup': {'asset_key': 'claim'}, 'observed_result': observed,
             'evidence_ref': 'canonical-db://claim@v1'},
            hashlib.sha256(canonical(observed).encode()).hexdigest())
        policy.record_dispatch_preflight(TASK, 'v1', ['query'], 'NOT_FOUND',
                                         'fixture host checked')
        if grant_history:
            s.db.execute('UPDATE tasks SET lease_id=? WHERE task_id=?',
                         ('lease-stale', TASK))
        s.db.commit()
        tables = {row[0] for row in s.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        s.close()
        self.source_tables = sorted(tables - handoff.DISALLOWED_CARRY)

    def add_task_rows(self, rows):
        """Append unrelated-task rows to the isolated synthetic source, shaped
        from the real ledger's residual grant rows (full history columns)."""
        db = sqlite3.connect(self.source)
        cols = [r[1] for r in db.execute('PRAGMA table_info(tasks)')]
        base = dict(zip(cols, db.execute('SELECT * FROM tasks').fetchone()))
        for task_id, patch in rows:
            row = dict(base, task_id=task_id, writer_scope='ws-' + task_id,
                       spec_sha256='d' * 64, checkpoint_sha256='c' * 64)
            row.update(patch)
            db.execute('INSERT INTO tasks (%s) VALUES(%s)' % (
                ','.join('"%s"' % c for c in cols),
                ','.join('?' * len(cols))), tuple(row[c] for c in cols))
        db.commit()
        db.close()

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
        self.anchor_file.chmod(0o600)
        self.anchor, self.fingerprint = handoff.load_anchor(str(self.anchor_file))
        self.trust_key = self.root / 'freeze.key'
        self.trust_key.write_bytes(b'f' * 48)
        self.trust_key.chmod(0o600)
        self.build_source()
        self._seq = 0

    def make_freeze(self, ttl=300):
        self._seq += 1
        tag = 'f%d' % self._seq
        self.backup = str(self.root / ('snapshot-%s.sqlite' % tag))
        self.freeze_path = str(self.root / ('freeze-%s.json' % tag))
        self.manifest_path = str(self.root / ('manifest-%s.json' % tag))
        return handoff.create_freeze(self.source, self.backup, 'op-1743',
                                     str(self.trust_key), self.freeze_path,
                                     self.manifest_path, ttl=ttl)

    def bindings(self, expires=None, now=None):
        roles = {'developer': ('host-developer', 'developer-principal'),
                 'independent-reviewer': ('host-reviewer', 'reviewer-principal'),
                 'product-acceptance-ai': ('host-acceptance', 'acceptance-principal')}
        return {role: sign_principal_binding(str(self.private_file), role,
                    subject, 'tenant-a', principal, TASK,
                    (time.time() + 3600) if expires is None else expires,
                    now=now)
                for role, (subject, principal) in roles.items()}

    def caller(self, expires=None):
        return sign_caller_context(str(self.private_file), 'tc-host-caller',
            'run-1743', 'session-1743', 'gateway-local', TASK,
            (time.time() + 1800) if expires is None else expires)

    def decision(self, carry=None, **overrides):
        value = {
            'kind': 'OWNER_INITIAL_AUTHORITY_DECISION_V1',
            'approval': {'decision': 'APPROVE',
                         'approval_ref': 'om_x100b7fa146d7fca4c06762aa1fcdd57',
                         'approved_at': time.time() - 60, 'decided_by': 'Owner'},
            'task_id': TASK, 'immutable_spec_sha256': SPEC,
            'checkpoint_sha256': CHECKPOINT, 'project_isolation_only': True,
            'scope': ['READ_SOURCE', 'WRITE_SOURCE', 'RUN_TEST'],
            'allowed_files': sorted(FILES),
            'initial_trust': {'existing_authorized_public_key_ref': self.fingerprint,
                              'or_authorize_first_project_root': None,
                              'named_signer_custodian': '小维ed43',
                              'canonical_owner_alias': 'developer',
                              'actual_owner_identity_ref': 'owner-msg-om_x100b7fa146d7fca4c06762aa1fcdd57'},
            'business_binding': {'developer_identity_ref': 'host-developer@' + self.fingerprint[:12],
                                 'qa_identity_and_key_ref': 'host-reviewer@' + self.fingerprint[:12],
                                 'security_identity_and_key_ref': 'host-acceptance@' + self.fingerprint[:12]},
            'caller': {'trusted_host_source_ref': 'project-python-host:caller-issuer',
                       'or_authorize_project_local_python_caller_issuer': True,
                       'grant_or_lease_valid_until': time.time() + 86400},
            'data_handoff': {'approve_source_preserving_same_task_handoff': True,
                             'implementation_owner': 'developer',
                             'execution_owner': '小维ed43', 'create_new_task': False,
                             'sql_profile_flip': False,
                             'promote_test_credentials_or_history': False,
                             'carry_over_tables': self.source_tables if carry is None else carry},
            'secrets_in_response': False, 'creates_grant_or_signature': False,
            'requires_author_installation_permission': False}
        for path, override in overrides.items():
            node = value
            keys = path.split('.')
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = override
        return value

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, sort_keys=True))
        path.chmod(0o600)
        return str(path)

    def do_handoff(self, target='formal.sqlite', operation='op-1743',
                   decision=None, bindings=None, caller=None):
        return handoff.handoff(self.source, self.backup, self.freeze_path,
            self.manifest_path, str(self.trust_key),
            decision_file=self.write_json('d-%s.json' % operation, decision or self.decision()),
            anchor_public_key_file=str(self.anchor_file),
            bindings_file=self.write_json('b-%s.json' % operation, bindings or self.bindings()),
            caller_file=self.write_json('c-%s.json' % operation, caller or self.caller()),
            target=str(self.root / target), operation_id=operation)

    def run_handoff(self, target='formal.sqlite', extra_rows=None, **kwargs):
        if extra_rows:
            self.add_task_rows(extra_rows)
        self.make_freeze()
        return self.do_handoff(target=target, **kwargs)

class HandoffTests(HandoffFixture):
    def test_freeze_pins_consistent_snapshot_and_before_manifest(self):
        source_sha = sha(self.source)
        body = self.make_freeze()
        self.assertEqual(body['profile'], 'TEST_ONLY')
        self.assertEqual(body['task_pins'], {'task_id': TASK, 'spec_sha256': SPEC,
            'checkpoint_sha256': CHECKPOINT, 'owner': 'developer', 'entry': 'CHATGPT',
            'state': 'READY'})
        self.assertEqual(body['effects']['writer_operations'], 0)
        self.assertEqual(body['effects']['resource_claims'], 0)
        manifest = json.loads(Path(self.manifest_path).read_text())
        self.assertEqual(manifest['tables']['tasks']['count'], 1)
        snapshot = sqlite3.connect('file:%s?mode=ro' % self.backup, uri=True)
        self.assertEqual(snapshot.execute(
            'SELECT profile FROM authority_runtime_profile').fetchone()[0], 'TEST_ONLY')
        snapshot.close()
        self.assertEqual(sha(self.source), source_sha)

    def test_formal_source_legacy_schema_and_drift_are_rejected(self):
        formal = str(self.root / 'other-formal.sqlite')
        Supervisor(formal, development_identity_verifier=TrustedRegistrationVerifier(
            self.private.public_key())).close()
        with self.assertRaises(ValueError) as caught:
            handoff.create_freeze(formal, str(self.root / 'b1'), 'op',
                                  str(self.trust_key), str(self.root / 'f1'), str(self.root / 'm1'))
        self.assertEqual(str(caught.exception), 'SOURCE_ALREADY_FORMAL_NO_HANDOFF_NEEDED')
        legacy = str(self.root / 'legacy.sqlite')
        sqlite3.connect(legacy).close()
        with self.assertRaises(ValueError) as caught:
            handoff.create_freeze(legacy, str(self.root / 'b2'), 'op',
                                  str(self.trust_key), str(self.root / 'f2'), str(self.root / 'm2'))
        self.assertEqual(str(caught.exception), 'EXPECTED_MODERN_SUPERVISOR_TEST_ONLY_SCHEMA')
        db = sqlite3.connect(self.source)
        db.execute('UPDATE tasks SET spec_sha256=? WHERE task_id=?', ('e' * 64, TASK))
        db.commit(); db.close()
        with self.assertRaises(ValueError) as caught:
            self.make_freeze()
        self.assertEqual(str(caught.exception), 'ORIGINAL_TASK_PIN_MISMATCH')

    def test_happy_path_receipt_and_query_reverification(self):
        source_sha = sha(self.source)
        receipt = self.run_handoff()
        self.assertEqual(receipt['state'], 'COMMITTED')
        self.assertEqual(receipt['profile'], 'FORMAL')
        self.assertEqual(receipt['promoted_authority'], 'NONE')
        self.assertEqual(receipt['first_registration'], 'REQUIRED_VIA_SIGNED_F4_REGISTER')
        self.assertEqual(receipt['task_id'], TASK)
        self.assertEqual(receipt['spec_sha256'], SPEC)
        self.assertEqual(receipt['checkpoint_sha256'], CHECKPOINT)
        self.assertEqual(receipt['trust_root_fingerprint'], self.fingerprint)
        target = str(self.root / 'formal.sqlite')
        db = sqlite3.connect('file:%s?mode=ro' % target, uri=True)
        self.assertEqual(db.execute(
            'SELECT profile FROM authority_runtime_profile').fetchone()[0], 'FORMAL')
        for table in ('events', 'writer_operations', 'resource_claims'):
            self.assertEqual(db.execute('SELECT count(*) FROM "%s"' % table).fetchone()[0], 0)
        self.assertEqual(db.execute(
            'SELECT count(*) FROM gateway_task_metadata').fetchone()[0], 1)
        self.assertEqual(db.execute(
            'SELECT count(*) FROM dispatch_preflights').fetchone()[0], 1)
        self.assertEqual(db.execute(
            'SELECT spec_sha256,checkpoint_sha256 FROM tasks WHERE task_id=?',
            (TASK,)).fetchone(), (SPEC, CHECKPOINT))
        db.close()
        self.assertEqual(sha(self.source), source_sha)
        self.assertEqual(handoff.query(target, 'op-1743'), receipt)
        again = self.do_handoff(operation='op-1743')
        self.assertEqual(again, receipt)
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(operation='op-other')
        self.assertEqual(str(caught.exception), 'TARGET_OCCUPIED_OR_INCOMPLETE')

    def test_tampered_snapshot_expired_freeze_and_changed_source_fail_closed(self):
        body = self.make_freeze(ttl=1)
        self.assertEqual(body['operation_id'], 'op-1743')
        time.sleep(2.1)
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='t1.sqlite')
        self.assertEqual(str(caught.exception), 'FREEZE_EXPIRED')
        self.make_freeze()
        db = sqlite3.connect(self.backup)
        db.execute('INSERT INTO supervisor_heartbeats VALUES(?,?,?,?,?)',
                   ('tamper', time.time(), 'x', 'y', time.time()))
        db.commit(); db.close()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='t2.sqlite')
        self.assertEqual(str(caught.exception), 'FREEZE_BACKUP_MISMATCH')
        self.make_freeze()
        db = sqlite3.connect(self.source)
        db.execute('INSERT INTO supervisor_heartbeats VALUES(?,?,?,?,?)',
                   ('drift', time.time(), 'x', 'y', time.time()))
        db.commit(); db.close()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='t3.sqlite')
        self.assertEqual(str(caught.exception), 'FREEZE_DATABASE_STATE_CHANGED')
        # manifest tampering
        self.make_freeze()
        manifest = json.loads(Path(self.manifest_path).read_text())
        manifest['tables']['tasks']['count'] = 99
        Path(self.manifest_path).write_text(json.dumps(manifest, sort_keys=True))
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='t4.sqlite')
        self.assertEqual(str(caught.exception), 'FREEZE_MANIFEST_MISMATCH')

    def test_unapproved_or_flipped_decisions_are_rejected(self):
        cases = {
            'approval': ({'decision': 'REJECT', 'approval_ref': None,
                          'approved_at': time.time(), 'decided_by': 'Owner'},
                         'OWNER_APPROVAL_FACT_REQUIRED'),
            'task_id': ('other-task', 'DECISION_TASK_PIN_MISMATCH'),
            'data_handoff.sql_profile_flip': (True, 'DECISION_HANDOFF_TERMS_INVALID'),
            'data_handoff.create_new_task': (True, 'DECISION_HANDOFF_TERMS_INVALID'),
            'data_handoff.promote_test_credentials_or_history': (
                True, 'DECISION_HANDOFF_TERMS_INVALID'),
            'project_isolation_only': (False, 'DECISION_SCOPE_NOT_PROJECT_ISOLATED'),
            'secrets_in_response': (True, 'DECISION_SCOPE_ESCAPED'),
            'initial_trust.existing_authorized_public_key_ref': (
                'dead' * 16, 'DECISION_ANCHOR_FINGERPRINT_MISMATCH'),
            'caller.grant_or_lease_valid_until': (
                time.time() - 1, 'DECISION_CALLER_HOST_OR_LEASE_UNBOUND'),
        }
        self.make_freeze()
        for index, (path, (override, code)) in enumerate(cases.items()):
            with self.assertRaises(ValueError) as caught:
                self.do_handoff(target='neg-%d.sqlite' % index,
                                decision=self.decision(**{path: override}))
            self.assertEqual(str(caught.exception), code, path)

    def test_authority_tables_cannot_be_carried_over(self):
        self.make_freeze()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='neg.sqlite',
                            decision=self.decision(carry=self.source_tables + ['events']))
        self.assertEqual(str(caught.exception), 'CARRY_OVER_TABLE_DENIED')
        self.make_freeze()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='neg2.sqlite',
                            decision=self.decision(carry=self.source_tables + ['no-such-table']))
        self.assertEqual(str(caught.exception), 'CARRY_OVER_TABLE_ABSENT_IN_SOURCE')

    def test_plain_json_agent_names_are_not_authenticated_principals(self):
        forged = {'developer': {'role': 'developer', 'subject': 'developer-agent',
                    'tenant_id': 'tenant-a', 'principal_id': 'developer',
                    'task_id': TASK, 'expires_at': time.time() + 600},
                  'independent-reviewer': self.bindings()['independent-reviewer'],
                  'product-acceptance-ai': self.bindings()['product-acceptance-ai']}
        with self.assertRaises(ValueError) as caught:
            require_task_bindings(forged, self.anchor, self.fingerprint, TASK)
        self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_BINDING_FIELDS_EXACT')
        documents = self.bindings()
        documents['developer']['signature'] = base64.b64encode(b'0' * 64).decode()
        with self.assertRaises(ValueError) as caught:
            require_task_bindings(documents, self.anchor, self.fingerprint, TASK)
        self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_ATTESTATION_INVALID')
        expired = self.bindings(expires=time.time() + 30)
        with self.assertRaises(ValueError) as caught:
            require_task_bindings(expired, self.anchor, self.fingerprint, TASK,
                                  now=time.time() + 60)
        self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_EXPIRY_INVALID')
        drifted = self.bindings()
        drifted['developer']['task_id'] = 'other-task'
        with self.assertRaises(ValueError) as caught:
            require_task_bindings(drifted, self.anchor, self.fingerprint, TASK)
        self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_TASK_SCOPE_MISMATCH')
        # two posts cannot share one subject
        twins = self.bindings()
        twins['independent-reviewer']['subject'] = twins['developer']['subject']
        twins['independent-reviewer'] = json.loads(json.dumps(twins['developer']))
        with self.assertRaises(ValueError) as caught:
            require_task_bindings(twins, self.anchor, self.fingerprint, TASK)
        self.assertEqual(str(caught.exception), 'HOST_PRINCIPAL_SUBJECTS_DISTINCT')

    def test_expired_and_over_grant_caller_is_rejected(self):
        self.make_freeze()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='neg-c1.sqlite',
                            caller=self.caller(expires=time.time() - 1))
        self.assertEqual(str(caught.exception), 'HOST_CALLER_LEASE_INVALID')
        self.make_freeze()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='neg-c2.sqlite',
                            caller=self.caller(expires=time.time() + 90000))
        self.assertEqual(str(caught.exception), 'CALLER_LEASE_EXCEEDS_APPROVED_GRANT')
        # principal attestations must also stay inside the real approved grant
        self.make_freeze()
        with self.assertRaises(ValueError) as caught:
            self.do_handoff(target='neg-c3.sqlite',
                            bindings=self.bindings(expires=time.time() + 90000))
        self.assertEqual(str(caught.exception), 'PRINCIPAL_LEASE_EXCEEDS_APPROVED_GRANT')

    def test_source_task_grant_history_blocks_carry_over(self):
        for suffix in ('', '-wal', '-shm'):
            path = self.source + suffix
            if os.path.lexists(path):
                os.unlink(path)
        self.build_source(grant_history=True)
        with self.assertRaises(ValueError) as caught:
            self.run_handoff(target='neg-grant-history.sqlite')
        self.assertEqual(str(caught.exception), 'SOURCE_TASK_GRANT_HISTORY_RECONCILIATION_REQUIRED')

    # Real-window residuals, un-neutralized shapes from the live ledger.
    UNRELATED_ROWS = (
        ('mcp-5801d831db422d9ecc3ec6da', dict(stage='DEVELOPMENT',
            state='RUNNING', owner='developer', entry='MCP',
            authority_state='VALID', lease_id='lease-mcp-attempt-1',
            attempt_id='attempt-mcp-1', started_at=1793105160.57)),
        ('tc-r5-20261123-1600', dict(stage='DEVELOPMENT', state='HOLD',
            owner='developer', entry='MCP',
            authority_state='REVOKED', lease_id='lease-r5-attempt-2',
            attempt_id='attempt-r5-2', started_at=1795420564.35)))

    def test_unrelated_live_or_unresolved_grant_still_blocks_carry(self):
        # BUG-3147C scope decision: the same-task invariant is pinned to the
        # target row plus zero promoted live grants. An unrelated task whose
        # grant is still VALID/REVOKING/UNKNOWN must be closed through the
        # original supervisor/fence revocation channel before the window;
        # neutralizing or deleting its row is not a legitimate pass.
        self.add_task_rows(self.UNRELATED_ROWS)
        for live_state in ('VALID', 'REVOKING', 'UNKNOWN'):
            db = sqlite3.connect(self.source)
            db.execute('UPDATE tasks SET authority_state=? WHERE task_id=?',
                       (live_state, 'mcp-5801d831db422d9ecc3ec6da'))
            db.commit()
            db.close()
            with self.assertRaises(ValueError) as caught:
                self.run_handoff(target='neg-live-%s.sqlite' % live_state)
            self.assertEqual(str(caught.exception),
                             'SOURCE_TASK_GRANT_HISTORY_RECONCILIATION_REQUIRED')

    def test_unrelated_terminal_grant_history_carries_verbatim(self):
        # Both real residual rows after the live one was legitimately closed:
        # full grant history (lease/attempt/started) preserved byte-identical
        # in the live carry AND in authority_handoff_provenance; the pinned
        # task stays grant-free; no VALID grant is promoted.
        self.add_task_rows(self.UNRELATED_ROWS)
        db = sqlite3.connect(self.source)
        db.execute("UPDATE tasks SET authority_state='REVOKED' WHERE task_id=?",
                   ('mcp-5801d831db422d9ecc3ec6da',))
        db.commit()
        db.close()
        receipt = self.run_handoff(target='terminal-carry.sqlite')
        self.assertEqual(receipt['state'], 'COMMITTED')
        target = str(self.root / 'terminal-carry.sqlite')
        db = sqlite3.connect('file:%s?mode=ro' % target, uri=True)
        self.assertEqual(db.execute(
            'SELECT authority_state,lease_id,attempt_id,started_at FROM tasks '
            'WHERE task_id=?', ('mcp-5801d831db422d9ecc3ec6da',)).fetchone(),
            ('REVOKED', 'lease-mcp-attempt-1', 'attempt-mcp-1', 1793105160.57))
        self.assertEqual(db.execute(
            'SELECT authority_state,lease_id,attempt_id,started_at FROM tasks '
            'WHERE task_id=?', ('tc-r5-20261123-1600',)).fetchone(),
            ('REVOKED', 'lease-r5-attempt-2', 'attempt-r5-2', 1795420564.35))
        self.assertEqual(db.execute(
            "SELECT count(*) FROM tasks WHERE authority_state='VALID'"
        ).fetchone()[0], 0)
        self.assertEqual(db.execute(
            'SELECT authority_state,lease_id,started_at FROM tasks '
            'WHERE task_id=?', (TASK,)).fetchone(), ('NONE', 'UNKNOWN', None))
        db.close()

    def test_failpoint_rollback_leaves_no_partial_authority(self):
        self.make_freeze()
        os.environ['XUANJUN_HANDOFF_FAIL_AT'] = 'before_commit'
        try:
            with self.assertRaises(RuntimeError):
                self.do_handoff(target='partial.sqlite')
        finally:
            del os.environ['XUANJUN_HANDOFF_FAIL_AT']
        db = sqlite3.connect(str(self.root / 'partial.sqlite'))
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        db.close()
        self.assertFalse({'authority_handoff_receipts', 'authority_handoff_provenance',
                          'gateway_task_metadata', 'execution_units'} & tables)
        # resume from the checkpoint: the custodian discards the unfinished
        # staging file (no authority artifact was ever committed) and retries.
        os.unlink(str(self.root / 'partial.sqlite'))
        self.make_freeze()
        receipt = self.do_handoff(target='resumed.sqlite')
        self.assertEqual(receipt['state'], 'COMMITTED')

    def test_provenance_tampering_breaks_query_invariants(self):
        self.run_handoff()
        target = str(self.root / 'formal.sqlite')
        db = sqlite3.connect(target)
        row = db.execute("SELECT seq FROM authority_handoff_provenance WHERE source_table='tasks' LIMIT 1").fetchone()
        db.execute('UPDATE authority_handoff_provenance SET row_json=? WHERE seq=?',
                   ('["forged"]', row[0]))
        db.commit(); db.close()
        with self.assertRaises(ValueError) as caught:
            handoff.query(target, 'op-1743')
        self.assertIn(str(caught.exception),
                      ('PROVENANCE_ROW_TAMPERED', 'PRESERVATION_INVARIANT_MISMATCH'))

    def test_switch_reconcile_rollback_and_isolation_detection(self):
        self.run_handoff()
        target = str(self.root / 'formal.sqlite')
        pointer = str(self.root / 'authority-reference.json')
        body = handoff.switch(pointer, str(self.trust_key), target, self.source, 'op-1743')
        self.assertTrue(body['single_authority_reference'])
        self.assertEqual(body['former_authority_view']['isolation'], 'ISOLATED_READ_ONLY')
        self.assertEqual(handoff.reconcile(pointer, str(self.trust_key))['state'], 'ISOLATED')
        self.assertEqual(handoff.switch(pointer, str(self.trust_key), target,
                       self.source, 'op-1743')['operation_id'], 'op-1743')
        with self.assertRaises(ValueError) as caught:
            handoff.switch(pointer, str(self.trust_key), target, self.source, 'op-other')
        # a switch without its own committed handoff receipt is refused before
        # any pointer mutation
        self.assertEqual(str(caught.exception), 'HANDOFF_RECEIPT_MISSING')
        db = sqlite3.connect(self.source)
        db.execute('INSERT INTO supervisor_heartbeats VALUES(?,?,?,?,?)',
                   ('after-switch', time.time(), 'x', 'y', time.time()))
        db.commit(); db.close()
        with self.assertRaises(ValueError) as caught:
            handoff.reconcile(pointer, str(self.trust_key))
        self.assertEqual(str(caught.exception), 'TEST_WRITE_AFTER_SWITCH_DETECTED')
        record = handoff.rollback(pointer, str(self.trust_key))
        self.assertFalse(record['data_destructive'])
        self.assertFalse(os.path.lexists(pointer))
        with self.assertRaises(ValueError):
            handoff.rollback(pointer, str(self.trust_key))


MODEL_PROVIDERS_DDL = '''CREATE TABLE IF NOT EXISTS model_providers(
  tenant_id TEXT NOT NULL,provider_id TEXT NOT NULL,
  display_name TEXT NOT NULL,adapter_type TEXT NOT NULL,
  base_url TEXT NOT NULL,enabled INTEGER NOT NULL,
  price_state TEXT NOT NULL,rate_limit_per_min INTEGER NOT NULL,
  concurrency_limit INTEGER NOT NULL,timeout_seconds REAL NOT NULL,
  retry_limit INTEGER NOT NULL,secret_cipher BLOB,secret_mask TEXT,
  config_version INTEGER NOT NULL,circuit_state TEXT NOT NULL,
  failure_count INTEGER NOT NULL,next_probe_at REAL,
  created_at REAL NOT NULL,updated_at REAL NOT NULL,
  PRIMARY KEY(tenant_id,provider_id))'''
SERVICE_CONNECTIONS_DDL = '''CREATE TABLE IF NOT EXISTS service_connections(
  tenant_id TEXT NOT NULL,connection_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,purpose TEXT NOT NULL,auth_type TEXT NOT NULL,
  destination_origin TEXT NOT NULL,issuer TEXT,
  authorization_endpoint TEXT,token_endpoint TEXT,revocation_endpoint TEXT,
  redirect_uri TEXT,client_id TEXT,scopes_json TEXT NOT NULL,
  supports_refresh INTEGER NOT NULL,status TEXT NOT NULL,
  config_version INTEGER NOT NULL,secret_cipher BLOB,secret_mask TEXT,
  refresh_cipher BLOB,access_expires_at REAL,refresh_lease TEXT,
  refresh_lease_until REAL,credential_generation INTEGER NOT NULL DEFAULT 0,
  connection_mutation_epoch INTEGER NOT NULL DEFAULT 0,
  stable_prior_status TEXT NOT NULL DEFAULT 'CONFIGURED',
  created_at REAL NOT NULL,updated_at REAL NOT NULL,
  PRIMARY KEY(tenant_id,connection_id))'''


class BlobSchemaDrillTests(HandoffFixture):
    """BUG-3147: real ledger has BLOB cells (secret_cipher 164B)."""

    def add_blob_tables(self):
        db = sqlite3.connect(self.source)
        db.execute(MODEL_PROVIDERS_DDL)
        db.execute(SERVICE_CONNECTIONS_DDL)
        self.blob = b'K' * 164
        db.execute('INSERT INTO model_providers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('tenant-a', 'p1', 'n', 'a', 'u', 1, 's', 10, 2, 30.5, 3,
             self.blob, '****', 1, 'CLOSED', 0, None, 1.0, 2.0))
        cols = [row[1] for row in db.execute('PRAGMA table_info(service_connections)')]
        values = {'tenant_id': 'tenant-a', 'connection_id': 'c1', 'provider_id': 'p1',
            'purpose': 'pp', 'auth_type': 'aa', 'destination_origin': 'o',
            'scopes_json': '[]', 'supports_refresh': 1, 'status': 'OK',
            'config_version': 1, 'secret_cipher': self.blob, 'secret_mask': '****',
            'refresh_cipher': self.blob, 'credential_generation': 0,
            'connection_mutation_epoch': 0, 'stable_prior_status': 'CONFIGURED',
            'created_at': 1.0, 'updated_at': 2.0}
        db.execute('INSERT INTO service_connections(%s) VALUES(%s)' % (
            ','.join(cols), ','.join('?' * len(cols))),
            [values.get(column) for column in cols])
        db.commit()
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        db.close()
        self.source_tables = sorted(tables - handoff.DISALLOWED_CARRY)

    def test_freeze_handles_blob_rows_deterministically_without_leaking_content(self):
        import base64
        self.add_blob_tables()
        body = self.make_freeze()
        manifest_text = Path(self.manifest_path).read_text()
        freeze_text = Path(self.freeze_path).read_text()
        self.assertNotIn('KKKK', manifest_text)
        self.assertNotIn('KKKK', freeze_text)
        self.assertNotIn(base64.b64encode(self.blob).decode(), manifest_text)
        self.assertNotIn(base64.b64encode(self.blob).decode(), freeze_text)
        # determinism: identical source -> identical manifest digest
        self.assertEqual(self.make_freeze()['manifest_digest'], body['manifest_digest'])
        # same-length byte mutation must change the digest (type-tag+length+sha256)
        db = sqlite3.connect(self.source)
        db.execute('UPDATE model_providers SET secret_cipher=? WHERE provider_id=?',
                   (b'J' * 164, 'p1'))
        db.commit(); db.close()
        self.assertNotEqual(self.make_freeze()['manifest_digest'], body['manifest_digest'])

    def test_type_tags_keep_null_text_int_float_blob_distinct(self):
        self.add_blob_tables()
        rows = [self.blob, None, 1, 1.0, '1']
        db = sqlite3.connect(self.source)
        db.execute('CREATE TABLE blob_type_probe(a BLOB,b,c,d,e)')
        db.execute('INSERT INTO blob_type_probe VALUES(?,?,?,?,?)', rows)
        db.commit()
        manifest = handoff.table_manifest(db)
        encoded = json.loads(handoff.encode_row(rows))
        db.close()
        self.assertEqual(encoded, [["b", 164, hashlib.sha256(self.blob).hexdigest()],
                                   ["n"], ["i", 1], ["f", 1.0], ["s", "1"]])
        self.assertTrue(manifest['blob_type_probe']['count'] >= 1)
        with self.assertRaises(ValueError) as caught:
            handoff.encode_cell(object())
        self.assertEqual(str(caught.exception), 'CELL_TYPE_UNSUPPORTED')

    def test_full_chain_with_blob_tables_carry_switch_reconcile_rollback(self):
        self.add_blob_tables()
        receipt = self.run_handoff()
        target = str(self.root / 'formal.sqlite')
        db = sqlite3.connect('file:%s?mode=ro' % target, uri=True)
        # live carry keeps exact ciphertext bytes for the formal ledger
        self.assertEqual(db.execute(
            'SELECT secret_cipher FROM model_providers').fetchone()[0], self.blob)
        # provenance/receipt never contain the ciphertext content
        leak = 0
        for (row_json,) in db.execute('SELECT row_json FROM authority_handoff_provenance'):
            if 'KKKK' in row_json:
                leak += 1
        db.close()
        self.assertEqual(leak, 0)
        self.assertEqual(handoff.query(target, 'op-1743'), receipt)
        pointer = str(self.root / 'authority-reference.json')
        handoff.switch(pointer, str(self.trust_key), target, self.source, 'op-1743')
        self.assertEqual(handoff.reconcile(pointer, str(self.trust_key))['state'], 'ISOLATED')
        self.assertFalse(handoff.rollback(pointer, str(self.trust_key))['data_destructive'])


class F4FormalClaimOnTargetTests(HandoffFixture):
    def assembly(self):
        contract = {'task_id': TASK, 'spec_sha256': SPEC, 'checkpoint_sha256': CHECKPOINT,
            'target_repository': 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control',
            'target_base_sha': 'b' * 40, 'entry': 'CHATGPT',
            'developer': {'issuer': 'native', 'subject': 'developer'},
            'allowed_files': FILES,
            'trusted_reviewers': [{'issuer': 'native', 'subject': 'reviewer-principal',
                                   'key_id': 'rv-1', 'role': 'QA'},
                                  {'issuer': 'native', 'subject': 'acceptance-principal',
                                   'key_id': 'pa-1', 'role': 'SECURITY'}]}
        digest = hashlib.sha256(json.dumps(contract, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        rows = [dict(tenant_id='tenant-a', principal_id='developer-principal',
            project_id='project-mcp', task_id=TASK, spec_sha256=SPEC,
            checkpoint_sha256=CHECKPOINT, contract_sha256=digest, role_id='developer',
            role_version='v1', phase='EXECUTOR', review_kind=None,
            authority_identity=contract['developer'],
            actions=['task_development_apply', 'task_development_status'],
            candidate_root=None, executor_profile=None)]
        for policy in contract['trusted_reviewers']:
            rows.append(dict(rows[0], principal_id=policy['subject'],
                role_id=policy['subject'], phase='REVIEWER',
                review_kind=policy['role'],
                authority_identity={key: policy[key] for key in ('issuer', 'subject')},
                actions=['task_development_review', 'task_development_status'],
                executor_profile=None))
        verifier = TrustedRegistrationVerifier(self.private.public_key())
        grant = {'issuer': 'owner-auth', 'subject': 'developer',
                 'developer': contract['developer'], 'contract_sha256': digest,
                 'valid_until': time.time() + 600}
        grant['signature'] = base64.b64encode(self.private.sign(
            json.dumps({key: grant[key] for key in grant if key != 'signature'},
                       sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False).encode())).decode()
        custody = {'owner_grant': grant,
                   'developer_credential': {'contract': contract,
                                            'developer_identity': contract['developer']},
                   'caller': {'caller_id': 'tc-host-caller', 'run_id': 'run-1743',
                              'session_id': 'session-1743', 'gateway_id': 'gateway-local'},
                   'lock_root': str(self.root / 'locks'), 'valid_until': time.time() + 500}
        claim_host = ClaimHost(rows, verifier, lambda identity, task_id: copy.deepcopy(custody))
        host = DevelopmentHost(rows, contract_provider=lambda task_id: dict(contract),
                               native_source_provider=lambda *a: None)
        host.claim_host = claim_host
        return FirstClaimAssembly(host)

    def test_repo_form_resource_registers_and_claims_RECEIVED_on_formal_target(self):
        # BUG-3147B end-to-end regression with the real canonical form: the
        # gateway metadata resource is the repo:<org>/<repo>:<name> reference
        # accepted by admission; register once + same-params claim once must
        # reach RECEIVED with the exact reference bound, no stand-in key.
        repo_ref = ('repo:huhongchuan0422-creator/'
                    'Repository-name-xuanjun-ai-control:development-entry')
        for suffix in ('', '-wal', '-shm'):
            path = self.source + suffix
            if os.path.lexists(path):
                os.unlink(path)
        self.build_source(resources=[repo_ref])
        source_sha = sha(self.source)
        target = str(self.root / 'formal-repo.sqlite')
        receipt = self.run_handoff(target='formal-repo.sqlite')
        assembly = self.assembly()
        registered = assembly.run(target, KEY, TASK, 'register')
        self.assertFalse(registered['duplicate'])
        self.assertFalse(registered['authority_created'])
        claimed = assembly.run(target, KEY, TASK, 'claim')
        self.assertEqual(claimed['state'], 'RECEIVED')
        self.assertFalse(claimed['execution_started'])
        db = sqlite3.connect('file:%s?mode=ro' % target, uri=True)
        self.assertEqual(
            [r[0] for r in db.execute(
                'SELECT DISTINCT resource_key FROM resource_claims')],
            [repo_ref])
        self.assertEqual(json.loads(db.execute(
            'SELECT resources_json FROM gateway_task_metadata WHERE task_id=?',
            (TASK,)).fetchone()[0]), [repo_ref])
        db.close()
        self.assertEqual(receipt['promoted_authority'], 'NONE')
        # same-params re-claim must not double-claim (concurrency intact)
        with self.assertRaises(ValueError):
            assembly.run(target, KEY, TASK, 'claim')
        self.assertEqual(sha(self.source), source_sha)

    def test_same_task_registers_and_claims_RECEIVED_on_formal_target(self):
        source_sha = sha(self.source)
        receipt = self.run_handoff()
        target = str(self.root / 'formal.sqlite')
        assembly = self.assembly()
        registered = assembly.run(target, KEY, TASK, 'register')
        self.assertFalse(registered['duplicate'])
        self.assertFalse(registered['browser_session_created'])
        claimed = assembly.run(target, KEY, TASK, 'claim')
        self.assertEqual(claimed['state'], 'RECEIVED')
        self.assertFalse(claimed['execution_started'])
        db = sqlite3.connect('file:%s?mode=ro' % target, uri=True)
        self.assertEqual(db.execute(
            "SELECT count(*) FROM events WHERE kind='DEVELOPMENT_CONTRACT'").fetchone()[0], 1)
        self.assertEqual(db.execute('SELECT count(*) FROM resource_claims').fetchone()[0], 2)
        db.close()
        self.assertEqual(sha(self.source), source_sha)
        with self.assertRaises(ValueError) as caught:
            assembly.run(self.source, KEY, TASK, 'register')
        self.assertEqual(str(caught.exception), 'AUTHORITY_RUNTIME_PROFILE_MISMATCH')
        self.assertEqual(receipt['promoted_authority'], 'NONE')


if __name__ == '__main__':
    unittest.main()
