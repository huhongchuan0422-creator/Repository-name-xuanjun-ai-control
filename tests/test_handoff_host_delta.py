"""Isolated fake-host contract tests, never production authentication."""
import copy, hashlib, io, json, os, sqlite3, tempfile, unittest
from types import SimpleNamespace
from task_center_handoff_host import HandoffHost, HostAuthAdapter, FormalHandoffIdentityProvider, REQUIRED_CONTEXT
from task_center_app import build_handler

CONFIG={'schema_version':1,'enabled':True,'bindings':[{'tenant_id':'tenant-1','principal_id':'dispatch-user','project_id':'demo-project',
        'roles':{'role-agent':{'role_version':'v1','principal_id':'agent','provider_id':'fixture-only','model_id':'fixture-model','connection_id':'fixture-connection'}}}]}

class SimulatedHost(HostAuthAdapter):
    def __init__(self):self.enabled=True;self.override={};self.backup={'state':'COMPLETE','missing':[],'cycle_at':990}
    def authenticate_and_authorize(self,session,action,binding):
        if not self.enabled or not session:return None
        return dict({'issuer':'formal-fixture','tenant_id':'tenant-1','principal_id':session,
                     'session_id':'session-'+session,'role_id':'role-'+session,
                     'scope':'handoff:'+action,'expires_at':2000},**self.override)
    def assess_backup(self,binding):return self.backup
    def assess_provider(self,binding):return 'CONNECTED' if binding['provider_ref']=='fixture-only' else None

