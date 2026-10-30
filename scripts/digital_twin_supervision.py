"""Pure read/decision layer for digital-twin supervision and recovery.

This module deliberately owns no table, writer, timer or executor.  It accepts
one already-authorized snapshot from the existing Task Supervisor/Gateway and
returns a deterministic decision.  A caller must send every mutation back to
the original service and re-check its fence/epoch there.
"""
from __future__ import print_function

import hashlib
import json
import math


UNKNOWN = 'UNKNOWN'
TERMINAL_STATES = frozenset(('SUCCESS', 'FAILURE', 'CANCELLED', 'HOLD',
                             'CAPABILITY_UNAVAILABLE'))
ACTIVE_STATES = frozenset(('RECEIVED', 'STARTED', 'RUNNING',
                           'HANDOFF_PENDING'))
START_KINDS = frozenset(('STARTED', 'PROCESS_STARTED'))
PROGRESS_KINDS = frozenset(('PROGRESS', 'PROGRESS_EVIDENCED'))
HEARTBEAT_KINDS = frozenset(('HEARTBEAT', 'HEARTBEAT_OBSERVED'))
ACK_KINDS = frozenset(('RECEIVED', 'EXECUTOR_ACK'))
EXIT_KINDS = frozenset(('PROCESS_EXITED',))
TERMINAL_KINDS = frozenset(('TERMINAL', 'TERMINAL_RECEIPT'))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _known(value):
    return value not in (None, '', UNKNOWN)


def _event_time(event):
    value = event.get('observed_at', event.get('occurred_at'))
    return value if _finite(value) else None


def _latest(events, kinds):
    selected = [item for item in events if item.get('kind') in kinds]
    if not selected:
        return None
    return max(selected, key=lambda item: (_event_time(item) or -1,
                                           item.get('event_id') or ''))


def _identity_matches(task, execution):
    expected = {
        'run_id': task.get('run_id'),
        'session_id': task.get('session_id'),
        'writer_epoch': task.get('epoch'),
    }
    mismatches = []
    for name, expected_value in expected.items():
        observed = execution.get(name)
        if _known(observed) and _known(expected_value) and observed != expected_value:
            mismatches.append(name)
    return expected, mismatches


def _checkpoint(snapshot, task):
    matching = [item for item in snapshot.get('checkpoints', [])
                if item.get('attempt_id') == task.get('attempt_id')]
    if not matching:
        return None
    return max(matching, key=lambda item: (item.get('created_at') or -1,
                                           item.get('checkpoint_id') or ''))


def _unknown_effects(snapshot, task):
    unresolved = []
    malformed = []
    for effect in snapshot.get('unknown_effects', []):
        if effect.get('state') not in ('UNKNOWN', 'DISPATCHING'):
            continue
        required = ('task_id', 'attempt_id', 'operation_id', 'resource_key')
        if any(not _known(effect.get(name)) for name in required):
            malformed.append(effect)
            continue
        if (effect['task_id'] != task.get('task_id')
                or effect['attempt_id'] != task.get('attempt_id')):
            malformed.append(effect)
            continue
        unresolved.append(effect)
    return unresolved, malformed


def _action_id(task, decision, checkpoint=None):
    body = {
        'task_id': task.get('task_id', UNKNOWN),
        'attempt_id': task.get('attempt_id', UNKNOWN),
        'epoch': task.get('epoch', UNKNOWN),
        'decision': decision,
        'checkpoint_id': (checkpoint or {}).get('checkpoint_id', UNKNOWN),
    }
    return hashlib.sha256(_canonical(body).encode('utf-8')).hexdigest()


