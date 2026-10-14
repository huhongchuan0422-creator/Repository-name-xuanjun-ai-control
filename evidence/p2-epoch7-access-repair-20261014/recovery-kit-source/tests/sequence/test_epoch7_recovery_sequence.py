"""Offline fake-adapter flow tests. No subprocess, host path, network or model."""
import copy
import base64
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'recovery-design-candidate'),
               str(HERE.parent / 'diagnostics-candidate')]
import epoch7_recovery_sequence as s
import epoch7_injected_recovery as r
import epoch7_delta as d
from test_epoch7_injected_recovery import prepared


def h(label): return s.sha(label.encode('ascii'))


class SecretError(Exception):
    def __str__(self): raise AssertionError('exception text must never be inspected')
    def __repr__(self): raise AssertionError('exception repr must never be inspected')


class Faults(object):
    def __init__(self): self.events = []; self.failures = {}; self.overrides = {}
    def hit(self, operation):
        self.events.append(operation)
        if operation in self.failures:
            fault = self.failures[operation]
            raise fault() if isinstance(fault, type) else fault


class OuterIO(object):
    def __init__(self, rig): self.rig = rig
    def journal_exists(self, name):
        if name != s.OUTER_NAME: raise AssertionError('outer IO scope')
        return self.rig.ops.journal_exists(name)
    def read_journal(self, name):
        self.rig.faults.hit('outer_read')
        return self.rig.ops.read_journal(name)
    def create_exclusive(self, name, raw, uid, gid, mode):
        self.rig.faults.hit('outer_create_before')
        self.rig.ops.create_exclusive(name, raw, uid, gid, mode)
        self.rig.faults.hit('outer_create_after')
    def replace_exact(self, name, expected, raw, uid, gid, mode):
        stage = json.loads(raw.decode())['state']['stage']
        self.rig.faults.hit('save_before:' + stage)
        self.rig.ops.replace_exact(name, expected, raw, uid, gid, mode)
        self.rig.faults.hit('save_after:' + stage)


class Lock(object):
    def __init__(self, rig): self.rig = rig
    def __enter__(self):
        self.rig.faults.hit('lock_enter'); self.rig.ops.lock = True
    def __exit__(self, *args):
        self.rig.ops.lock = False
        self.rig.faults.hit('lock_exit')


class Controls(object):
    def __init__(self, rig): self.rig = rig; self.reviews = 0
    def result(self, context, operation):
        self.rig.faults.hit(operation)
        return copy.deepcopy(self.rig.faults.overrides.get(operation,
            s.observation(context, operation, h('fixture:' + operation))))
    def install_lock(self): return Lock(self.rig)
    def verify_outer_review(self, context):
        self.reviews += 1
        self.rig.faults.hit('review_' + str(self.reviews))
        return self.result(context, 'verify_outer_review')
    def preflight(self, context):
        assert self.rig.ops.lock
        return self.result(context, 'preflight')
    def before_phase(self, context, phase):
        assert self.rig.ops.lock
        return self.result(context, 'before:' + phase)
    def after_phase(self, context, phase, evidence):
        return self.result(context, 'after:' + phase)


class Containment(object):
    def __init__(self, rig): self.rig = rig
    def run(self, context, operation, unit, diagnostics):
        label = operation if unit is None else operation + ':' + unit
        self.rig.faults.hit('cleanup:' + label)
        return copy.deepcopy(self.rig.faults.overrides.get('cleanup:' + label,
            s.observation(context, label, h('fixture:' + label))))


class Rig(object):
    def __init__(self):
        self.snapshot, self.candidate, self.ops, self.verifier, self.gate, self.payloads = prepared()
        self.ops.lock = False
        self.faults = Faults()
        self.controls = Controls(self)
        self.io = OuterIO(self)
        self.saved_private = []
        self.capture_args = []
        self.capture_result = None
        self.identity_payloads = {}
        self.ops.chmod_generation_exact = self.chmod_generation
        self.driver = self.new_driver()

    def chmod_generation(self, before, after):
        self.faults.hit('chmod_generation')
        assert self.ops.snapshot['generation'] == before
        self.ops.snapshot['generation'] = copy.deepcopy(after)
        return copy.deepcopy(after)

    def publisher(self, evidence):
        self.faults.hit('publish_private')
        self.saved_private.append(copy.deepcopy(evidence))
        return {'name': 'command-e8-n%04d.json' % evidence['sequence'],
                'sha256': h('private bounded fixture')}

    def capture(self, *args):
        self.capture_args.append(args)
        result = copy.deepcopy(self.capture_result)
        result.update(failed_stage=args[1] + '_INTENT', operation=args[2],
                      epoch=args[3], sequence=args[4])
        return result

    def effect(self, phase):
        def run(context, diag):
            if phase == 'rebind_prepared_epoch':
                self.ops.activation = copy.deepcopy(self.candidate['activation'])
            elif phase == 'quiesce_exact_epoch':
                self.ops.activation['state'] = 'QUIESCED'
            elif phase == 'apply_fresh_sandbox':
                self.ops.snapshot['sandbox']['state'] = 'APPLIED'
            elif phase == 'activate_exact_epoch':
                self.ops.activation['state'] = 'ACTIVE'
            result = s.observation(context, phase, h('fixture:' + phase))
            if phase == 'rebind_tls_metadata_only':
                self.ops.preserved['tls']['release_sha256'] = self.candidate['manifest_sha256']
                return {'observation': result, 'tls_change': copy.deepcopy(context['tls_change'])}
            return result
        return run

    def new_driver(self):
        driver = s.InjectedDriver(self.gate, self.controls, self.io, self.ops,
            {p: self.effect(p) for p in s.EXTERNAL_PHASES}, Containment(self),
            s.BoundedDiagnostics(self.publisher, self.capture), self.payloads, self.identity_payloads)
        actual = driver.phase
        def phase(name):
            raw = self.ops.journals[s.OUTER_NAME]['data']
            assert json.loads(raw.decode())['state']['stage'] == name + '_INTENT'
            self.faults.hit('effect:' + name)
            if name in self.faults.overrides: return copy.deepcopy(self.faults.overrides[name])
            return actual(name)
        driver.phase = phase
        return driver

    def run(self): return s.resume_once(self.driver)
    def hold(self, cls=s.RecoveryHold):
        try: self.run()
        except cls as error: return error.state
        raise AssertionError('expected hold')
    def effects(self): return [e[7:] for e in self.faults.events if e.startswith('effect:')]
    def cleanups(self): return [e[8:] for e in self.faults.events if e.startswith('cleanup:')]
    def durable(self): return json.loads(self.ops.journals[s.OUTER_NAME]['data'].decode())['state']


