"""Real integration/black-box acceptance facts and fail-closed release gate.

This module stores metadata and evidence references only.  It cannot run a
test, follow a QR code, read a secret, deploy, pay, or send data externally.
Every observation is append-only and bound to one immutable release plan.
"""
from __future__ import print_function

import hashlib
import json
import time

from task_supervisor import canonical
from reusable_task_gateway import _text, _sha


FOUR_STATES = frozenset(('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED'))
GATES = frozenset(('FRONTEND_BACKEND_INTEGRATION', 'PRODUCT_ACCEPTANCE_AI'))
FORBIDDEN_EVIDENCE_KINDS = frozenset((
    'CI', 'UNIT_TEST', 'API_MOCK', 'MOCK', 'QR_CODE', 'SCREENSHOT_ONLY'))
INTEGRATION_CHECKS = (
    'REAL_REQUEST_CONTRACT', 'AUTH_SESSION', 'AUTHORIZATION',
    'FIELDS_ENCODING', 'UPLOAD_SIZE_TIMEOUT', 'IDEMPOTENCY_DUPLICATE',
    'ERROR_CODE_USER_FEEDBACK', 'PERSISTENCE', 'ASYNC_CALLBACK_POLLING',
    'RELOGIN_CROSS_DEVICE', 'SLOW_WEAK_NETWORK', 'FAILURE_RECOVERY')
BLACKBOX_CHECKS = (
    'REAL_ENTRY_AVAILABLE', 'ROLE_MATRIX', 'SECRET_ISOLATION',
    'ENVIRONMENT_BINDING', 'ARTIFACT_BINDING', 'PRIMARY_FLOW',
    'FAILURE_FLOW', 'EVIDENCE_COMPLETE', 'BLOCKERS_CLEARED')
ROLE_KEYS = frozenset((
    'frontend_owner', 'backend_owner', 'integration_owner',
    'acceptance_owner', 'release_owner'))


def ensure_schema(db):
    statements = (
        '''CREATE TABLE IF NOT EXISTS real_acceptance_enforcement(
          tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,policy_version TEXT NOT NULL,
          required_at REAL NOT NULL,PRIMARY KEY(tenant_id,task_id))''',
        '''CREATE TABLE IF NOT EXISTS real_acceptance_plans(
          tenant_id TEXT NOT NULL,plan_id TEXT NOT NULL,task_id TEXT NOT NULL,
          project_template TEXT NOT NULL,legacy_integration_state TEXT,
          entrypoint TEXT NOT NULL,environment TEXT NOT NULL,
          frontend_commit TEXT NOT NULL,frontend_build TEXT NOT NULL,
          frontend_app_version TEXT NOT NULL,backend_commit TEXT NOT NULL,
          backend_image TEXT NOT NULL,api_schema_version TEXT NOT NULL,
          artifact_sha256 TEXT NOT NULL,roles_json TEXT NOT NULL,
          secret_refs_json TEXT NOT NULL,created_by TEXT NOT NULL,
          created_at REAL NOT NULL,plan_sha256 TEXT NOT NULL,
          PRIMARY KEY(tenant_id,plan_id))''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS real_acceptance_plan_task_idx
          ON real_acceptance_plans(tenant_id,task_id,plan_id)''',
        '''CREATE TABLE IF NOT EXISTS real_acceptance_runs(
          tenant_id TEXT NOT NULL,run_id TEXT NOT NULL,plan_id TEXT NOT NULL,
          task_id TEXT NOT NULL,gate_type TEXT NOT NULL,status TEXT NOT NULL,
          responsible TEXT NOT NULL,observed_at REAL NOT NULL,
          entrypoint TEXT NOT NULL,environment TEXT NOT NULL,
          frontend_commit TEXT NOT NULL,frontend_build TEXT NOT NULL,
          frontend_app_version TEXT NOT NULL,backend_commit TEXT NOT NULL,
          backend_image TEXT NOT NULL,api_schema_version TEXT NOT NULL,
          artifact_sha256 TEXT NOT NULL,checklist_json TEXT NOT NULL,
          evidence_json TEXT NOT NULL,blockers_json TEXT NOT NULL,
          recheck_of_json TEXT NOT NULL,run_sha256 TEXT NOT NULL,
          PRIMARY KEY(tenant_id,run_id))''',
        '''CREATE INDEX IF NOT EXISTS real_acceptance_run_plan_idx
          ON real_acceptance_runs(tenant_id,plan_id,gate_type,observed_at,run_id)''',
    )
    with db:
        for statement in statements:
            db.execute(statement)


