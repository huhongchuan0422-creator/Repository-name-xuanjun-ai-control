"""Source-path preflight over an existing trusted claim snapshot; no registry."""
import math
import re


def _identity(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value) is not None


def _path(value, prefix=False):
    if not isinstance(value, str) or not 1 <= len(value) <= 300:
        return False
    text = value[:-1] if prefix and value.endswith('/') else value
    return (re.fullmatch(r'[A-Za-z0-9_./-]+', text) is not None and
            all(part not in ('', '.', '..', '.git') for part in text.split('/')))


def _covers(scope, path):
    return path.startswith(scope) if scope.endswith('/') else path == scope


def check_source_paths(snapshot, changes, repository, task_id, writer,
                       expected_revision, now, base_sha, head_sha, max_age=300):
    """Caller authenticates complete active claims; this result grants no writer."""
    if (not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository)
            or not _identity(task_id) or not _identity(writer) or
            type(expected_revision) is not int or expected_revision < 1):
        raise ValueError('EXACT_SOURCE_BINDING_REQUIRED')
    if any(not isinstance(v, str) or not re.fullmatch(r'[a-f0-9]{40}', v) for v in (base_sha, head_sha)):
        raise ValueError('EXACT_SOURCE_COMMIT_BINDING_REQUIRED')
    if not isinstance(snapshot, dict) or set(snapshot) != {'repository', 'revision', 'observed_at', 'complete', 'claims'}:
        raise ValueError('EXACT_CLAIM_SNAPSHOT_REQUIRED')
    for value in (now, snapshot['observed_at'], max_age):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('FINITE_TIME_REQUIRED')
    if not 0 < max_age <= 3600:
        raise ValueError('INVALID_FRESHNESS_BOUND')
    claims = snapshot['claims']
    if not isinstance(claims, list) or len(claims) > 1024:
        raise ValueError('BOUNDED_ACTIVE_CLAIMS_REQUIRED')
    scopes, total, claim_ids = [], 0, set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'claim_id', 'task_id', 'writer', 'paths'}:
            raise ValueError('EXACT_ACTIVE_CLAIM_REQUIRED')
        if any(not _identity(claim[k]) for k in ('claim_id', 'task_id', 'writer')):
            raise ValueError('INVALID_CLAIM_IDENTITY')
        if claim['claim_id'] in claim_ids:
            raise ValueError('DUPLICATE_CLAIM_ID')
        claim_ids.add(claim['claim_id'])
        paths = claim['paths']
        if (not isinstance(paths, list) or not 1 <= len(paths) <= 256 or
                any(not _path(p, prefix=True) for p in paths) or len(set(paths)) != len(paths)):
            raise ValueError('EXPLICIT_CANONICAL_PATH_SCOPE_REQUIRED')
        total += len(paths)
        if total > 4096:
            raise ValueError('TOTAL_SCOPE_BOUND')
        for path in paths:
            scopes.append((path, claim['task_id'], claim['writer'], claim['claim_id']))
    if not isinstance(changes, list) or not 1 <= len(changes) <= 256:
        raise ValueError('BOUNDED_CHANGED_PATHS_REQUIRED')
    requested, targets = [], set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'status', 'path', 'previous_path'}:
            raise ValueError('EXACT_CHANGE_RECORD_REQUIRED')
        if change['status'] not in ('added', 'modified', 'removed', 'renamed') or not _path(change['path']):
            raise ValueError('CANONICAL_CHANGE_PATH_REQUIRED')
        if change['path'] in targets:
            raise ValueError('DUPLICATE_CHANGED_PATH')
        targets.add(change['path'])
        requested.append(change['path'])
        previous = change['previous_path']
        if change['status'] == 'renamed':
            if not _path(previous) or previous == change['path']:
                raise ValueError('CANONICAL_RENAME_SOURCE_REQUIRED')
            requested.append(previous)
        elif previous is not None:
            raise ValueError('UNEXPECTED_PREVIOUS_PATH')
    warnings = []
    if snapshot['complete'] is not True:
        warnings.append('INCOMPLETE_CLAIM_SNAPSHOT')
    if (snapshot['repository'] != repository or type(snapshot['revision']) is not int or
            snapshot['revision'] != expected_revision):
        warnings.append('SNAPSHOT_BINDING_MISMATCH')
    if not snapshot['observed_at'] <= now <= snapshot['observed_at'] + max_age:
        warnings.append('STALE_OR_FUTURE_SNAPSHOT')
    # Same task may not have a second active source writer even on disjoint paths.
    if any(c['task_id'] == task_id and c['writer'] != writer for c in claims):
        warnings.append('MULTIPLE_ACTIVE_TASK_WRITERS')
    results = []
    for path in sorted(set(requested)):
        matches = [s for s in scopes if _covers(s[0], path)]
        mine = [s for s in matches if s[1:3] == (task_id, writer)]
        others = [s for s in matches if s[1:3] != (task_id, writer)]
        reasons = []
        if not mine:
            reasons.append('PATH_NOT_OWNED')
        if others:
            reasons.append('ACTIVE_PATH_CONFLICT')
        results.append({'path': path, 'state': 'HOLD' if reasons else 'OWNED_PATH',
                        'reasons': reasons, 'conflicting_claim_ids': sorted(set(s[3] for s in others))})
    return {'state': 'HOLD' if warnings or any(x['reasons'] for x in results) else 'SOURCE_PATHS_MATCH',
            'warnings': warnings, 'paths': results, 'revision': expected_revision,
            'task_id': task_id, 'writer': writer, 'base_sha': base_sha,
            'head_sha': head_sha, 'authority_effect': 'NONE',
            'writer_granted': False, 'runtime_lease_granted': False}
