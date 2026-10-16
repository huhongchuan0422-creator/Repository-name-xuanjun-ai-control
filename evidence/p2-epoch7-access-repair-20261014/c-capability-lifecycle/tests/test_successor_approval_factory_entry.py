"""Successor-only local tests; actual pure factories, synthetic private boundaries.

Imports original public fixture builders, never runs their old suites. Runtime
source payloads and compiler paths are real; the original fixture's four missing
private native pins are mapped ONLY by native_pins. All approval responses,
review IDs, source pins, predecessor measurement hashes and loader file buffers
below are explicitly synthetic. No production filesystem, network, commands,
review publication, lock acquisition, claim publication or phase is invoked.
"""
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import pathlib
import sys
import subprocess
import types
import unittest
from unittest import mock

CANDIDATE = pathlib.Path(__file__).resolve().parents[1]
BASELINE = CANDIDATE / 'baseline'
OVERLAY = CANDIDATE / 'kit-overlay'
# Only fixture definitions are imported. unittest discovers this file alone.
PATHS = [OVERLAY / 'helpers', BASELINE / 'helpers', BASELINE / 'xuanjun-p2-package/stage1']
PATHS += sorted(path for path in (BASELINE / 'tests').iterdir() if path.is_dir())
sys.path[:0] = [str(path) for path in PATHS]
sys.dont_write_bytecode = True

import epoch7_approval as base_approval
import epoch7_claim_successor as claim
import epoch7_complete_approval as approval
import epoch7_delta as delta
import epoch7_host_factory as factory
import epoch7_recovery_sequence as sequence
from test_epoch7_full_factory_fixture import native_pins

SPEC = importlib.util.spec_from_file_location('successor_test_entry', OVERLAY / 'epoch7_recovery_entry.py')
entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entry)

SYNTHETIC_REVIEW_ID = 7000000001
_FIXTURE = None


def synthetic_contract(kit_hash, expires='2099-01-01T00:00:00Z'):
    return {'schema': 1, 'kind': 'EXACT_CLAIM_ONLY_SUCCESSOR',
        'timing_policy': claim.TIMING_POLICY,
        'predecessor': claim.predecessor_contract(),
        'implementation': {'source_commit': 'a' * 40, 'source_tree': 'b' * 40,
                           'kit_manifest_sha256': kit_hash},
        'admission_expires_at_utc': expires, 'authorized_successors': 1, 'automatic_retry': False,
        'effect_scope': 'UNCHANGED_107_PAYLOADS_16_PHASES',
        'measured_predecessor_sha256': delta.digest('synthetic protected predecessor observation')}


