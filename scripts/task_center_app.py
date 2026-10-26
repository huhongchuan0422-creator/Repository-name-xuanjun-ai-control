"""Loopback-only TEST_ONLY task-center web application.

The API rebuilds every projection from the canonical Supervisor SQLite file.
It exposes no mutation endpoint and cannot dispatch production work.
"""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import sys
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(__file__))
from reusable_task_gateway import (GatewayKernel, TestOnlyExecutor,
                                   TestTenantAuthority, canonical)
from model_orchestration import ModelControl, ModelScheduler, load_master_key
from task_supervisor import Supervisor
from task_writer_fence import Fence
from execution_policy_gateway import ExecutionPolicyGateway
from connection_management import ConnectionManager
from codex_execution_adapter import (CodexExecutionControl,
                                     CodexAppServerTransport)
from task_center_session_auth import FileTestIdentityProvider, SessionStore
from secure_file_input import read_owned_secret_file
from provider_onboarding import (ensure_schema as ensure_onboarding_schema,
                                 public_presets, projection as onboarding_projection,
                                 saved_credential, test_connection, test_model,
                                 issue_receipt, save as save_onboarding)
from task_center_mcp import RemoteTaskCenterMCP
from task_center_mcp_auth import MCPAuthorizationStore
from task_center_mcp_service import (MCPModelWorkerLoop,MCPTaskService,
                                     ensure_schema as ensure_mcp_task_schema,
                                     recover_incomplete_mcp_starts)


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
ASSET_ROOT = os.path.join(ROOT, 'demos', 'task-center-digital-twin')
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
    '/admin.html': ('admin.html', 'text/html; charset=utf-8'),
    '/admin.js': ('admin.js', 'application/javascript; charset=utf-8'),
    '/login.html': ('login.html', 'text/html; charset=utf-8'),
    '/login.js': ('login.js', 'application/javascript; charset=utf-8'),
    '/oauth-callback.html': ('oauth-callback.html', 'text/html; charset=utf-8'),
}

PROJECTION_TABLES = frozenset((
    'tasks', 'events', 'gateway_task_metadata', 'gateway_dependencies',
    'gateway_checkpoints'))
MODEL_TABLES = frozenset((
    'model_providers', 'model_catalog', 'role_templates', 'model_requests',
    'model_usage_events', 'model_evaluations', 'delivery_candidates',
    'candidate_reviews', 'module_settings', 'task_work_specs',
    'model_call_attempts','model_request_bindings','model_call_reservations',
    'model_usage_attempts','model_runtime_limits','approved_skills',
    'role_instances','acceptance_checklists','model_quota_status',
    'codex_execution_intents','codex_execution_events',
    'provider_onboarding_configs'))

ROLE_ACTION_ROLES = {
    'START_TEST_ONLY_TASK': 'TASK_EXECUTOR',
    'CREATE_CODEX_INTENT': 'TASK_EXECUTOR',
    'CANCEL_CODEX_INTENT': 'TASK_EXECUTOR',
    'SUBMIT_CANDIDATE': 'TASK_EXECUTOR',
    'REPORT_TEST_ONLY_PROGRESS': 'TASK_EXECUTOR',
    'SAVE_TEST_ONLY_CHECKPOINT': 'TASK_EXECUTOR',
    'REVIEW_CANDIDATE': 'TASK_REVIEWER',
    'REVIEW_SCOPE_CHANGE': 'TASK_REVIEWER',
    'ACCEPT_CANDIDATE': 'TASK_ACCEPTOR',
}


def _read_owned_secret_file(path, label):
    return read_owned_secret_file(path, label)


