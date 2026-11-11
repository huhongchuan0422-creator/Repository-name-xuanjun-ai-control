"""Read-only batch view over owner_dashboard.snapshot; never authorizes actions.

Python 3.6+. Caller obtains the snapshot through the existing authenticated
Owner surface. This projection does not authenticate or refresh its input.
"""
import hashlib
import json
import math
import re


def _number(value):
    return (type(value) in (int, float) and 0 <= value <= 10 ** 15
            and math.isfinite(value))


def _text(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def build_digest(snapshot, now, limit=100, max_age=300):
    """Return bounded rows, full group counts and explicit integrity warnings.

    Identical projected task/fence rows collapse. Conflicting duplicates remain
    visible and block actionability. Input is never modified. No persistence,
    DB reads, network, notification, approval or execution is performed here.
    """
    if not _number(now) or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('INVALID_VIEW_ARGUMENT')
    if type(max_age) is not int or not 1 <= max_age <= 86400:
        raise ValueError('INVALID_MAX_AGE')
    if not isinstance(snapshot, dict):
        raise ValueError('INVALID_SNAPSHOT')
    queue = snapshot.get('human_queue')
    if not isinstance(queue, list) or len(queue) > 10000:
        raise ValueError('INVALID_HUMAN_QUEUE')
    warnings = set()
    observed = snapshot.get('observed_at')
    if not _number(observed) or observed > now or now - observed > max_age:
        warnings.add('STALE_OR_UNKNOWN_SNAPSHOT')
    if snapshot.get('source') != 'CANONICAL_LEDGER_READ_ONLY':
        warnings.add('UNEXPECTED_SOURCE')
    counts = snapshot.get('counts')
    expected = counts.get('WAITING_HUMAN') if isinstance(counts, dict) else None
    if type(expected) is not int or expected < 0 or expected != len(queue):
        warnings.add('QUEUE_COUNT_MISMATCH')
    rows = {}
    identities = {}
    invalid = 0
    for task in queue:
        if not isinstance(task, dict):
            invalid += 1
            continue
        task_id, fence = task.get('id'), task.get('fence')
        if (not _text(task_id, r'[A-Za-z0-9_.:-]{1,160}') or
                type(fence) is not int or not 0 <= fence <= 2 ** 63 - 1 or
                task.get('state') != 'WAITING_HUMAN'):
            invalid += 1
            continue
        cp = task.get('checkpoint')
        cp = cp if isinstance(cp, dict) else {}
        reason = cp.get('error_code', cp.get('reason'))
        reason = reason if _text(reason, r'[A-Z_]{1,80}') else 'UNKNOWN'
        commit = cp.get('commit', cp.get('sha'))
        commit = commit if _text(commit, r'[a-f0-9]{40}') else None
        phase = cp.get('phase')
        phase = phase if _text(phase, r'[A-Z_]{1,40}') else 'UNKNOWN'
        if phase == 'UNKNOWN' or commit is None:
            warnings.add('UNKNOWN_CHECKPOINT_EVIDENCE')
        row = {'task_id': task_id, 'fence': fence, 'reason': reason,
               'phase': phase, 'commit': commit,
               'execution_evidence': 'UNKNOWN', 'approval_granted': False}
        encoded = json.dumps(row, sort_keys=True, separators=(',', ':'))
        rows[encoded] = row
        identities.setdefault(task_id, set()).add(encoded)
    if invalid:
        warnings.add('INVALID_QUEUE_ROWS')
    conflicts = sorted(key for key, values in identities.items() if len(values) > 1)
    if conflicts:
        warnings.add('CONFLICTING_TASK_VERSIONS')
    ordered = sorted(rows.values(), key=lambda row: (row['reason'], row['task_id'],
                                                    row['fence'], row['phase'],
                                                    row['commit'] or ''))
    groups = {}
    for row in ordered:
        groups[row['reason']] = groups.get(row['reason'], 0) + 1
    if 'UNKNOWN' in groups:
        warnings.add('UNKNOWN_ACTION_REASON')
    # Identity describes the entire sanitized set, not just the display page.
    payload = {'items': ordered, 'warnings': sorted(warnings),
               'input_count': len(queue), 'invalid_count': invalid}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(',', ':')).encode('utf-8')).hexdigest()
    return {'schema': 'OWNER_ACTION_DIGEST_V1', 'digest_sha256': digest,
            'status': 'HOLD' if warnings else 'VIEW_READY',
            'warnings': sorted(warnings), 'input_count': len(queue),
            'invalid_count': invalid, 'unique_count': len(ordered),
            'duplicate_count': len(queue) - invalid - len(ordered),
            'group_counts': groups, 'items': ordered[:limit],
            'omitted_count': max(0, len(ordered) - limit),
            'conflicting_task_count': len(conflicts),
            'approval_granted': False, 'dispatch_performed': False,
            'source_authenticity': 'NOT_VERIFIED_BY_THIS_MODULE'}
