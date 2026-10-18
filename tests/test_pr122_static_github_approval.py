"""Offline static GitHub dual-approval regressions.

Every API response is a local test double, config/ledger/source files live in a
TemporaryDirectory, and the existing static coordinator uses fake operations.
These tests are authorization evidence only, never target-host acceptance or
permission to publish, enroll trust, fetch credentials, or run production tools.
"""
import copy
import fcntl
import json
import io
import sys
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from types import SimpleNamespace
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import scripts
from scripts import pr122_customer_release as release
from scripts import pr122_customer_attempts as attempts
from scripts import pr122_customer_workflow as workflow
from scripts import pr122_static_github_approval as dual
from scripts import pr122_static_workflow as static
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_static_workflow as static_fixtures


MODE = 'STATIC_GITHUB_DUAL_APPROVAL'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REPO_ID = 1413132159
OWNER_ID = 332398908
REVIEWER_ID = 95597695
NOW = 1792335600
REAL_GITHUB = release.github
INSTALL_PREFIX = 'XUANJUN_STATIC_INSTALL_V1\n'
REVIEW_PREFIX = 'XUANJUN_STATIC_GITHUB_REVIEW_V1\n'


class _DualFixture:
    """Reuse the original static stage/source fixture without inheriting tests."""
    inventory = static_fixtures.StaticTests.inventory
    patches = static_fixtures.StaticTests.patches
    fake_run = static_fixtures.StaticTests.fake_run
    bind_contract = static_fixtures.StaticTests.bind_contract

    def setUp(self):
        clock = patch('time.time', return_value=NOW)
        clock.start(); self.addCleanup(clock.stop)
        static_fixtures.StaticTests.setUp(self)
        # Reuse the actual protected reader and its strict bounded fd parser.
        # Only ownership is adapted for these sandbox-owned temporary files.
        real_fstat = os.fstat
        def fixture_private(path):
            def sandbox_owner(fd):
                values = list(real_fstat(fd)); values[4] = 0
                return os.stat_result(values)
            with patch.object(attempts.os, 'fstat', side_effect=sandbox_owner):
                return self.real_read(path)
        reader = patch.object(attempts, 'read_private', side_effect=fixture_private)
        reader.start(); self.addCleanup(reader.stop)
        self.plan = self.base
        self.trust = {
            'schema': 1, 'authorization_mode': MODE,
            'repository_id': REPO_ID, 'repository_full_name': REPO,
            'owner_id': OWNER_ID, 'reviewer_id': REVIEWER_ID,
            'source_writer_id': OWNER_ID, 'revoked_review_ids': [],
            'install_anchors': {},
        }
        self.plan.update(
            authorization_mode=MODE, github_authority_sha256=dual.trust_digest(self.trust),
            source_tree='b' * 40, artifact_tar_sha256='d' * 64,
            artifact_zip_sha256='e' * 64, artifact_id=7, ci_run_id=6,
            scope_sha256='f' * 64,
        )
        common_names = (
            'authorization_mode', 'transaction', 'github_authority_sha256',
            'deployment_profile', 'source_commit', 'source_tree', 'manifest_sha256',
            'artifact_tar_sha256', 'artifact_zip_sha256', 'artifact_id', 'ci_run_id',
            'scope_sha256', 'static_baseline_sha256', 'host_pins_sha256',
            'permit_window_seconds',
        )
        common = {key: self.plan[key] for key in common_names}
        common.update(
            plan_sha256=digest(canonical(self.plan)), attempt_policy=static.POLICY,
            workflow_contract_sha256=digest(canonical(self.plan['workflow_contract'])),
            max_executions=5, issued_unix=NOW - 1, expires_unix=NOW + 17999,
        )
        self.approval = dict(common, decision='INSTALL_APPROVED', rollback_approved=True,
                             review_comment_id=5, review_body_sha256='0' * 64)
        self.review = dict(common, decision='AUDIT_PASS', owner_id=OWNER_ID,
                           reviewer_id=REVIEWER_ID, source_writer_id=OWNER_ID,
                           findings={key: {'state': 'CLOSED', 'evidence_sha256': ['b' * 64]}
                                     for key in ('R1', 'R2', 'R3')})
        self.comments = {
            4: self.comment(4, OWNER_ID, release.OWNER),
            5: self.comment(5, REVIEWER_ID, 'independent-reviewer'),
        }
        repo_identity = {'id': REPO_ID, 'full_name': REPO}
        self.responses = {
            '': dict(repo_identity, owner={'id': OWNER_ID, 'login': release.OWNER}),
            'git/commits/' + self.plan['source_commit']: {
                'sha': self.plan['source_commit'], 'tree': {'sha': self.plan['source_tree']}},
            'actions/artifacts/7': {
                'id': 7, 'expired': False, 'digest': 'sha256:' + self.plan['artifact_zip_sha256'],
                'workflow_run': {'id': 6, 'head_sha': self.plan['source_commit']}},
            'actions/runs/6': {
                'id': 6, 'status': 'completed', 'conclusion': 'success',
                'head_sha': self.plan['source_commit'],
                'path': '.github/workflows/pr122-unified-release-review.yml', 'event': 'push',
                'repository': copy.deepcopy(repo_identity),
                'head_repository': copy.deepcopy(repo_identity)},
        }
        self.config = release.CONFIG / 'STATIC_GITHUB_DUAL_APPROVAL.json'
        self.fetched = []
        self.events = []
        self.prepare()
        mocked_fetch = patch.object(release, 'github', side_effect=self.fetch)
        self.github = mocked_fetch.start(); self.addCleanup(mocked_fetch.stop)

    def comment(self, number, user_id, login):
        return {'id': number, 'user': {'id': user_id, 'login': login, 'type': 'User'},
                'issue_url': 'https://api.github.com/repos/' + REPO + '/issues/122',
                'body': ''}

    def save_trust(self):
        self.config.write_bytes(canonical(self.trust)); self.config.chmod(0o600)

    def anchor(self):
        self.trust['install_anchors'][release.TXN] = {
            'install_comment_id': 4, 'install_body_sha256': digest(self.comments[4]['body'].encode()),
            'review_comment_id': 5, 'review_body_sha256': digest(self.comments[5]['body'].encode()),
        }
        self.save_trust()

    def prepare(self):
        self.comments[5]['body'] = REVIEW_PREFIX + canonical(self.review).decode()
        self.approval['review_body_sha256'] = digest(self.comments[5]['body'].encode())
        self.comments[4]['body'] = INSTALL_PREFIX + canonical(self.approval).decode()
        self.anchor()

    def fetch(self, path):
        self.fetched.append(path)
        if path.startswith('issues/comments/'):
            response = self.comments[int(path.rsplit('/', 1)[1])]
        else:
            response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)

    def gate(self, comment_id=4):
        return dual.gate(comment_id, self.plan, release.TXN)

    def assert_hold(self):
        with self.assertRaisesRegex(Denied, '^HOLD:'):
            self.gate()

    def configure_static_authority(self):
        # Exercise the real public authority.gate and _gate, while the original
        # host-reader dependency is an explicitly local, temporary fixture.
        self.pins = {
            'package_schema': 'FULL_STATIC_REVIEW_V1',
            'static_artifact_sha256': self.plan['artifact_tar_sha256'],
            'previous_release': str(self.b / 'previous-static'),
            'previous_receipt_sha256': '1' * 64,
            'previous_manifest_sha256': '2' * 64,
            'nginx': {str(self.b / 'fixture-nginx.conf'): '3' * 64},
        }
        self.pins_path = self.b / 'HOST_PINS.json'
        self.pins_path.write_bytes(canonical(self.pins))
        baseline = {key: self.pins[key] for key in ('previous_release',
                    'previous_receipt_sha256', 'previous_manifest_sha256', 'nginx')}
        self.plan['host_pins_sha256'] = digest(self.pins_path.read_bytes())
        self.plan['static_baseline_sha256'] = digest(canonical(baseline))
        for payload in (self.approval, self.review):
            payload.update(host_pins_sha256=self.plan['host_pins_sha256'],
                           static_baseline_sha256=self.plan['static_baseline_sha256'],
                           plan_sha256=digest(canonical(self.plan)))
        self.review['findings']['R3']['evidence_sha256'] = [self.plan['static_baseline_sha256']]
        self.prepare()
        def read_pins(path):
            self.assertEqual(path, self.pins_path)
            return self.pins_path.read_bytes()
        original = SimpleNamespace(PINS=self.pins_path,
                                   c=SimpleNamespace(read=Mock(side_effect=read_pins)))
        for adapter in (patch.object(scripts, 'pr122_site_hub_unified_release', original, create=True),
                        patch.dict(sys.modules, {'scripts.pr122_site_hub_unified_release': original})):
            adapter.start(); self.addCleanup(adapter.stop)
        self.authority = static.StaticAuthority.__new__(static.StaticAuthority)
        self.authority.tx = SimpleNamespace(id=release.TXN, pins=self.pins)
        self.authority.folder = self.source
        self.authority.STATE, self.authority.LOCK = release.STATE, release.LOCK
        self.authority.TXN, self.authority.atomic_json = release.TXN, release.atomic_json
        self.authority.authorization_mode, self.authority._dual_plan = None, None
        # Source closure has its own original tests; here the existing temporary
        # source verifier remains real, while no root release helper is imported.
        self.authority.source = release.source

    def reset_payloads(self, approval, review):
        self.approval = copy.deepcopy(approval)
        self.review = copy.deepcopy(review)
        self.prepare()


