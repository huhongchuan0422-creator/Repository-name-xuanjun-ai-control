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
        'effect_scope', 'measured_predecessor_sha256'}, 'CONTRACT_FIELDS')
    need(type(value['schema']) is int and value['schema'] == 1 and
        value['kind'] == 'EXACT_CLAIM_ONLY_SUCCESSOR' and
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
            value.stage == 'COMPLETE' and all(flag is True for flag in _progress(value)[1:7]) and
            type(value.outer_raw) is bytes and type(value.inner_raw) is bytes)


def _clock():
    mono, wall = time.monotonic(), time.time()
    need(type(mono) in (int, float) and type(wall) in (int, float) and
         math.isfinite(mono) and math.isfinite(wall), 'CLOCK_UNKNOWN')
    return mono, wall


def is_prepared_capability(value):
    return (type(value) is PreparedSuccessor and value in _ISSUED and
            value._mint is _MINT and value.owner_pid == os.getpid())


class PreparedSuccessor(object):
    """Process-local single-use capability; never a serialized PASS flag."""
    def __init__(self, mint, driver, contract, predecessor):
        need(mint is _MINT, 'CAPABILITY_CONSTRUCTOR')
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
        mono, wall = _clock()
        self.wall_expiry = parse_expiry(contract['admission_expires_at_utc'])
        need(wall < self.wall_expiry, 'APPROVAL_EXPIRED')
        self.expires = mono + min(TOKEN_SECONDS, self.wall_expiry - wall)
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
        _ISSUED.add(self)
        _PROGRESS[self] = _progress(self)

    def __copy__(self):
        raise TypeError('CLAIM_SUCCESSOR_CAPABILITY_NOT_COPYABLE')

    def __deepcopy__(self, memo):
        raise TypeError('CLAIM_SUCCESSOR_CAPABILITY_NOT_COPYABLE')

    def __reduce__(self):
        raise TypeError('CLAIM_SUCCESSOR_CAPABILITY_NOT_SERIALIZABLE')

    def _check(self):
        _require_progress(self)
        mono, wall = _clock()
        need(type(self.mint_window) is tuple and len(self.mint_window)==3 and
             all(type(v) in (int,float) and math.isfinite(v) for v in self.mint_window) and
             digest(self.mint_window)==self.mint_window_sha and
             self.wall_expiry==parse_expiry(self.contract['admission_expires_at_utc']) and
             self.mint_window[2]==self.mint_window[0]+min(TOKEN_SECONDS,self.wall_expiry-self.mint_window[1]),
             'CAPABILITY_MINT_WINDOW_MUTATED')
        need(digest(self.commit_guard)==self.commit_guard_sha and
             (self.commit_guard is None or type(self.commit_guard) in (int,float) and
              math.isfinite(self.commit_guard) and self.commit_guard==self.driver.controls.observer.guard_deadline),
             'CAPABILITY_GUARD_DEADLINE_MUTATED')
        expected_deadline = self.mint_window[2] if self.commit_guard is None else min(self.mint_window[2], self.commit_guard)
        need(type(self.expires) in (int,float) and math.isfinite(self.expires) and
             self.expires==expected_deadline, 'CAPABILITY_DEADLINE_MUTATED')
        need(self.mint_window[0] <= mono < self.expires and wall < self.wall_expiry, 'CAPABILITY_EXPIRED')
        need(is_prepared_capability(self) and self.driver.journal_io is self.outer_io and
             self.driver.retained_io is self.inner_io and self.driver.inner is self.inner and
             self.driver.controls.install_lock() is self.lock and self.lock.held() is True,
             'CAPABILITY_IDENTITY_OR_LOCK')
        need(digest(self.contract) == self.contract_sha and
             digest(self.driver.context) == self.context_sha and
             digest(self.driver.context['claim_successor']) == self.contract_sha and
             self.driver.gate.review_id == self.review_id and
             self.driver.gate.verifier.body_sha == self.review_body_sha and
             self.review_id != OLD_REVIEW_ID, 'CAPABILITY_BINDING')
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
        after_mono, after_wall = _clock()
        need(after_mono < self.expires and after_wall < self.wall_expiry, 'CAPABILITY_EXPIRED')

    def consume(self, driver):
        _require_progress(self)
        need(self.stage == 'PREPARED', 'CAPABILITY_SINGLE_USE')
        self.stage = 'CONSUMED'
        _PROGRESS[self] = _progress(self)
        need(driver is self.driver, 'CAPABILITY_DRIVER')
        self._check()

    def ready(self, predecessor, guard_deadline):
        need(self.stage == 'CONSUMED', 'CAPABILITY_COMMIT_ORDER')
        self._check()
        need(digest(predecessor) == self.predecessor_sha, 'PREDECESSOR_POST_PREPARE_CHANGED')
        need(type(guard_deadline) in (int, float) and math.isfinite(guard_deadline),
             'ORIGINAL_GUARD_DEADLINE_REQUIRED')
        self.commit_guard = guard_deadline
        self.commit_guard_sha = digest(guard_deadline)
        self.expires = min(self.mint_window[2], guard_deadline)
        self._check()
        self.inner_raw = self.inner._packed({'stage': 'ADMITTED'})
        self.stage = 'READY'
        _PROGRESS[self] = _progress(self)

    def begin_outer(self, journal, state):
        need(self.stage == 'READY' and journal.io is self.outer_io and
             journal.context == self.driver.context, 'OUTER_COMMIT_ORDER')
        self._check()
        self.stage = 'OUTER_BEGIN'
        self.outer_attempted = True
        self.outer_raw = journal._raw(state)
        _PROGRESS[self] = _progress(self)
        return self.outer_raw

    def authorize_outer_io(self, io, name, raw):
        need(self.stage == 'OUTER_BEGIN' and not self.outer_io_used and io is self.outer_io and
             name == NEW_OUTER and raw == self.outer_raw, 'OUTER_IO_CAPABILITY')
        self._check()
        self.outer_io_used = True
        _PROGRESS[self] = _progress(self)

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

    def begin_inner(self, journal, raw):
        need(self.stage == 'OUTER_CONFIRMED' and journal is self.inner and raw == self.inner_raw,
             'INNER_COMMIT_ORDER')
        self._check()
        self.stage = 'INNER_BEGIN'
        self.inner_attempted = True
        _PROGRESS[self] = _progress(self)

    def authorize_inner_io(self, io, name, raw):
        need(self.stage == 'INNER_BEGIN' and not self.io_used and io is self.inner_io and
             name == NEW_INNER and raw == self.inner_raw, 'INNER_IO_CAPABILITY')
        self._check()
        self.io_used = True
        _PROGRESS[self] = _progress(self)

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
        self.stage = 'COMPLETE'
        _PROGRESS[self] = _progress(self)
        self.driver.gate.verifier.seal_admission(self)

    def publication_status(self):
        return {'outer': ('CONFIRMED' if self.outer_confirmed else
                          'ATTEMPTED_UNKNOWN' if self.outer_attempted else 'NOT_ATTEMPTED'),
                'inner': ('CONFIRMED' if self.inner_confirmed else
                          'ATTEMPTED_UNKNOWN' if self.inner_attempted else 'NOT_ATTEMPTED'),
                'automatic_completion': False, 'capability_state': self.stage}

    def fail(self):
        self.stage = 'FAILED'
        self.io_used = True
        if is_prepared_capability(self): _PROGRESS[self] = _progress(self)


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
    need(not getattr(driver, '_successor_prepared', False), 'PREPARE_ONCE')
    driver._successor_prepared = True
    driver.check_binding()
    need(driver.controls.install_lock().held() is True, 'PREPARE_LOCK')
    driver.gate.verifier.verify_exact(driver.gate.review_id, copy.deepcopy(driver.gate.expected))
    predecessor = validate_live_predecessor(driver, contract)
    from epoch7_recovery_sequence import check_observation
    evidence = check_observation(driver.controls.preflight(copy.deepcopy(driver.context)),
                                 driver.context, 'preflight')
    driver.gate.check()
    driver.check_binding()
    need(digest(validate_live_predecessor(driver, contract)) == digest(predecessor),
         'PREPARE_PREDECESSOR_RACE')
    return PreparedSuccessor(_MINT, driver, contract, predecessor), evidence