def failed_command(reason='EXIT_NONZERO', interrupted=False):
    # Raw synthetic output exists only in the private evidence fixture.
    result = {'schema': 1, 'failed_stage': 'provision_from_retained_resources_INTENT',
        'operation': 'plugin_install', 'epoch': 8, 'sequence': 1,
        'reason': reason, 'returncode': 1 if reason == 'EXIT_NONZERO' else None,
        'interruption_requires_propagation': interrupted,
        'untrusted_error': 'SYNTHETIC_SECRET'}
    for name in ('stdout', 'stderr'):
        raw = ('SYNTHETIC_SECRET_' + name).encode('ascii')
        result[name] = {'prefix_b64': base64.b64encode(raw).decode('ascii'),
            'prefix_sha256': s.sha(raw), 'retained_bytes': len(raw), 'observed_bytes': len(raw),
            'eof_observed': True, 'truncated': False}
    return result


def two_identity_rig():
    import epoch7_additive_identity as a
    import epoch7_additive_server as server
    from test_epoch7_additive_identity import additive_fixture
    from test_epoch7_additive_server import server_fixture
    rig = Rig()
    config, manifest, sources, proof, review, server_absence, context = server_fixture()
    rig.snapshot, rig.candidate, rig.ops, rig.verifier, rig.payloads = context
    rig.ops.lock = False; rig.ops.chmod_generation_exact = rig.chmod_generation
    server_raw = d.canonical(config)
    server_addition = server.compile_addition(server_raw, a.raw_sha(server_raw), manifest,
        a.raw_sha(manifest), sources, proof, review, server_absence)
    owner, unused, unused_unit, interpreter, owner_absence = additive_fixture()
    manifest_sha = a.raw_sha(manifest)
    owner['release_sha256'] = manifest_sha
    owner['script'] = '/opt/xuanjun-control-releases/integration-' + manifest_sha[:16] + '/' + a.SCRIPT_REL
    owner['argv'] = a.expected_argv(owner['script'])
    unit = ('[Service]\nUser=xuanjun-callback\nGroup=xuanjun-control-db\nExecStart=' +
            ' '.join(owner['argv']) + '\n').encode()
    owner['unit_sha256'] = a.raw_sha(unit)
    rig.candidate['targets'][a.UNIT]['sha256'] = a.raw_sha(unit)
    rig.payloads[a.UNIT] = unit
    owner_raw = d.canonical(owner)
    owner_addition = a.compile_addition(owner_raw, a.raw_sha(owner_raw), manifest,
        manifest_sha, unit, interpreter, owner_absence)
    absences = {a.PATH: owner_absence, server.PATH: server_absence}
    published = {}
    rig.ops.read_additive_absence = lambda path: copy.deepcopy(absences[path])
    rig.ops.read_additive_target = lambda path: copy.deepcopy(published[path])
    def publish(before, raw, after):
        path = before['path']
        rig.faults.hit('publish_identity:' + path)
        assert path not in published
        inner = json.loads(rig.ops.journals[r.ATTEMPT]['data'].decode())
        assert inner['state']['stage'] == 'ADDITIVE_PUBLICATION_INTENT'
        assert a.raw_sha(raw) == after['sha256']
        published[path] = dict(after, dev=1, ino=8001 + len(published), nlink=1)
        return copy.deepcopy(published[path])
    rig.ops.publish_additive_exact = publish
    rig.identity_payloads = {a.PATH: owner_raw, server.PATH: server_raw}
    rig.gate = r.RecoveryGate(rig.snapshot, rig.candidate, d.digest(rig.snapshot),
        h('kit'), h('security'), 7000000000, rig.verifier, rig.ops,
        rig.ops.prior_provision_bytes, additive_deltas=[owner_addition, server_addition])
    rig.ops.preserved = copy.deepcopy(rig.gate.preserved)
    rig.driver = rig.new_driver()
    return rig, published


