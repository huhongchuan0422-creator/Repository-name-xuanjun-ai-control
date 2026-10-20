"""Offline adapter tests. Never import or invoke the root release helpers.

Fixtures exercise binding/reconciliation with temporary bytes only. They are not
production runtime, Nginx, TLS, publisher, or target-host acceptance evidence.
"""
import copy
import ast
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import tarfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import pr122_static_operations as static
from scripts.pr122_customer_core import Denied, canonical, digest


class Lease:
    def __init__(self): self.active_calls = 0
    def assert_fence(self): pass
    def authority(self): pass
    def verify_inputs(self, stage): pass
    def assert_active(self): self.active_calls += 1; raise AssertionError('Readonly proof requested effect lease')


class StaticOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.ops = static.OriginalStaticOperations.__new__(static.OriginalStaticOperations)
        self.ops.plan = {'source_commit': 'a' * 40}
        self.approval = {'permission': 'fixture-only'}
        self.ops.coordinator = SimpleNamespace(approval=self.approval)
        self.ops._bind_source = lambda: {'wrapper_sha256': 'b' * 64, 'pins_sha256': 'c' * 64}
        self.ops._bound = Mock()
        self.ops.c = SimpleNamespace(BASE=root / 'base', read=lambda path: Path(path).read_bytes())
        self.ops.t = SimpleNamespace(id='fixed-static-fixture', folder=root / 'child',
            receipt=root / 'child' / 'receipt.json', pins={'release_id': 'release-fixture'})
        self.ops.t.folder.mkdir(); self.ops.inputs = {s: {'stage': s} for s in static.STATIC_STAGES}
        self.data = {'schema': 1, 'transaction_id': self.ops.t.id, 'release_id': 'release-fixture',
            **self.ops._bind_source(), 'workflow_approval_sha256': digest(canonical(self.approval)),
            'approval': self.approval, 'source_commit': self.ops.plan['source_commit'], 'state': 'APPLYING',
            'completed': [], 'intent': None, 'nginx_identity': {'pid': 1}, 'sandbox': {'pid': 2}}
        self.save()

    def save(self):
        self.ops.t.receipt.write_text(json.dumps(self.data)); self.ops.t.receipt.chmod(0o600)

    def test_module_import_does_not_load_original_root_helpers(self):
        # Test discovery may run other suites first; trap this module's import
        # instead of assuming those suites have not loaded any release module.
        original_import = __import__
        def guarded(name, *args, **kwargs):
            names = args[2] if len(args) >= 3 else kwargs.get('fromlist', ())
            if (name.endswith(('pr122_site_hub_unified_release', 'pr122_site_hub_combined'))
                    or any(x in ('pr122_site_hub_unified_release', 'pr122_site_hub_combined') for x in names or ())):
                raise AssertionError('Root helper imported')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded): importlib.reload(static)

    def test_original_ten_stage_order_is_fixed(self):
        self.assertEqual(static.STATIC_STAGES, ('BACKUP_VERIFIED', 'SEALED_BUNDLE', 'STATIC_PREPARED',
            'NGINX_STAGED', 'NGINX_VALIDATED', 'ACTIVATION_DRIFT_CHECK', 'STATIC_ACTIVATED',
            'NGINX_RELOADED', 'HTTPS_SMOKE', 'STATIC_CHECK'))
        self.assertTrue(all(v == {'RECONCILE_STATIC'} for v in static.STATIC_RECOVERY.values()))

    def test_static_readonly_http_scope_does_not_claim_original_synthetic_smoke(self):
        # Inspect syntax only; neither root helper nor its preview POST is run.
        root = Path(__file__).resolve().parents[1]
        original_raw = (root / 'scripts/pr122_site_hub_combined.py').read_bytes()
        self.assertEqual(digest(original_raw), '8c403aac42253612c41465dbfdd3b9f43861449b2526a072ebd87bf02227cad3')
        adapter_tree = ast.parse((root / 'scripts/pr122_static_operations.py').read_bytes())
        cls = next(n for n in adapter_tree.body if isinstance(n, ast.ClassDef) and n.name == 'OriginalStaticOperations')
        readonly = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_static_https')
        keys = {key.value for key in readonly.body[-1].value.keys}
        self.assertEqual(keys, {'manifest_routes_checked', 'real_https', 'production_browser',
                                'state', 'business_e2e', 'preview_post'})
        for node in ast.walk(cls):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ('smoke', 'preview_probe'))

    def test_legacy_child_receipt_cannot_be_adopted(self):
        del self.data['workflow_approval_sha256']; self.save()
        with self.assertRaises(Denied): self.ops._load()

    def test_child_permission_pins_and_source_all_bound(self):
        for key, value in [('approval', {'permission': 'other'}), ('pins_sha256', 'd' * 64),
                           ('wrapper_sha256', 'd' * 64), ('source_commit', 'd' * 40),
                           ('workflow_approval_sha256', 'd' * 64)]:
            with self.subTest(key=key):
                old = self.data[key]; self.data[key] = value; self.save()
                with self.assertRaises(Denied): self.ops._load()
                self.data[key] = old

    def test_completed_steps_must_be_exact_unique_prefix(self):
        for completed in [['SEALED_BUNDLE'], ['BACKUP_VERIFIED', 'BACKUP_VERIFIED'],
                          list(reversed(static.STATIC_STAGES)), list(static.STATIC_STAGES) + ['STATIC_CHECK']]:
            self.data['completed'] = completed; self.save()
            with self.assertRaises(Denied): self.ops._load()

    def test_child_intent_can_only_be_next_original_step(self):
        self.data['completed'] = ['BACKUP_VERIFIED']; self.data['intent'] = 'STATIC_ACTIVATED'; self.save()
        with self.assertRaises(Denied): self.ops._load()

    def test_rollback_state_never_becomes_resume_permission(self):
        self.data['state'] = 'ROLLED_BACK'; self.save()
        with self.assertRaises(Denied): self.ops._load()

    def test_phase_checkpoint_is_stable_as_later_receipt_fields_advance(self):
        self.data['completed'] = ['BACKUP_VERIFIED']; self.save()
        self.ops._backup = lambda data: {'backup_sha256': 'e' * 64}
        first = self.ops._observe('BACKUP_VERIFIED')
        self.data['completed'] = list(static.STATIC_STAGES)
        self.data['state'] = static.STATIC_SUCCESS
        self.data['https'] = {'real_https': True}; self.save()
        self.assertEqual(first, self.ops._observe('BACKUP_VERIFIED'))

    def test_checkpoint_changes_if_live_phase_evidence_changes(self):
        self.data['completed'] = ['BACKUP_VERIFIED']; self.save()
        self.ops._backup = lambda data: {'backup_sha256': 'e' * 64}
        first = self.ops._observe('BACKUP_VERIFIED')
        self.ops._backup = lambda data: {'backup_sha256': 'f' * 64}
        self.assertNotEqual(first, self.ops._observe('BACKUP_VERIFIED'))

    def test_live_bytes_without_durable_completed_marker_are_not_completion(self):
        self.data['intent'] = 'BACKUP_VERIFIED'; self.save()
        self.ops._backup = Mock(return_value={'backup_sha256': 'e' * 64})
        with self.assertRaises(Denied): self.ops._observe('BACKUP_VERIFIED')
        self.ops._backup.assert_not_called()

    def test_reconcile_complete_uses_no_effect_lease_and_writes_no_receipt(self):
        self.data['completed'] = ['BACKUP_VERIFIED']; self.save()
        self.ops._backup = lambda data: {'backup_sha256': 'e' * 64}
        before = self.ops.t.receipt.read_bytes(); lease = Lease()
        proof = self.ops.reconcile('BACKUP_VERIFIED', {}, None, lease)
        self.assertEqual(proof['status'], 'COMPLETE'); self.assertEqual(lease.active_calls, 0)
        self.assertEqual(before, self.ops.t.receipt.read_bytes())

    def test_initialization_gap_does_not_retry_existing_empty_child(self):
        before = self.ops.t.receipt.read_bytes()
        proof = self.ops.reconcile('BACKUP_VERIFIED', {}, None, Lease())
        self.assertEqual(proof['status'], 'UNKNOWN')
        self.assertEqual(before, self.ops.t.receipt.read_bytes())

    def test_only_wholly_absent_initial_transaction_can_retry(self):
        self.ops.t.receipt.unlink(); self.ops.t.folder.rmdir()
        self.assertEqual(self.ops.reconcile('BACKUP_VERIFIED', {}, None, Lease())['status'], 'SAFE_TO_RETRY')
        residual = self.ops.c.BASE / ('.staging-' + self.ops.t.id)
        residual.parent.mkdir(); residual.mkdir()
        self.assertEqual(self.ops.reconcile('BACKUP_VERIFIED', {}, None, Lease())['status'], 'UNKNOWN')

    def test_exact_next_step_boundary_can_retry_but_pending_intent_cannot(self):
        self.data['completed'] = ['BACKUP_VERIFIED']; self.save()
        self.ops._backup = lambda data: {'backup_sha256': 'e' * 64}
        self.assertEqual(self.ops.reconcile('SEALED_BUNDLE', {}, None, Lease())['status'], 'SAFE_TO_RETRY')
        self.data['intent'] = 'SEALED_BUNDLE'; self.save()
        self.assertEqual(self.ops.reconcile('SEALED_BUNDLE', {}, None, Lease())['status'], 'UNKNOWN')

    def test_previous_checkpoint_drift_blocks_clean_next_step_retry(self):
        self.data['completed'] = ['BACKUP_VERIFIED']; self.save()
        self.ops._backup = Mock(side_effect=Denied('fixture backup drift'))
        self.assertEqual(self.ops.reconcile('SEALED_BUNDLE', {}, None, Lease())['status'], 'UNKNOWN')

    def test_unknown_reload_is_not_replayed_or_inferred_from_pointer(self):
        self.data['completed'] = list(static.STATIC_STAGES[:7]); self.data['intent'] = 'NGINX_RELOADED'; self.save()
        self.ops._activated = Mock(return_value={'active': True})
        self.ops._nginx = Mock(return_value={'staged': True})
        self.ops._runtime = Mock(return_value={'runtime': True})
        self.assertEqual(self.ops.reconcile('NGINX_RELOADED', {}, None, Lease())['status'], 'UNKNOWN')
        self.ops._activated.assert_not_called()

    def test_unknown_smoke_is_not_replayed(self):
        self.data['completed'] = list(static.STATIC_STAGES[:8]); self.data['intent'] = 'HTTPS_SMOKE'; self.save()
        self.ops._static_https = Mock(return_value={'real_https': True})
        self.assertEqual(self.ops.reconcile('HTTPS_SMOKE', {}, None, Lease())['status'], 'UNKNOWN')
        self.ops._static_https.assert_not_called()

    def test_completed_smoke_without_durable_result_stays_unknown(self):
        self.data['completed'] = list(static.STATIC_STAGES[:9]); self.save()
        self.ops._activated = lambda: {'active': True}; self.ops._nginx = lambda: {'staged': True}
        self.ops._runtime = lambda data: {'runtime': True}
        self.ops._static_https = lambda: {'real_https': True}
        self.assertEqual(self.ops.reconcile('HTTPS_SMOKE', {}, None, Lease())['status'], 'UNKNOWN')

    def test_fresh_absence_rejects_broken_symlink_residual(self):
        self.ops.t.receipt.unlink(); self.ops.t.folder.rmdir()
        os.symlink(self.temp.name + '/missing', self.ops.t.folder)
        self.assertFalse(self.ops._fresh_absent())

    def test_short_or_expired_phase_window_admits_no_effects(self):
        lease = SimpleNamespace(authority=Mock(), assert_active=Mock())
        self.ops._initialize = Mock(side_effect=AssertionError('Effects must not start'))
        before = self.ops.t.receipt.read_bytes()
        for remaining in (-1, 0, 599.999):
            with self.subTest(remaining=remaining), patch.object(static.time, 'time', return_value=1000):
                self.approval['expires_unix'] = 1000 + remaining
                with self.assertRaisesRegex(Denied, 'STATIC_PHASE_AUTHORIZATION_WINDOW'):
                    self.ops.execute('BACKUP_VERIFIED', lease)
        self.ops._initialize.assert_not_called()
        self.assertEqual(before, self.ops.t.receipt.read_bytes())

    def test_phase_admission_sets_original_deadline_within_lease(self):
        lease = SimpleNamespace(authority=Mock(), assert_active=Mock())
        self.approval['expires_unix'] = 1600
        with patch.object(static.time, 'time', return_value=1000), patch.object(static.time, 'monotonic', return_value=50):
            self.ops._admit(lease)
        self.assertEqual(self.ops.t.deadline, 650)

    def actual_backup_fixture(self, count=2, schema='FULL_STATIC_REVIEW_V1'):
        """Real temp manifest/config/archive bytes; no original helper execution."""
        root = Path(self.temp.name)
        inputs = root / 'inputs'; inputs.mkdir()
        previous = root / 'previous-release'; metadata = previous / 'release-metadata'
        metadata.mkdir(parents=True)
        conf = b'add_header Content-Security-Policy "default-src self" always;\n'
        meta_json = b'{"policy":"default-src self"}\n'
        (metadata / 'inline-csp.conf').write_bytes(conf)
        (metadata / 'inline-csp.json').write_bytes(meta_json)
        public = {'file-%04d.txt' % number: ('public-%d' % number).encode() for number in range(count)}
        manifest = {name: {'size': len(raw), 'sha256': digest(raw)} for name, raw in public.items()}
        manifest_raw = canonical({'files': [{'path': name, **row} for name, row in manifest.items()]})
        (inputs / 'R2_CANDIDATE_MANIFEST.json').write_bytes(manifest_raw)
        nginx = root / 'nginx.conf'; nginx_raw = b'fixture-config'; nginx.write_bytes(nginx_raw)
        backup = self.ops.t.folder / 'backup'; backup.mkdir(mode=0o700)
        (backup / 'config-0').write_bytes(nginx_raw); (backup / 'config-0').chmod(0o600)
        payloads = {'public/' + name: raw for name, raw in public.items()}
        payloads.update({'release-metadata/inline-csp.conf': conf, 'release-metadata/inline-csp.json': meta_json})
        self.ops.t.pins.update(package_schema=schema, previous_file_count=count,
            previous_release=str(previous), previous_manifest_sha256=digest(manifest_raw),
            nginx={str(nginx): digest(nginx_raw)})
        self.ops.t.inputs = inputs
        self.ops.c.trusted = lambda path, directory=False: None
        self.data.update(previous_link=str(previous), backup={'archive_verified': True,
            'static_files': manifest, 'nginx': {str(nginx): {
                'copy': 'config-0', 'sha256': digest(nginx_raw), 'mode': 0o644}}})
        self.write_actual_backup_archive(payloads.items())
        return payloads

    def write_actual_backup_archive(self, rows):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, raw in rows:
                member = tarfile.TarInfo(name); member.size = len(raw); member.mode = 0o644
                archive.addfile(member, io.BytesIO(raw))
        raw = stream.getvalue(); path = self.ops.t.folder / 'backup/previous-static.tar.gz'
        path.write_bytes(raw); path.chmod(0o600)
        self.data['backup']['static_sha256'] = digest(raw)

    def test_full_backup_verifies_real_two_file_manifest_and_four_member_archive(self):
        self.actual_backup_fixture(count=2)
        effect = self.ops._backup(self.data)
        self.assertEqual(effect['archive_sha256'], self.data['backup']['static_sha256'])
        self.assertEqual(effect['manifest_sha256'], digest(canonical(self.data['backup']['static_files'])))

    def test_brand_backup_retains_full_dynamic_count_and_hash_validation(self):
        self.actual_backup_fixture(count=2, schema='FULL_STATIC_BRAND_REVIEW_V1')
        self.assertEqual(self.ops._backup(self.data)['archive_sha256'], self.data['backup']['static_sha256'])
        self.ops.t.pins['previous_file_count'] = 3
        with self.assertRaisesRegex(Denied, 'STATIC_BACKUP_MANIFEST'): self.ops._backup(self.data)
        self.ops.t.pins['previous_file_count'] = True
        with self.assertRaisesRegex(Denied, 'STATIC_PREVIOUS_FILE_COUNT'): self.ops._backup(self.data)

    def test_full_backup_requires_strict_bounded_integer_count(self):
        self.actual_backup_fixture(count=2)
        for count in (None, True, False, '2', 2.0, 0, -1, 10001):
            with self.subTest(count=count):
                self.ops.t.pins['previous_file_count'] = count
                with self.assertRaisesRegex(Denied, 'STATIC_PREVIOUS_FILE_COUNT'):
                    self.ops._backup(self.data)

    def test_full_backup_pinned_count_must_match_actual_manifest(self):
        self.actual_backup_fixture(count=2)
        self.ops.t.pins['previous_file_count'] = 3
        with self.assertRaisesRegex(Denied, 'STATIC_BACKUP_MANIFEST'): self.ops._backup(self.data)

    def test_full_backup_archive_count_is_exact_pinned_count_plus_two(self):
        payloads = self.actual_backup_fixture(count=2)
        self.write_actual_backup_archive(list(payloads.items()) + [('public/extra.txt', b'extra')])
        with self.assertRaisesRegex(Denied, 'STATIC_BACKUP_MEMBERS'): self.ops._backup(self.data)

    def test_full_backup_rejects_duplicate_archive_member_at_correct_total_count(self):
        payloads = self.actual_backup_fixture(count=2)
        rows = list(payloads.items()); rows[-1] = rows[0]
        self.write_actual_backup_archive(rows)
        with self.assertRaisesRegex(Denied, 'STATIC_BACKUP_MEMBERS'): self.ops._backup(self.data)

    def test_legacy_backup_defaults_to_1279_even_if_smaller_count_pin_is_present(self):
        self.actual_backup_fixture(count=2, schema='LEGACY_UNIFIED_V1')
        with self.assertRaisesRegex(Denied, 'STATIC_BACKUP_MANIFEST'): self.ops._backup(self.data)

    def test_legacy_backup_real_1279_file_archive_remains_valid_without_schema_or_count_pin(self):
        self.actual_backup_fixture(count=1279, schema='LEGACY_UNIFIED_V1')
        del self.ops.t.pins['package_schema']; del self.ops.t.pins['previous_file_count']
        self.assertEqual(self.ops._backup(self.data)['archive_sha256'], self.data['backup']['static_sha256'])

    def test_http_expiry_or_fence_loss_never_posts_or_clears_step_intent(self):
        for reason in ('WORKFLOW_LEASE_EXPIRED', 'WORKFLOW_FENCE_LOST'):
            with self.subTest(reason=reason):
                active = [True]; writes = []
                def guard():
                    if not active[0]: raise Denied('HOLD:' + reason)
                lease = SimpleNamespace(assert_active=guard)
                def atomic(path, value):
                    guard(); writes.append(copy.deepcopy(value)); path.write_bytes(canonical(value)); path.chmod(0o600)
                self.ops._effect_helpers = lambda lease: SimpleNamespace(atomic=atomic)
                self.ops.t.data = copy.deepcopy(self.data)
                self.ops.t.data['completed'] = list(static.STATIC_STAGES[:8])
                self.ops.t.deadline = time.monotonic() + 600
                self.ops.t.entries = {'overlay/public/index.html': b'page'}
                self.ops.u = SimpleNamespace(smoke_routes=lambda entries: {'/': ('file', '/index.html')})
                def request(route, **kwargs):
                    self.assertEqual(kwargs, {'https': True})
                    if route == '/': return 200, {'content-security-policy': 'policy', 'x-content-type-options': 'nosniff'}, b'page'
                    active[0] = False  # Authorization lost during the last GET.
                    return 404, {}, b''
                self.ops.t.ops = SimpleNamespace(request=Mock(side_effect=request),
                    smoke=Mock(side_effect=AssertionError('Synthetic smoke forbidden')),
                    preview_probe=Mock(side_effect=AssertionError('Preview POST forbidden')))
                with self.assertRaisesRegex(Denied, reason):
                    self.ops._step('HTTPS_SMOKE', lambda: self.ops._static_https(lease), lease)
                receipt = json.loads(self.ops.t.receipt.read_bytes())
                self.assertEqual(receipt['intent'], 'HTTPS_SMOKE')
                self.assertEqual(receipt['completed'], list(static.STATIC_STAGES[:8]))
                self.assertEqual(len(writes), 1)
                self.assertEqual(self.ops.t.ops.request.call_count, 2)
                self.ops.t.ops.smoke.assert_not_called(); self.ops.t.ops.preview_probe.assert_not_called()

    def test_expiry_after_action_returns_keeps_pending_completion_receipt(self):
        active = [True]
        def guard():
            if not active[0]: raise Denied('HOLD:WORKFLOW_LEASE_EXPIRED')
        lease = SimpleNamespace(assert_active=guard)
        def atomic(path, value): guard(); path.write_bytes(canonical(value)); path.chmod(0o600)
        self.ops._effect_helpers = lambda lease: SimpleNamespace(atomic=atomic)
        self.ops.t.data = copy.deepcopy(self.data); self.ops.t.deadline = time.monotonic() + 600
        def action(): active[0] = False; return None
        with self.assertRaisesRegex(Denied, 'WORKFLOW_LEASE_EXPIRED'):
            self.ops._step('BACKUP_VERIFIED', action, lease)
        receipt = json.loads(self.ops.t.receipt.read_bytes())
        self.assertEqual(receipt['intent'], 'BACKUP_VERIFIED'); self.assertEqual(receipt['completed'], [])


