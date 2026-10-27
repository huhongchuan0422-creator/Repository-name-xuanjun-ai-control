"""Thin MCP composition over the canonical task-center ledger.

This module does not introduce another queue or task state machine.  It binds
four user-facing MCP operations to the existing Gateway, Fence,
ModelControl/model_requests queue, and ModelScheduler result ledger.
"""
from __future__ import print_function

import hashlib
import json
import errno
import fcntl
import os
import stat
import threading
import time

from execution_policy_gateway import ExecutionPolicyGateway
from model_orchestration import (ModelControl,ModelScheduler,
                                 QUOTA_VERIFICATION_MAX_AGE_SECONDS)
from reusable_task_gateway import (GatewayKernel, TestOnlyExecutor,
                                    TestTenantAuthority)
from task_supervisor import Supervisor, canonical
from task_writer_fence import Fence


ROLE_ID = 'mcp-text-executor'
ROLE_VERSION = 'v1'
TASK_TYPE = 'TEXT_CLASSIFICATION'
_SERVICE_LOCK_GUARD=threading.Lock()
_SERVICE_LOCK_PATHS=set()


class MCPServiceLease(object):
    """Process-lifetime proof that only one MCP service owns this ledger."""
    def __init__(self,path):
        self.path=os.path.realpath(path);self.fd=None
        if self.path!=path:raise ValueError('CANONICAL_MCP_SERVICE_LOCK_REQUIRED')
        fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            info=os.fstat(fd);current=os.lstat(path)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or
                    stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or
                    (info.st_dev,info.st_ino)!=(current.st_dev,current.st_ino)):
                raise ValueError('UNSAFE_MCP_SERVICE_LOCK')
            with _SERVICE_LOCK_GUARD:
                if path in _SERVICE_LOCK_PATHS:
                    raise ValueError('MCP_SERVICE_ALREADY_RUNNING')
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in (errno.EACCES,errno.EAGAIN):
                        raise ValueError('MCP_SERVICE_ALREADY_RUNNING')
                    raise
                _SERVICE_LOCK_PATHS.add(path)
            self.fd=fd
        except Exception:
            os.close(fd);raise

    def close(self):
        if self.fd is None:return
        try:fcntl.flock(self.fd,fcntl.LOCK_UN)
        finally:
            os.close(self.fd);self.fd=None
            with _SERVICE_LOCK_GUARD:_SERVICE_LOCK_PATHS.discard(self.path)


def ensure_schema(db):
    # Binding metadata supplies tenant/principal/project/idempotency ownership.
    # Canonical task state and results remain in tasks/model_requests.
    db.execute('''CREATE TABLE IF NOT EXISTS mcp_task_bindings(
      tenant_id TEXT NOT NULL,principal_id TEXT NOT NULL,project_id TEXT NOT NULL,
      idempotency_key TEXT NOT NULL,task_id TEXT NOT NULL,request_id TEXT NOT NULL,
      input_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,
      connection_id TEXT NOT NULL,provider_id TEXT NOT NULL,
      model_id TEXT NOT NULL,max_output_tokens INTEGER NOT NULL,
      submit_state TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,
      PRIMARY KEY(tenant_id,principal_id,project_id,idempotency_key),
      UNIQUE(tenant_id,task_id))''')
    columns={row['name'] for row in db.execute(
      'PRAGMA table_info(mcp_task_bindings)')}
    additions=(('request_sha256','TEXT'),('max_output_tokens','INTEGER'),
      ('submit_state','TEXT'),('updated_at','REAL'))
    for name,kind in additions:
        if name not in columns:
            db.execute('ALTER TABLE mcp_task_bindings ADD COLUMN %s %s'%(name,kind))
    db.execute('''UPDATE mcp_task_bindings SET
      request_sha256=COALESCE(request_sha256,input_sha256),
      max_output_tokens=COALESCE(max_output_tokens,0),
      submit_state=COALESCE(submit_state,'LEGACY_COMPLETE'),
      updated_at=COALESCE(updated_at,created_at)''')
    db.commit()


