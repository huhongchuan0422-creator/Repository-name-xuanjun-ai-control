"""Default-off host wiring for the existing authenticated MCP resource.

No credentials, role creation, ledger, queue, Writer claim or model invocation.
Configuration is deployment authority, not an MCP tool argument.
"""
import copy
from task_center_mcp_result_recovery import ResultRecoveryMCP, ACTIONS as RECOVERY_ACTIONS, validate_bindings as validate_recovery_bindings, tools as recovery_tools
import json
from task_center_mcp_completion import CandidateLifecycleMCP, ACTIONS, tools as completion_tools
from model_orchestration import ModelControl
from task_center_mcp_development import ACTIONS as DEVELOPMENT_ACTIONS
from secure_file_input import read_owned_secret_file
from task_center_mcp import (RemoteTaskCenterMCP, RegisteredTaskDispatchMCP,
                             _registered_dispatch_tools)

WRITE_TOOLS = frozenset(('task_submit','task_assign_role','task_dispatch',
                         'task_cancel_dispatch','task_submit_candidate','task_review_candidate','task_accept_candidate','task_development_apply','task_development_review','task_development_finalize','task_prepare_result_recovery','task_review_result_recovery','task_accept_result_recovery'))
DISPATCH_TOOLS = frozenset(x['name'] for x in _registered_dispatch_tools())


def _atom(value):
    return (isinstance(value,str) and 0<len(value)<=128 and
            all(33<=ord(c)<127 for c in value))


def validate_config(value):
    if value is None:return {'schema_version':1,'enabled':False,'bindings':[]}
    if (not isinstance(value,dict) or not {'schema_version','enabled','bindings'}.issubset(value) or set(value)-{'schema_version','enabled','bindings','completion_bindings','recovery_bindings'}
            or type(value['schema_version']) is not int or value['schema_version']!=1
            or type(value['enabled']) is not bool or not isinstance(value['bindings'],list)
            or len(value['bindings'])>128):
        raise ValueError('EXACT_MCP_DISPATCH_HOST_CONFIG_REQUIRED')
    seen=set()
    for item in value['bindings']:
        if (not isinstance(item,dict) or set(item)!=
                {'tenant_id','principal_id','project_id','roles'} or
                not all(_atom(item[k]) for k in ('tenant_id','principal_id','project_id'))
                or not isinstance(item['roles'],dict) or not 1<=len(item['roles'])<=32):
            raise ValueError('EXACT_MCP_DISPATCH_HOST_BINDING_REQUIRED')
        key=tuple(item[k] for k in ('tenant_id','principal_id','project_id'))
        if key in seen:raise ValueError('DUPLICATE_MCP_DISPATCH_HOST_BINDING')
        seen.add(key)
        for role_id,role in item['roles'].items():
            if (not _atom(role_id) or not isinstance(role,dict) or set(role)!=
                    {'role_version','principal_id','provider_id','model_id','connection_id'}
                    or not all(_atom(role[k]) for k in ('role_version','principal_id','provider_id','model_id'))
                    or not _atom(role['connection_id'])):
                raise ValueError('EXACT_MCP_DISPATCH_ROLE_BINDING_REQUIRED')
    completion=value.get('completion_bindings',[])
    if not isinstance(completion,list) or len(completion)>128:
        raise ValueError('EXACT_COMPLETION_BINDINGS_REQUIRED')
    seen_completion=set()
    for row in completion:
        expected={'tenant_id','principal_id','project_id','role_id','role_version','phase','review_kind','actions'}
        if (not isinstance(row,dict) or set(row)!=expected or
            not all(_atom(row[k]) for k in ('tenant_id','principal_id','project_id','role_id','role_version')) or
            row['phase'] not in ('EXECUTOR','REVIEWER','ACCEPTOR') or
            row['review_kind'] not in ('QA','SECURITY',None) or
            (row['phase']=='REVIEWER')!=(row['review_kind'] is not None) or
            not isinstance(row['actions'],list) or not row['actions'] or
            any(not isinstance(x,str) or x not in ACTIONS or (ACTIONS[x] is not None and ACTIONS[x]!=row['phase']) for x in row['actions']) or
            len(set(row['actions']))!=len(row['actions'])):
            raise ValueError('EXACT_COMPLETION_HOST_ROLE_REQUIRED')
        key=tuple(row[k] for k in ('tenant_id','principal_id','project_id'))
        if key in seen_completion:raise ValueError('DUPLICATE_COMPLETION_HOST_IDENTITY')
        seen_completion.add(key)
    recovery=validate_recovery_bindings(value.get('recovery_bindings',[]))
    if value['enabled'] and not value['bindings'] and not completion and not recovery:
        raise ValueError('ENABLED_MCP_DISPATCH_BINDING_REQUIRED')
    return copy.deepcopy(value)


