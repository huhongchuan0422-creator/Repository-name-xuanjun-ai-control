"""Read-only digital-twin projection over the canonical task-center ledger.

The projection deliberately contains no mutation or dispatch capability.  It
re-indexes the same task records for project, node and AI views and keeps
missing external domains explicit instead of manufacturing a second truth.
"""
from __future__ import print_function

import json


UNKNOWN = 'UNKNOWN'

FIELD_CONTRACT = {
    'identity': ['tenant_id', 'project_id', 'requirement_id',
                 'baseline_version', 'page_id', 'module_id', 'node_id',
                 'task_id', 'attempt_id', 'role_id', 'role_instance_id',
                 'run_id', 'session_id', 'process_id', 'writer_epoch'],
    'evidence': ['state', 'state_source', 'occurred_at', 'observed_at',
                 'last_heartbeat_at', 'last_progress_at', 'source_ref',
                 'source_version', 'event_id', 'idempotency_key',
                 'commit_sha', 'tree_sha', 'artifact_sha256', 'evidence_ref',
                 'test_ref', 'review_ref', 'install_ref', 'acceptance_ref',
                 'blocker', 'next_action', 'responsible_party'],
    'permission': ['actor_id', 'actor_kind', 'permission_scope',
                   'tenant_membership', 'project_membership',
                   'confirmation_kind', 'authorization_ref'],
}

EVENT_CONTRACT = [
    'REQUIREMENT_CONFIRMED', 'UI_BASELINE_CONFIRMED', 'TASK_CREATED',
    'DISPATCH_SENT', 'EXECUTOR_ACK', 'PROCESS_STARTED',
    'HEARTBEAT_OBSERVED', 'PROGRESS_EVIDENCED', 'ARTIFACT_SUBMITTED',
    'TEST_RECORDED', 'REVIEW_RECORDED', 'INSTALL_RECORDED',
    'ACCEPTANCE_RECORDED', 'PROCESS_EXITED', 'SIDE_EFFECT_RECONCILED',
    'WRITER_RELEASED', 'RESUME_STARTED', 'RESUME_SUCCEEDED', 'RESUME_FAILED',
]

EXTENSION_CONTRACTS = {
    'project_delivery': {
        'reader': 'project_delivery_contract.build_project_delivery_projection',
        'producer': 'Customer Project Center / CRM',
        'status': 'NOT_CONNECTED',
        'mutation': 'ORIGINAL_SERVICE_ONLY',
    },
    'mcp_development_closure': {
        'reader': 'mcp_development_closure.evaluate_closure',
        'producer': ('GatewayKernel / ModelControl / trusted process observer '
                     '/ live provider receipt'),
        'status': 'PARTIALLY_CONNECTED',
        'missing_producers': [
            'TRUSTED_PROCESS_OBSERVER', 'LIVE_PROVIDER_RECEIPT'],
        'mutation': 'NONE',
    },
    'supervision_recovery': {
        'reader': 'digital_twin_supervision.evaluate_supervision',
        'producer': ('Task Supervisor / GatewayKernel / trusted process '
                     'observer'),
        'status': 'PARTIALLY_CONNECTED',
        'missing_producers': ['TRUSTED_PROCESS_OBSERVER'],
        'mutation': 'ORIGINAL_SERVICE_ONLY',
    },
}


