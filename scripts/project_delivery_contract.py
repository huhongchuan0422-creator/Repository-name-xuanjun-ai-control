"""Website project/page delivery read contract for the existing task center.

This module is deliberately read-only.  It validates already-observed Customer
Project Center facts against GatewayKernel tenant/project/input-version
metadata and builds a projection.  It does not write CRM data, approve a page,
deliver a project, or create another ledger.
"""
from __future__ import print_function

from reusable_task_gateway import _text


UNKNOWN = 'UNKNOWN'
NOT_CONNECTED = 'NOT_CONNECTED'

SOURCE_TO_CANONICAL = {
    'PAGE_UI_CONFIRMED': 'UI_BASELINE_CONFIRMED',
    'CUSTOMER_COMMENT_RECORDED': 'PAGE_COMMENT_RECORDED',
    'PAGE_CHANGE_REQUESTED': 'PAGE_CHANGE_REQUESTED',
    'PAGE_RECTIFICATION_SUBMITTED': 'PAGE_RECTIFICATION_SUBMITTED',
    'PAGE_RECHECK_RECORDED': 'PAGE_RECHECK_RECORDED',
    'PAGE_ACCEPTED': 'PAGE_ACCEPTED',
    'PAGE_REJECTED': 'PAGE_REJECTED',
    'PROJECT_DELIVERED': 'PROJECT_DELIVERED',
    'SHOWCASE_REFERENCE_ALLOWED': 'SHOWCASE_REFERENCE_ALLOWED',
}

CONFIRMATION_EVENTS = frozenset((
    'PAGE_UI_CONFIRMED', 'PAGE_ACCEPTED', 'PAGE_REJECTED',
    'PROJECT_DELIVERED', 'SHOWCASE_REFERENCE_ALLOWED'))
CONFIRMERS = frozenset(('customer', 'requester', 'owner'))
ACTOR_KINDS = CONFIRMERS | frozenset(('developer', 'reviewer', 'system'))

EVENT_FIELDS = frozenset((
    'source', 'tenant_id', 'project_id', 'page_id', 'ui_version',
    'task_id', 'attempt_id', 'event_id', 'event_type', 'occurred_at',
    'actor_kind', 'actor_id', 'permission_scope', 'authorization_ref',
    'evidence_ref', 'change_id', 'delivery_id', 'acceptance_id',
    'content_ref', 'showcase_allowed'))


