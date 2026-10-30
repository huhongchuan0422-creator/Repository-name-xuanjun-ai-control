"""Fail-closed evidence reader for the MCP development execution closure.

The reader does not dispatch work and owns no state.  It evaluates a snapshot
copied from the existing task-center ledger and returns evidence decisions for
one exact task/attempt/writer generation.  Missing producers remain UNKNOWN;
SENT, ACK, heartbeat, process exit, and model text are never promoted to a
completed development task.
"""
from __future__ import print_function

import hashlib
import json


UNKNOWN = 'UNKNOWN'
PROVEN = 'PROVEN'
HOLD = 'HOLD'
NOT_REACHED = 'NOT_REACHED'

STAGES = (
  'SENT', 'ACK', 'PROCESS_STARTED', 'REAL_AI_CALL', 'TESTS_PASSED',
  'ARTIFACT_SUBMITTED', 'INDEPENDENT_REVIEW', 'ACCEPTED')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(
      char in '0123456789abcdef' for char in value)


def _decision(status, reason, refs=None):
    return {'status': status, 'reason': reason,
            'evidence_refs': sorted(set(refs or []))}


def _same(row, identity, names):
    return bool(row) and all(row.get(name) == identity.get(name)
                             for name in names)


def _event_ref(event):
    return 'codex-event:' + str(event.get('event_id', UNKNOWN))


def _identity(snapshot):
    task = snapshot.get('task') or {}
    assignment = snapshot.get('assignment') or {}
    request = snapshot.get('model_request') or {}
    intent = snapshot.get('execution_intent') or {}
    return {
      'tenant_id': snapshot.get('tenant_id'),
      'task_id': task.get('task_id'),
      'attempt_id': task.get('attempt_id'),
      'role_id': assignment.get('role_id') or request.get('role_id'),
      'role_instance_id': (snapshot.get('role_instance') or {}).get('instance_id'),
      'principal_id': assignment.get('principal_id'),
      'request_id': request.get('request_id'),
      'intent_id': intent.get('intent_id'),
      # Run/session are canonical task authority facts.  Never source these
      # selectors from the receipt that is being validated.
      'run_id': task.get('run_id') or task.get('authority_run_id'),
      'session_id': task.get('session_id') or task.get('authority_session_id'),
      'process_id': (snapshot.get('process_receipt') or {}).get('process_id'),
      'writer_principal': task.get('authority_caller_id'),
      'writer_fence': task.get('fence'),
      'writer_epoch': task.get('epoch'),
    }


def _integrity(snapshot, identity, observed_at, require_current_writer=True):
    task = snapshot.get('task') or {}
    assignment = snapshot.get('assignment') or {}
    binding = snapshot.get('model_request_binding') or {}
    intent = snapshot.get('execution_intent') or {}
    problems = []
    for name in ('tenant_id', 'task_id', 'attempt_id', 'role_id',
                 'principal_id', 'writer_principal', 'run_id', 'session_id'):
        if identity.get(name) in (None, '', UNKNOWN):
            problems.append('MISSING_' + name.upper())
    if type(identity.get('writer_fence')) is not int or identity['writer_fence'] < 1:
        problems.append('INVALID_WRITER_FENCE')
    if type(identity.get('writer_epoch')) is not int or identity['writer_epoch'] < 1:
        problems.append('INVALID_WRITER_EPOCH')
    if require_current_writer:
        if task.get('authority_state') != 'VALID':
            problems.append('WRITER_AUTHORITY_NOT_VALID')
        valid_until = task.get('authority_valid_until')
        if valid_until is None or observed_at is None or observed_at >= valid_until:
            problems.append('WRITER_AUTHORITY_NOT_CURRENT')
    if not _same(assignment, identity,
                 ('tenant_id', 'task_id', 'attempt_id', 'role_id', 'principal_id')):
        problems.append('ASSIGNMENT_IDENTITY_MISMATCH')
    if assignment.get('state') != 'ASSIGNED':
        problems.append('ASSIGNMENT_NOT_CURRENT')
    role_instance = snapshot.get('role_instance') or {}
    if (role_instance.get('instance_id') != identity.get('principal_id') or
            identity.get('role_instance_id') != identity.get('principal_id')):
        problems.append('ROLE_INSTANCE_IDENTITY_MISMATCH')
    if ('current_request_id' in role_instance and
            role_instance.get('current_request_id') != identity.get('request_id')):
        problems.append('ROLE_INSTANCE_REQUEST_MISMATCH')
    request = snapshot.get('model_request') or {}
    if request and not _same(request, identity,
                             ('tenant_id', 'task_id', 'attempt_id', 'role_id',
                              'request_id')):
        problems.append('MODEL_REQUEST_IDENTITY_MISMATCH')
    if binding:
        expected = ('writer_principal', 'writer_fence', 'writer_epoch')
        if not _same(binding, identity, expected):
            problems.append('REQUEST_WRITER_GENERATION_MISMATCH')
        if identity.get('request_id') and binding.get('request_id') != identity['request_id']:
            problems.append('REQUEST_BINDING_ID_MISMATCH')
    if intent:
        if not _same(intent, identity, ('tenant_id', 'task_id', 'attempt_id')):
            problems.append('INTENT_TASK_ATTEMPT_MISMATCH')
        if intent.get('writer_principal') != identity['writer_principal'] or \
                intent.get('writer_fence') != identity['writer_fence'] or \
                intent.get('writer_epoch') != identity['writer_epoch']:
            problems.append('INTENT_WRITER_GENERATION_MISMATCH')
        if intent.get('session_id') != identity['session_id']:
            problems.append('INTENT_SESSION_MISMATCH')
    return problems