class StaticGithubApprovalTests(_DualFixture, unittest.TestCase):
    def test_exact_fixed_numeric_dual_approval_and_fresh_api_objects_pass(self):
        self.assertEqual(self.gate(), self.approval)
        expected = {'', 'issues/comments/4', 'issues/comments/5',
                    'git/commits/' + self.plan['source_commit'],
                    'actions/artifacts/7', 'actions/runs/6'}
        self.assertEqual(set(self.fetched), expected)
        first_count = len(self.fetched)
        self.assertEqual(self.gate(), self.approval)
        self.assertEqual(set(self.fetched[first_count:]), expected)

    def test_verify_returns_exact_review_with_no_signature_or_role_assertion(self):
        self.assertEqual(dual.verify(self.comments[5], self.comments[4], self.approval,
                                     self.plan, self.trust, self.fetch), self.review)
        self.assertNotIn('signature', self.review)
        self.assertNotIn('reviewer_role', self.review)

    def test_display_login_rename_cannot_replace_numeric_identity(self):
        self.comments[4]['user']['login'] = 'renamed-owner'
        self.comments[5]['user']['login'] = 'renamed-reviewer'
        self.assertEqual(self.gate(), self.approval)
        self.comments[5]['user'] = {'id': OWNER_ID, 'login': 'independent-reviewer'}
        self.assert_hold()

    def test_strict_json_rejects_duplicates_nonfinite_and_nonobject_roots(self):
        for raw in (b'{"decision":1,"decision":1}', b'{"a":{"x":1,"x":2}}',
                    b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b'{"a":1e999}',
                    b'[]', b'null', b'"value"', b'42', b'{bad', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(Denied):
                dual.strict_json(raw)
        self.assertEqual(dual.strict_json(b'{"ordinary":1}'), {'ordinary': 1})

    def test_strict_comment_parsing_even_when_malformed_bytes_are_anchored(self):
        originals = copy.deepcopy(self.comments)
        for number in (4, 5):
            for raw in ('{"decision":"AUDIT_PASS","decision":"AUDIT_PASS"}',
                        '{"unknown":NaN}', '[]'):
                with self.subTest(number=number, raw=raw):
                    self.comments = copy.deepcopy(originals)
                    prefix = INSTALL_PREFIX if number == 4 else REVIEW_PREFIX
                    self.comments[number]['body'] = prefix + raw
                    if number == 5:
                        self.approval['review_body_sha256'] = digest(self.comments[5]['body'].encode())
                        self.comments[4]['body'] = INSTALL_PREFIX + canonical(self.approval).decode()
                    self.anchor()
                    self.assert_hold()

    def test_unknown_or_missing_comment_fields_fail_closed(self):
        approval, review = copy.deepcopy(self.approval), copy.deepcopy(self.review)
        for who in ('approval', 'review'):
            for key, operation in (('unexpected', 'add'), ('authorization_mode', 'remove'),
                                   ('github_authority_sha256', 'remove')):
                with self.subTest(who=who, key=key, operation=operation):
                    self.reset_payloads(approval, review)
                    payload = getattr(self, who)
                    if operation == 'add': payload[key] = True
                    else: del payload[key]
                    self.prepare(); self.assert_hold()

    def test_protected_config_exact_schema_and_fixed_numeric_identities(self):
        original = copy.deepcopy(self.trust)
        changes = [('unexpected', True), ('schema', True), ('schema', 2),
                   ('authorization_mode', 'LEGACY'), ('repository_id', REPO_ID + 1),
                   ('repository_id', True), ('repository_id', str(REPO_ID)),
                   ('repository_full_name', 'attacker/repository'),
                   ('owner_id', OWNER_ID + 1), ('owner_id', True),
                   ('reviewer_id', OWNER_ID), ('reviewer_id', True),
                   ('source_writer_id', REVIEWER_ID), ('source_writer_id', True),
                   ('revoked_review_ids', [5, 5]), ('revoked_review_ids', [True]),
                   ('revoked_review_ids', [-1]), ('install_anchors', [])]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.trust = copy.deepcopy(original); self.trust[key] = value
                self.save_trust(); self.assert_hold()

    def test_protected_config_duplicate_keys_and_nan_are_rejected(self):
        valid = self.config.read_bytes()
        for suffix in (b',"schema":1}', b',"extra":NaN}'):
            self.config.write_bytes(valid[:-1] + suffix)
            with self.subTest(suffix=suffix): self.assert_hold()

    def test_config_missing_or_private_read_failure_has_no_legacy_fallback(self):
        self.config.unlink()
        self.assert_hold()
        self.save_trust()
        with patch.object(attempts, 'read_private', side_effect=OSError('fixture access denied')):
            self.assert_hold()

    def test_install_anchors_are_exact_strict_and_not_part_of_trust_digest(self):
        original = copy.deepcopy(self.trust)
        before = dual.trust_digest(original)
        anchor = original['install_anchors'][release.TXN]
        moved = copy.deepcopy(original)
        moved['install_anchors'][release.TXN]['install_comment_id'] = 40
        self.assertEqual(dual.trust_digest(moved), before)
        for key, value in [('install_comment_id', True), ('install_comment_id', 40),
                           ('review_comment_id', True), ('review_comment_id', 4),
                           ('install_body_sha256', 'f' * 64),
                           ('review_body_sha256', 'f' * 64), ('unexpected', True)]:
            with self.subTest(key=key, value=value):
                self.trust = copy.deepcopy(original)
                self.trust['install_anchors'][release.TXN][key] = value
                self.save_trust(); self.assert_hold()
        self.assertEqual(set(anchor), {'install_comment_id', 'install_body_sha256',
                                      'review_comment_id', 'review_body_sha256'})

    def test_live_repository_id_name_and_owner_are_all_required(self):
        original = copy.deepcopy(self.responses[''])
        for key, value in [('id', True), ('id', REPO_ID + 1),
                           ('full_name', 'attacker/Repository-name-xuanjun-ai-control'),
                           ('owner', {'id': REVIEWER_ID}), ('owner', {'id': True})]:
            with self.subTest(key=key, value=value):
                self.responses[''] = dict(original, **{key: value}); self.assert_hold()

    def test_comment_origin_must_be_exact_fixed_repository_issue_and_numeric_ids(self):
        original = copy.deepcopy(self.comments)
        for number in (4, 5):
            cases = [
                ('id', True), ('id', str(number)), ('id', number + 10),
                ('user', {'id': True, 'login': release.OWNER, 'type': 'User'}),
                ('user', {'id': OWNER_ID if number == 4 else REVIEWER_ID, 'type': 'Bot'}),
                ('user', {'id': OWNER_ID if number == 4 else REVIEWER_ID}),
                ('user', {'id': str(OWNER_ID if number == 4 else REVIEWER_ID)}),
                ('user', {'id': REVIEWER_ID if number == 4 else OWNER_ID}),
                ('issue_url', 'https://api.github.com/repos/attacker/repo/issues/122'),
                ('issue_url', 'http://api.github.com/repos/' + REPO + '/issues/122'),
                ('issue_url', 'https://api.github.com/repos/' + REPO + '/issues/123'),
                ('issue_url', 'https://api.github.com/repos/' + REPO + '/issues/122?x=1'),
            ]
            for key, value in cases:
                with self.subTest(number=number, key=key, value=value):
                    self.comments = copy.deepcopy(original)
                    self.comments[number][key] = value; self.assert_hold()
        for value in (True, False, 0, -1, '4', 4.0):
            with self.subTest(requested_comment=value), self.assertRaises(Denied):
                self.gate(value)

    def test_common_exact_plan_source_tree_host_contract_and_artifact_bindings(self):
        approval, review = copy.deepcopy(self.approval), copy.deepcopy(self.review)
        changes = {
            'authorization_mode': 'ED25519', 'transaction': 'pr122-other',
            'plan_sha256': '0' * 64, 'github_authority_sha256': '0' * 64,
            'deployment_profile': 'CUSTOMER_LOGIN_ONLY_V1', 'attempt_policy': workflow.POLICY,
            'workflow_contract_sha256': '0' * 64, 'source_commit': '0' * 40,
            'source_tree': '0' * 40, 'manifest_sha256': '0' * 64,
            'artifact_tar_sha256': '0' * 64, 'artifact_zip_sha256': '0' * 64,
            'artifact_id': 8, 'ci_run_id': 8, 'scope_sha256': '0' * 64,
            'static_baseline_sha256': '0' * 64, 'host_pins_sha256': '0' * 64,
        }
        for who in ('approval', 'review'):
            for key, value in changes.items():
                with self.subTest(who=who, key=key):
                    self.reset_payloads(approval, review)
                    getattr(self, who)[key] = value; self.prepare(); self.assert_hold()

    def test_plan_mutation_is_bound_including_additional_plan_inputs(self):
        original = copy.deepcopy(self.plan)
        for mutation in ('source_tree', 'host_pins_sha256', 'static_baseline_sha256',
                         'workflow_contract', 'additional_input'):
            with self.subTest(mutation=mutation):
                self.plan = copy.deepcopy(original)
                if mutation == 'workflow_contract':
                    self.plan[mutation]['stages'][0]['input_sha256'] = '0' * 64
                else: self.plan[mutation] = '0' * (40 if mutation == 'source_tree' else 64)
                self.assert_hold()

    def test_gate_rejects_reanchored_nonstatic_stage_contract_and_policy(self):
        original = copy.deepcopy(self.plan)
        for mutation in ('reordered', 'injected', 'recovery'):
            with self.subTest(mutation=mutation):
                self.plan = copy.deepcopy(original)
                rows = self.plan['workflow_contract']['stages']
                if mutation == 'reordered': rows.reverse()
                elif mutation == 'injected': rows[0]['stage'] = 'SHELL'
                else: rows[0]['recovery_actions'] = ['ARBITRARY_COMMAND']
                for payload in (self.approval, self.review):
                    payload['plan_sha256'] = digest(canonical(self.plan))
                    payload['workflow_contract_sha256'] = digest(canonical(self.plan['workflow_contract']))
                self.prepare(); self.assert_hold()

    def test_comment_numeric_fields_are_strict_integers_not_bools_or_floats(self):
        approval, review = copy.deepcopy(self.approval), copy.deepcopy(self.review)
        for who in ('approval', 'review'):
            for key in ('ci_run_id', 'artifact_id', 'issued_unix', 'expires_unix',
                        'permit_window_seconds', 'max_executions'):
                for value in (True, str(approval[key]), float(approval[key])):
                    with self.subTest(who=who, key=key, value=value):
                        self.reset_payloads(approval, review)
                        getattr(self, who)[key] = value; self.prepare(); self.assert_hold()

    def test_exact_five_hour_window_and_exact_five_attempt_limit(self):
        approval, review = copy.deepcopy(self.approval), copy.deepcopy(self.review)
        changes = [('permit_window_seconds', 7200), ('permit_window_seconds', 17999),
                   ('permit_window_seconds', 18001), ('max_executions', 0),
                   ('max_executions', 1), ('max_executions', 4), ('max_executions', 6),
                   ('expires_unix', NOW + 17998), ('expires_unix', NOW + 18000),
                   ('issued_unix', NOW)]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.reset_payloads(approval, review)
                self.approval[key] = self.review[key] = value
                self.prepare(); self.assert_hold()
        for issued in (NOW + 1, NOW - 18000):
            with self.subTest(issued=issued):
                self.reset_payloads(approval, review)
                for payload in (self.approval, self.review):
                    payload.update(issued_unix=issued, expires_unix=issued + 18000)
                self.prepare(); self.assert_hold()

    def test_owner_and_reviewer_require_exact_decisions_and_writer_separation(self):
        approval, review = copy.deepcopy(self.approval), copy.deepcopy(self.review)
        changes = [('approval', 'decision', 'AUDIT_PASS'),
                   ('approval', 'rollback_approved', 1), ('approval', 'rollback_approved', False),
                   ('approval', 'review_comment_id', 4), ('approval', 'review_comment_id', True),
                   ('approval', 'review_body_sha256', 'f' * 64),
                   ('review', 'decision', 'INSTALL_APPROVED'),
                   ('review', 'owner_id', REVIEWER_ID), ('review', 'reviewer_id', OWNER_ID),
                   ('review', 'source_writer_id', REVIEWER_ID),
                   ('review', 'owner_id', True), ('review', 'reviewer_id', True)]
        for who, key, value in changes:
            with self.subTest(who=who, key=key, value=value):
                self.reset_payloads(approval, review)
                getattr(self, who)[key] = value; self.prepare()
                # prepare() computes the legitimate exact body hash; override
                # that one field afterward to test its semantic binding too.
                if key == 'review_body_sha256':
                    self.approval[key] = value
                    self.comments[4]['body'] = INSTALL_PREFIX + canonical(self.approval).decode()
                    self.anchor()
                self.assert_hold()

    def test_findings_must_be_exact_closed_and_bind_static_baseline(self):
        approval, review = copy.deepcopy(self.approval), copy.deepcopy(self.review)
        cases = [None, {}, {'R1': review['findings']['R1']},
                 dict(review['findings'], R4=review['findings']['R1'])]
        for field, value in [('state', 'OPEN'), ('evidence_sha256', []),
                             ('evidence_sha256', ['not-a-digest']), ('unknown', True)]:
            findings = copy.deepcopy(review['findings']); findings['R2'][field] = value
            cases.append(findings)
        findings = copy.deepcopy(review['findings'])
        findings['R3']['evidence_sha256'] = ['0' * 64]; cases.append(findings)
        for findings in cases:
            with self.subTest(findings=findings):
                self.reset_payloads(approval, review)
                self.review['findings'] = findings; self.prepare(); self.assert_hold()

    def test_live_git_tree_and_artifact_identity_are_exact(self):
        commit_path = 'git/commits/' + self.plan['source_commit']
        original = copy.deepcopy(self.responses)
        cases = [(commit_path, 'sha', 'f' * 40),
                 (commit_path, 'tree', {'sha': 'f' * 40}),
                 ('actions/artifacts/7', 'id', True), ('actions/artifacts/7', 'id', 8),
                 ('actions/artifacts/7', 'expired', True), ('actions/artifacts/7', 'expired', 0),
                 ('actions/artifacts/7', 'digest', 'sha256:' + '0' * 64),
                 ('actions/artifacts/7', 'workflow_run', {'id': 8, 'head_sha': 'a' * 40}),
                 ('actions/artifacts/7', 'workflow_run', {'id': 6, 'head_sha': 'f' * 40})]
        for path, key, value in cases:
            with self.subTest(path=path, key=key, value=value):
                self.responses = copy.deepcopy(original)
                self.responses[path][key] = value; self.assert_hold()

    def test_ci_must_be_completed_successful_exact_run_commit_workflow_and_repo(self):
        original = copy.deepcopy(self.responses['actions/runs/6'])
        cases = [('id', True), ('id', 7), ('status', 'queued'), ('status', 'in_progress'),
                 ('conclusion', None), ('conclusion', 'failure'), ('head_sha', 'f' * 40),
                 ('path', '.github/workflows/pr122-customer-center.yml'),
                 ('event', 'pull_request'), ('event', 'pull_request_target')]
        for name in ('repository', 'head_repository'):
            cases.extend([(name, {'id': REPO_ID + 1, 'full_name': REPO}),
                          (name, {'id': REPO_ID, 'full_name': 'attacker/repo'}),
                          (name, {'id': True, 'full_name': REPO}), (name, None)])
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.responses['actions/runs/6'] = dict(original, **{key: value})
                self.assert_hold()

    def test_repeated_gate_detects_exact_body_edits_including_whitespace(self):
        original = copy.deepcopy(self.comments)
        for number in (4, 5):
            with self.subTest(number=number):
                self.comments = copy.deepcopy(original)
                self.assertEqual(self.gate(), self.approval)
                self.comments[number]['body'] += ' '
                self.assert_hold()

    def test_repeated_gate_detects_comment_deletion_or_live_identity_change(self):
        original = copy.deepcopy(self.comments)
        for number in (4, 5):
            for action in ('deleted', 'identity'):
                with self.subTest(number=number, action=action):
                    self.comments = copy.deepcopy(original); self.gate()
                    if action == 'deleted': del self.comments[number]
                    else: self.comments[number]['user']['id'] = 123
                    self.assert_hold()

    def test_repeated_gate_rereads_revocations_and_protected_config(self):
        original = copy.deepcopy(self.trust)
        for key, value in [('revoked_review_ids', [5]), ('reviewer_id', OWNER_ID),
                           ('source_writer_id', REVIEWER_ID), ('repository_id', REPO_ID + 1)]:
            with self.subTest(key=key):
                self.trust = copy.deepcopy(original); self.save_trust(); self.gate()
                self.trust[key] = value; self.save_trust(); self.assert_hold()

    def test_repeated_gate_api_exceptions_are_hold_without_cached_authorization(self):
        original_comments = copy.deepcopy(self.comments)
        original_responses = copy.deepcopy(self.responses)
        paths = ['', 'issues/comments/4', 'issues/comments/5',
                 'git/commits/' + self.plan['source_commit'], 'actions/artifacts/7', 'actions/runs/6']
        for path in paths:
            for error in (OSError('fixture 404'), TimeoutError('fixture timeout'),
                          ValueError('fixture malformed API response')):
                with self.subTest(path=path, exception=type(error).__name__):
                    self.comments = copy.deepcopy(original_comments)
                    self.responses = copy.deepcopy(original_responses); self.gate()
                    if path.startswith('issues/comments/'):
                        self.comments[int(path.rsplit('/', 1)[1])] = error
                    else: self.responses[path] = error
                    self.assert_hold()


class StaticGithubCoordinatorTests(_DualFixture, unittest.TestCase):
    """Exercise the original durable ledger with the real dual gate, no effects."""

    def setUp(self):
        super().setUp()
        self.configure_static_authority()

    def ledger_path(self):
        return release.STATE / (release.TXN + '.attempts.json')

    def ledger(self):
        return json.loads(self.ledger_path().read_bytes())

    def apply(self, after_admission=None):
        real_gate = self.authority.gate
        def fresh_gate(comment_id, plan):
            value = real_gate(comment_id, plan)
            self.events.append(('authorized', comment_id))
            return value
        fd = os.open(release.LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.patches(), patch.object(self.authority, 'gate', side_effect=fresh_gate):
                approval = fresh_gate(4, self.plan)
                if after_admission is not None: after_admission()
                return static.StaticCoordinator(self.authority, self.source, 4, self.plan,
                                                approval, self.ops, fd).run()
        finally:
            os.close(fd)

    def test_edit_or_delete_after_initial_admission_blocks_all_stage_effects(self):
        original = copy.deepcopy(self.comments)
        for number in (4, 5):
            for action in ('edit', 'delete'):
                with self.subTest(number=number, action=action):
                    self.comments = copy.deepcopy(original)
                    def change():
                        if action == 'delete': del self.comments[number]
                        else: self.comments[number]['body'] += ' '
                    with self.assertRaisesRegex(Denied, '^HOLD:'):
                        self.apply(after_admission=change)
                    self.assertEqual(self.ops.executed, [])
                    self.assertEqual(self.ops.reconciled, [])
                    self.assertFalse(self.ledger_path().exists())

    def test_edit_or_delete_after_restart_admission_blocks_recovery_without_writes(self):
        self.interrupt_first_stage()
        original = copy.deepcopy(self.comments)
        before = self.ledger_path().read_bytes()
        effects = copy.deepcopy(self.ops.executed)
        self.ops.proof_status = 'COMPLETE'
        for number in (4, 5):
            for action in ('edit', 'delete'):
                with self.subTest(number=number, action=action):
                    self.comments = copy.deepcopy(original)
                    def change():
                        if action == 'delete': del self.comments[number]
                        else: self.comments[number]['body'] += ' '
                    with self.assertRaisesRegex(Denied, '^HOLD:'):
                        self.apply(after_admission=change)
                    self.assertEqual(self.ops.executed, effects)
                    self.assertEqual(self.ops.reconciled, [])
                    self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_each_stage_effect_has_a_new_successful_live_gate(self):
        self.ops.execute_hook = lambda stage, lease: self.events.append(('execute', stage))
        result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(result['completed_stages'], list(static.STAGES))
        self.assertEqual([event[1] for event in self.events if event[0] == 'execute'], list(static.STAGES))
        for index, event in enumerate(self.events):
            if event[0] == 'execute': self.assertEqual(self.events[index - 1][0], 'authorized')
        self.assertEqual(self.events[-1][0], 'authorized')
        self.assertGreaterEqual(self.fetched.count('issues/comments/4'), len(static.STAGES) + 2)
        self.assertEqual(self.fetched.count('issues/comments/4'), self.fetched.count('issues/comments/5'))

    def test_edit_after_one_effect_holds_before_second_and_preserves_budget(self):
        def edit_review(stage, lease):
            if stage == static.STAGES[0]: self.comments[5]['body'] += '\n'
        self.ops.execute_hook = edit_review
        with self.assertRaisesRegex(Denied, '^HOLD:'): self.apply()
        held = self.ledger()
        self.assertEqual(held['state'], 'HOLD')
        self.assertEqual(len(held['attempts']), 1)
        self.assertEqual(held['attempts'][0]['state'], 'FAILED_HOLD')
        self.assertEqual(self.ops.executed, [(static.STAGES[0], 1)])
        before = self.ledger_path().read_bytes()
        with self.assertRaisesRegex(Denied, '^HOLD:'): self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(self.ops.executed, [(static.STAGES[0], 1)])

    def interrupt_first_stage(self):
        self.ops.execute_hook = lambda stage, lease: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt): self.apply()
        self.ops.execute_hook = None
        self.assertEqual(self.ledger()['intent']['stage'], static.STAGES[0])

    def test_recovery_is_sandwiched_by_fresh_gate_before_proof_and_commit(self):
        self.interrupt_first_stage()
        self.events.clear()
        self.ops.proof_status = 'COMPLETE'
        self.ops.reconcile_hook = lambda stage, intent, checkpoint, lease: self.events.append(('reconcile', stage))
        result = self.apply()
        self.assertEqual(result['state'], 'SUCCESS')
        index = next(i for i, event in enumerate(self.events) if event[0] == 'reconcile')
        self.assertEqual(self.events[index - 1][0], 'authorized')
        self.assertEqual(self.events[index + 1][0], 'authorized')
        self.assertEqual(sum(stage == static.STAGES[0] for stage, attempt in self.ops.executed), 1)
        self.assertEqual(result['recoveries'][0]['status'], 'COMPLETE')

    def test_revocation_during_readonly_recovery_cannot_commit_or_spend_attempt(self):
        self.interrupt_first_stage()
        before = self.ledger_path().read_bytes()
        effects = copy.deepcopy(self.ops.executed)
        self.ops.proof_status = 'COMPLETE'
        def revoke(stage, intent, checkpoint, lease):
            self.trust['revoked_review_ids'] = [5]; self.save_trust()
        self.ops.reconcile_hook = revoke
        with self.assertRaisesRegex(Denied, '^HOLD:'): self.apply()
        self.assertEqual(self.ledger_path().read_bytes(), before)
        self.assertEqual(self.ops.executed, effects)
        self.assertEqual(len(self.ledger()['attempts']), 1)
        self.assertEqual(self.ledger()['checkpoints'], {})

    def test_api_failure_between_effects_stops_original_coordinator(self):
        def break_api(stage, lease):
            if stage == static.STAGES[0]: self.responses[''] = TimeoutError('fixture timeout')
        self.ops.execute_hook = break_api
        with self.assertRaisesRegex(Denied, '^HOLD:'): self.apply()
        self.assertEqual(self.ops.executed, [(static.STAGES[0], 1)])
        self.assertEqual(self.ledger()['state'], 'HOLD')
        self.assertEqual(len(self.ledger()['attempts']), 1)


class StaticAuthorityRoutingTests(_DualFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.configure_static_authority()

    def test_explicit_dual_failure_never_falls_back_to_ed25519_or_login(self):
        from scripts import pr122_customer_review as legacy_review
        with patch.object(legacy_review, 'verify', side_effect=AssertionError('Legacy fallback')) as legacy, \
             patch.object(release, 'gate', side_effect=AssertionError('Login fallback')) as login:
            self.comments[5]['body'] += ' '
            with self.assertRaisesRegex(Denied, '^HOLD:'):
                self.authority.gate(4, self.plan)
            legacy.assert_not_called(); login.assert_not_called()

    def test_null_unknown_and_nonstring_modes_reject_before_any_authority_call(self):
        for mode in (None, '', 'ED25519', 'LOGIN_ONLY', True, {}, []):
            with self.subTest(mode=mode), patch.object(self.authority, '_gate') as admitted:
                self.plan['authorization_mode'] = mode
                with self.assertRaisesRegex(Denied, 'STATIC_AUTHORIZATION_MODE'):
                    self.authority.gate(4, self.plan)
                admitted.assert_not_called()

    def test_absent_mode_keeps_actual_original_ed25519_fixture_valid(self):
        from scripts import pr122_customer_review as legacy_review
        from tests import test_pr122_static_signature as signed_fixtures
        signed = signed_fixtures.StaticSignatureTests()
        signed.setUp(); self.addCleanup(signed.doCleanups)
        signed.configure()
        self.pins['static_artifact_sha256'] = signed.plan['artifact_tar_sha256']
        self.pins_path.write_bytes(canonical(self.pins))
        signed.plan.update(transaction=release.TXN,
                           host_pins_sha256=digest(self.pins_path.read_bytes()),
                           static_baseline_sha256=self.plan['static_baseline_sha256'])
        for payload in (signed.approval, signed.payload):
            payload.update(host_pins_sha256=signed.plan['host_pins_sha256'],
                           static_baseline_sha256=signed.plan['static_baseline_sha256'])
        signed.payload['findings']['R3']['evidence_sha256'] = [signed.plan['static_baseline_sha256']]
        signed.prepare()
        signed.comments[4]['body'] = INSTALL_PREFIX + canonical(signed.approval).decode()
        signed.trust['install_anchors'][release.TXN]['install_body_sha256'] = digest(signed.comments[4]['body'].encode())
        (release.CONFIG / 'INDEPENDENT_REVIEW_TRUST.json').write_bytes(canonical(signed.trust))
        def legacy_fetch(path):
            result = signed.fetch(path)
            if path == 'actions/runs/6':
                result['path'] = '.github/workflows/pr122-unified-release-review.yml'
            return result
        with patch.object(release, 'github', side_effect=legacy_fetch), \
             patch.object(dual, 'gate', side_effect=AssertionError('Implicit new mode')) as new_mode, \
             patch.object(legacy_review, 'verify', wraps=legacy_review.verify) as old_verify:
            self.assertEqual(self.authority.gate(4, signed.plan), signed.approval)
            old_verify.assert_called_once(); new_mode.assert_not_called()

    def test_host_pin_and_baseline_drift_hold_before_comment_fetch(self):
        for drift in ('raw-pins', 'baseline-plan', 'artifact-plan'):
            with self.subTest(drift=drift):
                pins = self.pins_path.read_bytes(); plan = copy.deepcopy(self.plan)
                if drift == 'raw-pins': self.pins_path.write_bytes(pins + b' ')
                elif drift == 'baseline-plan': self.plan['static_baseline_sha256'] = '0' * 64
                else: self.plan['artifact_tar_sha256'] = '0' * 64
                self.github.reset_mock()
                with self.assertRaisesRegex(Denied, '^HOLD:'):
                    self.authority.gate(4, self.plan)
                self.github.assert_not_called()
                self.pins_path.write_bytes(pins); self.plan = plan

    def test_real_no_redirect_handler_never_forwards_authorization(self):
        requests = []
        token = 'FIXTURE-NEVER-A-REAL-TOKEN'
        destination = 'https://untrusted.invalid/token-leak'
        class Transport(urllib.request.HTTPSHandler):
            def https_open(self, request):
                requests.append((request.full_url, dict(request.header_items())))
                headers = Message(); headers['Location'] = destination
                response = urllib.response.addinfourl(io.BytesIO(token.encode()), headers,
                                                       request.full_url, code=302)
                response.msg = 'Found'
                return response
        build_opener = urllib.request.build_opener
        def offline_opener(*handlers):
            return build_opener(Transport(), *handlers)
        fake_token = SimpleNamespace(stat=lambda: SimpleNamespace(st_uid=0, st_mode=0o600),
                                     read_text=lambda: token)
        with patch.object(release, 'private_path', return_value=fake_token), \
             patch.object(urllib.request, 'build_opener', side_effect=offline_opener), \
             patch.object(release, 'github', side_effect=REAL_GITHUB):
            with self.assertRaisesRegex(Denied, '^HOLD:') as caught:
                self.authority.gate(4, self.plan)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0], 'https://api.github.com/repos/' + REPO + '/issues/comments/4')
        self.assertEqual(requests[0][1]['Authorization'], 'Bearer ' + token)
        self.assertNotIn(token, str(caught.exception))
        self.assertNotIn(destination, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_api_exception_with_secret_is_sanitized_by_public_authority(self):
        token = 'FIXTURE-SECRET-IN-API-ERROR'
        self.responses[''] = RuntimeError('response includes ' + token)
        with self.assertRaisesRegex(Denied, '^HOLD:') as caught:
            self.authority.gate(4, self.plan)
        self.assertNotIn(token, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == '__main__':
    unittest.main()
