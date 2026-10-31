"""Restricted MCP facade over the existing task-center HTTP service.

The MCP process owns the server-issued admin/actor tokens. Tool arguments
cannot select tenant, principal, role, database, shell command, SQL, or path.
All mutations are delegated to the existing task-center service gates.
"""
from __future__ import print_function

import argparse
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError


TOOLS = (
  {'name':'task_list','description':'List tasks visible to the bound tenant.',
   'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
  {'name':'task_read_context','description':'Read one task and its scoped evidence.',
   'inputSchema':{'type':'object','required':['task_id'],'properties':{
     'task_id':{'type':'string'}},'additionalProperties':False}},
  {'name':'task_claim','description':'Claim an admitted TEST_ONLY task attempt.',
   'inputSchema':{'type':'object','required':['task_id','attempt_id'],'properties':{
     'task_id':{'type':'string'},'attempt_id':{'type':'string'}},
     'additionalProperties':False}},
  {'name':'task_report_progress','description':'Persist idempotent evidence-bound progress.',
   'inputSchema':{'type':'object','required':['task_id','event_id','evidence_ref'],
     'properties':{'task_id':{'type':'string'},'event_id':{'type':'string'},
     'evidence_ref':{'type':'string'}},'additionalProperties':False}},
  {'name':'task_save_checkpoint','description':'Persist the current attempt checkpoint.',
   'inputSchema':{'type':'object','required':['task_id','checkpoint_id','payload',
     'inflight','effects_state'],'properties':{'task_id':{'type':'string'},
     'checkpoint_id':{'type':'string'},'payload':{'type':'object'},
     'inflight':{'type':'array'},'effects_state':{'enum':['RECONCILED','UNKNOWN']}},
     'additionalProperties':False}},
  {'name':'task_submit_artifact','description':'Submit a frozen artifact for review.',
   'inputSchema':{'type':'object','required':['task_id','artifact_sha256',
     'checklist_sha256'],'properties':{'task_id':{'type':'string'},
     'artifact_sha256':{'type':'string'},'checklist_sha256':{'type':'string'}},
     'additionalProperties':False}},
  {'name':'task_request_review','description':'Submit the same frozen artifact to the existing independent-review gate.',
   'inputSchema':{'type':'object','required':['task_id','artifact_sha256',
     'checklist_sha256'],'properties':{'task_id':{'type':'string'},
     'artifact_sha256':{'type':'string'},'checklist_sha256':{'type':'string'}},
     'additionalProperties':False}},
  {'name':'task_query_result','description':'Query task and candidate result facts.',
   'inputSchema':{'type':'object','required':['task_id'],'properties':{
     'task_id':{'type':'string'}},'additionalProperties':False}},
)

REMOTE_TOOLS = (
  {'name':'task_dispatch_contract','description':
   'Read source-only role/dispatch integration contract. Does not assign, schedule, admit or execute tasks.',
   'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
   'annotations':{'readOnlyHint':True,'openWorldHint':False}},
  {'name':'task_capabilities','description':
   'List TEST_ONLY model execution capabilities, limits, and current holds.',
   'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
   'annotations':{'readOnlyHint':True,'openWorldHint':False}},
  {'name':'task_submit','description':
   'Submit one scoped asynchronous text-classification task. Returns a persistent task_id immediately.',
   'inputSchema':{'type':'object','required':['project_id','task_type',
     'input_text','idempotency_key','connection_id','max_output_tokens'],
     'properties':{'project_id':{'type':'string'},
       'task_type':{'type':'string','enum':['TEXT_CLASSIFICATION']},
       'input_text':{'type':'string','maxLength':4000},
       'idempotency_key':{'type':'string','maxLength':128},
       'connection_id':{'type':'string'},
       'max_output_tokens':{'type':'integer','minimum':1,'maximum':128}},
     'additionalProperties':False},
   'annotations':{'readOnlyHint':False,'destructiveHint':False,
                  'idempotentHint':True,'openWorldHint':True}},
  {'name':'task_get','description':'Read status for one task in the authorized project.',
   'inputSchema':{'type':'object','required':['task_id'],'properties':{
     'task_id':{'type':'string'}},'additionalProperties':False},
   'annotations':{'readOnlyHint':True,'openWorldHint':False}},
  {'name':'task_query_result','description':
   'Read the persisted model result, usage state, or exact failure for one task.',
   'inputSchema':{'type':'object','required':['task_id'],'properties':{
     'task_id':{'type':'string'}},'additionalProperties':False},
   'annotations':{'readOnlyHint':True,'openWorldHint':False}},
)


def dispatch_contract():
    """Source contract only: not an authority, admission, or runtime receipt."""
    return {
      'schema_version': 1,
      'status': 'SOURCE_CANDIDATE_NOT_WIRED',
      'execution_connected': False,
      'model_text_is_execution_authority': False,
      'new_registry_queue_or_writer': False,
      'available_remote_task_types': ['TEXT_CLASSIFICATION'],
      'existing_integration_points': {
        'role_assignment': 'ModelControl.assign',
        'dispatch_intent': 'ModelControl.queue_request',
        'scheduler': 'ModelScheduler.run_once',
        'dependency_ack': 'GatewayKernel.acknowledge_event',
        'cancellation': 'ModelControl.request_cancel',
        'writer': 'task_supervisor.Supervisor + task_writer_fence.Fence'},
      'required_bindings': [
        'EXISTING_REGISTERED_TASK_AND_PROJECT',
        'SERVER_AUTHENTICATED_TENANT_AND_ACTOR',
        'CURRENT_ATTEMPT_AND_VERSIONED_ROLE',
        'DURABLE_DEPENDENCY_ACK', 'CURRENT_UNIQUE_WRITER_AUTHORITY',
        'EXECUTION_POLICY_AND_REMAINING_BUDGET',
        'IDEMPOTENCY_AND_CANCELLATION', 'RESULT_AND_USAGE_EVIDENCE'],
      'mutating_orchestration_tools': [],
      'unverified_runtime_gates': [
        'LIVE_CANONICAL_LEDGER_BINDING', 'CURRENT_WRITER_OWNERSHIP',
        'SERVER_ROLE_ALLOWLIST', 'PROJECT_SCOPED_DISPATCH_AND_CANCEL',
        'CANONICAL_TERMINAL_RECONCILIATION'],
      'completion_rule': 'MODEL_REQUEST_SUCCESS_IS_NOT_CANONICAL_TASK_SUCCESS',
      'unknown_effects_policy': 'HOLD_NO_REPLAY'}


def _validate_remote_arguments(name, args):
    """Validate the published bounded schema before any service side effects."""
    specs = [item for item in REMOTE_TOOLS if item['name'] == name]
    if not specs:
        raise ValueError('UNKNOWN_MCP_TOOL')
    schema = specs[0]['inputSchema']
    if (not isinstance(args, dict) or
            set(args) - set(schema['properties']) or
            set(schema.get('required', [])) - set(args)):
        raise ValueError('EXACT_MCP_ARGUMENTS_REQUIRED')
    for key, value in args.items():
        field = schema['properties'][key]
        if field.get('type') == 'string':
            if not isinstance(value, str) or not value.strip():
                raise ValueError('NONEMPTY_STRING_REQUIRED:' + key)
            if 'maxLength' in field and len(value) > field['maxLength']:
                raise ValueError('MCP_STRING_LIMIT:' + key)
        if field.get('type') == 'integer':
            if type(value) is not int:
                raise ValueError('MCP_INTEGER_REQUIRED:' + key)
            if value < field['minimum'] or value > field['maximum']:
                raise ValueError('MCP_INTEGER_LIMIT:' + key)
        if 'enum' in field and value not in field['enum']:
            raise ValueError('MCP_ENUM_REQUIRED:' + key)


class RemoteTaskCenterMCP(object):
    """Stateless JSON-RPC surface over an authenticated MCPTaskService."""
    def __init__(self,service):self.service=service
    def call(self,name,args):
        _validate_remote_arguments(name, args)
        if name=='task_dispatch_contract':return dispatch_contract()
        if name=='task_capabilities':return self.service.capabilities()
        if name=='task_submit':return self.service.submit(args)
        if name=='task_get':return self.service.status(args['task_id'])
        if name=='task_query_result':return self.service.result(args['task_id'])
        raise ValueError('UNKNOWN_MCP_TOOL')
    def rpc(self,value):
        method=value.get('method');rpc_id=value.get('id')
        if method=='initialize':
            result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},
              'serverInfo':{'name':'xuanjun-task-center','version':'mcp-v1'}}
        elif method=='tools/list':result={'tools':list(REMOTE_TOOLS)}
        elif method=='tools/call':
            params=value.get('params') or {}
            result={'content':[{'type':'text','text':json.dumps(
              self.call(params.get('name'),params.get('arguments') or {}),
              ensure_ascii=False,sort_keys=True)}]}
        elif method in ('notifications/initialized','ping'):
            result={}
        else:raise ValueError('UNSUPPORTED_MCP_METHOD')
        return {'jsonrpc':'2.0','id':rpc_id,'result':result}