def evaluate_closure(snapshot, observed_at=None):
    """Evaluate one exact development chain without mutating its source.

    ``snapshot`` is deliberately explicit so callers cannot merge evidence
    from different attempts.  The result digest can be stored by the owning
    service as a read receipt; this module itself persists nothing.
    """
    if not isinstance(snapshot, dict):
        raise ValueError('SNAPSHOT_OBJECT_REQUIRED')
    identity = _identity(snapshot)
    task = snapshot.get('task') or {}
    terminal = snapshot.get('terminal_receipt') or {}
    completed_generation = (task.get('state') == 'SUCCESS' and
      task.get('authority_state') == 'REVOKED' and
      _same(terminal, identity, ('tenant_id', 'task_id', 'attempt_id')) and
      terminal.get('state') == 'SUCCESS' and
      terminal.get('authority_state') == 'REVOKED')
    problems = _integrity(snapshot, identity, observed_at,
                          require_current_writer=not completed_generation)
    if problems:
        stages = {name: _decision(HOLD, 'IDENTITY_OR_WRITER_HOLD:' +
                                  ','.join(sorted(problems))) for name in STAGES}
        result = {'verdict': HOLD, 'identity': identity,
                  'integrity_holds': sorted(problems), 'stages': stages}
        result['receipt_sha256'] = hashlib.sha256(
          _canonical(result).encode('utf-8')).hexdigest()
        return result

    stages = {}
    events = [item for item in snapshot.get('execution_events', [])
              if _same(item, identity, ('tenant_id', 'intent_id')) and
              item.get('accepted') in (1, True)]
    sent = [item for item in events if item.get('event_kind') == 'SENT_INTENT']
    stages['SENT'] = (_decision(PROVEN, 'ACCEPTED_SEND_INTENT_EVENT',
                                [_event_ref(item) for item in sent]) if sent else
                      _decision(UNKNOWN, 'NO_ACCEPTED_SEND_INTENT_EVENT'))

    ack = [item for item in events if item.get('event_kind') in
           ('ACKED', 'RUNNING', 'WAITING_APPROVAL', 'EXECUTION_COMPLETED',
            'SUCCEEDED')]
    intent = snapshot.get('execution_intent') or {}
    ack_identity = bool(intent.get('execution_id') or intent.get('thread_id'))
    stages['ACK'] = (_decision(PROVEN, 'REMOTE_EXECUTION_ID_ACKNOWLEDGED',
                               [_event_ref(item) for item in ack])
                     if ack and ack_identity else
                     _decision(UNKNOWN, 'ACK_WITH_REMOTE_EXECUTION_ID_NOT_PROVEN'))

    process = snapshot.get('process_receipt') or {}
    process_ok = (_same(process, identity, ('tenant_id', 'task_id', 'attempt_id',
      'run_id', 'session_id', 'writer_epoch')) and
      bool(process.get('process_id')) and
      process.get('state') == 'STARTED' and
      process.get('source_kind') == 'TRUSTED_PROCESS_OBSERVER' and
      bool(process.get('observed_at')))
    stages['PROCESS_STARTED'] = (_decision(PROVEN, 'TRUSTED_PROCESS_RECEIPT',
      ['process:' + str(identity['process_id'])]) if process_ok else
      _decision(UNKNOWN, 'TRUSTED_PROCESS_RECEIPT_NOT_CONNECTED'))

    call = snapshot.get('ai_call_receipt') or {}
    request = snapshot.get('model_request') or {}
    call_ok = (_same(call, identity, ('tenant_id', 'task_id', 'attempt_id',
      'request_id', 'role_id', 'writer_epoch')) and
      call.get('source_kind') == 'LIVE_PROVIDER_RECEIPT' and
      bool(call.get('provider_request_id')) and _sha(call.get('response_sha256')) and
      request.get('state') == 'SUCCEEDED')
    stages['REAL_AI_CALL'] = (_decision(PROVEN, 'ATTRIBUTABLE_LIVE_PROVIDER_RECEIPT',
      ['provider-request:' + str(call.get('provider_request_id'))]) if call_ok else
      _decision(UNKNOWN, 'LIVE_PROVIDER_RECEIPT_NOT_PROVEN_TEST_FIXTURE_NOT_ACCEPTED'))

    checklist = snapshot.get('checklist') or {}
    checklist_ok = (_same(checklist, identity, ('tenant_id', 'task_id', 'attempt_id')) and
                    checklist.get('all_required_passed') in (1, True) and
                    checklist.get('has_unexecuted') in (0, False) and
                    _sha(checklist.get('content_sha256')))
    stages['TESTS_PASSED'] = (_decision(PROVEN, 'EXECUTED_FROZEN_CHECKLIST',
      ['checklist:' + str(checklist.get('content_sha256'))]) if checklist_ok else
      _decision(UNKNOWN, 'COMPLETE_EXECUTED_CHECKLIST_NOT_PROVEN'))

    candidate = snapshot.get('candidate') or {}
    artifact_ok = (_same(candidate, identity,
      ('tenant_id', 'task_id', 'attempt_id')) and
      _sha(candidate.get('artifact_sha256')) and checklist_ok and
      candidate.get('checklist_sha256') == checklist.get('content_sha256') and
      candidate.get('submitted_by') == identity['principal_id'])
    stages['ARTIFACT_SUBMITTED'] = (_decision(PROVEN,
      'FROZEN_ARTIFACT_BOUND_TO_CURRENT_ATTEMPT',
      ['artifact:' + str(candidate.get('artifact_sha256'))]) if artifact_ok else
      _decision(UNKNOWN, 'CURRENT_ATTEMPT_ARTIFACT_NOT_PROVEN'))

    reviews = [item for item in snapshot.get('reviews', [])
               if item.get('tenant_id') == identity['tenant_id'] and
               item.get('candidate_id') == candidate.get('candidate_id')]
    passed = {item.get('review_kind'): item for item in reviews
              if item.get('decision') in ('QA_PASSED', 'SECURITY_PASSED')}
    reviewers = {item.get('reviewer') for item in passed.values()}
    review_ok = (artifact_ok and set(passed) == {'QA', 'SECURITY'} and
                 len(reviewers) == 2 and
                 identity['principal_id'] not in reviewers and
                 candidate.get('state') in ('REVIEW_PASSED', 'ACCEPTED'))
    stages['INDEPENDENT_REVIEW'] = (_decision(PROVEN,
      'DISTINCT_QA_AND_SECURITY_REVIEW_PASSED',
      ['review:' + str(item.get('review_id')) for item in passed.values()])
      if review_ok else _decision(UNKNOWN,
      'DISTINCT_CURRENT_ARTIFACT_QA_AND_SECURITY_REVIEW_NOT_PROVEN'))

    accepted_by = candidate.get('accepted_by')
    accepted_ok = (review_ok and candidate.get('state') == 'ACCEPTED' and
      bool(accepted_by) and accepted_by != identity['principal_id'] and
      accepted_by not in reviewers and
      _same(terminal, identity, ('tenant_id', 'task_id', 'attempt_id')) and
      terminal.get('state') == 'SUCCESS' and
      terminal.get('artifact_sha256') == candidate.get('artifact_sha256') and
      terminal.get('authority_state') == 'REVOKED' and completed_generation)
    stages['ACCEPTED'] = (_decision(PROVEN,
      'CANONICAL_SUCCESS_AND_INDEPENDENT_ACCEPTANCE',
      ['acceptor:' + str(accepted_by),
       'terminal-artifact:' + str(candidate.get('artifact_sha256'))])
      if accepted_ok else _decision(UNKNOWN,
      'CANONICAL_SUCCESS_INDEPENDENT_ACCEPTANCE_NOT_PROVEN'))

    verdict = PROVEN if all(stages[name]['status'] == PROVEN for name in STAGES) \
      else (HOLD if any(stages[name]['status'] == HOLD for name in STAGES) else UNKNOWN)
    result = {'verdict': verdict, 'identity': identity, 'integrity_holds': [],
              'stages': stages,
              'completion_rule': 'ALL_STAGES_PROVEN_SAME_IDENTITY'}
    result['receipt_sha256'] = hashlib.sha256(
      _canonical(result).encode('utf-8')).hexdigest()
    return result