def commit_successor(driver, prepared, journal, state):
    """Repeat actual guards, then the fixed two exclusive publications once."""
    need(is_prepared_capability(prepared), 'PREPARED_CAPABILITY_REQUIRED')
    prepared.consume(driver)
    try:
        predecessor = validate_live_predecessor(driver, prepared.contract)
        driver.check_binding()
        driver.gate.verifier.verify_exact(driver.gate.review_id, copy.deepcopy(driver.gate.expected))
        from epoch7_recovery_sequence import check_observation
        evidence = check_observation(driver.controls.preflight(copy.deepcopy(driver.context)),
                                     driver.context, 'preflight')
        # The complete original inner gate is the last live safety gate. This
        # includes writer/DB exclusion; no cached boolean substitutes for it.
        predecessor = validate_live_predecessor(driver, prepared.contract)
        driver.gate.check()
        driver.check_binding()
        prepared.ready(predecessor, driver.controls.observer.guard_deadline)
        state['preflight_evidence'] = evidence
        raw = prepared.begin_outer(journal, state)
        journal.create_prechecked(state, prepared)
        prepared.confirm_outer(journal, raw)
        driver.inner.create_prechecked({'stage': 'ADMITTED'}, prepared)
        prepared.confirm_inner(driver.inner)
        return evidence
    except BaseException:
        prepared.fail()
        raise