class _ReadOnlySupervisor(object):
    """Small projection-only facade; it never initializes or migrates."""
    def __init__(self, connection):
        self.db = connection

    def _task(self, task_id):
        row = self.db.execute('SELECT * FROM tasks WHERE task_id=?',
                              (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return dict(row)


def _read_only_connection(db_path, required_tables):
    """Open the live database in SQLite read-only mode, including WAL data."""
    from urllib.parse import quote
    uri = 'file:%s?mode=ro' % quote(os.path.realpath(db_path), safe='/')
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        actual = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(set(required_tables) - actual)
        if missing:
            raise ValueError('READ_SCHEMA_MISSING:' + ','.join(missing))
        return connection
    except Exception:
        connection.close()
        raise


def read_only_projection(db_path, authority_key, tenant_id, principal_id):
    connection = _read_only_connection(db_path, PROJECTION_TABLES)
    try:
        authority = TestTenantAuthority(authority_key)
        gateway = GatewayKernel.__new__(GatewayKernel)
        gateway.db = connection
        gateway.supervisor = _ReadOnlySupervisor(connection)
        gateway.tenants = authority
        return gateway.projection(authority.issue(tenant_id, principal_id))
    finally:
        connection.close()


def read_only_model_projection(db_path, authority_key, tenant_id,
                               principal_id):
    connection = _read_only_connection(db_path, MODEL_TABLES)
    try:
        authority = TestTenantAuthority(authority_key)
        gateway = GatewayKernel.__new__(GatewayKernel)
        gateway.db = connection
        gateway.supervisor = _ReadOnlySupervisor(connection)
        gateway.tenants = authority
        control = ModelControl.__new__(ModelControl)
        control.gateway = gateway
        control.db = connection
        control.context = authority.issue(tenant_id, 'admin:' + principal_id)
        control.tenant_id = tenant_id
        result = control.projection()
        codex=CodexExecutionControl.__new__(CodexExecutionControl)
        codex.db=connection;codex.tenant_id=tenant_id
        result['codex_executions']=codex.projection()
        result['provider_presets']=public_presets()
        result['provider_onboarding']=onboarding_projection(connection,tenant_id)
        actual = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if {'execution_units','asset_preflight_checks',
                'execution_action_requests'}.issubset(actual):
            policy = ExecutionPolicyGateway.__new__(ExecutionPolicyGateway)
            policy.gateway=gateway;policy.db=connection;policy.context=control.context
            policy.tenant_id=tenant_id
            result['policy']=policy.projection()
        else:
            result['policy']={'units':[],'preflights':[],'actions':[],
                              'mode':'TEST_ONLY','external_execution':
                              'NOT_IMPLEMENTED'}
        return result
    finally:
        connection.close()


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


class CodexWorkerLoop(object):
    """Optional TEST_ONLY durable dispatcher using the canonical SQLite DB."""
    def __init__(self,db_path,authority_key,tenant_id,transports,interval=1.0):
        self.db_path=db_path;self.authority_key=authority_key;self.tenant_id=tenant_id
        self.transports=transports;self.interval=interval;self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self._run,name='codex-test-only-worker')
        self.thread.daemon=True
    def start(self):self.thread.start()
    def stop(self):self.stop_event.set();self.thread.join(5)
    def _run(self):
        supervisor=Supervisor(self.db_path)
        try:
            authority=TestTenantAuthority(self.authority_key)
            control=CodexExecutionControl(GatewayKernel(supervisor,authority),
              authority.issue(self.tenant_id,'admin:codex-worker'))
            control.reconcile_restart()
            while not self.stop_event.is_set():
                reconciled=control.reconcile_transport_once(self.transports)
                sent=control.dispatch_once(self.transports)
                cancelled=control.dispatch_cancel_once(self.transports)
                streamed=control.poll_transport_once(self.transports)
                if (reconciled.get('state') in ('IDLE','UNKNOWN') and sent.get('state')=='IDLE'
                        and cancelled.get('state')=='IDLE' and
                        streamed.get('state') in ('IDLE','RUNNING',
                        'WAITING_APPROVAL','CANCEL_REQUESTED')):
                    self.stop_event.wait(self.interval)
        finally:supervisor.close()


def _normalize_base_path(value):
    value = value or '/'
    if not value.startswith('/') or '//' in value or '?' in value or '#' in value:
        raise ValueError('VALID_BASE_PATH_REQUIRED')
    if not value.endswith('/'):
        value += '/'
    if value != '/' and any(part in ('', '.', '..')
                            for part in value[1:-1].split('/')):
        raise ValueError('VALID_BASE_PATH_REQUIRED')
    return value


def _normalize_external_origin(value):
    if value is None:return None
    parsed=urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('','/')
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('HTTPS_EXTERNAL_ORIGIN_REQUIRED')
    return 'https://'+parsed.netloc


def build_handler(db_path, authority_key, tenant_id, principal_id,
                  model_master_key=None, admin_token=None, actor_tokens=None,
                  codex_transports=None, identity_provider=None,
                  session_store=None, outbound_enabled=False,
                  provider_connection_test_enabled=False,
                  external_origin=None, base_path='/',mcp_auth_store=None):
    actor_tokens = dict(actor_tokens or {})
    codex_transports = dict(codex_transports or {})
    base_path = _normalize_base_path(base_path)
    external_origin = _normalize_external_origin(external_origin)
    external_host = (urlsplit(external_origin).netloc
                     if external_origin is not None else None)
    class TaskCenterHandler(BaseHTTPRequestHandler):
        server_version = 'XuanjunTaskCenter/1.0-TEST_ONLY'

        def log_message(self, fmt, *args):
            # Never log query strings (OAuth codes/state) or request bodies.
            sys.stderr.write('task-center-app: %s %s\n' %
                             (self.command, self.path.split('?', 1)[0]))

        def _send(self, status, body, content_type, extra_headers=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; object-src 'none'; "
                             "frame-ancestors 'none'")
            for name, value in (extra_headers or []):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._host_allowed():
                self._send(421,_json_bytes({'error':'LOOPBACK_HOST_REQUIRED'}),
                  'application/json; charset=utf-8');return
            path = self._route_path()
            if path is None:
                self._send(404,b'not found\n','text/plain; charset=utf-8');return
            if path == '/healthz':
                self._send(200, _json_bytes({'state':'UP','mode':'TEST_ONLY',
                  'outbound':'DISABLED' if not outbound_enabled else
                  'TEST_FIXTURE_ONLY','provider_connection_test':
                  'ENABLED' if provider_connection_test_enabled else 'DISABLED'}),
                  'application/json; charset=utf-8');return
            if path == '/readyz':
                try:
                    connection=_read_only_connection(db_path,PROJECTION_TABLES)
                    connection.close()
                    self._send(200,_json_bytes({'state':'READY','mode':'TEST_ONLY',
                      'identity_adapter':('CONFIGURED' if identity_provider else
                      'NOT_CONFIGURED')}),'application/json; charset=utf-8')
                except Exception as exc:
                    self._send(503,_json_bytes({'state':'NOT_READY',
                      'detail':str(exc)}),'application/json; charset=utf-8')
                return
            if path == '/.well-known/oauth-protected-resource':
                if mcp_auth_store is None:
                    self._send(404,b'not found\n','text/plain; charset=utf-8');return
                self._send(200,_json_bytes(
                  mcp_auth_store.protected_resource_metadata()),
                  'application/json; charset=utf-8');return
            if path == '/.well-known/oauth-authorization-server':
                if mcp_auth_store is None:
                    self._send(404,b'not found\n','text/plain; charset=utf-8');return
                base=(external_origin or ('http://'+self.headers.get('Host')))+(
                  base_path[:-1] if base_path!='/' else '')
                self._send(200,_json_bytes(
                  mcp_auth_store.authorization_server_metadata(base)),
                  'application/json; charset=utf-8');return
            if path == '/oauth/authorize':
                if mcp_auth_store is None:
                    self._send(404,b'not found\n','text/plain; charset=utf-8');return
                session=self._session()
                if session is None:
                    target=self.path
                    self.send_response(302);self.send_header('Location',
                      self._external_path('/login.html')+'?next='+
                      __import__('urllib.parse').parse.quote(target,safe=''))
                    self.send_header('Cache-Control','no-store');self.end_headers();return
                if 'TASK_CENTER_ADMIN' not in session['roles']:
                    self._send(403,_json_bytes({'error':'MCP_OWNER_REQUIRED'}),
                      'application/json; charset=utf-8');return
                try:
                    query=__import__('urllib.parse').parse.parse_qs(
                      urlsplit(self.path).query,keep_blank_values=True)
                    params={key:values[-1] for key,values in query.items()}
                    location=mcp_auth_store.authorize(session,params)
                    self.send_response(302);self.send_header('Location',location)
                    self.send_header('Cache-Control','no-store');self.end_headers()
                except Exception as exc:
                    self._send(400,_json_bytes({'error':type(exc).__name__,
                      'detail':str(exc)}),'application/json; charset=utf-8')
                return
            if path == '/mcp':
                self._send(405,_json_bytes({'error':'MCP_POST_REQUIRED'}),
                  'application/json; charset=utf-8',[('Allow','POST')]);return
            if path == '/api/session':
                session=self._session()
                if session is None:
                    self._send(401,_json_bytes({'error':'LOGIN_REQUIRED'}),
                      'application/json; charset=utf-8');return
                self._send(200,_json_bytes({'principal_id':session['principal_id'],
                  'tenant_id':session['tenant_id'],'roles':session['roles'],
                  'expires_at':session['expires_at']}),
                  'application/json; charset=utf-8');return
            if (session_store is not None and path in ('/','/index.html',
                    '/admin.html') and self._session() is None):
                self.send_response(302);self.send_header('Location',self._external_path('/login.html'))
                self.send_header('Cache-Control','no-store');self.end_headers();return
            if path == '/api/projection':
                if session_store is not None and self._session() is None:
                    self._send(401,_json_bytes({'error':'LOGIN_REQUIRED'}),
                      'application/json; charset=utf-8');return
                try:
                    self._send(200, _json_bytes(read_only_projection(
                               db_path, authority_key, tenant_id,
                               principal_id)),
                               'application/json; charset=utf-8')
                except Exception as exc:
                    self._send(500, _json_bytes({
                        'mode': 'TEST_ONLY', 'error': type(exc).__name__,
                        'detail': str(exc), 'production_status':
                        'NOT_IMPLEMENTED'}),
                        'application/json; charset=utf-8')
                return
            if path == '/api/admin/model-control':
                if not self._admin_allowed():
                    self._send(403, _json_bytes({'error':'ADMIN_REQUIRED'}),
                               'application/json; charset=utf-8'); return
                try:
                    self._send(200, _json_bytes(read_only_model_projection(
                               db_path, authority_key, tenant_id,
                               principal_id)),
                               'application/json; charset=utf-8')
                except Exception as exc:
                    self._send(400,_json_bytes({'error':str(exc)}),
                               'application/json; charset=utf-8')
                return
            asset = ASSETS.get(path)
            if asset is None:
                self._send(404, b'not found\n', 'text/plain; charset=utf-8')
                return
            with open(os.path.join(ASSET_ROOT, asset[0]), 'rb') as stream:
                self._send(200, stream.read(), asset[1])

        def do_POST(self):
            if not self._host_allowed():
                self._send(421,_json_bytes({'error':'HOST_REQUIRED'}),
                  'application/json; charset=utf-8');return
            path = self._route_path()
            if path is None:
                self._send(404,b'not found\n','text/plain; charset=utf-8');return
            if path in ('/oauth/register','/oauth/token','/mcp'):
                return self._mcp_post(path)
            if not self._origin_allowed():
                self._send(403,_json_bytes({'error':'SAME_ORIGIN_REQUIRED'}),
                  'application/json; charset=utf-8');return
            if path == '/api/session/login':
                return self._login()
            if path == '/api/session/logout':
                session=self._session();token=self._session_token()
                if session is None:
                    self._send(401,_json_bytes({'error':'LOGIN_REQUIRED'}),
                      'application/json; charset=utf-8');return
                if not session_store.verify_csrf(session,
                        self.headers.get('X-CSRF-Token')):
                    self._send(403,_json_bytes({'error':'CSRF_REQUIRED'}),
                      'application/json; charset=utf-8');return
                session_store.revoke(token)
                self._send(200,_json_bytes({'state':'LOGGED_OUT'}),
                  'application/json; charset=utf-8', [('Set-Cookie',
                  session_store.COOKIE+'=; Path='+base_path+'; HttpOnly; SameSite=Strict; '+self._secure_cookie()+'Max-Age=0'),
                  ('Set-Cookie',session_store.CSRF_COOKIE+
                   '=; Path='+base_path+'; SameSite=Strict; '+self._secure_cookie()+'Max-Age=0')]);return
            if path != '/api/admin/model-control':
                self._send(405,b'read only\n','text/plain; charset=utf-8');return
            session=self._session()
            if session_store is not None:
                if session is None:
                    self._send(401,_json_bytes({'error':'LOGIN_REQUIRED'}),
                               'application/json; charset=utf-8');return
                if not session_store.verify_csrf(session,
                        self.headers.get('X-CSRF-Token')):
                    self._send(403,_json_bytes({'error':'CSRF_REQUIRED'}),
                               'application/json; charset=utf-8');return
            elif not self._admin_allowed():
                self._send(403,_json_bytes({'error':'ADMIN_REQUIRED'}),
                           'application/json; charset=utf-8');return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<2 or length>65536:raise ValueError('BODY_LIMIT')
                value=json.loads(self.rfile.read(length).decode('utf-8'))
                action=value.pop('action')
                required_role=ROLE_ACTION_ROLES.get(action)
                if session is not None:
                    if required_role is not None and required_role not in session['roles']:
                        self._send(403,_json_bytes({'error':'ROLE_REQUIRED',
                          'required_role':required_role}),
                          'application/json; charset=utf-8');return
                    if (required_role is None and
                            'TASK_CENTER_ADMIN' not in session['roles']):
                        self._send(403,_json_bytes({'error':'ADMIN_REQUIRED'}),
                          'application/json; charset=utf-8');return
                supervisor, control=self._model_control()
                try:
                    actor=None
                    if required_role is not None:
                        actor=self._actor_principal()
                        if actor is None:
                            raise ValueError('AUTHENTICATED_ACTOR_REQUIRED')
                        control=ModelControl(control.gateway,
                          control.gateway.tenants.issue(tenant_id,actor),
                          model_master_key)
                    if action=='UPSERT_PROVIDER':
                        result=control.upsert_provider(value['config'],value.get('secret'))
                    elif action=='TEST_PROVIDER_CONNECTION':
                        if not provider_connection_test_enabled:
                            raise ValueError('PROVIDER_CONNECTION_TEST_DISABLED')
                        credential=value.get('credential')
                        if not credential:
                            credential,_,_=saved_credential(control,
                              model_master_key,value['platform'],
                              value.get('connection_name'))
                        tested=test_connection(value['platform'],credential)
                        tested['test_receipt']=issue_receipt(model_master_key,
                          tenant_id,value['platform'],credential,
                          tested['models'])
                        result=tested
                    elif action=='SAVE_PROVIDER_ONBOARDING':
                        credential=value.get('credential')
                        if not credential:
                            credential,_,_=saved_credential(control,
                              model_master_key,value['platform'],
                              value.get('connection_name'))
                        result=save_onboarding(control,model_master_key,
                          value['platform'],value.get('connection_name'),
                          credential,value['model_id'],
                          value['test_receipt'],value.get('call_receipt'))
                    elif action=='TEST_PROVIDER_MODEL':
                        if not provider_connection_test_enabled:
                            raise ValueError('PROVIDER_CONNECTION_TEST_DISABLED')
                        credential=value.get('credential')
                        if not credential:
                            credential,_,_=saved_credential(control,
                              model_master_key,value['platform'],
                              value.get('connection_name'))
                        result=test_model(control,model_master_key,tenant_id,
                          value['platform'],credential,value['model_id'],
                          value['test_receipt'],value.get('confirm_paid_test') is True)
                    elif action=='UPSERT_CONNECTION':
                        result=ConnectionManager(control.gateway,control.context,
                          model_master_key).upsert(value['config'],value.get('credential'))
                    elif action=='BEGIN_OAUTH':
                        result=ConnectionManager(control.gateway,control.context,
                          model_master_key).begin_oauth(value['connection_id'])
                    elif action=='COMPLETE_OAUTH':
                        if not outbound_enabled:raise ValueError('REAL_OUTBOUND_DISABLED')
                        result=ConnectionManager(control.gateway,control.context,
                          model_master_key).complete_oauth(value['connection_id'],
                          value['flow_id'],value['state'],value['code'],
                          value['issuer'],value['redirect_uri'])
                    elif action=='REFRESH_OAUTH':
                        if not outbound_enabled:raise ValueError('REAL_OUTBOUND_DISABLED')
                        result=ConnectionManager(control.gateway,control.context,
                          model_master_key).refresh(value['connection_id'])
                    elif action=='REVOKE_CONNECTION':
                        result=ConnectionManager(control.gateway,control.context,
                          model_master_key).revoke(value['connection_id'])
                    elif action=='DISABLE_PROVIDER':
                        result=control.disable_provider(value['provider_id'])
                    elif action=='UPSERT_MODEL':result=control.upsert_model(value['config'])
                    elif action=='CREATE_ROLE':result=control.create_role(value['config'])
                    elif action=='CONFIGURE_INSTANCE':result=control.configure_instance(
                        value['instance_id'],value['role_id'],
                        value['role_version'],value['desired_state'])
                    elif action=='BIND_SKILL':result=control.bind_skill(value['role_id'],value['role_version'],value['skill_id'],value['skill_version'],value['review_sha256'],value['status'])
                    elif action=='REGISTER_SKILL':result=control.register_skill(
                        value['skill_id'],value['skill_version'],value['content'],
                        value['review_sha256'])
                    elif action=='REVOKE_SKILL':result=control.revoke_skill(
                        value['skill_id'],value['skill_version'])
                    elif action=='SET_RUNTIME_LIMITS':result=control.set_runtime_limits(
                        value['provider_id'],value['tpm_limit'],
                        value['max_output_tokens'],value.get('tenant_budget'),
                        value.get('task_budget'))
                    elif action=='SET_QUOTA_STATUS':result=control.set_quota_status(
                        value['provider_id'],value['quota_state'],
                        value['quota_source'],value.get('verified_at'),
                        value.get('unavailable_reason'))
                    elif action=='REGISTER_GRAPH':
                        result=control.gateway.register_graph(control.context,value['graph'])
                    elif action=='CREATE_PROJECT_TASK':
                        fields=value['task']
                        required={'project_id','task_id','board_id','goal',
                          'deliverables','acceptance','dependencies','priority',
                          'owner','delivery_stage','feature_unit','scope',
                          'asset_version'}
                        if not isinstance(fields,dict) or set(fields)!=required:
                            raise ValueError('EXACT_PROJECT_TASK_REQUIRED')
                        seed=canonical(fields)
                        digest=hashlib.sha256(seed.encode('utf-8')).hexdigest()
                        graph={'graph_id':'graph-'+digest[:24],
                          'tenant_id':tenant_id,'project_id':fields['project_id'],
                          'graph_version':'v1-'+digest[:12],'tasks':[{
                          'task_id':fields['task_id'],'node_id':'node-'+digest[:12],
                          'stage':'TEST_ONLY_EXECUTION','owner':fields['owner'],
                          'entry':'model-scheduler-runtime','checkpoint_sha256':
                          hashlib.sha256(b'{}').hexdigest(),'spec_sha256':digest,
                          'input_version':'v1','output_version':'v1',
                          'priority':fields['priority'],'preemptible':True,
                          'module_id':'xuanjun.scheduler.kernel',
                          'resources':['fake:'+fields['task_id']],
                          'dependencies':fields['dependencies'],
                          'board_id':fields['board_id'],
                          'completion_evidence':fields['acceptance']} ]}
                        # Validate every post-registration business field before
                        # the canonical graph write.  A rejected unit therefore
                        # leaves no half-created graph/task.
                        unit={'task_id':fields['task_id'],
                          'delivery_stage':fields['delivery_stage'],
                          'feature_unit':fields['feature_unit'],
                          'goal':fields['goal'],'scope':fields['scope'],
                          'acceptance':fields['acceptance'],
                          'dependencies':fields['dependencies'] or ['NONE'],
                          'asset_version':fields['asset_version'],
                          'responsible_party':fields['owner']}
                        ExecutionPolicyGateway.validate_unit_input(unit)
                        if (not fields['deliverables'] or not fields['acceptance']):
                            raise ValueError('TASK_SPEC_ARRAYS_REQUIRED')
                        result=control.gateway.register_graph(control.context,graph)
                        control.record_task_spec(fields['task_id'],fields['goal'],
                          fields['deliverables'],fields['acceptance'])
                        policy=ExecutionPolicyGateway(control.gateway,
                          control.context)
                        policy.record_unit(unit)
                        result['graph_id']=graph['graph_id']
                    elif action=='START_TEST_ONLY_TASK':
                        ExecutionPolicyGateway(control.gateway,
                          control.context).require_dispatch_ready(value['task_id'])
                        fence=Fence(supervisor,db_path+'.test-only-locks')
                        try:
                            executor=TestOnlyExecutor(control.gateway,fence,
                                                      control.context)
                            result=executor.start(value['task_id'],
                              value['attempt_id'],
                              control.gateway.canonical_resources(
                                value['task_id']),__import__('time').time()+600)
                        finally:fence.close()
                    elif action=='ASSIGN_ROLE':
                        ExecutionPolicyGateway(control.gateway,
                          control.context).require_dispatch_ready(value['task_id'])
                        result=control.assign(value['task_id'],value['role_id'],
                          value['role_version'],value['principal_id'],
                          bool(value.get('allow_paid',False)))
                    elif action=='QUEUE_REQUEST':
                        ExecutionPolicyGateway(control.gateway,
                          control.context).require_dispatch_ready(value['task_id'])
                        result=control.queue_request(value['task_id'],
                          value['role_id'],value['messages'],
                          value['idempotency_key'],value.get('max_output_tokens'),
                          value.get('connection_id'))
                    elif action in ('REPORT_TEST_ONLY_PROGRESS',
                                     'SAVE_TEST_ONLY_CHECKPOINT'):
                        task=supervisor._task(value['task_id'])
                        assigned=supervisor.db.execute('''SELECT 1 FROM
                          model_assignments WHERE tenant_id=? AND task_id=? AND
                          attempt_id=? AND principal_id=?''',(tenant_id,
                          value['task_id'],task['attempt_id'],actor)).fetchone()
                        if assigned is None:
                            raise ValueError('CURRENT_ASSIGNED_ACTOR_REQUIRED')
                        if action=='REPORT_TEST_ONLY_PROGRESS':
                            fence=Fence(supervisor,db_path+'.test-only-locks')
                            try:result=TestOnlyExecutor(control.gateway,fence,
                              control.context).progress(value['task_id'],
                              task['attempt_id'],value['event_id'],
                              value['evidence_ref'])
                            finally:fence.close()
                        else:
                            result=control.gateway.save_checkpoint(
                              control.context,value['task_id'],task['attempt_id'],
                              value['checkpoint_id'],value['payload'],
                              value['inflight'],value['effects_state'],
                              control.gateway.canonical_resources(
                                value['task_id']))
                    elif action=='CANCEL_REQUEST':
                        result=control.request_cancel(value['request_id'])
                    elif action=='REGISTER_BENCHMARK':
                        result=control.register_benchmark_suite(
                          value['suite_version'],value['cases'])
                    elif action=='RUN_BENCHMARK':
                        if not outbound_enabled:raise ValueError('REAL_OUTBOUND_DISABLED')
                        result=control.run_benchmark(value['provider_id'],
                          value['model_id'],value['suite_version'],
                          allow_paid=bool(value.get('allow_paid',False)))
                    elif action=='RUN_SCHEDULER_ONCE':
                        if not outbound_enabled:raise ValueError('REAL_OUTBOUND_DISABLED')
                        result=ModelScheduler(control).run_once()
                    elif action=='CREATE_CODEX_INTENT':
                        result=CodexExecutionControl(control.gateway,
                          control.context).create_intent(value['task_id'],
                          value['transport_kind'],value['idempotency_key'],
                          value['context'])
                    elif action=='CANCEL_CODEX_INTENT':
                        result=CodexExecutionControl(control.gateway,
                          control.context).cancel(value['intent_id'])
                    elif action=='RECONCILE_CODEX_RESTART':
                        result=CodexExecutionControl(control.gateway,
                          control.context).reconcile_restart()
                    elif action=='RUN_CODEX_ADAPTER_ONCE':
                        if not outbound_enabled:raise ValueError('REAL_OUTBOUND_DISABLED')
                        result=CodexExecutionControl(control.gateway,
                          control.context).dispatch_once(codex_transports)
                    elif action=='RUN_CODEX_CANCEL_ONCE':
                        if not outbound_enabled:raise ValueError('REAL_OUTBOUND_DISABLED')
                        result=CodexExecutionControl(control.gateway,
                          control.context).dispatch_cancel_once(codex_transports)
                    elif action=='SUBMIT_CANDIDATE':
                        if value['submitted_by']!=actor:
                            raise ValueError('AUTHENTICATED_EXECUTOR_REQUIRED')
                        result=control.submit_candidate(value['task_id'],
                          value['artifact_sha256'],value['checklist_sha256'],
                          value['submitted_by'])
                    elif action=='REGISTER_CHECKLIST':
                        result=control.register_checklist(value['task_id'],
                          value['items'],actor or control.context['principal_id'])
                    elif action=='REVIEW_CANDIDATE':
                        if value['reviewer']!=actor:
                            raise ValueError('AUTHENTICATED_REVIEWER_REQUIRED')
                        result=control.review_candidate(value['candidate_id'],
                          value['reviewer'],value['findings'],
                          bool(value['passed']),value.get('review_kind','QA'))
                    elif action=='ACCEPT_CANDIDATE':
                        if value['acceptor']!=actor:
                            raise ValueError('AUTHENTICATED_ACCEPTOR_REQUIRED')
                        candidate=control.validate_accept_candidate(
                          value['candidate_id'],value['acceptor'])
                        fence=Fence(supervisor,db_path+'.test-only-locks')
                        try:
                            task=supervisor._task(candidate['task_id'])
                            if (task['state']=='SUCCESS' and
                                    task['authority_state']=='REVOKED'):
                                terminal={'state':'SUCCESS','recovered':True}
                            else:
                                terminal=TestOnlyExecutor(control.gateway,fence,
                                  control.context).complete_success(
                                  candidate['task_id'],candidate['attempt_id'],
                                  candidate['artifact_sha256'],
                                  json.loads(task['completion_json']))
                        finally:fence.close()
                        result=control.accept_candidate(value['candidate_id'],
                          value['acceptor'])
                        result['canonical_task_state']=terminal['state']
                    elif action=='SET_MODULE':
                        result=control.set_module(value['module_id'],
                          value['version'],bool(value['enabled']))
                    elif action=='RECORD_PREFLIGHT':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).record_preflight(value['task_id'],
                          value['checked'],value['outcome'],value.get('reused_asset'),
                          value.get('reused_version'),bool(value['need_new']),
                          value['reason'],value['evidence_ref'],
                          query_ids=value.get('query_ids'))
                    elif action=='RECORD_ASSET_QUERY':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).record_asset_query(value['task_id'],
                          value['query_id'],value['source_kind'],
                          value['source_version'],value['query'],
                          value['result_digest'])
                    elif action=='QUERY_CANONICAL_ASSET':
                        policy=ExecutionPolicyGateway(control.gateway,
                          control.context)
                        asset_key=value['asset_key'];version=value['source_version']
                        row=supervisor.db.execute('''SELECT content_json FROM
                          canonical_asset_registry WHERE tenant_id=? AND
                          asset_key=? AND source_version=?''',(tenant_id,
                          asset_key,version)).fetchone()
                        observed=(json.loads(row['content_json']) if row else
                                  {'matches':[]})
                        query={'lookup':{'asset_key':asset_key},
                          'observed_result':observed,
                          'evidence_ref':'canonical-db://%s@%s'%(asset_key,version)}
                        digest=hashlib.sha256(canonical(observed).encode()).hexdigest()
                        result=policy.record_asset_query(value['task_id'],
                          value['query_id'],'CANONICAL_DB',version,query,digest)
                    elif action=='UPSERT_CANONICAL_ASSET':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).upsert_canonical_asset(
                          value['asset_key'],value['source_version'],
                          value['content'])
                    elif action=='RECORD_DISPATCH_PREFLIGHT':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).record_dispatch_preflight(
                          value['task_id'],value['asset_version'],
                          value['query_ids'],value['outcome'],
                          value['reuse_reason'])
                    elif action=='GRANT_APPROVAL_ROLE':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).grant_approval_role(value['task_id'],
                          value['principal_id'],value['approval_kind'],
                          value['valid_until'])
                    elif action=='ADD_TEST_AUTHORIZATION':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).add_authorization(
                          value['authorization_id'],value['task_id'],
                          value['asset_version'],value['writer_principal'],
                          value['source_kind'],value['scopes'],
                          bool(value['read_only']),
                          value['valid_from'],value['valid_until'],
                          value['evidence_ref'])
                    elif action=='PROPOSE_SCOPE_CHANGE':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).propose_change(value['change_id'],
                          value['task_id'],value['base_asset_version'],
                          value['new_scope'],value['reason'])
                    elif action=='REVIEW_SCOPE_CHANGE':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).review_change(value['change_id'],
                          value['reviewer'],bool(value['approved']),
                          value['evidence_ref'])
                    elif action=='REQUEST_ACTION':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).request_action(value['request'])
                    else:raise ValueError('UNKNOWN_ADMIN_ACTION')
                finally:supervisor.close()
                self._send(200,_json_bytes(result),'application/json; charset=utf-8')
            except Exception as exc:
                self._send(400,_json_bytes({'error':type(exc).__name__,
                  'detail':str(exc)}),'application/json; charset=utf-8')

        def _admin_allowed(self):
            session=self._session()
            if session is not None:
                return 'TASK_CENTER_ADMIN' in session['roles']
            if session_store is not None:return False
            supplied=self.headers.get('X-Test-Admin-Token')
            return (admin_token is not None and supplied is not None and
                    __import__('hmac').compare_digest(admin_token,supplied))

        def _actor_principal(self):
            session=self._session()
            if session is not None:return session['principal_id']
            if session_store is not None:return None
            supplied=self.headers.get('X-Test-Actor-Token')
            if supplied is None:return None
            for token,actor in actor_tokens.items():
                if __import__('hmac').compare_digest(token,supplied):
                    return actor
            return None

        def _session_token(self):
            if session_store is None:return None
            cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
            item=cookie.get(session_store.COOKIE)
            return item.value if item is not None else None

        def _mcp_post(self,path):
            if mcp_auth_store is None or model_master_key is None:
                self._send(404,b'not found\n','text/plain; charset=utf-8');return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<1 or length>65536:raise ValueError('BODY_LIMIT')
                raw=self.rfile.read(length)
                if path=='/oauth/register':
                    value=json.loads(raw.decode('utf-8'))
                    result=mcp_auth_store.register(value)
                    self._send(201,_json_bytes(result),
                      'application/json; charset=utf-8');return
                if path=='/oauth/token':
                    parsed=__import__('urllib.parse').parse.parse_qs(
                      raw.decode('utf-8'),keep_blank_values=True)
                    params={key:values[-1] for key,values in parsed.items()}
                    result=mcp_auth_store.exchange(params)
                    self._send(200,_json_bytes(result),
                      'application/json; charset=utf-8');return
                value=json.loads(raw.decode('utf-8'))
                method=value.get('method')
                scope=('task:submit' if method=='tools/call' and
                  (value.get('params') or {}).get('name')=='task_submit'
                  else 'task:read')
                identity=mcp_auth_store.authenticate(
                  self.headers.get('Authorization'),scope)
                if identity is None:
                    metadata=((external_origin or
                      ('http://'+self.headers.get('Host')))+
                      (base_path if base_path!='/' else '/')+
                      '.well-known/oauth-protected-resource')
                    self._send(401,_json_bytes({'error':'MCP_AUTH_REQUIRED'}),
                      'application/json; charset=utf-8',[('WWW-Authenticate',
                      'Bearer resource_metadata="%s", scope="%s"'%(metadata,scope))]);return
                service=MCPTaskService(db_path,authority_key,tenant_id,
                  model_master_key,identity['principal_id'],identity['project_id'])
                result=RemoteTaskCenterMCP(service).rpc(value)
                if value.get('id') is None:
                    self._send(202,b'','application/json; charset=utf-8');return
                self._send(200,_json_bytes(result),
                  'application/json; charset=utf-8')
            except Exception as exc:
                self._send(400,_json_bytes({'error':type(exc).__name__,
                  'detail':str(exc)}),'application/json; charset=utf-8')

        def _host_allowed(self):
            supplied=self.headers.get('Host','')
            if external_host is not None:
                return supplied.lower() == external_host.lower()
            allowed={'127.0.0.1:%d'%self.server.server_port,
                     'localhost:%d'%self.server.server_port,
                     '[::1]:%d'%self.server.server_port}
            return supplied in allowed

        def _origin_allowed(self):
            origin=self.headers.get('Origin')
            if external_origin is not None:
                return origin == external_origin
            if origin is None:return True
            supplied=self.headers.get('Host','')
            return origin=='http://'+supplied

        def _route_path(self):
            raw=self.path.split('?',1)[0]
            # RFC 8414 section 3.1 inserts a path-bearing issuer after the
            # well-known prefix.  Keep the historical below-base alias for
            # compatibility, while also exposing the standards-derived path
            # used by remote MCP clients.
            issuer_path=(base_path[:-1] if base_path!='/' else '')
            if raw=='/.well-known/oauth-authorization-server'+issuer_path:
                return '/.well-known/oauth-authorization-server'
            if base_path == '/':return raw
            prefix=base_path[:-1]
            if raw == prefix:return '/'
            if not raw.startswith(base_path):return None
            return '/'+raw[len(base_path):]

        def _external_path(self, path):
            return ((base_path[:-1] if base_path != '/' else '') + path)

        def _secure_cookie(self):
            return 'Secure; ' if external_origin is not None else ''

        def _session(self):
            return (session_store.get(self._session_token())
                    if session_store is not None else None)

        def _login(self):
            if identity_provider is None or session_store is None:
                self._send(503,_json_bytes({'error':'LOGIN_NOT_CONFIGURED'}),
                  'application/json; charset=utf-8');return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<2 or length>8192:raise ValueError('BODY_LIMIT')
                value=json.loads(self.rfile.read(length).decode('utf-8'))
                if set(value)!={'username','password'}:raise ValueError('EXACT_LOGIN_REQUIRED')
                identity=identity_provider.verify(value['username'],value['password'])
                if identity is None:raise ValueError('INVALID_CREDENTIALS')
                token,csrf,expires=session_store.create(identity)
                self._send(200,_json_bytes({'state':'AUTHENTICATED',
                  'principal_id':identity['principal_id'],'roles':identity['roles'],
                  'csrf_token':csrf,'expires_at':expires}),
                  'application/json; charset=utf-8', [('Set-Cookie',
                  '%s=%s; Path=%s; HttpOnly; SameSite=Strict; %sMax-Age=%d'%(
                  session_store.COOKIE,token,base_path,self._secure_cookie(),session_store.ttl_seconds)),
                  ('Set-Cookie','%s=%s; Path=%s; SameSite=Strict; %sMax-Age=%d'%(
                  session_store.CSRF_COOKIE,csrf,base_path,self._secure_cookie(),session_store.ttl_seconds))])
            except Exception as exc:
                self._send(401,_json_bytes({'error':type(exc).__name__,
                  'detail':str(exc)}),'application/json; charset=utf-8')

        def _model_control(self):
            if model_master_key is None:raise ValueError('MODEL_ADMIN_DISABLED')
            supervisor=Supervisor(db_path)
            authority=TestTenantAuthority(authority_key)
            gateway=GatewayKernel(supervisor,authority)
            session=self._session()
            current=(session['principal_id'] if session is not None else
                     principal_id)
            context=authority.issue(tenant_id,'admin:'+current)
            return supervisor,ModelControl(gateway,context,model_master_key)

    return TaskCenterHandler