def _owned_secret(path):
    import stat
    info=os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
            info.st_uid!=os.getuid() or info.st_mode & 0o077):
        raise ValueError('OWNED_MODE_0600_TOKEN_FILE_REQUIRED')
    with open(path) as stream:return stream.read().strip()


class TaskCenterMCP(object):
    def __init__(self,base_url,admin_token,actor_token,trusted_principal,opener=None):
        parsed=urlsplit(base_url)
        if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or
                parsed.username is not None or parsed.password is not None or
                parsed.port is None or parsed.path not in ('','/') or
                parsed.query or parsed.fragment):
            raise ValueError('LOOPBACK_TASK_CENTER_REQUIRED')
        self.base='http://127.0.0.1:%d'%parsed.port;self.admin=admin_token
        self.actor=actor_token;self.principal=trusted_principal
        self.open=opener or urlopen

    def _get(self,path):
        request=Request(self.base+path,headers={'X-Test-Admin-Token':self.admin})
        return json.loads(self.open(request,timeout=5).read().decode('utf-8'))

    def _post(self,value):
        request=Request(self.base+'/api/admin/model-control',method='POST',
          data=json.dumps(value,separators=(',',':')).encode('utf-8'),headers={
          'Content-Type':'application/json','X-Test-Admin-Token':self.admin,
          'X-Test-Actor-Token':self.actor})
        try:return json.loads(self.open(request,timeout=5).read().decode('utf-8'))
        except HTTPError as exc:
            raise ValueError('TASK_CENTER_REJECTED:'+exc.read().decode('utf-8'))

    @staticmethod
    def _task(projection,task_id):
        rows=[x for x in projection.get('tasks',[]) if x.get('task_id')==task_id]
        if len(rows)!=1:raise KeyError('TASK_NOT_VISIBLE')
        return rows[0]

    def call(self,name,args):
        if name=='task_list':return self._get('/api/projection').get('tasks',[])
        if name in ('task_read_context','task_query_result'):
            task=self._task(self._get('/api/projection'),args['task_id'])
            admin=self._get('/api/admin/model-control')
            return {'task':task,'candidates':[x for x in admin.get('candidates',[])
              if x.get('task_id')==args['task_id']],
              'requests':[x for x in admin.get('requests',[])
              if x.get('task_id')==args['task_id']]}
        if name=='task_claim':return self._post({'action':'START_TEST_ONLY_TASK',
          'task_id':args['task_id'],'attempt_id':args['attempt_id']})
        if name=='task_report_progress':return self._post(dict(args,
          action='REPORT_TEST_ONLY_PROGRESS'))
        if name=='task_save_checkpoint':return self._post(dict(args,
          action='SAVE_TEST_ONLY_CHECKPOINT'))
        if name in ('task_submit_artifact','task_request_review'):
            return self._post(dict(args,action='SUBMIT_CANDIDATE',
              submitted_by=self.principal))
        raise ValueError('UNKNOWN_MCP_TOOL')

    def rpc(self,value):
        method=value.get('method');rpc_id=value.get('id')
        if method=='initialize':result={'protocolVersion':'2025-06-18',
          'capabilities':{'tools':{}},'serverInfo':{'name':'xuanjun-task-center',
          'version':'r6-test-only'}}
        elif method=='tools/list':result={'tools':list(TOOLS)}
        elif method=='tools/call':
            params=value.get('params') or {};result={'content':[{'type':'text',
              'text':json.dumps(self.call(params.get('name'),
              params.get('arguments') or {}),ensure_ascii=False,sort_keys=True)}]}
        else:raise ValueError('UNSUPPORTED_MCP_METHOD')
        return {'jsonrpc':'2.0','id':rpc_id,'result':result}


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--base-url',required=True)
    parser.add_argument('--admin-token-file',required=True)
    parser.add_argument('--actor-token-file',required=True)
    parser.add_argument('--trusted-principal',required=True)
    args=parser.parse_args(argv)
    service=TaskCenterMCP(args.base_url,_owned_secret(args.admin_token_file),
      _owned_secret(args.actor_token_file),args.trusted_principal)
    for line in sys.stdin:
        try:response=service.rpc(json.loads(line))
        except Exception as exc:response={'jsonrpc':'2.0','id':None,'error':{
          'code':-32000,'message':type(exc).__name__+':'+str(exc)}}
        sys.stdout.write(json.dumps(response,ensure_ascii=False,
          separators=(',',':'))+'\n');sys.stdout.flush()
    return 0




