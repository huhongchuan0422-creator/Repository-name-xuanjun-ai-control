"""Pure data admission gates for the three native development entries.

This module never executes submitted code or changes authority.  Every result
is bound to one immutable contract or one canonical task attempt.
"""
import ast
import hashlib
import json
import math
import re

ENTRIES = ('WORK', 'CHATGPT', 'DOTS')
IDENTITY_FIELDS = ('task_id', 'attempt', 'run_id', 'session_id', 'fence',
                   'checkpoint_sha256', 'ledger_revision')
HEX40 = re.compile(r'[0-9a-f]{40}')
HEX64 = re.compile(r'[0-9a-f]{64}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}')
SAFE_PATH = re.compile(r'[A-Za-z0-9_./-]+')


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _name(value):
    return isinstance(value, str) and NAME.fullmatch(value) is not None


def _safe_path(path):
    return (isinstance(path, str) and SAFE_PATH.fullmatch(path) is not None
            and all(part not in ('', '.', '..') for part in path.split('/')))


def _validate_contract(contract):
    required = {'task_id', 'spec_sha256', 'checkpoint_sha256',
                'target_repository', 'target_base_sha', 'code_commit',
                'entry', 'developer', 'allowed_files', 'trusted_reviewers'}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError('EXACT_TRUSTED_CONTRACT_REQUIRED')
    if contract['entry'] not in ENTRIES or not _name(contract['task_id']):
        raise ValueError('UNKNOWN_ENTRY_OR_TASK')
    if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',
                        contract['target_repository'] or ''):
        raise ValueError('REPOSITORY_BINDING_REQUIRED')
    for field in ('spec_sha256', 'checkpoint_sha256'):
        if not isinstance(contract[field], str) or not HEX64.fullmatch(contract[field]):
            raise ValueError('HASH_BINDING_REQUIRED')
    for field in ('target_base_sha', 'code_commit'):
        if not isinstance(contract[field], str) or not HEX40.fullmatch(contract[field]):
            raise ValueError('HASH_BINDING_REQUIRED')
    if not _name(contract['developer']):
        raise ValueError('EXACT_DEVELOPER_REQUIRED')
    allowed = contract['allowed_files']
    if (not isinstance(allowed, list) or not allowed or len(allowed) > 32
            or any(not _safe_path(path) for path in allowed)
            or len(set(allowed)) != len(allowed)):
        raise ValueError('EXACT_PATH_ALLOWLIST_REQUIRED')
    reviewers = contract['trusted_reviewers']
    if (not isinstance(reviewers, list) or len(reviewers) != 2
            or len(set(reviewers)) != 2 or any(not _name(item) for item in reviewers)
            or contract['developer'] in reviewers):
        raise ValueError('EXACT_REVIEWER_LIST_REQUIRED')


def review_bundle(contract, files, reviews):
    """Bind all policy fields, exact bytes and two authenticated reviews."""
    _validate_contract(contract)
    if not isinstance(files, dict) or not files or len(files) > 32:
        raise ValueError('BOUNDED_FILES_REQUIRED')
    if set(files) != set(contract['allowed_files']):
        raise ValueError('EXACT_AUTHORIZED_FILE_SET_REQUIRED')
    manifest, total = {}, 0
    for path in sorted(files):
        raw = files[path]
        if not _safe_path(path):
            raise ValueError('PATH_NOT_AUTHORIZED')
        if type(raw) is not bytes or len(raw) > 131072:
            raise ValueError('BOUNDED_PLAIN_BYTES_REQUIRED')
        total += len(raw)
        if total > 524288:
            raise ValueError('BUNDLE_TOO_LARGE')
        text = raw.decode('utf-8', 'strict')
        if '\x00' in text or '\r' in text:
            raise ValueError('CANONICAL_UTF8_LF_REQUIRED')
        if path.endswith('.py'):
            ast.parse(text, filename=path)
        elif path.endswith('.json'):
            json.loads(text, object_pairs_hook=unique,
                       parse_constant=lambda unused: (_ for _ in ()).throw(
                           ValueError('NONFINITE_JSON')))
        else:
            raise ValueError('HOLD_EXTERNAL_SANDBOX_SYNTAX_CHECK_REQUIRED')
        manifest[path] = digest(raw)
    binding = {'contract': contract, 'files': manifest}
    bundle_sha = digest(canonical(binding))
    if not isinstance(reviews, list) or len(reviews) > 2:
        raise ValueError('BOUNDED_REVIEW_LIST_REQUIRED')
    roles, identities, evidence_ids = set(), set(), set()
    for review in reviews:
        if (not isinstance(review, dict) or set(review) != {
                'reviewer', 'role', 'bundle_sha256', 'decision', 'evidence_id'}
                or review['role'] not in ('QA', 'SECURITY')
                or review['reviewer'] not in contract['trusted_reviewers']
                or review['reviewer'] in identities or review['role'] in roles
                or review['bundle_sha256'] != bundle_sha
                or review['decision'] != 'PASS'
                or not isinstance(review['evidence_id'], str)
                or not re.fullmatch(r'github-review:[1-9][0-9]*', review['evidence_id'])
                or review['evidence_id'] in evidence_ids):
            raise ValueError('INDEPENDENT_EXACT_VERSION_REVIEW_REQUIRED')
        roles.add(review['role']); identities.add(review['reviewer'])
        evidence_ids.add(review['evidence_id'])
    return {'state': 'ISOLATED_TEST_ELIGIBLE' if roles == {'QA', 'SECURITY'}
            else 'HOLD_INDEPENDENT_REVIEW_REQUIRED',
            'bundle_sha256': bundle_sha, 'binding': binding,
            'authority_effect': 'NONE', 'release_approved': False,
            'syntax_only_not_command_safety': True}


