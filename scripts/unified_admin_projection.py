"""Pure, read-only normalized projection for the unified admin workbench.

The caller owns authentication and source reads.  This module deliberately
does not open a database, decrypt a secret, or infer production connectivity.
"""
from __future__ import print_function

UNKNOWN = 'UNKNOWN'
NOT_CONNECTED = 'NOT_CONNECTED'


def _source(source_id, status, observed_at, detail):
    return {'source_id': source_id, 'status': status,
            'observed_at': observed_at, 'detail': detail}


def _disconnected_source(source_id, observed_at, candidates, evidence_refs,
                         gaps):
    return {
        'source_id': source_id,
        'status': NOT_CONNECTED,
        'source_level': 'CANDIDATE_ONLY_UNVERIFIED',
        'observed_at': observed_at,
        'source_candidates': candidates,
        'evidence_refs': evidence_refs,
        'gaps': gaps,
        'detail': 'No authoritative adapter is registered.',
    }


def _capability():
    return {'authority': 'SERVER', 'access': 'READ_ONLY',
            'allowed_actions': [], 'mutation': 'NONE'}


def _task_record(value):
    ordinary = ('task_id', 'project_id', 'state', 'runtime_status',
                'responsible_party', 'next_action', 'last_real_progress_at',
                'blocker')
    return {key: value.get(key, UNKNOWN) for key in ordinary}


def _task_audit(value, events):
    technical = ('task_id', 'attempt_id', 'run_id', 'session_id', 'epoch',
                 'checkpoint_sha256', 'input_version', 'output_version',
                 'process_state', 'session_state', 'executor_instance_id',
                 'writer_identity', 'authority_state',
                 'authority_valid_until', 'writer_stopped',
                 'effects_reconciled')
    result = {key: value.get(key, UNKNOWN) for key in technical}
    result['checkpoints'] = value.get('checkpoints', [])
    result['evidence'] = [item for item in events
                          if item.get('task_id') == value.get('task_id')]
    return result


def _provider_record(value):
    # secret_mask is intentionally not copied: only configuration state is
    # exposed, never a mask, cipher, token, key, or credential body.
    return {
        'provider_id': value.get('provider_id', UNKNOWN),
        'display_name': value.get('display_name', UNKNOWN),
        'adapter_type': value.get('adapter_type', UNKNOWN),
        'enabled': bool(value.get('enabled', False)),
        'price_state': value.get('price_state', UNKNOWN),
        'circuit_state': value.get('circuit_state', UNKNOWN),
        'config_version': value.get('config_version', UNKNOWN),
        'secret': {
            'state': ('CONFIGURED' if (value.get('secret_configured') or
                                       value.get('secret_mask') is not None)
                      else 'NOT_CONFIGURED'),
            'ref': ('PROTECTED_PROVIDER_SECRET:' +
                    str(value.get('provider_id', UNKNOWN)))
        },
        'updated_at': value.get('updated_at', UNKNOWN),
    }


def _model_usage_record(value):
    """Expose ModelControl usage without turning estimates into billing facts."""
    cost_state = value.get('cost_state', UNKNOWN)
    estimated_cost = (value.get('known_cost')
                      if cost_state in ('KNOWN', 'KNOWN_ZERO') else None)
    return {
        'provider_id': value.get('provider_id', UNKNOWN),
        'model_id': value.get('model_id', UNKNOWN),
        'request_count': value.get('request_count', UNKNOWN),
        'input_tokens': value.get('input_tokens', UNKNOWN),
        'output_tokens': value.get('output_tokens', UNKNOWN),
        'cost_state': cost_state,
        'estimated_cost': (estimated_cost if estimated_cost is not None
                           else UNKNOWN),
        'cost_unit': UNKNOWN,
        'semantic': 'MODEL_ESTIMATE_NOT_BILLING_OR_ACTUAL_CHARGE',
    }


