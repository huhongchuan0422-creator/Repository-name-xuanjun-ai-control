"""Exact claim-only predecessor contract. No host access or approval creation.

The historical record is immutable. All live observations and new exclusive
claims are supplied by the separately authenticated successor host path.
"""
import copy
import datetime
import hashlib
import json
import math
import os
import re
import time
import threading
import weakref

OLD_OUTER = 'epoch7-recovery-sequence.json'
OLD_INNER = 'epoch7-recovery-execution.json'
NEW_OUTER = 'epoch7-recovery-sequence-successor-a5602f7e70e22edba.json'
NEW_INNER = 'epoch7-recovery-execution-successor-a5602f7e70e22edba.json'
TX = 'c529c379-9341-4510-8384-fc6be1e412e5'
TRANSACTION = ('/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/'
               'legacy-isolation-' + TX)
PREDECESSOR_SHA256 = 'a5602f7e70e22edbab683518f21ae8b851369fb61008e7683af1451f4b357055'
PREDECESSOR_SIZE = 1641
PREDECESSOR_STATE_SHA256 = 'bbe789b615ee9237626263ea8cfc0c7d39b79c8feb0f62d303e9d16238c6bff7'
PREDECESSOR_BINDING_SHA256 = '73ca008c00b9cf2b80a5b368ceebf6b3d5bf9c7278566d925355b3c12fc1e2ba'
OLD_REVIEW_ID = 6212022929
OLD_REVIEW_SHA256 = '88023d5e6d4d93d5f263892f900caf6ced21d1f4f038d01419e4ee854aa94a48'
OLD_PLAN_SHA256 = 'eae1e341408b821af0902a225021394d6f2e91a6c557bafe3dcd67a29c3b08da'
OLD_SEED_SHA256 = '6de7d12246826388949723e9238cd464686e6e86847187946837df927c97a550'
OLD_BODY_SHA256 = 'bc0ab80b60c3c662b7960f68b1ce7fc57e62ee39ecb819a3b8ece239d1dba6f1'
SHA = re.compile(r'^[0-9a-f]{64}$')
COMMIT = re.compile(r'^[0-9a-f]{40}$')
TOKEN_SECONDS = 30
TIMING_POLICY = 'PREPARED_START_30S_ORDERED_GUARDS_PUBLICATION_MIN_V1'


def need(value, code):
    if not value:
        raise ValueError('CLAIM_SUCCESSOR_' + code)


def canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    need(len(raw) <= 262144, 'CONTRACT_BOUND')
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def predecessor_contract():
    return {'schema': 1, 'transaction_id': TX, 'outer_name': OLD_OUTER,
        'inner_name': OLD_INNER, 'raw_sha256': PREDECESSOR_SHA256,
        'raw_size': PREDECESSOR_SIZE, 'binding_sha256': PREDECESSOR_BINDING_SHA256,
        'state_sha256': PREDECESSOR_STATE_SHA256, 'review_id': OLD_REVIEW_ID,
        'review_sha256': OLD_REVIEW_SHA256, 'plan_sha256': OLD_PLAN_SHA256,
        'seed_sha256': OLD_SEED_SHA256, 'body_sha256': OLD_BODY_SHA256,
        'successor_outer_name': NEW_OUTER, 'successor_inner_name': NEW_INNER,
        'parent_mutable_fields': ['ctime_ns', 'mtime_ns', 'size']}


def validate_predecessor_contract(value):
    need(type(value) is dict and canonical(value) == canonical(predecessor_contract()),
         'EXACT_PREDECESSOR_CONTRACT')
    return copy.deepcopy(value)


def parse_expiry(value):
    need(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', value),
         'EXPIRY_GRAMMAR')
    try:
        parsed = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
        epoch = (parsed - datetime.datetime(1970, 1, 1)).total_seconds()
    except (ValueError, OverflowError):
        raise ValueError('CLAIM_SUCCESSOR_EXPIRY_VALUE')
    need(epoch > 0 and parsed.strftime('%Y-%m-%dT%H:%M:%SZ') == value, 'EXPIRY_VALUE')
    return epoch


def validate_contract(value):
    need(type(value) is dict and set(value) == {'schema', 'kind', 'predecessor',
        'implementation', 'admission_expires_at_utc', 'authorized_successors', 'automatic_retry',
        'effect_scope', 'measured_predecessor_sha256', 'timing_policy'}, 'CONTRACT_FIELDS')
    need(type(value['schema']) is int and value['schema'] == 1 and
        value['kind'] == 'EXACT_CLAIM_ONLY_SUCCESSOR' and value['timing_policy'] == TIMING_POLICY and
        type(value['authorized_successors']) is int and value['authorized_successors'] == 1 and
        value['automatic_retry'] is False and value['effect_scope'] == 'UNCHANGED_107_PAYLOADS_16_PHASES',
        'CONTRACT_POLICY')
    validate_predecessor_contract(value['predecessor'])
    implementation = value['implementation']
    need(type(implementation) is dict and set(implementation) ==
        {'source_commit', 'source_tree', 'kit_manifest_sha256'}, 'IMPLEMENTATION_FIELDS')
    for key in ('source_commit', 'source_tree'):
        need(type(implementation[key]) is str and COMMIT.fullmatch(implementation[key]), 'IMPLEMENTATION_UNBOUND')
    for raw in (implementation['kit_manifest_sha256'], value['measured_predecessor_sha256']):
        need(type(raw) is str and SHA.fullmatch(raw), 'IMPLEMENTATION_UNBOUND')
    parse_expiry(value['admission_expires_at_utc'])
    return copy.deepcopy(value)


