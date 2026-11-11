"""Aggregate one complete cumulative sample per run; no model polling."""
import re

COUNTERS = ('model_calls', 'input_tokens', 'output_tokens', 'cpu_seconds', 'memory_mib')


def usage_projection(samples):
    if not isinstance(samples, list) or len(samples) > 10000:
        raise ValueError('INVALID_USAGE_INPUT')
    seen = {}; reasons = set(); totals = dict.fromkeys(COUNTERS, 0)
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {'run_id', 'provider', 'counters', 'evidence_sha256'}:
            raise ValueError('INVALID_USAGE_SAMPLE')
        run = sample['run_id']; provider = sample['provider']; evidence = sample['evidence_sha256']
        if (not isinstance(run, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', run)
                or provider not in ('XUANJUN', 'TENANT', 'DEDICATED_CUSTOMER', 'INTERNAL', 'UNKNOWN')):
            raise ValueError('INVALID_USAGE_IDENTITY')
        if run in seen:
            if seen[run] != sample:
                raise ValueError('CONFLICTING_RUN_SAMPLE')
            continue
        seen[run] = dict(sample)
        if provider == 'UNKNOWN': reasons.add('UNKNOWN_PROVIDER')
        valid_evidence = isinstance(evidence, str) and re.fullmatch('[a-f0-9]{64}', evidence)
        if not valid_evidence: reasons.add('MISSING_USAGE_EVIDENCE')
        counters = sample['counters']
        if not isinstance(counters, dict) or set(counters) != set(COUNTERS):
            raise ValueError('INVALID_COUNTER_SCHEMA')
        for key in COUNTERS:
            value = counters[key]
            if value is not None and (type(value) is not int or not 0 <= value <= 2 ** 63 - 1):
                raise ValueError('INVALID_COUNTER')
            if value is None or not valid_evidence:
                totals[key] = None; reasons.add('UNKNOWN_' + key.upper())
            elif totals[key] is not None:
                # Memory is summed per-run peak, a conservative bound, not concurrent usage.
                totals[key] += value
                if totals[key] > 2 ** 63 - 1: raise ValueError('COUNTER_OVERFLOW')
    if not samples:
        totals = dict.fromkeys(COUNTERS, None); reasons.add('NO_USAGE_EVIDENCE')
    return {'schema': 'RUN_USAGE_PROJECTION_V1', 'totals': totals,
            'run_count': len(seen), 'reasons': sorted(reasons),
            'status': 'HOLD' if reasons else 'SUPPLIED_USAGE_EVIDENCED',
            'quota_remaining': None, 'amount': None, 'execution_granted': False,
            'completeness': 'CALLER_RUN_INVENTORY_REQUIRED',
            'memory_semantics': 'SUM_OF_RUN_PEAKS_NOT_CONCURRENT',
            'native_chat_quota_attribution': 'UNKNOWN'}