def _validate_identity(identity):
    if not isinstance(identity, dict) or set(identity) != set(IDENTITY_FIELDS):
        raise ValueError('EXACT_ATTEMPT_IDENTITY_REQUIRED')
    for field in IDENTITY_FIELDS:
        value = identity[field]
        if field == 'ledger_revision':
            if type(value) is not int or value < 0:
                raise ValueError('LEDGER_REVISION_REQUIRED')
        elif field == 'checkpoint_sha256':
            if not isinstance(value, str) or not HEX64.fullmatch(value):
                raise ValueError('CHECKPOINT_BINDING_REQUIRED')
        elif not _name(value):
            raise ValueError('ATTEMPT_IDENTITY_REQUIRED')


def continuation_due(receipt_read_at, now, evidence, identity=None):
    """Evaluate exact canonical evidence for the 5/10/15 minute policy."""
    for number in (receipt_read_at, now):
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError('FINITE_TIME_REQUIRED')
    if now < receipt_read_at:
        raise ValueError('CLOCK_RECONCILIATION_REQUIRED')
    _validate_identity(identity)
    if evidence is not None:
        if not isinstance(evidence, dict):
            raise ValueError('CANONICAL_EVIDENCE_REQUIRED')
        kind = evidence.get('kind')
        common = set(IDENTITY_FIELDS) | {'kind', 'observed_at'}
        if any(evidence.get(k) != identity[k] for k in IDENTITY_FIELDS):
            raise ValueError('CROSS_ATTEMPT_EVIDENCE_REJECTED')
        observed = evidence.get('observed_at')
        if type(observed) not in (int, float) or not math.isfinite(observed) \
                or observed < receipt_read_at or observed > now:
            raise ValueError('EVIDENCE_TIME_BINDING_REQUIRED')
        if kind == 'CONTINUED':
            expected = common | {'verified_execution', 'execution_receipt_sha256'}
            if (set(evidence) == expected and evidence['verified_execution'] is True
                    and isinstance(evidence['execution_receipt_sha256'], str)
                    and HEX64.fullmatch(evidence['execution_receipt_sha256'])):
                return {'state': 'CONTINUED', 'authority_effect': 'NONE'}
        elif kind == 'HANDOFF_ACKNOWLEDGED':
            proof = {'receiver_accepted', 'old_writer_stopped',
                     'old_fence_invalidated', 'effects_reconciled'}
            expected = common | proof | {'handoff_receipt_sha256'}
            if (set(evidence) == expected and all(evidence[k] is True for k in proof)
                    and isinstance(evidence['handoff_receipt_sha256'], str)
                    and HEX64.fullmatch(evidence['handoff_receipt_sha256'])):
                return {'state': kind, 'authority_effect': 'NONE'}
        elif kind == 'HOLD':
            expected = common | {'blocker', 'checkpoint', 'next_action',
                                 'hold_receipt_sha256'}
            if (set(evidence) == expected
                    and evidence['checkpoint'] == identity['checkpoint_sha256']
                    and all(isinstance(evidence[k], str) and evidence[k].strip()
                            for k in ('blocker', 'next_action'))
                    and isinstance(evidence['hold_receipt_sha256'], str)
                    and HEX64.fullmatch(evidence['hold_receipt_sha256'])):
                return {'state': 'HOLD', 'authority_effect': 'NONE'}
    age = now - receipt_read_at
    action = ('HOLD_CONTINUATION_MISSING' if age >= 900 else
              'INSPECT_AND_RESUME_SAME_ATTEMPT' if age >= 600 else
              'RECOVER_INTAKE' if age >= 300 else 'AWAIT_EXECUTION_EVIDENCE')
    return {'state': action, 'authority_effect': 'NONE',
            'takeover_allowed': False, 'read_or_heartbeat_is_progress': False,
            'identity': identity}