class RegisteredTaskDispatchMCP(object):
    """Candidate facade over an already-open canonical ModelControl.

    Trusted host supplies authenticated control, project, and approved role
    bindings. No ledger/queue creation, task creation, claim or Writer transfer.
    One host must serialize use of its existing SQLite connection as usual.
    Scheduling is queue admission; only the existing worker runs providers.
    """
    def __init__(self, control, project_id, role_bindings):
        self.control = control
        self.project_id = project_id
        self.roles = {key: dict(value) for key, value in role_bindings.items()}
        for binding in self.roles.values():
            if set(binding) != {'role_version','principal_id','provider_id',
                                'model_id','connection_id'}:
                raise ValueError('EXACT_TRUSTED_ROLE_BINDING_REQUIRED')

    @staticmethod
    def _args(args, required):
        if not isinstance(args, dict) or set(args) != set(required):
            raise ValueError('EXACT_MCP_ARGUMENTS_REQUIRED')
        for key in required:
            if not isinstance(args[key], str) or not args[key].strip():
                raise ValueError('NONEMPTY_STRING_REQUIRED:' + key)
            if len(args[key]) > (4000 if key == 'input_text' else 128):
                raise ValueError('MCP_STRING_LIMIT:' + key)

    def _task(self, args):
        c = self.control
        c.gateway.assert_task_context(c.context, args['task_id'])
        row = c.db.execute('''SELECT project_id FROM gateway_task_metadata
            WHERE task_id=? AND tenant_id=?''',
            (args['task_id'], c.tenant_id)).fetchone()
        if row is None or row['project_id'] != self.project_id:
            raise ValueError('PROJECT_TASK_NOT_VISIBLE')
        task = c.gateway.supervisor._task(args['task_id'])
        if task['attempt_id'] != args['attempt_id']:
            raise ValueError('STALE_TASK_ATTEMPT')
        return task

    def _role(self, args):
        binding = self.roles.get(args['role_id'])
        if binding is None:
            raise ValueError('ROLE_NOT_ALLOWED_BY_HOST')
        return binding

    def _request(self, args):
        self._task(args)
        row = self.control.db.execute('''SELECT * FROM model_requests
            WHERE tenant_id=? AND task_id=? AND attempt_id=? AND request_id=?''',
            (self.control.tenant_id,args['task_id'],args['attempt_id'],
             args['request_id'])).fetchone()
        if row is None:
            raise ValueError('REQUEST_NOT_VISIBLE')
        self._role({'role_id':row['role_id']})
        return row

    def assign(self, args):
        self._args(args, ('task_id','attempt_id','role_id'))
        task = self._task(args)
        binding = self._role(args)
        if (task['state'] != 'STARTED' or task['authority_state'] != 'VALID'
                or task['authority_valid_until'] is None or
                self.control.clock() >= task['authority_valid_until']):
            raise ValueError('CURRENT_ADMITTED_WRITER_REQUIRED')
        row = self.control.db.execute('''SELECT * FROM model_assignments
            WHERE tenant_id=? AND task_id=? AND attempt_id=? AND role_id=?''',
            (self.control.tenant_id,args['task_id'],args['attempt_id'],
             args['role_id'])).fetchone()
        if row is not None:
            for key in ('role_version','principal_id','provider_id','model_id'):
                if row[key] != binding[key]:
                    raise ValueError('ASSIGNMENT_BINDING_CONFLICT')
            return {'task_id':args['task_id'],'attempt_id':args['attempt_id'],
                    'role_id':args['role_id'],'state':'ASSIGNED','duplicate':True}
        self.control.assign(args['task_id'],args['role_id'],
            binding['role_version'],binding['principal_id'],allow_paid=False,
            provider_id=binding['provider_id'],model_id=binding['model_id'],
            expected_attempt_id=args['attempt_id'],expected_project_id=self.project_id)
        return {'task_id':args['task_id'],'attempt_id':args['attempt_id'],
                'role_id':args['role_id'],'state':'ASSIGNED','duplicate':False}

    def dispatch(self, args):
        if not isinstance(args,dict):raise ValueError('EXACT_MCP_ARGUMENTS_REQUIRED')
        strings = {key:value for key,value in args.items() if key != 'max_output_tokens'}
        self._args(strings, ('task_id','attempt_id','role_id','input_text','idempotency_key'))
        if (type(args.get('max_output_tokens')) is not int or
                not 1 <= args['max_output_tokens'] <= 128):
            raise ValueError('BOUNDED_OUTPUT_TOKENS_REQUIRED')
        self._task(args)
        binding = self._role(args)
        assignment = self.control.db.execute('''SELECT * FROM model_assignments
            WHERE tenant_id=? AND task_id=? AND attempt_id=? AND role_id=?''',
            (self.control.tenant_id,args['task_id'],args['attempt_id'],
             args['role_id'])).fetchone()
        if assignment is None or any(assignment[key] != binding[key] for key in
                ('role_version','principal_id','provider_id','model_id')):
            raise ValueError('CURRENT_TRUSTED_ASSIGNMENT_REQUIRED')
        prior = self.control.db.execute('''SELECT b.max_output_tokens,b.connection_id
            FROM model_requests r JOIN model_request_bindings b ON
            r.tenant_id=b.tenant_id AND r.request_id=b.request_id
            WHERE r.tenant_id=? AND r.idempotency_key=?''',
            (self.control.tenant_id,args['idempotency_key'])).fetchone()
        if prior is not None and (prior['max_output_tokens'] != args['max_output_tokens']
                or prior['connection_id'] != binding['connection_id']):
            raise ValueError('IDEMPOTENCY_BINDING_CONFLICT')
        result = self.control.queue_request(args['task_id'],args['role_id'],
            [{'role':'user','content':args['input_text']}],args['idempotency_key'],
            args['max_output_tokens'],binding['connection_id'],
            expected_attempt_id=args['attempt_id'],
            expected_assignment_binding=binding,expected_project_id=self.project_id)
        return dict(result, task_id=args['task_id'], attempt_id=args['attempt_id'],
                    dispatch_semantics='EXISTING_QUEUE_ADMISSION_NOT_EXECUTION')

    def status(self, args):
        self._args(args, ('task_id','attempt_id','request_id'))
        row = self._request(args)
        task = self._task(args)
        usage = self.control.db.execute('''SELECT input_tokens,output_tokens,
            cost_state,cost_value,outcome FROM model_usage_events WHERE
            tenant_id=? AND request_id=?''',
            (self.control.tenant_id,args['request_id'])).fetchone()
        return {'task_id':args['task_id'],'attempt_id':args['attempt_id'],
                'request_id':row['request_id'],'request_state':row['state'],
                'canonical_task_state':task['state'],'attempts':row['attempts'],
                'error_kind':row['error_kind'],'cancel_requested':bool(row['cancel_requested']),
                'result':json.loads(row['result_json']) if row['result_json'] else None,
                'usage':dict(usage) if usage else None}

    def cancel(self, args):
        self._args(args, ('task_id','attempt_id','request_id'))
        row = self._request(args)
        if row['state'] == 'CANCELLED':
            return {'request_id':row['request_id'],'state':'CANCELLED',
                    'cancel_requested':True,'duplicate':True}
        return self.control.request_cancel(row['request_id'],
            expected_task_id=args['task_id'],expected_attempt_id=args['attempt_id'],
            expected_project_id=self.project_id)

    def call(self, name, args):
        methods = {'task_assign_role':self.assign,'task_dispatch':self.dispatch,
                   'task_dispatch_status':self.status,'task_cancel_dispatch':self.cancel}
        if name not in methods:raise ValueError('UNKNOWN_MCP_TOOL')
        return methods[name](args)


    def rpc(self, value):
        method=value.get('method')
        if method=='tools/list':result={'tools':_registered_dispatch_tools()}
        elif method=='initialize':result={'protocolVersion':'2025-06-18',
            'capabilities':{'tools':{}},'serverInfo':{
            'name':'xuanjun-task-center','version':'registered-dispatch-local-candidate'}}
        elif method=='tools/call':
            params=value.get('params') or {}
            result={'content':[{'type':'text','text':json.dumps(self.call(
                params.get('name'),params.get('arguments')),ensure_ascii=False,sort_keys=True)}]}
        else:raise ValueError('UNSUPPORTED_MCP_METHOD')
        return {'jsonrpc':'2.0','id':value.get('id'),'result':result}


