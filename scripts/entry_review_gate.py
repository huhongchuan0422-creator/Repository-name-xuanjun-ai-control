"""Pure data gates for Issue19; no execution, authority grants or task queue.

The caller must authenticate contracts/reviewers and read canonical evidence.
Passing this module is eligibility for isolated tests, never release approval.
"""
import ast
import hashlib
import json
import math
import re

ENTRIES = ('WORK', 'CHATGPT', 'DOTS')


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


def review_bundle(contract, files, reviews):
    """Check in-memory bytes against a trusted contract and trusted reviews.

    No patches are applied. Shell/JS/etc need a separate bounded sandbox
    checker; unsupported formats HOLD instead of claiming syntax PASS.
    Human/model review evidence must originate outside the submitted bundle.
    """
    required = {'task_id', 'spec_sha256', 'checkpoint_sha256',
                'target_repository', 'target_base_sha', 'code_commit',
                'entry', 'developer', 'allowed_files', 'trusted_reviewers'}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError('EXACT_TRUSTED_CONTRACT_REQUIRED')
    if contract['entry'] not in ENTRIES:
        raise ValueError('UNKNOWN_ENTRY')
    for field, size in (('spec_sha256', 64), ('checkpoint_sha256', 64),
                        ('target_base_sha', 40), ('code_commit', 40)):
        if not isinstance(contract[field], str) or not re.fullmatch(
                '[0-9a-f]{%d}' % size, contract[field]):
            raise ValueError('HASH_BINDING_REQUIRED')
    if not isinstance(files, dict) or not files or len(files) > 32:
        raise ValueError('BOUNDED_FILES_REQUIRED')
    if not isinstance(contract['allowed_files'], list):
        raise ValueError('EXACT_PATH_ALLOWLIST_REQUIRED')
    manifest, total = {}, 0
    for path, raw in files.items():
        if (not isinstance(path, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', path)
                or any(p in ('', '.', '..') for p in path.split('/'))
                or path not in contract['allowed_files']):
            raise ValueError('PATH_NOT_AUTHORIZED')
        # Only bytes; symlink/file objects and command strings are rejected.
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
    binding = {k: contract[k] for k in ('task_id', 'spec_sha256',
        'checkpoint_sha256', 'target_repository', 'target_base_sha',
        'code_commit', 'entry')}
    binding['files'] = manifest
    bundle_sha = digest(canonical(binding))
    roles, identities = set(), set()
    for review in reviews:
        if (not isinstance(review, dict) or set(review) != {
                'reviewer', 'role', 'bundle_sha256', 'decision', 'evidence_id'}
                or review['role'] not in ('QA', 'SECURITY')
                or review['reviewer'] not in contract['trusted_reviewers']
                or review['reviewer'] == contract['developer']
                or review['reviewer'] in identities or review['role'] in roles
                or review['bundle_sha256'] != bundle_sha
                or review['decision'] != 'PASS'
                or not isinstance(review['evidence_id'], str)
                or not review['evidence_id'].strip()):
            raise ValueError('INDEPENDENT_EXACT_VERSION_REVIEW_REQUIRED')
        roles.add(review['role']); identities.add(review['reviewer'])
    return {'state': 'ISOLATED_TEST_ELIGIBLE' if roles == {'QA', 'SECURITY'}
            else 'HOLD_INDEPENDENT_REVIEW_REQUIRED',
            'bundle_sha256': bundle_sha, 'binding': binding,
            'authority_effect': 'NONE', 'release_approved': False,
            'syntax_only_not_command_safety': True}


def continuation_due(receipt_read_at, now, evidence):
    """Evaluate trusted canonical evidence; reads/heartbeats do not count.

    This emits a decision, never launches/kills/changes a lease. A runtime
    consumer must persist it in the existing ledger, not another queue.
    """
    for number in (receipt_read_at, now):
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError('FINITE_TIME_REQUIRED')
    if now < receipt_read_at:
        raise ValueError('CLOCK_RECONCILIATION_REQUIRED')
    if evidence is not None:
        if not isinstance(evidence, dict):
            raise ValueError('CANONICAL_EVIDENCE_REQUIRED')
        kind = evidence.get('kind')
        if kind == 'CONTINUED' and evidence.get('verified_execution') is True:
            return {'state': 'CONTINUED', 'authority_effect': 'NONE'}
        if (kind == 'HANDOFF_ACKNOWLEDGED'
                and all(evidence.get(k) is True for k in (
                    'receiver_accepted', 'old_writer_stopped',
                    'old_fence_invalidated', 'effects_reconciled'))):
            return {'state': kind, 'authority_effect': 'NONE'}
        if kind == 'HOLD' and all(isinstance(evidence.get(k), str)
                                 and evidence[k].strip() for k in (
                                     'blocker', 'checkpoint', 'next_action')):
            return {'state': 'HOLD', 'authority_effect': 'NONE'}
    age = now - receipt_read_at
    action = ('HOLD_CONTINUATION_MISSING' if age >= 900 else
              'INSPECT_AND_RESUME_SAME_ATTEMPT' if age >= 600 else
              'RECOVER_INTAKE' if age >= 300 else 'AWAIT_EXECUTION_EVIDENCE')
    return {'state': action, 'authority_effect': 'NONE',
            'takeover_allowed': False, 'read_or_heartbeat_is_progress': False}
