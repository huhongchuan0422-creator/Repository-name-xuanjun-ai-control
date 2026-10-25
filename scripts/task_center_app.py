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
import stat
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(__file__))
from reusable_task_gateway import (GatewayKernel, TestOnlyExecutor,
                                   TestTenantAuthority, canonical)
from model_orchestration import ModelControl, ModelScheduler, load_master_key
from task_supervisor import Supervisor
from task_writer_fence import Fence
from execution_policy_gateway import ExecutionPolicyGateway


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
ASSET_ROOT = os.path.join(ROOT, 'demos', 'task-center-digital-twin')
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
    '/admin.html': ('admin.html', 'text/html; charset=utf-8'),
    '/admin.js': ('admin.js', 'application/javascript; charset=utf-8'),
}

PROJECTION_TABLES = frozenset((
    'tasks', 'events', 'gateway_task_metadata', 'gateway_dependencies',
    'gateway_checkpoints'))
MODEL_TABLES = frozenset((
    'model_providers', 'model_catalog', 'role_templates', 'model_requests',
    'model_usage_events', 'model_evaluations', 'delivery_candidates',
    'candidate_reviews', 'module_settings', 'task_work_specs',
    'model_call_attempts'))


def _read_owned_secret_file(path, label):
    info=os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
            info.st_uid!=os.getuid()):
        raise ValueError('OWNED_REGULAR_%s_FILE_REQUIRED'%label)
    if info.st_mode & 0o077:
        raise ValueError('%s_FILE_MODE_0600_REQUIRED'%label)
    with open(path) as stream:return stream.read()


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


def build_handler(db_path, authority_key, tenant_id, principal_id,
                  model_master_key=None, admin_token=None, actor_tokens=None):
    actor_tokens = dict(actor_tokens or {})
    class TaskCenterHandler(BaseHTTPRequestHandler):
        server_version = 'XuanjunTaskCenter/1.0-TEST_ONLY'

        def log_message(self, fmt, *args):
            sys.stderr.write('task-center-app: ' + fmt % args + '\n')

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; object-src 'none'; "
                             "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path == '/api/projection':
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
            path = self.path.split('?',1)[0]
            if path != '/api/admin/model-control':
                self._send(405,b'read only\n','text/plain; charset=utf-8');return
            if not self._admin_allowed():
                self._send(403,_json_bytes({'error':'ADMIN_REQUIRED'}),
                           'application/json; charset=utf-8');return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<2 or length>65536:raise ValueError('BODY_LIMIT')
                value=json.loads(self.rfile.read(length).decode('utf-8'))
                action=value.pop('action')
                supervisor, control=self._model_control()
                try:
                    role_actions={'SUBMIT_CANDIDATE','REVIEW_CANDIDATE',
                                  'ACCEPT_CANDIDATE','REVIEW_SCOPE_CHANGE'}
                    actor=None
                    if action in role_actions:
                        actor=self._actor_principal()
                        if actor is None:
                            raise ValueError('AUTHENTICATED_ACTOR_REQUIRED')
                        control=ModelControl(control.gateway,
                          control.gateway.tenants.issue(tenant_id,actor),
                          model_master_key)
                    if action=='UPSERT_PROVIDER':
                        result=control.upsert_provider(value['config'],value.get('secret'))
                    elif action=='DISABLE_PROVIDER':
                        result=control.disable_provider(value['provider_id'])
                    elif action=='UPSERT_MODEL':result=control.upsert_model(value['config'])
                    elif action=='CREATE_ROLE':result=control.create_role(value['config'])
                    elif action=='BIND_SKILL':result=control.bind_skill(value['role_id'],value['role_version'],value['skill_id'],value['skill_version'],value['review_sha256'],value['status'])
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
                        result=control.gateway.register_graph(control.context,graph)
                        control.record_task_spec(fields['task_id'],fields['goal'],
                          fields['deliverables'],fields['acceptance'])
                        policy=ExecutionPolicyGateway(control.gateway,
                          control.context)
                        policy.record_unit({'task_id':fields['task_id'],
                          'delivery_stage':fields['delivery_stage'],
                          'feature_unit':fields['feature_unit'],
                          'goal':fields['goal'],'scope':fields['scope'],
                          'acceptance':fields['acceptance'],
                          'dependencies':fields['dependencies'] or ['NONE'],
                          'asset_version':fields['asset_version'],
                          'responsible_party':fields['owner']})
                        result['graph_id']=graph['graph_id']
                    elif action=='START_TEST_ONLY_TASK':
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
                        result=control.assign(value['task_id'],value['role_id'],
                          value['role_version'],value['principal_id'],
                          bool(value.get('allow_paid',False)))
                    elif action=='QUEUE_REQUEST':
                        result=control.queue_request(value['task_id'],
                          value['role_id'],value['messages'],
                          value['idempotency_key'])
                    elif action=='CANCEL_REQUEST':
                        result=control.request_cancel(value['request_id'])
                    elif action=='REGISTER_BENCHMARK':
                        result=control.register_benchmark_suite(
                          value['suite_version'],value['cases'])
                    elif action=='RUN_BENCHMARK':
                        result=control.run_benchmark(value['provider_id'],
                          value['model_id'],value['suite_version'])
                    elif action=='RUN_SCHEDULER_ONCE':
                        result=ModelScheduler(control).run_once()
                    elif action=='SUBMIT_CANDIDATE':
                        if value['submitted_by']!=actor:
                            raise ValueError('AUTHENTICATED_EXECUTOR_REQUIRED')
                        result=control.submit_candidate(value['task_id'],
                          value['artifact_sha256'],value['checklist_sha256'],
                          value['submitted_by'])
                    elif action=='REVIEW_CANDIDATE':
                        if value['reviewer']!=actor:
                            raise ValueError('AUTHENTICATED_REVIEWER_REQUIRED')
                        result=control.review_candidate(value['candidate_id'],
                          value['reviewer'],value['findings'],
                          bool(value['passed']))
                    elif action=='ACCEPT_CANDIDATE':
                        if value['acceptor']!=actor:
                            raise ValueError('AUTHENTICATED_ACCEPTOR_REQUIRED')
                        result=control.accept_candidate(value['candidate_id'],
                          value['acceptor'])
                        candidate=control.db.execute('''SELECT * FROM
                          delivery_candidates WHERE tenant_id=? AND
                          candidate_id=?''',(control.tenant_id,
                          value['candidate_id'])).fetchone()
                        fence=Fence(supervisor,db_path+'.test-only-locks')
                        try:
                            task=supervisor._task(candidate['task_id'])
                            terminal=TestOnlyExecutor(control.gateway,fence,
                              control.context).complete_success(
                              candidate['task_id'],candidate['attempt_id'],
                              candidate['artifact_sha256'],
                              json.loads(task['completion_json']))
                        finally:fence.close()
                        result['canonical_task_state']=terminal['state']
                    elif action=='SET_MODULE':
                        result=control.set_module(value['module_id'],
                          value['version'],bool(value['enabled']))
                    elif action=='RECORD_PREFLIGHT':
                        result=ExecutionPolicyGateway(control.gateway,
                          control.context).record_preflight(value['task_id'],
                          value['checked'],value['outcome'],value.get('reused_asset'),
                          value.get('reused_version'),bool(value['need_new']),
                          value['reason'],value['evidence_ref'])
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
            supplied=self.headers.get('X-Test-Admin-Token')
            return (admin_token is not None and supplied is not None and
                    __import__('hmac').compare_digest(admin_token,supplied))

        def _actor_principal(self):
            supplied=self.headers.get('X-Test-Actor-Token')
            if supplied is None:return None
            for token,actor in actor_tokens.items():
                if __import__('hmac').compare_digest(token,supplied):
                    return actor
            return None

        def _model_control(self):
            if model_master_key is None:raise ValueError('MODEL_ADMIN_DISABLED')
            supervisor=Supervisor(db_path)
            authority=TestTenantAuthority(authority_key)
            gateway=GatewayKernel(supervisor,authority)
            context=authority.issue(tenant_id,'admin:'+principal_id)
            return supervisor,ModelControl(gateway,context,model_master_key)

    return TaskCenterHandler