def make_server(db_path, authority_key, tenant_id, principal_id,
                host='127.0.0.1', port=8765, model_master_key=None,
                admin_token=None, actor_tokens=None,codex_transports=None,
                identity_provider=None,session_store=None,
                outbound_enabled=True,provider_connection_test_enabled=False,
                external_origin=None,base_path='/',mcp_enabled=False,
                mcp_model_worker_enabled=False,mcp_worker_adapters=None):
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('LOOPBACK_HOST_REQUIRED')
    if not os.path.isfile(db_path):
        raise ValueError('CANONICAL_SQLITE_REQUIRED')
    # Schema initialization is an explicit startup phase.  GET handlers remain
    # pure read-only and never migrate or create tables.
    if model_master_key is not None:
        supervisor=Supervisor(db_path)
        try:
            authority=TestTenantAuthority(authority_key)
            gateway=GatewayKernel(supervisor,authority)
            ModelControl(gateway,authority.issue(tenant_id,
              'admin:'+principal_id),model_master_key)
            ensure_onboarding_schema(supervisor.db)
            ConnectionManager(gateway,authority.issue(tenant_id,
              'admin:'+principal_id),model_master_key)
            CodexExecutionControl(gateway,authority.issue(tenant_id,
              'admin:'+principal_id))
        finally:supervisor.close()
    mcp_auth_store=None
    if mcp_enabled:
        if identity_provider is None or session_store is None or external_origin is None:
            raise ValueError('MCP_SESSION_AND_HTTPS_REQUIRED')
        def mcp_connect():
            db=sqlite3.connect(os.path.realpath(db_path),timeout=5)
            db.row_factory=sqlite3.Row;return db
        normalized_base=_normalize_base_path(base_path)
        issuer=external_origin+(normalized_base[:-1] if normalized_base!='/' else '')
        resource=external_origin+(normalized_base if normalized_base!='/' else '/')+'mcp'
        mcp_auth_store=MCPAuthorizationStore(mcp_connect,tenant_id,issuer,resource)
        mcp_db=mcp_connect()
        try:ensure_mcp_task_schema(mcp_db)
        finally:mcp_db.close()
        # A fresh service process proves the prior local process stopped.  Only
        # then may the existing fenced recovery contract revoke incomplete MCP
        # claims that never produced a STARTED receipt.
        recover_incomplete_mcp_starts(os.path.realpath(db_path),authority_key,
                                      tenant_id)
    handler = build_handler(os.path.realpath(db_path), authority_key,
                            tenant_id, principal_id, model_master_key,
                            admin_token, actor_tokens,codex_transports,
                            identity_provider,session_store,outbound_enabled,
                            provider_connection_test_enabled,
                            external_origin,base_path,mcp_auth_store)
    server=HTTPServer((host, port), handler)
    server.codex_worker=None
    if codex_transports:
        server.codex_worker=CodexWorkerLoop(os.path.realpath(db_path),
          authority_key,tenant_id,codex_transports);server.codex_worker.start()
    server.mcp_worker=None
    if mcp_model_worker_enabled:
        if not mcp_enabled:raise ValueError('MCP_WORKER_REQUIRES_MCP')
        server.mcp_worker=MCPModelWorkerLoop(os.path.realpath(db_path),
          authority_key,tenant_id,model_master_key,adapters=mcp_worker_adapters)
        server.mcp_worker.start()
    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    authority = parser.add_mutually_exclusive_group(required=True)
    authority.add_argument('--test-authority-key')
    authority.add_argument('--test-authority-key-file')
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--principal', default='local-ui-viewer')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--model-master-key-file')
    parser.add_argument('--admin-token-file')
    parser.add_argument('--actor-token-file')
    parser.add_argument('--codex-app-server-command-json')
    parser.add_argument('--test-identity-file')
    parser.add_argument('--session-ttl-seconds',type=int,default=1800)
    parser.add_argument('--allow-loopback-fixture-outbound',action='store_true')
    parser.add_argument('--allow-provider-connection-test',action='store_true')
    parser.add_argument('--external-origin')
    parser.add_argument('--base-path',default='/')
    parser.add_argument('--enable-mcp',action='store_true')
    parser.add_argument('--allow-mcp-model-outbound',action='store_true')
    args = parser.parse_args(argv)
    raw_key = (args.test_authority_key if args.test_authority_key is not None
               else _read_owned_secret_file(args.test_authority_key_file,
                                             'TEST_AUTHORITY_KEY').rstrip('\r\n'))
    if not raw_key:
        raise ValueError('VALID_TEST_AUTHORITY_KEY_REQUIRED')
    key = raw_key.encode('utf-8')
    model_key = (load_master_key(args.model_master_key_file)
                 if args.model_master_key_file else None)
    admin_token = None
    if args.admin_token_file:
        admin_token=_read_owned_secret_file(args.admin_token_file,
          'ADMIN_TOKEN').strip()
        if len(admin_token) < 16:raise ValueError('VALID_ADMIN_TOKEN_REQUIRED')
    actor_tokens={}
    if args.actor_token_file:
        configured=json.loads(_read_owned_secret_file(args.actor_token_file,
          'ACTOR_TOKEN'))
        if (not isinstance(configured,dict) or not configured or
                any(not isinstance(p,str) or not p or not isinstance(t,str)
                    or len(t)<16 for p,t in configured.items())):
            raise ValueError('VALID_ACTOR_TOKEN_MAP_REQUIRED')
        actor_tokens={token:principal for principal,token in configured.items()}
    codex_transports={}
    if args.codex_app_server_command_json:
        if not args.allow_loopback_fixture_outbound:
            raise ValueError('CODEX_TRANSPORT_REQUIRES_FIXTURE_OUTBOUND_FLAG')
        command=json.loads(args.codex_app_server_command_json)
        codex_transports['CODEX_APP_SERVER']=CodexAppServerTransport(command=command)
    identity_provider=None;session_store=None
    if args.test_identity_file:
        identity_provider=FileTestIdentityProvider(args.test_identity_file)
        def connect():
            db=sqlite3.connect(os.path.realpath(args.db),timeout=5)
            db.row_factory=sqlite3.Row
            return db
        session_store=SessionStore(connect,args.tenant,args.session_ttl_seconds)
    if model_key is None and (admin_token is not None or identity_provider is not None):
        raise ValueError('MODEL_KEY_REQUIRED_FOR_ADMIN_ACCESS')
    if model_key is not None and admin_token is None and identity_provider is None:
        raise ValueError('ADMIN_TOKEN_OR_IDENTITY_REQUIRED')
    if identity_provider is not None and (admin_token is not None or actor_tokens):
        raise ValueError('SINGLE_AUTH_MODE_REQUIRED')
    server = make_server(args.db, key, args.tenant, args.principal,
                         args.host, args.port, model_key, admin_token,
                         actor_tokens,codex_transports,identity_provider,
                         session_store,args.allow_loopback_fixture_outbound,
                         args.allow_provider_connection_test,
                         args.external_origin,args.base_path,args.enable_mcp,
                         args.allow_mcp_model_outbound)
    advertised_origin=(args.external_origin or
                       'http://%s:%d'%server.server_address)
    advertised_base=_normalize_base_path(args.base_path)
    receipt = {'state': 'STARTED', 'mode': 'TEST_ONLY',
               'url': advertised_origin+advertised_base,
               'db': os.path.realpath(args.db), 'tenant_id': args.tenant,
               'production_mutation_api': 'DISABLED',
               'test_only_admin_mutation_api': ('ENABLED' if model_key else
                                                'DISABLED'),
               'model_admin_api': ('TEST_ONLY_ENABLED' if model_key else
                                   'DISABLED'),
               'authentication': ('INJECTED_TEST_IDENTITY' if identity_provider
                                  else 'LEGACY_TEST_TOKEN'),
               'real_outbound': ('TEST_FIXTURE_ONLY' if
                                  args.allow_loopback_fixture_outbound else
                                  'DISABLED'),
               'provider_connection_test': ('ENABLED' if
                  args.allow_provider_connection_test else 'DISABLED'),
               'mcp': ('ENABLED' if args.enable_mcp else 'DISABLED'),
               'mcp_model_outbound': ('ENABLED_ZERO_SPEND_GATES' if
                  args.allow_mcp_model_outbound else 'DISABLED'),
               'production_status': 'NOT_IMPLEMENTED'}
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True), flush=True)
    previous_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,
                  lambda _signum, _frame: (_ for _ in ()).throw(
                      KeyboardInterrupt()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if getattr(server,'mcp_worker',None):server.mcp_worker.stop()
        if getattr(server,'codex_worker',None):server.codex_worker.stop()
        server.server_close()
        signal.signal(signal.SIGTERM, previous_term)
        print(json.dumps({'state': 'STOPPED', 'mode': 'TEST_ONLY'},
                         sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
