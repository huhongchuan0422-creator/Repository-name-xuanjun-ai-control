"""Pure association checks for caller-authenticated GitHub CI records. Python 3.6."""
import math
import re


def _text(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _positive(value):
    return type(value) is int and 0 < value < 2 ** 63


def bind_ci_receipt(expected, run, jobs, observed_at, now, max_age=300):
    """No fetch, signing, execution, test-assertion verification or release grant."""
    keys = {'repository', 'head_sha', 'workflow_path', 'run_id', 'run_attempt',
            'scope', 'jobs'}
    if not isinstance(expected, dict) or set(expected) != keys:
        raise ValueError('EXACT_TRUSTED_CI_EXPECTATION_REQUIRED')
    if (not _text(expected['repository'], r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+') or
            not _text(expected['head_sha'], r'[a-f0-9]{40}') or
            not _text(expected['workflow_path'], r'\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml') or
            not _positive(expected['run_id']) or not _positive(expected['run_attempt']) or
            expected['scope'] not in ('HOSTED_FIXTURE', 'UK_ISOLATED_FIXTURE')):
        raise ValueError('INVALID_CI_EXPECTATION')
    for value in (observed_at, now, max_age):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('FINITE_TIME_REQUIRED')
    if not 0 < max_age <= 3600:
        raise ValueError('INVALID_FRESHNESS_BOUND')
    if not isinstance(run, dict) or not isinstance(jobs, list) or len(jobs) > 128:
        raise ValueError('BOUNDED_GITHUB_RECORDS_REQUIRED')
    policies = expected['jobs']
    if not isinstance(policies, list) or not 1 <= len(policies) <= 32:
        raise ValueError('BOUNDED_REQUIRED_JOBS')
    policy_ids = set()
    for policy in policies:
        if not isinstance(policy, dict) or set(policy) != {'id', 'name', 'runner_id', 'runner_name', 'runner_group_id', 'labels', 'required_steps'}:
            raise ValueError('EXACT_JOB_POLICY_REQUIRED')
        if (not _positive(policy['id']) or policy['id'] in policy_ids or
                not _positive(policy['runner_id']) or type(policy['runner_group_id']) is not int or
                policy['runner_group_id'] < 0):
            raise ValueError('EXACT_JOB_RUNNER_ID_REQUIRED')
        policy_ids.add(policy['id'])
        for field in ('name', 'runner_name'):
            if not _text(policy[field], r'[A-Za-z0-9_.:/ ()-]{1,200}'):
                raise ValueError('INVALID_JOB_IDENTITY')
        for field in ('labels', 'required_steps'):
            values = policy[field]
            if (not isinstance(values, list) or not 1 <= len(values) <= 64 or
                    any(not _text(v, r'[A-Za-z0-9_.:/ ()-]{1,200}') for v in values) or
                    len(set(values)) != len(values)):
                raise ValueError('EXPLICIT_LABELS_AND_STEPS_REQUIRED')
        if expected['scope'] == 'UK_ISOLATED_FIXTURE' and 'self-hosted' not in policy['labels']:
            raise ValueError('UK_SELF_HOSTED_POLICY_REQUIRED')
        if expected['scope'] == 'HOSTED_FIXTURE' and 'self-hosted' in policy['labels']:
            raise ValueError('HOSTED_POLICY_CONFLICT')
    warnings = []
    if not observed_at <= now <= observed_at + max_age:
        warnings.append('STALE_OR_FUTURE_OBSERVATION')
    repo = run.get('repository')
    if not isinstance(repo, dict) or repo.get('full_name') != expected['repository']:
        warnings.append('REPOSITORY_MISMATCH')
    if (type(run.get('id')) is not int or run.get('id') != expected['run_id'] or
            type(run.get('run_attempt')) is not int or run.get('run_attempt') != expected['run_attempt'] or
            run.get('head_sha') != expected['head_sha'] or run.get('path') != expected['workflow_path']):
        warnings.append('RUN_BINDING_MISMATCH')
    if run.get('status') != 'completed' or run.get('conclusion') != 'success':
        warnings.append('RUN_NOT_SUCCESSFUL_TERMINAL')
    found = {}
    for job in jobs:
        if not isinstance(job, dict) or not _positive(job.get('id')):
            warnings.append('MALFORMED_JOB')
            continue
        if job['id'] in found:
            warnings.append('DUPLICATE_JOB_ID')
        found[job['id']] = job
    reports = []
    for policy in policies:
        reasons = []
        job = found.get(policy['id'])
        if job is None:
            reasons.append('REQUIRED_JOB_MISSING')
        else:
            if (type(job.get('run_id')) is not int or job.get('run_id') != expected['run_id'] or
                    type(job.get('run_attempt')) is not int or job.get('run_attempt') != expected['run_attempt'] or
                    job.get('head_sha') != expected['head_sha'] or job.get('name') != policy['name']):
                reasons.append('JOB_BINDING_MISMATCH')
            if job.get('status') != 'completed' or job.get('conclusion') != 'success':
                reasons.append('JOB_NOT_SUCCESSFUL_TERMINAL')
            labels = job.get('labels')
            if (type(job.get('runner_id')) is not int or job.get('runner_id') != policy['runner_id'] or
                    type(job.get('runner_group_id')) is not int or job.get('runner_group_id') != policy['runner_group_id'] or
                    job.get('runner_name') != policy['runner_name'] or not isinstance(labels, list) or
                    len(labels) > 64 or any(not _text(x, r'[A-Za-z0-9_.:/ ()-]{1,200}') for x in labels) or
                    set(labels) != set(policy['labels']) or len(set(labels)) != len(labels)):
                reasons.append('RUNNER_BINDING_MISMATCH')
            steps = job.get('steps')
            if not isinstance(steps, list) or len(steps) > 256:
                reasons.append('STEP_EVIDENCE_MISSING')
            else:
                named = {}
                for step in steps:
                    if not isinstance(step, dict) or not _text(step.get('name'), r'[A-Za-z0-9_.:/ ()-]{1,200}'):
                        reasons.append('INVALID_STEP_EVIDENCE')
                        continue
                    name = step['name']
                    if name in named:
                        reasons.append('AMBIGUOUS_STEP_NAME')
                    named[name] = step
                for name in policy['required_steps']:
                    step = named.get(name, {})
                    if step.get('status') != 'completed' or step.get('conclusion') != 'success':
                        reasons.append('REQUIRED_STEP_NOT_SUCCESSFUL')
        reports.append({'job_id': policy['id'], 'state': 'HOLD' if reasons else 'JOB_COMPLETED',
                        'reasons': sorted(set(reasons))})
    return {'state': 'HOLD' if warnings or any(x['reasons'] for x in reports) else 'CI_ASSOCIATION_VERIFIED',
            'warnings': sorted(set(warnings)), 'jobs': reports,
            'scope': expected['scope'], 'head_sha': expected['head_sha'],
            'run_id': expected['run_id'], 'run_attempt': expected['run_attempt'],
            'checked_out_commit': None, 'test_assertions_verified': False,
            'artifact_verified': False, 'installed_acceptance': False,
            'release_granted': False, 'authority_effect': 'NONE'}
