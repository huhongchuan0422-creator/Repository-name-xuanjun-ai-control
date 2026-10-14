"""Authenticated inventory completeness for display, never controller authority."""
from foundation_integration import bound_receipt, digest
from task_cost_projection import project_costs
from run_usage_projection import usage_projection


def _identity(kind, item):
    keys = ('component_id', 'currency', 'kind') if kind == 'costs' else ('run_id', 'provider')
    if not isinstance(item, dict) or not set(keys) <= set(item):
        raise ValueError('INVALID_INVENTORY_ITEM')
    values = tuple(item[key] for key in keys)
    if any(not isinstance(value, str) for value in values):
        raise ValueError('INVALID_INVENTORY_IDENTITY')
    return values


def complete_producer_view(kind, binding, inventory_envelope, records_envelope,
                           inventory_verifier, records_verifier, now):
    """Consume independently authenticated existing controller inventory.

    Both verifier functions are trusted-runtime dependencies, never uploaded
    keys/callbacks. Controller inventory authentication must certify source,
    issuer role, scope and revision, not merely cryptographic validity.
    This pure helper neither discovers nor creates that inventory. Missing
    inventory, omitted records or stale/rebound evidence cannot become complete.
    """
    if kind not in ('costs', 'usage'):
        raise ValueError('INVALID_PRODUCER_KIND')
    try:
        inventory = bound_receipt(kind, binding, inventory_envelope, inventory_verifier, now)
        data = bound_receipt(kind, binding, records_envelope, records_verifier, now)
        if (not isinstance(inventory, dict) or set(inventory) != {'type', 'revision', 'items'}
                or inventory['type'] != 'CANONICAL_PRODUCER_INVENTORY'
                or type(inventory['revision']) is not int or not 1 <= inventory['revision'] <= 2 ** 63 - 1
                or not isinstance(inventory['items'], list) or not 1 <= len(inventory['items']) <= 10000):
            raise ValueError('COMPLETE_INVENTORY_REQUIRED')
        if (not isinstance(data, dict) or set(data) != {'type', 'inventory_sha256', 'revision', 'complete', 'records'}
                or data['type'] != 'CANONICAL_PRODUCER_RECORDS'
                or data['inventory_sha256'] != digest(inventory)
                or type(data['revision']) is not int or data['revision'] != inventory['revision']
                or data['complete'] is not True
                or not isinstance(data['records'], list) or not 1 <= len(data['records']) <= 10000):
            raise ValueError('RECORDS_INVENTORY_BINDING_REQUIRED')
        keys = {'component_id', 'currency', 'kind'} if kind == 'costs' else {'run_id', 'provider'}
        expected = set()
        for item in inventory['items']:
            if not isinstance(item, dict) or set(item) != keys:
                raise ValueError('INVALID_INVENTORY_DESCRIPTOR')
            identity = _identity(kind, item)
            if identity in expected:
                raise ValueError('DUPLICATE_INVENTORY_DESCRIPTOR')
            expected.add(identity)
        observed = {_identity(kind, item) for item in data['records']}
        if observed != expected:
            raise ValueError('PARTIAL_OR_EXTRA_PRODUCER_RECORDS')
        # Original modules validate schemas, typed values, task identity,
        # conflicting duplicate records, totals and UNKNOWN behavior.
        result = (project_costs(binding['task_id'], data['records']) if kind == 'costs'
                  else usage_projection(data['records']))
        result['task_inventory_status'] = 'AUTHENTICATED_DECLARED_INVENTORY_MATCH'
        result['inventory_sha256'] = digest(inventory)
        result['inventory_revision'] = inventory['revision']
        result['live_authority'] = 'EXISTING_CONTROLLER_ATOMIC_RECHECK_REQUIRED'
        result['execution_granted'] = False
        result['release_granted'] = False
        return result
    except (ValueError, TypeError, KeyError, RecursionError):
        return {'status': 'HOLD', 'reasons': ['UNVERIFIED_OR_INCOMPLETE_PRODUCER_INVENTORY'],
                'task_inventory_status': 'NOT_VERIFIED', 'execution_granted': False,
                'release_granted': False}
