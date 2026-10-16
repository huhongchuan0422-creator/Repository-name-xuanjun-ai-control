"""Offline, injected epoch7 -> epoch8 one-attempt coordinator. No entrypoint.

This is control flow, not a host driver or authority verifier. Every external
effect, live observation, lock and receipt backend must be supplied explicitly.
The narrow pre-active RecoveryGate and its inner attempt remain unchanged.
The separate outer receipt requires a new reviewed absence/IO contract.
"""
import copy
import base64
import hashlib
import json
import math
import subprocess

import epoch7_delta as d
import epoch7_claim_successor as successor
import epoch7_injected_recovery as retained
import protected_command_evidence as diagnostics


OUTER_NAME = successor.NEW_OUTER
PHASES = (
    'stage_exact_release', 'preserve_prior_receipts', 'rebind_prepared_epoch',
    'quiesce_exact_epoch', 'replace_retained_targets',
    'publish_reviewed_identities', 'change_generation_access',
    'apply_reviewed_access', 'rebind_tls_metadata_only', 'apply_fresh_sandbox',
    'install_verified_plugin', 'reopen_existing_database',
    'verify_runtime_access', 'activate_exact_epoch', 'activate_new_services',
    'post_install_checks')
BUILTIN_PHASES = frozenset(('replace_retained_targets',
    'publish_reviewed_identities', 'change_generation_access'))
EXTERNAL_PHASES = frozenset(PHASES) - BUILTIN_PHASES
STOP_UNITS = (
    'xuanjun-p2-tls-renew.timer', 'xuanjun-p2-tls-renew.service',
    'xuanjun-github-intake.timer', 'xuanjun-ledger.socket',
    'xj-root-broker.socket', 'xuanjun-github-intake.service',
    'xuanjun-development-dispatcher.service',
    'xuanjun-p2-gateway-relay.service', 'xuanjun-p2-gateway-relay.socket',
    'xuanjun-uk-owner-callback.service', 'xuanjun-uk-owner-dashboard.service',
    'xuanjun-ledger.service', 'xj-root-broker.service', 'nginx.service',
    'xuanjun-uk-openclaw.service')
CLEANUP = (('fence', None),) + tuple(('stop_unit', u) for u in STOP_UNITS) + tuple(
    ('observe_stopped_before', u) for u in STOP_UNITS) + (
    ('preserve_boot_inhibition', None), ('restore_exact_owner_masks', None),
    ('preserve_legacy_masks', None), ('restore_owned_epoch7_sandbox', None)) + tuple(
    ('observe_stopped_after', u) for u in STOP_UNITS) + (
    ('verify_legacy_exclusion', None), ('verify_retained_tls', None))
CLEANUP_METHODS = frozenset(x[0] for x in CLEANUP)
MAX_JOURNAL_BYTES = 262144
MAX_COMMANDS = 9999
ADAPTER_BOUNDS = {'guard_timeout_seconds': 30, 'phase_timeout_seconds': 600,
    'cleanup_operation_timeout_seconds': 45, 'command_cleanup_seconds': 2,
    'command_stream_limit_bytes': 65536, 'outer_receipt_limit_bytes': MAX_JOURNAL_BYTES}
COMMAND_PHASE = dict((p, p if p in diagnostics.PHASES else
    'provision_from_retained_resources') for p in PHASES)


def need(value, reason):
    if not value:
        raise ContractError(reason)


class ContractError(ValueError):
    """Only fixed source labels; never external exception/output text."""


def error_class(error):
    if isinstance(error, KeyboardInterrupt): return 'KeyboardInterrupt'
    if isinstance(error, SystemExit): return 'SystemExit'
    if isinstance(error, OSError): return 'OSError'
    if isinstance(error, ContractError): return 'ContractError'
    if isinstance(error, CommandFailure): return 'BoundedCommandFailure'
    return 'Exception'


def packed(value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False) + '\n').encode('utf-8')
    need(len(raw) <= MAX_JOURNAL_BYTES, 'SEQUENCE_RECEIPT_BOUND')
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def observation(context, operation, evidence_sha256, status='OBSERVED'):
    """Construct a content-free envelope; this does NOT authenticate evidence."""
    value = {'context_sha256': context['context_sha256'], 'operation': operation,
             'status': status, 'evidence_sha256': evidence_sha256}
    return value