def predecessor_resource_identity(contract):
    validate_contract(contract)
    return {'path': TRANSACTION + '/' + OLD_OUTER, 'uid': 0, 'gid': 0,
        'mode': 0o600, 'sha256': PREDECESSOR_SHA256, 'size': PREDECESSOR_SIZE}


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'JSON_DUPLICATE')
            value[key] = item
        return value
    def bad(unused):
        raise ValueError('CLAIM_SUCCESSOR_JSON_NONFINITE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad)


def validate_predecessor_record(raw, metadata):
    """Validate measured bytes/metadata, never synthesize authority or stamps."""
    need(type(raw) is bytes and len(raw) == PREDECESSOR_SIZE and
         hashlib.sha256(raw).hexdigest() == PREDECESSOR_SHA256, 'PREDECESSOR_BYTES')
    need(type(metadata) is dict, 'PREDECESSOR_METADATA')
    required = {'uid', 'gid', 'mode', 'dev', 'ino', 'nlink', 'size', 'mtime_ns', 'ctime_ns'}
    need(set(metadata) == required | {'kind', 'sha256'}, 'PREDECESSOR_METADATA')
    for key in required:
        need(type(metadata[key]) is int and metadata[key] >= (1 if key in ('ino', 'nlink') else 0),
             'PREDECESSOR_METADATA_INTEGER')
    need((metadata['uid'], metadata['gid'], metadata['mode'], metadata['nlink'], metadata['size']) ==
         (0, 0, 0o600, 1, PREDECESSOR_SIZE), 'PREDECESSOR_AUTHORITY')
    if 'kind' in metadata: need(metadata['kind'] == 'FILE', 'PREDECESSOR_TYPE')
    if 'sha256' in metadata: need(metadata['sha256'] == PREDECESSOR_SHA256, 'PREDECESSOR_METADATA_HASH')
    for key in ('access_acl', 'default_acl', 'capability'):
        if key in metadata:
            need(metadata[key] in (None, '', 'user::rw-\ngroup::---\nother::---\n') if key == 'access_acl'
                 else metadata[key] in (None, ''), 'PREDECESSOR_EXTENDED_AUTHORITY')
    value = _json(raw)
    need(type(value) is dict and set(value) == {'schema', 'name', 'transaction_id',
         'context_sha256', 'binding', 'state'} and canonical(value) + b'\n' == raw,
         'PREDECESSOR_ENVELOPE')
    need(type(value['schema']) is int and value['schema'] == 1 and value['name'] == OLD_OUTER and
         value['transaction_id'] == TX and type(value['context_sha256']) is str and
         SHA.fullmatch(value['context_sha256']), 'PREDECESSOR_IDENTITY')
    need(digest(value['binding']) == PREDECESSOR_BINDING_SHA256 and
         hashlib.sha256(canonical(value['state']) + b'\n').hexdigest() == PREDECESSOR_STATE_SHA256,
         'PREDECESSOR_BINDING_STATE')
    state = value['state']
    fixed = {'stage': 'HOLD', 'failed_stage': 'CLAIM_INTENT', 'failed_phase': 'admission',
        'failed_operation': 'create_inner_attempt', 'admission': 'UNKNOWN',
        'receipt_status': 'OBSERVED', 'completed': [], 'phase_evidence': {},
        'containment': [], 'containment_status': 'NOT_ATTEMPTED', 'secondary_errors': [],
        'interruption': None, 'automatic_retry': False, 'legacy_restart': False,
        'historical_notification_replay': False, 'prerequisite_replay': False}
    need(all(key in state and canonical(state[key]) == canonical(item) for key,item in fixed.items()),
         'PREDECESSOR_NO_PHASE_HOLD')
    need(value['binding'].get('review_id') == OLD_REVIEW_ID and
         value['binding'].get('approval_body_sha256') == OLD_REVIEW_SHA256,
         'PREDECESSOR_OLD_REVIEW')
    return {'schema': 1, 'raw_sha256': PREDECESSOR_SHA256, 'raw_size': PREDECESSOR_SIZE,
        'binding_sha256': PREDECESSOR_BINDING_SHA256, 'state_sha256': PREDECESSOR_STATE_SHA256,
        'context_sha256': value['context_sha256'], 'metadata': copy.deepcopy(metadata)}


_MINT = object()
_ISSUED = weakref.WeakSet()
_PROGRESS = weakref.WeakKeyDictionary()
_LIFECYCLE = weakref.WeakKeyDictionary()
_DRIVERS = weakref.WeakKeyDictionary()
_REGISTRY_LOCK = threading.RLock()
_GUARD_CHECKS = ('install_lock_held', 'read_preserved_pins', 'read_activation_evidence',
    'read_generation', 'read_sandbox', 'read_targets', 'read_additive_absence',
    'read_additive_target', 'read_writer_exclusion')
_CHECK_ORDER = ('START_PREDECESSOR', 'START_BINDING', 'START_APPROVAL',
                'PREFLIGHT', 'FINAL_PREDECESSOR', 'INNER_GATE', 'FINAL_BINDING')
_TIMING_STAGES = ('prepare_start', 'prepare_preflight_start', 'prepare_preflight_complete',
    'prepare_inner_start', 'prepare_inner_complete', 'prepared_minted', 'commit_consumed',
    'commit_start_checks_complete', 'commit_preflight_start', 'commit_preflight_complete',
    'commit_predecessor_complete', 'commit_inner_start', 'commit_inner_complete',
    'commit_binding_complete', 'publication_minted', 'outer_begin', 'outer_confirmed',
    'inner_begin', 'inner_confirmed', 'complete', 'failed')
_TIME_FAILURES = frozenset(('PREPARED_START_EXPIRED', 'PREFLIGHT_GUARD_EXPIRED',
    'INNER_GUARD_EXPIRED', 'PUBLICATION_EXPIRED', 'APPROVAL_EXPIRED',
    'APPROVAL_MONOTONIC_EXPIRED', 'CLOCK_ROLLBACK', 'CLOCK_UNKNOWN'))


def _new_timing():
    return {'schema': 1, 'timing_policy': TIMING_POLICY, 'stages': [],
        'prepared_start_deadline': None, 'approval_monotonic_ceiling': None,
        'preflight_deadline': None, 'inner_deadline': None, 'publication_deadline': None,
        'failure_predicate': None}


def timing_status(driver):
    """Bounded public projection: no paths, bodies, evidence or authority data."""
    record = _DRIVERS.get(driver)
    return copy.deepcopy(record['timing'] if record is not None else _new_timing())


def _failure(record, error):
    timing = record['timing']
    if timing['failure_predicate'] is None:
        # Never serialize arbitrary exception text, type names, or private data.
        code = error.args[0] if type(error) is ValueError and error.args and type(error.args[0]) is str else None
        codes = {'CLAIM_SUCCESSOR_' + name: name for name in _TIME_FAILURES}
        timing['failure_predicate'] = codes.get(code, 'INTERRUPTION' if
            isinstance(error, (KeyboardInterrupt, SystemExit)) else 'CHECK_FAILED')


def _clock():
    mono, wall = time.monotonic(), time.time()
    need(type(mono) in (int, float) and type(wall) in (int, float) and
         math.isfinite(mono) and math.isfinite(wall) and mono >= 0 and wall > 0,
         'CLOCK_UNKNOWN')
    return mono, wall


def _sample(record, deadline=None, predicate=None, stage=None):
    try:
        mono, wall = _clock()
        # Revalidate injected clocks too. Public telemetry contains finite values only.
        need(type(mono) in (int, float) and type(wall) in (int, float) and
             math.isfinite(mono) and math.isfinite(wall) and mono >= 0 and wall > 0,
             'CLOCK_UNKNOWN')
        if deadline is not None:
            need(type(deadline) in (int, float) and math.isfinite(deadline), 'CLOCK_UNKNOWN')
        if stage is not None:
            need(stage in _TIMING_STAGES and all(row['stage'] != stage for row in record['timing']['stages']),
                 'TIMING_STAGE_ORDER')
            record['timing']['stages'].append({'stage': stage, 'monotonic': mono,
                'wall_utc': wall, 'deadline_monotonic': deadline})
        # Deadline failure takes precedence when rollback and expiry coincide.
        if deadline is not None:
            need(type(deadline) in (int, float) and math.isfinite(deadline), 'CLOCK_UNKNOWN')
            need(mono < deadline, predicate)
        need(wall < record['wall_expiry'], 'APPROVAL_EXPIRED')
        ceiling = record.get('approval_ceiling')
        if ceiling is not None:
            need(mono < ceiling, 'APPROVAL_MONOTONIC_EXPIRED')
        previous = record.get('last_clock')
        need(previous is None or mono >= previous[0] and wall >= previous[1], 'CLOCK_ROLLBACK')
        record['last_clock'] = (mono, wall)
        return mono, wall
    except BaseException as error:
        _failure(record, error)
        raise


def _guard_deadline(driver):
    deadline = driver.controls.observer.guard_deadline
    need(type(deadline) in (int, float) and math.isfinite(deadline),
         'ORIGINAL_GUARD_DEADLINE_REQUIRED')
    return deadline


def _run_guard(driver, action, kind):
    """Observe the original guard's creation, without choosing a new budget.

    This temporary instance-only wrapper forwards the real call and exact return
    value. It cannot mint authority; only a returned full check plus the private
    once-only guard observation can advance the caller's transcript.
    """
    controls = driver.controls
    original = controls._begin_guard
    need(callable(original), 'ORIGINAL_GUARD_REQUIRED')
    had_instance = '_begin_guard' in vars(controls)
    instance_value = vars(controls).get('_begin_guard')
    owner_thread = threading.get_ident()
    captured = []
    calls = [0]
    broken = [False]
    def observe(*args, **kwargs):
        calls[0] += 1
        try:
            need(threading.get_ident() == owner_thread and calls[0] == 1,
                 'ORIGINAL_GUARD_SINGLE_CALL')
            deadline = original(*args, **kwargs)
            need(type(deadline) in (int, float) and math.isfinite(deadline),
                 'ORIGINAL_GUARD_DEADLINE_REQUIRED')
            need(deadline == _guard_deadline(driver), 'CAPABILITY_GUARD_DEADLINE_MUTATED')
            _sample(_DRIVERS[driver], deadline, kind.upper() + '_GUARD_EXPIRED')
            captured.append(deadline)
            return deadline
        except BaseException:
            broken[0] = True
            raise
    primary = None
    try:
        controls._begin_guard = observe
        result = action()
        need(threading.get_ident() == owner_thread and calls[0] == 1 and
             len(captured) == 1 and not broken[0], 'ORIGINAL_GUARD_SINGLE_CALL')
        need(captured[0] == _guard_deadline(driver), 'CAPABILITY_GUARD_DEADLINE_MUTATED')
        return result, captured[0]
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            unchanged = getattr(controls, '_begin_guard', None) is observe
            if had_instance:
                controls._begin_guard = instance_value
            else:
                del controls._begin_guard
            need(unchanged and _method_identity(controls._begin_guard) == _method_identity(original),
                 'ORIGINAL_GUARD_WRAPPER_MUTATED')
        except BaseException:
            # Any restoration failure is fatal, but never replace a first guard
            # failure or interruption with an incidental restoration exception.
            if primary is None:
                raise


def _method_identity(method):
    return (getattr(method, '__self__', None), getattr(method, '__func__', method))


def _check_identities(driver):
    try:
        methods = (driver.check_binding, driver.controls.preflight, driver.controls._begin_guard, driver.gate.check,
                   driver.gate.verifier.verify_exact, driver.journal_io.read_predecessor_proof)
        methods += tuple(getattr(driver.gate.guards, name) for name in _GUARD_CHECKS)
        need(all(callable(method) for method in methods), 'CAPABILITY_CHECK_IDENTITY')
        return tuple(_method_identity(method) for method in methods)
    except (AttributeError, TypeError):
        raise ValueError('CLAIM_SUCCESSOR_CAPABILITY_CHECK_IDENTITY')


def _same_identities(left, right):
    return len(left) == len(right) and all(actual is expected for actual, expected in zip(left, right))


def _progress(value):
    return (value.stage, value.outer_attempted, value.inner_attempted,
            value.outer_confirmed, value.inner_confirmed,
            value.outer_io_used, value.io_used,
            value.outer_raw, value.inner_raw)


def _progress_matches(value):
    recorded = _PROGRESS.get(value)
    current = _progress(value)
    return (recorded is not None and recorded[:7] == current[:7] and
            recorded[7] is current[7] and recorded[8] is current[8])


def _require_progress(value):
    need(is_prepared_capability(value) and _progress_matches(value),
         'CAPABILITY_TRANSITION_ATTESTATION')


def is_completed_capability(value):
    return (is_prepared_capability(value) and _progress_matches(value) and
            _LIFECYCLE[value]['completed'] is True and not _LIFECYCLE[value]['failed'] and
            value.stage == 'COMPLETE' and all(flag is True for flag in _progress(value)[1:7]) and
            type(value.outer_raw) is bytes and type(value.inner_raw) is bytes)


def is_admitted_capability(value):
    """No clock check: durable completed admission retains cleanup authority."""
    return (is_completed_capability(value) and
            value.driver.gate.verifier.admitted_capability is value)


def is_prepared_capability(value):
    return (type(value) is PreparedSuccessor and value in _ISSUED and
            value in _LIFECYCLE and value._mint is _MINT and
            value.owner_pid == _LIFECYCLE[value]['owner_pid'] == os.getpid())


def _burn_on_error(method):
    def checked(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except BaseException as error:
            # Rejected replay cannot revoke an already sealed cleanup authority.
            record = _LIFECYCLE.get(self)
            if record is not None and not (record['completed'] and
                    getattr(self.driver.gate.verifier, 'admitted_capability', None) is self):
                self.fail(error)
            raise
    return checked


def _record_check(value, proof, name, result):
    """Only commit_successor owns this invocation's never-returned proof object."""
    record = _LIFECYCLE[value]
    _require_progress(value)
    need(not record['failed'] and proof is record['proof'] and
         record['thread'] == threading.get_ident() and
         record['checks'] == _CHECK_ORDER[:len(record['checks'])] and
         len(record['checks']) < len(_CHECK_ORDER) and
         name == _CHECK_ORDER[len(record['checks'])] and
         _check_identities(value.driver) == record['check_identities'], 'COMMIT_CHECK_PROOF')
    # The private immutable transcript binds exact input/check/result identities.
    record['results'] += ((name, digest(result)),)
    record['checks'] += (name,)


class PreparedSuccessor(object):
    """One start handle; publication is a separate private one-use transition."""
    def __init__(self, mint, driver, contract, predecessor, prepare_proof=None):
        need(mint is _MINT, 'CAPABILITY_CONSTRUCTOR')
        driver_record = _DRIVERS.get(driver)
        need(driver_record is not None and driver_record.get('prepared') is False and
             prepare_proof is driver_record.get('prepare_proof'), 'CAPABILITY_PREPARE_PROOF')
        self._mint = mint
        self.owner_pid = os.getpid()
        self.driver = driver
        self.outer_io, self.inner_io = driver.journal_io, driver.retained_io
        self.inner = driver.inner
        self.lock = driver.controls.install_lock()
        self.contract = validate_contract(contract)
        self.contract_sha = digest(self.contract)
        self.context_sha = digest(driver.context)
        self.review_id = driver.gate.review_id
        self.review_body_sha = driver.gate.verifier.body_sha
        self.predecessor = copy.deepcopy(predecessor)
        self.predecessor_sha = digest(predecessor)
        mono, wall = _sample(driver_record)
        self.wall_expiry = parse_expiry(contract['admission_expires_at_utc'])
        self.approval_mono_expiry = mono + (self.wall_expiry - wall)
        self.expires = min(mono + TOKEN_SECONDS, self.approval_mono_expiry)
        self.mint_window = (mono, wall, self.expires)
        self.mint_window_sha = digest(self.mint_window)
        self.commit_guard = None
        self.commit_guard_sha = digest(None)
        self.stage = 'PREPARED'
        self.inner_raw = None
        self.outer_raw = None
        self.outer_io_used = False
        self.io_used = False
        self.outer_attempted = False
        self.inner_attempted = False
        self.outer_confirmed = False
        self.inner_confirmed = False
        driver_record['prepared'] = True
        driver_record['approval_ceiling'] = self.approval_mono_expiry
        driver_record['timing']['prepared_start_deadline'] = self.expires
        driver_record['timing']['approval_monotonic_ceiling'] = self.approval_mono_expiry
        _LIFECYCLE[self] = dict(driver_record=driver_record, owner_pid=self.owner_pid,
            identities=(driver, self.outer_io, self.inner_io, self.inner, self.lock,
                        driver.controls, driver.controls.observer, driver.gate, driver.gate.verifier, driver.gate.guards),
            check_identities=_check_identities(driver), contract_sha=self.contract_sha,
            context_sha=self.context_sha, review_id=self.review_id, review_body_sha=self.review_body_sha,
            predecessor_sha=self.predecessor_sha, mint_window=self.mint_window,
            wall_expiry=self.wall_expiry, approval_ceiling=self.approval_mono_expiry,
            deadline=self.expires, predicate='PREPARED_START_EXPIRED', guard=None,
            publication_deadline=None, publication_mint=None, mint_attempted=False,
            checks=(), results=(), proof=None, thread=None, failed=False, completed=False)
        _ISSUED.add(self)
        _PROGRESS[self] = _progress(self)
        _sample(driver_record, self.expires, 'PREPARED_START_EXPIRED', 'prepared_minted')

    def __copy__(self):
        raise TypeError('CLAIM_SUCCESSOR_CAPABILITY_NOT_COPYABLE')

    def __deepcopy__(self, memo):
        raise TypeError('CLAIM_SUCCESSOR_CAPABILITY_NOT_COPYABLE')

    def __reduce__(self):
        raise TypeError('CLAIM_SUCCESSOR_CAPABILITY_NOT_SERIALIZABLE')

    def _checkpoint(self, stage=None):
        _require_progress(self)
        record = _LIFECYCLE[self]
        need(not record['failed'], 'CAPABILITY_SINGLE_USE')
        need(record['thread'] is None or record['thread'] == threading.get_ident(),
             'CAPABILITY_CONCURRENT_ENTRY')
        need(_same_identities((self.driver, self.outer_io, self.inner_io, self.inner, self.lock,
              self.driver.controls, self.driver.controls.observer, self.driver.gate,
              self.driver.gate.verifier, self.driver.gate.guards), record['identities']) and
             _check_identities(self.driver) == record['check_identities'], 'CAPABILITY_IDENTITY_OR_LOCK')
        need(self.mint_window == record['mint_window'] and
             self.mint_window_sha == digest(record['mint_window']) and
             self.wall_expiry == record['wall_expiry'] and
             self.approval_mono_expiry == record['approval_ceiling'], 'CAPABILITY_MINT_WINDOW_MUTATED')
        expected_expires = record['publication_deadline'] if record['mint_attempted'] and record['publication_deadline'] is not None else record['mint_window'][2]
        need(type(self.expires) in (int, float) and math.isfinite(self.expires) and
             self.expires == expected_expires, 'CAPABILITY_DEADLINE_MUTATED')
        need(self.commit_guard == record['guard'] and self.commit_guard_sha == digest(record['guard']) and
             (record['guard'] is None or record['guard'] == _guard_deadline(self.driver)),
             'CAPABILITY_GUARD_DEADLINE_MUTATED')
        need(self.contract_sha == record['contract_sha'] == digest(self.contract) ==
             digest(self.driver.context['claim_successor']) and
             self.context_sha == record['context_sha'] == digest(self.driver.context) and
             self.predecessor_sha == record['predecessor_sha'] == digest(self.predecessor) and
             self.review_id == record['review_id'] == self.driver.gate.review_id and
             self.review_body_sha == record['review_body_sha'] == self.driver.gate.verifier.body_sha,
             'CAPABILITY_BINDING')
        return _sample(record['driver_record'], record['deadline'], record['predicate'], stage)

    @_burn_on_error
    def _check(self):
        self._checkpoint()
        need(self.driver.journal_io is self.outer_io and self.driver.retained_io is self.inner_io and
             self.driver.inner is self.inner and self.driver.controls.install_lock() is self.lock and
             self.lock.held() is True, 'CAPABILITY_IDENTITY_OR_LOCK')
        self.driver.check_binding()
        self.driver.gate.verifier._bound()
        self.driver.gate.verifier.check_admission_expiry()
        need(self.driver.gate.verifier.checked_under_lock is True and
             self.driver.gate.verifier.cached is not None, 'CAPABILITY_LOCKED_APPROVAL')
        need(self.outer_io.predecessor_inner_absent() is True and
             digest(self.outer_io.predecessor_record()) == digest(self.predecessor['record']),
             'CAPABILITY_PREDECESSOR_DRIFT')
        current_ancestors = self.outer_io.predecessor_ancestors()
        need(type(current_ancestors) is dict and set(current_ancestors)==set(self.predecessor['ancestors']),
             'CAPABILITY_ANCESTOR_SET')
        for path, expected in self.predecessor['ancestors'].items():
            mutable = {'size','mtime_ns','ctime_ns'} if path==TRANSACTION and self.outer_confirmed else set()
            need(digest({k:v for k,v in current_ancestors[path].items() if k not in mutable})==
                 digest({k:v for k,v in expected.items() if k not in mutable}), 'CAPABILITY_ANCESTOR_DRIFT')
        self._checkpoint()

    def consume(self, driver):
        # Check-and-consume is one critical section, including the private proof
        # allocation. Failure burns this handle and never opens another window.
        with _REGISTRY_LOCK:
            recorded = _PROGRESS.get(self)
            need(recorded is not None and recorded[0] == 'PREPARED', 'CAPABILITY_SINGLE_USE')
            try:
                _require_progress(self)
                need(self.stage == 'PREPARED', 'CAPABILITY_SINGLE_USE')
            except BaseException as error:
                self.fail(error)
                raise
            self.stage = 'CONSUMED'
            record = _LIFECYCLE[self]
            record['thread'] = threading.get_ident()
            _PROGRESS[self] = _progress(self)
        try:
            need(driver is self.driver, 'CAPABILITY_DRIVER')
            self._checkpoint('commit_consumed')
            self._check()
        except BaseException as error:
            self.fail(error)
            raise

    @_burn_on_error
    def ready(self, predecessor, guard_deadline, proof=None):
        record = _LIFECYCLE[self]
        with _REGISTRY_LOCK:
            _require_progress(self)
            need(self.stage == 'CONSUMED' and proof is not None and proof is record['proof'] and
                 record['thread'] == threading.get_ident() and record['checks'] == _CHECK_ORDER and
                 len(record['results']) == len(_CHECK_ORDER) and not record['mint_attempted'] and
                 not record['failed'], 'CAPABILITY_COMMIT_PROOF_REQUIRED')
            record['mint_attempted'] = True
        try:
            need(digest(predecessor) == record['predecessor_sha'], 'PREDECESSOR_POST_PREPARE_CHANGED')
            need(guard_deadline == record['guard'] == _guard_deadline(self.driver),
                 'CAPABILITY_GUARD_DEADLINE_MUTATED')
            self._check()
            mono, wall = self._checkpoint()
            # All three ceilings already exist. Never remap signed UTC here or
            # restart the final guard. The prepared start window has been spent.
            deadline = min(mono + TOKEN_SECONDS, guard_deadline, record['approval_ceiling'])
            record['publication_mint'] = (mono, wall)
            record['publication_deadline'] = record['deadline'] = deadline
            record['predicate'] = 'PUBLICATION_EXPIRED'
            self.expires = deadline
            record['driver_record']['timing']['publication_deadline'] = deadline
            self._checkpoint('publication_minted')
            self.inner_raw = self.inner._packed({'stage': 'ADMITTED'})
            self.stage = 'READY'
            _PROGRESS[self] = _progress(self)
            self._check()
        except BaseException as error:
            self.fail(error)
            raise

    @_burn_on_error
    def begin_outer(self, journal, state):
        need(self.stage == 'READY' and journal.io is self.outer_io and
             journal.context == self.driver.context, 'OUTER_COMMIT_ORDER')
        self._check()
        self._checkpoint('outer_begin')
        self.stage = 'OUTER_BEGIN'
        self.outer_attempted = True
        self.outer_raw = journal._raw(state)
        _PROGRESS[self] = _progress(self)
        return self.outer_raw

    @_burn_on_error
    def authorize_outer_io(self, io, name, raw):
        need(self.stage == 'OUTER_BEGIN' and not self.outer_io_used and io is self.outer_io and
             name == NEW_OUTER and raw == self.outer_raw, 'OUTER_IO_CAPABILITY')
        self._check()
        self.outer_io_used = True
        _PROGRESS[self] = _progress(self)

    @_burn_on_error
    def confirm_outer(self, journal, raw):
        need(self.stage == 'OUTER_BEGIN' and self.outer_io_used and journal.last is not None and
             journal.last['data'] == raw and not journal.poisoned, 'OUTER_NOT_CONFIRMED')
        _require_progress(self)
        need(journal.io is self.outer_io and journal.io.read_journal(NEW_OUTER) == journal.last and
             raw == self.outer_raw, 'OUTER_AUTHORITATIVE_READBACK')
        self.outer_confirmed = True
        _PROGRESS[self] = _progress(self)
        self._check()
        self.stage = 'OUTER_CONFIRMED'
        _PROGRESS[self] = _progress(self)
        self._checkpoint('outer_confirmed')

    @_burn_on_error
    def begin_inner(self, journal, raw):
        need(self.stage == 'OUTER_CONFIRMED' and journal is self.inner and raw == self.inner_raw,
             'INNER_COMMIT_ORDER')
        self._check()
        self._checkpoint('inner_begin')
        self.stage = 'INNER_BEGIN'
        self.inner_attempted = True
        _PROGRESS[self] = _progress(self)

    @_burn_on_error
    def authorize_inner_io(self, io, name, raw):
        need(self.stage == 'INNER_BEGIN' and not self.io_used and io is self.inner_io and
             name == NEW_INNER and raw == self.inner_raw, 'INNER_IO_CAPABILITY')
        self._check()
        self.io_used = True
        _PROGRESS[self] = _progress(self)

    @_burn_on_error
    def confirm_inner(self, journal):
        need(self.stage == 'INNER_BEGIN' and self.io_used and journal is self.inner and
             journal.last is not None and journal.last['data'] == self.inner_raw and
             not journal.poisoned, 'INNER_NOT_CONFIRMED')
        _require_progress(self)
        need(journal.io is self.inner_io and journal.io.read_journal(NEW_INNER) == journal.last,
             'INNER_AUTHORITATIVE_READBACK')
        self.inner_confirmed = True
        _PROGRESS[self] = _progress(self)
        self._check()
        self._checkpoint('inner_confirmed')
        self.stage = 'COMPLETE'
        _LIFECYCLE[self]['completed'] = True
        _PROGRESS[self] = _progress(self)
        self._checkpoint('complete')
        self.driver.gate.verifier.seal_admission(self)

    def publication_status(self):
        return {'outer': ('CONFIRMED' if self.outer_confirmed else
                          'ATTEMPTED_UNKNOWN' if self.outer_attempted else 'NOT_ATTEMPTED'),
                'inner': ('CONFIRMED' if self.inner_confirmed else
                          'ATTEMPTED_UNKNOWN' if self.inner_attempted else 'NOT_ATTEMPTED'),
                'automatic_completion': False, 'capability_state': self.stage}

    def timing_status(self):
        return timing_status(self.driver)

    def fail(self, error=None):
        with _REGISTRY_LOCK:
            if self not in _LIFECYCLE:
                return
            record = _LIFECYCLE[self]
            record['failed'] = True
            record['completed'] = False
            if error is not None:
                _failure(record['driver_record'], error)
            self.stage = 'FAILED'
            self.io_used = True
            _PROGRESS[self] = _progress(self)


def validate_live_predecessor(driver, contract):
    validate_contract(contract)
    proof = driver.journal_io.read_predecessor_proof()
    need(type(proof) is dict and digest(proof) == contract['measured_predecessor_sha256'],
         'MEASURED_PREDECESSOR_BINDING')
    need(driver.journal_io.predecessor_inner_absent() is True and
         driver.journal_io.journal_exists(NEW_OUTER) is False and
         driver.retained_io.journal_exists(NEW_INNER) is False, 'PREDECESSOR_OR_SUCCESSOR_CLAIM_EXISTS')
    return proof


def prepare_successor(driver, contract):
    """Run all guards with no claims. Caller owns one existing held lock."""
    contract = validate_contract(contract)
    need(driver.context.get('claim_successor') == contract and driver.gate.review_id != OLD_REVIEW_ID,
         'NEW_APPROVAL_REQUIRED')
    with _REGISTRY_LOCK:
        need(driver not in _DRIVERS and not getattr(driver, '_successor_prepared', False), 'PREPARE_ONCE')
        driver._successor_prepared = True
        record = {'timing': _new_timing(), 'prepared': False,
                  'wall_expiry': parse_expiry(contract['admission_expires_at_utc']),
                  'prepare_proof': object()}
        _DRIVERS[driver] = record
    try:
        _sample(record, stage='prepare_start')
        driver.check_binding()
        need(driver.controls.install_lock().held() is True, 'PREPARE_LOCK')
        driver.gate.verifier.verify_exact(driver.gate.review_id, copy.deepcopy(driver.gate.expected))
        predecessor = validate_live_predecessor(driver, contract)
        from epoch7_recovery_sequence import check_observation
        _sample(record, stage='prepare_preflight_start')
        observed, deadline = _run_guard(driver, lambda: driver.controls.preflight(copy.deepcopy(driver.context)), 'preflight')
        evidence = check_observation(observed, driver.context, 'preflight')
        _sample(record, deadline, 'PREFLIGHT_GUARD_EXPIRED', 'prepare_preflight_complete')
        _sample(record, deadline, 'PREFLIGHT_GUARD_EXPIRED', 'prepare_inner_start')
        unused, deadline = _run_guard(driver, driver.gate.check, 'inner')
        _sample(record, deadline, 'INNER_GUARD_EXPIRED', 'prepare_inner_complete')
        driver.check_binding()
        need(digest(validate_live_predecessor(driver, contract)) == digest(predecessor),
             'PREPARE_PREDECESSOR_RACE')
        need(deadline == _guard_deadline(driver), 'CAPABILITY_GUARD_DEADLINE_MUTATED')
        _sample(record, deadline, 'INNER_GUARD_EXPIRED')
        return PreparedSuccessor(_MINT, driver, contract, predecessor, record['prepare_proof']), evidence
    except BaseException as error:
        _failure(record, error)
        raise


def _use_guard(prepared, kind, deadline):
    record = _LIFECYCLE[prepared]
    _require_progress(prepared)
    need(prepared.commit_guard == record['guard'] and
         prepared.commit_guard_sha == digest(record['guard']), 'CAPABILITY_GUARD_DEADLINE_MUTATED')
    need(deadline == _guard_deadline(prepared.driver), 'CAPABILITY_GUARD_DEADLINE_MUTATED')
    record['guard'] = deadline
    record['deadline'] = deadline
    record['predicate'] = kind.upper() + '_GUARD_EXPIRED'
    prepared.commit_guard = deadline
    prepared.commit_guard_sha = digest(deadline)
    record['driver_record']['timing'][kind + '_deadline'] = deadline


def commit_successor(driver, prepared, journal, state):
    """Actual ordered guards mint one publication right; failures burn it."""
    need(is_prepared_capability(prepared), 'PREPARED_CAPABILITY_REQUIRED')
    # A rejected replay must not revoke a previous successful admission seal.
    need(not is_completed_capability(prepared), 'CAPABILITY_SINGLE_USE')
    prepared.consume(driver)
    try:
        record = _LIFECYCLE[prepared]
        proof = object()
        with _REGISTRY_LOCK:
            need(record['proof'] is None and not record['failed'], 'CAPABILITY_SINGLE_USE')
            record['proof'] = proof
        predecessor = validate_live_predecessor(driver, prepared.contract)
        _record_check(prepared, proof, 'START_PREDECESSOR', predecessor)
        driver.check_binding()
        _record_check(prepared, proof, 'START_BINDING', driver.context)
        review = driver.gate.verifier.verify_exact(driver.gate.review_id, copy.deepcopy(driver.gate.expected))
        _record_check(prepared, proof, 'START_APPROVAL', review)
        prepared._checkpoint('commit_start_checks_complete')
        from epoch7_recovery_sequence import check_observation
        prepared._checkpoint('commit_preflight_start')
        observed, deadline = _run_guard(driver, lambda: driver.controls.preflight(copy.deepcopy(driver.context)), 'preflight')
        evidence = check_observation(observed, driver.context, 'preflight')
        _use_guard(prepared, 'preflight', deadline)
        prepared._checkpoint('commit_preflight_complete')
        _record_check(prepared, proof, 'PREFLIGHT', evidence)
        predecessor = validate_live_predecessor(driver, prepared.contract)
        prepared._checkpoint('commit_predecessor_complete')
        _record_check(prepared, proof, 'FINAL_PREDECESSOR', predecessor)
        # This terminal check assigns all pre-inner fixed IO to the unchanged
        # preflight deadline. The actual gate alone begins its original guard.
        prepared._checkpoint('commit_inner_start')
        checked, deadline = _run_guard(driver, driver.gate.check, 'inner')
        _use_guard(prepared, 'inner', deadline)
        prepared._checkpoint('commit_inner_complete')
        _record_check(prepared, proof, 'INNER_GATE', checked)
        driver.check_binding()
        prepared._checkpoint('commit_binding_complete')
        _record_check(prepared, proof, 'FINAL_BINDING', driver.context)
        prepared.ready(predecessor, record['guard'], proof)
        state['preflight_evidence'] = evidence
        state['successor_timing'] = prepared.timing_status()
        raw = prepared.begin_outer(journal, state)
        journal.create_prechecked(state, prepared)
        prepared.confirm_outer(journal, raw)
        driver.inner.create_prechecked({'stage': 'ADMITTED'}, prepared)
        prepared.confirm_inner(driver.inner)
        state['successor_timing'] = prepared.timing_status()
        return evidence
    except BaseException as error:
        if not is_admitted_capability(prepared):
            prepared.fail(error)
        raise