class SequenceTests(unittest.TestCase):
    def test_locked_approval_precedes_preflight_and_fresh_evidence_is_persisted(self):
        rig=Rig();result=rig.run();events=rig.faults.events
        self.assertLess(events.index('lock_enter'),events.index('review_2'))
        self.assertLess(events.index('review_2'),events.index('preflight'))
        expected=s.observation(rig.driver.context,'preflight',h('fixture:preflight'))
        self.assertEqual(result['preflight_evidence'],expected)
        self.assertEqual(rig.durable()['preflight_evidence'],expected)

    def test_locked_review_refusal_does_not_run_authorized_preflight_commands(self):
        rig=Rig();rig.faults.failures['review_2']=OSError
        state=rig.hold()
        self.assertNotIn('preflight',rig.faults.events)
        self.assertNotIn('preflight_evidence',state)
        self.assertEqual(rig.ops.journals,{})

    def test_complete_actual_inner_phases_then_later_active_outer_receipt(self):
        rig = Rig(); result = rig.run()
        self.assertEqual(rig.effects(), list(s.PHASES))
        self.assertEqual(result['completed'], list(s.PHASES))
        self.assertEqual(result['stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
        self.assertEqual(result['production_acceptance'], 'PENDING')
        self.assertEqual(rig.cleanups(), [])
        self.assertEqual(rig.driver.inner.state['stage'], 'GENERATION_ACCESS_COMPLETE')
        self.assertEqual(rig.ops.snapshot['generation']['mode'], 0o700)
        self.assertEqual(rig.ops.activation['epoch'], 8)
        self.assertEqual(rig.ops.activation['state'], 'ACTIVE')
        self.assertEqual(rig.durable(), result)
        rig.ops.lock = True
        with self.assertRaises(ValueError): rig.gate.check()

    def test_inner_attempt_schema_preserved_and_no_outer_phase_written_into_it(self):
        rig = Rig(); rig.run()
        inner = json.loads(rig.ops.journals[r.ATTEMPT]['data'].decode())
        self.assertNotIn('completed', inner['state'])
        self.assertEqual(inner['name'], r.ATTEMPT)
        self.assertEqual(inner['binding'], rig.gate.journal_binding())

    def test_context_exact_epoch_and_fresh_approval_and_outer_name(self):
        rig = Rig(); c = rig.driver.context
        self.assertEqual((c['expected_epoch'], c['proposed_prepared_epoch']), (7, 8))
        self.assertIn(s.OUTER_NAME, rig.snapshot['absent_paths'])
        self.assertEqual(c['phase_order'], list(s.PHASES))
        self.assertEqual(c['stop_units'], list(s.STOP_UNITS))
        rig.gate.expected['expected_epoch'] = 5
        with self.assertRaises(s.ContractError): s.context_from_gate(rig.gate)

    def test_second_same_object_refused_without_callbacks(self):
        rig = Rig(); rig.run(); count = len(rig.faults.events)
        with self.assertRaisesRegex(s.ContractError, 'ALREADY_USED'): rig.run()
        self.assertEqual(len(rig.faults.events), count)

    def test_new_driver_cannot_adopt_success_partial_or_failed_outer(self):
        for raw in (b'partial', b'{}\n'):
            with self.subTest(raw=raw):
                rig = Rig(); rig.ops.journals[s.OUTER_NAME] = rig.ops.record(raw)
                before = copy.deepcopy(rig.ops.journals)
                result = rig.hold()
                self.assertEqual(result['admission'], 'NOT_GRANTED')
                self.assertEqual(rig.ops.journals, before)
                self.assertEqual(rig.effects() + rig.cleanups(), [])

    def test_existing_inner_attempt_blocks_outer_creation(self):
        rig = Rig(); rig.ops.journals[r.ATTEMPT] = rig.ops.record(b'consumed')
        rig.hold(); self.assertNotIn(s.OUTER_NAME, rig.ops.journals)
        self.assertEqual(rig.effects() + rig.cleanups(), [])

    def test_real_failed_attempt_is_not_replayed_after_new_driver(self):
        rig = Rig(); rig.faults.failures['effect:install_verified_plugin'] = OSError
        rig.hold(); previous = rig.effects()[:]
        rig.faults.failures.clear(); rig.driver = rig.new_driver()
        rig.hold(); self.assertEqual(previous, rig.effects())

    def test_gate_refusal_no_claim_or_cleanup(self):
        rig = Rig(); rig.verifier.reject = True
        state = rig.hold()
        self.assertEqual(state['failed_operation'], 'verify_retained_gate')
        self.assertEqual(rig.ops.journals, {})
        self.assertEqual(rig.effects() + rig.cleanups(), [])

    def test_outer_review_unknown_not_truthy_admission(self):
        rig = Rig(); rig.faults.overrides['verify_outer_review'] = True
        state = rig.hold()
        self.assertEqual(state['admission'], 'NOT_GRANTED')
        self.assertEqual(rig.ops.journals, {})

    def test_outer_create_unknown_consumes_no_runtime_effects_no_retry(self):
        rig = Rig(); rig.faults.failures['outer_create_after'] = OSError
        state = rig.hold()
        self.assertIn(s.OUTER_NAME, rig.ops.journals)
        self.assertNotIn(r.ATTEMPT, rig.ops.journals)
        self.assertEqual(state['admission'], 'UNKNOWN')
        self.assertEqual(state['receipt_status'], 'UNKNOWN')
        self.assertEqual(rig.effects() + rig.cleanups(), [])

    def test_inner_create_unknown_retains_both_claims_no_runtime_effect(self):
        rig = Rig(); old = rig.ops.create_exclusive
        def create(name, *args):
            old(name, *args)
            if name == r.ATTEMPT: raise OSError('synthetic fsync unknown')
        rig.ops.create_exclusive = create
        state = rig.hold()
        self.assertEqual(state['failed_operation'], 'create_inner_attempt')
        self.assertEqual(state['admission'], 'UNKNOWN')
        self.assertIn(s.OUTER_NAME, rig.ops.journals); self.assertIn(r.ATTEMPT, rig.ops.journals)
        self.assertEqual(rig.effects() + rig.cleanups(), [])

    def test_admission_receipt_failure_contains_after_both_claims(self):
        rig = Rig(); rig.faults.failures['save_before:ADMITTED'] = OSError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'admission')
        self.assertEqual(state['failed_operation'], 'save_admission')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))
        self.assertEqual(rig.effects(), [])

    def test_completion_receipt_failure_keeps_full_observed_effect_list(self):
        rig = Rig(); rig.faults.failures['save_after:COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE'] = OSError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'completion')
        self.assertEqual(state['failed_stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
        self.assertEqual(state['completed'], list(s.PHASES))
        self.assertEqual(state['receipt_status'], 'UNKNOWN')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_hold_receipt_failure_preserves_primary_stage_and_operation(self):
        rig = Rig(); rig.faults.failures['effect:install_verified_plugin'] = SecretError
        rig.faults.failures['save_before:HOLD'] = OSError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'install_verified_plugin')
        self.assertEqual(state['failed_stage'], 'install_verified_plugin_INTENT')
        self.assertEqual(state['failed_operation'], 'install_verified_plugin')
        self.assertEqual(state['error_type'], 'Exception')
        self.assertEqual(state['receipt_status'], 'UNKNOWN')
        self.assertEqual(state['secondary_errors'][-1]['operation'], 'save_hold_receipt')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_secret_error_text_and_repr_never_published(self):
        rig = Rig(); rig.faults.failures['effect:stage_exact_release'] = SecretError
        state = rig.hold(); raw = s.packed(state)
        self.assertNotIn(b'SecretError', raw)
        self.assertNotIn(b'SYNTHETIC_SECRET', raw)

    def test_tls_result_wrong_state_certificate_or_nonzero_call_holds(self):
        for key, value in (('retained_state', 'HOLD'), ('certificate_sha256', h('changed')),
                           ('issuance_calls', 1), ('renewal_calls', 1), ('dry_run_calls', 1)):
            with self.subTest(key=key):
                rig = Rig(); handler = rig.driver.handlers['rebind_tls_metadata_only']
                def bad(context, diag):
                    result = handler(context, diag); result['tls_change'][key] = value; return result
                rig.driver.handlers['rebind_tls_metadata_only'] = bad
                state = rig.hold()
                self.assertEqual(state['failed_phase'], 'rebind_tls_metadata_only')
                self.assertNotIn('apply_fresh_sandbox', rig.effects())

    def test_no_tls_issuance_renewal_dryrun_or_prerequisite_replay_api(self):
        rig = Rig(); state = rig.run()
        self.assertEqual(state['coordinator_tls_calls'], {'issue': 0, 'renew': 0, 'dry_run': 0})
        self.assertFalse(state['prerequisite_replay'])
        self.assertEqual(set(rig.driver.handlers), s.EXTERNAL_PHASES)
        self.assertFalse(any(n in s.PHASES for n in ('tls_apply', 'renew', 'issue', 'dry_run', 'restore')))

    def test_unknown_cleanup_does_not_claim_observed(self):
        rig = Rig(); rig.faults.failures['effect:stage_exact_release'] = OSError
        rig.faults.overrides['cleanup:fence'] = s.observation(rig.driver.context, 'fence', None, 'UNKNOWN')
        state = rig.hold()
        self.assertEqual(state['containment_status'], 'UNKNOWN')
        self.assertEqual(state['containment'][0]['status'], 'UNKNOWN')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_unknown_cleanup_preserves_valid_partial_evidence_hash(self):
        rig = Rig(); rig.faults.failures['effect:stage_exact_release'] = OSError
        rig.faults.overrides['cleanup:fence'] = s.observation(rig.driver.context, 'fence', h('partial fence'), 'UNKNOWN')
        state = rig.hold(); row = state['containment'][0]
        self.assertEqual(row['status'], 'UNKNOWN')
        self.assertEqual(row['evidence_sha256'], h('partial fence'))
        self.assertNotIn('error_type', row)
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_unknown_phase_preserves_partial_evidence_without_progression(self):
        rig = Rig(); phase = 'stage_exact_release'
        rig.faults.overrides[phase] = s.observation(rig.driver.context, phase, h('partial phase'), 'UNKNOWN')
        state = rig.hold()
        self.assertEqual(state['phase_evidence'][phase]['evidence_sha256'], h('partial phase'))
        self.assertEqual(state['phase_evidence'][phase]['status'], 'UNKNOWN')
        self.assertEqual(state['completed'], [])
        self.assertEqual(rig.effects(), [phase])

    def test_lock_exit_failure_reports_unknown_without_unlocked_mutation(self):
        rig = Rig(); rig.faults.failures['lock_exit'] = OSError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'lock_release')
        self.assertEqual(state['receipt_status'], 'UNKNOWN')
        self.assertEqual(state['containment_status'], 'UNKNOWN')
        self.assertEqual(rig.cleanups(), [])

    def test_lock_exit_secondary_never_replaces_primary(self):
        rig = Rig(); rig.faults.failures['effect:stage_exact_release'] = OSError
        rig.faults.failures['lock_exit'] = SecretError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'stage_exact_release')
        self.assertEqual(state['secondary_errors'][-1]['operation'], 'release_install_lock')

    def test_interruption_in_primary_cleanup_or_hold_save_propagates_after_all_cleanup(self):
        for cls, expected in ((KeyboardInterrupt, s.RecoveryInterrupted), (SystemExit, s.RecoveryExited)):
            for place in ('effect:stage_exact_release', 'cleanup:fence', 'save_before:HOLD'):
                with self.subTest(cls=cls, place=place):
                    rig = Rig(); rig.faults.failures['effect:stage_exact_release'] = OSError
                    rig.faults.failures[place] = cls
                    state = rig.hold(expected)
                    self.assertEqual(state['failed_phase'], 'stage_exact_release')
                    self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_bound_context_mutation_refused_before_effect(self):
        rig = Rig(); rig.driver.context['expected_epoch'] = 6
        state = rig.hold()
        self.assertEqual(state['admission'], 'NOT_GRANTED'); self.assertEqual(rig.ops.journals, {})

    def test_adapters_cannot_add_unreviewed_extra_phase(self):
        rig = Rig(); handlers = dict(rig.driver.handlers, issue=lambda *a: None)
        with self.assertRaisesRegex(s.ContractError, 'EXACT_PHASE'):
            s.InjectedDriver(rig.gate, rig.controls, rig.io, rig.ops, handlers,
                Containment(rig), rig.driver.diagnostics, rig.payloads, {})

    def test_actual_owner_publication_preserves_inner_intent_and_then_generation(self):
        import epoch7_additive_identity as a
        from test_epoch7_additive_identity import additive_fixture
        rig = Rig()
        config, manifest, unit, interpreter, absence = additive_fixture()
        raw = d.canonical(config) + b'\n'
        addition = a.compile_addition(raw, a.raw_sha(raw), manifest, a.raw_sha(manifest),
                                      unit, interpreter, absence)
        rig.candidate['manifest_sha256'] = config['release_sha256']
        rig.candidate['activation']['release_sha256'] = config['release_sha256']
        rig.candidate['targets'][a.UNIT]['sha256'] = config['unit_sha256']
        rig.payloads[a.UNIT] = unit
        rig.identity_payloads = {a.PATH: raw}
        published = {}
        rig.ops.read_additive_absence = lambda path: copy.deepcopy(absence)
        rig.ops.read_additive_target = lambda path: copy.deepcopy(published[path])
        def publish(before, data, after):
            inner = json.loads(rig.ops.journals[r.ATTEMPT]['data'].decode())
            self.assertEqual(inner['state']['stage'], 'ADDITIVE_PUBLICATION_INTENT')
            self.assertEqual(data, raw); self.assertEqual(before, absence)
            self.assertNotIn(a.PATH, published)
            observed = dict(after, dev=1, ino=7001, nlink=1)
            published[a.PATH] = observed
            return copy.deepcopy(observed)
        rig.ops.publish_additive_exact = publish
        rig.gate = r.RecoveryGate(rig.snapshot, rig.candidate, d.digest(rig.snapshot),
            h('kit'), h('security'), 7000000000, rig.verifier, rig.ops,
            rig.ops.prior_provision_bytes, additive_delta=addition)
        rig.ops.preserved = copy.deepcopy(rig.gate.preserved)
        rig.driver = rig.new_driver()
        state = rig.run()
        self.assertEqual(state['stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
        self.assertEqual(published[a.PATH]['sha256'], a.raw_sha(raw))
        self.assertIn(a.PATH, rig.driver.inner.state['identity_receipts'])
        self.assertIn('epoch7-owner-identity-publication.json', rig.ops.journals)
        self.assertEqual(rig.driver.inner.state['stage'], 'GENERATION_ACCESS_COMPLETE')

    def test_observation_extra_output_or_nonfinite_metadata_is_never_recorded(self):
        for extra in ({'stderr': 'SYNTHETIC_SECRET'}, {'latency': float('nan')}):
            with self.subTest(extra=list(extra)):
                rig = Rig(); result = s.observation(rig.driver.context, 'stage_exact_release', h('x'))
                result.update(extra); rig.faults.overrides['stage_exact_release'] = result
                state = rig.hold()
                self.assertEqual(state['failed_phase'], 'stage_exact_release')
                self.assertNotIn('stage_exact_release', state['phase_evidence'])
                self.assertNotIn(b'SYNTHETIC_SECRET', s.packed(state))

    def test_both_reviewed_identity_publishers_run_with_distinct_receipts(self):
        rig, published = two_identity_rig(); state = rig.run()
        self.assertEqual(rig.gate.expected['total_target_count'], 26)
        self.assertEqual(rig.gate.expected['retained_target_count'], 24)
        self.assertEqual(len(published), 2)
        self.assertEqual(len(rig.driver.inner.state['identity_receipts']), 2)
        self.assertEqual(rig.driver.inner.state['stage'], 'GENERATION_ACCESS_COMPLETE')
        self.assertEqual(state['stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
        for name in ('epoch7-owner-identity-publication.json', 'epoch7-server-identity-publication.json'):
            self.assertIn(name, rig.ops.journals)

    def test_second_identity_failure_retains_first_and_skips_generation(self):
        rig, published = two_identity_rig()
        last_path = rig.gate.additions[1]['path']
        rig.faults.failures['publish_identity:' + last_path] = OSError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'publish_reviewed_identities')
        self.assertEqual(len(published), 1)
        self.assertNotIn('change_generation_access', rig.effects())
        self.assertEqual(rig.driver.inner.state['stage'], 'ADDITIVE_PUBLICATION_INTENT')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))


class DiagnosticTests(unittest.TestCase):
    def command_rig(self, reason='EXIT_NONZERO', interrupted=False):
        rig = Rig(); rig.capture_result = failed_command(reason, interrupted)
        def plugin(context, diag):
            return diag.capture_owned(object(), 'install_verified_plugin', 'plugin_install',
                                      timeout_seconds=12, cleanup_seconds=1, stream_limit=1024)
        rig.driver.handlers['install_verified_plugin'] = plugin
        return rig

    def test_bounded_capture_parameters_and_static_phase_map(self):
        rig = self.command_rig(); state = rig.hold()
        args = rig.capture_args[0]
        self.assertEqual(args[1:], ('provision_from_retained_resources', 'plugin_install', 8, 1, 12, 1, 1024))
        self.assertEqual(state['failed_phase'], 'install_verified_plugin')
        self.assertEqual(state['failed_operation'], 'plugin_install')
        self.assertEqual(state['command_failure']['diagnostic_state'], 'PERSISTED_PRIVATE')
        self.assertEqual(len(rig.saved_private), 1)
        self.assertNotIn(b'SYNTHETIC_SECRET', s.packed(state))
        self.assertNotIn(b'prefix_b64', s.packed(state))

    def test_containment_precedes_private_publish_and_hold_receipt(self):
        rig = self.command_rig(); rig.hold()
        events = rig.faults.events
        last_cleanup = max(i for i, e in enumerate(events) if e.startswith('cleanup:'))
        self.assertLess(last_cleanup, events.index('publish_private'))
        self.assertLess(events.index('publish_private'), events.index('save_before:HOLD'))

    def test_private_publication_and_hold_receipt_both_fail_keep_primary(self):
        rig = self.command_rig(); rig.faults.failures['publish_private'] = SecretError
        rig.faults.failures['save_after:HOLD'] = OSError
        state = rig.hold()
        self.assertEqual(state['failed_phase'], 'install_verified_plugin')
        self.assertEqual(state['failed_operation'], 'plugin_install')
        self.assertEqual(state['command_failure']['diagnostic_state'], 'UNAVAILABLE')
        self.assertEqual(state['receipt_status'], 'UNKNOWN')
        self.assertEqual(rig.faults.events.count('publish_private'), 1)
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_cleanup_interruption_flag_propagates_even_with_success_or_timeout_reason(self):
        for reason in ('TIMEOUT', 'SUCCESS'):
            with self.subTest(reason=reason):
                rig = self.command_rig(reason, True)
                state = rig.hold(s.RecoveryInterrupted)
                self.assertEqual(state['failed_operation'], 'plugin_install')
                self.assertEqual(state['command_failure']['reason'], reason)
                self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_captured_systemexit_from_main_or_cleanup_propagates_systemexit(self):
        for source in ('main', 'cleanup'):
            with self.subTest(source=source):
                rig = self.command_rig('TIMEOUT', True)
                if source == 'main': rig.capture_result['failure_class'] = 'SystemExit'
                else: rig.capture_result['cleanup'] = {'reap_error_class': 'SystemExit'}
                state = rig.hold(s.RecoveryExited)
                self.assertEqual(state['interruption'], 'SystemExit')
                self.assertEqual(state['failed_operation'], 'plugin_install')
                self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_original_command_failure_survives_handler_finally_failure(self):
        rig = self.command_rig()
        original = rig.driver.handlers['install_verified_plugin']
        def handler(*args):
            try: original(*args)
            finally: raise OSError('synthetic rollback callback error')
        rig.driver.handlers['install_verified_plugin'] = handler
        state = rig.hold()
        self.assertEqual(state['failed_operation'], 'plugin_install')
        self.assertEqual(state['error_type'], 'BoundedCommandFailure')
        self.assertEqual(state['command_failure']['reason'], 'EXIT_NONZERO')
        self.assertIn({'operation': 'subsequent_phase_error', 'error_type': 'OSError'}, state['secondary_errors'])
        self.assertEqual(len(rig.saved_private), 1)

    def test_swallowed_command_failure_cannot_become_phase_success(self):
        rig = self.command_rig(); original = rig.driver.handlers['install_verified_plugin']
        def handler(context, diag):
            try: original(context, diag)
            except s.CommandFailure: pass
            return s.observation(context, 'install_verified_plugin', h('pretended success'))
        rig.driver.handlers['install_verified_plugin'] = handler
        state = rig.hold()
        self.assertEqual(state['failed_operation'], 'plugin_install')
        self.assertNotIn('install_verified_plugin', state['completed'])

    def test_cleanup_command_diagnostics_publish_only_after_all_cleanup(self):
        rig = self.command_rig(); original = rig.driver.containment.run
        def contain(context, operation, unit, diag):
            if operation == 'stop_unit' and unit == s.STOP_UNITS[0]:
                rig.faults.hit('cleanup:' + operation + ':' + unit)
                try:
                    diag.capture_owned(object(), 'install_verified_plugin', 'service_stop', 1)
                finally:
                    raise OSError('secondary callback error')
            return original(context, operation, unit, diag)
        rig.driver.containment.run = contain
        state = rig.hold()
        self.assertEqual(state['failed_operation'], 'plugin_install')
        row = state['containment'][1]
        self.assertEqual(row['status'], 'UNKNOWN')
        self.assertEqual(row['command_failure']['operation'], 'service_stop')
        self.assertEqual(row['command_failure']['diagnostic_state'], 'PERSISTED_PRIVATE')
        self.assertEqual([x['sequence'] for x in rig.saved_private], [1, 2])
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))
        last = max(i for i, e in enumerate(rig.faults.events) if e.startswith('cleanup:'))
        self.assertGreater(rig.faults.events.index('publish_private'), last)

    def test_secondary_command_publisher_failure_and_interrupt_do_not_skip_cleanup(self):
        for failure, raised in ((OSError, s.RecoveryHold), (SystemExit, s.RecoveryExited)):
            with self.subTest(failure=failure):
                rig = self.command_rig(); original = rig.driver.containment.run
                def contain(context, operation, unit, diag):
                    if operation == 'fence':
                        rig.faults.hit('cleanup:fence')
                        diag.capture_owned(object(), 'install_verified_plugin', 'service_stop', 1)
                    return original(context, operation, unit, diag)
                rig.driver.containment.run = contain
                original_publisher = rig.publisher
                def publisher(evidence):
                    if evidence['sequence'] == 2: raise failure()
                    return original_publisher(evidence)
                rig.driver.diagnostics.publisher = publisher
                state = rig.hold(raised)
                self.assertEqual(state['failed_operation'], 'plugin_install')
                self.assertEqual(state['command_failure']['diagnostic_state'], 'PERSISTED_PRIVATE')
                self.assertEqual(state['containment'][0]['command_failure']['diagnostic_state'], 'UNAVAILABLE')
                self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_cleanup_original_systemexit_precedes_later_finally_keyboardinterrupt(self):
        rig = Rig(); rig.faults.failures['effect:install_verified_plugin'] = OSError
        original = rig.driver.containment.run
        def contain(context, operation, unit, diag):
            if operation == 'fence':
                rig.faults.hit('cleanup:fence')
                try:
                    raise diag.record_adapter_failure('install_verified_plugin', 'service_stop',
                                                       'SystemExit', 'SPAWN_UNCONFIRMED')
                finally: raise KeyboardInterrupt()
            return original(context, operation, unit, diag)
        rig.driver.containment.run = contain
        state = rig.hold(s.RecoveryExited)
        self.assertEqual(state['interruption'], 'SystemExit')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_private_publication_interrupt_propagates_after_cleanup(self):
        rig = self.command_rig(); rig.faults.failures['publish_private'] = KeyboardInterrupt
        state = rig.hold(s.RecoveryInterrupted)
        self.assertEqual(state['failed_operation'], 'plugin_install')
        self.assertEqual(state['command_failure']['diagnostic_state'], 'UNAVAILABLE')

    def test_invalid_private_reference_is_not_copied_to_public_receipt(self):
        rig = self.command_rig(); rig.driver.diagnostics.publisher = lambda e: {
            'name': 'credentials-in-name', 'sha256': h('bad')}
        state = rig.hold()
        self.assertEqual(state['command_failure']['diagnostic_state'], 'UNAVAILABLE')
        self.assertNotIn(b'credentials-in-name', s.packed(state))

    def test_command_sequence_no_reuse_and_explicit_bound(self):
        rig = Rig(); rig.capture_result = failed_command('SUCCESS')
        rig.capture_result['returncode'] = 0
        diag = rig.driver.diagnostics
        for unused in range(2): diag.capture_owned(object(), 'install_verified_plugin', 'plugin_inventory', 1)
        self.assertEqual([a[4] for a in rig.capture_args], [1, 2])
        diag.sequence = s.MAX_COMMANDS
        with self.assertRaisesRegex(s.ContractError, 'COUNT'):
            diag.capture_owned(object(), 'install_verified_plugin', 'plugin_inventory', 1)
        self.assertEqual(len(rig.capture_args), 2)

    def test_invalid_command_limits_reject_before_capture(self):
        for kwargs in ({'timeout_seconds': 0}, {'timeout_seconds': 601},
            {'timeout_seconds': True}, {'timeout_seconds': float('inf')},
            {'timeout_seconds': 1, 'cleanup_seconds': 3},
            {'timeout_seconds': 1, 'stream_limit': 1048577}):
            with self.subTest(kwargs=kwargs):
                rig = Rig()
                with self.assertRaises(s.ContractError):
                    rig.driver.diagnostics.capture_owned(object(), 'install_verified_plugin',
                                                         'plugin_install', **kwargs)
                self.assertEqual(rig.capture_args, [])

    def test_protected_diagnostic_real_capture_dependency_unchanged(self):
        diag = s.BoundedDiagnostics(lambda value: None)
        self.assertIs(diag.capture, s.diagnostics.capture_owned_process)
        self.assertEqual(s.diagnostics.MAX_CLEANUP_SECONDS, 2.0)
        self.assertEqual(s.diagnostics.MAX_STREAM_BYTES, 1048576)

    def test_exact_expected_nonzero_returns_actual_summary_without_failure(self):
        rig = Rig(); rig.capture_result = failed_command()
        diag = rig.driver.diagnostics
        result = diag.capture_owned(object(), 'install_verified_plugin', 'service_is_active',
                                    1, accepted_returncodes=(1, 3))
        self.assertEqual(result['reason'], 'EXIT_NONZERO')
        self.assertEqual(result['returncode'], 1)
        self.assertIsNone(diag.scope_failure)
        self.assertEqual(rig.saved_private, [])

    def test_private_completed_process_has_no_argv_and_validated_bytes(self):
        rig = Rig(); rig.capture_result = failed_command()
        result = rig.driver.diagnostics.capture_owned(object(), 'install_verified_plugin',
            'plugin_inventory', 1, accepted_returncodes=(1,), return_output=True)
        self.assertIsNone(result.args)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'SYNTHETIC_SECRET_stdout')
        self.assertEqual(result.stderr, b'SYNTHETIC_SECRET_stderr')
        self.assertEqual(rig.saved_private, [])

    def test_unexpected_zero_is_failure_when_only_nonzero_was_reviewed(self):
        rig = Rig(); rig.capture_result = failed_command('SUCCESS')
        rig.capture_result['returncode'] = 0
        with self.assertRaises(s.CommandFailure) as caught:
            rig.driver.diagnostics.capture_owned(object(), 'install_verified_plugin',
                'service_is_active', 1, accepted_returncodes=(1,))
        self.assertEqual(caught.exception.summary['reason'], 'SUCCESS')
        self.assertEqual(caught.exception.summary['returncode'], 0)

    def test_accepted_codes_cannot_accept_timeout_or_interrupt(self):
        for reason, interrupted in (('TIMEOUT', False), ('EXIT_NONZERO', True)):
            with self.subTest(reason=reason):
                rig = Rig(); rig.capture_result = failed_command(reason, interrupted)
                rig.capture_result['returncode'] = 1
                with self.assertRaises(s.CommandFailure):
                    rig.driver.diagnostics.capture_owned(object(), 'install_verified_plugin',
                        'service_is_active', 1, accepted_returncodes=(1,))

    def test_bad_accepted_code_contract_refused_before_capture(self):
        for codes in ((), (True,), (-1,), (256,), (1, 1), range(2), (0,) * 9):
            with self.subTest(codes=str(type(codes))):
                rig = Rig()
                with self.assertRaises(s.ContractError):
                    rig.driver.diagnostics.capture_owned(object(), 'install_verified_plugin',
                        'plugin_inventory', 1, accepted_returncodes=codes)
                self.assertEqual(rig.capture_args, [])

    def test_accepted_private_output_must_be_complete_bounded_and_hash_bound(self):
        for changes in ({'eof_observed': False}, {'truncated': True},
            {'prefix_sha256': h('wrong')}, {'prefix_b64': 'not base64'},
            {'retained_bytes': True}, {'observed_bytes': 999999}):
            with self.subTest(changes=list(changes)):
                rig = Rig(); rig.capture_result = failed_command()
                rig.capture_result['stdout'].update(changes)
                with self.assertRaises(s.ContractError):
                    rig.driver.diagnostics.capture_owned(object(), 'install_verified_plugin',
                        'plugin_inventory', 1, accepted_returncodes=(1,), return_output=True)


