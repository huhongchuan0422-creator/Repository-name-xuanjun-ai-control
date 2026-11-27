"""Authenticated first-claim seam; no task creation, role assignment or runner.

Bootstrap injects existing signed registration custody and trusted caller context.
Tool input contains only a task id. Canonical Supervisor allocates attempt/lease.
"""
import copy
import hashlib
import json
from development_identity_adapter import TrustedRegistrationVerifier
from execution_policy_gateway import ExecutionPolicyGateway
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_supervisor import Supervisor, canonical
from task_writer_fence import Fence

ACTIONS = frozenset(('task_claim', 'task_claim_status'))


def tools():
    return [{'name': name, 'description': 'Claim an already admitted development task.' if name == 'task_claim' else 'Read canonical development claim state; never retries execution.',
             'inputSchema': {'type': 'object', 'properties': {'task_id': {'type': 'string', 'minLength': 1, 'maxLength': 160}},
                             'required': ['task_id'], 'additionalProperties': False},
             'annotations': {'readOnlyHint': name != 'task_claim', 'openWorldHint': False}}
            for name in sorted(ACTIONS)]


class ClaimHost:
    def __init__(self, bindings, verifier, custody_provider):
        # Reuse the validated existing development bindings, not a new registry.
        from task_center_mcp_development import DevelopmentHost
        self.bindings = DevelopmentHost(bindings).bindings
        if not isinstance(verifier, TrustedRegistrationVerifier) or not callable(custody_provider):
            raise ValueError('TRUSTED_REGISTRATION_BOOTSTRAP_REQUIRED')
        self.verifier = verifier
        self.custody_provider = custody_provider

    def binding(self, identity, task_id=None):
        return next((b for b in self.bindings if b['phase'] == 'EXECUTOR'
                     and all(b[k] == identity.get(k) for k in ('tenant_id', 'principal_id', 'project_id'))
                     and (task_id is None or b['task_id'] == task_id)), None)

    def visible(self, identity):
        if self.binding(identity) is None or 'task:read' not in identity.get('scopes', []):
            return []
        return [t for t in tools() if t['name'] != 'task_claim' or 'task:submit' in identity.get('scopes', [])]

    def rpc(self, service, identity, value):
        p = value.get('params')
        if not isinstance(p, dict) or set(p) != {'name', 'arguments'} or p['name'] not in ACTIONS:
            raise ValueError('EXACT_CLAIM_RPC_REQUIRED')
        name, args = p['name'], p['arguments']
        if (not isinstance(args, dict) or set(args) != {'task_id'} or
                not isinstance(args['task_id'], str) or not 0 < len(args['task_id']) <= 160):
            raise ValueError('EXACT_CLAIM_ARGUMENTS_REQUIRED')
        b = self.binding(identity, args['task_id'])
        if b is None: raise ValueError('CLAIM_HOST_EXECUTOR_BINDING_REQUIRED')
        if any(getattr(service, k) != identity.get(k) for k in ('tenant_id', 'principal_id', 'project_id')):
            raise ValueError('CLAIM_OAUTH_IDENTITY_MISMATCH')
        required = 'task:submit' if name == 'task_claim' else 'task:read'
        if required not in identity.get('scopes', []): raise ValueError('CLAIM_OAUTH_SCOPE_REQUIRED')
        s = Supervisor(service.db_path, development_identity_verifier=self.verifier)
        try:
            g = GatewayKernel(s, TestTenantAuthority(service.authority_key))
            context = g.tenants.issue(identity['tenant_id'], identity['principal_id'])
            task_id = args['task_id']
            def check():
                g.assert_task_context(context, task_id)
                meta = s.db.execute('SELECT project_id FROM gateway_task_metadata WHERE task_id=?', (task_id,)).fetchone()
                task = s._task(task_id)
                contract = s.development_contract(task_id)
                if (meta is None or meta['project_id'] != b['project_id'] or
                        task['spec_sha256'] != b['spec_sha256'] or task['checkpoint_sha256'] != b['checkpoint_sha256'] or
                        hashlib.sha256(canonical(contract).encode()).hexdigest() != b['contract_sha256'] or
                        contract['developer'] != b['authority_identity']):
                    raise ValueError('CURRENT_CANONICAL_CLAIM_SCOPE_REQUIRED')
                role = s.db.execute('SELECT phase,enabled,writer_allowed FROM role_templates WHERE tenant_id=? AND role_id=? AND version=?',
                                    (b['tenant_id'], b['role_id'], b['role_version'])).fetchone()
                if role is None or tuple(role) != ('EXECUTOR', 1, 1):
                    raise ValueError('CURRENT_CLAIM_ROLE_ALLOWLIST_REQUIRED')
                return task, contract
            task, contract = check()
            if name == 'task_claim':
                # Never calls the local TEST_ONLY start adapter or admin service.
                policy = ExecutionPolicyGateway(g, context)
                policy.require_dispatch_ready(task_id)
                custody = self.custody_provider(copy.deepcopy(identity), task_id)
                expected = {'owner_grant', 'developer_credential', 'caller', 'lock_root', 'valid_until'}
                if not isinstance(custody, dict) or set(custody) != expected:
                    raise ValueError('EXISTING_REGISTRATION_CUSTODY_REQUIRED')
                resources = g.canonical_resources(task_id)
                def admission():
                    check()
                    verified = self.verifier.verify(custody['owner_grant'], custody['developer_credential'], task_id, b['contract_sha256'])
                    if verified['owner'] != {'issuer': 'owner-auth', 'subject': s._task(task_id)['owner']}:
                        raise ValueError('CANONICAL_OWNER_CLAIM_REQUIRED')
                    policy.require_dispatch_ready(task_id)
                    g.assert_start_allowed(context, task_id, resources)
                    if service.write_admission is not None:
                        service.write_admission()
                admission()
                fence = Fence(s, custody['lock_root'])
                try:
                    fence.claim_first_development_writer(task_id, contract['entry'], custody['caller'], resources,
                        custody['valid_until'], custody['owner_grant'], custody['developer_credential'], admission_check=admission)
                finally:
                    fence.close()
                # RECEIVED is a claim, not evidence of code execution/STARTED.
                task = s._task(task_id)
            result = {k: task[k] for k in ('task_id', 'state', 'attempt_id', 'lease_id', 'fence', 'epoch', 'authority_state')}
            result.update(execution_started=False if task['state'] == 'RECEIVED' else task['started_at'] is not None,
                          claim_is_execution=False, next_action='USE_EXISTING_EXECUTION_ENTRY_NOT_RECLAIM')
            return {'jsonrpc': '2.0', 'id': value.get('id'), 'result': {'content': [{'type': 'text', 'text': json.dumps(result, sort_keys=True)}], 'isError': False}}
        finally:
            s.close()