def _expected_writer(task_id,attempt_id,lock_provider_id):
    return {'owner':'mcp-worker','entry':'model-scheduler-runtime',
      'attempt_id':attempt_id,'lease_id':'lease-'+attempt_id,
      'authority_caller_id':'test-writer-'+attempt_id,
      'authority_run_id':'test-run-'+attempt_id,
      'authority_session_id':'test-session-'+attempt_id,
      'authority_gateway_id':'test-gateway',
      'authority_lock_provider_id':lock_provider_id,
      'resource_scope_json':canonical(['fake:'+task_id])}


def _assert_expected_writer(supervisor,task,lock_provider_id):
    expected=_expected_writer(task['task_id'],task['attempt_id'],lock_provider_id)
    for name,value in expected.items():
        if task[name]!=value:raise ValueError('MCP_WRITER_AUTHORITY_CONFLICT')
    if (type(task['fence']) is not int or type(task['epoch']) is not int or
            task['fence']<1 or task['epoch']<1):
        raise ValueError('MCP_WRITER_AUTHORITY_CONFLICT')
    claims=list(supervisor.db.execute('''SELECT resource_key,task_id,attempt_id,
      fence,epoch,state FROM resource_claims WHERE task_id=?''',(task['task_id'],)))
    exact=[('fake:'+task['task_id'],task['task_id'],task['attempt_id'],
      task['fence'],task['epoch'],'VALID')]
    if [tuple(row) for row in claims]!=exact:
        raise ValueError('MCP_WRITER_AUTHORITY_CONFLICT')


def recover_incomplete_mcp_starts(db_path,authority_key,tenant_id):
    """Startup-only recovery after the prior service process is proven dead."""
    supervisor=Supervisor(db_path);authority=TestTenantAuthority(authority_key)
    gateway=GatewayKernel(supervisor,authority)
    context=authority.issue(tenant_id,'admin:mcp-startup-recovery')
    fence=Fence(supervisor,db_path+'.test-only-locks')
    try:
        task_ids=[row['task_id'] for row in supervisor.db.execute('''SELECT
          b.task_id FROM mcp_task_bindings b JOIN tasks t ON t.task_id=b.task_id
          WHERE b.tenant_id=? AND b.submit_state='CONTRACT_PERSISTED' AND
          t.state='RECEIVED' AND t.authority_state='VALID' AND NOT EXISTS(
            SELECT 1 FROM events e WHERE e.task_id=t.task_id AND
            e.attempt_id=t.attempt_id AND e.kind='STARTED') ORDER BY b.task_id''',
          (tenant_id,))]
        executor=TestOnlyExecutor(gateway,fence,context)
        recovered=[]
        for task_id in task_ids:
            task=supervisor._task(task_id)
            _assert_expected_writer(supervisor,task,fence.locks.provider_id)
            recovered.extend(executor.recover_incomplete_starts(
              task_ids=[task_id]))
        return recovered
    finally:fence.close();supervisor.close()