def admission_for_real_task(snapshot, observed_at=None):
    """Return strict pre-execution admission for a future real task.

    Admission proves identity and writer freshness only.  It does not say that
    a process or model call occurred and never returns a completion verdict.
    """
    identity = _identity(snapshot)
    holds = _integrity(snapshot, identity, observed_at)
    connection = snapshot.get('connection') or {}
    quota = snapshot.get('quota') or {}
    if (connection.get('purpose') not in ('CODEX_EXECUTION', 'MODEL_INFERENCE') or
            connection.get('status') != 'ACTIVE'):
        holds.append('ACTIVE_EXECUTION_CONNECTION_REQUIRED')
    if quota.get('quota_state') != 'AVAILABLE':
        holds.append('ATTRIBUTABLE_QUOTA_AVAILABLE_REQUIRED')
    if quota.get('quota_source') not in ('EXISTING_SUBSCRIPTION_INCLUDED',
                                          'VERIFIED_FREE_TIER'):
        holds.append('ZERO_NEW_SPEND_SOURCE_REQUIRED')
    if not snapshot.get('idempotency_key'):
        holds.append('IDEMPOTENCY_KEY_REQUIRED')
    return {'status': PROVEN if not holds else HOLD, 'identity': identity,
            'holds': sorted(set(holds)),
            'does_not_prove': ['PROCESS_STARTED', 'REAL_AI_CALL', 'COMPLETION']}