def original_synthetic_seed():
    # A separate baseline-only interpreter keeps old fixture setup independent
    # of the deliberately incompatible successor gate API. No old test runs.
    result = subprocess.run([sys.executable, '-I', '-B', '-S',
        str(CANDIDATE / 'tests/synthetic_historical_seed.py')],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
    if len(result.stdout) > 64 * 1024 * 1024:
        raise ValueError('SYNTHETIC_FIXTURE_BOUND')
    def decode(node):
        kind, value = node
        if kind == 'bytes': return base64.b64decode(value, validate=True)
        if kind == 'dict': return {key: decode(child) for key, child in value}
        if kind in ('list', 'tuple'):
            values = [decode(child) for child in value]
            return tuple(values) if kind == 'tuple' else values
        if kind not in ('str', 'int', 'bool', 'NoneType'):
            raise ValueError('SYNTHETIC_FIXTURE_TYPE')
        return value
    return decode(json.loads(result.stdout))


def prepared_fixture():
    global _FIXTURE
    if _FIXTURE is None:
        original = original_synthetic_seed()
        seed = copy.deepcopy(original)
        seed['claim_successor'] = synthetic_contract(seed['kit_manifest_sha256'])
        before = factory.input_digest(seed)
        with native_pins(seed):
            result = factory.prepare_host_inputs(seed)
            assert result['state'] == 'COMPILED_NOT_ADMITTED'
            inputs = result['inputs']
            contract = factory.compile_host_contract(inputs)
        assert before == factory.input_digest(seed)
        _FIXTURE = (original, seed, inputs, contract)
    return copy.deepcopy(_FIXTURE)


def approval_fixture(expires='2099-01-01T00:00:00Z', bind=True):
    original, seed, inputs, contract = prepared_fixture()
    successor = synthetic_contract(seed['kit_manifest_sha256'], expires)
    gate = factory.RecoveryGate(inputs['snapshot'], inputs['candidate'], delta.digest(inputs['snapshot']),
        inputs['kit_manifest_sha256'], delta.digest(inputs['access_rows']), SYNTHETIC_REVIEW_ID,
        object(), object(), inputs['prior_provision_bytes'], additive_deltas=inputs['additive_deltas'],
        claim_successor=successor)
    wanted = approval.expected_complete('c' * 64, gate)
    bodies = [base_approval.MARKER + json.dumps(wanted, sort_keys=True)]
    body_hash = hashlib.sha256(bodies[0].encode()).hexdigest()
    lock = [False]
    calls = []
    def fetch(review_id, expected):
        calls.append((review_id, lock[0]))
        raw = json.dumps({'id': review_id, 'user': {'id': 332398908,
            'login': 'huhongchuan0422-creator'},
            'issue_url': 'https://api.github.com/repos/' + base_approval.REPO + '/issues/58',
            'body': bodies[0]}).encode()
        return base_approval.validate(raw, review_id, expected)
    verifier = approval.CompleteApprovalVerifier(SYNTHETIC_REVIEW_ID, body_hash, lambda: lock[0], fetch)
    gate.verifier = verifier
    if bind:
        verifier.bind(gate, 'c' * 64)
    return verifier, gate, lock, calls, bodies


def private_seed(seed):
    def utf8(value):
        if type(value) is bytes:
            return value.decode('utf-8')
        if type(value) is dict:
            return {key: utf8(child) for key, child in value.items()}
        if type(value) is list:
            return [utf8(child) for child in value]
        return value
    return utf8({key: seed[key] for key in entry.PRIVATE_SEED_FIELDS})


def fixture_kit(seed):
    runtime = entry.RUNTIME
    manifest = {'kit_source_commit': 'a' * 40, 'kit_source_tree': 'b' * 40,
        'runtime_source_commit': seed['artifact']['source_commit'],
        'runtime_source_tree': seed['artifact']['source_tree'],
        'runtime_manifest_sha256': seed['artifact']['manifest_sha256']}
    cache = {runtime + 'deploy/integration-manifest.json': seed['source_manifest_raw'],
             runtime + 'scripts/uk-integration-install.py': seed['installer_source']}
    cache.update({runtime + key: value for key, value in seed['source_payloads'].items()})
    return entry.VerifiedKit('/synthetic/authenticated-successor-kit', manifest, cache,
                             seed['kit_manifest_sha256'])


class SuccessorFactoryTests(unittest.TestCase):
    def test_real_factory_preserves_observation_and107_payloads(self):
        original, seed, inputs, contract = prepared_fixture()
        self.assertNotIn('claim_successor', original)
        self.assertEqual(original['observation'], inputs['observation'])
        self.assertEqual(original['observation']['snapshot'], inputs['snapshot'])
        self.assertEqual(original['observation']['evidence'], inputs['supporting_evidence'])
        self.assertEqual(original['source_payloads'], inputs['source_payloads'])
        self.assertEqual(len(inputs['source_payloads']), 107)
        self.assertEqual(len(inputs['resource_views']), 17)
        self.assertEqual(len(sequence.PHASES), 16)
        self.assertIn('claim_successor', factory.host_input_contract()['private_fields'])
        self.assertNotIn('claim_successor', factory.DERIVED_INPUTS)

    def test_actual_proposal_and17_views_bind_same_successor(self):
        original, seed, inputs, contract = prepared_fixture()
        with native_pins(seed):
            proposal = factory._proposal(inputs)
        computed_delta, authorization, neutral = proposal[1:4]
        self.assertEqual(authorization['claim_successor'], seed['claim_successor'])
        self.assertEqual(neutral['claim_successor'], seed['claim_successor'])
        self.assertEqual(computed_delta['new_attempt_name'], claim.NEW_INNER)
        self.assertEqual(neutral['inner_attempt_name'], claim.NEW_INNER)
        self.assertEqual(neutral['outer_receipt_name'], claim.NEW_OUTER)
        self.assertEqual(contract['host_contract']['sequence_contract_sha256'],
                         approval.sequence_contract_sha256(neutral))
        for view in inputs['resource_views']:
            rows = {row['path']: row for row in view['historical']}
            predecessor = rows[claim.TRANSACTION + '/' + claim.OLD_OUTER]
            self.assertEqual(predecessor['sha256'], claim.PREDECESSOR_SHA256)
            self.assertEqual(rows[claim.TRANSACTION + '/' + claim.OLD_INNER]['kind'], 'ABSENT')
            self.assertIn(claim.TRANSACTION + '/' + claim.NEW_INNER, rows)

    def test_real_assembly_constructs_claim_authority_without_effects(self):
        original, seed, inputs, contract = prepared_fixture()
        plan_raw = delta.canonical(contract) + b'\n'
        import os
        import socket
        metadata = types.SimpleNamespace(st_mode=0o40755, st_uid=0, st_gid=0,
            st_dev=8, st_ino=9001, st_nlink=2, st_size=4096,
            st_mtime_ns=11, st_ctime_ns=12)
        def root_open(path, flags, *args, **kwargs):
            if path != '/' or flags != factory.fs.DIR_FLAGS:
                raise AssertionError('Only synthetic root descriptor construction is allowed')
            return 98765
        def root_stat(path, *args, **kwargs):
            if str(path).startswith(str(CANDIDATE) + '/'):
                return metadata  # ExistingInstallLock asks only for metadata key shape.
            if path != '/': raise FileNotFoundError('Synthetic namespace has no other paths')
            return metadata
        def root_fstat(fd):
            if fd != 98765: raise AssertionError('No real descriptor may be inspected')
            return metadata
        def root_close(fd):
            if fd != 98765: raise AssertionError('No real descriptor may be closed')
        # Exact low-level host-identity/root-stamp boundary only. Every actual
        # constructor, type check, compiler, authority and gate is retained.
        with native_pins(seed), mock.patch.object(os, 'geteuid', return_value=0), \
             mock.patch.object(socket, 'gethostname', return_value=factory.snap.HOST), \
             mock.patch.object(os, 'open', side_effect=root_open), \
             mock.patch.object(os, 'lstat', side_effect=root_stat), \
             mock.patch.object(os, 'stat', side_effect=root_stat), \
             mock.patch.object(os, 'fstat', side_effect=root_fstat), \
             mock.patch.object(os, 'close', side_effect=root_close), \
             mock.patch.object(base_approval, 'fetch', side_effect=AssertionError('network forbidden')):
            driver = factory.assemble_host_driver(plan_raw, inputs, SYNTHETIC_REVIEW_ID, 'd' * 64)
        self.assertEqual(driver.context['claim_successor'], seed['claim_successor'])
        self.assertEqual(driver.context['inner_attempt_name'], claim.NEW_INNER)
        self.assertEqual(driver.context['outer_receipt_name'], claim.NEW_OUTER)
        self.assertEqual(driver.journal_io.authority.context, driver.context)
        self.assertIs(driver.journal_io.authority.verifier, driver.gate.verifier)
        # A detached gate copy tests the real binding serializer only. This
        # synthetic body hash is not authenticated admission and is never used.
        serializer = copy.copy(driver.gate)
        serializer.authorization = {'body_sha256': 'd' * 64}
        self.assertEqual(driver.journal_io.authority.binding, serializer.journal_binding())
        self.assertIsNone(driver.gate.authorization)
        self.assertFalse(driver.gate.verifier.checked_under_lock)
        self.assertIsNone(driver.gate.verifier.cached)
        self.assertEqual(driver.inner.name, claim.NEW_INNER)

    def test_missing_contract_refused_at_seed_boundary(self):
        original, seed, inputs, contract = prepared_fixture()
        with self.assertRaisesRegex(ValueError, 'COMPLETE_MEASURED_SEED'):
            factory.prepare_host_inputs(original)
        inputs.pop('claim_successor')
        with self.assertRaisesRegex(ValueError, 'EXACT_COMPLETE_MEASURED_INPUTS'):
            factory.compile_host_contract(inputs)

    def test_unbound_and_changed_kit_refuse_before_compilation(self):
        for value in ('UNBOUND', 'e' * 64):
            original, seed, inputs, contract = prepared_fixture()
            seed['claim_successor']['implementation']['kit_manifest_sha256'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'UNBOUND|SUCCESSOR_KIT_BINDING'):
                factory.prepare_host_inputs(seed)

    def test_changed_claim_cannot_reuse_old_plan(self):
        original, seed, inputs, contract = prepared_fixture()
        inputs['claim_successor']['measured_predecessor_sha256'] = 'f' * 64
        with native_pins(seed):
            changed = factory.compile_host_contract(inputs)
            self.assertNotEqual(changed['host_contract'], contract['host_contract'])
            with self.assertRaisesRegex(ValueError, 'REVIEWED_PLAN_BINDING'):
                factory.assemble_host_driver(delta.canonical(contract), inputs, SYNTHETIC_REVIEW_ID, 'd' * 64)


class SuccessorApprovalTests(unittest.TestCase):
    def test_new_body_schema_decision_and_exact_contract(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        self.assertEqual(verifier.wanted['schema'], 3)
        self.assertEqual(verifier.wanted['decision'], 'APPROVED_ONE_EXACT_EPOCH7_CLAIM_ONLY_SUCCESSOR')
        self.assertEqual(verifier.wanted['sequence_contract']['claim_successor'],
                         verifier.wanted['retained_authorization']['claim_successor'])
        self.assertNotEqual(verifier.body_sha, claim.OLD_REVIEW_SHA256)
        self.assertNotIn('review_id', verifier.wanted['sequence_contract'])

    def test_two_authenticated_fetches_then_cached_inner_verification(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        verifier.verify_outer_review(verifier.context)
        with self.assertRaisesRegex(ValueError, 'FRESH_LOCKED_VERIFICATION'):
            verifier.verify_exact(gate.review_id, gate.expected)
        lock[0] = True
        verifier.verify_outer_review(verifier.context)
        for unused in range(3):
            verifier.verify_exact(gate.review_id, gate.expected)
        self.assertEqual(calls, [(SYNTHETIC_REVIEW_ID, False), (SYNTHETIC_REVIEW_ID, True)])

    def test_original_review_id_and_body_hash_refused(self):
        for review_id, body_hash in ((claim.OLD_REVIEW_ID, 'd' * 64),
                                    (SYNTHETIC_REVIEW_ID, claim.OLD_REVIEW_SHA256)):
            with self.subTest(review_id=review_id), self.assertRaisesRegex(ValueError, 'FRESH_REVIEW|BODY_HASH'):
                approval.CompleteApprovalVerifier(review_id, body_hash, lambda: True)

    def test_original_review_cannot_be_reintroduced_with_rehashed_context(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        context = copy.deepcopy(verifier.context)
        context['review_id'] = claim.OLD_REVIEW_ID
        context.pop('context_sha256')
        context['context_sha256'] = approval.digest(context)
        with self.assertRaisesRegex(ValueError, 'FRESH_REVIEW'):
            approval.sequence_contract(context)

    def test_missing_changed_predecessor_or_names_rejected(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        neutral = verifier.wanted['sequence_contract']
        mutations = [lambda value: value.pop('claim_successor'),
            lambda value: value['claim_successor']['predecessor'].update(raw_sha256='f' * 64),
            lambda value: value.update(inner_attempt_name=claim.OLD_INNER),
            lambda value: value.update(outer_receipt_name=claim.OLD_OUTER),
            lambda value: value['claim_successor']['predecessor'].update(successor_inner_name='other.json')]
        for mutate in mutations:
            value = copy.deepcopy(neutral)
            mutate(value)
            with self.subTest(value=value.get('inner_attempt_name')), self.assertRaises(ValueError):
                approval.sequence_contract(value)

    def test_old_complete_body_rejected_and_prior_locked_proof_revoked(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        lock[0] = True
        verifier.verify_outer_review(verifier.context)
        old = copy.deepcopy(verifier.wanted)
        old.update(schema=2, decision='APPROVED_ONE_EXACT_EPOCH7_COMPLETE_RETAINED_RECOVERY')
        bodies[0] = base_approval.MARKER + json.dumps(old, sort_keys=True)
        with self.assertRaisesRegex(ValueError, 'EXACT_BINDING'):
            verifier.verify_outer_review(verifier.context)
        self.assertFalse(verifier.checked_under_lock)
        with self.assertRaisesRegex(ValueError, 'FRESH_LOCKED_VERIFICATION'):
            verifier.verify_exact(gate.review_id, gate.expected)

    def test_expired_binding_and_non_utc_grammar_refused(self):
        with self.assertRaisesRegex(ValueError, 'EXPIRED_OR_CLOCK'):
            approval_fixture(expires='2001-01-01T00:00:00Z')
        for expires in ('2099-01-01T00:00:00+00:00', '2099-01-01T00:00:00.0Z',
                        '2099-02-30T00:00:00Z', '2099-01-01t00:00:00z'):
            with self.subTest(expires=expires), self.assertRaisesRegex(ValueError, 'EXPIRY_'):
                approval_fixture(expires=expires)

    def test_cached_verifier_checks_wall_expiry_without_fetch(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        lock[0] = True
        verifier.verify_outer_review(verifier.context)
        expiry = claim.parse_expiry(gate.expected['claim_successor']['admission_expires_at_utc'])
        with mock.patch.object(approval.time, 'time', return_value=expiry):
            with self.assertRaisesRegex(ValueError, 'EXPIRED_OR_CLOCK'):
                verifier.verify_exact(gate.review_id, gate.expected)
        self.assertEqual(len(calls), 1)

    def test_backward_wall_clock_cannot_extend_monotonic_expiry(self):
        verifier, gate, lock, calls, bodies = approval_fixture(bind=False)
        expiry = claim.parse_expiry(gate.expected['claim_successor']['admission_expires_at_utc'])
        with mock.patch.object(approval.time, 'time', return_value=expiry - 5), \
             mock.patch.object(approval.time, 'monotonic', return_value=100):
            verifier.bind(gate, 'c' * 64)
        lock[0] = True
        with mock.patch.object(approval.time, 'time', return_value=expiry - 1000), \
             mock.patch.object(approval.time, 'monotonic', return_value=105):
            with self.assertRaisesRegex(ValueError, 'EXPIRED_OR_CLOCK'):
                verifier.verify_outer_review(verifier.context)
        self.assertEqual(calls, [])

    def test_expiry_crossed_during_fetch_cannot_grant_locked_authority(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        expiry, start, deadline = verifier.expiry_window
        lock[0] = True
        with mock.patch.object(approval.time, 'time', side_effect=[expiry - 1, expiry]), \
             mock.patch.object(approval.time, 'monotonic', return_value=start + 1):
            with self.assertRaisesRegex(ValueError, 'EXPIRED_OR_CLOCK'):
                verifier.verify_outer_review(verifier.context)
        self.assertFalse(verifier.checked_under_lock)
        self.assertIsNone(verifier.cached)
        self.assertEqual(len(calls), 1)

    def test_expiry_does_not_revoke_integrity_only_receipt_authority(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        lock[0] = True
        verifier.verify_outer_review(verifier.context)
        expiry = claim.parse_expiry(gate.expected['claim_successor']['admission_expires_at_utc'])
        with mock.patch.object(approval.time, 'time', return_value=expiry):
            verifier._bound()
            with self.assertRaisesRegex(ValueError, 'EXPIRED_OR_CLOCK'):
                verifier.check_admission_expiry()
        self.assertTrue(verifier.checked_under_lock)
        self.assertEqual(len(calls), 1)

    def test_boolean_or_caller_dictionary_cannot_seal_admission(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        lock[0] = True
        verifier.verify_outer_review(verifier.context)
        for forged in (True, {'stage': 'COMPLETE', 'outer_confirmed': True, 'inner_confirmed': True}):
            with self.subTest(forged=forged), self.assertRaisesRegex(ValueError, 'COMPLETED_CAPABILITY_REQUIRED'):
                verifier.seal_admission(forged)
        self.assertIsNone(verifier.admitted_capability)

    def test_mutated_cached_approval_refused_without_network(self):
        verifier, gate, lock, calls, bodies = approval_fixture()
        lock[0] = True
        verifier.verify_outer_review(verifier.context)
        verifier.cached['approval']['sequence_contract']['claim_successor']['authorized_successors'] = 2
        with self.assertRaisesRegex(ValueError, 'CACHED_AUTHORITY_MUTATED'):
            verifier.verify_exact(gate.review_id, gate.expected)
        self.assertEqual(len(calls), 1)


class SuccessorEntryTests(unittest.TestCase):
    def test_hydrate_crosschecks_current_authenticated_implementation(self):
        original, seed, inputs, contract = prepared_fixture()
        private = private_seed(seed)
        before = copy.deepcopy(private)
        kit = fixture_kit(seed)
        hydrated = kit._hydrate_seed(private, factory)
        self.assertEqual(private, before)
        self.assertEqual(hydrated['claim_successor'], seed['claim_successor'])
        self.assertEqual(hydrated['source_payloads'], original['source_payloads'])
        self.assertEqual(hydrated['kit_manifest_sha256'], kit.digest)
        self.assertEqual(set(hydrated), factory.INPUTS - factory.DERIVED_INPUTS)

    def test_hydrate_missing_or_changed_implementation_refuses(self):
        original, seed, inputs, contract = prepared_fixture()
        for key in ('source_commit', 'source_tree', 'kit_manifest_sha256'):
            private = private_seed(seed)
            private['claim_successor']['implementation'][key] = 'e' * (64 if key.endswith('sha256') else 40)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'IMPLEMENTATION_UNBOUND_OR_CHANGED'):
                fixture_kit(seed)._hydrate_seed(private, factory)
        private = private_seed(seed)
        private.pop('claim_successor')
        with self.assertRaisesRegex(ValueError, 'PRIVATE_SEED_SCHEMA'):
            fixture_kit(seed)._hydrate_seed(private, factory)

    def test_ordinary_resume_disabled_before_any_host_access(self):
        original, seed, inputs, contract = prepared_fixture()
        with mock.patch.object(entry.os, 'geteuid', side_effect=AssertionError('host lookup forbidden')):
            with self.assertRaisesRegex(ValueError, 'ORDINARY_RESUME_DISABLED'):
                fixture_kit(seed).resume()

    def test_successor_observation_and_probe_are_disabled_before_host_access(self):
        original, seed, inputs, contract = prepared_fixture()
        with self.assertRaisesRegex(ValueError, 'SUCCESSOR_OBSERVATION_OR_PROBE_DISABLED'):
            fixture_kit(seed).observe('/never-read')

    def test_manifest_requires_new_mode_and_new_helper_closure(self):
        manifest = json.loads((BASELINE / entry.MANIFEST).read_text())
        with self.assertRaisesRegex(ValueError, 'EXACT_SCOPE'):
            entry.validate_manifest(manifest)
        manifest['production_resume'] = entry.RESUME_COMPOSED
        manifest['status'] = entry.MODE_STATUS[entry.RESUME_COMPOSED]
        with self.assertRaisesRegex(ValueError, 'COMPOSITION_MODULES_REQUIRED'):
            entry.validate_manifest(manifest)
        name = 'helpers/epoch7_claim_successor.py'
        manifest['files'][name] = hashlib.sha256((OVERLAY / name).read_bytes()).hexdigest()
        manifest['modules']['epoch7_claim_successor'] = name
        self.assertIs(entry.validate_manifest(manifest), manifest)

    def test_old_private_paths_and_seed_schema_are_not_reused(self):
        original, seed, inputs, contract = prepared_fixture()
        kit = fixture_kit(seed)
        root = entry.CANDIDATE_PARENT
        with mock.patch.object(entry, 'DescriptorTree', side_effect=AssertionError('private read forbidden')):
            with self.assertRaisesRegex(ValueError, 'PRIVATE_INPUT_PATH'):
                kit._private_resume_inputs(root + '/epoch7-approved-plan-' + 'a' * 16 + '.private.json',
                    'a' * 64, root + '/epoch7-resume-inputs-' + 'b' * 16 + '.private.json', 'b' * 64)
        plan_name = 'epoch7-successor-approved-plan-' + 'a' * 16 + '.private.json'
        seed_name = 'epoch7-successor-resume-inputs-' + 'b' * 16 + '.private.json'
        plan_raw = delta.canonical(contract)
        for schema in (1, 2):
            seed_raw = delta.canonical({'schema': schema, 'seed': private_seed(seed)})
            class SyntheticReadOnlyTree:
                def __init__(self, *args): pass
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, name, maximum, private=False):
                    return {plan_name: plan_raw, seed_name: seed_raw}[name]
                def recheck(self): pass
            args = (root + '/' + plan_name, entry.sha(plan_raw), root + '/' + seed_name, entry.sha(seed_raw))
            with mock.patch.object(entry, 'DescriptorTree', SyntheticReadOnlyTree):
                if schema == 1:
                    with self.assertRaisesRegex(ValueError, 'PRIVATE_SEED_SCHEMA'):
                        kit._private_resume_inputs(*args)
                else:
                    raw, value, private = kit._private_resume_inputs(*args)
                    self.assertEqual(value, contract)
                    self.assertEqual(private['claim_successor'], seed['claim_successor'])

    def test_entry_has_only_explicit_successor_coordinator_call(self):
        tree = ast.parse((OVERLAY / 'epoch7_recovery_entry.py').read_text())
        methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'successor_resume']
        self.assertEqual(len(methods), 1)
        calls = [node for node in ast.walk(methods[0]) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == 'sequence']
        self.assertEqual([node.func.attr for node in calls], ['successor_resume_once', 'packed'])
        source = (OVERLAY / 'epoch7_recovery_entry.py').read_text()
        self.assertIn("'/epoch7-recovery-candidate-r7-claim-lifecycle'", source)
        self.assertNotIn("'/epoch7-recovery-candidate-r7-claim-successor'", source)
        self.assertNotIn("'/epoch7-recovery-candidate-r7-resourcebind'", source)


if __name__ == '__main__':
    unittest.main()