def check_observation(value, context, operation, require_observed=True):
    need(type(value) is dict and set(value) == {
        'context_sha256', 'operation', 'status', 'evidence_sha256'},
        'OBSERVATION_EXACT_SCHEMA')
    need(value['context_sha256'] == context['context_sha256'] and
         value['operation'] == operation and value['status'] in ('OBSERVED', 'UNKNOWN'),
         'OBSERVATION_BINDING')
    if value['evidence_sha256'] is not None:
        d.hash_value(value['evidence_sha256'])
    need(value['status'] != 'OBSERVED' or value['evidence_sha256'] is not None,
         'OBSERVED_EVIDENCE_REQUIRED')
    if require_observed:
        need(value['status'] == 'OBSERVED', 'OBSERVATION_UNKNOWN')
    return copy.deepcopy(value)


def context_from_gate(gate):
    """Parameterize only the already compiled exact 7 -> 8 proposal, no defaults."""
    need(isinstance(gate, retained.RecoveryGate), 'REVIEWED_GATE_REQUIRED')
    expected = gate.expected
    need(expected['transaction_id'] == d.TX and type(expected['expected_epoch']) is int
         and expected['expected_epoch'] == 7 and
         type(expected['proposed_prepared_epoch']) is int and
         expected['proposed_prepared_epoch'] == 8 and
         expected['authorized_attempts'] == 1 and
         expected['tls_issuance_renewal_or_dry_run'] is False and
         expected['automatic_retry'] is False, 'EXACT_EPOCH7_EPOCH8_POLICY')
    value = {'schema': 1, 'transaction_id': d.TX, 'expected_epoch': 7,
        'proposed_prepared_epoch': 8, 'review_id': gate.review_id,
        'authorization_sha256': d.digest(expected),
        'snapshot_sha256': gate.delta['snapshot_sha256'],
        'candidate_sha256': gate.delta['candidate_sha256'],
        'runtime_manifest_sha256': gate.delta['runtime_manifest_sha256'],
        'delta_sha256': gate.delta_sha256,
        'kit_manifest_sha256': expected['kit_manifest_sha256'],
        'security_delta_sha256': expected['security_delta_sha256'],
        'inner_attempt_name': retained.ATTEMPT, 'outer_receipt_name': OUTER_NAME,
        'phase_order': list(PHASES), 'stop_units': list(STOP_UNITS),
        'adapter_bounds': copy.deepcopy(ADAPTER_BOUNDS),
        'tls_change': copy.deepcopy(gate.delta['tls_change']),
        'production_acceptance': 'PENDING',
        'claim_successor': successor.validate_contract(expected['claim_successor'])}
    value['context_sha256'] = d.digest(value)
    return value


class OuterJournal(object):
    """One O_EXCL claim and exact CAS updates using an injected protected IO.

    io has journal_exists/read_journal/create_exclusive/replace_exact, with the
    BoundJournal metadata/bytes contract. No host backend for OUTER_NAME ships
    here. Receipt writes must require held lock and authenticated claim binding,
    but MUST NOT require successful runtime pins/ACTIVE/sandbox/TLS state.
    A changed target must not prevent recording its failure. Any uncertain IO
    poisons this object; no rewrite/retry/adoption follows.
    """
    def __init__(self, io, context, binding):
        need(io is not None, 'OUTER_PROTECTED_IO_REQUIRED')
        self.io, self.context, self.binding = io, copy.deepcopy(context), copy.deepcopy(binding)
        self.last = None
        self.poisoned = False

    def _raw(self, state):
        return packed({'schema': 1, 'name': OUTER_NAME, 'transaction_id': d.TX,
                       'context_sha256': self.context['context_sha256'],
                       'binding': self.binding, 'state': copy.deepcopy(state)})

    def _read(self):
        record = self.io.read_journal(OUTER_NAME)
        value = retained.BoundJournal._validate_record(record)
        need(len(record['data']) <= MAX_JOURNAL_BYTES, 'OUTER_READ_BOUND')
        need(type(value) is dict and set(value) == {'schema', 'name', 'transaction_id',
             'context_sha256', 'binding', 'state'} and type(value['schema']) is int and
             value['schema'] == 1 and value['name'] == OUTER_NAME and
             value['transaction_id'] == d.TX and
             value['context_sha256'] == self.context['context_sha256'] and
             d.same(value['binding'], self.binding), 'OUTER_RECORD_BINDING')
        return record

    def _confirm(self, raw):
        record = self._read()
        need(record['data'] == raw, 'OUTER_PUBLICATION_UNCONFIRMED')
        self.last = copy.deepcopy(record)

    def create(self, state):
        need(not self.poisoned and self.last is None, 'OUTER_NO_RESUME_OR_RESET')
        need(self.io.journal_exists(OUTER_NAME) is False, 'OUTER_ALREADY_CONSUMED')
        raw = self._raw(state)
        try:
            self.io.create_exclusive(OUTER_NAME, raw, 0, 0, 0o600)
            self._confirm(raw)
        except BaseException:
            self.poisoned = True
            raise

    def create_prechecked(self, state, prepared):
        need(successor.is_prepared_capability(prepared) and not self.poisoned and
             self.last is None, 'SUCCESSOR_OUTER_CAPABILITY_REQUIRED')
        need(self.io.journal_exists(OUTER_NAME) is False, 'EXISTING_OUTER_RECEIPT_HOLD')
        raw = self._raw(state)
        try:
            self.io.create_prechecked_outer(OUTER_NAME, raw, prepared)
            self._confirm(raw)
        except BaseException:
            self.poisoned = True
            prepared.fail()
            raise

    def save(self, state):
        need(not self.poisoned and self.last is not None, 'OUTER_UNCLAIMED_OR_POISONED')
        raw = self._raw(state)
        try:
            need(self._read() == self.last, 'OUTER_CAS_DRIFT')
            self.io.replace_exact(OUTER_NAME, copy.deepcopy(self.last), raw, 0, 0, 0o600)
            self._confirm(raw)
        except BaseException:
            self.poisoned = True
            raise


