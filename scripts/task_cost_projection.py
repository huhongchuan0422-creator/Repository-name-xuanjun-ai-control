"""Pure cost evidence projection; caller authenticates canonical input."""
import re

MAX_AMOUNT = 2 ** 63 - 1


def _id(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value)


def project_costs(task_id, records):
    """Separate actual/estimated micro-unit totals; never infer absent costs.

    Each complete record represents one unique cost component. Missing actual
    evidence poisons that currency's actual total; estimates remain separate.
    No conversion, payment, revenue, margin or commission is computed.
    """
    if not _id(task_id) or not isinstance(records, list) or len(records) > 10000:
        raise ValueError('INVALID_COST_INPUT')
    groups = {}; seen = {}; warnings = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
                'task_id', 'component_id', 'currency', 'kind', 'amount_micros',
                'evidence_sha256'}:
            raise ValueError('INVALID_COST_RECORD')
        currency = record['currency']; amount = record['amount_micros']
        evidence = record['evidence_sha256']; kind = record['kind']
        if (record['task_id'] != task_id or not _id(record['component_id'])
                or not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency)
                or kind not in ('ACTUAL', 'ESTIMATE', 'UNKNOWN')
                or (amount is not None and (type(amount) is not int
                    or not 0 <= amount <= MAX_AMOUNT))
                or (evidence is not None and (not isinstance(evidence, str)
                    or not re.fullmatch('[a-f0-9]{64}', evidence)))
                or (kind == 'UNKNOWN' and (amount is not None or evidence is not None))):
            raise ValueError('INVALID_COST_RECORD')
        # One record per component+kind; contradictory duplicates are rejected.
        key = (record['component_id'], kind)
        if key in seen:
            if seen[key] != record:
                raise ValueError('CONFLICTING_COST_RECORD')
            continue
        seen[key] = dict(record)
        group = groups.setdefault(currency, {'actual_micros': 0,
            'estimate_micros': 0, 'actual_complete': True,
            'estimate_complete': True, 'record_count': 0, 'has_actual': False,
            'has_estimate': False})
        group['record_count'] += 1
        if kind == 'UNKNOWN':
            group['actual_complete'] = False
            warnings.add('UNKNOWN_ACTUAL_COST')
        else:
            prefix = 'actual' if kind == 'ACTUAL' else 'estimate'
            group['has_' + prefix] = True
            if amount is None or evidence is None:
                group[prefix + '_complete'] = False
                warnings.add('MISSING_' + kind + '_EVIDENCE')
            else:
                group[prefix + '_micros'] += amount
                if group[prefix + '_micros'] > MAX_AMOUNT:
                    raise ValueError('COST_TOTAL_OVERFLOW')
    for group in groups.values():
        for prefix in ('actual', 'estimate'):
            if not group.pop('has_' + prefix) or not group[prefix + '_complete']:
                group[prefix + '_micros'] = None
                group[prefix + '_complete'] = False
    if not groups:
        warnings.add('NO_COST_EVIDENCE')
    if any(not g['actual_complete'] for g in groups.values()):
        warnings.add('ACTUAL_TOTAL_INCOMPLETE')
    return {'schema': 'TASK_COST_PROJECTION_V1', 'currencies': groups,
            'warnings': sorted(warnings), 'status': 'HOLD' if warnings else 'VIEW_READY',
            'financial_completeness': 'CALLER_COMPONENT_INVENTORY_REQUIRED',
            'source_authenticity': 'CALLER_REQUIRED', 'payment_granted': False}