def build_projection(task_projection, model_projection, observed_at):
    """Build one fail-closed TEST_ONLY admin projection."""
    if not isinstance(task_projection, dict) or not isinstance(
            model_projection, dict):
        raise ValueError('PROJECTION_OBJECTS_REQUIRED')
    if task_projection.get('mode') != 'TEST_ONLY' or model_projection.get(
            'mode') != 'TEST_ONLY':
        raise ValueError('TEST_ONLY_SOURCES_REQUIRED')
    tenant_id = task_projection.get('tenant_id')
    model_tenant = model_projection.get('tenant_id', tenant_id)
    if not tenant_id or model_tenant != tenant_id:
        raise ValueError('SAME_TENANT_REQUIRED')
    raw_tasks = task_projection.get('tasks', [])
    providers = [_provider_record(item) for item in
                 model_projection.get('providers', [])]
    model_usage = [_model_usage_record(item) for item in
                   model_projection.get('usage', [])]
    events = [{key: item.get(key, UNKNOWN) for key in
               ('task_id', 'attempt_id', 'event_id', 'kind', 'observed_at',
                'evidence_kind', 'evidence_ref')}
              for item in task_projection.get('timeline', [])]
    research_raw = [task for task in raw_tasks if
                    task.get('board_id') == 'research-development']
    tasks = [_task_record(item) for item in raw_tasks]
    project_source = _disconnected_source(
        'PROJECT_DELIVERY', observed_at, ['Project Delivery adapter'],
        ['NONE_FOUND'],
        ['CANONICAL_ADAPTER', 'IDENTITY', 'SCHEMA_VERSION',
         'TENANT_MAPPING', 'CURRENT_WRITER', 'INSTALL_EVIDENCE'])
    finance_source = _disconnected_source(
        'FINANCE_LEDGER', observed_at,
        ['Canonical Finance adapter', 'Finance ledger projection'],
        ['git:0b47f98d656f0ac7b182a724746a72b7f7028e40:'
         'scripts/community_saas_offer_catalog.py',
         'git:0cd56648867bcb6bc0d8c35fda82f05e4fe58a5f:'
         'scripts/owner_finance_takeover_combined_inspect.py'],
        ['CANONICAL_ADAPTER', 'IDENTITY', 'SCHEMA_VERSION',
         'TENANT_MAPPING', 'CURRENT_WRITER', 'INSTALL_EVIDENCE'])
    social_source = _disconnected_source(
        'SOCIAL_MEDIA', observed_at,
        ['Channel Registry', 'Channel Metrics projection'],
        ['git:b021d8059654570aa8caeb0ee88befe3214fc9a3:'
         'deploy/pr122-oauth-candidate/',
         'git:ce76432a7050cfd0bd3410a1967624f969a253d9:'
         'deploy/pr122-minimal-cutover/tokyo-nginx-source-inventory.json'],
        ['CHANNEL_REGISTRY', 'METRICS', 'RBAC', 'INSTALL_EVIDENCE'])
    server_source = _disconnected_source(
        'SERVER_INVENTORY', observed_at,
        ['Infrastructure Registry', 'Blueprint HTTP adapter'],
        ['git:3398098ffffe741fd087e854a8f3c75007113481:'
         'scripts/v27-batch-readonly.sh',
         'git:ce76432a7050cfd0bd3410a1967624f969a253d9:'
         'scripts/pr122_domestic_channel_inventory.py'],
        ['INFRA_REGISTRY', 'BLUEPRINT_HTTP', 'CAPABILITY',
         'CURRENT_INVENTORY'])
    sources = {
        'task_registry': _source('CANONICAL_TASK_REGISTRY',
                                 'CONNECTED_TEST_ONLY', observed_at,
                                 'Canonical read-only task projection.'),
        'model_control': _source('MODEL_CONTROL', 'CONNECTED_TEST_ONLY',
                                 observed_at,
                                 'Read-only ModelControl projection.'),
        'project': project_source,
        'finance': finance_source,
        'social_media': social_source,
        'servers': server_source,
    }
    research = [_task_record(task) for task in research_raw]
    research_audit = [_task_audit(task, events) for task in research_raw]
    return {
        'schema': 1,
        'projection': 'UNIFIED_ADMIN_PROJECTION_V1',
        'mode': 'TEST_ONLY',
        'production_status': 'NOT_IMPLEMENTED',
        'tenant_id': tenant_id,
        'observed_at': observed_at,
        'source_observed_at': task_projection.get('observed_at', UNKNOWN),
        'status': 'READ_ONLY_TEST_ONLY',
        'capability': _capability(),
        'sources': sources,
        'modules': {
            'overview': {
                'status': 'CONNECTED_TEST_ONLY',
                'source': 'CANONICAL_TASK_REGISTRY',
                'observed_at': observed_at,
                'source_observed_at': task_projection.get('observed_at',
                                                           UNKNOWN),
                'summary': {'task_count': len(tasks),
                            'research_task_count': len(research),
                            'project_progress': UNKNOWN,
                            'finance': UNKNOWN},
                'capability': _capability(),
            },
            'research-development': {
                'status': 'CONNECTED_TEST_ONLY',
                'source': 'CANONICAL_TASK_REGISTRY',
                'observed_at': observed_at,
                'records': research,
                'capability': _capability(),
                'advanced': {'audit_records': research_audit},
            },
            'configuration': {
                'status': 'CONNECTED_TEST_ONLY',
                'source': 'MODEL_CONTROL',
                'observed_at': observed_at,
                'records': providers,
                'capability': _capability(),
                'advanced': {
                    'quota_status': model_projection.get('quota_status', []),
                    'modules': model_projection.get('modules', []),
                    'model_usage': model_usage,
                    'model_usage_semantic':
                        'MODEL_ESTIMATE_NOT_BILLING_OR_ACTUAL_CHARGE',
                    'openai_channel_preference':model_projection.get(
                        'openai_channel_preference', {
                          'selected_preference': UNKNOWN,
                          'effective_channel': 'NONE',
                          'status': 'NOT_CONFIGURED'}),
                },
            },
            'finance': {
                'status': NOT_CONNECTED,
                'source': 'FINANCE_LEDGER',
                'observed_at': observed_at,
                'metrics': {'revenue': UNKNOWN, 'cost': UNKNOWN,
                            'profit': UNKNOWN, 'balance': UNKNOWN},
                'records': [], 'capability': _capability(),
                'source': finance_source,
            },
            'project': {'status': NOT_CONNECTED, 'records': [],
                        'capability': _capability(),
                        'source': project_source},
            'social_media': {'status': NOT_CONNECTED, 'records': [],
                             'capability': _capability(),
                             'source': social_source},
            'servers': {'status': NOT_CONNECTED, 'records': [],
                        'capability': _capability(),
                        'source': server_source},
        },
    }