def _json(value, fallback):
    if value in (None, ''):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _task_display_state(task, candidate, events):
    """Return a UI state only when canonical evidence supports it."""
    runtime = task.get('runtime_status') or task.get('state') or UNKNOWN
    if runtime == 'LIVENESS_UNKNOWN' or task.get('effects_reconciled') == UNKNOWN:
        return UNKNOWN
    if task.get('blocker') or runtime in (
            'HOLD', 'FAILURE', 'CANCELLED', 'CAPABILITY_UNAVAILABLE',
            'WAITING_DEPENDENCY', 'WAITING_AUTHORIZATION'):
        return 'BLOCKED'
    kinds = {item.get('kind') for item in events}
    if 'RESUME_STARTED' in kinds and not ({'RESUME_SUCCEEDED',
                                           'RESUME_FAILED'} & kinds):
        return 'RECOVERING'
    candidate_state = candidate.get('state') if candidate else None
    if candidate_state in ('SUBMITTED', 'QA_PASSED', 'SECURITY_PASSED',
                           'REVIEW_PASSED'):
        return 'PENDING_REVIEW'
    if candidate_state in ('ACCEPTED', 'DELIVERED') or runtime in (
            'SUCCESS', 'COMPLETED'):
        return 'COMPLETE'
    if any(kind in kinds for kind in ('TEST_STARTED', 'TEST_PROGRESS',
                                      'TEST_COMPLETED')):
        return 'TESTING'
    if runtime in ('STARTED', 'RUNNING'):
        return 'EXECUTING'
    if runtime == 'RECEIVED':
        return 'ACCEPTED'
    if runtime == 'READY':
        return 'PENDING_CLAIM'
    return UNKNOWN


def _animation_allowed(display_state, task, events):
    if display_state not in ('EXECUTING', 'TESTING', 'RECOVERING'):
        return False
    if task.get('last_real_progress_at') is not None:
        return True
    return any(item.get('evidence_ref') not in (None, '', UNKNOWN)
               for item in events)


def _latest_event(events, kinds):
    candidates = [item for item in events if item.get('kind') in kinds]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (
        item.get('observed_at') or 0, item.get('event_id') or ''))


def _event_ref(events, kinds):
    event = _latest_event(events, kinds)
    if event is None:
        return UNKNOWN
    return event.get('evidence_ref') or UNKNOWN