class ProjectDeliveryContract(object):
    """Validate external facts without consuming or persisting them."""

    def __init__(self, gateway, context):
        self.gateway = gateway
        self.context = context

    def normalize(self, value):
        if not isinstance(value, dict) or set(value) != EVENT_FIELDS:
            raise ValueError('EXACT_PROJECT_DELIVERY_EVENT_REQUIRED')
        if value['source'] != 'CUSTOMER_PROJECT_CENTER':
            raise ValueError('CUSTOMER_PROJECT_CENTER_SOURCE_REQUIRED')
        if value['event_type'] not in SOURCE_TO_CANONICAL:
            raise ValueError('PROJECT_DELIVERY_EVENT_TYPE_REQUIRED')
        if value['actor_kind'] not in ACTOR_KINDS:
            raise ValueError('ACTOR_KIND_REQUIRED')
        if not isinstance(value['occurred_at'], (int, float)):
            raise ValueError('OCCURRED_AT_REQUIRED')
        if not isinstance(value['showcase_allowed'], bool):
            raise ValueError('BOOLEAN_SHOWCASE_ALLOWED_REQUIRED')

        tenant_id = self.gateway.tenants.verify(self.context)
        if value['tenant_id'] != tenant_id:
            raise ValueError('CROSS_TENANT_PROJECT_EVENT_REJECTED')
        self.gateway.assert_task_context(self.context, value['task_id'])
        metadata = self.gateway.db.execute('''SELECT m.tenant_id,m.project_id,
          m.input_version,t.attempt_id FROM gateway_task_metadata m
          JOIN tasks t ON t.task_id=m.task_id WHERE m.task_id=?''',
          (value['task_id'],)).fetchone()
        if metadata is None:
            raise ValueError('TASK_METADATA_REQUIRED')
        if value['project_id'] != metadata['project_id']:
            raise ValueError('PROJECT_BINDING_MISMATCH')
        if value['ui_version'] != metadata['input_version']:
            raise ValueError('UI_VERSION_MISMATCH')
        current_attempt = metadata['attempt_id'] or UNKNOWN
        if value['attempt_id'] != current_attempt:
            raise ValueError('ATTEMPT_BINDING_MISMATCH')

        for name in EVENT_FIELDS - frozenset((
                'occurred_at', 'showcase_allowed')):
            _text(value[name], name)

        event_type = value['event_type']
        if event_type in CONFIRMATION_EVENTS:
            if value['actor_kind'] not in CONFIRMERS:
                raise ValueError('AI_OR_EXECUTOR_CANNOT_CONFIRM')
            if value['authorization_ref'] == UNKNOWN:
                raise ValueError('CONFIRMATION_AUTHORIZATION_REQUIRED')
        if event_type in ('PAGE_ACCEPTED', 'PAGE_REJECTED'):
            if value['acceptance_id'] == UNKNOWN:
                raise ValueError('PAGE_ACCEPTANCE_ID_REQUIRED')
        if event_type in ('PAGE_CHANGE_REQUESTED',
                          'PAGE_RECTIFICATION_SUBMITTED'):
            if value['change_id'] == UNKNOWN:
                raise ValueError('PAGE_CHANGE_ID_REQUIRED')
        if event_type == 'PAGE_REJECTED' and value['evidence_ref'] == UNKNOWN:
            raise ValueError('REJECTION_REASON_REFERENCE_REQUIRED')
        if event_type == 'PROJECT_DELIVERED':
            if (value['delivery_id'] == UNKNOWN or
                    value['page_id'] != 'PROJECT'):
                raise ValueError('DELIVERY_ID_REQUIRED')
        elif value['page_id'] == 'PROJECT':
            raise ValueError('PAGE_ID_REQUIRED')
        if event_type == 'SHOWCASE_REFERENCE_ALLOWED':
            if not value['showcase_allowed'] or value['content_ref'] == UNKNOWN:
                raise ValueError('EXPLICIT_SHOWCASE_REFERENCE_REQUIRED')
        elif value['showcase_allowed']:
            raise ValueError('SHOWCASE_FLAG_EVENT_MISMATCH')

        result = dict(value)
        result.update({
            'canonical_event_type': SOURCE_TO_CANONICAL[event_type],
            'mapping_state': 'VALIDATED_NOT_PERSISTED',
            'production_adapter': 'NOT_CONNECTED',
        })
        return result


def _page_key(event):
    return (event['project_id'], event['page_id'], event['ui_version'])


def _new_page(event):
    return {
        'project_id': event['project_id'],
        'page_id': event['page_id'],
        'ui_version': event['ui_version'],
        'task_id': event['task_id'],
        'attempt_id': event['attempt_id'],
        'state': UNKNOWN,
        'baseline_state': UNKNOWN,
        'acceptance_blocker': UNKNOWN,
        'change_id': UNKNOWN,
        'acceptance_id': UNKNOWN,
        'rejection_reason_ref': UNKNOWN,
        'last_event_id': event['event_id'],
        'source_ref': ('customer-project-center://projects/{0}/pages/{1}/'
                       'versions/{2}').format(event['project_id'],
                                              event['page_id'],
                                              event['ui_version']),
    }


