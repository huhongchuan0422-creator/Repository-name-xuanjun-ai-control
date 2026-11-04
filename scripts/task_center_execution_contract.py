"""Read-only P2/P3 receipt mapping contract for the TEST_ONLY task center.

It validates an already-observed external receipt against the canonical task
and returns a normalized fact.  It never writes, dispatches, acknowledges, or
claims authority; production adapters remain NOT_IMPLEMENTED.
"""
from __future__ import print_function

from reusable_task_gateway import _text


PHASES = frozenset(('SENT', 'ACK', 'RESULT', 'ACCEPTANCE'))
SOURCES = frozenset(('P2', 'P3'))


class ExternalReceiptContract(object):
    def __init__(self, gateway, context):
        self.gateway = gateway
        self.context = context

    def normalize(self, value):
        required = {'source', 'tenant_id', 'task_id', 'attempt_id',
                    'input_version', 'event_id', 'phase', 'status',
                    'evidence_ref', 'permission_scope'}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError('EXACT_EXTERNAL_RECEIPT_REQUIRED')
        if value['source'] not in SOURCES:
            raise ValueError('P2_P3_SOURCE_REQUIRED')
        if value['phase'] not in PHASES:
            raise ValueError('CANONICAL_RECEIPT_PHASE_REQUIRED')
        tenant = self.gateway.tenants.verify(self.context)
        if value['tenant_id'] != tenant:
            raise ValueError('CROSS_TENANT_RECEIPT_REJECTED')
        self.gateway.assert_task_context(self.context, value['task_id'])
        metadata = self.gateway.db.execute('''SELECT input_version FROM
          gateway_task_metadata WHERE task_id=?''',
          (value['task_id'],)).fetchone()
        if metadata['input_version'] != value['input_version']:
            raise ValueError('INPUT_VERSION_MISMATCH')
        for name in required - {'source', 'phase', 'tenant_id'}:
            _text(value[name], name)
        return {
            'source': value['source'], 'tenant_id': tenant,
            'task_id': value['task_id'], 'attempt_id': value['attempt_id'],
            'input_version': value['input_version'],
            'event_id': value['event_id'], 'phase': value['phase'],
            'status': value['status'], 'evidence_ref': value['evidence_ref'],
            'permission_scope': value['permission_scope'],
            'mapping_state': 'VALIDATED_NOT_CONSUMED',
            'production_adapter': 'NOT_IMPLEMENTED',
        }