def build_projection(task_projection, model_projection):
    """Build one immutable multi-view document from existing projections."""
    tenant_id = task_projection['tenant_id']
    timeline = list(task_projection.get('timeline') or [])
    events_by_task = {}
    for event in timeline:
        events_by_task.setdefault(event.get('task_id'), []).append(event)

    candidates_by_attempt = {}
    for candidate in model_projection.get('candidates') or []:
        key = (candidate.get('task_id'), candidate.get('attempt_id'))
        current = candidates_by_attempt.get(key)
        if current is None or ((candidate.get('updated_at') or 0),
                               candidate.get('candidate_id') or '') > (
                                   (current.get('updated_at') or 0),
                                   current.get('candidate_id') or ''):
            candidates_by_attempt[key] = candidate

    reviews_by_candidate = {}
    for review in model_projection.get('candidate_reviews') or []:
        reviews_by_candidate.setdefault(review.get('candidate_id'), []).append(
            review)

    assignments = list(model_projection.get('assignments') or [])
    requests = {item.get('request_id'): item
                for item in model_projection.get('requests') or []}
    tasks = []
    evidence = []
    for source in task_projection.get('tasks') or []:
        task = dict(source)
        historical_events = events_by_task.get(task['task_id'], [])
        task_events = [item for item in historical_events
                       if item.get('attempt_id') == task.get('attempt_id')]
        candidate = candidates_by_attempt.get(
            (task['task_id'], task.get('attempt_id')))
        candidate_reviews = reviews_by_candidate.get(
            (candidate or {}).get('candidate_id'), [])
        display_state = _task_display_state(task, candidate, task_events)
        review_ref = UNKNOWN
        if candidate_reviews:
            latest_review = max(candidate_reviews, key=lambda item: (
                item.get('observed_at') or 0, item.get('review_id') or ''))
            review_ref = latest_review.get('review_id') or UNKNOWN
        acceptance_ref = _event_ref(task_events, {'ACCEPTANCE_RECORDED'})
        if (acceptance_ref == UNKNOWN and candidate and
                candidate.get('state') in ('ACCEPTED', 'DELIVERED')):
            acceptance_ref = candidate.get('candidate_id') or UNKNOWN
        task.update({
            'display_state': display_state,
            'animation_allowed': _animation_allowed(display_state, task,
                                                     task_events),
            'heartbeat_state': UNKNOWN,
            'last_heartbeat_at': UNKNOWN,
            'artifact_sha256': (candidate or {}).get('artifact_sha256',
                                                     UNKNOWN),
            'review_state': (candidate or {}).get('state', UNKNOWN),
            'requirement_id': UNKNOWN,
            'requirement_source_ref': UNKNOWN,
            'baseline_version': task.get('input_version') or UNKNOWN,
            'confirmed_ui_version': UNKNOWN,
            'page_id': UNKNOWN,
            'source_commit': UNKNOWN,
            'source_tree': UNKNOWN,
            'test_ref': _event_ref(task_events,
                                   {'TEST_RECORDED', 'TEST_COMPLETED'}),
            'review_ref': review_ref,
            'install_ref': _event_ref(task_events, {'INSTALL_RECORDED'}),
            'acceptance_ref': acceptance_ref,
            'current_responsible_party': (task.get('responsible_party') or
                                          UNKNOWN),
            'state_source': ('candidate:' + candidate['candidate_id']
                             if candidate else
                             'task-runtime:' +
                             (task.get('runtime_status') or UNKNOWN)),
            'source_ref': 'canonical-task-center://tasks/' + task['task_id'],
            'source_version': task.get('checkpoint_sha256') or UNKNOWN,
        })
        tasks.append(task)
        for event in historical_events:
            evidence.append({
                'evidence_id': event.get('event_id') or UNKNOWN,
                'task_id': task['task_id'],
                'attempt_id': event.get('attempt_id') or UNKNOWN,
                'event_id': event.get('event_id') or UNKNOWN,
                'kind': event.get('kind') or UNKNOWN,
                'evidence_kind': event.get('evidence_kind') or UNKNOWN,
                'evidence_ref': event.get('evidence_ref') or UNKNOWN,
                'occurred_at': event.get('observed_at'),
                'producer': 'Task Supervisor events',
            })
        if candidate:
            evidence.append({
                'evidence_id': candidate.get('candidate_id') or UNKNOWN,
                'task_id': task['task_id'],
                'attempt_id': candidate.get('attempt_id') or UNKNOWN,
                'event_id': UNKNOWN,
                'kind': 'ARTIFACT_CANDIDATE',
                'evidence_kind': 'ARTIFACT_SHA256',
                'evidence_ref': candidate.get('artifact_sha256') or UNKNOWN,
                'occurred_at': candidate.get('updated_at'),
                'producer': 'ModelControl delivery_candidates',
            })

    task_ids = {item['task_id'] for item in tasks}
    ai_instances = []
    for source in model_projection.get('instances') or []:
        instance = dict(source)
        instance_assignments = [item for item in assignments
                                if item.get('principal_id') ==
                                instance.get('instance_id') and any(
                                  task['task_id'] == item.get('task_id') and
                                  task.get('attempt_id') ==
                                  item.get('attempt_id') for task in tasks)]
        linked_task_ids = sorted({item.get('task_id')
                                  for item in instance_assignments
                                  if item.get('task_id') in task_ids})
        request = requests.get(instance.get('current_request_id')) or {}
        linked_tasks = [task for task in tasks
                        if task['task_id'] in linked_task_ids]
        bound_task = linked_tasks[0] if len(linked_tasks) == 1 else {}
        progress_values = [task.get('last_real_progress_at')
                           for task in linked_tasks
                           if task.get('last_real_progress_at') is not None]
        ai_instances.append({
            'role_instance_id': instance.get('instance_id') or UNKNOWN,
            'role_id': instance.get('role_id') or UNKNOWN,
            'role_version': instance.get('role_version') or UNKNOWN,
            'state': instance.get('state') or UNKNOWN,
            'desired_state': instance.get('desired_state') or UNKNOWN,
            'task_ids': linked_task_ids,
            'current_request_id': instance.get('current_request_id') or UNKNOWN,
            'run_id': bound_task.get('run_id') or UNKNOWN,
            'session_id': bound_task.get('session_id') or UNKNOWN,
            'process_id': UNKNOWN,
            'writer_epoch': bound_task.get('epoch') or UNKNOWN,
            'last_heartbeat_at': request.get('last_heartbeat') or UNKNOWN,
            'last_progress_at': (max(progress_values) if progress_values
                                 else UNKNOWN),
            'checkpoint': _json(instance.get('last_checkpoint_json'), UNKNOWN),
            'source_ref': ('canonical-task-center://role_instances/' +
                           (instance.get('instance_id') or UNKNOWN)),
            'observed_at': instance.get('updated_at'),
        })

    project_index = {}
    node_index = {}
    project_node_index = {}
    for task in tasks:
        project_index.setdefault(task['project_id'], []).append(task['task_id'])
        node_index.setdefault(task['node_id'], []).append(task['task_id'])
        project_node_index.setdefault(task['project_id'] + '::' +
                                      task['node_id'], []).append(
                                          task['task_id'])
    ai_index = {item['role_instance_id']: item['task_ids']
                for item in ai_instances}
    projects = [{'project_id': key,
                 'task_ids': sorted(value),
                 'node_ids': sorted({task['node_id'] for task in tasks
                                     if task['task_id'] in value}),
                 'customer_id': UNKNOWN,
                 'requirement_id': UNKNOWN,
                 'confirmed_version': UNKNOWN,
                 'source_ref': 'canonical-task-center://projects/' + key}
                for key, value in sorted(project_index.items())]
    nodes = [{'node_id': key.split('::', 1)[1],
              'project_id': key.split('::', 1)[0],
              'task_ids': sorted(value),
              'source_ref': ('canonical-task-center://projects/' +
                             key.split('::', 1)[0] + '/nodes/' +
                             key.split('::', 1)[1])}
             for key, value in sorted(project_node_index.items())]

    return {
        'schema': 1,
        'mode': task_projection.get('mode', 'TEST_ONLY'),
        'tenant_id': tenant_id,
        'observed_at': task_projection.get('observed_at'),
        'permissions': {
            'read_role': 'TASK_CENTER_ADMIN',
            'mutation': 'NONE',
            'action_redirect': 'ORIGINAL_SERVICE_ONLY',
        },
        'field_contract': FIELD_CONTRACT,
        'event_contract': {
            'types': EVENT_CONTRACT,
            'confirmation_kinds': ['customer', 'requester', 'owner'],
            'ai_may_confirm': False,
            'sent_ack_heartbeat_are_completion': False,
        },
        'extension_contracts': EXTENSION_CONTRACTS,
        'sources': [
            {'producer': 'Task Supervisor + GatewayKernel',
             'interface': '/api/projection', 'status': 'CONNECTED'},
            {'producer': 'ModelControl',
             'interface': '/api/admin/model-control', 'status': 'CONNECTED'},
            {'producer': 'Identity/CRM/Customer Project Center',
             'interface': UNKNOWN, 'status': 'NOT_CONNECTED'},
            {'producer': 'P2/P3 controlled installer',
             'interface': UNKNOWN, 'status': 'NOT_CONNECTED'},
        ],
        'records': {
            'projects': projects,
            'nodes': nodes,
            'tasks': tasks,
            'ai_instances': ai_instances,
            'events': timeline,
            'evidence': evidence,
        },
        # Views contain references only.  They never duplicate task state.
        'views': {
            'project_task_ids': {key: sorted(value)
                                 for key, value in sorted(project_index.items())},
            'node_task_ids': {key: sorted(value)
                              for key, value in sorted(node_index.items())},
            'project_node_task_ids': {
                key: sorted(value)
                for key, value in sorted(project_node_index.items())},
            'ai_task_ids': ai_index,
        },
        'integration_boundaries': task_projection.get(
            'integration_boundaries') or [],
        'gaps': [
            'CUSTOMER_PROJECT_IDENTITY_ADAPTER_NOT_CONNECTED',
            'PAGE_BASELINE_AND_FEEDBACK_ADAPTER_NOT_CONNECTED',
            'SESSION_PROCESS_LIVENESS_ADAPTER_NOT_CONNECTED',
            'P2_P3_INSTALL_RECEIPT_ADAPTER_NOT_CONNECTED',
        ],
        'production_status': 'NOT_IMPLEMENTED',
    }