class OuterJournalTests(unittest.TestCase):
    def journal(self):
        rig = Rig(); rig.ops.lock = True; rig.gate.check()
        journal = s.OuterJournal(rig.io, rig.driver.context, rig.gate.journal_binding())
        return rig, journal

    def test_private_metadata_and_canonical_readback(self):
        rig, journal = self.journal(); journal.create({'stage': 'ADMITTED'})
        self.assertEqual((journal.last['uid'], journal.last['gid'], journal.last['mode'], journal.last['nlink']),
                         (0, 0, 0o600, 1))
        journal.save({'stage': 'HOLD'})
        self.assertEqual(rig.durable()['stage'], 'HOLD')

    def test_mutated_binding_rejected_and_poisoned(self):
        rig, journal = self.journal(); journal.create({'stage': 'ADMITTED'})
        record = rig.ops.journals[s.OUTER_NAME]
        data = json.loads(record['data'].decode()); data['context_sha256'] = h('wrong')
        record['data'] = s.packed(data)
        with self.assertRaisesRegex(s.ContractError, 'BINDING'): journal.save({'stage': 'HOLD'})
        self.assertTrue(journal.poisoned)

    def test_inode_drift_rejects_no_adoption(self):
        rig, journal = self.journal(); journal.create({'stage': 'ADMITTED'})
        rig.ops.journals[s.OUTER_NAME]['ino'] += 1
        with self.assertRaisesRegex(s.ContractError, 'CAS_DRIFT'): journal.save({'stage': 'HOLD'})
        self.assertTrue(journal.poisoned)

    def test_receipt_bound_before_creation(self):
        rig, journal = self.journal()
        with self.assertRaisesRegex(s.ContractError, 'BOUND'):
            journal.create({'stage': 'ADMITTED', 'padding': 'x' * s.MAX_JOURNAL_BYTES})
        self.assertNotIn(s.OUTER_NAME, rig.ops.journals)

    def test_no_save_or_recreate_after_uncertain_replace(self):
        rig, journal = self.journal(); journal.create({'stage': 'ADMITTED'})
        rig.faults.failures['save_after:HOLD'] = OSError
        with self.assertRaises(OSError): journal.save({'stage': 'HOLD'})
        before = len(rig.faults.events)
        with self.assertRaises(s.ContractError): journal.save({'stage': 'HOLD'})
        with self.assertRaises(s.ContractError): journal.create({'stage': 'ADMITTED'})
        self.assertEqual(len(rig.faults.events), before)


