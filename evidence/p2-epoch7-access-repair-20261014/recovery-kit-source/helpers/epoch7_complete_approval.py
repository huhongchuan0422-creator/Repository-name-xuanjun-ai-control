"""One PR58 approval envelope for retained gate and complete outer sequence.

No approval is created. Fetching/validating a comment is not install admission.
The outer driver still owns live guards, lock and exclusive attempt claims.
"""
import copy
import hashlib
import json
from epoch7_approval import (fetch, need, SHA, MARKER, TX, CONSUMED)
from epoch7_injected_recovery import RecoveryGate, ATTEMPT, DECISION as RETAINED_DECISION
from epoch7_recovery_sequence import (context_from_gate, observation, OUTER_NAME,
    PHASES, STOP_UNITS, ADAPTER_BOUNDS)

DECISION='APPROVED_ONE_EXACT_EPOCH7_COMPLETE_RETAINED_RECOVERY'

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def same(a,b):return canonical(a)==canonical(b)

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

_CONTRACT_FIELDS = frozenset(('schema', 'transaction_id', 'expected_epoch',
    'proposed_prepared_epoch', 'authorization_sha256', 'snapshot_sha256',
    'candidate_sha256', 'runtime_manifest_sha256', 'delta_sha256',
    'kit_manifest_sha256', 'security_delta_sha256', 'inner_attempt_name',
    'outer_receipt_name', 'phase_order', 'stop_units', 'adapter_bounds',
    'tls_change', 'production_acceptance'))
_CONTEXT_FIELDS = _CONTRACT_FIELDS | frozenset(('review_id', 'context_sha256'))
_DELTA_FIELDS = frozenset(('attempt_create_policy', 'authorized_attempts',
    'automatic_retry', 'cache_import_delete_or_rewrite', 'candidate_sha256',
    'changes', 'dry_run_calls', 'effects', 'expected_epoch', 'failure_policy',
    'generation_change', 'install_admission', 'issuance_calls', 'kind',
    'legacy_restart', 'new_attempt_name', 'prerequisite_replay', 'preserve',
    'proposed_epoch', 'renewal_calls', 'runtime_manifest_sha256', 'sandbox_change',
    'schema', 'snapshot_sha256', 'tls_change', 'transaction_id', 'controller_transition'))
_AUTHORIZATION_FIELDS = frozenset(('additive_targets', 'additive_targets_sha256',
    'authorized_attempts', 'automatic_retry', 'candidate_sha256',
    'complete_delta_sha256', 'decision', 'delta_sha256', 'expected_epoch',
    'failure_policy', 'historical_notification_replay', 'kit_manifest_sha256',
    'legacy_restart', 'production_acceptance', 'proposed_prepared_epoch',
    'retained_target_count', 'runtime_manifest_sha256', 'schema',
    'security_delta_sha256', 'snapshot_sha256', 'tls_issuance_renewal_or_dry_run',
    'total_target_count', 'transaction_id'))


def sequence_contract(context_or_contract):
    """Return a review-ID-neutral proposal, never authentication or admission.

    A full context must verify its exact fresh ID and full hash before stripping
    only those two admission fields. A neutral contract has neither field. All
    other fields, including authorization, kit, phases and TLS pins, are retained.
    Runtime effects/receipts must continue using the full admitted context.
    """
    need(type(context_or_contract) is dict, 'COMPLETE_SEQUENCE_CONTRACT')
    value = copy.deepcopy(context_or_contract)
    if set(value) == _CONTEXT_FIELDS:
        review_id = value['review_id']
        need(type(review_id) is int and review_id > 0 and review_id not in CONSUMED,
             'COMPLETE_FRESH_REVIEW')
        head = value.pop('context_sha256')
        need(type(head) is str and SHA.fullmatch(head) and digest(value) == head,
             'COMPLETE_CONTEXT_MUTATED')
        value.pop('review_id')
    else:
        need(set(value) == _CONTRACT_FIELDS, 'COMPLETE_SEQUENCE_CONTRACT_FIELDS')
    fixed = {'schema':1, 'transaction_id':TX, 'expected_epoch':7,
        'proposed_prepared_epoch':8, 'inner_attempt_name':ATTEMPT,
        'outer_receipt_name':OUTER_NAME, 'phase_order':list(PHASES),
        'stop_units':list(STOP_UNITS), 'adapter_bounds':copy.deepcopy(ADAPTER_BOUNDS),
        'production_acceptance':'PENDING'}
    need(same(dict((key, value[key]) for key in fixed), fixed),
         'COMPLETE_SEQUENCE_FIXED_POLICY')
    for key in ('authorization_sha256', 'snapshot_sha256', 'candidate_sha256',
                'runtime_manifest_sha256', 'delta_sha256', 'kit_manifest_sha256',
                'security_delta_sha256'):
        need(type(value[key]) is str and SHA.fullmatch(value[key]),
             'COMPLETE_SEQUENCE_HASH')
    need(type(value['tls_change']) is dict, 'COMPLETE_SEQUENCE_TLS')
    return value