def make_server(db_path, authority_key, tenant_id, principal_id,
                host='127.0.0.1', port=8765, model_master_key=None,
                admin_token=None, actor_tokens=None):
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
        finally:supervisor.close()
    handler = build_handler(os.path.realpath(db_path), authority_key,
                            tenant_id, principal_id, model_master_key,
                            admin_token, actor_tokens)
    return HTTPServer((host, port), handler)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--test-authority-key', required=True)
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--principal', default='local-ui-viewer')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--model-master-key-file')
    parser.add_argument('--admin-token-file')
    parser.add_argument('--actor-token-file')
    args = parser.parse_args(argv)
    key = args.test_authority_key.encode('utf-8')
    model_key = (load_master_key(args.model_master_key_file)
                 if args.model_master_key_file else None)
    admin_token = None
    if args.admin_token_file:
        admin_token=_read_owned_secret_file(args.admin_token_file,
          'ADMIN_TOKEN').strip()
        if len(admin_token) < 16:raise ValueError('VALID_ADMIN_TOKEN_REQUIRED')
    if (model_key is None) != (admin_token is None):
        raise ValueError('MODEL_KEY_AND_ADMIN_TOKEN_REQUIRED_TOGETHER')
    actor_tokens={}
    if args.actor_token_file:
        configured=json.loads(_read_owned_secret_file(args.actor_token_file,
          'ACTOR_TOKEN'))
        if (not isinstance(configured,dict) or not configured or
                any(not isinstance(p,str) or not p or not isinstance(t,str)
                    or len(t)<16 for p,t in configured.items())):
            raise ValueError('VALID_ACTOR_TOKEN_MAP_REQUIRED')
        actor_tokens={token:principal for principal,token in configured.items()}
    server = make_server(args.db, key, args.tenant, args.principal,
                         args.host, args.port, model_key, admin_token,
                         actor_tokens)
    receipt = {'state': 'STARTED', 'mode': 'TEST_ONLY',
               'url': 'http://%s:%d/' % server.server_address,
               'db': os.path.realpath(args.db), 'tenant_id': args.tenant,
               'production_mutation_api': 'DISABLED',
               'test_only_admin_mutation_api': ('ENABLED' if model_key else
                                                'DISABLED'),
               'model_admin_api': ('TEST_ONLY_ENABLED' if model_key else
                                   'DISABLED'),
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
        server.server_close()
        signal.signal(signal.SIGTERM, previous_term)
        print(json.dumps({'state': 'STOPPED', 'mode': 'TEST_ONLY'},
                         sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
