"""Concrete canonical ACL backend; only login provenance/key are synthetic."""
import contextlib,http.client,io,json,sqlite3,threading,time,unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from development_identity_adapter import TrustedRegistrationVerifier
from execution_policy_gateway import ExecutionPolicyGateway
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from task_center_handoff_host import FormalHandoffIdentityProvider,HandoffHost
from task_center_handoff_backend import CanonicalHandoffBackend
from task_center_handoff_runtime import HostIdentityProvider,HostActionAdapter
import task_center_handoff_runtime as runtime
import task_center_app as app
import test_handoff_backup_script_main_delta as fixture

class Provenance(FormalHandoffIdentityProvider):
    """Explicit isolated test provenance, not a live identity or grant issuer."""
    active=True
    def verify(self,*args):return None
    def is_formal_session(self,session):return self.active and session.get('principal_id')=='alice'

class CanonicalBackend(unittest.TestCase):
    write_config=fixture.ScriptMainBackup.write_config
    def setUp(self):
        original=fixture.Supervisor
        verifier=TrustedRegistrationVerifier(Ed25519PrivateKey.generate().public_key())
        with patch.object(fixture,'Supervisor',side_effect=lambda path:original(path,development_identity_verifier=verifier)):
            fixture.ScriptMainBackup.setUp(self)
        g=GatewayKernel(self.s,TestTenantAuthority(b'0123456789abcdef0123456789abcdef'))
        self.policy=ExecutionPolicyGateway(g,g.tenants.issue('tenant-1','admin:fixture'))
        self.s.db.execute('INSERT INTO role_templates VALUES(?,?,?,?,?,?,?,?)',('tenant-1','role-alice','v1','ACCEPTOR',json.dumps(['code']),0,1,None))
        self.s.db.execute('INSERT INTO model_assignments VALUES(?,?,?,?,?,?,?,?,?,?,?)',('tenant-1','demo-b','attempt-1','role-alice','v1','alice','identity-fixture','fixture-model','ASSIGNED','FIXTURE',time.time()));self.s.db.commit()
        self.provider=Provenance();self.backend=CanonicalHandoffBackend(self.sessions,self.provider,'formal-fixture',self.s.db)
        for action in ('ISSUE','PROPOSE','READ'):
            self.policy.grant_approval_role('demo-b','alice','handoff:'+action,time.time()+300)
        self.session=self.sessions.get(self.token);self.current=self.backend.current_session(self.session)
        self.binding=dict(task_id='demo-b',attempt_id='attempt-1',handoff_version=1)
    def test_exact_existing_session_role_and_explicit_action_grant(self):
        self.assertEqual(self.current['session_id'],self.session['session_hash'])
        result=self.backend.authorize(self.current,'READ',self.binding)
        self.assertEqual(result['claims']['role_id'],'role-alice')
        self.assertEqual(result['binding'],self.binding)
        self.assertIsNone(self.backend.authorize(self.current,'VERIFIED',self.binding))
        self.assertIsNone(self.backend.authorize(self.current,'READ',dict(self.binding,attempt_id='other')))
        self.assertIsNone(self.backend.current_session(dict(self.session,tenant_id='other')))
        self.assertIsNone(self.backend.authorize(dict(self.current,session_id='other'),'READ',self.binding))
        self.s.db.execute("UPDATE formal_approval_roles SET valid_until=0 WHERE approval_kind='handoff:READ'");self.s.db.commit()
        self.assertIsNone(self.backend.authorize(self.current,'READ',self.binding))
    def test_grant_role_session_and_provenance_revocations_are_live(self):
        self.s.db.execute("DELETE FROM formal_approval_roles WHERE approval_kind='handoff:READ'");self.s.db.commit()
        self.assertIsNone(self.backend.authorize(self.current,'READ',self.binding))
        self.assertIsNotNone(self.backend.authorize(self.current,'PROPOSE',self.binding))
        self.s.db.execute("UPDATE model_assignments SET state='REVOKED' WHERE principal_id='alice'");self.s.db.commit()
        self.assertIsNone(self.backend.authorize(self.current,'PROPOSE',self.binding))
        self.provider.active=False;self.assertIsNone(self.backend.current_session(self.session));self.provider.active=True
        self.sessions.revoke(self.token)
        self.assertIsNone(self.backend.current_session(self.session));self.assertIsNone(self.backend.authorize(self.current,'PROPOSE',self.binding))
    def test_test_only_profile_never_promoted_and_backend_does_not_write(self):
        count=self.s.db.execute('SELECT count(*) FROM formal_approval_roles').fetchone()[0]
        for _ in range(2):self.backend.current_session(self.session);self.backend.authorize(self.current,'READ',self.binding)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM formal_approval_roles').fetchone()[0],count)
        self.s.db.execute("UPDATE authority_runtime_profile SET profile='TEST_ONLY'");self.s.db.commit()
        self.assertIsNone(self.backend.current_session(self.session));self.assertIsNone(self.backend.authorize(self.current,'READ',self.binding))
        self.assertEqual(self.s.db.execute('SELECT profile FROM authority_runtime_profile').fetchone()[0],'TEST_ONLY')
    def test_login_reuses_existing_verifier_only_on_formal_ledger(self):
        identity=dict(tenant_id='tenant-1',principal_id='alice',roles=['TASK_CENTER_ADMIN'])
        with patch.object(self.provider,'verify',return_value=identity) as verify:
            self.assertEqual(self.backend.verify('synthetic-user','synthetic-test-only'),identity)
            self.assertEqual(verify.call_count,1)
            self.s.db.execute("UPDATE authority_runtime_profile SET profile='TEST_ONLY'");self.s.db.commit()
            self.assertIsNone(self.backend.verify('synthetic-user','synthetic-test-only'))
            self.assertEqual(verify.call_count,1)

    def test_wrong_database_and_nonfinite_clock_do_not_authorize(self):
        factory=self.sessions.connection_factory
        self.sessions.connection_factory=lambda:sqlite3.connect(str(self.root/'other.sqlite'))
        try:
            with self.assertRaisesRegex(ValueError,'CANONICAL_SESSION_DATABASE_MISMATCH'):self.backend._read()
        finally:self.sessions.connection_factory=factory
        self.backend.clock=lambda:float('nan')
        self.assertIsNone(self.backend.current_session(self.session))
        self.assertIsNone(self.backend.authorize(self.current,'READ',self.binding))

    def test_original_runtime_main_http_uses_concrete_backend_not_authority_stub(self):
        identity=HostIdentityProvider('tenant-1',self.backend)
        host=HandoffHost(self.s.db,'tenant-1','formal-fixture',HostActionAdapter(identity,'formal-fixture',self.auth),mcp_config=self.host.mcp_config,role_contract=self.host.role_contract)
        ref=host.issue_reference(self.session,'demo-b','attempt-1',1)
        contract=self.host.role_contract.resolve('tenant-1','demo-b','attempt-1','fixture-only')
        binding=dict(ref,task_id='demo-b',attempt_id='attempt-1',snapshot_digest='a'*64,provider_ref='fixture-only',contract_id=contract['contract_id'],contract_version=contract['contract_version'],contract_sha256=contract['contract_sha256'],applicability={k:contract[k] for k in ('role_id','role_version','role_scope','required_categories','not_applicable','required_checks')})
        cycle=self.component.prepare(binding);self.component.publish_candidate(binding,cycle);self.component.reconcile_settlement(binding,cycle)
        manifest=json.loads((self.component.cyclepath(cycle)/'record.json').read_text())['manifest_sha256']
        self.req.update(ref);self.req['backup_manifest_sha256']=manifest
        root=self.root/'lifecycle';(root/'artifacts').mkdir(parents=True)
        original=app.make_server;responses=[]
        def wrapping(*args,**kwargs):
            self.assertIsInstance(args[10].backend,CanonicalHandoffBackend)
            server=original(*args,**kwargs)
            def serve():
                for method,path,body in [('POST','/api/admin/handoff-event',self.req),('GET','/api/admin/handoff-event?task_id=demo-b&attempt_id=attempt-1&event_id='+self.req['event_id'],None)]:
                    t=threading.Thread(target=server.handle_request);t.start();c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    try:
                        c.request(method,path,json.dumps(body) if body else None,{'Host':'localhost:%d'%server.server_port,'Cookie':self.sessions.COOKIE+'='+self.token,'X-CSRF-Token':self.csrf,'Content-Type':'application/json'})
                        r=c.getresponse();responses.append((r.status,json.loads(r.read())))
                    finally:c.close();t.join(5)
            server.serve_forever=serve;return server
        with patch.object(app,'make_server',side_effect=wrapping),contextlib.redirect_stdout(io.StringIO()):
            runtime.main(self.argv+['--handoff-backup-inventory-file',str(self.config)],db=self.s.db,tenant_id='tenant-1',issuer='formal-fixture',identity_provider=self.provider,session_store=self.sessions,evidence=self.auth,role_contract=self.host.role_contract,mcp_config=self.host.mcp_config,lifecycle_root=str(root),ledger_root=str(self.root/'ledger-canonical'),namespace='tenant-ledger',writer='writer')
        self.assertEqual([r[0] for r in responses],[200,200])
        self.assertEqual(responses[1][1]['backup_state'],'INCOMPLETE')
        self.assertNotIn('SOURCE',responses[1][1]['missing']);self.assertIn('CREDENTIAL_RECOVERY',responses[1][1]['missing'])
        self.assertFalse(self.s.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
