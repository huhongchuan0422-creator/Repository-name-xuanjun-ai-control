"""Fail-closed native Epoch7 attempt admission boundary (Python 3.6).

This is an incremental production-source gate, not an installation entry point.
The original successor contract and its single-use authority remain unchanged.
"""
from __future__ import absolute_import
import hashlib
import json

class AdmissionHold(RuntimeError):
    pass

def _hold(code):
    raise AdmissionHold('EPOCH7_ATTEMPT5_' + code)

def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def verify_native_recovery(driver, grant, attempt, authority, receipts, phase_order):
    """Check trusted admission/readback before allowing a native coordinator.

    Nothing here skips or replays a phase. Recovery must be selected and
    implemented by the separately reviewed original coordinator.
    """
    if not isinstance(grant, dict) or grant.get('max_attempts') != 5:
        _hold('NEW_GRANT_REQUIRED')
    if not isinstance(attempt, dict) or attempt.get('grant_id') != grant.get('grant_id'):
        _hold('ATTEMPT_SCOPE')
    if not callable(authority) or not callable(receipts):
        _hold('PROVIDER_REQUIRED')
    if not getattr(driver, 'check_binding', None):
        _hold('DRIVER_REQUIRED')
    try:
        driver.check_binding()
        proof = authority(grant, attempt)
        if not isinstance(proof, dict) or proof.get('verified') is not True:
            _hold('WRITER_FENCE_UNKNOWN')
        if proof.get('grant_id') != grant['grant_id'] or proof.get('attempt_id') != attempt.get('id'):
            _hold('FENCE_SCOPE')
        if proof.get('lease_valid') is not True or proof.get('exclusive') is not True:
            _hold('LEASE_OR_WRITER')
        readback = receipts(grant, attempt)
        if not isinstance(readback, dict) or readback.get('verified') is not True:
            _hold('RECEIPT_UNKNOWN')
        if readback.get('grant_id') != grant['grant_id'] or readback.get('attempt_id') != attempt.get('id'):
            _hold('RECEIPT_SCOPE')
        for key in ('run_id', 'job_id', 'invoke_id', 'checkpoint_sha256', 'backup_sha256'):
            if not isinstance(readback.get(key), str) or not readback[key]:
                _hold('RECEIPT_INCOMPLETE')
        completed = readback.get('completed')
        if not isinstance(completed, list) or not isinstance(phase_order, (list, tuple)):
            _hold('PHASE_RECEIPT')
        if completed != list(phase_order[:len(completed)]):
            _hold('PHASE_ORDER')
        if completed:
            # Original successor_resume_once never resumes inside the loop:
            # only an independently reviewed native recovery entry may do so.
            _hold('NATIVE_RECOVERY_NOT_CONNECTED')
        return {'schema': 1, 'grant_id': grant['grant_id'],
                'attempt_id': attempt['id'], 'authority_sha256': _sha(proof),
                'receipt_sha256': _sha(readback)}
    except AdmissionHold:
        raise
    except BaseException:
        _hold('PROVIDER_UNKNOWN')
