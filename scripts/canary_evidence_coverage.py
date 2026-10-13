"""Exact-version receipt coverage, never release authorization."""
import re

CASES = ('task_one_e2e', 'task_two_e2e', 'duplicate_event', 'worker_failure',
         'restart_recovery', 'old_writer_rejected', 'unknown_effect_hold',
         'outbox_ack', 'authenticated_dashboard', 'rollback')


def _hash(value, length):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{%d}' % length, value)


def evaluate_coverage(commit, artifact_sha256, receipts):
    """Caller verifies receipt authenticity and completeness before calling.

    Accept only UK_RUNTIME evidence bound to the exact source and artifact.
    Conflicting/duplicate cases fail closed, including failure hidden by PASS.
    Evidence digest presence is not signature validation or live execution.
    """
    if not _hash(commit, 40) or not _hash(artifact_sha256, 64):
        raise ValueError('INVALID_VERSION_BINDING')
    if not isinstance(receipts, list) or len(receipts) > 100:
        raise ValueError('INVALID_RECEIPTS')
    covered = set(); seen = set(); reasons = set()
    for receipt in receipts:
        if not isinstance(receipt, dict) or set(receipt) != {
                'case', 'commit', 'artifact_sha256', 'evidence_sha256',
                'environment', 'status', 'run_id'}:
            reasons.add('MALFORMED_RECEIPT'); continue
        case = receipt['case']
        if not isinstance(case, str) or case not in CASES:
            reasons.add('UNKNOWN_CASE'); continue
        if case in seen:
            reasons.add('DUPLICATE_CASE_' + case.upper())
        seen.add(case)
        valid = True
        if receipt['commit'] != commit or receipt['artifact_sha256'] != artifact_sha256:
            reasons.add('VERSION_MISMATCH_' + case.upper()); valid = False
        if receipt['environment'] != 'UK_RUNTIME':
            reasons.add('NON_RUNTIME_EVIDENCE_' + case.upper()); valid = False
        if receipt['status'] != 'PASS':
            reasons.add('CASE_NOT_PASS_' + case.upper()); valid = False
        if (not _hash(receipt['evidence_sha256'], 64)
                or not isinstance(receipt['run_id'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', receipt['run_id'])):
            reasons.add('MISSING_EVIDENCE_' + case.upper()); valid = False
        if valid:
            covered.add(case)
    missing = sorted(set(CASES) - covered)
    if missing:
        reasons.add('MISSING_REQUIRED_CASES')
    return {'schema': 'CANARY_EVIDENCE_COVERAGE_V1',
            'status': 'COVERAGE_COMPLETE' if not reasons else 'HOLD',
            'covered': sorted(covered), 'missing': missing, 'reasons': sorted(reasons),
            'authenticity': 'CALLER_REQUIRED', 'independent_review': 'REQUIRED',
            'release_granted': False, 'install_granted': False,
            'dispatch_performed': False}