def load_config(path):
    def unique(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:raise ValueError('DUPLICATE_MCP_DISPATCH_CONFIG_KEY')
            obj[k]=v
        return obj
    return validate_config(json.loads(read_owned_secret_file(path,
                           'MCP_DISPATCH_CONFIG'),object_pairs_hook=unique))


def roles_for(config, identity):
    if not config['enabled']:return None
    for row in config['bindings']:
        if all(row[k]==identity.get(k) for k in ('tenant_id','principal_id','project_id')):
            return copy.deepcopy(row['roles'])
    return None


def dispatch_rpc(service, identity, config, value, worker_enabled, development_host=None):
    """After existing OAuth verification only; binding is per authenticated token."""
    roles=roles_for(config,identity)
    completion=next((row for row in config.get('completion_bindings',[]) if config['enabled'] and
        all(row[k]==identity.get(k) for k in ('tenant_id','principal_id','project_id'))),None)
    recovery=next((row for row in config.get('recovery_bindings',[]) if config['enabled'] and all(row[k]==identity.get(k) for k in ('tenant_id','principal_id','project_id'))),None)
    method=value.get('method');params=value.get('params') or {}
    name=params.get('name') if isinstance(params,dict) else None
    if method=='tools/list':
        result=RemoteTaskCenterMCP(service).rpc(value)
        if roles:
            result['result']['tools'].extend(_registered_dispatch_tools())
        if development_host is not None:
            result['result']['tools'].extend(development_host.visible(identity))
        if recovery:result['result']['tools'].extend(recovery_tools(recovery))
        if completion:
            result['result']['tools'].extend(x for x in completion_tools() if x['name'] in completion['actions'])
        return result
    if method=='tools/call' and name in RECOVERY_ACTIONS:
        if recovery is None:raise ValueError('RECOVERY_HOST_BINDING_REQUIRED')
        required='task:read' if name=='task_result_recovery_status' else 'task:submit'
        if required not in identity.get('scopes',[]):raise ValueError('RECOVERY_OAUTH_SCOPE_REQUIRED')
        if service.tenant_id!=identity['tenant_id'] or service.project_id!=identity['project_id']:raise ValueError('RECOVERY_TENANT_PROJECT_REQUIRED')
        supervisor,gateway,control,context=service._open()
        try:
            actor=ModelControl(gateway,gateway.tenants.issue(service.tenant_id,identity['principal_id']),service.master_key)
            result=ResultRecoveryMCP(actor,recovery).call(name,params.get('arguments'))
            return {'jsonrpc':'2.0','id':value.get('id'),'result':{'content':[{'type':'text','text':json.dumps(result,sort_keys=True)}],'isError':False}}
        finally:supervisor.close()
    if method=='tools/call' and name in DEVELOPMENT_ACTIONS:
        if development_host is None:raise ValueError('MCP_DEVELOPMENT_HOST_UNAVAILABLE')
        return development_host.rpc(service,identity,value)
    if method=='tools/call' and name in ACTIONS:
        if not completion:raise ValueError('MCP_COMPLETION_HOST_BINDING_REQUIRED')
        required='task:submit' if name in WRITE_TOOLS else 'task:read'
        if required not in identity.get('scopes',[]):raise ValueError('MCP_COMPLETION_SCOPE_REQUIRED')
        if service.tenant_id!=identity['tenant_id'] or service.project_id!=identity['project_id'] or service.principal_id!=identity['principal_id']:
            raise ValueError('MCP_COMPLETION_IDENTITY_MISMATCH')
        supervisor,gateway,control,context=service._open()
        try:
            # Existing host-verified OAuth subject, not admin:mcp:<subject> and
            # never a principal supplied in tool arguments. No credentials minted.
            actor_context=gateway.tenants.issue(service.tenant_id,identity['principal_id'])
            actor_control=ModelControl(gateway,actor_context,service.master_key)
            return CandidateLifecycleMCP(actor_control,completion,service.db_path+'.test-only-locks').rpc(value)
        finally:supervisor.close()
    if method!='tools/call' or name not in DISPATCH_TOOLS:
        return RemoteTaskCenterMCP(service).rpc(value)
    if not roles:raise ValueError('MCP_DISPATCH_HOST_BINDING_REQUIRED')
    if name in ('task_assign_role','task_dispatch','task_cancel_dispatch') and 'task:submit' not in identity.get('scopes',[]):
        raise ValueError('MCP_DISPATCH_SUBMIT_SCOPE_REQUIRED')
    if name=='task_dispatch' and not worker_enabled:
        raise ValueError('MCP_DISPATCH_WORKER_DISABLED')
    supervisor,gateway,control,context=service._open()
    try:
        return RegisteredTaskDispatchMCP(control,identity['project_id'],roles).rpc(value)
    finally:supervisor.close()


def check_existing_bindings(db_path, config):
    """Read existing registrations only; never seed roles, quota or credentials."""
    if not config['enabled']:return
    import os
    import sqlite3
    from urllib.parse import quote
    db=sqlite3.connect('file:'+quote(os.path.realpath(db_path))+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        for item in config.get('recovery_bindings',[]):
            row=db.execute('SELECT principal_id,project_id,request_id FROM mcp_task_bindings WHERE tenant_id=? AND task_id=?',(item['tenant_id'],item['task_id'])).fetchone()
            if row is None or row['project_id']!=item['project_id'] or row['request_id']!=item['request_id']:raise ValueError('RECOVERY_EXISTING_TASK_BINDING_REQUIRED')
            if item['phase']=='CONTROLLER':
                if row['principal_id']!=item['principal_id']:raise ValueError('RECOVERY_ORIGINAL_SUBMITTER_REQUIRED')
            else:
                role=db.execute('''SELECT r.phase,r.review_kind,r.enabled,r.writer_allowed FROM model_assignments a JOIN role_templates r
                  ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
                  WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.principal_id=? AND a.role_id=? AND a.role_version=?''',
                  (item['tenant_id'],item['task_id'],item['attempt_id'],item['principal_id'],item['role_id'],item['role_version'])).fetchone()
                if role is None or tuple(role)!=(item['phase'],item['review_kind'],1,0):raise ValueError('RECOVERY_EXISTING_INDEPENDENT_ROLE_REQUIRED')
        for item in config.get('completion_bindings',[]):
            row=db.execute('SELECT phase,review_kind,enabled FROM role_templates WHERE tenant_id=? AND role_id=? AND version=?',
                (item['tenant_id'],item['role_id'],item['role_version'])).fetchone()
            if row is None or tuple(row)!=(item['phase'],item['review_kind'],1):
                raise ValueError('MCP_EXISTING_COMPLETION_ROLE_REQUIRED')
        for item in config['bindings']:
            for role_id,binding in item['roles'].items():
                role=db.execute('''SELECT 1 FROM role_templates WHERE tenant_id=?
                    AND role_id=? AND version=? AND enabled=1''',
                    (item['tenant_id'],role_id,binding['role_version'])).fetchone()
                connection=db.execute('''SELECT 1 FROM service_connections WHERE
                    tenant_id=? AND connection_id=? AND provider_id=?
                    AND purpose='MODEL_INFERENCE' AND status='ACTIVE' ''',
                    (item['tenant_id'],binding['connection_id'],binding['provider_id'])).fetchone()
                model=db.execute('''SELECT 1 FROM model_catalog WHERE tenant_id=?
                    AND provider_id=? AND model_id=? AND enabled=1''',
                    (item['tenant_id'],binding['provider_id'],binding['model_id'])).fetchone()
                if role is None or connection is None or model is None:
                    raise ValueError('MCP_EXISTING_ROLE_MODEL_CONNECTION_REQUIRED')
    except sqlite3.Error:
        raise ValueError('MCP_EXISTING_REGISTRY_SCHEMA_REQUIRED')
    finally:db.close()
