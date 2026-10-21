"""Synthetic identities only; exercise actual Center transactions and HTTP."""
import base64
import copy
import hashlib
import http.client
import json
import threading
import os
import tempfile
import unittest
from http.server import HTTPServer
from unittest.mock import patch

from scripts.pr122_customer_core import Center, Denied, Conflict, canonical
from scripts.pr122_customer_http import App, COOKIE
from scripts.pr122_customer_identity import (Boundary, SCHEMA, MAPPING_SCHEMA, SUBJECT,
    EVIDENCE, CONSUME_PATH, import_mapping, signature, boundary_from_config)
from scripts.pr122_customer_ops import validate_runtime_contexts
from scripts.pr122_customer_providers import Providers
from tests import test_pr122_customer_center as fixtures


class IdentityTests(unittest.TestCase):
    imported = fixtures.CustomerTests.imported

    def setUp(self):
        fixtures.CustomerTests.setUp(self)
        self.service_key = b's' * 32
        self.trust = {'community-uk': {'key': self.service_key, 'audience': 'community',
                      'operations': {'community.access': ['OWNER', 'EDITOR', 'VIEWER']}}}
        self.boundary = Boundary(self.trust)
        self.proofs = {}
        self.mapping = {'schema': MAPPING_SCHEMA, 'mapping_id': 'map-a', 'version': 1,
                        'status': 'ACTIVE', 'user_id': self.owner, 'tenant_id': 'tenant-a',
                        'project_id': 'project-a', 'domestic_customer_id': 'domestic-a',
                        'confirmed_by': 'owner-authority', 'issued_unix': self.now,
                        'expires_unix': self.now + 1800}
        for field, kind in EVIDENCE.items():
            value = {'schema': 'PR122_IDENTITY_EVIDENCE_V1', 'kind': kind,
                     'confirmed_by': 'owner-authority', 'verified': True,
                     'expires_unix': self.now + 1800,
                     **{f: self.mapping[f] for f in SUBJECT}}
            raw = canonical(value); self.proofs[field] = raw
            self.mapping[field] = {'ref': field, 'sha256': hashlib.sha256(raw).hexdigest()}
        self.put(self.mapping)

    def put(self, mapping, **kwargs):
        document = {'payload': mapping, 'signature': signature(self.auth, MAPPING_SCHEMA, mapping)}
        return import_mapping(self.c, document, self.auth,
                              kwargs.get('confirmers', ['owner-authority']),
                              kwargs.get('evidence', self.proofs.__getitem__))

    def scope(self, **changes):
        return {'schema': SCHEMA, 'request_id': 'request-a', 'caller': 'community-uk',
                'audience': 'community', 'user_id': self.owner, 'tenant_id': 'tenant-a',
                'project_id': 'project-a', 'operation': 'community.access',
                'issued_unix': self.now, 'expires_unix': self.now + 30, **changes}

    def issue(self, **changes):
        user = self.users['owner']
        return self.boundary.issue(self.c, user['token'], user['csrf'], self.scope(**changes))

    def envelope(self, grant=None, **changes):
        value = dict(grant or self.issue()); value.pop('store_authorized')
        value.update(changes)
        return {'payload': value, 'signature': signature(self.service_key, CONSUME_PATH, value)}

    def test_exact_subject_and_signed_response_no_store_grant(self):
        result = self.boundary.consume(self.c, self.envelope())
        p = result['payload']
        self.assertEqual(p['user_id'], self.owner)
        self.assertEqual(p['domestic_customer_id'], 'domestic-a')
        self.assertEqual(p['mapping_version'], 1)
        self.assertFalse(p['store_authorized'])
        self.assertNotIn('authorization_token', p)
        self.assertEqual(result['signature'], signature(self.service_key, SCHEMA + ':response', p))
        self.assertNotEqual(result['signature'], signature(self.service_key, CONSUME_PATH, p))

    def test_missing_or_untrusted_confirmer_and_evidence_rejected(self):
        p = {**self.mapping, 'version': 2}
        for kwargs in ({'confirmers': []}, {'confirmers': ['other']}, {'evidence': None},
                       {'evidence': lambda ref: b'{}'}):
            with self.subTest(kwargs=list(kwargs)), self.assertRaises(Denied):self.put(p, **kwargs)
        self.assertEqual(self.c.db.execute('SELECT version FROM identity_mappings').fetchone()[0], 1)

    def test_wrong_evidence_subject_kind_verified_expiry_rejected(self):
        for field, changed in [('user_id', 'other'), ('kind', 'WRONG'), ('verified', 1),
                               ('expires_unix', self.now), ('confirmed_by', 'other')]:
            raw = json.loads(self.proofs['local_identity_evidence']);raw[field] = changed
            b = canonical(raw); p = copy.deepcopy(self.mapping); p['version'] = 2
            p['local_identity_evidence']['sha256'] = hashlib.sha256(b).hexdigest()
            with self.subTest(field=field), self.assertRaises(Denied):
                self.put(p, evidence=lambda ref: b if ref == 'local_identity_evidence' else self.proofs[ref])

    def test_mapping_signature_and_exact_schema(self):
        doc = {'payload': self.mapping, 'signature': '0' * 64}
        with self.assertRaises(Denied):import_mapping(self.c, doc, self.auth, ['owner-authority'], self.proofs.__getitem__)
        with self.assertRaises(Denied):self.put({**self.mapping, 'version': 2, 'email': 'same@example.com'})

    def test_mapping_old_version_bool_and_conflicting_id_rejected(self):
        with self.assertRaises(Conflict):self.put(self.mapping)
        with self.assertRaises(Denied):self.put({**self.mapping, 'version': True})
        with self.assertRaises(Denied):self.put({**self.mapping, 'mapping_id': 'map-b'})
        with self.assertRaises(Denied):self.put({**self.mapping, 'version': 2, 'domestic_customer_id': 'other'})

    def test_expired_mapping_and_boolean_times_rejected(self):
        for change in ({'expires_unix': self.now}, {'issued_unix': True},
                       {'expires_unix': self.now + 90000}):
            with self.subTest(change=change), self.assertRaises(Denied):self.put({**self.mapping, 'version': 2, **change})

    def test_mapping_revocation_persists_history_and_invalidates_grant(self):
        doc = self.envelope()
        self.put({**self.mapping, 'version': 2, 'status': 'REVOKED'})
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)
        with self.assertRaises(Denied):self.issue(request_id='new')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM identity_mapping_history').fetchone()[0], 2)

    def test_mapping_revoke_works_after_project_expiry(self):
        self.now += 3601
        p = {**self.mapping, 'version': 2, 'status': 'REVOKED',
             'issued_unix': self.now, 'expires_unix': self.now + 30}
        self.put(p)
        self.assertEqual(self.c.db.execute('SELECT status FROM identity_mappings').fetchone()[0], 'REVOKED')

    def test_missing_mapping_does_not_create_identity(self):
        self.c.db.execute('DELETE FROM identity_mappings')
        counts = [self.c.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('accounts', 'projects')]
        with self.assertRaises(Denied):self.issue()
        self.assertEqual(counts, [self.c.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('accounts', 'projects')])

    def test_scope_user_tenant_project_caller_audience_operation_rejected(self):
        for field, value in [('user_id', self.other), ('tenant_id', 'tenant-b'), ('project_id', 'project-b'),
                             ('caller', 'other'), ('audience', 'other'), ('operation', 'payment.refund')]:
            with self.subTest(field=field), self.assertRaises(Denied):self.issue(**{field: value})

    def test_request_time_bool_future_expiry_and_store_field_rejected(self):
        for changes in ({'expires_unix': self.now}, {'expires_unix': self.now + 31},
                        {'issued_unix': True}, {'issued_unix': self.now + 1}, {'store_id': 'all'}):
            with self.subTest(changes=changes), self.assertRaises(Denied):self.issue(**changes)

    def test_csrf_and_expired_session_rejected(self):
        with self.assertRaises(Denied):self.boundary.issue(self.c, self.users['owner']['token'], 'wrong', self.scope())
        self.c.db.execute('UPDATE sessions SET expires=?', (self.now,))
        with self.assertRaises(Denied):self.issue()

    def test_reset_and_logout_invalidate_previously_issued_grants(self):
        doc = self.envelope();self.c.logout(self.users['owner']['token'])
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)
        self.users['owner'] = self.c.login('owner@example.com', 'correct-password-123')
        doc = self.envelope(self.issue(request_id='reset'))
        self.c.request_reset('owner@example.com')
        r = self.c.db.execute("SELECT * FROM outbox WHERE kind='RESET' ORDER BY rowid DESC LIMIT 1").fetchone()
        token = json.loads(self.c.decrypt(r['payload'], 'outbox:' + r['id']))['token']
        self.c.reset(token, 'new-password-1234')
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)

    def test_member_revocation_and_regrant_never_revive_old_grant(self):
        invitation = self.c.invite(self.owner, 'project-a', 'member@example.com', 'EDITOR')['invitation']
        self.c.accept_invite(self.member, invitation)
        p = copy.deepcopy(self.mapping);p.update(mapping_id='map-member', user_id=self.member)
        proofs = {}
        for field, kind in EVIDENCE.items():
            value = json.loads(self.proofs[field]);value['user_id'] = self.member
            raw = canonical(value);proofs[field] = raw;p[field]['sha256'] = hashlib.sha256(raw).hexdigest()
        self.put(p, evidence=proofs.__getitem__)
        s = self.users['member'];scope = self.scope(user_id=self.member)
        grant = self.boundary.issue(self.c, s['token'], s['csrf'], scope);doc = self.envelope(grant)
        self.c.revoke(self.owner, 'project-a', self.member)
        invitation = self.c.invite(self.owner, 'project-a', 'member@example.com', 'EDITOR')['invitation']
        self.c.accept_invite(self.member, invitation)
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)

    def test_authority_refresh_invalidates_old_mapping_and_grant(self):
        doc = self.envelope();self.imported(2, [self.p])
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)
        with self.assertRaises(Denied):self.issue(request_id='new')

    def test_mapping_refresh_invalidates_prior_grant(self):
        doc = self.envelope();self.put({**self.mapping, 'version': 2})
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)
        self.assertEqual(self.boundary.consume(self.c, self.envelope(self.issue(request_id='new')))['payload']['mapping_version'], 2)

    def test_role_removed_or_not_in_policy_rejected(self):
        doc = self.envelope()
        self.c.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?", (self.owner,))
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)

    def test_one_use_request_and_grant_replay_rejected_after_reopen(self):
        doc = self.envelope()
        with self.assertRaises(Conflict):self.issue()
        self.boundary.consume(self.c, doc)
        c2 = Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now)
        self.addCleanup(c2.db.close)
        with self.assertRaises(Denied):self.boundary.consume(c2, doc)

    def test_wrong_mac_and_tampered_scope_rejected_without_consumption(self):
        doc = self.envelope();bad = copy.deepcopy(doc);bad['signature'] = '0' * 64
        with self.assertRaises(Denied):self.boundary.consume(self.c, bad)
        bad = self.envelope({**doc['payload'], 'store_authorized': False}, request_id='other')
        with self.assertRaises(Denied):self.boundary.consume(self.c, bad)
        self.boundary.consume(self.c, doc)

    def test_timeout_does_not_reissue_or_replay_consumed_request(self):
        doc = self.envelope();self.boundary.consume(self.c, doc)  # Simulated lost response, no external write.
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)
        with self.assertRaises(Conflict):self.issue()

    def test_expired_grant_and_mapping_rejected_at_consume(self):
        doc = self.envelope();self.now += 30
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)
        self.now -= 30;self.c.db.execute('UPDATE identity_mappings SET expires=?', (self.now,))
        with self.assertRaises(Denied):self.boundary.consume(self.c, doc)

    def test_audit_failure_rolls_back_mapping_issue_and_consume(self):
        with patch.object(self.c, 'audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):self.put({**self.mapping, 'version': 2})
            with self.assertRaises(RuntimeError):self.issue()
        self.assertEqual(self.c.db.execute('SELECT version FROM identity_mappings').fetchone()[0], 1)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM identity_grants').fetchone()[0], 0)
        doc = self.envelope()
        with patch.object(self.c, 'audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):self.boundary.consume(self.c, doc)
        self.assertEqual(self.c.db.execute('SELECT used FROM identity_grants').fetchone()[0], 0)
        self.boundary.consume(self.c, doc)

    def test_default_disabled_trust_and_key_separation(self):
        self.assertIsNone(boundary_from_config({}))
        raw = base64.b64encode(self.service_key).decode()
        cfg = {'identity_authorization': {'community-uk': {**self.trust['community-uk'], 'key': raw}}}
        self.assertIsInstance(boundary_from_config(cfg), Boundary)
        for field in ('authority_verify_key', 'backup_key'):
            with self.subTest(field=field), self.assertRaises(Denied):boundary_from_config({**cfg, field: raw})
        with self.assertRaises(Denied):boundary_from_config({**cfg, 'keys': {'v1': raw}})

    def test_runtime_binding_and_login_only_do_not_expand(self):
        cfg = {'keys': {'v1': base64.b64encode(self.key).decode()}, 'active_key': 'v1', 'providers': {}}
        item = {**self.trust['community-uk'], 'key': base64.b64encode(self.service_key).decode()}
        cfg['identity_authorization'] = {'community-uk': item}
        self.assertTrue(validate_runtime_contexts(cfg, cfg))
        with self.assertRaises(Denied):validate_runtime_contexts(cfg, {k:v for k,v in cfg.items() if k!='identity_authorization'})
        cfg.update(deployment_profile='OFFICIAL_LOGIN_ONLY_V1', providers={'smtp': {'configured': True}})
        with self.assertRaises(Denied):validate_runtime_contexts(cfg, cfg)

    def test_mapping_column_or_history_tamper_rejected(self):
        self.c.db.execute("UPDATE identity_mappings SET domestic_customer_id='tampered'")
        with self.assertRaises(Denied):self.issue()
        self.c.db.execute("UPDATE identity_mappings SET domestic_customer_id='domestic-a'")
        self.c.db.execute('DELETE FROM identity_mapping_history')
        with self.assertRaises(Denied):self.issue()

    def test_caller_keys_cannot_be_shared_between_identities(self):
        with self.assertRaises(Denied):Boundary({**self.trust, 'other-caller': self.trust['community-uk']})


class IdentityHTTPTests(IdentityTests):
    def setUp(self):
        super().setUp()
        def factory():return Center(self.root, {'v1': self.key}, 'v1', clock=lambda: self.now)
        self.app = App(factory, Providers({}), 'https://wenwenwenyiyiyi.work',
                       'deploy/pr122-customer-center/ui', identity_boundary=self.boundary)
        self.server = HTTPServer(('127.0.0.1', 0), self.app.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.addCleanup(self.finish)

    def finish(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self, path, body, authenticated=False, origin=True):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Host': 'wenwenwenyiyiyi.work', 'Content-Type': 'application/json'}
        if origin:headers['Origin'] = 'https://wenwenwenyiyiyi.work'
        if authenticated:
            headers.update(Cookie=COOKIE + '=' + self.users['owner']['token'])
            headers['X-CSRF-Token'] = self.users['owner']['csrf']
        conn.request('POST', '/customer/center/api/' + path, json.dumps(body), headers)
        response = conn.getresponse();raw = response.read();status = response.status;conn.close()
        return status, json.loads(raw)

    def test_browser_issue_service_consume_and_no_mapping_http(self):
        status, grant = self.request('authorization', self.scope(), True)
        self.assertEqual(status, 200)
        status, result = self.request('authorization/consume', self.envelope(grant), origin=False)
        self.assertEqual(status, 200);self.assertFalse(result['payload']['store_authorized'])
        self.assertEqual(self.request('import-identity-mapping', self.mapping, True)[0], 404)

    def test_http_auth_csrf_origin_default_trust_and_mac_rejected(self):
        self.assertEqual(self.request('authorization', self.scope())[0], 403)
        self.assertEqual(self.request('authorization', self.scope(), True, False)[0], 403)
        doc = self.envelope();doc['signature'] = '0' * 64
        self.assertEqual(self.request('authorization/consume', doc, origin=False)[0], 403)
        self.app.identity_boundary = None
        self.assertEqual(self.request('authorization', self.scope(request_id='new'), True)[0], 403)
        self.assertEqual(self.request('authorization/consume', doc, origin=False)[0], 403)

    def test_login_only_denies_both_identity_paths_before_db(self):
        self.app.deployment_profile = 'OFFICIAL_LOGIN_ONLY_V1'
        with patch.object(self.app, 'factory', side_effect=AssertionError('DB forbidden')):
            self.assertEqual(self.request('authorization', self.scope(), True)[0], 403)
            self.assertEqual(self.request('authorization/consume', {}, origin=False)[0], 403)


# Keep the HTTP collection limited to its own actual socket tests.
for _name in IdentityTests.__dict__:
    if _name.startswith('test_'):setattr(IdentityHTTPTests, _name, None)


class ProtectedInputTests(unittest.TestCase):
    def setUp(self):
        # This exact isolated suite runs as root in Hosted, like existing operator tests.
        self.assertEqual(os.geteuid(), 0)
        self.tmp = tempfile.TemporaryDirectory(prefix='pr122-identity-synthetic-', dir='/root')
        self.addCleanup(self.tmp.cleanup)
        from pathlib import Path
        self.path = Path(self.tmp.name) / 'proof.json'
        self.path.write_bytes(b'{"synthetic":true}')
        self.path.chmod(0o600)

    def test_root_private_bytes_are_read_bounded(self):
        from scripts.pr122_customer_identity import read_root_file
        self.assertEqual(read_root_file(str(self.path)), b'{"synthetic":true}')
        self.path.write_bytes(b'x' * 65537)
        with self.assertRaises(Denied):read_root_file(str(self.path))

    def test_public_mode_hardlink_and_symlink_rejected(self):
        from scripts.pr122_customer_identity import read_root_file
        self.path.chmod(0o644)
        with self.assertRaises(Denied):read_root_file(str(self.path))
        self.path.chmod(0o600)
        link = self.path.parent / 'link.json';os.link(self.path, link)
        with self.assertRaises(Denied):read_root_file(str(self.path))
        link.unlink();link.symlink_to(self.path)
        with self.assertRaises(OSError):read_root_file(str(link))

    def test_nonroot_and_parent_traversal_rejected(self):
        from scripts.pr122_customer_identity import read_root_file
        with patch('os.geteuid', return_value=1000), self.assertRaises(Denied):read_root_file(str(self.path))
        with self.assertRaises(Denied):read_root_file(str(self.path.parent) + '/../proof.json')

    def test_operator_loader_only_reads_fixed_evidence_namespace(self):
        from scripts.pr122_customer_identity import load_operator_mapping, EVIDENCE_ROOT
        document = {'payload': {'status': 'ACTIVE', **{f: {'ref': f, 'sha256': 'a'*64} for f in EVIDENCE}}}
        with patch('scripts.pr122_customer_identity.read_root_file', side_effect=[canonical(document), b'a', b'b', b'c']) as reader:
            _, proofs = load_operator_mapping(str(self.path))
            self.assertEqual(len(proofs), 3)
            self.assertEqual([call.args[0] for call in reader.call_args_list][1:],
                             [EVIDENCE_ROOT + '/' + f + '.json' for f in EVIDENCE])
        document['payload']['local_identity_evidence']['ref'] = '../secret'
        with patch('scripts.pr122_customer_identity.read_root_file', return_value=canonical(document)), self.assertRaises(Denied):
            load_operator_mapping(str(self.path))


if __name__ == '__main__':unittest.main()
