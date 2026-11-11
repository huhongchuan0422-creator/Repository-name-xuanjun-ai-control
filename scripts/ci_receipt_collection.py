"""Bounded read-only collection for the existing CI association checker.

The injected reader authenticates GitHub and accepts only generated API paths.
No credentials, arbitrary URLs, dispatch, review or release authority here.
"""
import copy
import re


def collect_ci_receipt(expected, read_json, bind, now):
    repo = expected.get('repository') if isinstance(expected, dict) else None
    if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('INVALID_REPOSITORY')
    for key in ('run_id', 'run_attempt'):
        if type(expected.get(key)) is not int or not 0 < expected[key] < 2 ** 63:
            raise ValueError('EXACT_RUN_ATTEMPT_REQUIRED')
    trusted = copy.deepcopy(expected)
    prefix = '/repos/{}/actions/runs/{}'.format(repo, trusted['run_id'])
    def run():
        value = read_json(prefix)
        if not isinstance(value, dict):
            raise ValueError('INVALID_RUN_RESPONSE')
        return copy.deepcopy(value)
    before = run()
    jobs, total, ids = [], None, set()
    for page in (1, 2):
        response = read_json(prefix + '/attempts/{}/jobs?per_page=100&page={}'.format(trusted['run_attempt'], page))
        if not isinstance(response, dict):
            raise ValueError('INVALID_JOBS_RESPONSE')
        count, rows = response.get('total_count'), response.get('jobs')
        if type(count) is not int or not 0 <= count <= 128 or not isinstance(rows, list):
            raise ValueError('JOBS_BOUND_OR_SCHEMA')
        if total is None:
            total = count
        if total != count or len(rows) != min(100, max(0, total - len(jobs))):
            raise ValueError('INCOMPLETE_OR_CHANGING_JOB_PAGES')
        for row in rows:
            if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= 0:
                raise ValueError('INVALID_JOB_ID')
            if row['id'] in ids:
                raise ValueError('DUPLICATE_JOB_ACROSS_PAGES')
            ids.add(row['id'])
            jobs.append(copy.deepcopy(row))
        if len(jobs) == total:
            break
    after = run()
    # Full returned run metadata equality rejects reruns and transition races.
    # It is a bounded observation, not an atomic GitHub snapshot or attestation.
    if before != after:
        raise ValueError('RUN_CHANGED_DURING_COLLECTION')
    result = bind(trusted, after, jobs, now, now)
    return {'schema': 'CI_COLLECTION_V1', 'run_id': trusted['run_id'],
            'run_attempt': trusted['run_attempt'], 'job_count': total,
            'complete_job_pages': True, 'association': result,
            'source_authentication': 'CALLER_REQUIRED',
            'atomic_snapshot': False, 'release_granted': False,
            'artifact_bytes_verified': False}
