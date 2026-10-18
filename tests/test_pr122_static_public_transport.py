"""Offline public GitHub transport/budget regressions, never target acceptance.

Uses temporary source/receipt files, exact existing coordinator/adapter guard
methods, and in-memory HTTP responses. No real credentials or network calls.
"""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.error

from scripts import pr122_customer_release as release
from scripts import pr122_static_github_approval as dual
from scripts import pr122_static_workflow as static
from scripts.pr122_customer_core import Denied, canonical, digest
from tests.test_pr122_static_github_approval import _DualFixture, MODE, NOW, REPO
from tests import test_pr122_static_operations as operations_fixtures

REAL_SUBPROCESS_RUN = subprocess.run

TRANSPORT = {'mode': 'PUBLIC_GITHUB', 'comments_page': 4, 'per_page': 100,
             'metadata_policy': 'PROCESS_START_AND_RESTART', 'request_budget': 54}
COMMENTS = 'issues/122/comments?per_page=100&page=4'
API_ROOT = 'https://api.github.com/repos/' + REPO + '/'


class _PublicFixture(_DualFixture):
    def setUp(self):
        super().setUp()
        contexts = patch.dict(dual._PUBLIC_CONTEXTS, {}, clear=True)
        contexts.start(); self.addCleanup(contexts.stop)
        self.transport = copy.deepcopy(TRANSPORT)
        self.trust['github_transport'] = copy.deepcopy(self.transport)
        self.plan['github_transport'] = copy.deepcopy(self.transport)
        self.bind_public()
        self.requests = []
        self.http_payloads = {}
        self.http_headers = {}
        self.http_status = {}
        self.http_errors = {}
        self.collection = None
        self.available = 60
        self.http_hook = None
        self.opener = Mock(open=Mock(side_effect=self.http_open))
        opener_patch = patch.object(dual.urllib.request, 'build_opener', side_effect=self.build_opener)
        opener_patch.start(); self.addCleanup(opener_patch.stop)
        self.github.side_effect = AssertionError('Authenticated fallback is forbidden')

    def bind_public(self):
        self.plan['github_authority_sha256'] = dual.trust_digest(self.trust)
        for payload in (self.approval, self.review):
            payload.update(github_transport=copy.deepcopy(self.transport),
                           github_authority_sha256=self.plan['github_authority_sha256'],
                           plan_sha256=digest(canonical(self.plan)),
                           workflow_contract_sha256=digest(canonical(self.plan['workflow_contract'])))
        self.prepare()

    def build_opener(self, *handlers):
        self.assertEqual(len(handlers), 2)
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], dual._NoRedirect)
        return self.opener

    def http_open(self, request, timeout):
        self.assertEqual(timeout, 15)
        self.assertTrue(request.full_url.startswith(API_ROOT))
        self.assertEqual(request.get_method(), 'GET')
        self.assertFalse(any(name.lower() in ('authorization', 'cookie', 'proxy-authorization')
                             for name, value in request.header_items()))
        relative = request.full_url[len(API_ROOT):]
        allowed = {COMMENTS, 'git/commits/' + self.plan['source_commit'],
                   'actions/artifacts/7', 'actions/runs/6'}
        self.assertIn(relative, allowed)
        self.requests.append(relative)
        if self.http_hook is not None: self.http_hook(relative)
        if relative in self.http_errors: raise self.http_errors[relative]
        if relative in self.http_payloads:
            raw = self.http_payloads[relative]
        else:
            value = (self.collection if self.collection is not None else list(self.comments.values())) \
                    if relative == COMMENTS else self.responses[relative]
            raw = canonical(value)
        headers = {'X-RateLimit-Remaining': str(max(0, self.available - len(self.requests))),
                   'X-RateLimit-Reset': str(NOW + 3600)}
        headers.update(self.http_headers.get(relative, {}))
        status = self.http_status.get(relative, 200)
        class Response:
            def __init__(inner): inner.status, inner.headers = status, headers
            def __enter__(inner): return inner
            def __exit__(inner, *args): return False
            def read(inner, limit):
                self.assertEqual(limit, 2_000_001)
                return raw[:limit]
        return Response()


