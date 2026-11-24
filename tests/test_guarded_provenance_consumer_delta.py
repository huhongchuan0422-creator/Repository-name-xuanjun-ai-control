"""Fixtures only; no production source or cross-runtime bridge."""
import copy
import os
import sqlite3
import tempfile
import unittest
from task_center_session_auth import SessionStore
from task_center_provenance_consumer import GuardedProvenanceConsumer as Consumer

class Source:
    def __init__(self):
        self.live=True;self.at_guard=None
        self.binding=dict(source_ref='fixture',source_version='v1',subject='subject',
            incarnation='parent-run1',tenant_id='tenant',principal_id='writer',expires_at=150)
    def verify_login(self,u,p):return copy.deepcopy(self.binding)
    def current_provenance(self,b,s):
        if not self.live:raise ValueError('fixture revoked')
        return copy.deepcopy(self.binding)
    def assert_effect_current(self):
        if self.at_guard:self.at_guard()
        if not self.live:raise ValueError('fixture guard revoked')

class GuardedConsumer(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=os.path.join(self.tmp.name,'db')
        def connect():
            c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;return c
        self.connect=connect;self.sessions=SessionStore(connect,'tenant',clock=lambda:100)
        self.source=Source()
        self.mapper=lambda b:dict(tenant_id=b['tenant_id'],principal_id=b['principal_id'],roles=['developer'])
        self.consumer=Consumer(self.sessions,self.source,self.mapper,clock=lambda:100)
    def tearDown(self):self.tmp.cleanup()
    def count(self):
        c=self.connect()
        try:return c.execute('SELECT count(*) FROM task_center_sessions').fetchone()[0]
        finally:c.close()
    def login(self):
        identity,result=self.consumer.guarded_login(self.sessions,'owner-label','not logged')
        return result[0],self.sessions.get(result[0])
    def test_store_live_source_logout_and_restart(self):
        token,s=self.login();self.assertTrue(self.consumer.is_formal_session(s))
        self.assertEqual(s['roles'],['developer'])
        restarted=Consumer(self.sessions,self.source,self.mapper,clock=lambda:100)
        self.assertFalse(restarted.is_formal_session(s))
        self.sessions.revoke(token);self.assertFalse(self.consumer.is_formal_session(s))
    def test_final_guard_revocation_rolls_back_insert(self):
        self.source.at_guard=lambda:setattr(self.source,'live',False)
        with self.assertRaisesRegex(ValueError,'^FORMAL_PROVENANCE_UNAVAILABLE$'):self.login()
        self.assertEqual(self.count(),0)
    def test_current_replacement_expiry_revocation(self):
        _,s=self.login();original=copy.deepcopy(self.source.binding)
        for field,value in [('incarnation','other-run'),('subject','other'),('tenant_id','other'),
                            ('source_version','v2'),('expires_at',99)]:
            self.source.binding=dict(original,**{field:value})
            self.assertFalse(self.consumer.is_formal_session(s),field)
        self.source.binding=original;self.source.live=False
        self.assertFalse(self.consumer.is_formal_session(s))
    def test_row_and_owner_labels_not_provenance(self):
        token,_,_=self.sessions.create(dict(tenant_id='tenant',principal_id='admin:owner',roles=['admin']))
        self.assertFalse(self.consumer.is_formal_session(self.sessions.get(token)))
        self.assertIsNone(self.consumer.verify('Owner','password'))
        self.consumer.mapper=lambda b:dict(tenant_id='tenant',principal_id='admin:owner',roles=['admin'])
        with self.assertRaisesRegex(ValueError,Consumer.ERROR):self.login()
        self.assertEqual(self.count(),1)
    def test_missing_source_or_mapper_fixed_denial(self):
        for source,mapper in [({},self.mapper),(self.source,None)]:
            with self.assertRaisesRegex(ValueError,Consumer.ERROR):Consumer(self.sessions,source,mapper)
    def test_async_or_bool_guard_not_sync_capability(self):
        async def async_guard():return None
        for guard in (async_guard,lambda:True,lambda:False):
            self.source.assert_effect_current=guard
            with self.assertRaisesRegex(ValueError,Consumer.ERROR):self.login()
            self.assertEqual(self.count(),0)
    def test_original_http_login_uses_consumer_and_rejects_body_authority(self):
        import http.client,json,threading
        from task_center_app import make_server
        from task_supervisor import Supervisor
        from reusable_task_gateway import GatewayKernel,TestTenantAuthority
        from reusable_scheduler_cli import demo_graph
        key=b'0123456789abcdef0123456789abcdef'
        os.unlink(self.path)
        supervisor=Supervisor(self.path);authority=TestTenantAuthority(key)
        GatewayKernel(supervisor,authority).register_graph(
            authority.issue('tenant','seed'),demo_graph('tenant'))
        supervisor.close()
        self.sessions.__init__(self.connect,'tenant',clock=lambda:100)
        server=make_server(self.path,key,'tenant','viewer',port=0,
            identity_provider=self.consumer,session_store=self.sessions,outbound_enabled=False)
        def request(body):
            thread=threading.Thread(target=server.handle_request);thread.start()
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                connection.request('POST','/api/session/login',json.dumps(body),
                    {'Host':'localhost:%d'%server.server_port,'Content-Type':'application/json'})
                response=connection.getresponse();return response.status,json.loads(response.read())
            finally:connection.close();thread.join(5)
        try:
            for extra in ({'roles':['admin']},{'sessionKey':'owner'},{'admin':True}):
                status,_=request(dict(username='Owner',password='fixture',**extra))
                self.assertEqual(status,401)
            self.assertEqual(self.count(),0)
            status,result=request(dict(username='Owner',password='fixture'))
            self.assertEqual(status,200);self.assertEqual(result['principal_id'],'writer')
            self.assertEqual(result['roles'],['developer'])
            self.source.at_guard=lambda:setattr(self.source,'live',False)
            status,result=request(dict(username='Owner',password='fixture'))
            self.assertEqual(status,401);self.assertEqual(result['detail'],Consumer.ERROR)
            self.assertEqual(self.count(),1)
        finally:server.server_close()

    def test_host_backend_profile_denial(self):
        from task_center_handoff_backend import CanonicalHandoffBackend
        from task_center_handoff_runtime import HostIdentityProvider
        db=self.connect()
        try:
            db.execute('CREATE TABLE authority_runtime_profile(singleton INTEGER,profile TEXT)')
            db.execute("INSERT INTO authority_runtime_profile VALUES(1,'TEST_ONLY')");db.commit()
            backend=CanonicalHandoffBackend(self.sessions,self.consumer,'issuer',db,clock=lambda:100)
            host=HostIdentityProvider('tenant',backend,clock=lambda:100)
            with self.assertRaisesRegex(ValueError,Consumer.ERROR):host.guarded_login(self.sessions,'u','p')
            self.assertEqual(self.count(),0)
            # Isolated profile fixture only, never a live promotion.
            db.execute("UPDATE authority_runtime_profile SET profile='FORMAL'");db.commit()
            identity,result=host.guarded_login(self.sessions,'u','p')
            session=self.sessions.get(result[0]);self.assertTrue(host.is_formal_session(session))
            self.assertIsNone(backend.authorize(host.current(session),'RECEIVE',
                dict(task_id='task',attempt_id='attempt',handoff_version=1)))
        finally:db.close()

if __name__=='__main__':unittest.main()