def evaluate_supervision(snapshot, now, progress_max_age=600,
                         supervisor_max_age=300):
    """Return a deterministic, read-only supervision/recovery decision.

    The result never authorizes a write.  ``recovery.allowed`` only means the
    supplied facts are eligible to be re-validated by the original Gateway,
    Fence and executor admission path.
    """
    if not isinstance(snapshot, dict) or not _finite(now):
        raise ValueError('EXACT_SNAPSHOT_AND_FINITE_TIME_REQUIRED')
    if (not _finite(progress_max_age) or progress_max_age <= 0
            or not _finite(supervisor_max_age) or supervisor_max_age <= 0):
        raise ValueError('POSITIVE_SUPERVISION_THRESHOLDS_REQUIRED')
    task = snapshot.get('task')
    if not isinstance(task, dict) or not _known(task.get('task_id')):
        raise ValueError('CANONICAL_TASK_REQUIRED')
    events = list(snapshot.get('events') or [])
    # Old-attempt evidence may coexist in the canonical ledger.  It can be
    # displayed elsewhere, but it cannot upgrade the current attempt.
    events = [item for item in events
              if item.get('task_id', task['task_id']) == task['task_id']
              and item.get('attempt_id', task.get('attempt_id')) ==
              task.get('attempt_id')]
    execution = dict(snapshot.get('execution') or {})
    supervisor = dict(snapshot.get('supervisor') or {})

    expected, mismatches = _identity_matches(task, execution)
    # A process observation is attributable only when both sides contain the
    # complete canonical identity.  Do not let UNKNOWN canonical fields turn
    # this into an all(empty-set) success.
    identity_complete = all(_known(value)
                            and _known(execution.get(name))
                            and execution.get(name) == value
                            for name, value in expected.items())
    checkpoint = _checkpoint(snapshot, task)
    unresolved, malformed = _unknown_effects(snapshot, task)
    last_start = _latest(events, START_KINDS)
    last_progress = _latest(events, PROGRESS_KINDS)
    last_heartbeat = _latest(events, HEARTBEAT_KINDS)
    last_ack = _latest(events, ACK_KINDS)
    last_exit = _latest(events, EXIT_KINDS)
    last_terminal = _latest(events, TERMINAL_KINDS)

    canonical_progress = task.get('last_real_progress_at')
    event_progress = _event_time(last_progress) if last_progress else None
    progress_at = max([x for x in (canonical_progress, event_progress)
                       if _finite(x)], default=None)
    heartbeat_at = _event_time(last_heartbeat) if last_heartbeat else None

    sup_heartbeat = supervisor.get('last_heartbeat_at')
    supervisor_stale = (supervisor.get('process_state') == 'PROVEN_EXITED'
                        or not _finite(sup_heartbeat)
                        or now - sup_heartbeat > supervisor_max_age)
    supervisor_status = ('STALLED_OR_UNKNOWN' if supervisor_stale
                         else 'HEARTBEAT_FRESH_PROCESS_NOT_PROVEN')

    decision = 'UNKNOWN'
    reason = 'INSUFFICIENT_CANONICAL_FACTS'
    next_action = 'RECONCILE_ORIGINAL_KEYS'
    recovery_allowed = False

    # A stale generation is rejected before interpreting its apparent result.
    if mismatches:
        decision = 'STALE_EXECUTOR_REJECTED'
        reason = 'EXECUTION_IDENTITY_OR_EPOCH_MISMATCH'
        next_action = 'REJECT_LATE_RESULT_AND_READ_CURRENT_ATTEMPT'
    elif malformed:
        decision = 'HOLD'
        reason = 'UNKNOWN_EFFECT_ORIGINAL_KEY_MISSING_OR_MISMATCHED'
        next_action = 'RECONCILE_BY_ORIGINAL_TASK_ATTEMPT_OPERATION_RESOURCE'
    elif unresolved or task.get('effects_reconciled') == UNKNOWN:
        decision = 'HOLD'
        reason = 'UNKNOWN_SIDE_EFFECTS_REQUIRE_READBACK'
        next_action = 'RECONCILE_UNKNOWN_EFFECTS_NO_REDISPATCH'
    elif (execution.get('process_state') in ('PROVEN_RUNNING', 'PROVEN_EXITED')
          and not identity_complete):
        decision = 'HOLD'
        reason = 'EXECUTION_OBSERVATION_NOT_BOUND_TO_CURRENT_IDENTITY'
        next_action = 'READ_ORIGINAL_RUN_SESSION_PROCESS_EPOCH'
    elif task.get('state') in TERMINAL_STATES:
        if last_terminal is None:
            decision = 'RESULT_MISSING'
            reason = 'TERMINAL_STATE_WITHOUT_BOUND_TERMINAL_RECEIPT'
            next_action = 'RECOVER_ORIGINAL_TERMINAL_RECEIPT'
        else:
            decision = 'COMPLETE' if task.get('state') == 'SUCCESS' else 'TERMINAL'
            reason = 'CANONICAL_TERMINAL_WITH_BOUND_RECEIPT'
            next_action = 'NONE'
    elif execution.get('process_state') == 'PROVEN_EXITED' or last_exit:
        # Exit is an observation, never an automatic failure.
        if last_terminal:
            decision = 'RESULT_MISSING'
            reason = 'PROCESS_EXITED_WITH_RECEIPT_NOT_CANONICALLY_APPLIED'
            next_action = 'RECOVER_ORIGINAL_RESULT_NO_RERUN'
        elif (task.get('state') in ACTIVE_STATES and checkpoint is not None
              and checkpoint.get('effects_state') == 'RECONCILED'
              and task.get('effects_reconciled') in (True, 'TRUE')):
            decision = 'RECOVERABLE_SAME_ATTEMPT'
            reason = 'PROVEN_EXIT_CHECKPOINT_AND_RECONCILED_EFFECTS'
            next_action = 'REQUEST_ORIGINAL_GATEWAY_RESUME_SAME_ATTEMPT'
            recovery_allowed = True
        else:
            decision = 'RESULT_MISSING'
            reason = 'PROCESS_EXITED_WITHOUT_SAFE_RESUME_EVIDENCE'
            next_action = 'RECONCILE_RESULT_CHECKPOINT_AND_EFFECTS'
    elif task.get('state') == 'RECEIVED' and last_start is None:
        decision = 'ACCEPTED_NOT_STARTED'
        reason = ('ACK_IS_NOT_START' if last_ack else
                  'RECEIPT_WITHOUT_PROCESS_START')
        next_action = 'VERIFY_ORIGINAL_EXECUTION_UNIT'
    elif task.get('state') in ('STARTED', 'RUNNING') or last_start:
        if execution.get('process_state') != 'PROVEN_RUNNING':
            decision = 'LIVENESS_UNKNOWN'
            reason = 'TASK_STATE_DOES_NOT_PROVE_PROCESS'
            next_action = 'READ_ORIGINAL_RUN_SESSION_PROCESS'
        elif progress_at is None or now - progress_at > progress_max_age:
            decision = 'STALLED_NO_PROGRESS'
            reason = 'HEARTBEAT_DOES_NOT_REFRESH_REAL_PROGRESS'
            next_action = 'INSPECT_ORIGINAL_EXECUTOR_AND_CHECKPOINT'
        else:
            decision = 'EXECUTING'
            reason = 'MATCHED_PROCESS_AND_RECENT_REAL_PROGRESS'
            next_action = 'CONTINUE_SUPERVISION'
    elif task.get('state') == 'READY':
        decision = 'PENDING_CLAIM'
        reason = 'NO_ACCEPTED_EXECUTION_ATTEMPT'
        next_action = 'ORIGINAL_GATEWAY_ADMISSION'

    action_id = None if next_action == 'NONE' else _action_id(
        task, next_action, checkpoint)
    return {
        'schema': 1,
        'mode': 'READ_ONLY_DECISION',
        'task_id': task['task_id'],
        'attempt_id': task.get('attempt_id', UNKNOWN),
        'expected_execution_identity': expected,
        'decision': decision,
        'reason': reason,
        'next_action': next_action,
        'next_action_id': action_id,
        'progress': {
            'last_real_progress_at': progress_at,
            'last_heartbeat_at': heartbeat_at,
            'heartbeat_counts_as_progress': False,
        },
        'supervisor': {
            'status': supervisor_status,
            'last_heartbeat_at': sup_heartbeat if _finite(sup_heartbeat) else UNKNOWN,
            'heartbeat_proves_process': False,
        },
        'unknown_effects': {
            'unresolved_operation_ids': sorted(
                item['operation_id'] for item in unresolved),
            'malformed_count': len(malformed),
            'redispatch_allowed': False,
        },
        'recovery': {
            'allowed': recovery_allowed,
            'same_task_id': task['task_id'],
            'same_attempt_id': task.get('attempt_id', UNKNOWN),
            'same_executor_required': True,
            'checkpoint_id': (checkpoint or {}).get('checkpoint_id', UNKNOWN),
            'original_gateway_revalidation_required': True,
            'new_writer_authority_granted': False,
        },
    }