def build_project_delivery_projection(task_projection, normalized_events=None,
                                      showcase_allowlist=None):
    """Build a read model; only validated facts may affect page state.

    The event list remains the audit trail.  Project delivery becomes effective
    only when every tracked page/version is accepted.  Showcase output contains
    opaque references that are both explicitly allowed by an authorized event
    and present in the caller-provided allowlist.
    """
    raw_events = list(normalized_events or [])
    allowlist = frozenset(showcase_allowlist or [])
    tenant_id = task_projection['tenant_id']
    task_ids = {item['task_id'] for item in task_projection.get('tasks') or []}
    by_event_id = {}
    for event in raw_events:
        if event.get('mapping_state') != 'VALIDATED_NOT_PERSISTED':
            raise ValueError('VALIDATED_PROJECT_EVENT_REQUIRED')
        if event.get('tenant_id') != tenant_id:
            raise ValueError('CROSS_TENANT_PROJECT_EVENT_REJECTED')
        if event.get('task_id') not in task_ids:
            raise ValueError('UNKNOWN_TASK_EVENT_REJECTED')
        previous = by_event_id.get(event['event_id'])
        if previous is not None and previous != event:
            raise ValueError('CONFLICTING_PROJECT_EVENT_ID')
        by_event_id[event['event_id']] = event
    events = list(by_event_id.values())
    events.sort(key=lambda item: (item['occurred_at'], item['event_id']))

    pages = {}
    delivery_results = {}
    showcase_refs = []
    for event in events:
        kind = event['canonical_event_type']
        if kind == 'PROJECT_DELIVERED':
            current_keys = [key for key in pages
                            if (key[0] == event['project_id'] and
                                key[2] == event['ui_version'])]
            accepted = (bool(current_keys) and all(
                pages[key]['baseline_state'] == 'CONFIRMED' and
                pages[key]['state'] == 'ACCEPTED'
                for key in current_keys))
            delivery_results[event['project_id']] = {
                'effective': accepted,
                'delivery_id': event['delivery_id'],
            }
            continue
        if kind == 'SHOWCASE_REFERENCE_ALLOWED':
            if event['content_ref'] in allowlist:
                showcase_refs.append({
                    'project_id': event['project_id'],
                    'content_ref': event['content_ref'],
                    'authorization_ref': event['authorization_ref'],
                    'event_id': event['event_id'],
                })
            continue
        key = _page_key(event)
        page = pages.setdefault(key, _new_page(event))
        page['last_event_id'] = event['event_id']
        page['attempt_id'] = event['attempt_id']
        if kind == 'UI_BASELINE_CONFIRMED':
            page['state'] = 'CONFIRMED'
            page['baseline_state'] = 'CONFIRMED'
            page['acceptance_blocker'] = UNKNOWN
        elif kind in ('PAGE_COMMENT_RECORDED', 'PAGE_CHANGE_REQUESTED'):
            page['state'] = 'PENDING_CHANGE'
            page['change_id'] = event['change_id']
        elif kind == 'PAGE_RECTIFICATION_SUBMITTED':
            page['state'] = 'PENDING_RECHECK'
            page['change_id'] = event['change_id']
        elif kind == 'PAGE_RECHECK_RECORDED':
            page['state'] = 'PENDING_ACCEPTANCE'
        elif kind == 'PAGE_ACCEPTED':
            if page['baseline_state'] != 'CONFIRMED':
                page['state'] = 'BLOCKED_BASELINE_UNCONFIRMED'
                page['acceptance_blocker'] = 'UI_BASELINE_NOT_CONFIRMED'
            else:
                page['state'] = 'ACCEPTED'
                page['acceptance_id'] = event['acceptance_id']
                page['acceptance_blocker'] = UNKNOWN
                page['rejection_reason_ref'] = UNKNOWN
        elif kind == 'PAGE_REJECTED':
            page['state'] = 'REJECTED'
            page['acceptance_id'] = event['acceptance_id']
            page['rejection_reason_ref'] = event['evidence_ref']

    page_records = [pages[key] for key in sorted(pages)]
    projects = {}
    for task in task_projection.get('tasks') or []:
        project = projects.setdefault(task['project_id'], {
            'project_id': task['project_id'],
            'task_ids': [],
            'active_development': True,
            'delivery_state': UNKNOWN,
            'delivery_id': UNKNOWN,
            'customer_project_source': NOT_CONNECTED,
        })
        project['task_ids'].append(task['task_id'])

    for project_id, delivery in delivery_results.items():
        project = projects[project_id]
        if delivery['effective']:
            project['active_development'] = False
            project['delivery_state'] = 'FORMALLY_DELIVERED'
            project['delivery_id'] = delivery['delivery_id']
        else:
            project['delivery_state'] = 'BLOCKED_INCOMPLETE_PAGE_ACCEPTANCE'

    for project in projects.values():
        project['task_ids'].sort()
    return {
        'schema': 1,
        'mode': task_projection.get('mode', 'TEST_ONLY'),
        'tenant_id': tenant_id,
        'permissions': {
            'read_role': 'TASK_CENTER_ADMIN',
            'mutation': 'NONE',
            'confirmation_service': 'ORIGINAL_CUSTOMER_PROJECT_CENTER_ONLY',
        },
        'source': {
            'producer': 'Identity/CRM/Customer Project Center',
            'status': (NOT_CONNECTED if not events else
                       'TEST_ONLY_VALIDATED_INPUT'),
            'production_adapter': NOT_CONNECTED,
        },
        'records': {
            'projects': [projects[key] for key in sorted(projects)],
            'page_versions': page_records,
            'events': events,
            'showcase_references': showcase_refs,
        },
        'gaps': ([] if events else [
            'CUSTOMER_PROJECT_CENTER_PRODUCER_NOT_CONNECTED',
            'PAGE_VERSION_ACCEPTANCE_FACTS_UNKNOWN']),
        'production_status': 'NOT_IMPLEMENTED',
    }
