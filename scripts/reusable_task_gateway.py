"""Reusable TEST_ONLY Task Gateway on the canonical Supervisor ledger.

The module deliberately reuses ``task_supervisor.tasks/events/outbox`` as the
single task and event authority.  Its tables contain graph requirements,
durable consumer acknowledgements, checkpoints and read projections only.
It grants no production dispatch, credential, tenant, or distributed-lock
capability.
"""
from __future__ import print_function

import hashlib
import hmac
import json
import math
import sqlite3

from task_supervisor import Supervisor, UNKNOWN, canonical
from task_writer_fence import Fence


TEST_ONLY = 'TEST_ONLY'
BOARDS = frozenset(('operations', 'customer', 'research-development',
                    'acceptance-delivery', 'maintenance',
                    'shared-ecosystem', 'finance'))
MODULE_CONTRACTS = (
    {
        'module_id': 'xuanjun.scheduler.kernel', 'version': '1.0.0-test',
        'capabilities': ['dynamic-task-graph', 'durable-outbox',
                         'safe-checkpoint-resume'],
        'input_schema': 'TaskGraph.v1', 'output_schema': 'TaskResult.v1',
        'tenant_source': 'trusted-server-context',
        'resource_owner': 'canonical-supervisor-ledger',
        'lifecycle': 'TEST_ONLY', 'compatibility': 'supervisor-schema-v3',
    },
    {
        'module_id': 'xuanjun.digital-twin.projection',
        'version': '1.0.0-test',
        'capabilities': ['read-projection', 'restart-rebuild'],
        'input_schema': 'CanonicalLedger.v3',
        'output_schema': 'DigitalTwinProjection.v1',
        'tenant_source': 'trusted-server-context',
        'resource_owner': 'read-only-projection',
        'lifecycle': 'TEST_ONLY', 'compatibility': 'scheduler-kernel-1.x',
    },
)


def _digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError('NONEMPTY_%s_REQUIRED' % name.upper())
    return value


def _sha(value, name):
    if (not isinstance(value, str) or len(value) != 64
            or any(ch not in '0123456789abcdef' for ch in value)):
        raise ValueError('CANONICAL_%s_REQUIRED' % name.upper())
    return value


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('FINITE_%s_REQUIRED' % name.upper())
    return value


class TestTenantAuthority(object):
    """HMAC test authority; raw client tenant_id is never trusted."""

    issuer = 'TEST_AUTHORITY'
    audience = 'xuanjun.scheduler.kernel'

    def __init__(self, key):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError('TEST_AUTHORITY_KEY_REQUIRED')
        self._key = key

    def issue(self, tenant_id, principal_id):
        body = {'issuer': self.issuer, 'audience': self.audience,
                'tenant_id': _text(tenant_id, 'tenant_id'),
                'principal_id': _text(principal_id, 'principal_id')}
        body['assertion_sha256'] = hmac.new(
            self._key, canonical(body).encode('utf-8'), hashlib.sha256
        ).hexdigest()
        return body

    def verify(self, value):
        if not isinstance(value, dict):
            raise ValueError('TRUSTED_TENANT_CONTEXT_REQUIRED')
        required = {'issuer', 'audience', 'tenant_id', 'principal_id',
                    'assertion_sha256'}
        if set(value) != required:
            raise ValueError('TRUSTED_TENANT_CONTEXT_REQUIRED')
        unsigned = {key: value[key] for key in required
                    if key != 'assertion_sha256'}
        expected = hmac.new(self._key, canonical(unsigned).encode('utf-8'),
                            hashlib.sha256).hexdigest()
        if (value['issuer'] != self.issuer
                or value['audience'] != self.audience
                or not hmac.compare_digest(expected,
                                           value['assertion_sha256'])):
            raise ValueError('TRUSTED_TENANT_CONTEXT_REQUIRED')
        return value['tenant_id']