class AdapterFailureTests(unittest.TestCase):
    def test_spawn_allocates_once_and_records_no_fake_capture(self):
        rig = Rig(); diag = rig.driver.diagnostics
        failure = diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                               'OSError', 'SPAWN_UNCONFIRMED')
        self.assertIsInstance(failure, s.CommandFailure)
        self.assertEqual(diag.sequence, 1)
        self.assertIsNone(failure.private)
        self.assertEqual(failure.summary['diagnostic_state'], 'UNAVAILABLE')
        self.assertEqual(failure.summary['reason'], 'SPAWN_UNCONFIRMED')
        self.assertFalse(any(k in failure.summary for k in ('stdout', 'stderr', 'diagnostic_reference')))
        same = diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                           'Exception', 'SPAWN_UNCONFIRMED')
        self.assertIs(same, failure); self.assertEqual(diag.sequence, 1)

    def test_unexpected_capture_exception_reuses_allocation(self):
        rig = Rig(); diag = rig.driver.diagnostics
        diag.capture = lambda *args: (_ for _ in ()).throw(OSError())
        with self.assertRaises(OSError):
            diag.capture_owned(object(), 'install_verified_plugin', 'plugin_install', 1)
        self.assertEqual(diag.sequence, 1)
        failure = diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                               'OSError', 'CAPTURE_UNCONFIRMED')
        self.assertEqual(failure.summary['sequence'], 1)
        self.assertEqual(diag.sequence, 1)
        self.assertIsNone(diag.capture_allocation)

    def test_capture_refusal_before_allocation_gets_one_failure_sequence(self):
        rig = Rig(); diag = rig.driver.diagnostics
        with self.assertRaises(s.ContractError):
            diag.capture_owned(object(), 'install_verified_plugin', 'plugin_install', 0)
        failure = diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                               'ContractError', 'CAPTURE_UNCONFIRMED')
        self.assertEqual(failure.summary['sequence'], 1)

    def test_capture_allocation_cannot_be_claimed_for_other_command(self):
        rig = Rig(); diag = rig.driver.diagnostics
        diag.capture = lambda *args: (_ for _ in ()).throw(OSError())
        with self.assertRaises(OSError):
            diag.capture_owned(object(), 'install_verified_plugin', 'plugin_install', 1)
        for phase, operation, stage in (('stage_exact_release', 'plugin_install', 'CAPTURE_UNCONFIRMED'),
            ('install_verified_plugin', 'plugin_enable', 'CAPTURE_UNCONFIRMED'),
            ('install_verified_plugin', 'plugin_install', 'SPAWN_UNCONFIRMED')):
            with self.assertRaises(s.ContractError):
                diag.record_adapter_failure(phase, operation, 'OSError', stage)
        self.assertEqual(diag.sequence, 1)

    def test_scope_reset_refuses_unrecorded_capture(self):
        rig = Rig(); diag = rig.driver.diagnostics
        diag.capture = lambda *args: (_ for _ in ()).throw(OSError())
        with self.assertRaises(OSError):
            diag.capture_owned(object(), 'install_verified_plugin', 'plugin_install', 1)
        with self.assertRaisesRegex(s.ContractError, 'UNRECORDED'):
            diag.start_scope('cleanup:fence')

    def test_adapter_failure_cannot_be_overwritten_or_swallowed_by_handler(self):
        for later in ('raise', 'swallow'):
            with self.subTest(later=later):
                rig = Rig()
                def plugin(context, diag):
                    failure = diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                                          'OSError', 'SPAWN_UNCONFIRMED')
                    if later == 'raise':
                        try: raise failure
                        finally: raise SecretError()
                    return s.observation(context, 'install_verified_plugin', h('false success'))
                rig.driver.handlers['install_verified_plugin'] = plugin
                state = rig.hold()
                self.assertEqual(state['failed_operation'], 'plugin_install')
                self.assertEqual(state['command_failure']['reason'], 'SPAWN_UNCONFIRMED')
                self.assertEqual(state['command_failure']['diagnostic_state'], 'UNAVAILABLE')
                self.assertEqual(rig.saved_private, [])
                self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_adapter_original_interrupt_type_survives_finally_failure(self):
        for error_class, caught in (('KeyboardInterrupt', s.RecoveryInterrupted), ('SystemExit', s.RecoveryExited)):
            with self.subTest(error_class=error_class):
                rig = Rig()
                def plugin(context, diag):
                    try:
                        raise diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                                          error_class, 'SPAWN_UNCONFIRMED')
                    finally: raise OSError()
                rig.driver.handlers['install_verified_plugin'] = plugin
                state = rig.hold(caught)
                self.assertEqual(state['interruption'], error_class)
                self.assertEqual(state['failed_operation'], 'plugin_install')
                self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))

    def test_secondary_emergency_cleanup_interrupt_still_propagates(self):
        rig = Rig()
        def plugin(context, diag):
            diag.record_adapter_failure('install_verified_plugin', 'plugin_install',
                                        'OSError', 'CAPTURE_UNCONFIRMED')
            raise SystemExit(999)
        rig.driver.handlers['install_verified_plugin'] = plugin
        state = rig.hold(s.RecoveryExited)
        self.assertEqual(state['command_failure']['adapter_error_type'], 'OSError')
        self.assertEqual(state['interruption'], 'SystemExit')

    def test_only_fixed_adapter_stage_and_error_labels(self):
        for error_class, stage in (('PasswordError:secret', 'SPAWN_UNCONFIRMED'),
            ('OSError', 'secret-spawn-output'), ('ValueError', 'CAPTURE_UNCONFIRMED')):
            rig = Rig()
            with self.assertRaises(s.ContractError):
                rig.driver.diagnostics.record_adapter_failure('install_verified_plugin',
                    'plugin_install', error_class, stage)
            self.assertEqual(rig.driver.diagnostics.sequence, 0)

    def test_spawn_failure_at_command_bound_refuses_without_counter_wrap(self):
        rig = Rig(); diag = rig.driver.diagnostics; diag.sequence = s.MAX_COMMANDS
        with self.assertRaises(s.ContractError):
            diag.record_adapter_failure('install_verified_plugin', 'plugin_install', 'OSError', 'SPAWN_UNCONFIRMED')
        self.assertEqual(diag.sequence, s.MAX_COMMANDS)

    def test_unrecorded_capture_exception_cannot_block_outer_cleanup_scopes(self):
        rig = Rig(); rig.driver.diagnostics.capture = lambda *a: (_ for _ in ()).throw(OSError())
        def plugin(context, diag):
            return diag.capture_owned(object(), 'install_verified_plugin', 'plugin_install', 1)
        rig.driver.handlers['install_verified_plugin'] = plugin
        state = rig.hold()
        self.assertEqual(state['command_failure']['reason'], 'CAPTURE_UNCONFIRMED')
        self.assertEqual(state['failed_operation'], 'plugin_install')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))


