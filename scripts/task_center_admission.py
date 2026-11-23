"""Original admin admission metadata for an existing task; never claims it.

Reuses record_task_spec/record_unit/record_dispatch_preflight. Each existing
committed stage is compared, never replaced; a lost response is queryable.
"""
import hashlib
import json
from execution_policy_gateway import ExecutionPolicyGateway
from task_supervisor import canonical


def _scope(control, task_id, project_id):
    control._admin()
    control.gateway.assert_task_context(control.context, task_id)
    control._assert_expected_project(task_id, project_id)
    return control.gateway.supervisor._task(task_id)


def admission_status(control, value):
    if not isinstance(value, dict) or set(value) != {'task_id', 'project_id'}:
        raise ValueError('EXACT_ADMISSION_STATUS_REQUIRED')
    task = _scope(control, value['task_id'], value['project_id'])
    db = control.db
    task_id = value['task_id']
    result = {'task': {k: task[k] for k in ('task_id', 'spec_sha256', 'checkpoint_sha256', 'state', 'authority_state', 'attempt_id')},
              'resources': control.gateway.canonical_resources(task_id), 'authority_created': False}
    for key, table in (('work_specs', 'task_work_specs'), ('units', 'execution_units'),
                       ('dispatch_preflights', 'dispatch_preflights'), ('asset_queries', 'asset_query_receipts')):
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        result[key] = [dict(r) for r in db.execute('SELECT * FROM '+table+' WHERE tenant_id=? AND task_id=?',
                        (control.tenant_id, task_id))] if exists else []
    result['asset_queries']=[{k:r[k] for k in ('query_id','source_kind','source_version','result_digest','observed_at')} for r in result['asset_queries']]
    return result


def record_existing_admission(control, value):
    expected = {'task_id', 'project_id', 'checkpoint_sha256', 'spec', 'scope', 'query_ids', 'reuse_reason'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError('EXACT_EXISTING_ADMISSION_REQUIRED')
    task_id = value['task_id']
    task = _scope(control, task_id, value['project_id'])
    spec = value['spec']
    if (not isinstance(spec, dict) or hashlib.sha256(canonical(spec).encode()).hexdigest() != task['spec_sha256']
            or value['checkpoint_sha256'] != task['checkpoint_sha256']):
        raise ValueError('IMMUTABLE_ADMISSION_SPEC_CHECKPOINT_REQUIRED')
    if task['state'] != 'READY' or task['authority_state'] != 'NONE':
        raise ValueError('EXISTING_UNCLAIMED_TASK_REQUIRED')
    for key in ('allowed_files', 'acceptance'):
        if not isinstance(spec.get(key), list) or not spec[key] or any(not isinstance(x, str) or not x.strip() for x in spec[key]):
            raise ValueError('ORIGINAL_WORK_SPEC_REQUIRED')
    if not isinstance(spec.get('goal'), str) or not spec['goal'].strip():
        raise ValueError('ORIGINAL_WORK_SPEC_REQUIRED')
    if (not isinstance(value['scope'], list) or not value['scope'] or len(set(value['scope'])) != len(value['scope'])
            or any(x not in ('READ_SOURCE', 'WRITE_SOURCE', 'RUN_TEST') for x in value['scope'])):
        raise ValueError('DEVELOPMENT_METADATA_SCOPE_REQUIRED')
    if (not isinstance(value['query_ids'], list) or not value['query_ids']
            or any(not isinstance(x, str) or not x for x in value['query_ids'])
            or len(set(value['query_ids'])) != len(value['query_ids'])
            or not isinstance(value['reuse_reason'], str) or not value['reuse_reason'].strip()):
        raise ValueError('EXISTING_RESOURCE_QUERY_REQUIRED')
    policy = ExecutionPolicyGateway(control.gateway, control.context)
    meta = control.db.execute('SELECT * FROM gateway_task_metadata WHERE task_id=?', (task_id,)).fetchone()
    unit = {'task_id': task_id, 'delivery_stage': task['stage'], 'feature_unit': meta['node_id'],
            'goal': spec['goal'], 'scope': value['scope'], 'acceptance': spec['acceptance'],
            'dependencies': json.loads(task['dependencies_json']) or ['NONE'],
            'asset_version': meta['input_version'], 'responsible_party': task['owner']}
    policy.validate_unit_input(unit)
    queries = []
    for query_id in value['query_ids']:
        row = control.db.execute('SELECT * FROM asset_query_receipts WHERE tenant_id=? AND task_id=? AND query_id=?',
                                (control.tenant_id, task_id, query_id)).fetchone()
        if row is None or row['source_kind'] != 'CANONICAL_DB' or row['source_version'] != meta['input_version']:
            raise ValueError('EXISTING_VERSIONED_RESOURCE_QUERY_REQUIRED')
        query = json.loads(row['query_json'])
        if query['lookup']['asset_key'] not in control.gateway.canonical_resources(task_id):
            raise ValueError('CANONICAL_RESOURCE_QUERY_REQUIRED')
        observed = query['observed_result']
        if not isinstance(observed, dict) or not isinstance(observed.get('matches'), list):
            raise ValueError('ASSET_QUERY_OUTCOME_UNDETERMINED')
        queries.append(observed)
    outcome = 'FOUND' if any(q['matches'] for q in queries) else 'NOT_FOUND'
    before = admission_status(control, {'task_id': task_id, 'project_id': value['project_id']})
    desired_spec = {'goal': spec['goal'], 'deliverables_json': canonical(spec['allowed_files']), 'acceptance_json': canonical(spec['acceptance'])}
    desired_unit = {k: unit[k] for k in ('delivery_stage', 'feature_unit', 'goal', 'asset_version', 'responsible_party')}
    desired_unit.update({'scope_json':canonical(unit['scope']), 'acceptance_json':canonical(unit['acceptance']), 'dependency_json':canonical(unit['dependencies'])})
    # Validate every existing stage before the first write. No update/upsert.
    for key, desired in (('work_specs', desired_spec), ('units', desired_unit)):
        rows = before[key]
        if len(rows) > 1 or (rows and any(rows[0][k] != v for k, v in desired.items())):
            raise ValueError('EXISTING_ADMISSION_METADATA_CONFLICT:'+key)
    body = {'task_id': task_id, 'asset_version': unit['asset_version'], 'query_ids': sorted(value['query_ids']),
            'outcome': outcome, 'reuse_reason': value['reuse_reason']}
    preflight_id = hashlib.sha256(canonical(body).encode()).hexdigest()
    if before['dispatch_preflights'] and not any(r['preflight_id'] == preflight_id for r in before['dispatch_preflights']):
        raise ValueError('EXISTING_ADMISSION_METADATA_CONFLICT:dispatch_preflights')
    if not before['work_specs']:
        control.record_task_spec(task_id, spec['goal'], spec['allowed_files'], spec['acceptance'])
    if not before['units']:
        policy.record_unit(unit)
    if not before['dispatch_preflights']:
        policy.record_dispatch_preflight(task_id, unit['asset_version'], value['query_ids'], outcome, value['reuse_reason'])
    result = admission_status(control, {'task_id': task_id, 'project_id': value['project_id']})
    result['admission'] = policy.require_dispatch_ready(task_id)
    return result
