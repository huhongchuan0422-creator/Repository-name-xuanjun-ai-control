"""Original HTTP SessionStore principal-to-host claim binding; fixture identity only."""
import http.client, json, sqlite3, threading
from test_handoff_ledger_host_bridge import MainChain
from task_center_handoff_host import FormalHandoffIdentityProvider, REQUIRED_CONTEXT
from task_center_session_auth import SessionStore
from task_center_app import make_server

class SessionBinding(MainChain):
    def test_original_http_session_claim_binding_and_revocation(self):
        class FixtureFormal(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('tenant_id')=='tenant-1'
        def connect():
            db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
        sessions=SessionStore(connect,'tenant-1',ttl_seconds=3600,clock=lambda:self.now)
        token,csrf,_=sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        original=self.auth.authenticate_and_authorize
        self.auth.authenticate_and_authorize=lambda session,action,binding:original(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        server=make_server(self.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,identity_provider=FixtureFormal(),session_store=sessions,outbound_enabled=False,handoff_host=self.host,ledger_bridge=self.bridge)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        def call(method,path,value=None):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                headers={'Host':'localhost:%s'%server.server_port,'Cookie':sessions.COOKIE+'='+token,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
                c.request(method,path,json.dumps(value) if value is not None else None,headers)
                r=c.getresponse();return r.status,json.loads(r.read().decode())
            finally:c.close()
        try:
            request={'task_id':'task-1','attempt_id':'attempt-1','handoff_version':1}
            self.auth.override={'principal_id':'bob','expires_at':self.expiry}
            self.assertEqual(call('POST','/api/admin/handoff-reference',request)[0],409)
            self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind='HANDOFF_REFERENCE_ISSUED'").fetchone()[0],0)
            self.auth.override={'expires_at':self.expiry+1}
            self.assertEqual(call('POST','/api/admin/handoff-reference',request)[0],409)
            self.auth.override={'expires_at':self.expiry}
            status,ref=call('POST','/api/admin/handoff-reference',request);self.assertEqual(status,200)
            event=dict(ref,task_id='task-1',attempt_id='attempt-1',action='PROPOSE',causation='NONE',snapshot_digest='a'*64,backup_manifest_sha256='b'*64,checked=sorted(REQUIRED_CONTEXT),provider_ref='fixture-only')
            self.auth.override={'principal_id':'bob','expires_at':self.expiry}
            self.assertEqual(call('POST','/api/admin/handoff-event',event)[0],409)
            self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind='AUTHENTICATED_HANDOFF_PROPOSE'").fetchone()[0],0)
            self.auth.override={'expires_at':self.expiry}
            self.assertEqual(call('POST','/api/admin/handoff-event',event)[1]['state'],'RECORDED')
            path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id='+ref['event_id']
            self.assertEqual(call('GET',path)[0],200)
            self.auth.override={'principal_id':'bob','expires_at':self.expiry}
            self.assertEqual(call('GET',path)[0],404)
            self.auth.override={'expires_at':self.expiry}
            sessions.revoke(token)
            self.assertEqual(call('GET',path)[0],401)
        finally:server.shutdown();thread.join(3);server.server_close()