def _registered_dispatch_tools():
    atom={'type':'string','minLength':1,'maxLength':128}
    identity={'task_id':dict(atom),'attempt_id':dict(atom),'role_id':dict(atom)}
    request={'task_id':dict(atom),'attempt_id':dict(atom),'request_id':dict(atom)}
    dispatch=dict(identity,input_text={'type':'string','minLength':1,'maxLength':4000},
                  idempotency_key=dict(atom),
                  max_output_tokens={'type':'integer','minimum':1,'maximum':128})
    rows=[]
    for name, description, fields, readonly in (
      ('task_assign_role','Assign a host-approved role to an existing admitted attempt; no Writer claim.',identity,False),
      ('task_dispatch','Enqueue once in the existing queue; acceptance is not model execution or task completion.',dispatch,False),
      ('task_dispatch_status','Read request result, usage and separate canonical task state.',request,True),
      ('task_cancel_dispatch','Cancel the scoped request; an in-flight request may remain RUNNING until reconciled.',request,False)):
        rows.append({'name':name,'description':description,'inputSchema':{
            'type':'object','properties':fields,'required':list(fields),
            'additionalProperties':False},'annotations':{
            'readOnlyHint':readonly,'openWorldHint':False,'idempotentHint':True}})
    return rows


if __name__=='__main__':raise SystemExit(main())