class HostDelta(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=os.path.join(self.tmp.name,'db')
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row
        self.db.executescript('''CREATE TABLE tasks(task_id TEXT PRIMARY KEY,attempt_id TEXT,authority_state TEXT,authority_valid_until REAL,fence INTEGER,epoch INTEGER,resource_scope_json TEXT,resource_scope_digest TEXT,last_trusted_time REAL);
          CREATE TABLE gateway_task_metadata(task_id TEXT,tenant_id TEXT,project_id TEXT);
          CREATE TABLE writer_operations(task_id TEXT,state TEXT);
          CREATE TABLE resource_claims(task_id TEXT,resource_key TEXT,attempt_id TEXT,fence INTEGER,epoch INTEGER,state TEXT);
          CREATE TABLE model_assignments(tenant_id TEXT,task_id TEXT,attempt_id TEXT,role_id TEXT,role_version TEXT,principal_id TEXT,provider_id TEXT,model_id TEXT,state TEXT);
          CREATE TABLE outbox(outbox_id TEXT PRIMARY KEY,task_id TEXT,attempt_id TEXT,event_id TEXT,payload_json TEXT,next_attempt_at REAL,delivered_at REAL);
          CREATE TABLE events(task_id TEXT,attempt_id TEXT,event_id TEXT,kind TEXT,observed_at REAL,evidence_kind TEXT,evidence_ref TEXT,payload_json TEXT,PRIMARY KEY(task_id,attempt_id,event_id));
          INSERT INTO resource_claims VALUES('task-1','repo','attempt-1',1,1,'VALID');
          INSERT INTO gateway_task_metadata VALUES('task-1','tenant-1','demo-project');
          INSERT INTO model_assignments VALUES('tenant-1','task-1','attempt-1','role-agent','v1','agent','fixture-only','fixture-model','ASSIGNED');''')
        scope=hashlib.sha256(b'["repo"]').hexdigest()
        self.db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',('task-1','attempt-1','VALID',2000,1,1,'["repo"]',scope,900))
        self.db.commit();self.auth=SimulatedHost();self.host=HandoffHost(self.db,'tenant-1','formal-fixture',self.auth,clock=lambda:1000,mcp_config=CONFIG)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def req(self,action='PROPOSE',eid='event-1',cause='NONE'):
        return {'task_id':'task-1','attempt_id':'attempt-1','handoff_id':'handoff-1','handoff_version':1,'event_id':eid,'action':action,'causation':cause,'snapshot_digest':'a'*64,'backup_cycle_id':'cycle-1','backup_manifest_sha256':'b'*64,'checked':sorted(REQUIRED_CONTEXT),'provider_ref':'fixture-only'}
    def test_actual_transaction_chain_and_historical_verification(self):
        self.assertEqual(self.host.record('alice',self.req())['state'],'RECORDED')
        self.assertEqual(self.host.record('alice',self.req())['state'],'ALREADY_RECORDED')
        self.host.record('bob',self.req('RECEIVE','event-2','event-1'))
        self.host.record('carol',self.req('SUPERVISE','event-3','event-2'))
        with self.assertRaises(ValueError):self.host.record('bob',self.req('RECEIVE','other-event','event-1'))
        row=self.db.execute("SELECT payload_json FROM events WHERE event_id='handoff-host:event-2'").fetchone();payload=json.loads(row[0])
        self.assertEqual(payload['principal_id'],'bob')
        self.assertTrue(self.host.verify_recorded('tenant-1','task-1','attempt-1','event-2',payload))
        self.db.execute("UPDATE tasks SET authority_state='REVOKED'");self.db.commit()
        self.assertTrue(self.host.verify_recorded('tenant-1','task-1','attempt-1','event-2',payload))
        with self.assertRaises(ValueError):self.host.record('carol',self.req('SUPERVISE','event-4','event-2'))
        payload['handoff_version']=2
        self.assertFalse(self.host.verify_recorded('tenant-1','task-1','attempt-1','event-2',payload))
        self.assertFalse(self.host.verify_recorded('other','task-1','attempt-1','event-2',payload))
    def test_reject_untrusted_or_mismatched(self):
        with self.assertRaises(ValueError):HandoffHost(self.db,'tenant-1','TEST_ONLY',self.auth)
        with self.assertRaises(ValueError):HandoffHost(self.db,'tenant-1','test-fixture',self.auth)
        with self.assertRaises(ValueError):HandoffHost(self.db,'tenant-1','formal-fixture',HostAuthAdapter())
        for changes in ({'issuer':'evil'},{'tenant_id':'other'},{'expires_at':999},{'scope':'handoff:RECEIVE'}):
            self.auth.override=changes
            with self.assertRaises(ValueError):self.host.record('alice',self.req())
        self.auth.override={};self.auth.enabled=False
        with self.assertRaises(ValueError):self.host.record('alice',self.req())
        self.auth.enabled=True
        wrong=self.req();wrong['attempt_id']='attempt-2'
        with self.assertRaises(ValueError):self.host.record('alice',wrong)
        wrong=self.req();wrong['principal_id']='alice'
        with self.assertRaises(ValueError):self.host.record('alice',wrong)
        self.host.record('alice',self.req())
        wrong=self.req('RECEIVE','event-2','event-1');wrong['handoff_version']=2
        with self.assertRaises(ValueError):self.host.record('bob',wrong)
        wrong=self.req('RECEIVE','event-2','event-1');wrong['backup_manifest_sha256']='c'*64
        with self.assertRaises(ValueError):self.host.record('bob',wrong)
        with self.assertRaises(ValueError):self.host.record('alice',self.req('RECEIVE','event-2','event-1'))
        self.db.execute("INSERT INTO writer_operations VALUES('task-1','UNKNOWN')");self.db.commit()
        with self.assertRaises(ValueError):self.host.record('bob',self.req('RECEIVE','event-2','event-1'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
    def test_incomplete_checklist_unknown_backup_and_revoked_claims(self):
        self.auth.backup=None
        result=self.host.record('alice',self.req());self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1','event-1')['backup_state'],'UNKNOWN')
        self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990}
        unchecked=self.req(eid='event-2');unchecked['checked'].remove('RESTORE')
        result=self.host.record('alice',unchecked);self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertIn('RESTORE',self.host.read_receipt('bob','task-1','attempt-1','event-2')['missing'])
        self.db.execute("UPDATE resource_claims SET state='REVOKED'");self.db.commit()
        with self.assertRaises(ValueError):self.host.record('alice',self.req(eid='event-3'))
        self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind='AUTHENTICATED_HANDOFF_PROPOSE'").fetchone()[0],0)
    def test_incomplete_backup_alert_queue_and_revalidation(self):
        self.auth.backup={'state':'INCOMPLETE','missing':['INSTALL_ENTRY','CREDENTIAL_REFERENCE'],'cycle_at':990}
        result=self.host.record('alice',self.req())
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertEqual(result['alert_delivery'],'UNKNOWN')
        observed=self.host.read_receipt('bob','task-1','attempt-1','event-1')
        self.assertEqual(observed['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertEqual(observed['alert_delivery'],'UNKNOWN')
        self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind='AUTHENTICATED_HANDOFF_PROPOSE'").fetchone()[0],0)
        self.assertIsNone(self.db.execute('SELECT delivered_at FROM outbox').fetchone()[0])
        self.assertEqual(self.host.record('alice',self.req())['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990}
        self.assertEqual(self.host.record('alice',self.req())['state'],'RECORDED')
        self.host.record('bob',self.req('RECEIVE','event-2','event-1'))
        self.host.record('carol',self.req('SUPERVISE','event-3','event-2'))
    def test_stale_or_future_cycle_is_not_complete(self):
        for i,stamp in enumerate((699,1001)):
            self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':stamp}
            event=self.req(eid='cycle-event-'+str(i))
            self.assertEqual(self.host.record('alice',event)['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
            self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',event['event_id'])['backup_state'],'UNKNOWN')
    def test_unconnected_provider_never_produces_receipt(self):
        value=self.req();value['provider_ref']='dots'
        self.assertEqual(self.host.record('alice',value)['state'],'NOT_CONNECTED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
        self.db.execute("UPDATE model_assignments SET role_version='wrong'");self.db.commit()
        self.assertEqual(self.host.record('alice',self.req())['state'],'NOT_CONNECTED')
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_real_supervisor_schema_transaction_and_outbox(self):
        from task_supervisor import Supervisor
        from reusable_task_gateway import GatewayKernel, TestTenantAuthority
        from reusable_scheduler_cli import demo_graph
        with tempfile.TemporaryDirectory() as root:
            s=Supervisor(os.path.join(root,'supervisor.sqlite'),clock=lambda:1000)
            try:
                authority=TestTenantAuthority(b'0'*32);gateway=GatewayKernel(s,authority)
                gateway.register_graph(authority.issue('tenant-1','seed'),demo_graph('tenant-1'))
                caller={'caller_id':'caller','run_id':'run','session_id':'session','gateway_id':'gateway'}
                s.claim_writer('demo-b','attempt-1','owner','entry',caller,'lease','provider',['fake:demo-b'],2000)
                s.db.execute('CREATE TABLE model_assignments(tenant_id TEXT,task_id TEXT,attempt_id TEXT,role_id TEXT,role_version TEXT,principal_id TEXT,provider_id TEXT,model_id TEXT,state TEXT)')
                s.db.execute("INSERT INTO model_assignments VALUES('tenant-1','demo-b','attempt-1','role-agent','v1','agent','fixture-only','fixture-model','ASSIGNED')");s.db.commit()
                host=HandoffHost(s.db,'tenant-1','formal-fixture',self.auth,clock=lambda:1000,mcp_config=CONFIG)
                req=self.req();req['task_id']='demo-b'
                self.auth.backup={'state':'INCOMPLETE','missing':['RESTORE'],'cycle_at':990}
                self.assertEqual(host.record('alice',req)['alert_delivery'],'UNKNOWN')
                self.assertIsNone(s.db.execute('SELECT delivered_at FROM outbox WHERE event_id=?',('handoff-missing:event-1',)).fetchone()[0])
                self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990}
                self.assertEqual(host.record('alice',req)['state'],'RECORDED')
                self.assertEqual(host.read_receipt('bob','demo-b','attempt-1','event-1')['state'],'HISTORICAL_RECORDED')
            finally:s.close()
    def test_expired_writer_and_wrong_resource_scope_are_denied(self):
        self.db.execute("UPDATE tasks SET authority_valid_until=999");self.db.commit()
        with self.assertRaises(ValueError):self.host.record('alice',self.req())
        self.db.execute("UPDATE tasks SET authority_valid_until=2000,resource_scope_digest='wrong'");self.db.commit()
        with self.assertRaises(ValueError):self.host.record('alice',self.req())
        self.assertEqual(self.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_handler_requires_provider_session_csrf_and_hides_claims(self):
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(self,token):return 'alice' if token=='good' else None
            def verify_csrf(self,session,token):return token=='good-csrf'
        class SimulatedFormalProvider(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session=='alice'
        handler=build_handler(self.path,b'0'*32,'tenant-1','viewer',identity_provider=SimulatedFormalProvider(),session_store=Sessions(),handoff_host=self.host)
        def post(cookie,csrf,body):
            h=handler.__new__(handler);h.command='POST';h.path='/api/admin/handoff-event';h.server=SimpleNamespace(server_port=8765)
            raw=json.dumps(body).encode();h.headers={'Host':'localhost:8765','Cookie':'session='+cookie,'X-CSRF-Token':csrf,'Content-Length':str(len(raw))}
            h.rfile=io.BytesIO(raw);out=[];h._send=lambda status,data,kind,extra_headers=None:out.append((status,data));h.do_POST();return out[0]
        self.assertEqual(post('bad','good-csrf',self.req())[0],401)
        self.assertEqual(post('good','bad',self.req())[0],403)
        self.auth.backup={'state':'INCOMPLETE','missing':['RESTORE'],'cycle_at':990}
        self.assertIn(b'HANDOFF_INCOMPLETE_ALERT_QUEUED',post('good','good-csrf',self.req(eid='alert-1'))[1])
        h=handler.__new__(handler);h.command='GET';h.path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id=alert-1';h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765','Cookie':'session=good'}
        out=[];h._send=lambda status,data,kind,extra_headers=None:out.append((status,data));h.do_GET()
        self.assertEqual(out[0][0],200);self.assertIn(b'RESTORE',out[0][1]);self.assertIn(b'UNKNOWN',out[0][1])
        self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':990}
        status,body=post('good','good-csrf',self.req());self.assertEqual(status,200);self.assertNotIn(b'alice',body)
        h=handler.__new__(handler);h.command='GET';h.path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id=event-1';h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765','Cookie':'session=good'}
        out=[];h._send=lambda status,data,kind,extra_headers=None:out.append((status,data));h.do_GET()
        self.assertEqual(out[0][0],200);self.assertNotIn(b'alice',out[0][1]);self.assertIn(b'HISTORICAL_RECORDED',out[0][1])
        self.auth.enabled=False;out[:]=[];h.do_GET();self.assertEqual(out[0][0],404)
        self.auth.enabled=True
        value=self.req(eid='event-other');value['principal_id']='other'
        status,body=post('good','good-csrf',value);self.assertEqual(status,409);self.assertNotIn(b'other',body)
        from task_center_session_auth import FileTestIdentityProvider
        test_identity=FileTestIdentityProvider.__new__(FileTestIdentityProvider)
        blocked=build_handler(self.path,b'0'*32,'tenant-1','viewer',identity_provider=test_identity,session_store=Sessions(),handoff_host=self.host)
        h=blocked.__new__(blocked);h.command='POST';h.path='/api/admin/handoff-event';h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765'}
        out=[];h._send=lambda status,data,kind,extra_headers=None:out.append(status);h.do_POST();self.assertEqual(out,[503])
        blocked=build_handler(self.path,b'0'*32,'tenant-1','viewer',identity_provider=object(),session_store=Sessions(),handoff_host=self.host)
        h=blocked.__new__(blocked);h.command='POST';h.path='/api/admin/handoff-event';h.server=SimpleNamespace(server_port=8765);h.headers={'Host':'localhost:8765'}
        out=[];h._send=lambda status,data,kind,extra_headers=None:out.append(status);h.do_POST();self.assertEqual(out,[503])

if __name__=='__main__':unittest.main()