def sequence_contract_sha256(context_or_contract):
    """Plan/resource pin of the neutral contract; not a proof of authority."""
    return digest(sequence_contract(context_or_contract))


def preapproval_sequence_contract(delta, retained_authorization):
    """Compile from already validated proposal inputs without any review ID.

    This checks the exact cross-bindings, but does not replace the gate's full
    snapshot/candidate/additive validation or genuine GitHub authentication.
    """
    need(type(delta) is dict and type(retained_authorization) is dict,
         'COMPLETE_PREAPPROVAL_INPUTS')
    need(set(delta) == _DELTA_FIELDS and set(retained_authorization) == _AUTHORIZATION_FIELDS,
         'COMPLETE_PREAPPROVAL_INPUT_FIELDS')
    # A field name alone is not a controller-transition proof. Recompute the
    # exact old/new activation pair and unchanged canonical ledger identity.
    from epoch7_delta import validate_controller_transition
    transition = validate_controller_transition(delta['controller_transition'])
    need(transition['after']['release_sha256'] == delta['runtime_manifest_sha256'],
         'COMPLETE_CONTROLLER_TRANSITION_MANIFEST')
    expected = retained_authorization
    policy = {'schema':1, 'decision':RETAINED_DECISION, 'transaction_id':TX,
        'expected_epoch':7, 'proposed_prepared_epoch':8, 'authorized_attempts':1,
        'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY', 'automatic_retry':False,
        'legacy_restart':False, 'historical_notification_replay':False,
        'tls_issuance_renewal_or_dry_run':False, 'production_acceptance':'PENDING'}
    need(same(dict((key, expected.get(key)) for key in policy), policy),
         'COMPLETE_PREAPPROVAL_POLICY')
    delta_policy = {'schema':1, 'kind':'OFFLINE_EPOCH7_DELTA_NOT_INSTALL_PLAN',
        'transaction_id':TX, 'expected_epoch':7, 'proposed_epoch':8,
        'authorized_attempts':0, 'effects':0, 'install_admission':'NOT_GRANTED'}
    need(same(dict((key, delta.get(key)) for key in delta_policy), delta_policy),
         'COMPLETE_PREAPPROVAL_DELTA')
    need(expected.get('delta_sha256') == digest(delta), 'COMPLETE_PREAPPROVAL_DELTA_HASH')
    for key in ('snapshot_sha256', 'candidate_sha256', 'runtime_manifest_sha256'):
        need(expected.get(key) == delta.get(key), 'COMPLETE_PREAPPROVAL_BINDING')
    value = {'schema':1, 'transaction_id':TX, 'expected_epoch':7,
        'proposed_prepared_epoch':8, 'authorization_sha256':digest(expected),
        'snapshot_sha256':delta['snapshot_sha256'],
        'candidate_sha256':delta['candidate_sha256'],
        'runtime_manifest_sha256':delta['runtime_manifest_sha256'],
        'delta_sha256':digest(delta), 'kit_manifest_sha256':expected['kit_manifest_sha256'],
        'security_delta_sha256':expected['security_delta_sha256'],
        'inner_attempt_name':ATTEMPT, 'outer_receipt_name':OUTER_NAME,
        'phase_order':list(PHASES), 'stop_units':list(STOP_UNITS),
        'adapter_bounds':copy.deepcopy(ADAPTER_BOUNDS),
        'tls_change':copy.deepcopy(delta['tls_change']), 'production_acceptance':'PENDING'}
    return sequence_contract(value)


