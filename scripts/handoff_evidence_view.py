"""Version-bound handoff evidence display, never execution authority."""
import re

PROOFS = ('old_writer_stopped', 'descendants_stopped', 'old_fence_revoked',
          'effects_reconciled', 'successor_ack', 'successor_lease_valid')


def handoff_view(expected, observed):
    keys = {'task_id', 'spec_sha256', 'checkpoint_sha256', 'commit', 'artifact_sha256'}
    if not isinstance(expected, dict) or set(expected) != keys:
        raise ValueError('INVALID_HANDOFF_BINDING')
    for key, value in expected.items():
        pattern = r'[A-Za-z0-9_.:-]{1,160}' if key == 'task_id' else '[a-f0-9]{%d}' % (40 if key == 'commit' else 64)
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError('INVALID_HANDOFF_BINDING')
    reasons = []
    if not isinstance(observed, dict) or set(observed) != keys | set(PROOFS) | {'evidence_sha256'}:
        reasons.append('INCOMPLETE_HANDOFF_EVIDENCE')
    else:
        for key in sorted(keys):
            if observed[key] != expected[key]: reasons.append('BINDING_MISMATCH_' + key.upper())
        for key in PROOFS:
            if observed[key] is not True: reasons.append('UNPROVEN_' + key.upper())
        evidence = observed['evidence_sha256']
        if not isinstance(evidence, str) or not re.fullmatch('[a-f0-9]{64}', evidence):
            reasons.append('MISSING_HANDOFF_EVIDENCE')
    return {'schema': 'HANDOFF_EVIDENCE_VIEW_V1',
            'status': 'HOLD' if reasons else 'HANDOFF_PROOFS_REPORTED',
            'reasons': sorted(reasons), 'execution_granted': False,
            'handoff_performed': False, 'authenticity': 'CALLER_REQUIRED',
            'atomic_authority_recheck': 'CANONICAL_CONTROLLER_REQUIRED'}