class PublicTransportTests(_PublicFixture, unittest.TestCase):
    def test_first_gate_four_reads_then_exact_one_live_collection_per_gate(self):
        self.assertEqual(self.gate(), self.approval)
        self.assertEqual(self.requests, [COMMENTS, 'git/commits/' + self.plan['source_commit'],
                                        'actions/artifacts/7', 'actions/runs/6'])
        self.assertEqual(self.gate(), self.approval)
        self.assertEqual(self.requests[-1], COMMENTS)
        self.assertEqual(len(self.requests), 5)
        self.assertEqual(dual.public_budget_context(self.plan), {
            'requests_used': 5, 'remaining': 55, 'reserved_remaining': 49,
            'last_status': 200, 'reset_unix': NOW + 3600})
        self.github.assert_not_called()

    def test_all_four_signed_transport_contracts_must_match(self):
        for target in ('trust', 'plan', 'approval', 'review'):
            with self.subTest(target=target):
                original = copy.deepcopy(getattr(self, target))
                getattr(self, target)['github_transport']['comments_page'] = 2
                if target == 'trust': self.save_trust()
                elif target in ('approval', 'review'): self.prepare()
                self.assert_hold()
                setattr(self, target, original); self.prepare()
                dual._PUBLIC_CONTEXTS.clear(); self.requests.clear()

    def test_transport_requires_exact_schema_integer_page_and_budget(self):
        original = copy.deepcopy(self.trust)
        cases = [('comments_page', True), ('comments_page', 0), ('comments_page', 10001),
                 ('comments_page', '1'), ('per_page', 99), ('per_page', True),
                 ('request_budget', 55), ('request_budget', True),
                 ('metadata_policy', 'CACHE_FOREVER'), ('mode', 'AUTHENTICATED'), ('extra', True)]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                self.trust = copy.deepcopy(original)
                self.trust['github_transport'][name] = value; self.save_trust()
                self.assert_hold(); self.assertEqual(self.requests, [])

    def test_wrong_missing_duplicated_or_moved_comments_never_follow_pagination(self):
        original = copy.deepcopy(self.comments)
        cases = [[], [original[4]], [original[5]],
                 [original[4], original[5], copy.deepcopy(original[5])],
                 [dict(original[4], issue_url='https://api.github.com/repos/foreign/repo/issues/122'), original[5]]]
        for collection in cases:
            with self.subTest(size=len(collection)):
                self.collection = collection
                self.http_headers[COMMENTS] = {'Link': '<https://untrusted.invalid/next>; rel="next"'}
                self.assert_hold(); self.assertEqual(self.requests, [COMMENTS])
                dual._PUBLIC_CONTEXTS.clear(); self.requests.clear()

    def test_collection_strict_json_rejects_duplicates_nan_oversize_and_wrong_shape(self):
        cases = [b'{}', b'null', b'[{"id":4,"id":5}]', b'[{"id":NaN}]',
                 b'[{"value":1e999}]', b'[' + b' ' * 2_000_000 + b']',
                 canonical([{'id': n} for n in range(101)])]
        for raw in cases:
            with self.subTest(raw_size=len(raw)):
                self.http_payloads[COMMENTS] = raw
                self.assert_hold(); self.assertEqual(self.requests, [COMMENTS])
                dual._PUBLIC_CONTEXTS.clear(); self.requests.clear()

    def test_edit_deletion_or_revocation_after_success_cannot_use_cached_authority(self):
        for action in ('edit', 'delete', 'revoke'):
            with self.subTest(action=action):
                comments, trust = copy.deepcopy(self.comments), copy.deepcopy(self.trust)
                self.gate()
                if action == 'edit': self.comments[5]['body'] += ' '
                elif action == 'delete': del self.comments[5]
                else: self.trust['revoked_review_ids'] = [5]; self.save_trust()
                self.assert_hold()
                count = len(self.requests)
                self.assert_hold()
                self.assertEqual(len(self.requests), count)
                self.comments, self.trust = comments, trust
                self.save_trust(); dual._PUBLIC_CONTEXTS.clear(); self.requests.clear()

    def test_new_process_rechecks_all_metadata_instead_of_reusing_prior_success(self):
        self.gate(); self.gate()
        self.assertEqual(len(self.requests), 5)
        current = os.getpid()
        with patch.object(dual.os, 'getpid', return_value=current + 1):
            self.gate()
        self.assertEqual(self.requests[5:], [COMMENTS, 'git/commits/' + self.plan['source_commit'],
                                            'actions/artifacts/7', 'actions/runs/6'])

    def test_restart_detects_artifact_expiry_under_explicit_process_metadata_policy(self):
        self.gate()
        self.responses['actions/artifacts/7']['expired'] = True
        self.gate()  # Signed policy deliberately rechecks metadata only on restart.
        current = os.getpid()
        with patch.object(dual.os, 'getpid', return_value=current + 1): self.assert_hold()
        self.assertEqual(self.requests[-1], 'actions/artifacts/7')

    def test_rate_status_reset_and_uncertain_errors_fail_closed_without_fallback(self):
        cases = [('status', 403), ('status', 429), ('status', 302),
                 ('remaining', None), ('remaining', 'abc'), ('remaining', '-1'),
                 ('remaining', '52'), ('reset', None), ('reset', '0'),
                 ('error', TimeoutError('FIXTURE_SECRET')), ('error', OSError('FIXTURE_SECRET'))]
        for kind, value in cases:
            with self.subTest(kind=kind, value=str(value)):
                if kind == 'status': self.http_status[COMMENTS] = value
                elif kind == 'remaining': self.http_headers[COMMENTS] = {'X-RateLimit-Remaining': value}
                elif kind == 'reset': self.http_headers[COMMENTS] = {'X-RateLimit-Reset': value}
                else: self.http_errors[COMMENTS] = value
                with self.assertRaisesRegex(Denied, '^HOLD:') as caught: self.gate()
                self.assertNotIn('FIXTURE_SECRET', str(caught.exception))
                self.assert_hold(); self.assertEqual(len(self.requests), 1)
                self.github.assert_not_called()
                self.http_status.clear(); self.http_headers.clear(); self.http_errors.clear()
                self.requests.clear(); dual._PUBLIC_CONTEXTS.clear()

    def test_local_fifty_four_request_cap_is_hard_even_if_api_has_more(self):
        self.available = 1000
        self.gate()
        for _ in range(50): self.gate()
        self.assertEqual(len(self.requests), 54)
        self.assertEqual(dual.public_budget_context(self.plan)['reserved_remaining'], 0)
        self.assert_hold(); self.assertEqual(len(self.requests), 54)

    def test_phase_budget_requires_both_live_and_reserved_capacity(self):
        self.gate()
        self.assertEqual(dual.require_public_budget(self.plan, 50)['reserved_remaining'], 50)
        for calls in (51, -1, True, '1'):
            with self.subTest(calls=calls), self.assertRaises(Denied):
                dual.require_public_budget(self.plan, calls)
        context = dual._PUBLIC_CONTEXTS[dual._context_key(self.plan)]
        context['remaining'] = 10
        with self.assertRaises(Denied): dual.require_public_budget(self.plan, 11)

    def test_no_crypto_with_actual_authority_source_and_exact_twenty_three_file_closure(self):
        from scripts import pr122_static_source_package as package
        archive, report = package.build(Path(__file__).resolve().parents[1], self.plan['source_commit'])
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
            for member in bundle.getmembers():
                name = member.name.removeprefix('pr122-static-controlled/')
                self.assertTrue(member.isfile())
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.extractfile(member).read())
        manifest_raw = (root / 'STATIC_SOURCE_MANIFEST.json').read_bytes()
        manifest = json.loads(manifest_raw)
        self.assertEqual(report['source_bindings'], 23)
        self.assertEqual(len(manifest['files']), 23)
        pins = {'package_schema': 'FULL_STATIC_REVIEW_V1',
                'static_artifact_sha256': self.plan['artifact_tar_sha256'],
                'previous_release': str(root / 'previous'), 'previous_receipt_sha256': '1' * 64,
                'previous_manifest_sha256': '2' * 64, 'nginx': {},
                'static_source_manifest_sha256': digest(manifest_raw)}
        pins_raw = canonical(pins); (root / 'HOST_PINS.json').write_bytes(pins_raw)
        baseline = {key: pins[key] for key in ('previous_release', 'previous_receipt_sha256',
                                              'previous_manifest_sha256', 'nginx')}
        bindings = {'manifest_sha256': digest(manifest_raw),
                    'scope_sha256': digest(canonical(manifest['files'])),
                    'host_pins_sha256': digest(pins_raw),
                    'static_baseline_sha256': digest(canonical(baseline))}
        self.plan.update(bindings)
        for obj in (self.approval, self.review): obj.update(bindings)
        self.review['findings']['R3']['evidence_sha256'] = [bindings['static_baseline_sha256']]
        self.bind_public()
        program = r'''
import builtins,sys,json,io
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
original_import=builtins.__import__
def restricted(name,*args,**kwargs):
    if name=='cryptography' or name.startswith('cryptography.'):
        raise AssertionError('Cryptography imported on public path')
    return original_import(name,*args,**kwargs)
builtins.__import__=restricted
from unittest.mock import patch
from types import SimpleNamespace
from scripts import pr122_static_github_approval as d
from scripts import pr122_customer_release as r
from scripts import pr122_customer_attempts as a
from scripts import pr122_static_workflow as s
from scripts import pr122_site_hub_unified_release as original
value=json.loads(sys.stdin.read());seen=[]
class Response:
    status=200
    def __init__(self,raw):
        self.raw=raw
        self.headers={'X-RateLimit-Remaining':str(60-len(seen)),'X-RateLimit-Reset':'1792339200'}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw[:n]
def opened(request,timeout):
    path=request.full_url.split('/'+d.REPOSITORY+'/',1)[1];seen.append(path)
    assert not any(k.lower()=='authorization' for k,v in request.header_items())
    return Response(json.dumps(value['responses'][path]).encode())
# Only filesystem ownership/custody adapters are mocked. The 23 actual source
# bytes, manifest, original source verifier, StaticAuthority constructor, public
# gate, and loaded-module closure verification all run unchanged.
original.PINS=root/'HOST_PINS.json';original.c.CONTROL=root/'control'
original.c.read=lambda path:Path(path).read_bytes()
original.c.trusted=lambda *args:None
transaction=original.Transaction.__new__(original.Transaction)
transaction.id=value['plan']['transaction'];transaction.pins=json.loads(original.PINS.read_bytes())
authority=s.StaticAuthority(transaction,root)
with patch.object(a,'read_private',return_value=value['trust']),patch.object(r,'github',side_effect=AssertionError('credential client')),patch.object(d.urllib.request,'build_opener',return_value=SimpleNamespace(open=opened)),patch.object(d.time,'time',return_value=1792335600):
    result=authority.gate(4,value['plan'])
    manifest,raw,files=authority.source(root)
assert result==value['approval']
assert len(files)==len(manifest['files'])==23
assert not any(n=='cryptography' or n.startswith('cryptography.') for n in sys.modules)
print(json.dumps({'requests':seen,'crypto_imported':False,'source_files':len(files)}))
'''
        payload = {'trust': self.trust, 'plan': self.plan, 'approval': self.approval,
                   'responses': {**self.responses, COMMENTS: list(self.comments.values())}}
        result = REAL_SUBPROCESS_RUN([sys.executable, '-I', '-S', '-B', '-c', program, str(root)],
                                     input=canonical(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        output = json.loads(result.stdout)
        self.assertFalse(output['crypto_imported'])
        self.assertEqual(output['source_files'], 23)
        self.assertEqual(len(output['requests']), 4)

    def test_signed_nonfirst_page_accepts_appended_unrelated_comments_without_rescoping(self):
        self.assertEqual(self.plan['github_transport']['comments_page'], 4)
        self.gate()
        self.collection = list(self.comments.values()) + [{'id': number} for number in range(100, 198)]
        self.assertEqual(len(self.collection), 100)
        self.assertEqual(self.gate(), self.approval)
        self.assertEqual(self.requests[-1], COMMENTS)
        self.assertNotIn('issues/122/comments?per_page=100&page=1', self.requests)


class PublicCoordinatorBudgetTests(_PublicFixture, unittest.TestCase):
    def adapter_fixture(self, public=True):
        fixture = operations_fixtures.CoordinatorAdapterFixtureTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        if not public:
            return fixture
        fixture.ops.t.id = release.TXN
        fixture.ops.t.folder = fixture.release.STATE / release.TXN
        fixture.ops.t.receipt = fixture.ops.t.folder / 'receipt.json'
        fixture.release.TXN = release.TXN
        fixture.ops.inputs = {stage: fixture.ops.expected_input(stage) for stage in static.STAGES}
        self.plan['workflow_contract'] = {'schema': 1, 'stages': [{
            'stage': stage, 'input_sha256': digest(canonical(fixture.ops.input(stage))),
            'implementation_sha256': digest(fixture.ops.implementation(stage)),
            'adopt_receipt_sha256': None, 'recovery_actions': ['RECONCILE_STATIC']
        } for stage in static.STAGES]}
        self.bind_public()
        fixture.plan = copy.deepcopy(self.plan)
        fixture.ops.plan = copy.deepcopy(self.plan)
        fixture.approval = copy.deepcopy(self.approval)
        fixture.release.authorization_mode = MODE
        fixture.release.source = lambda folder: release.source(self.source)
        self.gate_calls = 0
        def real_gate(comment, plan):
            self.gate_calls += 1
            return dual.gate(comment, plan, release.TXN)
        fixture.release.gate = real_gate
        fixture.ops.coordinator = None
        fixture.coordinator = static.StaticCoordinator(fixture.release, fixture.root, 4,
            fixture.plan, fixture.approval, fixture.ops, fixture.fd)
        return fixture

    def run_adapter(self, fixture):
        fixture.release.gate(4, fixture.plan)  # controlled_apply admission
        return fixture.coordinator.run()

    def test_original_authenticated_adapter_still_requires_fifty_nine_gates(self):
        fixture = self.adapter_fixture(public=False)
        gate = Mock(wraps=fixture.release.gate); fixture.release.gate = gate
        self.assertEqual(self.run_adapter(fixture)['state'], 'SUCCESS')
        self.assertEqual(gate.call_count, 59)

    def test_public_full_real_adapter_uses_thirty_eight_gates_forty_one_gets(self):
        fixture = self.adapter_fixture()
        real = dual.require_public_budget
        with patch.object(dual, 'require_public_budget', wraps=real) as budget:
            result = self.run_adapter(fixture)
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(self.gate_calls, 38)
        self.assertEqual(len(self.requests), 41)
        self.assertEqual(self.requests.count(COMMENTS), 38)
        self.assertEqual(dual.public_budget_context(self.plan)['reserved_remaining'], 13)
        self.assertEqual(dual.public_budget_context(self.plan)['remaining'], 19)
        self.assertEqual([call.args[1] for call in budget.call_args_list],
                         [46, 45, 42, 39, 36, 33, 30, 24, 24, 21, 18, 15])
        self.assertEqual(fixture.events, ['backup', 'seal', 'prepare', 'stage_nginx',
            'nginx_test', 'activate', 'reload', 'readonly_http', 'check'])

    def test_public_fifty_four_available_requests_suffice_with_thirteen_reserved(self):
        fixture = self.adapter_fixture(); self.available = 54
        self.assertEqual(self.run_adapter(fixture)['state'], 'SUCCESS')
        self.assertEqual(len(self.requests), 41)
        self.assertEqual(dual.public_budget_context(self.plan)['remaining'], 13)
        self.assertEqual(dual.public_budget_context(self.plan)['reserved_remaining'], 13)

    def test_fixed_page_cutoff_before_admission_has_no_child_or_stage_writes(self):
        fixture = self.adapter_fixture()
        self.collection = [self.comments[4]]  # Reviewer would be on another page.
        with self.assertRaisesRegex(Denied, '^HOLD:'): self.run_adapter(fixture)
        self.assertEqual(self.requests, [COMMENTS])
        self.assertEqual(fixture.events, [])
        self.assertFalse(fixture.ops.t.folder.exists())
        self.assertFalse(fixture.coordinator.path.exists())

    def test_completed_final_phase_recovers_readonly_with_ten_fresh_gates(self):
        fixture = self.adapter_fixture()
        observe = fixture.ops._observe
        interrupted = [False]
        def crash_after_complete(stage):
            checkpoint = observe(stage)
            if stage == 'STATIC_CHECK' and not interrupted[0]:
                interrupted[0] = True
                raise KeyboardInterrupt('offline checkpoint gap')
            return checkpoint
        fixture.ops._observe = crash_after_complete
        with self.assertRaises(KeyboardInterrupt): self.run_adapter(fixture)
        self.assertEqual(self.gate_calls, 37)
        self.assertEqual(len(self.requests), 40)
        effects = list(fixture.events)
        child = json.loads(fixture.ops.t.receipt.read_bytes())
        self.assertEqual(child['completed'], list(static.STAGES))
        self.assertEqual(len(json.loads(fixture.coordinator.path.read_bytes())['checkpoints']), 9)
        fixture.ops._observe = observe
        self.requests.clear(); before = self.gate_calls
        process = os.getpid()
        with patch.object(dual.os, 'getpid', return_value=process + 1):
            result = self.run_adapter(fixture)
        self.assertEqual(result['state'], 'SUCCESS')
        self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(self.gate_calls - before, 10)
        self.assertEqual(len(self.requests), 13)
        self.assertEqual(fixture.events, effects)

    def test_unknown_reload_recovery_retains_eight_live_gates_and_no_replay(self):
        fixture = self.adapter_fixture()
        fixture.failure = 'reload'; fixture.failures_left = 1
        with self.assertRaises(Denied): self.run_adapter(fixture)
        self.assertEqual(fixture.events.count('reload'), 1)
        before_ledger = fixture.coordinator.path.read_bytes()
        effects = list(fixture.events)
        self.requests.clear(); before = self.gate_calls
        process = os.getpid()
        with patch.object(dual.os, 'getpid', return_value=process + 1):
            with self.assertRaises(Denied): self.run_adapter(fixture)
        self.assertEqual(self.gate_calls - before, 8)
        self.assertEqual(len(self.requests), 11)
        self.assertEqual(fixture.events, effects)
        self.assertEqual(fixture.coordinator.path.read_bytes(), before_ledger)

    def test_insufficient_initial_quota_prevents_child_directory_and_all_effects(self):
        fixture = self.adapter_fixture(); self.available = 53
        with self.assertRaisesRegex(Denied, '^HOLD:'): self.run_adapter(fixture)
        self.assertEqual(fixture.events, [])
        self.assertFalse(fixture.ops.t.folder.exists())
        self.assertFalse(fixture.coordinator.path.exists())

    def test_phase_budget_failure_prevents_initial_child_mkdir_and_backup(self):
        fixture = self.adapter_fixture()
        with patch.object(dual, 'require_public_budget', side_effect=Denied('HOLD:FIXTURE_LOW_BUDGET')):
            with self.assertRaises(Denied): self.run_adapter(fixture)
        self.assertEqual(fixture.events, [])
        self.assertFalse(fixture.ops.t.folder.exists())
        ledger = json.loads(fixture.coordinator.path.read_bytes())
        self.assertNotEqual(ledger['state'], 'SUCCESS')
        self.assertEqual(ledger['checkpoints'], {})

    def test_phase_budget_failure_before_seal_preserves_backup_without_seal_effect(self):
        fixture = self.adapter_fixture()
        actual = dual.require_public_budget
        def limited(plan, calls_needed):
            if calls_needed == 42: raise Denied('HOLD:FIXTURE_LOW_BUDGET')
            return actual(plan, calls_needed)
        with patch.object(dual, 'require_public_budget', side_effect=limited):
            with self.assertRaises(Denied): self.run_adapter(fixture)
        self.assertEqual(fixture.events, ['backup'])
        child = json.loads(fixture.ops.t.receipt.read_bytes())
        self.assertEqual(child['completed'], ['BACKUP_VERIFIED'])
        self.assertIsNone(child['intent'])


if __name__ == '__main__':
    unittest.main()