class GatewayKernel(object):
    """Gateway contract backed by one existing Supervisor SQLite database."""

    def __init__(self, supervisor, tenant_authority, clock=None):
        if not isinstance(supervisor, Supervisor):
            raise ValueError('CANONICAL_SUPERVISOR_REQUIRED')
        self.supervisor = supervisor
        self.db = supervisor.db
        self.clock = clock or supervisor.clock
        self.tenants = tenant_authority
        self._schema()

    def _schema(self):
        statements = (
            '''CREATE TABLE IF NOT EXISTS gateway_graphs(
              graph_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,
              project_id TEXT NOT NULL,graph_version TEXT NOT NULL,
              graph_sha256 TEXT NOT NULL,created_at REAL NOT NULL,
              UNIQUE(tenant_id,project_id,graph_version))''',
            '''CREATE TABLE IF NOT EXISTS gateway_task_metadata(
              task_id TEXT PRIMARY KEY,graph_id TEXT NOT NULL,
              tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,
              node_id TEXT NOT NULL,input_version TEXT NOT NULL,
              output_version TEXT NOT NULL,priority INTEGER NOT NULL,
              preemptible INTEGER NOT NULL,module_id TEXT NOT NULL,
              resources_json TEXT NOT NULL,board_id TEXT NOT NULL,
              FOREIGN KEY(task_id) REFERENCES tasks(task_id),
              FOREIGN KEY(graph_id) REFERENCES gateway_graphs(graph_id))''',
            '''CREATE TABLE IF NOT EXISTS gateway_dependencies(
              consumer_task_id TEXT NOT NULL,producer_task_id TEXT NOT NULL,
              required_version TEXT NOT NULL,required_evidence_ref TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'WAITING',event_attempt_id TEXT,
              event_id TEXT,
              updated_at REAL NOT NULL,
              PRIMARY KEY(consumer_task_id,producer_task_id),
              FOREIGN KEY(consumer_task_id) REFERENCES tasks(task_id),
              FOREIGN KEY(producer_task_id) REFERENCES tasks(task_id))''',
            '''CREATE TABLE IF NOT EXISTS gateway_inbox(
              tenant_id TEXT NOT NULL,event_id TEXT NOT NULL,
              producer_task_id TEXT NOT NULL,producer_attempt_id TEXT NOT NULL,
              output_version TEXT NOT NULL,evidence_ref TEXT NOT NULL,
              state TEXT NOT NULL,received_at REAL NOT NULL,acked_at REAL,
              payload_sha256 TEXT NOT NULL,
              PRIMARY KEY(tenant_id,producer_task_id,producer_attempt_id,event_id))''',
            '''CREATE TABLE IF NOT EXISTS gateway_checkpoints(
              task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
              checkpoint_id TEXT NOT NULL,payload_json TEXT NOT NULL,
              inflight_json TEXT NOT NULL,effects_state TEXT NOT NULL,
              resources_json TEXT NOT NULL,created_at REAL NOT NULL,
              PRIMARY KEY(task_id,attempt_id,checkpoint_id),
              FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
            '''CREATE TABLE IF NOT EXISTS gateway_resource_releases(
              task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
              checkpoint_id TEXT NOT NULL,coverage_digest TEXT NOT NULL,
              evidence_ref TEXT NOT NULL,released_at REAL NOT NULL,
              PRIMARY KEY(task_id,attempt_id),
              FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
            '''CREATE TABLE IF NOT EXISTS gateway_resume_grants(
              grant_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,
              checkpoint_id TEXT NOT NULL,dependency_event_ids_json TEXT NOT NULL,
              state TEXT NOT NULL,valid_until REAL NOT NULL,
              created_at REAL NOT NULL,used_at REAL,
              FOREIGN KEY(task_id) REFERENCES tasks(task_id))''',
            '''CREATE TABLE IF NOT EXISTS gateway_delivery_receipts(
              task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,event_id TEXT NOT NULL,
              phase TEXT NOT NULL,evidence_ref TEXT NOT NULL,
              observed_at REAL NOT NULL,
              PRIMARY KEY(task_id,attempt_id,event_id,phase))''',
            '''CREATE TABLE IF NOT EXISTS gateway_module_contracts(
              module_id TEXT NOT NULL,version TEXT NOT NULL,contract_json TEXT NOT NULL,
              contract_sha256 TEXT NOT NULL,PRIMARY KEY(module_id,version))''',
            '''CREATE INDEX IF NOT EXISTS gateway_dependency_state_idx
               ON gateway_dependencies(consumer_task_id,state)''',
            '''CREATE INDEX IF NOT EXISTS gateway_task_tenant_idx
               ON gateway_task_metadata(tenant_id,project_id,task_id)''',
        )
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            for statement in statements:
                self.db.execute(statement)
            for contract in MODULE_CONTRACTS:
                body = canonical(contract)
                self.db.execute('''INSERT OR IGNORE INTO gateway_module_contracts
                  VALUES (?,?,?,?)''', (contract['module_id'],
                  contract['version'], body,
                  hashlib.sha256(body.encode('utf-8')).hexdigest()))

    @staticmethod
    def _graph_shape(value):
        required = {'graph_id', 'tenant_id', 'project_id', 'graph_version',
                    'tasks'}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError('EXACT_TASK_GRAPH_REQUIRED')
        for name in required - {'tasks'}:
            _text(value[name], name)
        if not isinstance(value['tasks'], list) or not value['tasks']:
            raise ValueError('NONEMPTY_TASK_GRAPH_REQUIRED')
        task_required = {'task_id', 'node_id', 'stage', 'owner', 'entry',
                         'checkpoint_sha256', 'spec_sha256', 'input_version',
                         'output_version', 'priority', 'preemptible',
                         'module_id', 'resources', 'dependencies', 'board_id',
                         'completion_evidence'}
        ids = []
        for task in value['tasks']:
            if not isinstance(task, dict) or set(task) != task_required:
                raise ValueError('EXACT_GRAPH_TASK_REQUIRED')
            for name in ('task_id', 'node_id', 'stage', 'owner', 'entry',
                         'input_version', 'output_version', 'module_id',
                         'board_id'):
                _text(task[name], name)
            if task['board_id'] not in BOARDS:
                raise ValueError('CANONICAL_BOARD_REQUIRED')
            _sha(task['checkpoint_sha256'], 'checkpoint_sha256')
            _sha(task['spec_sha256'], 'spec_sha256')
            if (type(task['priority']) is not int or task['priority'] < 0
                    or type(task['preemptible']) is not bool
                    or not isinstance(task['resources'], list)
                    or not task['resources']
                    or len(task['resources']) != len(set(task['resources']))
                    or any(not isinstance(x, str) or not x for x in
                           task['resources'])
                    or not isinstance(task['dependencies'], list)
                    or not isinstance(task['completion_evidence'], list)
                    or not task['completion_evidence']):
                raise ValueError('EXACT_GRAPH_TASK_REQUIRED')
            ids.append(task['task_id'])
        if len(ids) != len(set(ids)):
            raise ValueError('DUPLICATE_GRAPH_TASK')
        known = set(ids)
        for task in value['tasks']:
            for dep in task['dependencies']:
                if (not isinstance(dep, dict)
                        or set(dep) != {'task_id', 'version', 'evidence_ref'}
                        or dep['task_id'] not in known
                        or dep['task_id'] == task['task_id']):
                    raise ValueError('EXACT_GRAPH_DEPENDENCY_REQUIRED')
                _text(dep['version'], 'dependency_version')
                _text(dep['evidence_ref'], 'dependency_evidence_ref')
        # Directed-cycle rejection.
        edges = {t['task_id']: [d['task_id'] for d in t['dependencies']]
                 for t in value['tasks']}
        visiting, done = set(), set()
        def visit(node):
            if node in visiting:
                raise ValueError('CYCLIC_TASK_GRAPH')
            if node in done:
                return
            visiting.add(node)
            for dependency in edges[node]:
                visit(dependency)
            visiting.remove(node); done.add(node)
        for node in sorted(edges):
            visit(node)
        return value

    def register_graph(self, context, value, now=None):
        tenant_id = self.tenants.verify(context)
        value = self._graph_shape(value)
        if tenant_id != value['tenant_id']:
            raise ValueError('CROSS_TENANT_GRAPH_REJECTED')
        now = self.clock() if now is None else _finite(now, 'time')
        graph_body = canonical(value)
        graph_sha = hashlib.sha256(graph_body.encode('utf-8')).hexdigest()
        existing = self.db.execute(
            'SELECT graph_sha256 FROM gateway_graphs WHERE graph_id=?',
            (value['graph_id'],)).fetchone()
        if existing is not None:
            if existing['graph_sha256'] == graph_sha:
                return {'duplicate': True, 'graph_sha256': graph_sha}
            raise ValueError('TASK_GRAPH_ID_CONFLICT')
        # Full shape validation above makes each canonical Supervisor insert
        # deterministic.  Graph visibility is committed only after all tasks.
        for task in value['tasks']:
            self.supervisor.register({
                'task_id': task['task_id'],
                'parent_task_id': value['project_id'], 'stage': task['stage'],
                'owner': task['owner'], 'entry': task['entry'],
                'checkpoint_sha256': task['checkpoint_sha256'],
                'spec_sha256': task['spec_sha256'],
                'next_action': 'WAIT_DEPENDENCIES' if task['dependencies']
                               else 'CLAIM_TEST_ONLY_EXECUTOR',
                'dependencies': [x['task_id'] for x in task['dependencies']],
                'completion_conditions': task['completion_evidence'],
                'progress_deadline': now + 900,
                'receipt_deadline': now + 300,
                'started_deadline': now + 600,
                'terminal_deadline': now + 3600,
                'handoff_deadline': now + 900,
            }, now=now)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('INSERT INTO gateway_graphs VALUES (?,?,?,?,?,?)',
                (value['graph_id'], tenant_id, value['project_id'],
                 value['graph_version'], graph_sha, now))
            for task in value['tasks']:
                self.db.execute('''INSERT INTO gateway_task_metadata
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (task['task_id'], value['graph_id'], tenant_id,
                   value['project_id'], task['node_id'], task['input_version'],
                   task['output_version'], task['priority'],
                   int(task['preemptible']), task['module_id'],
                   canonical(sorted(task['resources'])), task['board_id']))
                for dep in task['dependencies']:
                    self.db.execute('''INSERT INTO gateway_dependencies
                      VALUES (?,?,?,?,?,?,?,?)''',
                      (task['task_id'], dep['task_id'], dep['version'],
                       dep['evidence_ref'], 'WAITING', None, None, now))
        return {'duplicate': False, 'graph_sha256': graph_sha}

    def task_tenant(self, task_id):
        row = self.db.execute('''SELECT tenant_id FROM gateway_task_metadata
          WHERE task_id=?''', (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return row['tenant_id']

    def assert_task_context(self, context, task_id):
        tenant_id = self.tenants.verify(context)
        if tenant_id != self.task_tenant(task_id):
            raise ValueError('CROSS_TENANT_ACCESS_REJECTED')
        return tenant_id

    def canonical_resources(self, task_id):
        row = self.db.execute('''SELECT resources_json FROM
          gateway_task_metadata WHERE task_id=?''', (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return json.loads(row['resources_json'])

    def assert_claim_resources(self, context, task_id, resources):
        self.assert_task_context(context, task_id)
        if (not isinstance(resources, list)
                or sorted(resources) != self.canonical_resources(task_id)):
            raise ValueError('REGISTERED_RESOURCE_SCOPE_REQUIRED')
        return list(self.canonical_resources(task_id))

    def mark_outbox_sent(self, context, outbox_id, evidence_ref, now=None):
        row = self.db.execute('SELECT * FROM outbox WHERE outbox_id=?',
                              (outbox_id,)).fetchone()
        if row is None:
            raise KeyError(outbox_id)
        self.assert_task_context(context, row['task_id'])
        now = self.clock() if now is None else _finite(now, 'time')
        result = self.supervisor.outbox_result(outbox_id, True, now=now)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT OR IGNORE INTO gateway_delivery_receipts
              VALUES (?,?,?,?,?,?)''', (row['task_id'], row['attempt_id'],
                row['event_id'], 'SENT', _text(evidence_ref, 'evidence_ref'),
                now))
        return result

    def receive_outbox(self, context, outbox_id, now=None):
        tenant_id = self.tenants.verify(context)
        row = self.db.execute('SELECT * FROM outbox WHERE outbox_id=?',
                              (outbox_id,)).fetchone()
        if row is None:
            raise KeyError(outbox_id)
        if row['delivered_at'] is None:
            raise ValueError('OUTBOX_NOT_SENT')
        if self.task_tenant(row['task_id']) != tenant_id:
            raise ValueError('CROSS_TENANT_EVENT_REJECTED')
        meta = self.db.execute('''SELECT * FROM gateway_task_metadata
          WHERE task_id=?''', (row['task_id'],)).fetchone()
        payload = json.loads(row['payload_json'])
        evidence = payload.get('completion_evidence')
        evidence_ref = UNKNOWN
        if isinstance(evidence, list) and len(evidence) == 1:
            item = evidence[0]
            if isinstance(item, dict):
                evidence_ref = item.get('evidence_ref', UNKNOWN)
        now = self.clock() if now is None else _finite(now, 'time')
        payload_sha = hashlib.sha256(
            row['payload_json'].encode('utf-8')).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            prior = self.db.execute('''SELECT * FROM gateway_inbox
              WHERE tenant_id=? AND producer_task_id=?
              AND producer_attempt_id=? AND event_id=?''',
              (tenant_id, row['task_id'], row['attempt_id'],
               row['event_id'])).fetchone()
            exact = (tenant_id, row['event_id'], row['task_id'],
                     row['attempt_id'], meta['output_version'], evidence_ref,
                     payload_sha)
            if prior is not None:
                actual = (prior['tenant_id'], prior['event_id'],
                          prior['producer_task_id'],
                          prior['producer_attempt_id'], prior['output_version'],
                          prior['evidence_ref'], prior['payload_sha256'])
                if actual != exact:
                    raise ValueError('EVENT_ID_REUSE_CONFLICT')
                return {'duplicate': True, 'state': prior['state']}
            self.db.execute('''INSERT INTO gateway_inbox
              VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (tenant_id, row['event_id'], row['task_id'], row['attempt_id'],
               meta['output_version'], evidence_ref, 'RECEIVED', now, None,
               payload_sha))
        return {'duplicate': False, 'state': 'RECEIVED'}

    def acknowledge_event(self, context, producer_task_id,
                          producer_attempt_id=None, event_id=None, now=None):
        # Compatibility for the original single-identity API is deliberately
        # limited to an unambiguous row.  New callers pass the complete event
        # identity: producer task + attempt + event.
        if event_id is None:
            if producer_attempt_id is not None:
                if now is not None:
                    raise ValueError('AMBIGUOUS_EVENT_ACK_ARGUMENTS')
                now = producer_attempt_id
            event_id = producer_task_id
            producer_task_id = None
        tenant_id = self.tenants.verify(context)
        now = self.clock() if now is None else _finite(now, 'time')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            if producer_task_id is None:
                matches = list(self.db.execute('''SELECT * FROM gateway_inbox
                  WHERE tenant_id=? AND event_id=?''',
                  (tenant_id, event_id)))
                if len(matches) != 1:
                    raise ValueError('COMPLETE_EVENT_IDENTITY_REQUIRED')
                event = matches[0]
            else:
                event = self.db.execute('''SELECT * FROM gateway_inbox
                  WHERE tenant_id=? AND producer_task_id=?
                  AND producer_attempt_id=? AND event_id=?''',
                  (tenant_id, producer_task_id, producer_attempt_id,
                   event_id)).fetchone()
            if event is None:
                raise KeyError(event_id)
            if event['state'] == 'CONSUMED_ACK':
                return {'duplicate': True, 'state': 'CONSUMED_ACK'}
            if event['state'] != 'RECEIVED':
                raise ValueError('EVENT_NOT_RECEIVED')
            dependencies = list(self.db.execute('''SELECT * FROM
              gateway_dependencies WHERE producer_task_id=?''',
              (event['producer_task_id'],)))
            matched = 0
            for dep in dependencies:
                consumer_tenant = self.task_tenant(dep['consumer_task_id'])
                if consumer_tenant != tenant_id:
                    raise ValueError('CROSS_TENANT_DEPENDENCY_REJECTED')
                if (dep['required_version'] == event['output_version']
                        and dep['required_evidence_ref'] ==
                            event['evidence_ref']):
                    self.db.execute('''UPDATE gateway_dependencies
                      SET state='RECEIVED',event_attempt_id=?,event_id=?,
                      updated_at=?
                      WHERE consumer_task_id=? AND producer_task_id=?''',
                      (event['producer_attempt_id'], event_id, now,
                       dep['consumer_task_id'],
                       dep['producer_task_id']))
                    matched += 1
                    remaining = self.db.execute('''SELECT COUNT(*) FROM
                      gateway_dependencies WHERE consumer_task_id=?
                      AND state!='RECEIVED' ''',
                      (dep['consumer_task_id'],)).fetchone()[0]
                    if remaining == 0:
                        self.db.execute('''UPDATE tasks SET
                          next_action='RESUME_ADMISSION_REQUIRED',
                          receipt_deadline=?,started_deadline=?,
                          progress_deadline=?,terminal_deadline=?,
                          handoff_deadline=?,updated_at=?
                          WHERE task_id=? AND state='READY' ''',
                          (now + 300, now + 600, now + 900, now + 3600,
                           now + 900, now, dep['consumer_task_id']))
            self.db.execute('''UPDATE gateway_inbox
              SET state='CONSUMED_ACK',acked_at=?
              WHERE tenant_id=? AND producer_task_id=?
              AND producer_attempt_id=? AND event_id=?''',
              (now, tenant_id, event['producer_task_id'],
               event['producer_attempt_id'], event_id))
            self.db.execute('''INSERT OR IGNORE INTO gateway_delivery_receipts
              VALUES (?,?,?,?,?,?)''',
              (event['producer_task_id'], event['producer_attempt_id'],
               event_id, 'CONSUMED_ACK', event['payload_sha256'], now))
            return {'duplicate': False, 'state': 'CONSUMED_ACK',
                    'matched_dependencies': matched}

    def save_checkpoint(self, context, task_id, attempt_id, checkpoint_id,
                        payload, inflight, effects_state, resources, now=None):
        self.assert_task_context(context, task_id)
        if (not isinstance(payload, dict) or not isinstance(inflight, list)
                or effects_state not in ('RECONCILED', UNKNOWN)
                or not isinstance(resources, list)
                or not resources or len(resources) != len(set(resources))):
            raise ValueError('EXACT_CHECKPOINT_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            # Authority time is sampled only after the serialization lock is
            # held.  A caller that waited behind a writer must not use a
            # pre-lock timestamp to cross an authority expiry boundary.
            supplied_now = None if now is None else _finite(now, 'time')
            now = max(self.clock(), supplied_now) if supplied_now is not None else self.clock()
            task = self.supervisor._task(task_id)
            if task['attempt_id'] != attempt_id:
                raise ValueError('CHECKPOINT_ATTEMPT_MISMATCH')
            if (task['authority_state'] != 'VALID' or
                    task['authority_valid_until'] is None or
                    not now < task['authority_valid_until']):
                raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
            self.db.execute('''INSERT INTO gateway_checkpoints VALUES
              (?,?,?,?,?,?,?,?)''',
              (task_id, attempt_id, _text(checkpoint_id, 'checkpoint_id'),
               canonical(payload), canonical(inflight), effects_state,
               canonical(sorted(resources)), now))
            self.db.commit()
        except Exception:
            self.db.rollback();raise
        return {'checkpoint_id': checkpoint_id, 'effects_state': effects_state}

    def save_waiting_checkpoint(self, context, task_id, prior_attempt_id,
                                checkpoint_id, payload, resources, now=None):
        """Persist a prior-attempt checkpoint for a dependency-waiting task."""
        self.assert_task_context(context, task_id)
        task = self.supervisor._task(task_id)
        waiting = self.db.execute('''SELECT COUNT(*) AS n FROM
          gateway_dependencies WHERE consumer_task_id=? AND state!='RECEIVED' ''',
          (task_id,)).fetchone()['n']
        meta = self.db.execute('''SELECT resources_json FROM
          gateway_task_metadata WHERE task_id=?''', (task_id,)).fetchone()
        if (task['state'] != 'READY' or task['authority_state'] != 'NONE'
                or not waiting or not isinstance(payload, dict)
                or sorted(resources) != sorted(json.loads(
                    meta['resources_json']))):
            raise ValueError('DEPENDENCY_WAITING_CHECKPOINT_REQUIRED')
        now = self.clock() if now is None else _finite(now, 'time')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT INTO gateway_checkpoints VALUES
              (?,?,?,?,?,?,?,?)''',
              (task_id, _text(prior_attempt_id, 'prior_attempt_id'),
               _text(checkpoint_id, 'checkpoint_id'), canonical(payload),
               '[]', 'RECONCILED', canonical(sorted(resources)), now))
        return {'checkpoint_id': checkpoint_id,
                'prior_attempt_id': prior_attempt_id,
                'state': 'WAITING_DEPENDENCY'}

    def release_revoked_resources(self, context, task_id, attempt_id,
                                  checkpoint_id, evidence_ref, now=None,
                                  resume_ready=True):
        self.assert_task_context(context, task_id)
        now = self.clock() if now is None else _finite(now, 'time')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self.supervisor._task(task_id)
            checkpoint = self.db.execute('''SELECT * FROM gateway_checkpoints
              WHERE task_id=? AND attempt_id=? AND checkpoint_id=?''',
              (task_id, attempt_id, checkpoint_id)).fetchone()
            if (task['attempt_id'] != attempt_id
                    or task['authority_state'] != 'REVOKED'
                    or task['coverage_digest'] in ('', UNKNOWN)
                    or checkpoint is None
                    or checkpoint['effects_state'] != 'RECONCILED'
                    or json.loads(checkpoint['inflight_json'])
                    or sorted(json.loads(checkpoint['resources_json'])) !=
                       sorted(json.loads(task['resource_scope_json']))):
                raise ValueError('SAFE_RESOURCE_RELEASE_EVIDENCE_REQUIRED')
            self.db.execute('''DELETE FROM resource_claims
              WHERE task_id=? AND attempt_id=? AND state='REVOKED' ''',
              (task_id, attempt_id))
            if self.db.execute('SELECT changes()').fetchone()[0] < 1:
                raise ValueError('REVOKED_RESOURCE_CLAIM_REQUIRED')
            self.db.execute('''INSERT INTO gateway_resource_releases
              VALUES (?,?,?,?,?,?)''',
              (task_id, attempt_id, checkpoint_id, task['coverage_digest'],
               _text(evidence_ref, 'release_evidence'), now))
            if resume_ready:
                self.db.execute("""UPDATE tasks SET state='READY',
                  authority_state='NONE',authority_valid_until=NULL,
                  run_id=?,session_id=?,attempt_id=?,lease_id=?,fence=NULL,
                  epoch=NULL,next_action='RESUME_FROM_CHECKPOINT',
                  writer_stopped='TRUE',effects_reconciled='TRUE',updated_at=?
                  WHERE task_id=?""", (UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN,
                                       now, task_id))
        return {'state': 'RELEASED', 'checkpoint_id': checkpoint_id}

    def issue_resume_grant(self, context, task_id, checkpoint_id,
                           valid_until, now=None):
        self.assert_task_context(context, task_id)
        now = self.clock() if now is None else _finite(now, 'time')
        _finite(valid_until, 'valid_until')
        if valid_until <= now:
            raise ValueError('FRESH_RESUME_GRANT_REQUIRED')
        dependencies = list(self.db.execute('''SELECT * FROM
          gateway_dependencies WHERE consumer_task_id=?
          ORDER BY producer_task_id''', (task_id,)))
        if not dependencies or any(row['state'] != 'RECEIVED'
                                   for row in dependencies):
            raise ValueError('DEPENDENCY_ACCEPTANCE_REQUIRED')
        for dep in dependencies:
            producer = self.supervisor._task(dep['producer_task_id'])
            meta = self.db.execute('''SELECT output_version FROM
              gateway_task_metadata WHERE task_id=?''',
              (dep['producer_task_id'],)).fetchone()
            if (producer['state'] != 'SUCCESS'
                    or meta['output_version'] != dep['required_version']):
                raise ValueError('DEPENDENCY_VERSION_REVOKED')
        checkpoint = self.db.execute('''SELECT * FROM gateway_checkpoints
          WHERE task_id=? AND checkpoint_id=? ORDER BY created_at DESC LIMIT 1''',
          (task_id, checkpoint_id)).fetchone()
        if checkpoint is None or checkpoint['effects_state'] != 'RECONCILED':
            raise ValueError('ORIGINAL_CHECKPOINT_REQUIRED')
        task = self.supervisor._task(task_id)
        if task['state'] != 'READY' or task['authority_state'] != 'NONE':
            raise ValueError('TASK_NOT_RESUMABLE')
        meta = self.db.execute('''SELECT resources_json FROM
          gateway_task_metadata WHERE task_id=?''', (task_id,)).fetchone()
        resources = json.loads(meta['resources_json'])
        if sorted(json.loads(checkpoint['resources_json'])) != sorted(resources):
            raise ValueError('RESUME_CHECKPOINT_RESOURCE_MISMATCH')
        placeholders = ','.join('?' for _ in resources)
        conflicts = self.db.execute('''SELECT task_id FROM resource_claims
          WHERE resource_key IN (%s) AND state IN ('VALID','REVOKING')
          LIMIT 1''' % placeholders, resources).fetchone()
        if conflicts is not None:
            raise ValueError('RESUME_RESOURCE_CONFLICT')
        event_ids = [{'producer_task_id': row['producer_task_id'],
                      'producer_attempt_id': row['event_attempt_id'],
                      'event_id': row['event_id']}
                     for row in dependencies]
        grant_body = {'task_id': task_id, 'checkpoint_id': checkpoint_id,
                      'dependency_event_ids': event_ids,
                      'valid_until': valid_until}
        grant_id = _digest(grant_body)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT OR IGNORE INTO gateway_resume_grants
              VALUES (?,?,?,?,?,?,?,?)''',
              (grant_id, task_id, checkpoint_id, canonical(event_ids),
               'ELIGIBLE', valid_until, now, None))
        return {'grant_id': grant_id, 'state': 'ELIGIBLE'}

    def validate_resume_grant(self, context, task_id, grant_id,
                              checkpoint_id, now=None):
        self.assert_task_context(context, task_id)
        now = self.clock() if now is None else _finite(now, 'time')
        row = self.db.execute('''SELECT * FROM gateway_resume_grants
          WHERE grant_id=? AND task_id=?''', (grant_id, task_id)).fetchone()
        if row is None or row['checkpoint_id'] != checkpoint_id:
            raise ValueError('RESUME_CHECKPOINT_MISMATCH')
        if row['state'] != 'ELIGIBLE':
            raise ValueError('RESUME_GRANT_ALREADY_USED')
        if now >= row['valid_until']:
            raise ValueError('RESUME_GRANT_EXPIRED')
        return dict(row)

    def assert_start_allowed(self, context, task_id, resources,
                             checkpoint_id=None, resume_grant_id=None,
                             now=None):
        """Validate all Gateway facts before source authority is claimed."""
        self.assert_claim_resources(context, task_id, resources)
        now = self.clock() if now is None else _finite(now, 'time')
        dependencies = list(self.db.execute('''SELECT * FROM
          gateway_dependencies WHERE consumer_task_id=?
          ORDER BY producer_task_id''', (task_id,)))
        for dep in dependencies:
            if (dep['state'] != 'RECEIVED' or not dep['event_attempt_id']
                    or not dep['event_id']):
                raise ValueError('DEPENDENCY_CONSUMED_ACK_REQUIRED')
            producer = self.supervisor._task(dep['producer_task_id'])
            meta = self.db.execute('''SELECT output_version FROM
              gateway_task_metadata WHERE task_id=?''',
              (dep['producer_task_id'],)).fetchone()
            inbox = self.db.execute('''SELECT * FROM gateway_inbox
              WHERE tenant_id=? AND producer_task_id=?
              AND producer_attempt_id=? AND event_id=?
              AND state='CONSUMED_ACK' LIMIT 1''',
              (self.task_tenant(task_id), dep['producer_task_id'],
               dep['event_attempt_id'], dep['event_id'])).fetchone()
            if (producer['state'] != 'SUCCESS' or inbox is None
                    or meta['output_version'] != dep['required_version']
                    or inbox['output_version'] != dep['required_version']
                    or inbox['evidence_ref'] != dep['required_evidence_ref']):
                raise ValueError('DEPENDENCY_VERSION_EVIDENCE_REQUIRED')
        checkpoint = self.db.execute('''SELECT 1 FROM gateway_checkpoints
          WHERE task_id=? LIMIT 1''', (task_id,)).fetchone()
        if checkpoint is not None or resume_grant_id is not None:
            if not resume_grant_id or not checkpoint_id:
                raise ValueError('APPLICABLE_RESUME_GRANT_REQUIRED')
            self.validate_resume_grant(context, task_id, resume_grant_id,
                                       checkpoint_id, now=now)
        return {'dependencies': len(dependencies),
                'resume_required': checkpoint is not None}

    def consume_resume_grant(self, context, task_id, grant_id, checkpoint_id,
                             now=None):
        self.assert_task_context(context, task_id)
        now = self.clock() if now is None else _finite(now, 'time')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            row = self.db.execute('''SELECT * FROM gateway_resume_grants
              WHERE grant_id=? AND task_id=?''', (grant_id, task_id)).fetchone()
            if (row is None or row['checkpoint_id'] != checkpoint_id):
                raise ValueError('RESUME_CHECKPOINT_MISMATCH')
            if row['state'] != 'ELIGIBLE':
                raise ValueError('RESUME_GRANT_ALREADY_USED')
            if now >= row['valid_until']:
                self.db.execute('''UPDATE gateway_resume_grants
                  SET state='EXPIRED' WHERE grant_id=?''', (grant_id,))
                raise ValueError('RESUME_GRANT_EXPIRED')
            dependencies = list(self.db.execute('''SELECT state,
              producer_task_id,event_attempt_id,event_id FROM
              gateway_dependencies WHERE consumer_task_id=?''', (task_id,)))
            identities = [{'producer_task_id': dep['producer_task_id'],
                           'producer_attempt_id': dep['event_attempt_id'],
                           'event_id': dep['event_id']}
                          for dep in dependencies]
            if (any(dep['state'] != 'RECEIVED' for dep in dependencies)
                    or sorted(json.loads(row['dependency_event_ids_json']),
                              key=canonical) !=
                       sorted(identities, key=canonical)):
                raise ValueError('RESUME_DEPENDENCY_CHANGED')
            self.db.execute('''UPDATE gateway_resume_grants
              SET state='STARTED',used_at=? WHERE grant_id=?
              AND state='ELIGIBLE' ''', (now, grant_id))
            if self.db.execute('SELECT changes()').fetchone()[0] != 1:
                raise ValueError('RESUME_GRANT_CAS_FAILED')
        return {'grant_id': grant_id, 'state': 'STARTED'}

    def complete_resume(self, context, task_id, grant_id, succeeded,
                        evidence_ref, now=None):
        """Record the resume result without rewriting the STARTED fact."""
        self.assert_task_context(context, task_id)
        if type(succeeded) is not bool:
            raise ValueError('BOOLEAN_RESUME_RESULT_REQUIRED')
        now = self.clock() if now is None else _finite(now, 'time')
        result = 'SUCCEEDED' if succeeded else 'FAILED'
        evidence_ref = _text(evidence_ref, 'resume_evidence')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            row = self.db.execute('''SELECT * FROM gateway_resume_grants
              WHERE grant_id=? AND task_id=?''', (grant_id, task_id)).fetchone()
            if row is None or row['state'] != 'STARTED':
                raise ValueError('RESUME_NOT_STARTED')
            self.db.execute('''UPDATE gateway_resume_grants SET state=?
              WHERE grant_id=? AND state='STARTED' ''', (result, grant_id))
            self.db.execute('''INSERT INTO gateway_delivery_receipts
              VALUES (?,?,?,?,?,?)''',
              (task_id, UNKNOWN, grant_id, 'RESUME_' + result,
               evidence_ref, now))
        return {'grant_id': grant_id, 'started': True, 'result': result}

    def rollback_unstarted_claim(self, context, task_id, attempt_id, now=None):
        """Converge a fenced claim when resume admission failed pre-STARTED."""
        self.assert_task_context(context, task_id)
        now = self.clock() if now is None else _finite(now, 'time')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            task = self.supervisor._task(task_id)
            started = self.db.execute('''SELECT 1 FROM events WHERE task_id=?
              AND attempt_id=? AND kind='STARTED' LIMIT 1''',
              (task_id, attempt_id)).fetchone()
            if (task['attempt_id'] != attempt_id
                    or task['authority_state'] != 'REVOKED'
                    or started is not None):
                raise ValueError('UNSTARTED_REVOKED_CLAIM_REQUIRED')
            self.db.execute('''DELETE FROM resource_claims WHERE task_id=?
              AND attempt_id=? AND state='REVOKED' ''',
              (task_id, attempt_id))
            interrupted = self.db.execute('''UPDATE gateway_resume_grants
              SET state='INTERRUPTED' WHERE task_id=?
              AND state IN ('ELIGIBLE','STARTED')''', (task_id,))
            interrupted_count = self.db.execute(
                'SELECT changes()').fetchone()[0]
            next_action = ('REISSUE_RESUME_GRANT' if interrupted_count
                           else 'CLAIM_TEST_ONLY_EXECUTOR')
            self.db.execute('''UPDATE tasks SET state='READY',
              authority_state='NONE',authority_valid_until=NULL,
              run_id=?,session_id=?,attempt_id=?,lease_id=?,fence=NULL,
              epoch=NULL,next_action=?,
              writer_stopped='TRUE',effects_reconciled='TRUE',updated_at=?
              WHERE task_id=? AND authority_state='REVOKED' ''',
              (UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, next_action, now, task_id))
            self.db.execute('''INSERT OR IGNORE INTO gateway_delivery_receipts
              VALUES (?,?,?,?,?,?)''',
              (task_id, attempt_id, 'unstarted-recovery:' + attempt_id,
               'UNSTARTED_CLAIM_RECOVERED',
               'NO_STARTED_EVENT_RESOURCE_COVERAGE_RECONCILED', now))
        return {'state': 'READY', 'claim_state': 'ROLLED_BACK',
                'interrupted_grants': interrupted_count,
                'next_action': next_action}

    def preemption_decision(self, context, running_task_id, waiting_task_id):
        """Pure policy verdict; it never stops a process or transfers a lock."""
        self.assert_task_context(context, running_task_id)
        self.assert_task_context(context, waiting_task_id)
        running = self.db.execute('''SELECT priority,preemptible FROM
          gateway_task_metadata WHERE task_id=?''',
          (running_task_id,)).fetchone()
        waiting = self.db.execute('''SELECT priority FROM gateway_task_metadata
          WHERE task_id=?''', (waiting_task_id,)).fetchone()
        if not running['preemptible']:
            return {'decision': 'WAIT_NEXT_SAFE_POINT',
                    'reason': 'RUNNING_TASK_NON_PREEMPTIBLE'}
        if waiting['priority'] <= running['priority']:
            return {'decision': 'KEEP_RUNNING',
                    'reason': 'NO_HIGHER_PRIORITY_TASK'}
        return {'decision': 'REQUEST_SAFE_CHECKPOINT',
                'reason': 'HIGHER_PRIORITY_READY_NO_FORCE_STOP'}

    def revoke_dependency(self, context, producer_task_id, reason, now=None):
        self.assert_task_context(context, producer_task_id)
        now = self.clock() if now is None else _finite(now, 'time')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''UPDATE gateway_dependencies SET state='REVOKED',
              updated_at=? WHERE producer_task_id=?''',
              (now, producer_task_id))
            task_ids = [row['consumer_task_id'] for row in self.db.execute(
                '''SELECT consumer_task_id FROM gateway_dependencies
                   WHERE producer_task_id=?''', (producer_task_id,))]
            for task_id in task_ids:
                self.db.execute('''UPDATE tasks SET
                  next_action='WAIT_DEPENDENCIES',updated_at=?
                  WHERE task_id=? AND state='READY' ''', (now, task_id))
                self.db.execute('''UPDATE gateway_resume_grants
                  SET state='REVOKED' WHERE task_id=?
                  AND state IN ('ELIGIBLE','STARTED')''', (task_id,))
        return {'state': 'REVOKED', 'reason': _text(reason, 'reason')}

    def monitor(self, context, now=None):
        tenant_id = self.tenants.verify(context)
        now = self.clock() if now is None else _finite(now, 'time')
        rows = list(self.db.execute('''SELECT t.*,m.tenant_id,m.priority,
          m.preemptible FROM tasks t JOIN gateway_task_metadata m
          ON m.task_id=t.task_id WHERE m.tenant_id=? ORDER BY t.task_id''',
          (tenant_id,)))
        results = []
        for row in rows:
            waiting = self.db.execute('''SELECT COUNT(*) AS n FROM
              gateway_dependencies WHERE consumer_task_id=? AND state!='RECEIVED' ''',
              (row['task_id'],)).fetchone()['n']
            status = 'WAITING_DEPENDENCY' if row['state'] == 'READY' and waiting else row['state']
            results.append({'task_id': row['task_id'], 'status': status,
                            'waiting_dependencies': waiting,
                            'priority': row['priority'],
                            'preemptible': bool(row['preemptible']),
                            'checkpoint_sha256': row['checkpoint_sha256'],
                            'observed_at': now})
        return results

    def scan(self, context, now=None):
        """Run the canonical Supervisor scan with durable wait exemptions."""
        self.tenants.verify(context)
        return self.supervisor.scan(now=now)

    def projection(self, context):
        tenant_id = self.tenants.verify(context)
        tasks = []
        for row in self.db.execute('''SELECT t.*,m.project_id,m.node_id,
          m.input_version,m.output_version,m.priority,m.preemptible,m.module_id,
          m.resources_json,m.board_id
          FROM tasks t JOIN gateway_task_metadata m ON m.task_id=t.task_id
          WHERE m.tenant_id=? ORDER BY m.priority DESC,t.task_id''',
          (tenant_id,)):
            deps = [dict(x) for x in self.db.execute('''SELECT
              producer_task_id,required_version,required_evidence_ref,state,
              event_attempt_id,event_id
              FROM gateway_dependencies WHERE consumer_task_id=?
              ORDER BY producer_task_id''', (row['task_id'],))]
            checkpoints = [dict(x) for x in self.db.execute('''SELECT
              attempt_id,checkpoint_id,effects_state,resources_json,created_at
              FROM gateway_checkpoints WHERE task_id=? ORDER BY created_at''',
              (row['task_id'],))]
            dependency_blockers = [dep for dep in deps
                                   if dep['state'] != 'RECEIVED']
            blocker = None
            if dependency_blockers:
                blocker = 'DEPENDENCY_WAIT'
            elif row['state'] == 'HOLD':
                blocker = 'TASK_HOLD'
            elif row['state'] in ('FAILURE', 'CANCELLED',
                                  'CAPABILITY_UNAVAILABLE'):
                blocker = 'TASK_TERMINAL_' + row['state']
            runtime_status = row['state']
            if dependency_blockers and row['state'] == 'READY':
                runtime_status = 'WAITING_DEPENDENCY'
            elif row['state'] == 'READY' and row['authority_state'] == 'NONE':
                runtime_status = 'WAITING_AUTHORIZATION'
            elif (row['state'] in ('RECEIVED', 'STARTED', 'RUNNING')
                  and row['last_real_progress_at'] is None):
                runtime_status = 'LIVENESS_UNKNOWN'
            tasks.append({
                'task_id': row['task_id'], 'project_id': row['project_id'],
                'node_id': row['node_id'], 'state': row['state'],
                'runtime_status': runtime_status,
                'authority_state': row['authority_state'],
                'attempt_id': row['attempt_id'], 'epoch': row['epoch'],
                'checkpoint_sha256': row['checkpoint_sha256'],
                'input_version': row['input_version'],
                'output_version': row['output_version'],
                'priority': row['priority'],
                'preemptible': bool(row['preemptible']),
                'module_id': row['module_id'], 'dependencies': deps,
                'board_id': row['board_id'],
                'responsible_party': row['owner'],
                'task_responsible_party': row['owner'],
                'run_id': row['run_id'],
                'session_id': row['session_id'],
                'writer_identity': row['authority_caller_id'],
                'authority_valid_until': row['authority_valid_until'],
                'received_at': row['received_at'],
                'started_at': row['started_at'],
                'last_real_progress_at': row['last_real_progress_at'],
                'last_event_at': row['last_event_at'],
                'writer_stopped': row['writer_stopped'],
                'effects_reconciled': row['effects_reconciled'],
                # The canonical ledger has no independently verified per-task
                # process/session liveness adapter yet.  Never infer either
                # value from task state or from a finished chat turn.
                'process_state': UNKNOWN,
                'session_state': UNKNOWN,
                'executor_instance_id': UNKNOWN,
                'next_action': row['next_action'],
                'blocker': blocker,
                'resources': json.loads(row['resources_json']),
                'checkpoints': checkpoints,
            })
        events = [dict(row) for row in self.db.execute('''SELECT e.task_id,
          e.attempt_id,e.event_id,e.kind,e.observed_at,e.evidence_kind,
          e.evidence_ref FROM events e JOIN gateway_task_metadata m
          ON m.task_id=e.task_id WHERE m.tenant_id=?
          ORDER BY e.observed_at,e.event_id''', (tenant_id,))]
        boards = []
        anomalies = []
        for board_id in sorted(BOARDS):
            board_tasks = [task for task in tasks
                           if task['board_id'] == board_id]
            blocked = [task for task in board_tasks if task['blocker']]
            active = [task for task in board_tasks
                      if task['state'] in ('RECEIVED', 'STARTED', 'RUNNING')]
            boards.append({'board_id': board_id,
                           'task_count': len(board_tasks),
                           'active_count': len(active),
                           'blocked_count': len(blocked),
                           'health': ('BLOCKED' if blocked else
                                      'ACTIVE' if active else
                                      'NO_DATA' if not board_tasks else
                                      'STABLE')})
            for task in blocked:
                unresolved_dependencies = [dep for dep in
                                           task['dependencies']
                                           if dep['state'] != 'RECEIVED']
                resolver = UNKNOWN
                evidence = []
                depends_on = []
                if task['blocker'] == 'DEPENDENCY_WAIT':
                    depends_on = [dep['producer_task_id'] for dep in
                                  unresolved_dependencies]
                    owners = {self.supervisor._task(task_id)['owner']
                              for task_id in depends_on}
                    if len(owners) == 1:
                        resolver = next(iter(owners))
                    evidence = [dep['required_evidence_ref'] for dep in
                                unresolved_dependencies]
                    impact = 'DEPENDENT_TASK_NOT_STARTABLE'
                else:
                    terminal = [event for event in events
                                if event['task_id'] == task['task_id']
                                and event['kind'] in
                                ('TERMINAL', 'SUPERVISION_ACTION')]
                    evidence = [event['evidence_ref'] for event in terminal
                                if event['evidence_ref']]
                    impact = {
                        'TASK_HOLD': 'TASK_EXECUTION_HELD',
                        'TASK_TERMINAL_FAILURE': 'TASK_TERMINATED_FAILURE',
                        'TASK_TERMINAL_CANCELLED': 'TASK_TERMINATED_CANCELLED',
                        'TASK_TERMINAL_CAPABILITY_UNAVAILABLE':
                            'TASK_CAPABILITY_UNAVAILABLE',
                    }.get(task['blocker'], UNKNOWN)
                if not evidence:
                    evidence = [UNKNOWN]
                anomalies.append({
                    'anomaly_id': task['blocker'].lower() + ':' +
                                  task['task_id'],
                    'board_id': board_id, 'project_id': task['project_id'],
                    'task_id': task['task_id'], 'node_id': task['node_id'],
                    'missing': task['blocker'],
                    'depends_on': depends_on,
                    'impact': impact,
                    'responsible_party': resolver,
                    'task_responsible_party':
                        task['task_responsible_party'],
                    'resolution_responsible_party': resolver,
                    'next_action': task['next_action'],
                    'evidence_ref': evidence,
                })
        projection_time = self.db.execute('''SELECT MAX(t.last_event_at)
          FROM tasks t JOIN gateway_task_metadata m ON m.task_id=t.task_id
          WHERE m.tenant_id=?''', (tenant_id,)).fetchone()[0]
        return {'schema': 3, 'mode': TEST_ONLY, 'tenant_id': tenant_id,
                'observed_at': projection_time,
                'boards': boards, 'anomalies': anomalies,
                'tasks': tasks, 'timeline': events,
                'production_status': 'NOT_IMPLEMENTED'}