def load_claim_host(development_host, owner_public_key_file, custody_file):
    """Original bootstrap only. Paths are never accepted through MCP.

    Reuses existing validated development bindings and owner public key.
    Custody is existing signed owner grant/developer credential plus trusted
    host caller context, not a new issuer or reconstructed Writer ticket.
    """
    from development_authority import load_public_key
    from secure_file_input import read_owned_secret_file
    from task_center_mcp_development import DevelopmentHost, _read_host_json
    if not isinstance(development_host, DevelopmentHost):
        raise ValueError('EXISTING_DEVELOPMENT_HOST_REQUIRED')
    key = load_public_key(read_owned_secret_file(owner_public_key_file, 'OWNER_PUBLIC_KEY').encode('ascii'))
    def custody(identity, task_id):
        raw = _read_host_json(custody_file, 'EXISTING_REGISTRATION_CUSTODY')
        row = raw.get(task_id) if isinstance(raw, dict) else None
        if not isinstance(row, dict) or set(row) != {'tenant_id', 'principal_id', 'project_id', 'custody'}:
            raise ValueError('EXISTING_TASK_REGISTRATION_CUSTODY_REQUIRED')
        if any(row[k] != identity.get(k) for k in ('tenant_id', 'principal_id', 'project_id')):
            raise ValueError('EXISTING_CUSTODY_IDENTITY_MISMATCH')
        return row['custody']
    return ClaimHost(development_host.bindings, TrustedRegistrationVerifier(key), custody)
