"""Read-only resume prerequisites; never approves or resumes a task."""
import math
import re

FIELDS = ('identity_current', 'checkpoint_verified', 'old_writer_stopped',
          'old_fence_revoked', 'effects_reconciled', 'dependencies_accepted',
          'budget_available', 'owner_authorized')


def resume_view(evidence, now, max_age=300):
    if (type(now) not in (int, float) or not 0 <= now <= 10 ** 15 or not math.isfinite(now)
            or type(max_age) is not int or not 1 <= max_age <= 3600):
        raise ValueError('INVALID_RESUME_CLOCK')
    reasons = []
    if not isinstance(evidence, dict) or set(evidence) != set(FIELDS) | {'observed_at', 'binding_sha256'}:
        return {'schema': 'RESUME_PREREQUISITE_VIEW_V1', 'status': 'HOLD',
                'reasons': ['INVALID_EVIDENCE'], 'resume_granted': False}
    for field in FIELDS:
        if evidence[field] is not True:
            reasons.append('UNPROVEN_' + field.upper())
    stamp = evidence['observed_at']
    if (type(stamp) not in (int, float) or not 0 <= stamp <= now
            or not math.isfinite(stamp) or now - stamp > max_age):
        reasons.append('STALE_OR_UNKNOWN_EVIDENCE')
    digest = evidence['binding_sha256']
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        reasons.append('MISSING_VERSION_BINDING')
    return {'schema': 'RESUME_PREREQUISITE_VIEW_V1',
            'status': 'HOLD' if reasons else 'PREREQUISITES_REPORTED',
            'reasons': sorted(reasons), 'resume_granted': False,
            'live_atomic_recheck': 'EXISTING_CONTROLLER_REQUIRED',
            'authenticity': 'CALLER_REQUIRED'}
