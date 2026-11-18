"""Original app.main -> make_server -> actual HTTP; fixtures only."""
import contextlib, http.client, io, json, os, sqlite3, tempfile, threading, unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import task_center_app as app
from task_center_session_auth import SessionStore
from task_center_handoff_host import HostAuthAdapter, HandoffHost, FormalHandoffIdentityProvider
from task_center_handoff_ledger import HandoffLedgerBridge
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from reusable_scheduler_cli import demo_graph

class FixtureIdentity(FormalHandoffIdentityProvider):
    def is_formal_session(self,session):return session.get('tenant_id')=='tenant-fixture'

class FixtureAdapter(HostAuthAdapter):
    def authenticate_and_authorize(self,session,action,binding):
        if session.get('principal_id')!='fixture-actor':return None
        return dict(issuer='fixture-host',tenant_id='tenant-fixture',principal_id=session['principal_id'],session_id='fixture-session',role_id='fixture-role',expires_at=session['expires_at'],scope='handoff:'+action)

class MainHostEntry(unittest.TestCase):
    def test_main_injected_original_http_reference_and_unverified_backup(self):
        with tempfile.TemporaryDirectory() as root:
            dbpath=os.path.join(root,'ledger.db');s=Supervisor(dbpath)
            try:
                key=b'0123456789abcdef0123456789abcdef';authority=TestTenantAuthority(key)
                GatewayKernel(s,authority).register_graph(authority.issue('tenant-fixture','seed'),demo_graph('tenant-fixture'))
                s.claim_writer('demo-b','attempt-1','owner','entry',{'caller_id':'fixture','run_id':'run','session_id':'session','gateway_id':'gateway'},'lease','provider',['fake:demo-b'],s.clock()+600)
                def connect():
                    db=sqlite3.connect(dbpath);db.row_factory=sqlite3.Row;return db
                sessions=SessionStore(connect,'tenant-fixture',ttl_seconds=600)
                token,csrf,_=sessions.create({'tenant_id':'tenant-fixture','principal_id':'fixture-actor','roles':['TASK_CENTER_ADMIN']})
                host=HandoffHost(s.db,'tenant-fixture','fixture-host',FixtureAdapter())
                bridge=HandoffLedgerBridge(host,os.path.join(root,'observations'),'tenant-ledger','writer')
                captured=[];original=app.make_server
                def wrapping(*args,**kwargs):
                    self.assertIs(kwargs['handoff_host'],host);self.assertIs(kwargs['ledger_bridge'],bridge)
                    server=original(*args,**kwargs)
                    def serve_once():
                        t=threading.Thread(target=server.handle_request);t.start()
                        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                        try:
                            headers={'Host':'localhost:%s'%server.server_port,'Cookie':sessions.COOKIE+'='+token,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
                            c.request('POST','/api/admin/handoff-reference',json.dumps({'task_id':'demo-b','attempt_id':'attempt-1','handoff_version':1}),headers)
                            r=c.getresponse();captured.append((r.status,json.loads(r.read().decode())))
                        finally:c.close();t.join(3)
                    server.serve_forever=serve_once
                    return server
                argv=['--db',dbpath,'--test-authority-key',key.decode(),'--tenant','tenant-fixture','--port','0','--model-master-key-file','fixture-path']
                with patch.object(app,'load_master_key',return_value=Fernet.generate_key()),patch.object(app,'make_server',side_effect=wrapping),contextlib.redirect_stdout(io.StringIO()):
                    app.main(argv,identity_provider=FixtureIdentity(),session_store=sessions,handoff_host=host,ledger_bridge=bridge)
                self.assertEqual(captured[0][0],200);self.assertEqual(captured[0][1]['handoff_version'],1)
                self.assertIsNone(host.adapter.assess_backup({}))
                self.assertFalse(s.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
            finally:s.close()
    def test_injected_identity_session_must_be_paired(self):
        argv=['--db','fixture','--test-authority-key','0'*32,'--tenant','tenant-fixture']
        with self.assertRaisesRegex(ValueError,'HOST_IDENTITY_AND_SESSION_REQUIRED'):
            app.main(argv,identity_provider=FixtureIdentity())
    def test_injected_identity_cannot_mix_cli_fixture_identity(self):
        argv=['--db','fixture','--test-authority-key','0'*32,'--tenant','tenant-fixture','--test-identity-file','not-read']
        with self.assertRaisesRegex(ValueError,'SINGLE_AUTH_MODE_REQUIRED'):
            app.main(argv,identity_provider=FixtureIdentity(),session_store=object())
