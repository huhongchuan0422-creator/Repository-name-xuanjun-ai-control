"""Actual bootstrap/main/HTTP; synthetic external custody, never live identity."""
import contextlib,copy,http.client,io,json,threading,unittest
from unittest.mock import patch
import task_center_app as app
import task_center_handoff_runtime as runtime
import test_handoff_backup_script_main_delta as fixture

class Authority:
    def __init__(self):self.revoked=False;self.calls=[];self.change=None
    def verify(self,user,password):
        return dict(tenant_id='tenant-1',principal_id='alice',roles=['TASK_CENTER_ADMIN'])
    def current_session(self,session):
        if self.revoked:return None
        return dict(
            tenant_id=session['tenant_id'],principal_id=session['principal_id'],session_hash=session['session_hash'],
            expires_at=session['expires_at'],session_id='custodied-alice')
    def authorize(self,current,action,binding):
        self.calls.append((action,copy.deepcopy(binding)))
        claims=dict(issuer='formal-fixture',tenant_id=current['tenant_id'],principal_id=current['principal_id'],
            session_id=current['session_id'],role_id='role-giver',expires_at=current['expires_at'],scope='handoff:'+action)
        result=dict(binding=copy.deepcopy(binding),claims=claims)
        if self.change:self.change(result)
        return result

class RuntimeBootstrap(unittest.TestCase):
    write_config=fixture.ScriptMainBackup.write_config
    def setUp(self):fixture.ScriptMainBackup.setUp(self)

    def test_bootstrap_actual_main_reference_and_live_revocation(self):
        authority=Authority();root=self.root/'lifecycle';(root/'artifacts').mkdir(parents=True)
        original=app.make_server;observed=[];responses=[];gateway=object()
        def wrapping(*args,**kwargs):
            self.assertIs(kwargs['gateway_runtime'],gateway)
            self.assertIsInstance(args[10],runtime.HostIdentityProvider)
            self.assertIsInstance(kwargs['handoff_host'].adapter,runtime.HostActionAdapter)
            self.assertIs(kwargs['ledger_bridge'].host,kwargs['handoff_host'])
            observed.append(kwargs['handoff_host'])
            server=original(*args,**kwargs)
            def serve():
                reference=None
                for step in ('ISSUE','PROPOSE','READ','REVOKED'):
                    authority.revoked=step=='REVOKED'
                    method='POST';path='/api/admin/handoff-reference'
                    body=dict(task_id='demo-b',attempt_id='attempt-1',handoff_version=1)
                    if step=='PROPOSE':
                        path='/api/admin/handoff-event';body=dict(self.req,**reference)
                    elif step=='READ':
                        method='GET';path='/api/admin/handoff-event?task_id=demo-b&attempt_id=attempt-1&event_id='+reference['event_id'];body=None
                    t=threading.Thread(target=server.handle_request);t.start()
                    c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    try:
                        c.request(method,path,json.dumps(body) if body is not None else None,
                            {'Host':'localhost:%d'%server.server_port,'Cookie':self.sessions.COOKIE+'='+self.token,
                             'X-CSRF-Token':self.csrf,'Content-Type':'application/json'})
                        r=c.getresponse();responses.append((r.status,json.loads(r.read())))
                        if step=='ISSUE':reference=responses[-1][1]
                    finally:c.close();t.join(5)
            server.serve_forever=serve;return server
        with patch.object(app,'make_server',side_effect=wrapping),contextlib.redirect_stdout(io.StringIO()):
            runtime.main(self.argv,db=self.s.db,tenant_id='tenant-1',issuer='formal-fixture',identity_backend=authority,
                session_store=self.sessions,role_contract=self.host.role_contract,mcp_config=self.host.mcp_config,
                lifecycle_root=str(root),ledger_root=str(self.root/'runtime-ledger'),namespace='tenant-ledger',writer='writer',gateway_runtime=gateway)
        self.assertEqual([r[0] for r in responses],[200,200,200,409])
        self.assertEqual(responses[-1][1]['error'],'HANDOFF_REFERENCE_UNAVAILABLE')
        self.assertEqual(responses[1][1]['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(responses[2][1]['backup_state'],'UNKNOWN')
        self.assertIn('READ',[action for action,_ in authority.calls])
        self.assertEqual(authority.calls[0],('ISSUE',dict(task_id='demo-b',attempt_id='attempt-1',handoff_version=1)))
        self.assertIsNone(observed[0].adapter.prepare_backup_assessment(observed[0]))
        self.assertIsNone(observed[0].adapter.assess_provider({}))
        self.assertIsNone(self.host._lifecycle_candidate_readback)

    def test_exact_action_binding_identity_scope_expiry_and_revocation(self):
        backend=Authority();identity=runtime.HostIdentityProvider('tenant-1',backend)
        adapter=runtime.HostActionAdapter(identity,'formal-fixture');session=self.sessions.get(self.token)
        binding=dict(task_id='demo-b',attempt_id='attempt-1',handoff_version=1)
        for action in ('ISSUE','READ','PROPOSE','RECEIVE','NOMINATE','ALIGNED','SUPERVISION_START','VERIFIED'):
            self.assertEqual(adapter.authenticate_and_authorize(session,action,binding)['scope'],'handoff:'+action)
        changes=[lambda r:r['binding'].update(task_id='other'),lambda r:r['binding'].update(attempt_id='other'),
            lambda r:r['binding'].update(handoff_version=2),lambda r:r['claims'].update(tenant_id='other'),
            lambda r:r['claims'].update(principal_id='other'),lambda r:r['claims'].update(session_id='other'),
            lambda r:r['claims'].update(scope='handoff:VERIFIED'),lambda r:r['claims'].update(expires_at=0),
            lambda r:r['claims'].update(expires_at=session['expires_at']+1)]
        for change in changes:
            backend.change=change;self.assertIsNone(adapter.authenticate_and_authorize(session,'ISSUE',binding))
        backend.change=None;backend.revoked=True
        self.assertFalse(identity.is_formal_session(session));self.assertIsNone(adapter.authenticate_and_authorize(session,'ISSUE',binding))
        self.assertFalse(identity.is_formal_session(dict(session,tenant_id='other')))

    def test_missing_real_bootstrap_authority_fails_before_listener(self):
        with patch.object(app,'make_server',side_effect=AssertionError('no listener')):
            with self.assertRaisesRegex(ValueError,'FORMAL_IDENTITY_BACKEND_UNAVAILABLE'):
                runtime.main(self.argv,tenant_id='tenant-1')