class CommandFailure(RuntimeError):
    def __init__(self, phase, evidence):
        super(CommandFailure, self).__init__('BOUNDED_COMMAND_FAILURE')
        need(phase in PHASES, 'COMMAND_PHASE')
        summary = diagnostics.public_summary(evidence)
        need(summary['epoch'] == 8 and summary['failed_stage'] ==
             COMMAND_PHASE[phase] + '_INTENT', 'COMMAND_EXACT_CONTEXT')
        interrupted = evidence.get('interruption_requires_propagation')
        need(type(interrupted) is bool, 'COMMAND_INTERRUPTION_FLAG')
        raw = json.dumps(evidence, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        need(len(raw) <= 3 * ADAPTER_BOUNDS['command_stream_limit_bytes'], 'COMMAND_PRIVATE_EVIDENCE_BOUND')
        self.phase, self.summary, self.private = phase, summary, evidence
        self.interrupted = interrupted
        self.interruption_class = None
        if interrupted:
            # Preserve the first identifiable interruption without copying any
            # arbitrary class name or text. The helper also records cleanup-only
            # interrupts when the main reason remains TIMEOUT or SUCCESS.
            labels = [evidence.get('failure_class')]
            cleanup = evidence.get('cleanup', {})
            if type(cleanup) is dict:
                labels.extend(cleanup.get(k) for k in ('signal_error_class', 'drain_error_class',
                    'stdout_close_error_class', 'stderr_close_error_class',
                    'selector_close_error_class', 'reap_error_class'))
            self.interruption_class = next((x for x in labels if x in
                ('KeyboardInterrupt', 'SystemExit')), 'UnknownInterrupt')

    @classmethod
    def unavailable(cls, phase, operation, sequence, error_type, stage):
        """Static adapter failure; no fabricated output, hash or private file."""
        value = cls.__new__(cls)
        RuntimeError.__init__(value, 'BOUNDED_COMMAND_FAILURE')
        value.phase = phase
        value.summary = {'schema': 1, 'failed_stage': COMMAND_PHASE[phase] + '_INTENT',
            'operation': operation, 'epoch': 8, 'sequence': sequence,
            'reason': stage, 'returncode': None, 'diagnostic_state': 'UNAVAILABLE',
            'adapter_error_type': error_type}
        value.private = None
        value.interruption_class = error_type if error_type in ('KeyboardInterrupt', 'SystemExit') else None
        value.interrupted = value.interruption_class is not None
        return value


class BoundedDiagnostics(object):
    """Capture ONLY an already-owned process. No command, environment or launcher.

    Existing capture helper supplies output/time/cleanup limits and safe PGID
    proof. Never calls communicate. Failure publication is deferred until outer
    containment. A trusted protected publisher must be explicitly supplied.
    """
    def __init__(self, publisher, capture=diagnostics.capture_owned_process):
        need(callable(publisher) and callable(capture), 'DIAGNOSTIC_ADAPTERS_REQUIRED')
        self.publisher, self.capture = publisher, capture
        self.sequence = 0
        self.scope = None
        self.scope_failure = None
        self.capture_allocation = None

    def start_scope(self, scope):
        need(self.capture_allocation is None, 'UNRECORDED_CAPTURE_FAILURE')
        self.scope, self.scope_failure = scope, None

    def record_adapter_failure(self, phase, operation, error_class, stage):
        """Return/latch SPAWN_UNCONFIRMED or CAPTURE_UNCONFIRMED, never raise it.

        Call before a handler's finally/rollback can replace the first failure.
        error_class is one fixed classification, never str/repr(error). A failed
        capture reuses its already allocated sequence; a spawn failure (or a
        capture refusal before allocation) consumes one fresh sequence. Repeated
        calls retain the first failure and cannot allocate or publish again.
        The caller still owns bounded emergency cleanup after an unexpected
        capture exception. This method neither signals nor publishes anything.
        """
        need(phase in PHASES and operation in diagnostics.OPERATIONS, 'ADAPTER_FAILURE_SCOPE')
        need(error_class in ('OSError', 'Exception', 'ContractError',
                             'KeyboardInterrupt', 'SystemExit'), 'ADAPTER_ERROR_CLASS')
        need(stage in ('SPAWN_UNCONFIRMED', 'CAPTURE_UNCONFIRMED'), 'ADAPTER_FAILURE_STAGE')
        if self.scope_failure is not None:
            self.capture_allocation = None
            return self.scope_failure
        allocation = self.capture_allocation
        if allocation is not None:
            need(stage == 'CAPTURE_UNCONFIRMED' and allocation ==
                 (phase, operation, self.sequence), 'ADAPTER_CAPTURE_ALLOCATION_BINDING')
            sequence = allocation[2]
        else:
            need(self.sequence < MAX_COMMANDS, 'COMMAND_SCOPE_OR_COUNT')
            self.sequence += 1
            sequence = self.sequence
        failure = CommandFailure.unavailable(phase, operation, sequence, error_class, stage)
        self.capture_allocation = None
        self.scope_failure = failure
        return failure

    def capture_owned(self, process, phase, operation, timeout_seconds,
                      cleanup_seconds=2.0, stream_limit=65536,
                      accepted_returncodes=(0,), return_output=False):
        need(phase in PHASES and self.sequence < MAX_COMMANDS, 'COMMAND_SCOPE_OR_COUNT')
        need(operation in diagnostics.OPERATIONS, 'COMMAND_FIXED_OPERATION')
        need(type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds) and
             0 < timeout_seconds <= diagnostics.MAX_TIMEOUT_SECONDS, 'COMMAND_TIMEOUT_BOUND')
        need(type(cleanup_seconds) in (int, float) and math.isfinite(cleanup_seconds) and
             0 < cleanup_seconds <= diagnostics.MAX_CLEANUP_SECONDS, 'COMMAND_CLEANUP_BOUND')
        need(type(stream_limit) is int and 0 < stream_limit <= ADAPTER_BOUNDS['command_stream_limit_bytes'],
             'COMMAND_OUTPUT_BOUND')
        need(type(accepted_returncodes) in (tuple, list) and 1 <= len(accepted_returncodes) <= 8 and
             all(type(code) is int and 0 <= code <= 255 for code in accepted_returncodes) and
             len(set(accepted_returncodes)) == len(accepted_returncodes), 'COMMAND_ACCEPTED_CODES')
        need(type(return_output) is bool, 'COMMAND_OUTPUT_OPTION')
        need(self.capture_allocation is None, 'UNRECORDED_CAPTURE_FAILURE')
        self.sequence += 1
        self.capture_allocation = (phase, operation, self.sequence)
        evidence = self.capture(process, COMMAND_PHASE[phase], operation, 8,
            self.sequence, timeout_seconds, cleanup_seconds, stream_limit)
        summary = diagnostics.public_summary(evidence)
        need(summary['failed_stage'] == COMMAND_PHASE[phase] + '_INTENT' and
             summary['operation'] == operation and summary['epoch'] == 8 and
             summary['sequence'] == self.sequence, 'COMMAND_CAPTURE_BINDING')
        interrupted = evidence.get('interruption_requires_propagation')
        need(type(interrupted) is bool, 'COMMAND_INTERRUPTION_FLAG')
        accepted = (not interrupted and type(evidence['returncode']) is int and
            evidence['returncode'] in accepted_returncodes and evidence['reason'] ==
            ('SUCCESS' if evidence['returncode'] == 0 else 'EXIT_NONZERO'))
        if not accepted:
            failure = CommandFailure(phase, evidence)
            if self.scope_failure is None:
                self.scope_failure = failure
            self.capture_allocation = None
            raise self.scope_failure
        output = {}
        for name in ('stdout', 'stderr'):
            item = evidence[name]
            need(type(item) is dict and item.get('eof_observed') is True and
                 item.get('truncated') is False and type(item.get('retained_bytes')) is int and
                 type(item.get('observed_bytes')) is int and
                 0 <= item['retained_bytes'] == item['observed_bytes'] <= stream_limit and
                 type(item.get('prefix_b64')) is str and
                 len(item['prefix_b64']) <= 4 * ((stream_limit + 2) // 3),
                 'COMMAND_ACCEPTED_OUTPUT_COMPLETENESS')
            try:
                raw = base64.b64decode(item['prefix_b64'].encode('ascii'), validate=True)
            except Exception:
                raise ContractError('COMMAND_OUTPUT_ENCODING') from None
            need(len(raw) == item['retained_bytes'] and sha(raw) == item.get('prefix_sha256'),
                 'COMMAND_OUTPUT_BYTES_OR_HASH')
            output[name] = raw
        # Private output is ONLY for the internal inventory/config validator;
        # callers must never put this CompletedProcess in a receipt or report.
        if return_output:
            self.capture_allocation = None
            return subprocess.CompletedProcess(args=None, returncode=evidence['returncode'],
                                               stdout=output['stdout'], stderr=output['stderr'])
        # Known, reviewed nonzero queries keep the actual EXIT_NONZERO summary.
        self.capture_allocation = None
        return summary


class InjectedDriver(object):
    """Explicit adapter composition. No defaults for lock, guards or host steps.

    controls: install_lock(), verify_outer_review(context), preflight(context),
      before_phase(context, phase), after_phase(context, phase, observation).
    Each check returns the strict OBSERVED envelope for its fixed operation.
    verify_outer_review must authenticate the exact context as well as the gate
    approval. This deliberately cannot be satisfied by the older review schema.
    Full phase guards must validate actual evolving pins and legal transitions;
    passing a hash or bool to this class is not a replacement for those adapters.
    containment.run(context, operation, unit, bounded_diagnostics): separate calls.
    handlers: exactly EXTERNAL_PHASES; callable(context, bounded_diagnostics).
    All adapters must enforce the explicit context adapter_bounds themselves.
    Synchronous Python callbacks cannot be forcibly timed out safely here; there
    is no claim that a hung/malicious adapter is preempted by this coordinator.
    """
    def __init__(self, gate, controls, journal_io, retained_io, handlers,
                 containment, bounded_diagnostics, payloads, identity_payloads):
        need(isinstance(gate, retained.RecoveryGate), 'REVIEWED_GATE_REQUIRED')
        need(type(handlers) is dict and set(handlers) == EXTERNAL_PHASES and
             all(callable(v) for v in handlers.values()), 'EXACT_PHASE_ADAPTER_SET')
        need(type(payloads) is dict and type(identity_payloads) is dict,
             'EXACT_PAYLOAD_MAPS_REQUIRED')
        need(set(identity_payloads) == {row['path'] for row in gate.additions},
             'EXACT_REVIEWED_IDENTITY_PAYLOADS')
        need(isinstance(bounded_diagnostics, BoundedDiagnostics), 'BOUNDED_DIAGNOSTICS_REQUIRED')
        self.gate, self.controls = gate, controls
        self.journal_io, self.retained_io = journal_io, retained_io
        self.handlers, self.containment = dict(handlers), containment
        self.diagnostics = bounded_diagnostics
        self.payloads, self.identity_payloads = copy.deepcopy(payloads), copy.deepcopy(identity_payloads)
        self.context = context_from_gate(gate)
        self.inner = retained.BoundJournal(retained.ATTEMPT, gate, retained_io)
        self.target_step = retained.RetainedTargetDelta(gate, self.inner, retained_io)
        self.generation_step = retained.GenerationAccessStep(gate, self.inner, retained_io)
        self.started = False

    def check_binding(self):
        need(d.same(context_from_gate(self.gate), self.context), 'SEQUENCE_CONTEXT_MUTATED')

    def phase(self, name):
        self.check_binding()
        if name == 'replace_retained_targets':
            self.target_step.apply(copy.deepcopy(self.payloads))
            digest = sha(self.target_step.journal.last['data'])
        elif name == 'change_generation_access':
            self.generation_step.apply()
            digest = sha(self.generation_step.journal.last['data'])
        elif name == 'publish_reviewed_identities':
            receipts = []
            for row in self.gate.additions:
                step = retained.IdentityPublication(self.gate, self.inner,
                                                     self.retained_io, row['path'])
                step.apply(self.identity_payloads[row['path']])
                receipts.append({'path': row['path'], 'receipt_sha256': sha(step.journal.last['data'])})
            # An empty, explicitly reviewed additions list is a verified no-op,
            # never inference that production peer identity configuration exists.
            digest = d.digest(receipts)
        else:
            need(name in EXTERNAL_PHASES, 'FIXED_PHASE_ONLY')
            result = self.handlers[name](copy.deepcopy(self.context), self.diagnostics)
            if name == 'rebind_tls_metadata_only':
                need(type(result) is dict and set(result) == {'observation', 'tls_change'},
                     'TLS_METADATA_RESULT_SCHEMA')
                need(d.same(result['tls_change'], self.context['tls_change']),
                     'TLS_RETENTION_OR_ZERO_CALL_CONTRACT')
                result = result['observation']
            return result
        return observation(self.context, name, digest)


class RecoveryHold(RuntimeError):
    def __init__(self, state):
        super(RecoveryHold, self).__init__('EPOCH7_RECOVERY_HOLD_NO_RETRY')
        self.state = copy.deepcopy(state)


class RecoveryInterrupted(KeyboardInterrupt):
    def __init__(self, state):
        super(RecoveryInterrupted, self).__init__('EPOCH7_RECOVERY_INTERRUPTED_HOLD')
        self.state = copy.deepcopy(state)


class RecoveryExited(SystemExit):
    def __init__(self, state):
        super(RecoveryExited, self).__init__(1)
        self.state = copy.deepcopy(state)


def _interrupt(error):
    if isinstance(error, SystemExit): return 'SystemExit'
    if isinstance(error, KeyboardInterrupt): return 'KeyboardInterrupt'
    if isinstance(error, CommandFailure): return error.interruption_class
    return None


def _failure(state, phase, operation, error):
    # Called only for the FIRST failure. Secondary failures never replace it.
    failed_stage = state['stage']
    state.update(stage='HOLD', failed_phase=phase, failed_stage=failed_stage,
                 failed_operation=operation, error_type=error_class(error),
                 recovery='MANUAL_RECONCILIATION_REQUIRED_NO_RESTART')
    if isinstance(error, CommandFailure) and error.phase == phase:
        state['failed_operation'] = error.summary['operation']
        state['command_failure'] = copy.deepcopy(error.summary)
    state['interruption'] = _interrupt(error)
    # Preserve only the fixed same-census classification. Raw exception text,
    # process records, DB paths and command output never enter this envelope.
    try:
        race = getattr(error, 'epoch7_census_race', None)
        combinations = {
            ('PID_LIST_CHANGED', 'CHANGED', 'UNCHANGED'),
            ('DB_MAP_CHANGED', 'UNCHANGED', 'CHANGED'),
            ('BOTH_CHANGED', 'CHANGED', 'CHANGED'),
            ('UNKNOWN', 'CHANGED', 'UNKNOWN'),
            ('UNKNOWN', 'UNCHANGED', 'UNKNOWN')}
        if type(race) is dict and set(race) == {'classification', 'pid_list', 'db_map'} and (
                race['classification'], race['pid_list'], race['db_map']) in combinations:
            state['census_race'] = dict(race)
        elif race is not None:
            state['census_race'] = {'classification': 'UNKNOWN', 'pid_list': 'UNKNOWN', 'db_map': 'UNKNOWN'}
    except BaseException:
        state['census_race'] = {'classification': 'UNKNOWN', 'pid_list': 'UNKNOWN', 'db_map': 'UNKNOWN'}


def _secondary(state, location, error):
    state['secondary_errors'].append({'operation': location, 'error_type': error_class(error)})
    interrupt = _interrupt(error)
    if interrupt is not None and state['interruption'] is None:
        state['interruption'] = interrupt


def _latch_pending_capture(bounded, error):
    """Last-resort classification if an adapter forgot to record its exception.

    This cannot clean up its owned subprocess; the finite command adapter must
    do that. It does prevent an unrecorded allocation from blocking subsequent
    independent containment scopes or being overwritten by a handler finally.
    """
    if bounded.capture_allocation is not None:
        phase, operation, unused_sequence = bounded.capture_allocation
        bounded.record_adapter_failure(phase, operation, error_class(error), 'CAPTURE_UNCONFIRMED')


def _cleanup(driver, state):
    """Every unit/group is attempted, including after BaseException or UNKNOWN."""
    command_failures = []
    for operation, unit in CLEANUP:
        label = operation if unit is None else operation + ':' + unit
        driver.diagnostics.start_scope('cleanup:' + label)
        try:
            result = driver.containment.run(copy.deepcopy(driver.context), operation, unit, driver.diagnostics)
            if driver.diagnostics.scope_failure is not None:
                raise driver.diagnostics.scope_failure
            evidence = check_observation(result, driver.context, label, require_observed=False)
            row = {'operation': operation, 'unit': unit, 'status': evidence['status'],
                   'evidence_sha256': evidence['evidence_sha256']}
        except BaseException as error:
            _latch_pending_capture(driver.diagnostics, error)
            latched = driver.diagnostics.scope_failure
            later_error = None
            if latched is not None and error is not latched:
                later_error, error = error, latched
            row = {'operation': operation, 'unit': unit, 'status': 'UNKNOWN',
                   'error_type': error_class(error)}
            if isinstance(error, CommandFailure):
                row['command_failure'] = copy.deepcopy(error.summary)
                command_failures.append((row, error))
            _secondary(state, label, error)
            if later_error is not None:
                _secondary(state, label + ':subsequent_error', later_error)
        state['containment'].append(row)
    state['containment_status'] = ('OBSERVED' if all(
        row['status'] == 'OBSERVED' for row in state['containment']) else 'UNKNOWN')
    return command_failures


def _publish_command_failure(driver, state, destination, primary):
    if not isinstance(primary, CommandFailure) or primary.private is None: return
    try:
        reference = driver.diagnostics.publisher(primary.private)
        destination['command_failure'] = diagnostics.public_summary(primary.private, reference)
    except BaseException as error:
        # The primary operation/stage stays intact, even if fsync or its publisher
        # was interrupted. No second diagnostic publication attempt is allowed.
        _secondary(state, 'persist_private_diagnostic', error)


def _raise(state):
    if state['interruption'] == 'SystemExit': raise RecoveryExited(state) from None
    if state['interruption'] is not None: raise RecoveryInterrupted(state) from None
    raise RecoveryHold(state) from None


def successor_resume_once(driver, contract):
    """Return pending-independent-acceptance only after every durable phase.

    No callbacks can run a second time through this driver. Re-instantiation is
    also refused by either existing O_EXCL record, including partial records.
    Before admission, refusals invoke no cleanup effects. After both claims,
    every failure independently contains before any diagnostic/final publication.
    """
    need(isinstance(driver, InjectedDriver), 'INJECTED_DRIVER_REQUIRED')
    contract = successor.validate_contract(contract)
    need(contract == driver.context['claim_successor'], 'SUCCESSOR_DRIVER_CONTRACT')
    need(not driver.started, 'SEQUENCE_OBJECT_ALREADY_USED')
    driver.started = True
    state = {'schema': 1, 'stage': 'ADMISSION_PENDING', 'completed': [],
        'phase_evidence': {}, 'containment': [], 'containment_status': 'NOT_ATTEMPTED',
        'secondary_errors': [], 'automatic_retry': False, 'legacy_restart': False,
        'historical_notification_replay': False, 'prerequisite_replay': False,
        'coordinator_tls_calls': {'issue': 0, 'renew': 0, 'dry_run': 0},
        'tls_policy': 'RETAIN_NO_ISSUE_RENEW_DRY_RUN',
        'production_acceptance': 'PENDING', 'admission': 'NOT_GRANTED',
        'receipt_status': 'NOT_CREATED', 'interruption': None}
    phase, operation = 'admission', 'verify_outer_review'
    journal = None
    lock = None
    lock_entered = False
    primary = None
    cleanup_commands = []
    fully_admitted = False
    prepared = None
    try:
        driver.check_binding()
        check_observation(driver.controls.verify_outer_review(copy.deepcopy(driver.context)),
                          driver.context, 'verify_outer_review')
        operation = 'acquire_install_lock'
        lock = driver.controls.install_lock()
        lock.__enter__()
        lock_entered = True
        operation = 'verify_outer_review'
        check_observation(driver.controls.verify_outer_review(copy.deepcopy(driver.context)),
                          driver.context, 'verify_outer_review')
        operation = 'prepare_successor'
        prepared, state['prepare_evidence'] = successor.prepare_successor(driver, contract)
        journal = OuterJournal(driver.journal_io, driver.context, driver.gate.journal_binding())
        operation = 'commit_successor_claims'
        state.update(stage='CLAIM_INTENT', admission='UNKNOWN', receipt_status='UNKNOWN')
        successor.commit_successor(driver, prepared, journal, state)
        state['successor_publication'] = prepared.publication_status()
        fully_admitted = True
        state.update(stage='ADMITTED', admission='ADMITTED', receipt_status='OBSERVED')
        operation = 'save_admission'
        journal.save(state)
        for phase in PHASES:
            driver.diagnostics.start_scope('phase:' + phase)
            operation = 'save_phase_intent'
            state['stage'] = phase + '_INTENT'
            journal.save(state)
            operation = 'verify_phase_before'
            driver.check_binding()
            check_observation(driver.controls.before_phase(copy.deepcopy(driver.context), phase),
                              driver.context, 'before:' + phase)
            operation = phase
            result = driver.phase(phase)
            if driver.diagnostics.scope_failure is not None:
                raise driver.diagnostics.scope_failure
            evidence = check_observation(result, driver.context, phase, require_observed=False)
            state['phase_evidence'][phase] = evidence
            need(evidence['status'] == 'OBSERVED', 'PHASE_RESULT_UNKNOWN')
            operation = 'verify_phase_after'
            check_observation(driver.controls.after_phase(copy.deepcopy(driver.context), phase,
                                                         copy.deepcopy(evidence)),
                              driver.context, 'after:' + phase)
            driver.check_binding()
            state['completed'].append(phase)
            state['stage'] = phase + '_COMPLETE'
            operation = 'save_phase_complete'
            journal.save(state)
        phase, operation = 'completion', 'save_completion'
        state['stage'] = 'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE'
        journal.save(state)
    except BaseException as error:
        state['successor_publication'] = (prepared.publication_status() if prepared is not None else
            {'outer': 'NOT_ATTEMPTED', 'inner': 'NOT_ATTEMPTED',
             'automatic_completion': False, 'capability_state': 'NOT_PREPARED'})
        _latch_pending_capture(driver.diagnostics, error)
        later_error = None
        if driver.diagnostics.scope == 'phase:' + phase and driver.diagnostics.scope_failure is not None:
            latched = driver.diagnostics.scope_failure
            if error is not latched:
                later_error, error = error, latched
        primary = error
        _failure(state, phase, operation, error)
        if later_error is not None:
            _secondary(state, 'subsequent_phase_error', later_error)
        if journal is not None and journal.poisoned:
            state['receipt_status'] = 'UNKNOWN'
        if fully_admitted:
            cleanup_commands = _cleanup(driver, state)
        _publish_command_failure(driver, state, state, error)
        for destination, failure in cleanup_commands:
            _publish_command_failure(driver, state, destination, failure)
        if journal is not None and journal.last is not None and not journal.poisoned:
            try:
                state['receipt_status'] = 'OBSERVED'
                journal.save(state)
            except BaseException as receipt_error:
                state['receipt_status'] = 'UNKNOWN'
                _secondary(state, 'save_hold_receipt', receipt_error)
    finally:
        if lock_entered:
            try:
                # The lock adapter must not suppress body failure or launch any
                # effect at exit. Exit sees no raw exception/credentials.
                lock.__exit__(None, None, None)
            except BaseException as error:
                if primary is None:
                    primary = error
                    _failure(state, 'lock_release', 'release_install_lock', error)
                    # Held-lock authority is no longer provable: never reacquire
                    # or call runtime effects blindly after an uncertain exit.
                    state['containment_status'] = 'UNKNOWN'
                    state['receipt_status'] = 'UNKNOWN'
                else:
                    _secondary(state, 'release_install_lock', error)
                    state['receipt_status'] = 'UNKNOWN'
    if primary is not None:
        _raise(state)
    return copy.deepcopy(state)


def resume_once(driver):
    raise ContractError('EXPLICIT_SUCCESSOR_ENTRY_REQUIRED')