def _exact(value, keys, code):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(code)
    return value


def _list_text(value, name, allow_empty=False):
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(name + '_REQUIRED')
    for item in value:
        _text(item, name)
    if len(value) != len(set(value)):
        raise ValueError(name + '_DUPLICATE')
    return value


class RealAcceptanceGateway(object):
    """Tenant-bound writer/projection for real acceptance evidence metadata."""

    def __init__(self, db, tenant_id, principal_id, clock=None):
        self.db = db
        self.tenant_id = _text(tenant_id, 'tenant_id')
        self.principal_id = _text(principal_id, 'principal_id')
        self.clock = clock or time.time
        ensure_schema(db)

    @staticmethod
    def validate_plan(value):
        keys = ('task_id', 'project_template', 'legacy_integration_state',
                'entrypoint', 'environment', 'frontend_commit',
                'frontend_build', 'frontend_app_version', 'backend_commit',
                'backend_image', 'api_schema_version', 'artifact_sha256',
                'roles', 'secret_refs')
        _exact(value, keys, 'EXACT_REAL_ACCEPTANCE_PLAN_REQUIRED')
        for name in keys:
            if name not in ('roles', 'secret_refs', 'legacy_integration_state'):
                _text(value[name], name)
        _sha(value['frontend_commit'], 'frontend_commit')
        _sha(value['backend_commit'], 'backend_commit')
        _sha(value['artifact_sha256'], 'artifact_sha256')
        if not (value['entrypoint'].startswith('https://') or
                value['entrypoint'].startswith('http://localhost:')):
            raise ValueError('REAL_ENTRYPOINT_REQUIRED')
        _exact(value['roles'], ROLE_KEYS, 'EXACT_ACCEPTANCE_ROLE_MATRIX_REQUIRED')
        for name, actor in value['roles'].items():
            _text(actor, name)
        if len(set(value['roles'].values())) < 4:
            raise ValueError('INDEPENDENT_ACCEPTANCE_ROLES_REQUIRED')
        if value['legacy_integration_state'] is not None:
            if (value['project_template'] != 'COMMUNITY_REVENUE_SHARE_ADMIN' or
                    value['legacy_integration_state'] != 'LEGACY_NOT_RETROFITTED'):
                raise ValueError('LEGACY_EXCEPTION_SCOPE_REJECTED')
        if not isinstance(value['secret_refs'], list) or not value['secret_refs']:
            raise ValueError('ISOLATED_SECRET_REFS_REQUIRED')
        for item in value['secret_refs']:
            _exact(item, ('secret_ref', 'purpose', 'environment',
                          'isolation_scope', 'isolation_proof_ref'),
                   'EXACT_SECRET_REF_METADATA_REQUIRED')
            for name in item:
                _text(item[name], name)
            if item['environment'] != value['environment']:
                raise ValueError('SECRET_ENVIRONMENT_MISMATCH')
            if item['isolation_scope'] in ('SHARED', 'UNKNOWN'):
                raise ValueError('SECRET_ISOLATION_PROOF_REQUIRED')
        return value

    def register_plan(self, value, now=None):
        value = self.validate_plan(value)
        now = self.clock() if now is None else now
        body = canonical(value)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        plan_id = hashlib.sha256(canonical({
            'tenant': self.tenant_id, 'task': value['task_id'],
            'plan': digest}).encode('utf-8')).hexdigest()
        existing = self.db.execute('''SELECT plan_sha256 FROM real_acceptance_plans
          WHERE tenant_id=? AND plan_id=?''', (self.tenant_id, plan_id)).fetchone()
        if existing:
            if existing['plan_sha256'] != digest:
                raise ValueError('ACCEPTANCE_PLAN_ID_CONFLICT')
            return {'plan_id': plan_id, 'plan_sha256': digest, 'duplicate': True}
        with self.db:
            self.db.execute('''INSERT INTO real_acceptance_plans VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
              self.tenant_id, plan_id, value['task_id'], value['project_template'],
              value['legacy_integration_state'], value['entrypoint'],
              value['environment'], value['frontend_commit'],
              value['frontend_build'], value['frontend_app_version'],
              value['backend_commit'], value['backend_image'],
              value['api_schema_version'], value['artifact_sha256'],
              canonical(value['roles']), canonical(value['secret_refs']),
              self.principal_id, now, digest))
        return {'plan_id': plan_id, 'plan_sha256': digest, 'duplicate': False}

    def mark_task_required(self, task_id, now=None):
        now = self.clock() if now is None else now
        with self.db:
            self.db.execute('''INSERT OR IGNORE INTO real_acceptance_enforcement
              VALUES (?,?,?,?)''', (self.tenant_id, _text(task_id, 'task_id'),
              'REAL_BLACKBOX_V1_20261106', now))
        return {'task_id': task_id, 'required': True,
                'policy_version': 'REAL_BLACKBOX_V1_20261106'}

    def _plan(self, plan_id):
        row = self.db.execute('''SELECT * FROM real_acceptance_plans WHERE
          tenant_id=? AND plan_id=?''', (self.tenant_id, plan_id)).fetchone()
        if row is None:
            raise KeyError(plan_id)
        return dict(row)

    def record_run(self, value, now=None):
        keys = ('run_id', 'plan_id', 'gate_type', 'status', 'responsible',
                'observed_at', 'entrypoint', 'environment', 'frontend_commit',
                'frontend_build', 'frontend_app_version', 'backend_commit',
                'backend_image', 'api_schema_version', 'artifact_sha256',
                'checklist', 'evidence', 'blockers', 'recheck_of')
        _exact(value, keys, 'EXACT_REAL_ACCEPTANCE_RUN_REQUIRED')
        for name in keys:
            if name not in ('checklist', 'evidence', 'blockers', 'recheck_of'):
                _text(value[name], name) if name != 'observed_at' else None
        if value['gate_type'] not in GATES or value['status'] not in FOUR_STATES:
            raise ValueError('FOUR_STATE_GATE_REQUIRED')
        plan = self._plan(value['plan_id'])
        if value['responsible'] != json.loads(plan['roles_json'])[
                'integration_owner' if value['gate_type'] ==
                'FRONTEND_BACKEND_INTEGRATION' else 'acceptance_owner']:
            raise ValueError('GATE_RESPONSIBLE_MISMATCH')
        if self.principal_id != value['responsible']:
            raise ValueError('AUTHENTICATED_GATE_RESPONSIBLE_REQUIRED')
        if self.principal_id != value['responsible']:
            raise ValueError('AUTHENTICATED_GATE_RESPONSIBLE_REQUIRED')
        binding_fields = ('entrypoint', 'environment', 'frontend_commit',
                          'frontend_build', 'frontend_app_version',
                          'backend_commit', 'backend_image',
                          'api_schema_version', 'artifact_sha256')
        if any(value[name] != plan[name] for name in binding_fields):
            raise ValueError('ACCEPTANCE_VERSION_OR_ENVIRONMENT_MISMATCH')
        _sha(value['frontend_commit'], 'frontend_commit')
        _sha(value['backend_commit'], 'backend_commit')
        _sha(value['artifact_sha256'], 'artifact_sha256')
        required = (INTEGRATION_CHECKS if value['gate_type'] ==
                    'FRONTEND_BACKEND_INTEGRATION' else BLACKBOX_CHECKS)
        if not isinstance(value['checklist'], list):
            raise ValueError('EXACT_GATE_CHECKLIST_REQUIRED')
        seen = set()
        for item in value['checklist']:
            _exact(item, ('id', 'status', 'evidence_refs'),
                   'EXACT_GATE_CHECK_REQUIRED')
            if item['id'] in seen or item['id'] not in required:
                raise ValueError('GATE_CHECK_COVERAGE_MISMATCH')
            seen.add(item['id'])
            if item['status'] not in FOUR_STATES:
                raise ValueError('FOUR_STATE_GATE_REQUIRED')
            _list_text(item['evidence_refs'], 'CHECK_EVIDENCE',
                       allow_empty=item['status'] != 'PASS')
        if seen != set(required):
            raise ValueError('GATE_CHECK_COVERAGE_MISMATCH')
        if not isinstance(value['evidence'], list) or not value['evidence']:
            raise ValueError('REAL_EVIDENCE_REQUIRED')
        for evidence in value['evidence']:
            _exact(evidence, ('evidence_ref', 'kind', 'source', 'observed_at'),
                   'EXACT_REAL_EVIDENCE_REQUIRED')
            for name in evidence:
                _text(evidence[name], name)
            if evidence['kind'] in FORBIDDEN_EVIDENCE_KINDS:
                raise ValueError('SUBSTITUTE_EVIDENCE_REJECTED')
        _list_text(value['blockers'], 'BLOCKERS', allow_empty=True)
        _list_text(value['recheck_of'], 'RECHECK_OF', allow_empty=True)
        all_pass = all(x['status'] == 'PASS' for x in value['checklist'])
        if value['status'] == 'PASS' and (not all_pass or value['blockers']):
            raise ValueError('PASS_REQUIRES_ALL_CHECKS_AND_NO_BLOCKERS')
        if value['status'] != 'PASS' and all_pass and not value['blockers']:
            raise ValueError('NON_PASS_REASON_REQUIRED')
        if value['recheck_of']:
            prior = list(self.db.execute('''SELECT run_id,status FROM
              real_acceptance_runs WHERE tenant_id=? AND plan_id=? AND
              gate_type=?''', (self.tenant_id, value['plan_id'],
              value['gate_type'])))
            prior_ids = {x['run_id'] for x in prior if x['status'] != 'PASS'}
            if not set(value['recheck_of']).issubset(prior_ids):
                raise ValueError('RECHECK_MUST_REFERENCE_PRIOR_NON_PASS')
        latest = self._latest(value['plan_id'], value['gate_type'])
        if (value['status'] == 'PASS' and latest is not None and
                latest['status'] != 'PASS' and
                latest['run_id'] not in value['recheck_of']):
            raise ValueError('FIX_REQUIRES_SAME_BINDING_RECHECK')
        if value['gate_type'] == 'PRODUCT_ACCEPTANCE_AI':
            self.require_integration(value['plan_id'])
        body = canonical(value)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        existing = self.db.execute('''SELECT run_sha256 FROM real_acceptance_runs
          WHERE tenant_id=? AND run_id=?''', (self.tenant_id,
          value['run_id'])).fetchone()
        if existing:
            if existing['run_sha256'] != digest:
                raise ValueError('APPEND_ONLY_RUN_CONFLICT')
            return {'run_id': value['run_id'], 'status': value['status'],
                    'duplicate': True}
        with self.db:
            self.db.execute('''INSERT INTO real_acceptance_runs VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
              self.tenant_id, value['run_id'], value['plan_id'], plan['task_id'],
              value['gate_type'], value['status'], value['responsible'],
              float(value['observed_at']), value['entrypoint'],
              value['environment'], value['frontend_commit'],
              value['frontend_build'], value['frontend_app_version'],
              value['backend_commit'], value['backend_image'],
              value['api_schema_version'], value['artifact_sha256'],
              canonical(value['checklist']), canonical(value['evidence']),
              canonical(value['blockers']), canonical(value['recheck_of']), digest))
        return {'run_id': value['run_id'], 'status': value['status'],
                'duplicate': False}

    def _latest(self, plan_id, gate_type):
        row = self.db.execute('''SELECT * FROM real_acceptance_runs WHERE
          tenant_id=? AND plan_id=? AND gate_type=? ORDER BY observed_at DESC,
          rowid DESC LIMIT 1''', (self.tenant_id, plan_id, gate_type)).fetchone()
        return dict(row) if row else None

    def require_integration(self, plan_id):
        plan = self._plan(plan_id)
        if plan['legacy_integration_state'] == 'LEGACY_NOT_RETROFITTED':
            return {'state': 'LEGACY_NOT_RETROFITTED', 'pass': False,
                    'legacy_exception': True}
        run = self._latest(plan_id, 'FRONTEND_BACKEND_INTEGRATION')
        if run is None or run['status'] != 'PASS':
            raise ValueError('INTEGRATION_GATE_NOT_PASS')
        return {'state': 'PASS', 'run_id': run['run_id'], 'pass': True,
                'legacy_exception': False}

    def release_gate(self, plan_id):
        integration = self.require_integration(plan_id)
        if integration['pass'] is not True:
            raise ValueError('INTEGRATION_GATE_NOT_PASS')
        blackbox = self._latest(plan_id, 'PRODUCT_ACCEPTANCE_AI')
        if blackbox is None or blackbox['status'] != 'PASS':
            raise ValueError('REAL_BLACKBOX_GATE_NOT_PASS')
        return {'state': 'PASS', 'plan_id': plan_id,
                'integration': integration, 'blackbox_run_id': blackbox['run_id']}

    def require_task_release(self, task_id):
        plan = self.db.execute('''SELECT plan_id FROM real_acceptance_plans WHERE
          tenant_id=? AND task_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1''',
          (self.tenant_id, task_id)).fetchone()
        if plan is None:
            required = self.db.execute('''SELECT 1 FROM
              real_acceptance_enforcement WHERE tenant_id=? AND task_id=?''',
              (self.tenant_id, task_id)).fetchone()
            if required is not None:
                raise ValueError('REAL_ACCEPTANCE_PLAN_REQUIRED')
            return {'state': 'LEGACY_RECORD_NO_REAL_ACCEPTANCE_PLAN',
                    'enforced': False}
        result = self.release_gate(plan['plan_id'])
        result['enforced'] = True
        return result

    def projection(self):
        plans = []
        for row in self.db.execute('''SELECT * FROM real_acceptance_plans WHERE
          tenant_id=? ORDER BY created_at,plan_id''', (self.tenant_id,)):
            item = dict(row)
            item['roles'] = json.loads(item.pop('roles_json'))
            item['secret_refs'] = json.loads(item.pop('secret_refs_json'))
            item['integration'] = self._latest(item['plan_id'],
                                               'FRONTEND_BACKEND_INTEGRATION')
            item['blackbox'] = self._latest(item['plan_id'],
                                            'PRODUCT_ACCEPTANCE_AI')
            plans.append(item)
        runs = [dict(x) for x in self.db.execute('''SELECT * FROM
          real_acceptance_runs WHERE tenant_id=? ORDER BY observed_at,run_id''',
          (self.tenant_id,))]
        return {'plans': plans, 'runs': runs, 'states': sorted(FOUR_STATES),
                'release_policy': 'FAIL_CLOSED',
                'substitute_evidence_rejected': sorted(FORBIDDEN_EVIDENCE_KINDS),
                'community_template': {
                  'project_template': 'COMMUNITY_REVENUE_SHARE_ADMIN',
                  'surface': 'MANAGEMENT_BACKEND',
                  'mini_program': 'REFERENCE_ONLY',
                  'mini_program_responsible': '小新',
                  'mini_program_task_created': False,
                  'sensitive_data': 'REAL_ID_PAYMENT_OUTBOUND_FORBIDDEN'}}