class MCPTaskService(object):
    """Authenticated, project-scoped adapter for the minimal MCP journey."""
    def __init__(self, db_path, authority_key, tenant_id, master_key,
                 principal_id, project_id, clock=None,phase_hook=None,
                 execution_enabled=True):
        self.db_path=db_path;self.authority_key=authority_key
        self.tenant_id=tenant_id;self.master_key=master_key
        self.principal_id=principal_id;self.project_id=project_id
        self.clock=clock or time.time
        self.phase_hook=phase_hook
        self.execution_enabled=bool(execution_enabled)

    def _open(self):
        supervisor=Supervisor(self.db_path)
        authority=TestTenantAuthority(self.authority_key)
        gateway=GatewayKernel(supervisor,authority)
        context=authority.issue(self.tenant_id,'admin:mcp:'+self.principal_id)
        control=ModelControl(gateway,context,self.master_key)
        return supervisor,gateway,control,context

    def capabilities(self):
        supervisor,gateway,control,context=self._open()
        try:
            rows=[]
            for row in supervisor.db.execute('''SELECT c.connection_id,
              c.provider_id,c.status,c.config_version,o.model_id,
              o.model_callable_state,p.price_state AS provider_price,
              p.enabled AS provider_enabled,m.price_state AS model_price,
              m.enabled AS model_enabled,q.quota_state,q.quota_source,
              q.verified_at,e.state AS evaluation_state
              FROM service_connections c JOIN provider_onboarding_configs o
              ON o.tenant_id=c.tenant_id AND o.connection_id=c.connection_id
              JOIN model_providers p ON p.tenant_id=c.tenant_id AND
              p.provider_id=c.provider_id JOIN model_catalog m ON
              m.tenant_id=c.tenant_id AND m.provider_id=c.provider_id AND
              m.model_id=o.model_id LEFT JOIN model_quota_status q ON
              q.tenant_id=c.tenant_id AND q.provider_id=c.provider_id
              LEFT JOIN model_evaluations e ON e.tenant_id=c.tenant_id AND
              e.provider_id=c.provider_id AND e.model_id=o.model_id
              WHERE c.tenant_id=? AND c.purpose='MODEL_INFERENCE'
              ORDER BY c.connection_id,e.observed_at DESC''',(self.tenant_id,)):
                item=dict(row)
                effective=('UNKNOWN' if 'UNKNOWN' in
                  (item['provider_price'],item['model_price']) else
                  'KNOWN_PAID' if 'KNOWN_PAID' in
                  (item['provider_price'],item['model_price']) else 'KNOWN_FREE')
                item['effective_price_state']=effective
                item['dispatch_ready']=bool(item['status']=='ACTIVE' and
                  item['provider_enabled'] and item['model_enabled'] and
                  item['model_callable_state']=='TESTED_SUCCEEDED' and
                  effective=='KNOWN_FREE' and item['quota_state']=='AVAILABLE' and
                  item['verified_at'] is not None and self.clock()-
                  item['verified_at']<=QUOTA_VERIFICATION_MAX_AGE_SECONDS and
                  item['evaluation_state']=='QUALIFIED')
                rows.append(item)
            # One row per connection/model; do not disclose credentials.
            unique=[];seen=set()
            for item in rows:
                key=(item['connection_id'],item['model_id'])
                if key not in seen:seen.add(key);unique.append(item)
            return {'task_types':[TASK_TYPE],'connections':unique,
              'limits':{'max_output_tokens':128,'paid_fallback':False,
              'arbitrary_shell':False,'production_control':False},
              'mode':'TEST_ONLY'}
        finally:supervisor.close()

    @staticmethod
    def _validate_submit(value):
        required={'project_id','task_type','input_text','idempotency_key',
                  'connection_id','max_output_tokens'}
        if not isinstance(value,dict) or set(value)!=required:
            raise ValueError('EXACT_MCP_SUBMIT_REQUIRED')
        for name in ('project_id','input_text','idempotency_key','connection_id'):
            if not isinstance(value[name],str) or not value[name].strip():
                raise ValueError('VALID_%s_REQUIRED'%name.upper())
        if len(value['input_text'])>4000 or len(value['idempotency_key'])>128:
            raise ValueError('MCP_INPUT_LIMIT')
        if value['task_type']!=TASK_TYPE:raise ValueError('TASK_TYPE_NOT_SUPPORTED')
        if type(value['max_output_tokens']) is not int or not 1<=value['max_output_tokens']<=128:
            raise ValueError('MCP_OUTPUT_LIMIT')

    def _phase(self,supervisor,task_id,state):
        now=self.clock()
        supervisor.db.execute('''UPDATE mcp_task_bindings SET submit_state=?,
          updated_at=? WHERE tenant_id=? AND task_id=?''',(state,now,
          self.tenant_id,task_id));supervisor.db.commit()
        if self.phase_hook is not None:self.phase_hook(state)

    def _ensure_graph(self,supervisor,gateway,context,graph,now):
        body=canonical(graph);graph_sha=hashlib.sha256(body.encode()).hexdigest()
        row=supervisor.db.execute('''SELECT graph_sha256 FROM gateway_graphs
          WHERE graph_id=?''',(graph['graph_id'],)).fetchone()
        if row is not None:
            if row['graph_sha256']!=graph_sha:raise ValueError('TASK_GRAPH_ID_CONFLICT')
            return
        task_spec=graph['tasks'][0];task_id=task_spec['task_id']
        task=supervisor.db.execute('SELECT * FROM tasks WHERE task_id=?',
          (task_id,)).fetchone()
        if task is None:
            gateway.register_graph(context,graph,now=now);return
        expected=(graph['project_id'],task_spec['stage'],task_spec['owner'],
          task_spec['entry'],task_spec['checkpoint_sha256'],task_spec['spec_sha256'])
        actual=(task['parent_task_id'],task['stage'],task['owner'],task['entry'],
          task['checkpoint_sha256'],task['spec_sha256'])
        if actual!=expected:raise ValueError('MCP_PARTIAL_GRAPH_CONFLICT')
        # Recover the only non-atomic boundary in register_graph: Supervisor
        # task registration may have committed just before graph metadata.
        supervisor.db.execute('BEGIN IMMEDIATE')
        try:
            supervisor.db.execute('INSERT INTO gateway_graphs VALUES (?,?,?,?,?,?)',(
              graph['graph_id'],self.tenant_id,graph['project_id'],
              graph['graph_version'],graph_sha,now))
            supervisor.db.execute('''INSERT INTO gateway_task_metadata
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(task_id,graph['graph_id'],
              self.tenant_id,graph['project_id'],task_spec['node_id'],
              task_spec['input_version'],task_spec['output_version'],
              task_spec['priority'],int(task_spec['preemptible']),
              task_spec['module_id'],canonical(sorted(task_spec['resources'])),
              task_spec['board_id']))
            supervisor.db.commit()
        except Exception:supervisor.db.rollback();raise

    def _ensure_task_spec(self,supervisor,control,task_id,spec,now):
        expected=(spec['goal'],canonical(spec['deliverables']),
          canonical(spec['acceptance']))
        row=supervisor.db.execute('''SELECT goal,deliverables_json,
          acceptance_json FROM task_work_specs WHERE tenant_id=? AND task_id=?''',
          (self.tenant_id,task_id)).fetchone()
        if row is None:
            control.record_task_spec(task_id,spec['goal'],spec['deliverables'],
              spec['acceptance'],now=now);return
        if tuple(row)!=expected:raise ValueError('MCP_TASK_SPEC_CONFLICT')

    def _ensure_unit(self,supervisor,policy,unit,now):
        row=supervisor.db.execute('''SELECT delivery_stage,feature_unit,goal,
          scope_json,acceptance_json,dependency_json,asset_version,
          responsible_party FROM execution_units WHERE tenant_id=? AND task_id=?''',
          (self.tenant_id,unit['task_id'])).fetchone()
        expected=(unit['delivery_stage'],unit['feature_unit'],unit['goal'],
          canonical(unit['scope']),canonical(unit['acceptance']),
          canonical(unit['dependencies']),unit['asset_version'],
          unit['responsible_party'])
        if row is None:policy.record_unit(unit,now=now);return
        if tuple(row)!=expected:raise ValueError('MCP_EXECUTION_UNIT_CONFLICT')

    def _ensure_preflight(self,supervisor,policy,task_id,spec,query_id,query,
                          observed,now):
        row=supervisor.db.execute('''SELECT query_json,result_digest FROM
          asset_query_receipts WHERE tenant_id=? AND query_id=?''',(
          self.tenant_id,query_id)).fetchone()
        digest=hashlib.sha256(canonical(observed).encode()).hexdigest()
        if row is None:
            policy.record_asset_query(task_id,query_id,'CANONICAL_DB','v1',query,
              digest,now=now)
        elif (row['query_json'],row['result_digest'])!=(canonical(query),digest):
            raise ValueError('MCP_ASSET_QUERY_CONFLICT')
        existing=supervisor.db.execute('''SELECT asset_version,query_ids_json,
          outcome,reuse_reason FROM dispatch_preflights WHERE tenant_id=? AND
          task_id=? ORDER BY observed_at DESC,preflight_id DESC LIMIT 1''',(
          self.tenant_id,task_id)).fetchone()
        expected=(spec['asset_version'],canonical([query_id]),'NOT_FOUND',
          'verified isolated MCP task')
        if existing is None:
            policy.record_dispatch_preflight(task_id,spec['asset_version'],
              [query_id],'NOT_FOUND',expected[3],now=now)
        elif tuple(existing)!=expected:raise ValueError('MCP_PREFLIGHT_CONFLICT')

    def _ensure_started(self,supervisor,gateway,context,task_id,attempt_id,now):
        task=supervisor._task(task_id)
        if task['attempt_id']==attempt_id and task['authority_state']=='VALID':
            fence=Fence(supervisor,self.db_path+'.test-only-locks')
            try:_assert_expected_writer(supervisor,task,fence.locks.provider_id)
            finally:fence.close()
            started=supervisor.db.execute('''SELECT kind,evidence_kind,
              evidence_ref FROM events WHERE task_id=? AND attempt_id=? AND
              event_id=?''',(task_id,attempt_id,
              'started-'+attempt_id)).fetchone()
            if (task['state'] not in ('STARTED','RUNNING') or started is None or
                    tuple(started)!=('STARTED','PHASE_EXECUTION',
                    'test-started-'+attempt_id)):
                # Never manufacture STARTED for an authority whose prior
                # process liveness is not proven here.  Service startup owns
                # the existing controlled incomplete-start recovery.
                raise ValueError('MCP_INCOMPLETE_START_RECOVERY_REQUIRED')
            return
        if task['state']!='READY' or task['authority_state']!='NONE':
            raise ValueError('MCP_PARTIAL_START_RECONCILIATION_HOLD')
        fence=Fence(supervisor,self.db_path+'.test-only-locks')
        try:
            TestOnlyExecutor(gateway,fence,context).start(task_id,attempt_id,
              gateway.canonical_resources(task_id),now+600)
        finally:fence.close()

    def _ensure_assignment(self,supervisor,control,task_id,attempt_id,
                           connection,now):
        row=supervisor.db.execute('''SELECT principal_id,provider_id,model_id
          FROM model_assignments WHERE tenant_id=? AND task_id=? AND
          attempt_id=? AND role_id=?''',(self.tenant_id,task_id,attempt_id,
          ROLE_ID)).fetchone()
        expected=('mcp-worker',connection['provider_id'],connection['model_id'])
        if row is None:
            control.assign(task_id,ROLE_ID,ROLE_VERSION,'mcp-worker',False,now,
              connection['provider_id'],connection['model_id']);return
        if tuple(row)!=expected:raise ValueError('MCP_ASSIGNMENT_CONFLICT')

    def _reconcile_queued(self,supervisor,binding,request,value):
        attempt_id='attempt-'+binding['task_id'][4:]
        expected=(binding['request_id'],'mcp:'+self.principal_id+':'+
          value['idempotency_key'],binding['task_id'],attempt_id,ROLE_ID,
          binding['provider_id'],binding['model_id'])
        actual=tuple(request[name] for name in ('request_id','idempotency_key',
          'task_id','attempt_id','role_id','provider_id','model_id'))
        detail=supervisor.db.execute('''SELECT connection_id,max_output_tokens,
          writer_principal FROM model_request_bindings WHERE tenant_id=? AND
          request_id=?''',(self.tenant_id,binding['request_id'])).fetchone()
        expected_detail=(value['connection_id'],value['max_output_tokens'],
          'test-writer-'+attempt_id)
        if actual!=expected or detail is None or tuple(detail)!=expected_detail:
            raise ValueError('MCP_QUEUED_REQUEST_RECONCILIATION_FAILED')
        if binding['submit_state']!='QUEUED':
            supervisor.db.execute('''UPDATE mcp_task_bindings SET
              submit_state='QUEUED',updated_at=? WHERE tenant_id=? AND
              task_id=? AND request_id=?''',(self.clock(),self.tenant_id,
              binding['task_id'],binding['request_id']))
            if supervisor.db.execute('SELECT changes()').fetchone()[0]!=1:
                supervisor.db.rollback()
                raise ValueError('MCP_QUEUED_BINDING_CAS_FAILED')
            supervisor.db.commit()

    def submit(self,value):
        self._validate_submit(value)
        if value['project_id']!=self.project_id:
            raise ValueError('MCP_PROJECT_SCOPE_REJECTED')
        now=self.clock();input_sha=hashlib.sha256(value['input_text'].encode()).hexdigest()
        request_sha=hashlib.sha256(canonical({'task_type':value['task_type'],
          'input_sha256':input_sha,'connection_id':value['connection_id'],
          'max_output_tokens':value['max_output_tokens']}).encode()).hexdigest()
        identity={'tenant_id':self.tenant_id,'principal_id':self.principal_id,
          'project_id':self.project_id,'idempotency_key':value['idempotency_key']}
        task_id='mcp-'+hashlib.sha256(canonical(identity).encode()).hexdigest()[:24]
        attempt_id='attempt-'+task_id[4:]
        supervisor,gateway,control,context=self._open()
        try:
            existing=supervisor.db.execute('''SELECT * FROM mcp_task_bindings
              WHERE tenant_id=? AND principal_id=? AND project_id=? AND
              idempotency_key=?''',(self.tenant_id,self.principal_id,
              self.project_id,value['idempotency_key'])).fetchone()
            if existing is not None:
                if (existing['request_sha256']!=request_sha or
                        existing['connection_id']!=value['connection_id'] or
                        existing['max_output_tokens']!=value['max_output_tokens']):
                    raise ValueError('MCP_IDEMPOTENCY_CONFLICT')
                request=supervisor.db.execute('''SELECT * FROM model_requests
                  WHERE tenant_id=? AND request_id=?''',(self.tenant_id,
                  existing['request_id'])).fetchone()
                if request is not None:
                    self._reconcile_queued(supervisor,existing,request,value)
                    return {'task_id':existing['task_id'],
                      'request_id':existing['request_id'],'state':request['state'],
                      'duplicate':True}
            if not self.execution_enabled:
                raise ValueError('MCP_MODEL_OUTBOUND_DISABLED')
            connection=supervisor.db.execute('''SELECT c.provider_id,c.status,
              c.purpose,o.model_id FROM service_connections c JOIN
              provider_onboarding_configs o ON o.tenant_id=c.tenant_id AND
              o.connection_id=c.connection_id WHERE c.tenant_id=? AND
              c.connection_id=?''',(self.tenant_id,
              value['connection_id'])).fetchone()
            if (connection is None or connection['status']!='ACTIVE' or
                    connection['purpose']!='MODEL_INFERENCE'):
                raise ValueError('ACTIVE_MODEL_CONNECTION_REQUIRED')
            # All assignment, pricing, quota and evaluation gates are enforced
            # again by ModelControl.assign; this is only an early readable hold.
            ready=[x for x in self.capabilities()['connections'] if
              x['connection_id']==value['connection_id'] and
              x['model_id']==connection['model_id'] and x['dispatch_ready']]
            if not ready:raise ValueError('MODEL_CAPABILITY_OR_FREE_QUOTA_HOLD')
            request_identity={'tenant':self.tenant_id,'task':task_id,
              'attempt':attempt_id,'role':ROLE_ID,
              'provider':connection['provider_id'],'model':connection['model_id'],
              'idempotency':'mcp:'+self.principal_id+':'+value['idempotency_key']}
            request_id=hashlib.sha256(canonical(request_identity).encode()).hexdigest()
            if existing is None:
                supervisor.db.execute('''INSERT INTO mcp_task_bindings VALUES
                  (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,
                  self.principal_id,self.project_id,value['idempotency_key'],task_id,
                  request_id,input_sha,request_sha,value['connection_id'],
                  connection['provider_id'],connection['model_id'],
                  value['max_output_tokens'],'PREPARING',now,now))
                supervisor.db.commit()
                self._phase(supervisor,task_id,'BINDING_PERSISTED')
            else:
                if (existing['request_id']!=request_id or
                        existing['provider_id']!=connection['provider_id'] or
                        existing['model_id']!=connection['model_id']):
                    raise ValueError('MCP_IDEMPOTENCY_BINDING_CONFLICT')
            if supervisor.db.execute('''SELECT 1 FROM role_templates WHERE
              tenant_id=? AND role_id=? AND version=?''',(self.tenant_id,
              ROLE_ID,ROLE_VERSION)).fetchone() is None:
                control.create_role({'role_id':ROLE_ID,'version':ROLE_VERSION,
                  'phase':'EXECUTOR','capabilities':['general'],
                  'writer_allowed':True,'enabled':True,'review_kind':None})
            spec={'project_id':self.project_id,'task_id':task_id,
              'board_id':'research-development','goal':'Classify fixed test text',
              'deliverables':['structured_model_result'],
              'acceptance':['model_result_persisted'], 'dependencies':[],
              'priority':50,'owner':'mcp-worker','delivery_stage':'mcp-test',
              'feature_unit':'text-classification','scope':['MODEL_INFERENCE'],
              'asset_version':'mcp-text-classification-v1'}
            digest=hashlib.sha256(canonical(spec).encode()).hexdigest()
            graph={'graph_id':'graph-'+digest[:24],'tenant_id':self.tenant_id,
              'project_id':self.project_id,'graph_version':'v1-'+digest[:12],
              'tasks':[{'task_id':task_id,'node_id':'node-'+digest[:12],
              'stage':'TEST_ONLY_EXECUTION','owner':'mcp-worker',
              'entry':'model-scheduler-runtime','checkpoint_sha256':
              hashlib.sha256(b'{}').hexdigest(),'spec_sha256':digest,
              'input_version':'v1','output_version':'v1','priority':50,
              'preemptible':True,'module_id':'xuanjun.scheduler.kernel',
              'resources':['fake:'+task_id],'dependencies':[],
              'board_id':'research-development',
              'completion_evidence':['model_result_persisted']}]}
            self._ensure_graph(supervisor,gateway,context,graph,now)
            self._phase(supervisor,task_id,'GRAPH_PERSISTED')
            self._ensure_task_spec(supervisor,control,task_id,spec,now)
            policy=ExecutionPolicyGateway(gateway,context)
            unit={'task_id':task_id,'delivery_stage':'mcp-test',
              'feature_unit':'text-classification','goal':spec['goal'],
              'scope':['MODEL_INFERENCE'],'acceptance':spec['acceptance'],
              'dependencies':['NONE'],'asset_version':spec['asset_version'],
              'responsible_party':'mcp-worker'}
            self._ensure_unit(supervisor,policy,unit,now)
            observed={'matches':[]};query_id='query-'+task_id
            query={'lookup':{'asset_key':spec['asset_version']},
              'observed_result':observed,'evidence_ref':'canonical-db://%s@v1'%
              spec['asset_version']}
            self._ensure_preflight(supervisor,policy,task_id,spec,query_id,query,
              observed,now)
            self._phase(supervisor,task_id,'CONTRACT_PERSISTED')
            self._ensure_started(supervisor,gateway,context,task_id,attempt_id,now)
            self._phase(supervisor,task_id,'WRITER_STARTED')
            self._ensure_assignment(supervisor,control,task_id,attempt_id,
              connection,now)
            self._phase(supervisor,task_id,'MODEL_ASSIGNED')
            queued=control.queue_request(task_id,ROLE_ID,[
              {'role':'system','content':'Return JSON with keys label and reason.'},
              {'role':'user','content':value['input_text']}],
              'mcp:'+self.principal_id+':'+value['idempotency_key'],
              value['max_output_tokens'],value['connection_id'],now=now)
            if queued['request_id']!=request_id:
                raise ValueError('MCP_REQUEST_ID_RECONCILIATION_FAILED')
            if self.phase_hook is not None:self.phase_hook('REQUEST_COMMITTED')
            self._phase(supervisor,task_id,'QUEUED')
            return {'task_id':task_id,'request_id':queued['request_id'],
              'state':queued['state'],'duplicate':existing is not None}
        finally:supervisor.close()

    def _binding(self,task_id):
        supervisor,gateway,control,context=self._open()
        row=supervisor.db.execute('''SELECT * FROM mcp_task_bindings WHERE
          tenant_id=? AND principal_id=? AND project_id=? AND task_id=?''',(
          self.tenant_id,self.principal_id,self.project_id,task_id)).fetchone()
        if row is None:supervisor.close();raise KeyError('MCP_TASK_NOT_VISIBLE')
        return supervisor,dict(row)

    def status(self,task_id):
        supervisor,binding=self._binding(task_id)
        try:
            task=supervisor.db.execute('SELECT * FROM tasks WHERE task_id=?',
              (task_id,)).fetchone()
            request=supervisor.db.execute('''SELECT request_id,state,attempts,
              error_kind,lease_owner,lease_until,last_heartbeat,created_at,
              updated_at FROM model_requests WHERE tenant_id=? AND request_id=?''',(
              self.tenant_id,binding['request_id'])).fetchone()
            return {'task_id':task_id,'canonical_task_state':(
              task['state'] if task is not None else 'PREPARING'),
              'submit_state':binding['submit_state'],
              'request':dict(request) if request is not None else None,
              'provider_id':binding['provider_id'],
              'model_id':binding['model_id']}
        finally:supervisor.close()

    def result(self,task_id):
        supervisor,binding=self._binding(task_id)
        try:
            request=supervisor.db.execute('''SELECT request_id,state,result_json,
              error_kind,attempts FROM model_requests WHERE tenant_id=? AND
              request_id=?''',(self.tenant_id,binding['request_id'])).fetchone()
            if request is None:
                return {'task_id':task_id,'request_id':binding['request_id'],
                  'state':'PREPARING','submit_state':binding['submit_state'],
                  'result':None,'error_kind':None,'attempts':0,'usage':None}
            usage=supervisor.db.execute('''SELECT input_tokens,output_tokens,
              cost_state,cost_value,outcome,observed_at FROM model_usage_events
              WHERE tenant_id=? AND request_id=?''',(self.tenant_id,
              binding['request_id'])).fetchone()
            return {'task_id':task_id,'request_id':request['request_id'],
              'state':request['state'],'submit_state':binding['submit_state'],
              'result':(json.loads(request['result_json'])
              if request['result_json'] else None),'error_kind':request['error_kind'],
              'attempts':request['attempts'],'usage':dict(usage) if usage else None}
        finally:supervisor.close()


class MCPModelWorkerLoop(object):
    """Persistent loop over the existing model_requests queue."""
    def __init__(self,db_path,authority_key,tenant_id,master_key,interval=1.0,
                 adapters=None):
        import threading
        self.db_path=db_path;self.authority_key=authority_key
        self.tenant_id=tenant_id;self.master_key=master_key
        self.interval=interval;self.adapters=adapters
        self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self._run,name='mcp-model-worker')
        self.thread.daemon=True
    def start(self):self.thread.start()
    def stop(self):self.stop_event.set();self.thread.join(5)
    def _run(self):
        supervisor=Supervisor(self.db_path)
        try:
            authority=TestTenantAuthority(self.authority_key)
            control=ModelControl(GatewayKernel(supervisor,authority),
              authority.issue(self.tenant_id,'admin:mcp-worker'),self.master_key)
            scheduler=ModelScheduler(control,adapters=self.adapters,
              worker_id='mcp-worker')
            while not self.stop_event.is_set():
                result=scheduler.run_once()
                if result.get('state') in ('IDLE','QUEUED_LIMIT','HOLD'):
                    self.stop_event.wait(self.interval)
        finally:supervisor.close()
