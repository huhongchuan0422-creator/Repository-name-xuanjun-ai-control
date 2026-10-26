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


class RemoteTaskCenterMCP(object):
    """Stateless JSON-RPC surface over an authenticated MCPTaskService."""
    def __init__(self,service):self.service=service
    def call(self,name,args):
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


if __name__=='__main__':raise SystemExit(main())