class CoordinatorAdapterFixtureTests(unittest.TestCase):
    """Real Coordinator + real adapter dispatch/journal interface, simulated effects.

    This deliberately bypasses the production adapter constructor, source gate
    and host-effect verifiers. It does not import the original root helpers and
    must never be described as original writer or production integration proof.
    """
    def setUp(self):
        import fcntl
        import time
        from scripts import pr122_customer_workflow as workflow
        from scripts import pr122_static_workflow as profile
        self.workflow, self.profile = workflow, profile
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); state = self.root / 'state'; state.mkdir(mode=0o700)
        self.lock = self.root / 'transaction.lock'; self.lock.write_bytes(b''); self.lock.chmod(0o600)
        self.fd = os.open(self.lock, os.O_RDWR); self.addCleanup(os.close, self.fd)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        self.events = []; self.failure = None; self.failures_left = 0
        self.ops = static.OriginalStaticOperations.__new__(static.OriginalStaticOperations)
        self.ops.coordinator = None
        self.ops._bind_source = lambda: {'wrapper_sha256': 'b' * 64, 'pins_sha256': 'c' * 64}
        self.ops.implementation = lambda stage: b'OFFLINE SIMULATED EFFECT BACKEND'
        base = self.root / 'base'; (base / 'releases').mkdir(parents=True)
        (base / 'transactions').mkdir()
        self.previous = str(base / 'releases/previous'); self.target = str(base / 'releases/candidate')
        os.symlink(self.previous, base / 'current')
        self.old_files = {'old.txt': {'size': 3, 'sha256': digest(b'old')}}
        self.publisher_receipt = None
        self.locations = self.root / 'locations.conf'; self.locations.write_bytes(b'old')
        pins = {'release_id': 'candidate', 'previous_release': self.previous,
            'static_artifact_sha256': 'd' * 64, 'package_manifest_sha256': 'e' * 64,
            'source_archive_sha256': 'f' * 64, 'nginx': {str(self.locations): digest(b'old')}}
        self.ops.c = SimpleNamespace(BASE=base, LOCATIONS=self.locations,
            mkdir=lambda path, mode: path.mkdir(mode=mode), atomic=self.atomic,
            read=lambda path: Path(path).read_bytes(), write=self.write)
        self.ops.u = SimpleNamespace(routes=lambda entries: (b'staged', {}), smoke_routes=lambda entries: {})
        t = SimpleNamespace(id='fixture-static', folder=state / 'fixture-static', pins=pins,
            entries={}, inputs=self.root, bind_inputs=lambda: None, inventory=lambda expected: None,
            snapshot=lambda: copy.deepcopy(self.old_files), sandbox={'pid': 2}, nginx_identity={'pid': 1})
        t.receipt = t.folder / 'receipt.json'; t.baseline = lambda: copy.deepcopy(self.old_files)
        t.runtime = lambda: {'pid': 2}; t.load_publisher = lambda: None
        t.ops = SimpleNamespace(nginx_identity=lambda: {'pid': 1},
            nginx_test=lambda: self.effect('nginx_test'), reload_nginx=lambda: self.effect('reload'),
            smoke=lambda entries, routes: self.smoke())
        t.backup = self.backup; t.seal_bundle = lambda: self.effect('seal')
        t.publisher = self.publisher; t.step = self.step
        self.ops.t = t
        # These stand-ins expose simulated live state to the real _observe.
        self.ops._backup = lambda data: {'backup': 'fixture-valid'}
        self.ops._bundle = lambda: {'bundle': 'fixture-valid'}
        self.ops._nginx = lambda: {'nginx': 'fixture-valid'}
        self.ops._publisher = self.publisher_observe
        self.ops._static_https = self.readonly_http
        self.ops._original_action = lambda name, lease, *args: getattr(self.ops.t, name)(*args)
        self.ops._publisher_action = lambda action, lease: self.publisher(action)
        source = {'source_commit': 'a' * 40}; source_raw = canonical(source)
        self.plan = {'source_commit': 'a' * 40, 'manifest_sha256': digest(source_raw),
            'deployment_profile': profile.PROFILE, 'permit_window_seconds': 18000,
            'static_baseline_sha256': '1' * 64, 'host_pins_sha256': '2' * 64}
        self.ops.plan = copy.deepcopy(self.plan)
        self.ops.inputs = {stage: self.ops.expected_input(stage) for stage in static.STATIC_STAGES}
        self.plan['workflow_contract'] = {'schema': 1, 'stages': [{
            'stage': stage, 'input_sha256': digest(canonical(self.ops.input(stage))),
            'implementation_sha256': digest(self.ops.implementation(stage)),
            'adopt_receipt_sha256': None, 'recovery_actions': ['RECONCILE_STATIC']
        } for stage in static.STATIC_STAGES]}
        now = int(time.time())
        self.approval = {'issued_unix': now - 1, 'expires_unix': now - 1 + 18000,
            'attempt_policy': profile.POLICY, 'max_executions': 5,
            'workflow_contract_sha256': digest(canonical(self.plan['workflow_contract'])),
            **{key: self.plan[key] for key in ('deployment_profile', 'permit_window_seconds',
                                              'static_baseline_sha256', 'host_pins_sha256')}}
        self.release = SimpleNamespace(STATE=state, TXN=t.id, LOCK=self.lock,
            gate=lambda comment, plan: copy.deepcopy(self.approval),
            source=lambda folder: (source, source_raw, {}), atomic_json=self.atomic)
        self.coordinator = profile.StaticCoordinator(self.release, self.root, 1, self.plan,
                                                    self.approval, self.ops, self.fd)
        for context in (patch.object(workflow, 'read_private', lambda path: json.loads(Path(path).read_bytes())),
                        patch.object(workflow, 'protected_directory', lambda path: None)):
            context.start(); self.addCleanup(context.stop)

    def atomic(self, path, value):
        path.write_bytes(canonical(value)); path.chmod(0o600)

    def write(self, path, raw, expected=None):
        self.assertEqual(digest(path.read_bytes()), expected); path.write_bytes(raw); self.effect('stage_nginx')

    def effect(self, name):
        self.events.append(name)
        if self.failure == name and self.failures_left:
            self.failures_left -= 1; raise RuntimeError('simulated phase uncertainty')

    def backup(self, files):
        self.effect('backup'); self.ops.t.data['backup'] = {'static_files': copy.deepcopy(files)}
        self.ops.t.data['previous_link'] = self.previous

    def publisher(self, action):
        self.effect(action)
        if action == 'prepare':
            self.publisher_receipt = {'state': 'PREPARED', 'release': self.target,
                'candidate_manifest_sha256': 'a' * 64, 'source_pin_sha256': 'b' * 64,
                'package_manifest_sha256': 'e' * 64, 'source_archive_sha256': 'f' * 64,
                'release_envelope': {}, 'csp_inventory': {}}
        elif action == 'activate':
            self.publisher_receipt.update(state='ACTIVATED', target_current=self.target,
                                          previous_current={'link': self.previous})
            current = self.ops.c.BASE / 'current'; current.unlink(); os.symlink(self.target, current)
        elif action == 'check': self.publisher_receipt['state'] = 'CHECKED'
        return self.publisher_receipt

    def publisher_observe(self, states):
        if self.publisher_receipt is None or self.publisher_receipt['state'] not in states:
            raise Denied('Fixture publisher receipt unproven')
        return copy.deepcopy(self.publisher_receipt)

    def readonly_http(self, lease=None):
        if lease is not None:
            lease.assert_active(); self.effect('readonly_http')
        return {'manifest_routes_checked': 0, 'real_https': True, 'production_browser': 'PENDING',
                'state': 'STATIC_READONLY_HTTP_COMPLETE', 'business_e2e': 'PENDING', 'preview_post': 'PENDING'}

    def smoke(self):
        self.effect('synthetic_smoke')
        return {'manifest_routes_checked': 0, 'real_https': True, 'production_browser': 'PENDING'}

    def step(self, stage, action):
        # Exact original helper intent/completion ordering, confined to tmpdir.
        t = self.ops.t; t.data['intent'] = stage; self.atomic(t.receipt, t.data)
        value = action(); t.data['completed'].append(stage); t.data['intent'] = None
        self.atomic(t.receipt, t.data); return value

    def test_real_coordinator_and_adapter_dispatch_ten_phases_on_one_attempt(self):
        result = self.coordinator.run()
        self.assertEqual(result['state'], 'SUCCESS'); self.assertEqual(result['attempts_used'], 1)
        self.assertEqual(result['completed_stages'], list(static.STATIC_STAGES))
        self.assertEqual(self.events, ['backup', 'seal', 'prepare', 'stage_nginx', 'nginx_test',
                                       'activate', 'reload', 'readonly_http', 'check'])
        self.assertEqual(json.loads(self.ops.t.receipt.read_bytes())['state'], static.STATIC_SUCCESS)
        ledger = json.loads(self.coordinator.path.read_bytes())
        self.assertEqual(len(ledger['attempts']), 1)
        self.assertEqual(set(ledger['checkpoints']), set(static.STATIC_STAGES))
        self.assertNotIn('attempts', json.loads(self.ops.t.receipt.read_bytes()))

    def test_real_coordinator_holds_unknown_reload_and_does_not_consume_retry(self):
        self.failure = 'reload'; self.failures_left = 1
        with self.assertRaises(self.workflow.WorkflowStopped) as caught: self.coordinator.run()
        self.assertEqual(caught.exception.summary['state'], 'HOLD')
        self.assertEqual(caught.exception.summary['attempts_used'], 1)
        self.assertEqual(self.events.count('reload'), 1)
        self.assertNotIn('synthetic_smoke', self.events)
        self.assertNotIn('readonly_http', self.events)
        self.assertEqual(json.loads(self.ops.t.receipt.read_bytes())['intent'], 'NGINX_RELOADED')
        self.assertEqual(json.loads(self.coordinator.path.read_bytes())['intent']['stage'], 'NGINX_RELOADED')