class CompleteApprovalIntegrationTests(unittest.TestCase):
    def verifier_rig(self, fail_second=False):
        sys.path.insert(0, str(HERE.parent / 'approval-candidate'))
        from epoch7_complete_approval import CompleteApprovalVerifier
        rig = Rig(); fetches = []
        def fetch(review_id, expected):
            fetches.append((review_id, copy.deepcopy(expected)))
            if fail_second and len(fetches) == 2: raise OSError('synthetic transport failure')
            return {'review_id': review_id, 'body_sha256': h('authenticated fixture body'),
                    'approval': copy.deepcopy(expected)}
        verifier = CompleteApprovalVerifier(rig.gate.review_id, h('authenticated fixture body'),
            lambda: rig.ops.lock, fetcher=fetch)
        rig.gate.verifier = verifier
        verifier.bind(rig.gate, h('compiled fixture plan'))
        rig.controls.verify_outer_review = verifier.verify_outer_review
        return rig, verifier, fetches

    def test_one_complete_body_satisfies_outer_and_inner_without_effect_time_fetches(self):
        rig, verifier, fetches = self.verifier_rig()
        state = rig.run()
        self.assertEqual(state['stage'], 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
        self.assertEqual(len(fetches), 2)
        self.assertEqual(fetches[0], fetches[1])
        self.assertEqual(verifier.wanted['retained_authorization'], rig.gate.expected)
        self.assertNotIn('review_id', verifier.wanted['sequence_contract'])
        self.assertNotIn('context_sha256', verifier.wanted['sequence_contract'])

    def test_failed_locked_recheck_revokes_verifier_and_prevents_claim(self):
        rig, verifier, fetches = self.verifier_rig(fail_second=True)
        state = rig.hold()
        self.assertEqual(state['failed_operation'], 'verify_outer_review')
        self.assertEqual(len(fetches), 2)
        self.assertFalse(verifier.checked_under_lock)
        self.assertEqual(rig.ops.journals, {})
        self.assertEqual(rig.effects() + rig.cleanups(), [])
        self.assertEqual(rig.saved_private, [])

    def test_unrecorded_cleanup_capture_exception_cannot_skip_later_units(self):
        rig = Rig(); rig.faults.failures['effect:install_verified_plugin'] = OSError
        rig.driver.diagnostics.capture = lambda *a: (_ for _ in ()).throw(OSError())
        original = rig.driver.containment.run
        def containment(context, operation, unit, diag):
            if operation == 'fence':
                rig.faults.hit('cleanup:fence')
                return diag.capture_owned(object(), 'install_verified_plugin', 'service_stop', 1)
            return original(context, operation, unit, diag)
        rig.driver.containment.run = containment
        state = rig.hold()
        self.assertEqual(state['containment'][0]['command_failure']['reason'], 'CAPTURE_UNCONFIRMED')
        self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))