def expected_complete_from_inputs(plan_sha256, delta, retained_authorization):
    """Exact unsigned body for review, with no invented future comment ID."""
    need(isinstance(plan_sha256,str) and SHA.fullmatch(plan_sha256),'COMPLETE_PLAN_HASH')
    contract = preapproval_sequence_contract(delta, retained_authorization)
    return {'schema':2,'reviewer':'CHATGPT_NATIVE_TASK5','decision':DECISION,
        'transaction_id':TX,'recovery_plan_sha256':plan_sha256,
        'retained_authorization':copy.deepcopy(retained_authorization),
        'sequence_contract':contract,'production_acceptance':'PENDING'}


def expected_complete(plan_sha256, gate):
    need(isinstance(gate,RecoveryGate),'COMPLETE_GATE_REQUIRED')
    wanted = expected_complete_from_inputs(plan_sha256, gate.delta, gate.expected)
    need(same(wanted['sequence_contract'], sequence_contract(context_from_gate(gate))),
         'COMPLETE_ADMISSION_CONTRACT')
    return wanted

class CompleteApprovalVerifier(object):
    def __init__(self, review_id, body_sha256, install_lock_held, fetcher=fetch):
        need(type(review_id) is int and review_id>0 and review_id not in CONSUMED,'COMPLETE_FRESH_REVIEW')
        need(isinstance(body_sha256,str) and SHA.fullmatch(body_sha256),'COMPLETE_BODY_HASH')
        need(callable(install_lock_held) and callable(fetcher),'COMPLETE_ADAPTERS')
        self.review_id=review_id;self.body_sha=body_sha256
        self.authority_sha=digest({"review_id":review_id,"body_sha256":body_sha256})
        self.lock_check=install_lock_held;self.fetcher=fetcher
        self.wanted=None;self.context=None;self.cached=None;self.checked_under_lock=False
    def bind(self, gate, plan_sha256):
        need(self.wanted is None,'COMPLETE_BIND_ONCE')
        need(gate.verifier is self and gate.review_id==self.review_id,'COMPLETE_GATE_VERIFIER')
        self.wanted=expected_complete(plan_sha256,gate)
        self.context=context_from_gate(gate)
        self.binding_sha=digest(self.wanted)
    def _bound(self):
        need(digest({"review_id":self.review_id,"body_sha256":self.body_sha})==self.authority_sha,"COMPLETE_AUTHORITY_MUTATED")
        need(self.wanted is not None and digest(self.wanted)==self.binding_sha,'COMPLETE_BINDING_MUTATED')
        need(type(self.context) is dict and self.context['review_id']==self.review_id,'COMPLETE_CONTEXT')
        check=dict(self.context);head=check.pop('context_sha256')
        need(digest(check)==head,'COMPLETE_CONTEXT_MUTATED')
        need(same(sequence_contract(self.context), self.wanted['sequence_contract']),
             'COMPLETE_ADMISSION_CONTRACT')
    def verify_outer_review(self, context):
        # Every attempted recheck revokes the old admission before validation.
        self.checked_under_lock=False
        self._bound();need(same(context,self.context),'COMPLETE_OUTER_CONTEXT')
        # Outer sequence calls before and after lock acquisition. Both perform
        # a fresh exact HTTPS comment check before claiming the one attempt.
        value=self.fetcher(self.review_id,copy.deepcopy(self.wanted))
        need(type(value) is dict and set(value)=={'review_id','body_sha256','approval'} and
             value['review_id']==self.review_id and value['body_sha256']==self.body_sha and
             same(value['approval'],self.wanted),'COMPLETE_AUTHENTICATED_BODY')
        if self.cached is not None:need(same(value,self.cached),'COMPLETE_REVIEW_CHANGED')
        self.cached=copy.deepcopy(value)
        if self.lock_check() is True:self.checked_under_lock=True
        return observation(self.context,'verify_outer_review',digest(value))
    def verify_exact(self, review_id, expected):
        self._bound()
        need(self.lock_check() is True and self.checked_under_lock and self.cached is not None,
             'COMPLETE_FRESH_LOCKED_VERIFICATION_REQUIRED')
        need(type(review_id) is int and review_id==self.review_id and
             same(expected,self.wanted['retained_authorization']),'COMPLETE_INNER_BINDING')
        # No repeated HTTP calls mid-effect: authority is bound to the one
        # claimed transaction, whose live lock/state checks remain mandatory.
        return {'review_id':review_id,'body_sha256':self.body_sha,'binding':copy.deepcopy(expected)}