class PrivateGuardTests(unittest.TestCase):
    """Execute authored tempfile fixtures, never original root helper code."""
    FIXTURE = r'''import os
from pathlib import Path

def backup(root):
    root = Path(root)
    root.mkdir()
    for name in ('first', 'second'):
        fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try: os.write(fd, b'backup')
        finally: os.close(fd)
        tick('backup_' + name)

def seal(root):
    root = Path(root)
    root.mkdir()
    (root / 'one').write_bytes(b'one')
    tick('seal_one')
    os.chmod(root, 0o755)
    (root / 'two').write_bytes(b'two')

def csp(root):
    metadata = Path(root) / 'metadata'
    metadata.mkdir()
    (metadata / 'inline-csp.conf').write_text('policy')
    tick('csp_conf')
    (metadata / 'inline-csp.json').write_text('{}')

def activate(root):
    root = Path(root)
    os.symlink('candidate', root / 'temp')
    tick('activation_temp')
    os.replace(root / 'temp', root / 'current')

def atomic_json(path):
    path = Path(path)
    temporary = path.with_name('.receipt.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try: os.write(fd, b'completed')
    finally: os.close(fd)
    tick('receipt_before_replace')
    os.replace(temporary, path)

def failure_receipt(root):
    try: csp(root)
    except BaseException:
        atomic_json(Path(root) / 'failure.json')
        raise

def builtin_write(path):
    with open(path, 'w') as handle: handle.write('not supported')

def path_open_write(path):
    with Path(path).open('wb') as handle: handle.write(b'not supported')
'''

    def setUp(self):
        import types
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 0; self.expiry = 10; self.fence = True; self.break_at = None; self.break_kind = 'expiry'
        self.module = types.ModuleType('authored_guard_fixture')
        exec(compile(self.FIXTURE, '<authored-tempfile-fixture>', 'exec'), vars(self.module))
        self.module.tick = self.tick
        self.guarded = static._guarded_namespace(self.module, self.guard)

    def guard(self):
        if self.now >= self.expiry: raise Denied('HOLD:WORKFLOW_LEASE_EXPIRED')
        if not self.fence: raise Denied('HOLD:WORKFLOW_FENCE_LOST')

    def tick(self, label):
        if label == self.break_at:
            if self.break_kind == 'expiry': self.now = self.expiry
            else: self.fence = False

    def broken(self, at, kind):
        self.break_at = at; self.break_kind = kind

    def test_private_namespace_does_not_patch_original_os_path_or_functions(self):
        import os as real_os
        self.assertIs(self.module.os, real_os)
        self.assertIs(self.module.Path, Path)
        self.assertIsNot(self.guarded['os'], real_os)
        self.assertIsNot(self.guarded['Path'], Path)
        self.assertIs(self.guarded['backup'].__code__, self.module.backup.__code__)
        self.assertIsNot(self.guarded['backup'].__globals__, self.module.backup.__globals__)

    def test_expiry_or_fence_loss_mid_backup_blocks_next_file(self):
        for kind in ('expiry', 'fence'):
            with self.subTest(kind=kind):
                self.now = 0; self.fence = True; self.broken('backup_first', kind)
                root = self.root / kind
                with self.assertRaises(Denied): self.guarded['backup'](root)
                self.assertEqual((root / 'first').read_bytes(), b'backup')
                self.assertFalse((root / 'second').exists())

    def test_expiry_or_fence_loss_mid_seal_blocks_chmod_and_next_file(self):
        for kind in ('expiry', 'fence'):
            with self.subTest(kind=kind):
                self.now = 0; self.fence = True; self.broken('seal_one', kind)
                root = self.root / kind
                with self.assertRaises(Denied): self.guarded['seal'](root)
                self.assertEqual((root / 'one').read_bytes(), b'one')
                self.assertFalse((root / 'two').exists())

    def test_expiry_or_fence_loss_between_csp_writes_blocks_second_write(self):
        for kind in ('expiry', 'fence'):
            with self.subTest(kind=kind):
                self.now = 0; self.fence = True; self.broken('csp_conf', kind)
                root = self.root / kind; root.mkdir()
                with self.assertRaises(Denied): self.guarded['csp'](root)
                self.assertEqual((root / 'metadata/inline-csp.conf').read_text(), 'policy')
                self.assertFalse((root / 'metadata/inline-csp.json').exists())

    def test_expiry_or_fence_loss_between_symlink_and_replace_preserves_pointer(self):
        for kind in ('expiry', 'fence'):
            with self.subTest(kind=kind):
                self.now = 0; self.fence = True; self.broken('activation_temp', kind)
                root = self.root / kind; root.mkdir(); os.symlink('previous', root / 'current')
                with self.assertRaises(Denied): self.guarded['activate'](root)
                self.assertEqual(os.readlink(root / 'current'), 'previous')
                self.assertEqual(os.readlink(root / 'temp'), 'candidate')

    def test_expiry_or_fence_loss_before_atomic_replace_keeps_intent_receipt(self):
        for kind in ('expiry', 'fence'):
            with self.subTest(kind=kind):
                self.now = 0; self.fence = True; self.broken('receipt_before_replace', kind)
                root = self.root / kind; root.mkdir(); receipt = root / 'receipt.json'; receipt.write_bytes(b'pending-intent')
                with self.assertRaises(Denied): self.guarded['atomic_json'](receipt)
                self.assertEqual(receipt.read_bytes(), b'pending-intent')
                self.assertEqual((root / '.receipt.tmp').read_bytes(), b'completed')

    def test_expired_failure_handler_cannot_write_another_receipt(self):
        self.broken('csp_conf', 'expiry')
        with self.assertRaises(Denied): self.guarded['failure_receipt'](self.root)
        self.assertFalse((self.root / 'failure.json').exists())
        self.assertFalse((self.root / '.receipt.tmp').exists())

    def test_mutating_open_flags_guard_before_create_or_truncate(self):
        protected = self.root / 'existing'; protected.write_bytes(b'preserved')
        self.now = self.expiry
        for flags in (os.O_WRONLY, os.O_RDWR, os.O_RDONLY | os.O_CREAT, os.O_WRONLY | os.O_TRUNC):
            with self.subTest(flags=flags), self.assertRaises(Denied):
                self.guarded['os'].open(protected, flags, 0o600)
        self.assertEqual(protected.read_bytes(), b'preserved')

    def test_unbuffered_path_write_checks_each_write_after_open(self):
        actual_open = os.open
        def expires_after_open(*args, **kwargs):
            fd = actual_open(*args, **kwargs); self.now = self.expiry; return fd
        path = self.root / 'started'
        with patch.object(static.os, 'open', side_effect=expires_after_open):
            with self.assertRaises(Denied): self.guarded['Path'](path).write_bytes(b'must-not-be-written')
        self.assertEqual(path.read_bytes(), b'')

    def test_unreviewed_buffered_writer_paths_fail_closed(self):
        for name in ('builtin_write', 'path_open_write'):
            path = self.root / name
            with self.subTest(name=name), self.assertRaisesRegex(Denied, 'STATIC_BUFFERED_WRITE_FORBIDDEN'):
                self.guarded[name](path)
            self.assertFalse(path.exists())


if __name__ == '__main__': unittest.main()
