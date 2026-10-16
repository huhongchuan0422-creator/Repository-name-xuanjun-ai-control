"""Focused, local successor transaction tests. No network or host effects.

Real RecoveryGate, CompleteApprovalVerifier, prepared capabilities, BoundJournal,
OuterJournal and protected fixture-root filesystem code are exercised. Fetching,
lock ownership, process/database observations and predecessor proof are explicit
SYNTHETIC boundaries. No fixture is authority or an authenticated public review.

The original 1641-byte predecessor is unavailable locally. The isolated validator
fixture substitutes fixed raw/binding/state pins in a test-only module copy; a
separate test proves the unmodified production pins refuse those synthetic bytes.
No old suite is run, no frozen source is edited, and no bytecode enters baseline.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

CANDIDATE = Path(__file__).resolve().parent.parent
BASELINE = CANDIDATE / 'baseline'
OVERLAY = CANDIDATE / 'kit-overlay'
REAL_PARENT_SHA = 'a5602f7e70e22edbab683518f21ae8b851369fb61008e7683af1451f4b357055'


def run_isolated():
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix='successor-transaction-tests-') as temporary:
        merged = Path(temporary) / 'kit'
        shutil.copytree(str(BASELINE), str(merged))
        for source in OVERLAY.rglob('*'):
            if source.is_file() and '__pycache__' not in str(source):
                target = merged / source.relative_to(OVERLAY)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(source), str(target))
        fixture_base = merged / 'helpers/fixtures'
        fixture_base.mkdir(exist_ok=True)
        sys.path[:0] = [str(CANDIDATE / 'tests'), str(merged / 'helpers'), str(merged / 'tests/recovery'),
                       str(merged / 'xuanjun-p2-package/scripts'),
                       str(merged / 'xuanjun-p2-package/stage1')]
        import epoch7_claim_successor as c
        import epoch7_injected_recovery as retained
        import epoch7_recovery_sequence as sequence
        import epoch7_complete_approval as approval
        import epoch7_protected_fs as fs
        import epoch7_host_phases as host
        import epoch7_delta as d
        from test_epoch7_delta import fixture, h
        from test_epoch7_injected_recovery import FakeOps

        def proof_fixture():
            return {'schema': 1, 'record': {'synthetic_fixed_pin_boundary': True,
                    'raw_sha256': REAL_PARENT_SHA, 'raw_size': 1641},
                    'ancestors': {'synthetic_parent': {'ino': 10}},
                    'absent': {c.OLD_INNER: True, c.NEW_OUTER: True, c.NEW_INNER: True}}

        def contract_fixture(proof=None):
            return {'schema': 1, 'kind': 'EXACT_CLAIM_ONLY_SUCCESSOR',
                'predecessor': c.predecessor_contract(),
                'implementation': {'source_commit': '1' * 40, 'source_tree': '2' * 40,
                                   'kit_manifest_sha256': h('synthetic kit')},
                'admission_expires_at_utc': '2027-12-31T23:59:59Z',
                'authorized_successors': 1, 'automatic_retry': False,
                'effect_scope': 'UNCHANGED_107_PAYLOADS_16_PHASES',
                'measured_predecessor_sha256': c.digest(proof or proof_fixture())}

        class SyntheticLock(host.ExistingInstallLock):
            """Only this local fixture supplies lock identity/held observations."""
            def __init__(self, rig): self.rig = rig; self.active = True
            def held(self): return self.active
            def __enter__(self):
                self.rig.hit('lock_enter'); self.active = True; return self
            def __exit__(self, *unused):
                self.rig.hit('lock_exit'); self.active = False; return False

        class GuardOps(FakeOps):
            def __init__(self, snapshot, rig):
                super(GuardOps, self).__init__(snapshot); self.rig = rig
            def install_lock_held(self): return self.rig.lock.held()
            def read_preserved_pins(self):
                self.rig.hit('guard:preserved'); return super(GuardOps, self).read_preserved_pins()
            def read_activation_evidence(self):
                self.rig.hit('guard:activation'); return super(GuardOps, self).read_activation_evidence()
            def read_generation(self):
                self.rig.hit('guard:generation'); return super(GuardOps, self).read_generation()
            def read_sandbox(self):
                self.rig.hit('guard:sandbox'); return super(GuardOps, self).read_sandbox()
            def read_targets(self):
                self.rig.hit('guard:targets'); return super(GuardOps, self).read_targets()
            def read_writer_exclusion(self):
                self.rig.hit('guard:writer_exclusion')
                return super(GuardOps, self).read_writer_exclusion()

        class MemoryIO(object):
            def __init__(self, rig, role): self.rig = rig; self.role = role
            def journal_exists(self, name):
                assert name == (c.NEW_OUTER if self.role == 'outer' else c.NEW_INNER)
                self.rig.hit(self.role + ':exists')
                return name in self.rig.records
            def read_predecessor_proof(self):
                self.rig.hit('predecessor:proof'); return copy.deepcopy(self.rig.proof)
            def predecessor_record(self): return copy.deepcopy(self.rig.proof['record'])
            def predecessor_ancestors(self): return copy.deepcopy(self.rig.proof['ancestors'])
            def predecessor_inner_absent(self): return not self.rig.old_inner
            def read_journal(self, name):
                self.rig.hit(self.role + ':readback')
                return copy.deepcopy(self.rig.records[name])
            def _create(self, name, raw):
                self.rig.hit(self.role + ':before_write')
                if name in self.rig.records: raise FileExistsError('SYNTHETIC_O_EXCL')
                self.rig.records[name] = self.rig.ops.record(raw)
                self.rig.hit(self.role + ':after_write')
            def create_prechecked_outer(self, name, raw, token):
                assert self.role == 'outer'
                self.rig.hit('outer:before_authorize')
                token.authorize_outer_io(self, name, raw)
                self._create(name, raw)
            def create_prechecked_inner(self, name, raw, token):
                assert self.role == 'inner'
                self.rig.hit('inner:before_authorize')
                token.authorize_inner_io(self, name, raw)
                self._create(name, raw)
            def create_exclusive(self, name, raw, uid, gid, mode):
                raise AssertionError('ADMISSION_MUST_USE_EXACT_PRECHECKED_IO')
            def replace_exact(self, name, expected, raw, uid, gid, mode):
                assert self.rig.lock.held()
                assert self.rig.records[name] == expected
                self.rig.hit(self.role + ':save')
                self.rig.records[name] = self.rig.ops.record(raw)

        class Controls(object):
            def __init__(self, rig):
                self.rig = rig
                self.observer = types.SimpleNamespace(guard_deadline=time.monotonic() + 30)
            def install_lock(self): return self.rig.lock
            def verify_outer_review(self, context):
                return self.rig.verifier.verify_outer_review(context)
            def preflight(self, context):
                self.rig.hit('preflight')
                self.observer.guard_deadline = time.monotonic() + 30
                self.rig.hit('preflight:deadline')
                return sequence.observation(context, 'preflight', h('synthetic full preflight'))
            def before_phase(self, context, phase):
                self.rig.hit('before:' + phase)
                return sequence.observation(context, 'before:' + phase, h(phase))
            def after_phase(self, context, phase, evidence):
                self.rig.hit('after:' + phase)
                return sequence.observation(context, 'after:' + phase, h(phase))

        class Containment(object):
            def __init__(self, rig): self.rig = rig
            def run(self, context, operation, unit, diagnostics):
                label = operation if unit is None else operation + ':' + unit
                self.rig.hit('cleanup:' + label)
                return sequence.observation(context, label, h(label))

        class Rig(object):
            def __init__(self, proof=None):
                self.events = []; self.hooks = {}; self.failures = {}; self.records = {}
                self.old_inner = False; self.proof = copy.deepcopy(proof) if proof is not None else proof_fixture()
                self.contract = contract_fixture(self.proof)
                self.lock = SyntheticLock(self)
                snapshot, candidate = fixture()
                rows = []
                for path, row in sorted(snapshot['targets'].items()):
                    rows.append({'target': path,
                        'rendered_sha256': row.get('sha256', h('prior ' + path)),
                        'uid': 0, 'gid': 0, 'mode': 0o644,
                        'previous': {'masked': True} if path in d.OWNER_MASKS else None})
                prior = d.canonical({'schema': 1, 'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY',
                    'rollback_complete': False, 'targets': rows}) + b'\n'
                snapshot['receipts']['epoch6-runtime-provisioning.json'] = sequence.sha(prior)
                self.ops = GuardOps(snapshot, self)
                self.verifier = approval.CompleteApprovalVerifier(7000000017, h('synthetic review body'),
                    self.lock.held, self.fetch)
                self.gate = retained.RecoveryGate(snapshot, candidate, d.digest(snapshot),
                    h('synthetic kit'), h('synthetic security'), 7000000017,
                    self.verifier, self.ops, prior, claim_successor=self.contract)
                self.ops.preserved = copy.deepcopy(self.gate.preserved)
                self.verifier.bind(self.gate, h('synthetic plan'))
                self.controls = Controls(self)
                self.outer_io = MemoryIO(self, 'outer'); self.inner_io = MemoryIO(self, 'inner')
                self.driver = sequence.InjectedDriver(self.gate, self.controls, self.outer_io,
                    self.inner_io, {p: self.effect(p) for p in sequence.EXTERNAL_PHASES},
                    Containment(self), sequence.BoundedDiagnostics(self.publish), {}, {})
                # All phase effects remain SYNTHETIC; the unchanged real phase
                # implementation and business loop are checked independently by AST.
                self.driver.phase = self.phase
                self.verifier.verify_outer_review(self.driver.context)
                self.events[:] = []
            def hit(self, event):
                self.events.append(event)
                if event in self.hooks: self.hooks[event]()
                if event in self.failures: raise self.failures[event]
            def fetch(self, review_id, wanted):
                self.hit('fetch:synthetic_authenticated_boundary')
                return {'review_id': review_id, 'body_sha256': self.verifier.body_sha,
                        'approval': copy.deepcopy(wanted)}
            def publish(self, evidence): raise AssertionError('NO_COMMANDS_EXPECTED')
            def effect(self, name): return lambda context, diag: self.phase(name)
            def phase(self, name):
                self.hit('phase:' + name)
                return sequence.observation(self.driver.context, name, h(name))
            def prepare(self): return c.prepare_successor(self.driver, self.contract)[0]
            def journal(self):
                return sequence.OuterJournal(self.driver.journal_io, self.driver.context,
                                             self.gate.journal_binding())
            def commit(self, token, journal=None):
                journal = journal or self.journal()
                c.commit_successor(self.driver, token, journal,
                    {'stage': 'CLAIM_INTENT', 'admission': 'UNKNOWN'})
                return journal
            def claims(self): return [event for event in self.events if event.endswith(':before_write')]

        class ContractTests(unittest.TestCase):
            def test_exact_contract_fixed_names_old_identity_and_no_authority_defaults(self):
                contract = contract_fixture()
                self.assertEqual(c.validate_contract(contract), contract)
                self.assertEqual(contract['predecessor']['raw_sha256'], REAL_PARENT_SHA)
                self.assertEqual(contract['predecessor']['raw_size'], 1641)
                for value in (None, False, True, {}, {'schema': 1}):
                    with self.subTest(value=value), self.assertRaises(ValueError): c.validate_contract(value)
                for field, value in (('schema', True), ('schema', 2), ('automatic_retry', True),
                    ('authorized_successors', 2), ('effect_scope', 'EXPANDED')):
                    changed = copy.deepcopy(contract); changed[field] = value
                    with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                        c.validate_contract(changed)
                for field in ('source_commit', 'source_tree', 'kit_manifest_sha256'):
                    changed = copy.deepcopy(contract); changed['implementation'][field] = 'UNBOUND'
                    with self.subTest(field=field), self.assertRaises(ValueError): c.validate_contract(changed)
            def test_every_parent_contract_identity_and_old_plan_seed_body_is_fixed(self):
                for field, value in contract_fixture()['predecessor'].items():
                    changed = contract_fixture()
                    changed['predecessor'][field] = ('wrong' if type(value) is str else None)
                    with self.subTest(field=field), self.assertRaises(ValueError): c.validate_contract(changed)
            def test_exact_expiry_grammar_and_value(self):
                for value in ('2027-12-31', '2027-12-31T23:59:59+00:00',
                    '2027-12-31T23:59:59.0Z', '2027-02-30T00:00:00Z',
                    '2027-12-31T24:00:00Z', '2027-12-31T23:59:60Z', None, True):
                    with self.subTest(value=value), self.assertRaises(ValueError): c.parse_expiry(value)
            def test_old_review_and_original_body_cannot_be_reused(self):
                for review_id, body in ((c.OLD_REVIEW_ID, h('new')), (7000000017, c.OLD_REVIEW_SHA256)):
                    with self.subTest(review_id=review_id), self.assertRaises(ValueError):
                        approval.CompleteApprovalVerifier(review_id, body, lambda: True, lambda *args: None)
            def test_old_complete_schema_or_changed_fixed_names_rejected(self):
                rig = Rig()
                for field, value in (('inner_attempt_name', c.OLD_INNER),
                                     ('outer_receipt_name', c.OLD_OUTER), ('schema', 2)):
                    changed = approval.sequence_contract(rig.driver.context); changed[field] = value
                    with self.subTest(field=field), self.assertRaises(ValueError): approval.sequence_contract(changed)
                with self.assertRaises(ValueError): approval.sequence_contract({'schema': 2})
            def test_old_complete_review_schema_and_cached_body_mutation_are_rejected(self):
                rig = Rig()
                def old_schema(review_id, wanted):
                    value = rig.fetch(review_id, wanted)
                    value['approval']['schema'] = 2
                    return value
                rig.verifier.fetcher = old_schema
                with self.assertRaisesRegex(ValueError, 'AUTHENTICATED_BODY'):
                    rig.verifier.verify_outer_review(rig.driver.context)
                self.assertFalse(rig.verifier.checked_under_lock)
                with self.assertRaises(ValueError): rig.prepare()
                self.assertEqual(rig.claims(), [])
                rig = Rig(); rig.verifier.cached['approval']['schema'] = 2
                with self.assertRaisesRegex(ValueError, 'CACHED_AUTHORITY_MUTATED'): rig.prepare()
                self.assertEqual(rig.claims(), [])
            def test_real_pin_refuses_synthetic_predecessor(self):
                raw, metadata = synthetic_parent()
                self.assertNotEqual(sequence.sha(raw), REAL_PARENT_SHA)
                self.assertEqual(c.PREDECESSOR_SHA256, REAL_PARENT_SHA)
                with self.assertRaisesRegex(ValueError, 'PREDECESSOR_BYTES'):
                    c.validate_predecessor_record(raw, metadata)
            def test_synthetic_fixed_pin_copy_validates_full_shape_and_metadata(self):
                raw, metadata = synthetic_parent()
                module = synthetic_validator(raw)
                self.assertEqual(module.validate_predecessor_record(raw, metadata)['raw_sha256'], sequence.sha(raw))
                for field, value in (('uid', 1), ('gid', 1), ('mode', 0o644), ('nlink', 2),
                    ('ino', 0), ('size', len(raw) - 1), ('dev', True), ('kind', 'SYMLINK'),
                    ('sha256', 'f' * 64), ('access_acl', 'extended'), ('capability', 'setcap')):
                    changed = copy.deepcopy(metadata); changed[field] = value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        module.validate_predecessor_record(raw, changed)
            def test_synthetic_fixed_pin_mutations_never_validate_against_original_synthetic_pin(self):
                raw, metadata = synthetic_parent(); module = synthetic_validator(raw)
                value = json.loads(raw.decode())
                for field, replacement in (('schema', 2), ('name', c.NEW_OUTER), ('transaction_id', 'wrong'),
                                           ('binding', {}), ('context_sha256', 'x' * 64), ('state', {})):
                    changed = copy.deepcopy(value); changed[field] = replacement
                    changed_raw = c.canonical(changed) + b'\n'
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        module.validate_predecessor_record(changed_raw, metadata)
            def test_synthetic_fixed_pin_rejects_forbidden_state_even_with_recomputed_test_pins(self):
                raw, unused = synthetic_parent(); original = json.loads(raw.decode())
                for field, replacement in (('stage', 'ADMITTED'), ('admission', 'ADMITTED'),
                    ('completed', ['stage_exact_release']), ('interruption', 'KeyboardInterrupt'),
                    ('phase_evidence', {'x': {}}), ('containment', [{}]), ('secondary_errors', [{}]),
                    ('automatic_retry', True), ('legacy_restart', True), ('receipt_status', 'UNKNOWN')):
                    value = copy.deepcopy(original); value['state'][field] = replacement
                    changed_raw = c.canonical(value) + b'\n'
                    changed_meta = parent_metadata(changed_raw)
                    module = synthetic_validator(changed_raw)
                    with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'NO_PHASE_HOLD'):
                        module.validate_predecessor_record(changed_raw, changed_meta)

        def parent_metadata(raw):
            return {'uid': 0, 'gid': 0, 'mode': 0o600, 'dev': 1, 'ino': 2, 'nlink': 1,
                    'size': len(raw), 'mtime_ns': 123, 'ctime_ns': 456, 'kind': 'FILE',
                    'sha256': sequence.sha(raw)}

        def synthetic_parent():
            state = {'stage': 'HOLD', 'failed_stage': 'CLAIM_INTENT', 'failed_phase': 'admission',
                'failed_operation': 'create_inner_attempt', 'admission': 'UNKNOWN',
                'receipt_status': 'OBSERVED', 'completed': [], 'phase_evidence': {},
                'containment': [], 'containment_status': 'NOT_ATTEMPTED', 'secondary_errors': [],
                'interruption': None, 'automatic_retry': False, 'legacy_restart': False,
                'historical_notification_replay': False, 'prerequisite_replay': False}
            value = {'schema': 1, 'name': c.OLD_OUTER, 'transaction_id': c.TX,
                'context_sha256': h('SYNTHETIC predecessor context'),
                'binding': {'review_id': c.OLD_REVIEW_ID, 'approval_body_sha256': c.OLD_REVIEW_SHA256,
                            'synthetic_fixture_only': True}, 'state': state}
            raw = c.canonical(value) + b'\n'
            return raw, parent_metadata(raw)

        def synthetic_validator(raw):
            """Clone source; substitute fixed pins ONLY in this synthetic module."""
            value = json.loads(raw.decode())
            pins = {'PREDECESSOR_SHA256': sequence.sha(raw), 'PREDECESSOR_SIZE': len(raw),
                'PREDECESSOR_BINDING_SHA256': c.digest(value['binding']),
                'PREDECESSOR_STATE_SHA256': sequence.sha(c.canonical(value['state']) + b'\n')}
            source = (merged / 'helpers/epoch7_claim_successor.py').read_text()
            tree = ast.parse(source)
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    name = node.targets[0].id
                    if name in pins:
                        node.value = ast.parse(repr(pins[name]), mode='eval').body
            module = types.ModuleType('_SYNTHETIC_FIXED_PIN_SUCCESSOR_NOT_AUTHORITY')
            exec(compile(ast.fix_missing_locations(tree), '<synthetic-fixed-pin-successor>', 'exec'), module.__dict__)
            return module

        class TransactionTests(unittest.TestCase):
            def test_prepare_full_gate_no_claim_commit_same_guards_again(self):
                rig = Rig(); token = rig.prepare()
                self.assertTrue(c.is_prepared_capability(token)); self.assertEqual(rig.records, {})
                guards = ['guard:preserved', 'guard:activation', 'guard:generation',
                          'guard:sandbox', 'guard:targets', 'guard:writer_exclusion']
                self.assertEqual([e for e in rig.events if e.startswith('guard:')], guards)
                self.assertEqual(rig.events.count('preflight'), 1)
                rig.commit(token)
                self.assertEqual([e for e in rig.events if e.startswith('guard:')], guards + guards)
                self.assertEqual(rig.events.count('preflight'), 2)
                self.assertEqual(rig.claims(), ['outer:before_write', 'inner:before_write'])
                first = rig.events.index('outer:before_write'); second = rig.events.index('inner:before_write')
                self.assertFalse(any(e == 'preflight' or e.startswith('guard:') for e in rig.events[first:second]))
                self.assertNotIn('fetch:synthetic_authenticated_boundary', rig.events)
                self.assertEqual(set(rig.records), {c.NEW_OUTER, c.NEW_INNER})
                self.assertEqual(token.stage, 'COMPLETE')
                outer = json.loads(rig.records[c.NEW_OUTER]['data'].decode())
                inner = json.loads(rig.records[c.NEW_INNER]['data'].decode())
                self.assertEqual(outer['name'], c.NEW_OUTER); self.assertEqual(inner['name'], c.NEW_INNER)
                self.assertEqual(outer['binding'], inner['binding'])
                self.assertEqual(inner['state'], {'stage': 'ADMITTED'})
            def test_false_none_dict_and_lookalike_capabilities_rejected(self):
                for value in (False, True, None, {}, {'stage': 'PREPARED'}, types.SimpleNamespace(stage='PREPARED')):
                    rig = Rig(); rig.gate.check()
                    with self.subTest(value=repr(value)), self.assertRaises(ValueError): rig.commit(value)
                    self.assertEqual(rig.claims(), [])
            def test_preflight_requires_exact_observed_envelope_in_both_calls(self):
                for value in (False, True, None, {}, {'status': 'OBSERVED'}):
                    for at_commit in (False, True):
                        rig = Rig(); token = rig.prepare() if at_commit else None
                        rig.controls.preflight = lambda unused, result=value: result
                        with self.subTest(value=repr(value), at_commit=at_commit), self.assertRaises(ValueError):
                            rig.commit(token) if at_commit else rig.prepare()
                        self.assertEqual(rig.claims(), [])
            def test_copy_pickle_and_exact_type_forgery_rejected(self):
                rig = Rig(); token = rig.prepare()
                for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                    with self.subTest(operation=operation.__name__), self.assertRaises(TypeError): operation(token)
                forged = c.PreparedSuccessor.__new__(c.PreparedSuccessor)
                forged.__dict__.update(token.__dict__)
                self.assertFalse(c.is_prepared_capability(forged))
                with self.assertRaises(ValueError): rig.commit(forged)
                self.assertEqual(rig.claims(), [])
            def test_capability_cannot_cross_process(self):
                rig = Rig(); token = rig.prepare()
                read_fd, write_fd = os.pipe()
                pid = os.fork()
                if pid == 0:
                    os.close(read_fd)
                    try:
                        token._check(); result = b'ACCEPTED'
                    except BaseException: result = b'REJECTED'
                    os.write(write_fd, result); os.close(write_fd); os._exit(0)
                os.close(write_fd)
                result = os.read(read_fd, 100); os.close(read_fd); os.waitpid(pid, 0)
                self.assertEqual(result, b'REJECTED')
                self.assertEqual(rig.claims(), [])
            def test_no_prepare_or_commit_reuse(self):
                rig = Rig(); token = rig.prepare()
                with self.assertRaisesRegex(ValueError, 'PREPARE_ONCE'): rig.prepare()
                rig.commit(token); before = list(rig.events)
                with self.assertRaisesRegex(ValueError, 'SINGLE_USE'): rig.commit(token)
                self.assertEqual(rig.events, before)
            def test_approval_expired_before_prepare_or_between_prepare_commit_refuses(self):
                for after_prepare in (False, True):
                    rig = Rig(); token = rig.prepare() if after_prepare else None
                    expiry = c.parse_expiry(rig.contract['admission_expires_at_utc'])
                    with mock.patch.object(approval.time, 'time', return_value=expiry + 1):
                        with self.subTest(after_prepare=after_prepare), self.assertRaises(ValueError):
                            rig.commit(token) if after_prepare else rig.prepare()
                    self.assertEqual(rig.claims(), [])
            def test_seal_cannot_be_created_from_boolean_dict_unconfirmed_or_forged_object(self):
                rig = Rig(); token = rig.prepare()
                forged = c.PreparedSuccessor.__new__(c.PreparedSuccessor)
                forged.__dict__.update(token.__dict__); forged.stage = 'COMPLETE'
                for value in (False, True, {}, None, token, forged):
                    with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                        rig.verifier.seal_admission(value)
                self.assertIsNone(rig.verifier.admitted_capability)
                self.assertEqual(rig.claims(), [])
            def test_public_complete_flags_on_genuine_prepared_token_cannot_forge_seal(self):
                rig = Rig(); token = rig.prepare()
                token.stage = 'COMPLETE'
                for field in ('outer_attempted', 'inner_attempted', 'outer_confirmed',
                              'inner_confirmed', 'outer_io_used', 'io_used'):
                    setattr(token, field, True)
                token.outer_raw = rig.journal()._raw({'stage': 'CLAIM_INTENT', 'admission': 'UNKNOWN'})
                token.inner_raw = rig.driver.inner._packed({'stage': 'ADMITTED'})
                self.assertTrue(c.is_prepared_capability(token))
                self.assertFalse(c.is_completed_capability(token))
                with self.assertRaisesRegex(ValueError, 'EXACT_COMPLETED_CAPABILITY_REQUIRED'):
                    rig.verifier.seal_admission(token)
                self.assertIsNone(rig.verifier.admitted_capability)
                self.assertEqual(rig.records, {})
                self.assertEqual(rig.claims(), [])
                expiry = c.parse_expiry(rig.contract['admission_expires_at_utc'])
                with mock.patch.object(approval.time, 'time', return_value=expiry + 1):
                    with self.assertRaisesRegex(ValueError, 'EXPIRED'):
                        rig.verifier.verify_exact(rig.gate.review_id, rig.gate.expected)
            def test_direct_admitted_capability_substitution_cannot_bypass_expiry(self):
                rig = Rig(); token = rig.prepare()
                token.stage = 'COMPLETE'
                for field in ('outer_attempted', 'inner_attempted', 'outer_confirmed',
                              'inner_confirmed', 'outer_io_used', 'io_used'):
                    setattr(token, field, True)
                token.outer_raw = rig.journal()._raw({'stage': 'CLAIM_INTENT', 'admission': 'UNKNOWN'})
                token.inner_raw = rig.driver.inner._packed({'stage': 'ADMITTED'})
                rig.verifier.admitted_capability = token
                expiry = c.parse_expiry(rig.contract['admission_expires_at_utc'])
                with mock.patch.object(approval.time, 'time', return_value=expiry + 1):
                    with self.assertRaisesRegex(ValueError, 'ADMISSION_SEAL_MUTATED'):
                        rig.verifier.verify_exact(rig.gate.review_id, rig.gate.expected)
                self.assertEqual(rig.records, {})
                self.assertEqual(rig.claims(), [])
            def test_consume_cannot_reattest_mutated_public_transition_flags(self):
                for field in ('outer_attempted', 'inner_attempted', 'outer_confirmed',
                              'inner_confirmed', 'outer_io_used', 'io_used'):
                    rig = Rig(); token = rig.prepare(); setattr(token, field, True)
                    with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'TRANSITION_ATTESTATION'):
                        token.consume(rig.driver)
                    self.assertEqual(rig.records, {})
                    self.assertEqual(rig.claims(), [])
            def test_expiry_after_sealed_admission_does_not_disable_hold_or_original_phase_guard(self):
                rig = Rig(); token = rig.prepare(); journal = rig.commit(token)
                self.assertIs(rig.verifier.admitted_capability, token)
                self.assertTrue(c.is_completed_capability(token))
                expiry = c.parse_expiry(rig.contract['admission_expires_at_utc'])
                with mock.patch.object(approval.time, 'time', return_value=expiry + 1):
                    rig.verifier._bound()
                    rig.gate.check()
                    journal.save({'stage': 'HOLD', 'admission': 'ADMITTED'})
                    with self.assertRaisesRegex(ValueError, 'EXPIRED'): rig.verifier.check_admission_expiry()
                self.assertEqual(json.loads(journal.last['data'].decode())['state']['stage'], 'HOLD')
            def test_wrong_driver_consumes_token_without_any_claim(self):
                rig = Rig(); token = rig.prepare(); other = Rig(); other.gate.check()
                with self.assertRaisesRegex(ValueError, 'CAPABILITY_DRIVER'): other.commit(token)
                with self.assertRaisesRegex(ValueError, 'SINGLE_USE'): rig.commit(token)
                self.assertEqual(rig.claims() + other.claims(), [])
            def test_missing_or_revoked_locked_review_refuses(self):
                for attr, value in (('checked_under_lock', False), ('cached', None)):
                    rig = Rig(); setattr(rig.verifier, attr, value)
                    with self.subTest(attr=attr), self.assertRaises(ValueError): rig.prepare()
                    self.assertEqual(rig.claims(), [])
            def test_changed_context_lock_review_and_inputs_refuse(self):
                mutations = [lambda r: r.driver.context.update(outer_receipt_name=c.OLD_OUTER),
                    lambda r: setattr(r.lock, 'active', False),
                    lambda r: setattr(r, 'lock', SyntheticLock(r)),
                    lambda r: setattr(r.gate, 'review_id', c.OLD_REVIEW_ID),
                    lambda r: setattr(r.verifier, 'body_sha', h('different body')),
                    lambda r: setattr(r.driver, 'journal_io', object()),
                    lambda r: setattr(r.driver, 'retained_io', object()),
                    lambda r: setattr(r.driver, 'inner', object()),
                    lambda r: r.gate.candidate.update(manifest_sha256=h('different candidate')),
                    lambda r: r.proof['ancestors']['synthetic_parent'].update(ino=11),
                    lambda r: r.proof['record'].update(raw_sha256=h('different parent'))]
                for index, mutate in enumerate(mutations):
                    rig = Rig(); token = rig.prepare(); mutate(rig)
                    with self.subTest(mutation=index), self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
                    with self.assertRaises(ValueError): rig.commit(token)
            def test_old_inner_or_either_new_claim_refuses_prepare_and_postprepare_commit(self):
                for name in (c.OLD_INNER, c.NEW_OUTER, c.NEW_INNER):
                    for after in (False, True):
                        rig = Rig(); token = rig.prepare() if after else None
                        if name == c.OLD_INNER: rig.old_inner = True
                        else: rig.records[name] = {'existing': 'even partial records consume the name'}
                        with self.subTest(name=name, after=after), self.assertRaises(ValueError):
                            rig.commit(token) if after else rig.prepare()
                        self.assertEqual(rig.claims(), [])
            def test_postprepare_real_gate_rejects_each_original_guard_drift(self):
                mutations = [lambda r: r.ops.preserved.update(extra=True),
                    lambda r: r.ops.activation.update(epoch=900),
                    lambda r: r.ops.snapshot['generation'].update(mode=0o777),
                    lambda r: r.ops.snapshot['sandbox'].update(state='UNKNOWN'),
                    lambda r: r.ops.targets[next(iter(r.ops.targets))].update(ino=99999),
                    lambda r: r.ops.exclusion.update(all_stopped=False),
                    lambda r: r.ops.exclusion.update(database_fds_excluded=False),
                    lambda r: r.ops.exclusion.update(all_stopped=False, database_fds_excluded=False)]
                for index, mutate in enumerate(mutations):
                    rig = Rig(); token = rig.prepare(); mutate(rig)
                    with self.subTest(guard=index), self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
            def test_postprepare_db_unknown_keeps_first_exception_and_no_claim(self):
                rig = Rig(); token = rig.prepare(); original = OSError('SYNTHETIC_UNKNOWN_DB_OBSERVATION')
                rig.failures['guard:writer_exclusion'] = original
                with self.assertRaises(OSError) as caught: rig.commit(token)
                self.assertIs(caught.exception, original); self.assertEqual(rig.claims(), [])
            def test_commit_deadline_and_wall_expiry_fail_before_first_claim(self):
                for kind in ('token', 'wall', 'original_guard'):
                    rig = Rig(); token = rig.prepare()
                    if kind == 'token': token.expires = time.monotonic() - 1
                    if kind == 'wall': token.wall_expiry = time.time() - 1
                    if kind == 'original_guard':
                        rig.hooks['preflight:deadline'] = lambda: setattr(rig.controls.observer, 'guard_deadline', time.monotonic() - 1)
                    with self.subTest(kind=kind), self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
            def test_nan_infinity_and_extended_capability_deadlines_refuse(self):
                mutations = [lambda token: setattr(token, 'expires', float('nan')),
                    lambda token: setattr(token, 'expires', float('inf')),
                    lambda token: setattr(token, 'expires', token.expires + 60),
                    lambda token: setattr(token, 'wall_expiry', token.wall_expiry + 60),
                    lambda token: setattr(token, 'mint_window', (0, 0, token.expires + 60)),
                    lambda token: setattr(token, 'commit_guard', float('inf'))]
                for index, mutate in enumerate(mutations):
                    rig = Rig(); token = rig.prepare(); mutate(token)
                    with self.subTest(mutation=index), self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
            def test_changed_original_guard_deadline_between_claims_refuses(self):
                rig = Rig(); token = rig.prepare()
                rig.hooks['inner:before_authorize'] = lambda: setattr(rig.controls.observer,
                    'guard_deadline', rig.controls.observer.guard_deadline + 60)
                with self.assertRaisesRegex(ValueError, 'GUARD_DEADLINE_MUTATED'): rig.commit(token)
                self.assertEqual(rig.claims(), ['outer:before_write'])
                self.assertNotIn(c.NEW_INNER, rig.records)
            def test_backward_wall_does_not_extend_monotonic_capability(self):
                rig = Rig(); token = rig.prepare()
                with mock.patch.object(c, '_clock', return_value=(token.expires + 1, 1)):
                    with self.assertRaisesRegex(ValueError, 'EXPIRED'): rig.commit(token)
                self.assertEqual(rig.claims(), [])
            def test_before_each_write_rechecks_lock_and_deadline(self):
                for role in ('outer', 'inner'):
                    for change in ('lock', 'expiry', 'predecessor', 'old_inner', 'ancestor'):
                        rig = Rig(); token = rig.prepare()
                        def mutate():
                            if change == 'lock': rig.lock.active = False
                            elif change == 'expiry': token.expires = time.monotonic() - 1
                            elif change == 'old_inner': rig.old_inner = True
                            elif change == 'ancestor': rig.proof['ancestors']['synthetic_parent']['ino'] += 1
                            else: rig.proof['record']['raw_sha256'] = h('late predecessor drift')
                        rig.hooks[role + ':before_authorize'] = mutate
                        with self.subTest(role=role, change=change), self.assertRaises(ValueError): rig.commit(token)
                        self.assertEqual(rig.claims(), [] if role == 'outer' else ['outer:before_write'])
                        self.assertNotIn(c.NEW_INNER, rig.records)
            def test_outer_fail_unknown_readback_or_interrupt_never_attempt_inner(self):
                for point in ('outer:before_write', 'outer:after_write', 'outer:readback'):
                    for error in (OSError('SYNTHETIC_IO'), TimeoutError('SYNTHETIC_TIMEOUT'), KeyboardInterrupt(), SystemExit(4)):
                        rig = Rig(); token = rig.prepare(); journal = rig.journal()
                        rig.failures[point] = error
                        with self.subTest(point=point, kind=type(error).__name__), self.assertRaises(type(error)) as caught:
                            rig.commit(token, journal)
                        self.assertIs(caught.exception, error)
                        self.assertNotIn('inner:before_write', rig.events)
                        self.assertIsNone(journal.last); self.assertTrue(journal.poisoned)
                        self.assertEqual(token.stage, 'FAILED')
                        before = list(rig.events)
                        with self.assertRaises(ValueError): rig.commit(token, journal)
                        self.assertEqual(rig.events, before)
            def test_outer_confirmed_inner_fail_is_terminal_and_preserves_outer(self):
                for point in ('inner:before_write', 'inner:after_write', 'inner:readback'):
                    rig = Rig(); token = rig.prepare(); journal = rig.journal()
                    rig.failures[point] = OSError('SYNTHETIC_SECOND_PUBLICATION')
                    with self.subTest(point=point), self.assertRaises(OSError): rig.commit(token, journal)
                    self.assertIsNotNone(journal.last); self.assertFalse(journal.poisoned)
                    self.assertEqual(rig.records[c.NEW_OUTER], journal.last)
                    self.assertTrue(rig.driver.inner.poisoned); self.assertEqual(token.stage, 'FAILED')
                    self.assertFalse(any(event.startswith('phase:') for event in rig.events))
                    before = list(rig.events)
                    with self.assertRaises(ValueError): rig.commit(token, journal)
                    self.assertEqual(rig.events, before)
            def test_publication_status_distinguishes_no_attempt_unknown_and_confirmed(self):
                for point, expected in (
                    ('preflight', ('NOT_ATTEMPTED', 'NOT_ATTEMPTED')),
                    ('outer:before_write', ('ATTEMPTED_UNKNOWN', 'NOT_ATTEMPTED')),
                    ('outer:after_write', ('ATTEMPTED_UNKNOWN', 'NOT_ATTEMPTED')),
                    ('outer:readback', ('ATTEMPTED_UNKNOWN', 'NOT_ATTEMPTED')),
                    ('inner:before_write', ('CONFIRMED', 'ATTEMPTED_UNKNOWN')),
                    ('inner:after_write', ('CONFIRMED', 'ATTEMPTED_UNKNOWN')),
                    ('inner:readback', ('CONFIRMED', 'ATTEMPTED_UNKNOWN'))):
                    rig = Rig(); token = rig.prepare(); rig.failures[point] = OSError('SYNTHETIC')
                    with self.subTest(point=point), self.assertRaises(OSError): rig.commit(token)
                    status = token.publication_status()
                    self.assertEqual((status['outer'], status['inner']), expected)
                    self.assertIs(status['automatic_completion'], False)
                    self.assertEqual(status['capability_state'], 'FAILED')
                rig = Rig(); token = rig.prepare(); rig.commit(token)
                status = token.publication_status()
                self.assertEqual((status['outer'], status['inner']), ('CONFIRMED', 'CONFIRMED'))
            def test_corrupt_readback_bytes_or_metadata_are_terminal(self):
                for role in ('outer', 'inner'):
                    for corrupt in ('bytes', 'metadata'):
                        rig = Rig(); token = rig.prepare(); name = c.NEW_OUTER if role == 'outer' else c.NEW_INNER
                        def mutate():
                            if corrupt == 'metadata': rig.records[name]['mode'] = 0o644
                            else: rig.records[name]['data'] = b'{}\n'
                        rig.hooks[role + ':after_write'] = mutate
                        with self.subTest(role=role, corrupt=corrupt), self.assertRaises(ValueError): rig.commit(token)
                        self.assertEqual(token.stage, 'FAILED')
                        if role == 'outer': self.assertNotIn('inner:before_write', rig.events)
                        self.assertFalse(any(e.startswith('phase:') for e in rig.events))
            def test_prepare_or_commit_control_interrupt_creates_no_claim(self):
                for at_commit in (False, True):
                    for error in (KeyboardInterrupt(), SystemExit(7), TimeoutError('SYNTHETIC')):
                        rig = Rig(); token = rig.prepare() if at_commit else None
                        rig.failures['preflight'] = error
                        with self.subTest(at_commit=at_commit, kind=type(error).__name__), self.assertRaises(type(error)) as caught:
                            rig.commit(token) if at_commit else rig.prepare()
                        self.assertIs(caught.exception, error); self.assertEqual(rig.claims(), [])
            def test_frozen_resume_entry_refuses(self):
                rig = Rig()
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_SUCCESSOR_ENTRY_REQUIRED'):
                    sequence.resume_once(rig.driver)
                self.assertEqual(rig.events, [])
            def test_real_coordinator_enters_exact16_phases_only_after_both_claims(self):
                rig = Rig(); rig.lock.active = False
                state = sequence.successor_resume_once(rig.driver, rig.contract)
                self.assertEqual(state['completed'], list(sequence.PHASES))
                self.assertEqual(state['stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
                self.assertEqual([e[6:] for e in rig.events if e.startswith('phase:')], list(sequence.PHASES))
                self.assertLess(rig.events.index('inner:readback'), rig.events.index('phase:' + sequence.PHASES[0]))
                self.assertEqual(rig.events.count('fetch:synthetic_authenticated_boundary'), 2)
                with self.assertRaises(ValueError): sequence.successor_resume_once(rig.driver, rig.contract)
            def test_preclaim_failure_coordinator_does_not_contain_or_enter_phases(self):
                rig = Rig(); rig.failures['outer:after_write'] = OSError('UNCERTAIN')
                with self.assertRaises(sequence.RecoveryHold) as caught:
                    sequence.successor_resume_once(rig.driver, rig.contract)
                state = caught.exception.state
                self.assertEqual(state['stage'], 'HOLD'); self.assertEqual(state['completed'], [])
                self.assertEqual(state['receipt_status'], 'UNKNOWN')
                self.assertEqual(state['containment_status'], 'NOT_ATTEMPTED')
                self.assertFalse(any(e.startswith(('phase:', 'cleanup:')) for e in rig.events))
            def test_failure_preserves_only_safe_same_census_enumerations(self):
                allowed = [('PID_LIST_CHANGED', 'CHANGED', 'UNCHANGED'),
                    ('DB_MAP_CHANGED', 'UNCHANGED', 'CHANGED'),
                    ('BOTH_CHANGED', 'CHANGED', 'CHANGED'),
                    ('UNKNOWN', 'CHANGED', 'UNKNOWN'), ('UNKNOWN', 'UNCHANGED', 'UNKNOWN')]
                for classification, pids, databases in allowed:
                    error = OSError('PRIVATE_PATH_AND_ARGV_MUST_NOT_APPEAR')
                    error.epoch7_census_race = {'classification': classification,
                        'pid_list': pids, 'db_map': databases}
                    state = {'stage': 'CLAIM_INTENT'}
                    sequence._failure(state, 'admission', 'commit_successor_claims', error)
                    self.assertEqual(state['census_race'], error.epoch7_census_race)
                    self.assertNotIn('PRIVATE_PATH', json.dumps(state))
                for invalid in (True, 'PRIVATE_PATH', {}, {'classification': 'PID_LIST_CHANGED'},
                    {'classification': 'PID_LIST_CHANGED', 'pid_list': 'UNCHANGED', 'db_map': 'UNCHANGED'},
                    {'classification': 'UNKNOWN', 'pid_list': 'UNKNOWN', 'db_map': []}):
                    error = ValueError('PRIVATE_PATH'); error.epoch7_census_race = invalid
                    state = {'stage': 'CLAIM_INTENT'}
                    sequence._failure(state, 'admission', 'commit_successor_claims', error)
                    self.assertEqual(state['census_race'], {'classification': 'UNKNOWN',
                        'pid_list': 'UNKNOWN', 'db_map': 'UNKNOWN'})
                    self.assertNotIn('PRIVATE_PATH', json.dumps(state))
            def test_later_actual_census_guard_failure_preserves_original_containment(self):
                from test_census_race_classification import SyntheticCensus, run as run_census
                census = SyntheticCensus(); census.pids[1] = [10, 20, 30]
                try: run_census(census)
                except ValueError as error: census_error = error
                else: self.fail('Actual census comparison must refuse changed PID list')
                rig = Rig(); phase = sequence.PHASES[3]
                rig.failures['before:' + phase] = census_error
                with self.assertRaises(sequence.RecoveryHold) as caught:
                    sequence.successor_resume_once(rig.driver, rig.contract)
                state = caught.exception.state
                self.assertEqual(state['completed'], list(sequence.PHASES[:3]))
                self.assertEqual(state['failed_phase'], phase)
                self.assertEqual(state['failed_operation'], 'verify_phase_before')
                self.assertEqual(state['census_race'], {'classification': 'PID_LIST_CHANGED',
                    'pid_list': 'CHANGED', 'db_map': 'UNCHANGED'})
                expected = [op if unit is None else op + ':' + unit for op, unit in sequence.CLEANUP]
                self.assertEqual([e[8:] for e in rig.events if e.startswith('cleanup:')], expected)

        class ProtectedChainTests(unittest.TestCase):
            def setUp(self):
                self.temp = tempfile.TemporaryDirectory(prefix='real-protected-', dir=str(fixture_base))
                self.root = Path(self.temp.name)
                (self.root / fs.TRANSACTION.lstrip('/')).mkdir(parents=True, mode=0o700)
                os.chmod(str(self.root / fs.TRANSACTION.lstrip('/')), 0o700)
                probe = fs.ProtectedFilesystem(types.SimpleNamespace(check=lambda: None), fixture_root=str(self.root))
                measured = proof_fixture()
                measured['ancestors'] = host.HostPhaseFilesystem.predecessor_ancestors(probe)
                self.rig = Rig(measured)
                rig = self.rig
                # Owner IDs and immutable predecessor content are the only
                # synthetic boundaries; all fd ancestry/ACL/O_EXCL/fsync/readback
                # operations below execute the genuine fixture filesystem code.
                class FixtureOuter(host.HostPhaseFilesystem):
                    @staticmethod
                    def _matches(observed, expected):
                        # Same explicit fixture-owner projection used for the
                        # journal API; production CAS logic still compares all
                        # fields, bytes, inode and nanosecond stamps.
                        observed = dict(observed, uid=0, gid=0)
                        return fs.ProtectedFilesystem._matches(observed, expected)
                    def predecessor_record(self): return copy.deepcopy(rig.proof['record'])
                    def read_predecessor_proof(self): return copy.deepcopy(rig.proof)
                    def read_journal(self, name):
                        value = super(FixtureOuter, self).read_journal(name)
                        value.update(uid=0, gid=0); return value
                    def _exclusive_at(self, *args):
                        rig.hit('outer:before_write')
                        return super(FixtureOuter, self)._exclusive_at(*args)
                class FixtureInner(fs.ProtectedFilesystem):
                    def read_journal(self, name):
                        value = super(FixtureInner, self).read_journal(name)
                        value.update(uid=0, gid=0); return value
                    def _exclusive_at(self, *args):
                        rig.hit('inner:before_write')
                        return super(FixtureInner, self)._exclusive_at(*args)
                rig.gate.check()
                authority = host.ClaimAuthority(rig.lock, rig.verifier, rig.driver.context, rig.gate.journal_binding())
                rig.outer_io = FixtureOuter(authority, fixture_root=str(self.root))
                rig.inner_io = FixtureInner(rig.gate, fixture_root=str(self.root))
                rig.driver.journal_io = rig.outer_io; rig.driver.retained_io = rig.inner_io
                rig.driver.inner = retained.BoundJournal(c.NEW_INNER, rig.gate, rig.inner_io)
                rig.events[:] = []
            def tearDown(self): self.temp.cleanup()
            def path(self, name): return self.root / fs.TRANSACTION.lstrip('/') / name
            def test_real_outer_authority_and_protected_inner_complete_without_intervening_fullgate(self):
                rig = self.rig; token = rig.prepare(); rig.commit(token)
                self.assertEqual(sorted(p.name for p in self.path(c.NEW_OUTER).parent.iterdir()),
                                 sorted((c.NEW_OUTER, c.NEW_INNER)))
                self.assertEqual(os.stat(str(self.path(c.NEW_INNER))).st_mode & 0o777, 0o600)
                self.assertEqual(os.stat(str(self.path(c.NEW_INNER))).st_nlink, 1)
                first = rig.events.index('outer:before_write'); second = rig.events.index('inner:before_write')
                self.assertFalse(any(e.startswith('guard:') or e == 'preflight' for e in rig.events[first:second]))
                self.assertEqual(json.loads(self.path(c.NEW_INNER).read_text())['name'], c.NEW_INNER)
            def test_real_writes_keep_exclusive_nofollow_and_file_parent_fsync(self):
                rig = self.rig; token = rig.prepare()
                with mock.patch.object(fs.os, 'open', wraps=os.open) as opened:
                    with mock.patch.object(fs.os, 'fsync', wraps=os.fsync) as synced:
                        rig.commit(token)
                creates = [call for call in opened.call_args_list if call[0][1] & os.O_CREAT]
                self.assertEqual(len(creates), 2)
                self.assertEqual([call[0][0] for call in creates], [c.NEW_OUTER, c.NEW_INNER])
                for call in creates:
                    self.assertTrue(call[0][1] & os.O_EXCL)
                    self.assertTrue(call[0][1] & os.O_NOFOLLOW)
                    self.assertIn('dir_fd', call[1])
                self.assertEqual(synced.call_count, 4)
            def test_real_readback_hardlink_rejected_before_inner(self):
                rig = self.rig; token = rig.prepare()
                original = rig.outer_io._exclusive_at
                def after_outer(*args):
                    original(*args)
                    os.link(str(self.path(c.NEW_OUTER)), str(self.root / 'extra-hardlink'))
                rig.outer_io._exclusive_at = after_outer
                with self.assertRaisesRegex(ValueError, 'PROTECTED_REGULAR_FILE_REQUIRED'): rig.commit(token)
                self.assertTrue(self.path(c.NEW_OUTER).exists())
                self.assertFalse(self.path(c.NEW_INNER).exists())
            def test_real_hold_receipt_authority_survives_admission_expiry(self):
                rig = self.rig; token = rig.prepare(); journal = rig.commit(token)
                expiry = c.parse_expiry(rig.contract['admission_expires_at_utc'])
                with mock.patch.object(approval.time, 'time', return_value=expiry + 1):
                    journal.save({'stage': 'HOLD', 'admission': 'ADMITTED'})
                self.assertEqual(json.loads(self.path(c.NEW_OUTER).read_text())['state']['stage'], 'HOLD')
            def test_original_parent_modes_and_acl_guards_retained(self):
                for defect in ('mode', 'acl'):
                    with self.subTest(defect=defect):
                        if defect == 'mode':
                            os.chmod(str(self.path(c.NEW_INNER).parent), 0o777)
                            with self.assertRaises(ValueError): self.rig.prepare()
                            os.chmod(str(self.path(c.NEW_INNER).parent), 0o700)
                        else:
                            with mock.patch.object(self.rig.inner_io, '_xattr', return_value=b'UNREVIEWED_ACL'):
                                with self.assertRaises(ValueError): self.rig.inner_io.journal_exists(c.NEW_INNER)
                self.assertFalse(self.path(c.NEW_INNER).exists())
            def test_prechecked_inner_rejects_boolean_dict_fake_and_old_name(self):
                io = self.rig.inner_io
                for value in (False, True, None, {}, types.SimpleNamespace(authorize_inner_io=lambda *a: True)):
                    with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                        io.create_prechecked_inner(c.NEW_INNER, b'{}\n', value)
                token = self.rig.prepare()
                with self.assertRaises(ValueError): io.create_prechecked_inner(c.OLD_INNER, b'{}\n', token)
                self.assertFalse(self.path(c.NEW_INNER).exists())
            def test_real_unsafe_parent_mode_between_claims_prevents_second_write(self):
                rig = self.rig; token = rig.prepare()
                original = rig.outer_io._exclusive_at
                def after_outer(*args):
                    original(*args)
                    os.chmod(str(self.path(c.NEW_INNER).parent), 0o777)
                rig.outer_io._exclusive_at = after_outer
                with self.assertRaises(ValueError): rig.commit(token)
                self.assertTrue(self.path(c.NEW_OUTER).exists())
                self.assertFalse(self.path(c.NEW_INNER).exists())
            def test_transaction_parent_timestamp_drift_before_first_exclusive_write_refuses(self):
                rig = self.rig; token = rig.prepare()
                original = rig.outer_io.create_prechecked_outer
                def before_create(*args):
                    self.assertTrue(token.outer_attempted)
                    self.assertFalse(token.outer_confirmed)
                    parent = str(self.path(c.NEW_OUTER).parent)
                    info = os.stat(parent)
                    os.utime(parent, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
                    return original(*args)
                rig.outer_io.create_prechecked_outer = before_create
                with self.assertRaisesRegex(ValueError, 'ANCESTOR_DRIFT'): rig.commit(token)
                self.assertFalse(self.path(c.NEW_OUTER).exists())
                self.assertFalse(self.path(c.NEW_INNER).exists())
                self.assertEqual(rig.claims(), [])
            def test_safe_ancestor_replacement_between_claims_preserving_transaction_is_rejected(self):
                rig = self.rig; token = rig.prepare()
                original = rig.outer_io._exclusive_at
                def after_outer(*args):
                    original(*args)
                    parent = self.root / 'var/lib'; saved = self.root / 'var/lib.previous'
                    parent.rename(saved); parent.mkdir(mode=0o755)
                    (saved / 'xuanjun-p2-preparation').rename(parent / 'xuanjun-p2-preparation')
                rig.outer_io._exclusive_at = after_outer
                with self.assertRaisesRegex(ValueError, 'ANCESTOR_DRIFT'): rig.commit(token)
                self.assertTrue(self.path(c.NEW_OUTER).exists())
                self.assertFalse(self.path(c.NEW_INNER).exists())
            def test_real_inner_existing_symlink_never_followed_or_overwritten(self):
                rig = self.rig; token = rig.prepare()
                target = self.root / 'unrelated'; target.write_bytes(b'KEEP')
                original = rig.outer_io._exclusive_at
                def after_outer(*args):
                    original(*args); os.symlink(str(target), str(self.path(c.NEW_INNER)))
                rig.outer_io._exclusive_at = after_outer
                with self.assertRaises((FileExistsError, ValueError)): rig.commit(token)
                self.assertEqual(target.read_bytes(), b'KEEP')
                self.assertTrue(self.path(c.NEW_OUTER).exists())
                self.assertTrue(self.path(c.NEW_INNER).is_symlink())

        class InvariantTests(unittest.TestCase):
            def test_same16phase_loop_builtin_phase_logic_and_containment_ast(self):
                before = ast.parse((BASELINE / 'helpers/epoch7_recovery_sequence.py').read_text())
                after = ast.parse((merged / 'helpers/epoch7_recovery_sequence.py').read_text())
                def named(tree, name, kind=ast.FunctionDef):
                    return next(node for node in ast.walk(tree) if isinstance(node, kind) and node.name == name)
                before_run = named(before, 'resume_once'); after_run = named(after, 'successor_resume_once')
                def phase_loop(node):
                    return next(item for item in ast.walk(node) if isinstance(item, ast.For)
                                and isinstance(item.iter, ast.Name) and item.iter.id == 'PHASES')
                self.assertEqual(ast.dump(phase_loop(before_run)), ast.dump(phase_loop(after_run)))
                self.assertEqual(ast.dump(named(before, 'phase')), ast.dump(named(after, 'phase')))
                self.assertEqual(ast.dump(named(before, '_cleanup')), ast.dump(named(after, '_cleanup')))
                for name in ('PHASES', 'STOP_UNITS', 'CLEANUP'):
                    def assignment(tree):
                        return next(node for node in tree.body if isinstance(node, ast.Assign)
                                    and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
                    self.assertEqual(ast.dump(assignment(before)), ast.dump(assignment(after)))
                self.assertEqual(len(sequence.PHASES), 16)
            def test_all107_runtime_payloads_unchanged_and_no_runtime_overlay(self):
                identity = json.loads((CANDIDATE / 'SOURCE_IDENTITY.json').read_text())
                self.assertEqual(identity['runtime_payload_count'], 107)
                self.assertEqual(len(identity['runtime_payloads']), 107)
                self.assertFalse((OVERLAY / 'xuanjun-p2-package').exists())
                for relative, wanted in identity['runtime_payloads'].items():
                    with self.subTest(relative=relative):
                        raw = (BASELINE / 'xuanjun-p2-package' / relative).read_bytes()
                        self.assertEqual(hashlib.sha256(raw).hexdigest(), wanted)

        suite = unittest.TestSuite()
        for case in (ContractTests, TransactionTests, ProtectedChainTests, InvariantTests):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_isolated())
