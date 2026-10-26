"""Thin MCP composition over the canonical task-center ledger.

This module does not introduce another queue or task state machine.  It binds
four user-facing MCP operations to the existing Gateway, Fence,
ModelControl/model_requests queue, and ModelScheduler result ledger.
"""
from __future__ import print_function

import hashlib
import json
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


def ensure_schema(db):
    # Binding metadata supplies tenant/principal/project/idempotency ownership.
    # Canonical task state and results remain in tasks/model_requests.
    db.execute('''CREATE TABLE IF NOT EXISTS mcp_task_bindings(
      tenant_id TEXT NOT NULL,principal_id TEXT NOT NULL,project_id TEXT NOT NULL,
      idempotency_key TEXT NOT NULL,task_id TEXT NOT NULL,request_id TEXT NOT NULL,
      input_sha256 TEXT NOT NULL,connection_id TEXT NOT NULL,provider_id TEXT NOT NULL,
      model_id TEXT NOT NULL,created_at REAL NOT NULL,
      PRIMARY KEY(tenant_id,principal_id,project_id,idempotency_key),
      UNIQUE(tenant_id,task_id))''')
    db.commit()


class MCPTaskService(object):
    """Authenticated, project-scoped adapter for the minimal MCP journey."""
    def __init__(self, db_path, authority_key, tenant_id, master_key,
                 principal_id, project_id, clock=None):
        self.db_path=db_path;self.authority_key=authority_key
        self.tenant_id=tenant_id;self.master_key=master_key
        self.principal_id=principal_id;self.project_id=project_id
        self.clock=clock or time.time

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

    def submit(self,value):
        self._validate_submit(value)
        if value['project_id']!=self.project_id:
            raise ValueError('MCP_PROJECT_SCOPE_REJECTED')
        now=self.clock();input_sha=hashlib.sha256(value['input_text'].encode()).hexdigest()
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
                if (existing['input_sha256']!=input_sha or
                        existing['connection_id']!=value['connection_id']):
                    raise ValueError('MCP_IDEMPOTENCY_CONFLICT')
                request=supervisor.db.execute('''SELECT state FROM model_requests
                  WHERE tenant_id=? AND request_id=?''',(self.tenant_id,
                  existing['request_id'])).fetchone()
                return {'task_id':existing['task_id'],
                  'request_id':existing['request_id'],'state':request['state'],
                  'duplicate':True}
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
            gateway.register_graph(context,graph,now=now)
            control.record_task_spec(task_id,spec['goal'],spec['deliverables'],
                                     spec['acceptance'],now=now)
            policy=ExecutionPolicyGateway(gateway,context)
            policy.record_unit({'task_id':task_id,'delivery_stage':'mcp-test',
              'feature_unit':'text-classification','goal':spec['goal'],
              'scope':['MODEL_INFERENCE'],'acceptance':spec['acceptance'],
              'dependencies':['NONE'],'asset_version':spec['asset_version'],
              'responsible_party':'mcp-worker'},now=now)
            observed={'matches':[]};query_id='query-'+task_id
            query={'lookup':{'asset_key':spec['asset_version']},
              'observed_result':observed,'evidence_ref':'canonical-db://%s@v1'%
              spec['asset_version']}
            policy.record_asset_query(task_id,query_id,'CANONICAL_DB','v1',query,
              hashlib.sha256(canonical(observed).encode()).hexdigest(),now=now)
            policy.record_dispatch_preflight(task_id,spec['asset_version'],
              [query_id],'NOT_FOUND','verified isolated MCP task',now=now)
            fence=Fence(supervisor,self.db_path+'.test-only-locks')
            try:
                TestOnlyExecutor(gateway,fence,context).start(
                  task_id,attempt_id,gateway.canonical_resources(task_id),now+600)
            finally:fence.close()
            control.assign(task_id,ROLE_ID,ROLE_VERSION,'mcp-worker',False,now,
              connection['provider_id'],connection['model_id'])
            queued=control.queue_request(task_id,ROLE_ID,[
              {'role':'system','content':'Return JSON with keys label and reason.'},
              {'role':'user','content':value['input_text']}],
              'mcp:'+self.principal_id+':'+value['idempotency_key'],
              value['max_output_tokens'],value['connection_id'],now=now)
            supervisor.db.execute('''INSERT INTO mcp_task_bindings VALUES
              (?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,self.principal_id,
              self.project_id,value['idempotency_key'],task_id,
              queued['request_id'],input_sha,value['connection_id'],
              connection['provider_id'],connection['model_id'],now))
            supervisor.db.commit()
            return {'task_id':task_id,'request_id':queued['request_id'],
              'state':queued['state'],'duplicate':False}
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
            task=supervisor._task(task_id)
            request=supervisor.db.execute('''SELECT request_id,state,attempts,
              error_kind,lease_owner,lease_until,last_heartbeat,created_at,
              updated_at FROM model_requests WHERE tenant_id=? AND request_id=?''',(
              self.tenant_id,binding['request_id'])).fetchone()
            return {'task_id':task_id,'canonical_task_state':task['state'],
              'request':dict(request),'provider_id':binding['provider_id'],
              'model_id':binding['model_id']}
        finally:supervisor.close()

    def result(self,task_id):
        supervisor,binding=self._binding(task_id)
        try:
            request=supervisor.db.execute('''SELECT request_id,state,result_json,
              error_kind,attempts FROM model_requests WHERE tenant_id=? AND
              request_id=?''',(self.tenant_id,binding['request_id'])).fetchone()
            usage=supervisor.db.execute('''SELECT input_tokens,output_tokens,
              cost_state,cost_value,outcome,observed_at FROM model_usage_events
              WHERE tenant_id=? AND request_id=?''',(self.tenant_id,
              binding['request_id'])).fetchone()
            return {'task_id':task_id,'request_id':request['request_id'],
              'state':request['state'],'result':(json.loads(request['result_json'])
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
