"""Task 4/5 development closed-loop coordinator over the existing Supervisor.

This module never creates a task database, starts a model, grants a lease, or
switches chat windows.  It records exact review/test/handoff evidence in the
existing canonical Supervisor state machine and treats terminal outbox delivery
as part of closure.
"""
from __future__ import print_function

from entry_review_gate import review_outcome

TRUE_PROOF = {
    'receiver_accepted': True,
    'old_writer_stopped': True,
    'old_fence_invalidated': True,
    'effects_reconciled': True,
}


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name)
    return value


def _task(supervisor, task_id):
    row = supervisor.db.execute(
        'SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
    if row is None:
        raise KeyError(task_id)
    return dict(row)


def apply_code_review(supervisor, task_id, attempt_id, event_prefix,
                      contract, files, reviews, review_keys, observed_at,
                      evidence_ref, repair_owner, repair_entry,
                      pass_owner, pass_entry):
    """Persist exact-version review and request the next bounded handoff."""
    _nonempty(event_prefix, 'EVENT_PREFIX_REQUIRED')
    _nonempty(evidence_ref, 'REVIEW_EVIDENCE_REQUIRED')
    outcome = review_outcome(contract, files, reviews, review_keys)
    if outcome['state'] == 'HOLD_INDEPENDENT_REVIEW_REQUIRED':
        return dict(outcome, next_action='AWAIT_INDEPENDENT_REVIEW',
                    handoff_requested=False)
    if outcome['state'] == 'REPAIR_REQUIRED':
        next_owner = _nonempty(repair_owner, 'REPAIR_OWNER_REQUIRED')
        next_entry = _nonempty(repair_entry, 'REPAIR_ENTRY_REQUIRED')
        phase = 'REVIEW_FAILED_REPAIR_REQUIRED'
    else:
        next_owner = _nonempty(pass_owner, 'PASS_OWNER_REQUIRED')
        next_entry = _nonempty(pass_entry, 'PASS_ENTRY_REQUIRED')
        phase = 'REVIEW_PASSED_TEST_REQUIRED'
    progress_payload = {
        'phase': phase,
        'bundle_sha256': outcome['bundle_sha256'],
        'review_roles': outcome['review_roles'],
        'failed_roles': outcome['failed_roles'],
        'next_owner': next_owner,
        'next_entry': next_entry,
        'dispatch_performed': False,
    }
    supervisor.record(task_id, attempt_id, event_prefix + ':review',
                      'PROGRESS', observed_at,
                      evidence_kind='PHASE_EXECUTION',
                      evidence_ref=evidence_ref,
                      payload=progress_payload)
    supervisor.record(task_id, attempt_id, event_prefix + ':handoff',
                      'HANDOFF_REQUESTED', observed_at,
                      evidence_kind='PHASE_EXECUTION',
                      evidence_ref=evidence_ref,
                      payload={'next_owner': next_owner,
                               'next_entry': next_entry,
                               'reason': phase})
    return dict(outcome, next_action='HANDOFF_ACK_REQUIRED',
                next_owner=next_owner, next_entry=next_entry,
                handoff_requested=True, dispatch_performed=False)


def acknowledge_handoff(supervisor, task_id, attempt_id, event_id,
                        observed_at, evidence_ref, new_owner, new_entry,
                        proof):
    """Acknowledge only after stop/fence/effect proof is complete."""
    if proof != TRUE_PROOF:
        raise ValueError('EXACT_HANDOFF_PROOF_REQUIRED')
    task = _task(supervisor, task_id)
    payload = dict(TRUE_PROOF)
    payload.update({'new_owner': _nonempty(new_owner, 'NEW_OWNER_REQUIRED'),
                    'new_entry': _nonempty(new_entry, 'NEW_ENTRY_REQUIRED'),
                    'lease_id': task['lease_id'],
                    'fence': task['fence'],
                    'epoch': task['epoch']})
    return supervisor.record(task_id, attempt_id, event_id,
                             'HANDOFF_ACKNOWLEDGED', observed_at,
                             evidence_kind='PHASE_EXECUTION',
                             evidence_ref=_nonempty(
                                 evidence_ref, 'HANDOFF_EVIDENCE_REQUIRED'),
                             payload=payload)


def record_terminal(supervisor, task_id, attempt_id, event_id, observed_at,
                    evidence_ref, state, artifact_sha256, next_action,
                    completion_evidence):
    """Persist terminal evidence; delivery remains pending in durable outbox."""
    if state not in ('SUCCESS','FAILURE','CANCELLED','HOLD',
                     'CAPABILITY_UNAVAILABLE'):
        raise ValueError('TERMINAL_STATE_REQUIRED')
    payload = {
        'state': state,
        'artifact_sha256': artifact_sha256,
        'writer_stopped': True,
        'effects_reconciled': True,
        'next_action': _nonempty(next_action, 'NEXT_ACTION_REQUIRED'),
        'completion_evidence': completion_evidence,
    }
    result = supervisor.record(task_id, attempt_id, event_id, 'TERMINAL',
                               observed_at,
                               evidence_kind='PHASE_EXECUTION',
                               evidence_ref=_nonempty(
                                   evidence_ref, 'TERMINAL_EVIDENCE_REQUIRED'),
                               payload=payload)
    return dict(result, closed_loop_state=closed_loop_status(
        supervisor, task_id)['state'])


def acknowledge_outbox(supervisor, outbox_id, observed_at):
    result = supervisor.outbox_result(outbox_id, True, now=observed_at)
    row = supervisor.db.execute(
        'SELECT task_id FROM outbox WHERE outbox_id=?', (outbox_id,)).fetchone()
    if row is None:
        raise KeyError(outbox_id)
    return dict(result, closed_loop_state=closed_loop_status(
        supervisor, row['task_id'])['state'])


def closed_loop_status(supervisor, task_id):
    """SUCCESS is complete only after every durable terminal delivery ACK."""
    task = _task(supervisor, task_id)
    rows = list(supervisor.db.execute(
        'SELECT delivered_at,dead_lettered_at FROM outbox WHERE task_id=?',
        (task_id,)))
    if any(row['dead_lettered_at'] is not None for row in rows):
        return {'state': 'HOLD_OUTBOX_DEAD_LETTER',
                'task_state': task['state']}
    pending = sum(1 for row in rows if row['delivered_at'] is None)
    if task['state'] == 'SUCCESS' and rows and pending == 0:
        return {'state': 'DONE', 'task_state': task['state'],
                'pending_outbox': 0}
    if task['state'] in ('FAILURE','CANCELLED','HOLD',
                         'CAPABILITY_UNAVAILABLE'):
        return {'state': 'TERMINAL_NOT_SUCCESS',
                'task_state': task['state'],
                'pending_outbox': pending}
    if task['state'] == 'SUCCESS':
        return {'state': 'WAITING_OUTBOX_ACK',
                'task_state': task['state'],
                'pending_outbox': pending}
    if task['state'] == 'HANDOFF_PENDING':
        return {'state': 'WAITING_HANDOFF_ACK',
                'task_state': task['state']}
    return {'state': 'IN_PROGRESS', 'task_state': task['state']}