def add_matrix():
    def phase_case(phase, location):
        def test(self):
            rig = Rig()
            labels = {'effect': 'effect:' + phase, 'before': 'before:' + phase,
                'after': 'after:' + phase, 'intent': 'save_before:' + phase + '_INTENT',
                'complete': 'save_after:' + phase + '_COMPLETE'}
            rig.faults.failures[labels[location]] = OSError
            state = rig.hold()
            self.assertEqual(state['failed_phase'], phase)
            stage = phase + ('_COMPLETE' if location == 'complete' else '_INTENT')
            self.assertEqual(state['failed_stage'], stage)
            self.assertFalse(state['automatic_retry'])
            self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))
            self.assertNotIn(phase, rig.effects() if location in ('before', 'intent') else [])
            index = s.PHASES.index(phase)
            self.assertFalse(any(p in rig.effects() for p in s.PHASES[index + 1:]))
            if location in ('intent', 'complete'):
                self.assertEqual(state['receipt_status'], 'UNKNOWN')
        return test
    for phase in s.PHASES:
        for location in ('before', 'effect', 'after', 'intent', 'complete'):
            setattr(SequenceTests, 'test_matrix_' + location + '_' + phase, phase_case(phase, location))
        def unknown(self, phase=phase):
            rig = Rig(); rig.faults.overrides[phase] = s.observation(rig.driver.context, phase, h('uncertain'), 'UNKNOWN')
            state = rig.hold()
            self.assertEqual(state['failed_phase'], phase)
            self.assertNotIn(phase, state['completed'])
            self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))
        setattr(SequenceTests, 'test_matrix_unknown_' + phase, unknown)
    for index, (operation, unit) in enumerate(s.CLEANUP):
        label = operation if unit is None else operation + ':' + unit
        def cleanup(self, label=label):
            rig = Rig(); rig.faults.failures['effect:stage_exact_release'] = OSError
            rig.faults.failures['cleanup:' + label] = KeyboardInterrupt
            state = rig.hold(s.RecoveryInterrupted)
            self.assertEqual(len(rig.cleanups()), len(s.CLEANUP))
            self.assertEqual(state['failed_phase'], 'stage_exact_release')
            self.assertEqual(state['containment_status'], 'UNKNOWN')
            self.assertEqual(sum(x['status'] == 'UNKNOWN' for x in state['containment']), 1)
        setattr(SequenceTests, 'test_cleanup_independence_%02d' % index, cleanup)
    for label in ('review_1', 'lock_enter', 'preflight', 'review_2'):
        def refuse(self, label=label):
            rig = Rig(); rig.faults.failures[label] = OSError
            state = rig.hold()
            self.assertEqual(state['admission'], 'NOT_GRANTED')
            self.assertEqual(rig.ops.journals, {})
            self.assertEqual(rig.effects() + rig.cleanups(), [])
        setattr(SequenceTests, 'test_admission_refusal_' + label, refuse)


add_matrix()
if __name__ == '__main__': unittest.main()
