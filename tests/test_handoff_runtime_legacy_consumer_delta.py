"""Original runtime/main/HTTP + real SOURCE consumer; synthetic identity only."""
import contextlib,copy,http.client,io,json,threading,unittest
from unittest.mock import patch
import backup_component_hostcycle as component
import task_center_app as app
import task_center_handoff_runtime as runtime
import test_handoff_backup_script_main_delta as fixture

class ExistingAuthority:
    """Test-only custody; never a production identity provider/grant."""
    def __init__(self,evidence):self.evidence=evidence
    def verify(self,*args):return None
    def current_session(self,session):
        return dict(tenant_id=session['tenant_id'],principal_id=session['principal_id'],
            session_hash=session['session_hash'],session_id='session-'+session['principal_id'],expires_at=session['expires_at'])
    def authorize(self,current,action,binding):
        return dict(binding=copy.deepcopy(binding),claims=self.evidence.authenticate_and_authorize(current,action,binding))

class RuntimeExistingConsumer(unittest.TestCase):
    write_config=fixture.ScriptMainBackup.write_config
    def setUp(self):fixture.ScriptMainBackup.setUp(self)
    def run_entry(self,replace=False):
        root=self.root/'lifecycle';(root/'artifacts').mkdir(parents=True)
        original=app.make_server;read=component.BackupComponent._readback;observed=[];responses=[];hosts=[]
        def readback(obj,*args):
            observed.append(obj.host.host.db.in_transaction)
            result=read(obj,*args)
            if replace:self.auth.assess_backup=None
            return result
        def wrapping(*args,**kwargs):
            hosts.append(kwargs['handoff_host'])
            self.assertIs(kwargs['ledger_bridge'].host,kwargs['handoff_host'])
            server=original(*args,**kwargs)
            def serve():
                for method,path,body in [('POST','/api/admin/handoff-event',self.req),
                        ('GET','/api/admin/handoff-event?task_id=demo-b&attempt_id=attempt-1&event_id='+self.req['event_id'],None)]:
                    t=threading.Thread(target=server.handle_request);t.start()
                    c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    try:
                        c.request(method,path,json.dumps(body) if body is not None else None,
                            {'Host':'localhost:%d'%server.server_port,'Cookie':self.sessions.COOKIE+'='+self.token,
                             'X-CSRF-Token':self.csrf,'Content-Type':'application/json'})
                        r=c.getresponse();responses.append((r.status,json.loads(r.read())))
                    finally:c.close();t.join(5)
            server.serve_forever=serve;return server
        with patch.object(app,'make_server',side_effect=wrapping),patch.object(component.BackupComponent,'_readback',new=readback),contextlib.redirect_stdout(io.StringIO()):
            runtime.main(self.argv+['--handoff-backup-inventory-file',str(self.config)],
                db=self.s.db,tenant_id='tenant-1',issuer='formal-fixture',identity_backend=ExistingAuthority(self.auth),
                session_store=self.sessions,evidence=self.auth,role_contract=self.host.role_contract,mcp_config=self.host.mcp_config,
                lifecycle_root=str(root),ledger_root=str(self.root/'ledger-runtime'),namespace='tenant-ledger',writer='writer')
        return responses,observed,hosts
    def test_existing_consumer_through_runtime_main_http_is_source_only(self):
        before=self.s.db.execute("SELECT state FROM tasks WHERE task_id='demo-b'").fetchone()[0]
        responses,observed,hosts=self.run_entry()
        self.assertEqual([r[0] for r in responses],[200,200])
        self.assertEqual(responses[0][1]['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(responses[1][1]['backup_state'],'INCOMPLETE')
        self.assertNotIn('SOURCE',responses[1][1]['missing'])
        self.assertIn('CREDENTIAL_RECOVERY',responses[1][1]['missing'])
        self.assertEqual(observed,[False])
        self.assertIs(hosts[0].adapter.delegate.assess_backup,self.auth.assess_backup)
        self.assertEqual(self.s.db.execute("SELECT state FROM tasks WHERE task_id='demo-b'").fetchone()[0],before)
        self.assertFalse(self.s.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
    def test_consumer_replacement_during_readback_is_not_cached_or_complete(self):
        responses,observed,_=self.run_entry(replace=True)
        self.assertEqual([r[0] for r in responses],[200,200])
        self.assertEqual(responses[1][1]['backup_state'],'UNKNOWN')
        self.assertEqual(observed,[False]);self.assertIsNone(self.auth.assess_backup)
        self.assertFalse(self.s.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
    def test_arbitrary_complete_callback_still_rejected_before_listener(self):
        self.auth.assess_backup=lambda binding:dict(state='COMPLETE',missing=[],cycle_at=0)
        with patch.object(app,'make_server',side_effect=AssertionError('must not bind')) as server:
            with self.assertRaisesRegex(ValueError,'BACKUP_INVENTORY_CONFIG_UNAVAILABLE_OR_INVALID'):
                self.run_entry()
            self.assertFalse(server.called)