class TestOnlyExecutor(object):
    """Explicit local adapter that drives real Supervisor/Fence transitions."""

    def __init__(self, gateway, fence, context, clock=None,
                 start_claim_hook=None):
        if not isinstance(fence, Fence):
            raise ValueError('SOURCE_ONLY_FENCE_REQUIRED')
        self.gateway = gateway
        self.supervisor = gateway.supervisor
        self.fence = fence
        self.context = context
        self.clock = clock or gateway.clock
        self.start_claim_hook = start_claim_hook

    def recover_incomplete_starts(self, now=None):
        """Converge proven-dead TEST_ONLY claims with no STARTED event.

        The caller invokes this only after the prior local process has exited.
        Existing Fence drain and source invalidation receipts remain the safety
        proof; this method neither guesses process liveness nor creates a new
        authority system.
        """
        now = self.clock() if now is None else _finite(now, 'time')
        tenant_id = self.gateway.tenants.verify(self.context)
        rows = list(self.gateway.db.execute('''SELECT t.task_id,t.attempt_id
          FROM tasks t JOIN gateway_task_metadata m ON m.task_id=t.task_id
          WHERE m.tenant_id=? AND t.state='RECEIVED'
          AND t.authority_state='VALID' AND NOT EXISTS(
            SELECT 1 FROM events e WHERE e.task_id=t.task_id
            AND e.attempt_id=t.attempt_id AND e.kind='STARTED')
          ORDER BY t.task_id''', (tenant_id,)))
        recovered = []
        for row in rows:
            controller = {'role': 'REVOCATION_CONTROLLER',
                          'caller_id': 'test-restart-recovery'}
            self.fence.begin_revocation(row['task_id'], controller)
            self.fence.drain(row['task_id'], controller, timeout=1)
            self.fence.invalidate_source_resources(
                row['task_id'], 'restart-unstarted')
            self.supervisor.complete_revocation(row['task_id'])
            receipt = self.gateway.rollback_unstarted_claim(
                self.context, row['task_id'], row['attempt_id'], now=now)
            receipt.update({'task_id': row['task_id'],
                            'attempt_id': row['attempt_id']})
            recovered.append(receipt)
        return recovered

    def _caller(self, name):
        return {'caller_id': 'test-writer-' + name,
                'run_id': 'test-run-' + name,
                'session_id': 'test-session-' + name,
                'gateway_id': 'test-gateway'}

    def start(self, task_id, attempt_id, resources, valid_until,
              checkpoint_id=None, resume_grant_id=None):
        now = self.clock()
        self.gateway.assert_start_allowed(
            self.context, task_id, resources, checkpoint_id,
            resume_grant_id, now=now)
        task = self.supervisor._task(task_id)
        caller = self._caller(attempt_id)
        ticket = self.fence.claim(
            task_id, attempt_id, task['owner'], task['entry'], caller,
            'lease-' + attempt_id, resources, valid_until)
        if self.start_claim_hook is not None:
            self.start_claim_hook(task_id, attempt_id, ticket)
        try:
            now = self.clock()
            if resume_grant_id is not None:
                self.gateway.consume_resume_grant(
                    self.context, task_id, resume_grant_id, checkpoint_id,
                    now=now)
        except Exception:
            # A revocation/expiry between preflight and grant CAS must not
            # leave a VALID source claim without a STARTED fact.
            controller = {'role': 'REVOCATION_CONTROLLER',
                          'caller_id': 'test-start-rollback'}
            self.fence.begin_revocation(task_id, controller)
            self.fence.drain(task_id, controller, timeout=1)
            self.fence.invalidate_source_resources(task_id,
                                                   'start-rollback')
            self.supervisor.complete_revocation(task_id)
            self.gateway.rollback_unstarted_claim(
                self.context, task_id, attempt_id, now=self.clock())
            raise
        self.supervisor.record(task_id, attempt_id,
            'received-' + attempt_id, 'RECEIVED', now,
            'PHASE_EXECUTION', 'test-received-' + attempt_id)
        self.supervisor.record(task_id, attempt_id,
            'started-' + attempt_id, 'STARTED', now,
            'PHASE_EXECUTION', 'test-started-' + attempt_id)
        return {'ticket': ticket, 'caller': caller, 'state': 'STARTED'}

    def progress(self, task_id, attempt_id, event_id, evidence_ref, now=None):
        self.gateway.assert_task_context(self.context, task_id)
        return self.supervisor.record(
            task_id, attempt_id, event_id, 'PROGRESS',
            self.clock() if now is None else now,
            'TEST_RUN', evidence_ref,
            {'next_progress_deadline':
             (self.clock() if now is None else now) + 600})

    def complete_success(self, task_id, attempt_id, artifact_sha256,
                         completion_evidence, now=None):
        self.gateway.assert_task_context(self.context, task_id)
        now = self.clock() if now is None else now
        result = self.supervisor.record(
            task_id, attempt_id, 'terminal-' + attempt_id, 'TERMINAL', now,
            'TEST_RUN', 'test-terminal-' + attempt_id,
            {'state': 'SUCCESS', 'artifact_sha256': artifact_sha256,
             'writer_stopped': True, 'effects_reconciled': True,
             'next_action': 'DEPENDENCIES_RECHECK',
             'completion_evidence': completion_evidence})
        task = self.supervisor._task(task_id)
        resources = json.loads(task['resource_scope_json'])
        checkpoint_id = 'terminal-checkpoint-' + attempt_id
        self.gateway.save_checkpoint(
            self.context, task_id, attempt_id, checkpoint_id,
            {'terminal_state': 'SUCCESS'}, [], 'RECONCILED', resources, now)
        controller = {'role': 'REVOCATION_CONTROLLER',
                      'caller_id': 'test-executor-finalizer'}
        self.fence.begin_revocation(task_id, controller)
        self.fence.drain(task_id, controller, timeout=1)
        self.fence.invalidate_source_resources(task_id, 'terminal-release')
        self.supervisor.complete_revocation(task_id)
        self.gateway.release_revoked_resources(
            self.context, task_id, attempt_id, checkpoint_id,
            'test-terminal-release', now, resume_ready=False)
        return result

    def complete_failure(self, task_id, attempt_id, evidence_ref, now=None):
        """Persist a real TEST_ONLY failure and safely release its claim."""
        self.gateway.assert_task_context(self.context, task_id)
        now = self.clock() if now is None else now
        result = self.supervisor.record(
            task_id, attempt_id, 'terminal-' + attempt_id, 'TERMINAL', now,
            'TEST_RUN', evidence_ref,
            {'state': 'FAILURE', 'artifact_sha256': UNKNOWN,
             'writer_stopped': True,
             'effects_reconciled': True,
             'next_action': 'INVESTIGATE_FAILURE',
             'completion_evidence': []})
        task = self.supervisor._task(task_id)
        resources = json.loads(task['resource_scope_json'])
        checkpoint_id = 'terminal-checkpoint-' + attempt_id
        self.gateway.save_checkpoint(
            self.context, task_id, attempt_id, checkpoint_id,
            {'terminal_state': 'FAILURE'}, [], 'RECONCILED', resources, now)
        controller = {'role': 'REVOCATION_CONTROLLER',
                      'caller_id': 'test-executor-finalizer'}
        self.fence.begin_revocation(task_id, controller)
        self.fence.drain(task_id, controller, timeout=1)
        self.fence.invalidate_source_resources(task_id, 'terminal-release')
        self.supervisor.complete_revocation(task_id)
        self.gateway.release_revoked_resources(
            self.context, task_id, attempt_id, checkpoint_id,
            'test-terminal-release', now, resume_ready=False)
        return result
