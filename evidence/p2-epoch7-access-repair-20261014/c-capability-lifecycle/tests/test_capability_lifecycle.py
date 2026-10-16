"""Finite local lifecycle regression through the original real transaction Rig.

Clock, lock, host observations, predecessor pins, and phase effects stay explicit
synthetic boundaries inherited from test_successor_transactions. The actual
RecoveryGate, CompleteApprovalVerifier, journals and protected O_EXCL/readback
chain execute. This is source behavior evidence, never UK performance acceptance,
execution authority, a refreshed Plan, or approval. No network or host work.
"""
import copy
import json
import math
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_successor_transactions as original


def lifecycle_suite(env):
    c, approval, sequence = env['c'], env['approval'], env['sequence']
    Rig = env['Rig']
    ProtectedChainTests = env['ProtectedChainTests']

    class Clock(object):
        def __init__(self, remaining=600):
            self.mono = 1000.0
            self.wall = c.parse_expiry('2027-12-31T23:59:59Z') - remaining
            self.patches = []
        def __enter__(self):
            for field, value in (('monotonic', lambda: self.mono), ('time', lambda: self.wall)):
                patch = mock.patch.object(c.time, field, side_effect=value)
                patch.start(); self.patches.append(patch)
            return self
        def __exit__(self, *unused):
            for patch in reversed(self.patches): patch.stop()
        def advance(self, amount):
            self.mono += amount; self.wall += amount
        def advance_to(self, point): self.advance(point - self.mono)

    def delays(rig, clock, preflight=20, inner=20):
        rig.hooks['preflight:deadline'] = lambda: clock.advance(preflight)
        rig.hooks['guard:writer_exclusion'] = lambda: clock.advance(inner)

    class LifecycleTests(unittest.TestCase):
        def no_retry(self, rig, token):
            before = list(rig.events)
            with self.assertRaises(ValueError): rig.commit(token)
            self.assertEqual(rig.events, before)
            with self.assertRaises(ValueError): rig.prepare()
            self.assertEqual(rig.events, before)
        def test_exact_new_timing_policy_is_required_in_signed_contract(self):
            rig = Rig()
            self.assertEqual(c.TIMING_POLICY, 'PREPARED_START_30S_ORDERED_GUARDS_PUBLICATION_MIN_V1')
            for value in (None, False, {}, 'PREPARED_30S', c.TIMING_POLICY + '_MUTATED'):
                changed = copy.deepcopy(rig.contract)
                changed['timing_policy'] = value
                with self.subTest(value=value), self.assertRaises(ValueError): c.validate_contract(changed)
            changed = copy.deepcopy(rig.contract); del changed['timing_policy']
            with self.assertRaises(ValueError): c.validate_contract(changed)
        def test_two_real_complete_twenty_second_guards_publish_after_forty(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); start = clock.mono
                delays(rig, clock)
                rig.commit(token)
                self.assertEqual(clock.mono - start, 40)
                self.assertEqual(rig.events.count('preflight'), 2)
                self.assertEqual(rig.events.count('inner_guard:begin'), 2)
                for name in ('preserved', 'activation', 'generation', 'sandbox', 'targets', 'writer_exclusion'):
                    self.assertEqual(rig.events.count('guard:' + name), 2)
                self.assertEqual(rig.claims(), ['outer:before_write', 'inner:before_write'])
                self.assertTrue(c.is_completed_capability(token))
                self.assertEqual(token.expires, start + 50)
                self.assertLess(token.mint_window[2], clock.mono)
        def test_original_shared_thirty_second_predicate_rejects_identical_forty_second_trace(self):
            # Exact old aggregate ready predicate, applied at the actual ready
            # boundary. This is a policy regression, not a second old-suite run.
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); old_deadline = token.mint_window[2]
                delays(rig, clock)
                original_ready = c.PreparedSuccessor.ready
                def old_aggregate_ready(prepared, predecessor, deadline, *args, **kwargs):
                    mono, wall = c._clock()
                    c.need(prepared.mint_window[0] <= mono < old_deadline and
                           wall < prepared.wall_expiry, 'CAPABILITY_EXPIRED')
                    return original_ready(prepared, predecessor, deadline, *args, **kwargs)
                with mock.patch.object(c.PreparedSuccessor, 'ready', old_aggregate_ready):
                    with self.assertRaisesRegex(ValueError, 'CAPABILITY_EXPIRED'): rig.commit(token)
                self.assertEqual(clock.mono, 1040)
                self.assertEqual(rig.claims(), [])
                self.no_retry(rig, token)
        def test_prepared_handle_start_expiry_is_strict_at_thirty_seconds(self):
            for age, allowed in ((29.999, True), (30.0, False), (30.001, False)):
                with self.subTest(age=age), Clock() as clock:
                    rig = Rig(); token = rig.prepare(); clock.advance(age)
                    if allowed: rig.commit(token)
                    else:
                        with self.assertRaisesRegex(ValueError, 'PREPARED_START_EXPIRED'): rig.commit(token)
                        self.assertEqual(rig.claims(), [])
                        self.no_retry(rig, token)
        def test_consume_fixed_checks_stay_inside_original_handle_budget(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); rig.events[:] = []
                rig.hooks['predecessor:proof'] = lambda: clock.advance(30)
                with self.assertRaisesRegex(ValueError, 'PREPARED_START_EXPIRED'): rig.commit(token)
                self.assertNotIn('preflight', rig.events)
                self.assertEqual(rig.claims(), [])
                self.no_retry(rig, token)
        def test_each_guard_owns_unchanged_strict_thirty_second_budget(self):
            for role in ('preflight', 'inner'):
                for elapsed in (29.999, 30.0, 30.001):
                    with self.subTest(role=role, elapsed=elapsed), Clock() as clock:
                        rig = Rig(); token = rig.prepare()
                        delays(rig, clock, elapsed if role == 'preflight' else 0,
                               elapsed if role == 'inner' else 0)
                        if elapsed < 30: rig.commit(token)
                        else:
                            code = 'PREFLIGHT_GUARD_EXPIRED' if role == 'preflight' else 'INNER_GUARD_EXPIRED'
                            with self.assertRaisesRegex(ValueError, code): rig.commit(token)
                            self.assertEqual(rig.claims(), [])
                            self.no_retry(rig, token)
        def test_post_preflight_predecessor_io_uses_preflight_remaining_budget(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); rig.events[:] = []
                rig.hooks['preflight:deadline'] = lambda: clock.advance(20)
                def predecessor_tail():
                    if rig.events.count('predecessor:proof') == 2: clock.advance(10)
                rig.hooks['predecessor:proof'] = predecessor_tail
                with self.assertRaisesRegex(ValueError, 'PREFLIGHT_GUARD_EXPIRED'): rig.commit(token)
                self.assertNotIn('inner_guard:begin', rig.events)
                self.assertEqual(rig.claims(), [])
        def test_post_inner_binding_io_uses_inner_remaining_budget(self):
            with Clock() as clock:
                rig = Rig()
                binding = rig.driver.check_binding; injected = [False]
                def binding_tail():
                    result = binding()
                    if not injected[0] and rig.events.count('guard:writer_exclusion') == 2:
                        injected[0] = True; clock.advance(1)
                    return result
                rig.driver.check_binding = binding_tail
                token = rig.prepare(); delays(rig, clock, 0, 29)
                with self.assertRaisesRegex(ValueError, 'INNER_GUARD_EXPIRED'): rig.commit(token)
                self.assertTrue(injected[0]); self.assertEqual(rig.claims(), [])
        def test_final_inner_remaining_window_is_not_restarted_at_mint(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); delays(rig, clock)
                rig.hooks['outer:before_authorize'] = lambda: clock.advance(10)
                with self.assertRaisesRegex(ValueError, 'PUBLICATION_EXPIRED'): rig.commit(token)
                self.assertEqual(clock.mono, 1050)
                self.assertEqual(rig.claims(), [])
                self.assertEqual(token.expires, 1050)
                self.no_retry(rig, token)
        def test_prepare_utc_to_monotonic_ceiling_limits_publication(self):
            with Clock(remaining=45) as clock:
                rig = Rig(); token = rig.prepare(); delays(rig, clock)
                rig.commit(token)
                self.assertEqual(token.expires, 1045)
                self.assertEqual(token.mint_window[2], 1030)
                self.assertEqual(rig.controls.observer.guard_deadline, 1050)
        def test_wall_rollback_never_expands_original_ceiling(self):
            with Clock(remaining=45) as clock:
                rig = Rig(); token = rig.prepare(); original_window = token.mint_window
                rig.hooks['preflight:deadline'] = lambda: setattr(clock, 'wall', clock.wall - 100)
                with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK'): rig.commit(token)
                self.assertEqual(token.mint_window, original_window)
                self.assertEqual(rig.claims(), [])
                self.no_retry(rig, token)
        def test_wall_forward_to_exact_signed_expiry_fails_without_publication(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare()
                rig.hooks['preflight:deadline'] = lambda: setattr(clock, 'wall', token.wall_expiry)
                with self.assertRaisesRegex(ValueError, 'APPROVAL_EXPIRED|SUCCESSOR_EXPIRED'): rig.commit(token)
                self.assertEqual(rig.claims(), [])
                self.no_retry(rig, token)
        def test_monotonic_rollback_above_prepare_start_still_fails(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); delays(rig, clock, 20, 0)
                rig.hooks['inner_guard:begin'] = lambda: setattr(clock, 'mono', clock.mono - 1)
                with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK'): rig.commit(token)
                self.assertEqual(rig.claims(), [])
                self.no_retry(rig, token)
        def test_nonfinite_clock_samples_fail_closed_and_do_not_leak(self):
            for field in ('mono', 'wall'):
                for value in (float('nan'), float('inf'), -float('inf')):
                    with self.subTest(field=field, value=str(value)), Clock() as clock:
                        rig = Rig(); token = rig.prepare()
                        rig.hooks['preflight:deadline'] = lambda: setattr(clock, field, value)
                        with self.assertRaises(ValueError): rig.commit(token)
                        self.assertEqual(rig.claims(), [])
                        status = token.timing_status()
                        json.dumps(status, allow_nan=False)
        def test_atomic_concurrent_entry_has_one_winner_and_one_guard_sequence(self):
            with Clock():
                rig = Rig(); token = rig.prepare(); entered = threading.Event(); release = threading.Event()
                outcomes = []
                def block():
                    entered.set()
                    if not release.wait(5): raise AssertionError('SYNTHETIC_CONCURRENCY_TIMEOUT')
                rig.hooks['preflight:deadline'] = block
                def winner():
                    try: rig.commit(token); outcomes.append('COMPLETE')
                    except BaseException as error: outcomes.append(error)
                worker = threading.Thread(target=winner); worker.start()
                try:
                    self.assertTrue(entered.wait(5))
                    before = list(rig.events)
                    with self.assertRaisesRegex(ValueError, 'SINGLE_USE'): rig.commit(token)
                    self.assertEqual(rig.events, before)
                finally:
                    release.set(); worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(outcomes, ['COMPLETE'])
                self.assertEqual(rig.claims(), ['outer:before_write', 'inner:before_write'])
                self.assertEqual(rig.events.count('preflight'), 2)
        def test_other_driver_first_entry_permanently_consumes_handle(self):
            with Clock():
                rig = Rig(); token = rig.prepare(); other = Rig(); other.gate.check()
                with self.assertRaisesRegex(ValueError, 'CAPABILITY_DRIVER'): other.commit(token)
                self.assertEqual(rig.claims() + other.claims(), [])
                self.no_retry(rig, token)
        def test_direct_ready_cannot_mint_without_actual_ordered_commit_checks(self):
            for supplied in (False, True, {}, {'preflight': True, 'inner': True, 'complete': True}):
                with self.subTest(supplied=supplied), Clock():
                    rig = Rig(); token = rig.prepare(); token.consume(rig.driver)
                    token.completed_checks = supplied
                    token.commit_complete = True
                    token.preflight_complete = True
                    token.inner_complete = True
                    with self.assertRaises(ValueError):
                        token.ready(rig.proof, rig.controls.observer.guard_deadline)
                    self.assertEqual(rig.claims(), [])
                    self.assertFalse(c.is_completed_capability(token))
        def test_reconstructed_public_ready_state_cannot_publish_or_seal(self):
            with Clock():
                rig = Rig(); token = rig.prepare()
                token.stage = 'READY'; token.commit_complete = True
                token.commit_guard = rig.controls.observer.guard_deadline
                token.commit_guard_sha = c.digest(token.commit_guard)
                token.expires = token.commit_guard
                token.inner_raw = rig.driver.inner._packed({'stage': 'ADMITTED'})
                with self.assertRaises(ValueError): token.begin_outer(rig.journal(), {'stage': 'CLAIM_INTENT'})
                with self.assertRaises(ValueError): rig.verifier.seal_admission(token)
                self.assertEqual(rig.claims(), [])
        def test_context_or_predecessor_mutation_during_complete_checks_prevents_mint(self):
            for defect in ('context', 'predecessor', 'lock', 'approval'):
                with self.subTest(defect=defect), Clock():
                    rig = Rig(); token = rig.prepare()
                    def mutate():
                        if defect == 'context': rig.driver.context['outer_receipt_name'] = c.OLD_OUTER
                        elif defect == 'predecessor': rig.proof['ancestors']['synthetic_parent']['ino'] += 1
                        elif defect == 'lock': rig.lock.active = False
                        else: rig.verifier.cached['approval']['schema'] = -1
                    rig.hooks['guard:writer_exclusion'] = mutate
                    with self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
                    self.no_retry(rig, token)
        def test_interruption_before_and_after_mint_is_terminal_without_remint(self):
            for point in ('guard:writer_exclusion', 'outer:before_authorize'):
                for error in (KeyboardInterrupt(), SystemExit(17), TimeoutError('SYNTHETIC')):
                    with self.subTest(point=point, error=type(error).__name__), Clock():
                        rig = Rig(); token = rig.prepare(); rig.failures[point] = error
                        with self.assertRaises(type(error)) as caught: rig.commit(token)
                        self.assertIs(caught.exception, error)
                        self.assertEqual(token.stage, 'FAILED')
                        self.assertEqual(rig.claims(), [])
                        with self.assertRaises(ValueError): token.ready(rig.proof, rig.controls.observer.guard_deadline)
                        self.no_retry(rig, token)
        def test_exact_publication_expiry_at_write_and_readback_never_fills_or_retries(self):
            for role in ('outer', 'inner'):
                for point in ('before_authorize', 'after_write', 'readback'):
                    with self.subTest(role=role, point=point), Clock() as clock:
                        rig = Rig(); token = rig.prepare(); delays(rig, clock)
                        rig.hooks[role + ':' + point] = lambda: clock.advance_to(token.expires)
                        with self.assertRaisesRegex(ValueError, 'PUBLICATION_EXPIRED'): rig.commit(token)
                        expected = [] if role == 'outer' and point == 'before_authorize' else ['outer:before_write']
                        if role == 'inner' and point != 'before_authorize': expected.append('inner:before_write')
                        self.assertEqual(rig.claims(), expected)
                        self.assertIsNone(rig.verifier.admitted_capability)
                        self.assertEqual(token.stage, 'FAILED')
                        self.no_retry(rig, token)
        def test_unknown_write_or_readback_outcome_is_not_retried_or_completed(self):
            for role in ('outer', 'inner'):
                for point in ('before_write', 'after_write', 'readback'):
                    for error in (OSError('SYNTHETIC_UNKNOWN'), TimeoutError('SYNTHETIC_TIMEOUT')):
                        with self.subTest(role=role, point=point, error=type(error).__name__), Clock() as clock:
                            rig = Rig(); token = rig.prepare(); delays(rig, clock)
                            rig.failures[role + ':' + point] = error
                            with self.assertRaises(type(error)) as caught: rig.commit(token)
                            self.assertIs(caught.exception, error)
                            self.assertIsNone(rig.verifier.admitted_capability)
                            if role == 'outer': self.assertNotIn('inner:before_write', rig.events)
                            self.no_retry(rig, token)
        def test_sealed_success_preserves_later_expired_hold_save_and_phase_checks(self):
            with Clock(remaining=45) as clock:
                rig = Rig(); token = rig.prepare(); delays(rig, clock)
                journal = rig.commit(token)
                clock.advance(6)
                rig.hooks.clear()
                rig.gate.check()
                journal.save({'stage': 'HOLD', 'admission': 'ADMITTED'})
                self.assertTrue(c.is_completed_capability(token))
                self.assertEqual(json.loads(journal.last['data'].decode())['state']['stage'], 'HOLD')
                with self.assertRaises(ValueError): rig.verifier.check_admission_expiry()
        def test_lifecycle_success_does_not_disable_later_census_hold_and_containment(self):
            from test_census_race_classification import SyntheticCensus, run as run_census
            census = SyntheticCensus(); census.pids[1] = [10, 20, 30]
            try: run_census(census)
            except ValueError as error: census_error = error
            else: self.fail('Real census comparison must fail')
            with Clock() as clock:
                rig = Rig(); count = [0]
                def delay_commit():
                    count[0] += 1
                    if count[0] == 2: clock.advance(20)
                rig.hooks['preflight:deadline'] = delay_commit
                inner_count = [0]
                def delay_inner_commit():
                    inner_count[0] += 1
                    if inner_count[0] == 2: clock.advance(20)
                rig.hooks['guard:writer_exclusion'] = delay_inner_commit
                phase = sequence.PHASES[3]; rig.failures['before:' + phase] = census_error
                with self.assertRaises(sequence.RecoveryHold) as caught:
                    sequence.successor_resume_once(rig.driver, rig.contract)
                state = caught.exception.state
                self.assertEqual(state['stage'], 'HOLD')
                self.assertEqual(state['completed'], list(sequence.PHASES[:3]))
                self.assertEqual(state['census_race'], {'classification': 'PID_LIST_CHANGED',
                    'pid_list': 'CHANGED', 'db_map': 'UNCHANGED'})
                expected = [op if unit is None else op + ':' + unit for op, unit in sequence.CLEANUP]
                self.assertEqual([e[8:] for e in rig.events if e.startswith('cleanup:')], expected)
                self.assertEqual(rig.claims(), ['outer:before_write', 'inner:before_write'])

        def test_replaced_check_callables_cannot_fake_completed_private_progress(self):
            for target in ('preflight', 'inner', 'binding', 'approval', 'predecessor'):
                with self.subTest(target=target), Clock():
                    rig = Rig(); token = rig.prepare()
                    if target == 'preflight':
                        rig.controls.preflight = lambda context: sequence.observation(context, 'preflight', 'e' * 64)
                    elif target == 'inner': rig.gate.check = lambda: True
                    elif target == 'binding': rig.driver.check_binding = lambda: True
                    elif target == 'approval': rig.verifier.verify_exact = lambda *args: True
                    else: rig.outer_io.read_predecessor_proof = lambda: copy.deepcopy(rig.proof)
                    with self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
                    self.assertFalse(c.is_completed_capability(token))
                    self.no_retry(rig, token)
        def test_guard_provider_object_swap_cannot_reuse_prepared_check_proof(self):
            with Clock():
                rig = Rig(); token = rig.prepare(); original_provider = rig.gate.guards
                class ForwardingGuardProvider(object):
                    def __getattr__(self, name): return getattr(original_provider, name)
                rig.gate.guards = ForwardingGuardProvider()
                with self.assertRaises(ValueError): rig.commit(token)
                self.assertEqual(rig.claims(), [])
                self.assertFalse(c.is_completed_capability(token))
                self.no_retry(rig, token)
        def test_finite_guard_method_swaps_cannot_reuse_prepared_check_proof(self):
            methods = ('install_lock_held', 'read_preserved_pins', 'read_activation_evidence',
                'read_generation', 'read_sandbox', 'read_targets', 'read_additive_absence',
                'read_additive_target', 'read_writer_exclusion')
            for name in methods:
                with self.subTest(method=name), Clock():
                    rig = Rig(); token = rig.prepare(); original_method = getattr(rig.gate.guards, name)
                    def replacement(*args, **kwargs): return original_method(*args, **kwargs)
                    setattr(rig.gate.guards, name, replacement)
                    with self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.claims(), [])
                    self.assertFalse(c.is_completed_capability(token))
                    self.no_retry(rig, token)

        def test_resetting_public_prepare_flag_cannot_remint_a_driver(self):
            for interrupted in (False, True):
                with self.subTest(interrupted=interrupted), Clock():
                    rig = Rig(); token = rig.prepare()
                    if interrupted:
                        rig.failures['preflight'] = KeyboardInterrupt()
                        with self.assertRaises(KeyboardInterrupt): rig.commit(token)
                    rig.driver._successor_prepared = False
                    before = list(rig.events)
                    with self.assertRaisesRegex(ValueError, 'PREPARE_ONCE'): rig.prepare()
                    self.assertEqual(rig.events, before)
                    self.assertEqual(rig.claims(), [])
                    if interrupted:
                        token.stage = 'PREPARED'
                        with self.assertRaises(ValueError): rig.commit(token)
                        self.assertEqual(rig.events, before)

        def test_guard_deadline_requires_exactly_one_actual_begin_call(self):
            for role in ('preflight', 'inner'):
                for count in (0, 2):
                    with self.subTest(role=role, count=count), Clock():
                        rig = Rig(); calls = [0]
                        if role == 'preflight':
                            actual = rig.controls.preflight
                            def preflight(context):
                                calls[0] += 1
                                if calls[0] == 1: return actual(context)
                                for unused in range(count): rig.controls._begin_guard(False)
                                return sequence.observation(context, 'preflight', 'd' * 64)
                            rig.controls.preflight = preflight
                        else:
                            actual = rig.ops.install_lock_held
                            def inner_guard():
                                calls[0] += 1
                                if calls[0] == 1: return actual()
                                for unused in range(count): rig.controls._begin_guard()
                                return rig.lock.held()
                            rig.ops.install_lock_held = inner_guard
                        token = rig.prepare()
                        with self.assertRaises(ValueError): rig.commit(token)
                        self.assertEqual(rig.claims(), [])
                        self.no_retry(rig, token)
        def test_guard_deadline_mutation_and_begin_wrapper_mutation_fail_closed(self):
            for role in ('preflight', 'inner'):
                for change in ('deadline', 'wrapper'):
                    with self.subTest(role=role, change=change), Clock():
                        rig = Rig(); token = rig.prepare()
                        original_begin = rig.controls._begin_guard
                        def mutate():
                            if change == 'deadline': rig.controls.observer.guard_deadline += 30
                            else: rig.controls._begin_guard = lambda *args: rig.controls.observer.guard_deadline
                        rig.hooks['preflight:deadline' if role == 'preflight' else 'guard:writer_exclusion'] = mutate
                        with self.assertRaises(ValueError): rig.commit(token)
                        self.assertEqual(rig.claims(), [])
                        # Temporary instrumentation must always restore the
                        # exact original bound method, including failure paths.
                        self.assertEqual(rig.controls._begin_guard, original_begin)
                        self.no_retry(rig, token)
        def test_guard_begin_instrumentation_restores_after_interruption_and_success(self):
            for role in ('preflight', 'inner', 'success'):
                with self.subTest(role=role), Clock():
                    rig = Rig(); token = rig.prepare(); original_begin = rig.controls._begin_guard
                    if role == 'success': rig.commit(token)
                    else:
                        rig.failures['preflight:deadline' if role == 'preflight' else 'guard:writer_exclusion'] = KeyboardInterrupt()
                        with self.assertRaises(KeyboardInterrupt): rig.commit(token)
                    self.assertEqual(rig.controls._begin_guard, original_begin)

        def assert_finite_timing(self, status):
            fields = {'schema', 'timing_policy', 'stages', 'prepared_start_deadline',
                'approval_monotonic_ceiling', 'preflight_deadline', 'inner_deadline',
                'publication_deadline', 'failure_predicate'}
            self.assertEqual(set(status), fields)
            self.assertIs(type(status['schema']), int)
            self.assertEqual(status['schema'], 1)
            self.assertEqual(status['timing_policy'], c.TIMING_POLICY)
            stages = ('prepare_start', 'prepare_preflight_start', 'prepare_preflight_complete',
                'prepare_inner_start', 'prepare_inner_complete', 'prepared_minted', 'commit_consumed',
                'commit_start_checks_complete', 'commit_preflight_start', 'commit_preflight_complete',
                'commit_predecessor_complete', 'commit_inner_start', 'commit_inner_complete',
                'commit_binding_complete', 'publication_minted', 'outer_begin', 'outer_confirmed',
                'inner_begin', 'inner_confirmed', 'complete', 'failed')
            self.assertLessEqual(len(status['stages']), len(stages))
            names = []
            for row in status['stages']:
                self.assertEqual(set(row), {'stage', 'monotonic', 'wall_utc', 'deadline_monotonic'})
                self.assertIn(row['stage'], stages)
                self.assertNotIn(row['stage'], names); names.append(row['stage'])
                for key in ('monotonic', 'wall_utc', 'deadline_monotonic'):
                    if key == 'deadline_monotonic' and row[key] is None: continue
                    self.assertIn(type(row[key]), (int, float)); self.assertTrue(math.isfinite(row[key]))
            self.assertEqual([stages.index(name) for name in names], sorted(stages.index(name) for name in names))
            for key in fields - {'schema', 'timing_policy', 'stages', 'failure_predicate'}:
                if status[key] is not None:
                    self.assertIn(type(status[key]), (int, float)); self.assertTrue(math.isfinite(status[key]))
            self.assertIn(status['failure_predicate'], (None, 'PREPARED_START_EXPIRED',
                'PREFLIGHT_GUARD_EXPIRED', 'INNER_GUARD_EXPIRED', 'PUBLICATION_EXPIRED',
                'APPROVAL_EXPIRED', 'APPROVAL_MONOTONIC_EXPIRED', 'CLOCK_ROLLBACK',
                'CLOCK_UNKNOWN', 'INTERRUPTION', 'CHECK_FAILED'))
            self.assertLess(len(json.dumps(status, allow_nan=False)), 8192)
            return status
        def test_success_telemetry_exact_finite_schema_and_minimum_deadline(self):
            with Clock(remaining=45) as clock:
                rig = Rig(); token = rig.prepare(); delays(rig, clock)
                state = {'stage': 'CLAIM_INTENT', 'admission': 'UNKNOWN'}
                c.commit_successor(rig.driver, token, rig.journal(), state)
                timing = self.assert_finite_timing(token.timing_status())
                self.assertEqual(timing, state['successor_timing'])
                self.assertEqual(timing['prepared_start_deadline'], 1030)
                self.assertEqual(timing['approval_monotonic_ceiling'], 1045)
                self.assertEqual(timing['preflight_deadline'], 1030)
                self.assertEqual(timing['inner_deadline'], 1050)
                self.assertEqual(timing['publication_deadline'], 1045)
                self.assertIsNone(timing['failure_predicate'])
                samples = {row['stage']: row for row in timing['stages']}
                self.assertEqual(samples['commit_preflight_complete']['monotonic'] -
                                 samples['commit_preflight_start']['monotonic'], 20)
                self.assertEqual(samples['commit_inner_complete']['monotonic'] -
                                 samples['commit_inner_start']['monotonic'], 20)
                self.assertEqual(samples['publication_minted']['monotonic'], 1040)
                self.assertIn('complete', samples)
        def test_each_timing_failure_has_precise_finite_predicate(self):
            cases = ('PREPARED_START_EXPIRED', 'PREFLIGHT_GUARD_EXPIRED',
                'INNER_GUARD_EXPIRED', 'PUBLICATION_EXPIRED', 'APPROVAL_EXPIRED',
                'APPROVAL_MONOTONIC_EXPIRED', 'CLOCK_ROLLBACK', 'CLOCK_UNKNOWN')
            for expected in cases:
                with self.subTest(expected=expected), Clock(remaining=45) as clock:
                    rig = Rig(); token = rig.prepare()
                    if expected == 'PREPARED_START_EXPIRED': clock.advance(30)
                    elif expected == 'PREFLIGHT_GUARD_EXPIRED':
                        rig.hooks['preflight:deadline'] = lambda: clock.advance(30)
                    elif expected == 'INNER_GUARD_EXPIRED':
                        rig.hooks['guard:writer_exclusion'] = lambda: clock.advance(30)
                    elif expected == 'PUBLICATION_EXPIRED':
                        rig.hooks['outer:before_authorize'] = lambda: clock.advance_to(token.expires)
                    elif expected == 'APPROVAL_EXPIRED':
                        rig.hooks['preflight:deadline'] = lambda: setattr(clock, 'wall', token.wall_expiry)
                    elif expected == 'APPROVAL_MONOTONIC_EXPIRED':
                        # The guard starts after 20s of bounded fixed work; its
                        # unchanged deadline is 1050, but original UTC ceiling is 1045.
                        rig.hooks['preflight:deadline'] = lambda: setattr(clock, 'mono', 1020)
                        rig.hooks['guard:writer_exclusion'] = lambda: setattr(clock, 'mono', 1045)
                    elif expected == 'CLOCK_ROLLBACK':
                        rig.hooks['preflight:deadline'] = lambda: setattr(clock, 'mono', 999)
                    else: rig.hooks['preflight:deadline'] = lambda: setattr(clock, 'mono', float('nan'))
                    with self.assertRaisesRegex(ValueError, expected): rig.commit(token)
                    timing = self.assert_finite_timing(token.timing_status())
                    self.assertEqual(timing['failure_predicate'], expected)
                    self.assertEqual(rig.claims(), [])
        def test_telemetry_copy_cannot_mutate_deadline_or_private_completion(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare()
                timing = token.timing_status()
                expected = copy.deepcopy(timing)
                timing['publication_deadline'] = 999999
                timing['failure_predicate'] = 'PRIVATE_PATH_SECRET'
                timing['stages'].append({'stage': 'complete', 'monotonic': 0,
                                         'wall_utc': 0, 'deadline_monotonic': 999999})
                self.assertEqual(token.timing_status(), expected)
                token.consume(rig.driver)
                with self.assertRaises(ValueError): token.ready(rig.proof, 999999, timing)
                self.assertEqual(rig.claims(), [])
        def test_error_telemetry_never_serializes_private_exception_or_mutable_args(self):
            for error in (OSError('PRIVATE_PATH_PASSWORD_AND_ARGV'), ValueError({'PRIVATE': ['SECRET']}),
                          KeyboardInterrupt('PRIVATE_SECRET'), SystemExit('PRIVATE_SECRET')):
                with self.subTest(error=type(error).__name__), Clock():
                    rig = Rig(); token = rig.prepare(); rig.failures['preflight'] = error
                    with self.assertRaises(type(error)) as caught: rig.commit(token)
                    self.assertIs(caught.exception, error)
                    timing = self.assert_finite_timing(token.timing_status())
                    encoded = json.dumps(timing, allow_nan=False)
                    self.assertNotIn('PRIVATE', encoded); self.assertNotIn('SECRET', encoded)
                    expected = 'INTERRUPTION' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'CHECK_FAILED'
                    self.assertEqual(timing['failure_predicate'], expected)
        def test_replay_cannot_revoke_completed_seal_or_cleanup_authority(self):
            with Clock() as clock:
                rig = Rig(); token = rig.prepare(); journal = rig.commit(token)
                self.no_retry(rig, token)
                self.assertTrue(c.is_completed_capability(token))
                self.assertIs(rig.verifier.admitted_capability, token)
                clock.advance(601)
                journal.save({'stage': 'HOLD', 'admission': 'ADMITTED'})
                rig.gate.check()
        def test_clock_expiry_after_actual_seal_preserves_coordinator_admission(self):
            with Clock() as clock:
                rig = Rig(); seal = rig.verifier.seal_admission; sealed = []
                def seal_then_expire(token):
                    seal(token); sealed.append(token); clock.advance(601)
                rig.verifier.seal_admission = seal_then_expire
                state = sequence.successor_resume_once(rig.driver, rig.contract)
                self.assertEqual(state['completed'], list(sequence.PHASES))
                self.assertEqual(state['stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
                self.assertEqual(state['admission'], 'ADMITTED')
                self.assertTrue(c.is_completed_capability(sealed[0]))
                self.assertIs(rig.verifier.admitted_capability, sealed[0])
                self.assertEqual(rig.claims(), ['outer:before_write', 'inner:before_write'])

    class ProtectedLifecycleTests(ProtectedChainTests):
        # Only these new methods are loaded, avoiding duplicate core55 tests.
        def test_protected_two_twenty_second_guards_retain_real_exclusive_flags_and_readback(self):
            with Clock() as clock:
                rig = self.rig
                # Fixture was bound before synthetic time started. Rebuild that
                # fixture under the clock, retaining its original protected setup.
                self.tearDown(); self.setUp(); rig = self.rig
                token = rig.prepare(); delays(rig, clock)
                fs = env['fs']
                with mock.patch.object(fs.os, 'open', wraps=os.open) as opened:
                    with mock.patch.object(fs.os, 'fsync', wraps=os.fsync) as synced:
                        rig.commit(token)
                creates = [call for call in opened.call_args_list if call[0][1] & os.O_CREAT]
                self.assertEqual([call[0][0] for call in creates], [c.NEW_OUTER, c.NEW_INNER])
                self.assertEqual(synced.call_count, 4)
                for call in creates:
                    self.assertTrue(call[0][1] & os.O_EXCL)
                    self.assertTrue(call[0][1] & os.O_NOFOLLOW)
                    self.assertIn('dir_fd', call[1])
                self.assertTrue(c.is_completed_capability(token))
                self.assertEqual(json.loads(self.path(c.NEW_INNER).read_text())['state'], {'stage': 'ADMITTED'})
        def test_protected_readback_expiry_keeps_partial_claims_without_fill_or_replay(self):
            for role in ('outer', 'inner'):
                with self.subTest(role=role), Clock() as clock:
                    self.tearDown(); self.setUp(); rig = self.rig
                    token = rig.prepare(); delays(rig, clock)
                    io = rig.outer_io if role == 'outer' else rig.inner_io
                    read = io.read_journal
                    def expire_after_read(name):
                        result = read(name); clock.advance_to(token.expires); return result
                    io.read_journal = expire_after_read
                    with self.assertRaisesRegex(ValueError, 'PUBLICATION_EXPIRED'): rig.commit(token)
                    self.assertTrue(self.path(c.NEW_OUTER).exists())
                    self.assertEqual(self.path(c.NEW_INNER).exists(), role == 'inner')
                    self.assertIsNone(rig.verifier.admitted_capability)
                    preserved = {name: self.path(name).read_bytes() for name in (c.NEW_OUTER, c.NEW_INNER)
                                 if self.path(name).exists()}
                    before = list(rig.events)
                    with self.assertRaises(ValueError): rig.commit(token)
                    self.assertEqual(rig.events, before)
                    for name, raw in preserved.items(): self.assertEqual(self.path(name).read_bytes(), raw)

        def test_protected_second_write_unknown_keeps_both_names_and_no_admission_seal(self):
            with Clock() as clock:
                self.tearDown(); self.setUp(); rig = self.rig
                token = rig.prepare(); delays(rig, clock)
                exclusive = rig.inner_io._exclusive_at
                def interrupted(*args):
                    exclusive(*args)
                    raise OSError('SYNTHETIC_POST_O_EXCL_UNKNOWN')
                rig.inner_io._exclusive_at = interrupted
                with self.assertRaises(OSError): rig.commit(token)
                self.assertTrue(self.path(c.NEW_OUTER).exists())
                self.assertTrue(self.path(c.NEW_INNER).exists())
                self.assertIsNone(rig.verifier.admitted_capability)
                before = list(rig.events)
                with self.assertRaises(ValueError): rig.commit(token)
                self.assertEqual(rig.events, before)
                self.assertTrue(rig.driver.inner.poisoned)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleTests)
    for name in sorted(ProtectedLifecycleTests.__dict__):
        if name.startswith('test_'): suite.addTest(ProtectedLifecycleTests(name))
    return suite


if __name__ == '__main__':
    sys.exit(original.run_isolated(extra_suite_factory=lifecycle_suite,
                                  include_existing='--include-existing' in sys.argv))
