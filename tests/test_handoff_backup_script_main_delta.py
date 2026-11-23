"""Original app.main configured consumer; isolated identity and producer only."""
import contextlib,copy,http.client,io,json,os,pathlib,sqlite3,subprocess,tempfile,threading,time,unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import test_handoff_host_delta as fixture
import backup_component_hostcycle as component
import task_center_app as app
from task_center_handoff_host import FormalHandoffIdentityProvider,HandoffHost,REQUIRED_CONTEXT
from task_center_handoff_ledger import HandoffLedgerBridge
from task_center_session_auth import SessionStore
from task_center_role_contract import RoleContractResolver
from task_center_backup_local_resolver import LocalHostContract
from task_center_backup_bridge import BackupAssessment
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel,TestTenantAuthority
from reusable_scheduler_cli import demo_graph
from model_orchestration import ModelControl

class ScriptMainBackup(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
        self.path=str(self.root/'task-center.sqlite');self.s=Supervisor(self.path);self.addCleanup(self.s.close)
        key=b'0123456789abcdef0123456789abcdef';authority=TestTenantAuthority(key);gateway=GatewayKernel(self.s,authority)
        gateway.register_graph(authority.issue('tenant-1','seed'),demo_graph('tenant-1'))
        self.s.claim_writer('demo-b','attempt-1','owner','entry',{'caller_id':'caller','run_id':'run','session_id':'session','gateway_id':'gateway'},'lease','provider',['fake:demo-b'],time.time()+600)
        self.keyfile=self.root/'model.key';master=Fernet.generate_key();self.keyfile.write_bytes(master);self.keyfile.chmod(0o600)
        ModelControl(gateway,authority.issue('tenant-1','admin:fixture'),master)
        self.s.db.execute('INSERT INTO role_templates VALUES(?,?,?,?,?,?,?,?)',('tenant-1','role-agent','v1','EXECUTOR',json.dumps(['code']),1,1,None))
        self.s.db.execute('INSERT INTO model_assignments VALUES(?,?,?,?,?,?,?,?,?,?,?)',('tenant-1','demo-b','attempt-1','role-agent','v1','agent','fixture-only','fixture-model','ASSIGNED','FIXTURE',time.time()));self.s.db.commit()
        policy={'contract_id':'main-fixture','contract_version':1,'tenant_id':'tenant-1','project_id':'demo-project','task_id':'demo-b','attempt_id':'attempt-1','task_spec_sha256':'b'*64,'role_id':'role-agent','role_version':'v1','role_scope':['code'],'provider_id':'fixture-only','required_categories':['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT','INSTALL','SOURCE'],'not_applicable':{}}
        resolver=RoleContractResolver(self.s.db,[policy]);self.auth=fixture.SimulatedHost();self.auth.override={'expires_at':time.time()+600}
        self.host=HandoffHost(self.s.db,'tenant-1','formal-fixture',self.auth,mcp_config=fixture.CONFIG,role_contract=resolver)
        self.ref=self.host.issue_reference('alice','demo-b','attempt-1',1);contract=resolver.resolve('tenant-1','demo-b','attempt-1','fixture-only')
        self.source=self.root/'source';self.source.mkdir();(self.source/'demo.py').write_text('print(1)\n')
        subprocess.check_call(['git','init','--bare','-q',str(self.root/'remote.git')])
        policy={'tenant_id':'tenant-1','task_id':'demo-b','attempt_id':'attempt-1','provider_ref':'fixture-only','contract_sha256':contract['contract_sha256'],'resources':{'fake:demo-b':[('SOURCE',self.source,'demo.py')]}}
        self.component=component.BackupComponent(self.root/'home',self.root/'remote.git','backup/main',LocalHostContract(self.host,[policy]),fixture_push=True)
        binding=dict(self.ref,task_id='demo-b',attempt_id='attempt-1',snapshot_digest='a'*64,provider_ref='fixture-only',contract_id=contract['contract_id'],contract_version=contract['contract_version'],contract_sha256=contract['contract_sha256'],applicability={k:contract[k] for k in ('role_id','role_version','role_scope','required_categories','not_applicable','required_checks')})
        cycle=self.component.prepare(binding);self.component.publish_candidate(binding,cycle);self.component.reconcile_settlement(binding,cycle)
        manifest=json.loads((self.component.cyclepath(cycle)/'record.json').read_text())['manifest_sha256']
        self.req=dict(self.ref,task_id='demo-b',attempt_id='attempt-1',action='PROPOSE',causation='NONE',snapshot_digest='a'*64,backup_manifest_sha256=manifest,checked=list(contract['required_checks']),provider_ref='fixture-only')
        self.auth.assess_backup=BackupAssessment(self.component,'tenant-1',REQUIRED_CONTEXT)
        self.config=self.root/'inventory.json';self.doc={'schema_version':1,'enabled':True,'policies':[{'tenant_id':'tenant-1','task_id':'demo-b','attempt_id':'attempt-1','provider_ref':'fixture-only','contract_sha256':contract['contract_sha256'],'resources':{'fake:demo-b':[{'category':'SOURCE','root':str(self.source),'relative_path':'demo.py'}]}}]};self.write_config(self.doc)
        def connect():
            db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
        self.sessions=SessionStore(connect,'tenant-1',ttl_seconds=3600)
        self.token,self.csrf,_=self.sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        old=self.auth.authenticate_and_authorize
        self.auth.authenticate_and_authorize=lambda session,action,binding:old(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        self.bridge=HandoffLedgerBridge(self.host,str(self.root/'ledger'),'tenant-ledger','writer')
        self.argv=['--db',self.path,'--test-authority-key',key.decode(),'--tenant','tenant-1','--port','0','--model-master-key-file',str(self.keyfile)]
    def write_config(self,doc):self.config.write_text(json.dumps(doc));self.config.chmod(0o600)
    def run_main(self,extra,identity=True):
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('tenant_id')=='tenant-1'
        captured=[];binding=[];observed=[];original=app.make_server;read=component.BackupComponent._readback
        def readback(obj,*args):observed.append(obj.host.host.db.in_transaction);return read(obj,*args)
        def wrapping(*args,**kwargs):
            host=kwargs['handoff_host'];bridge=kwargs['ledger_bridge'];binding.append((host,bridge))
            server=original(*args,**kwargs)
            def serve_requests():
                def call(method,path,value=None):
                    t=threading.Thread(target=server.handle_request);t.start()
                    c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    headers={'Host':'localhost:%s'%server.server_port,'Cookie':self.sessions.COOKIE+'='+self.token,'X-CSRF-Token':self.csrf,'Content-Type':'application/json'}
                    try:
                        c.request(method,path,json.dumps(value) if value is not None else None,headers)
                        r=c.getresponse();captured.append((r.status,json.loads(r.read().decode())))
                    finally:c.close();t.join(5)
                call('POST','/api/admin/handoff-event',copy.deepcopy(self.req))
                call('GET','/api/admin/handoff-event?task_id=demo-b&attempt_id=attempt-1&event_id='+self.req['event_id'])
            server.serve_forever=serve_requests;return server
        args=self.argv+extra if identity else self.argv[:-2]+extra
        with patch.object(app,'make_server',side_effect=wrapping),patch.object(component.BackupComponent,'_readback',new=readback),contextlib.redirect_stdout(io.StringIO()):
            app.main(args,identity_provider=Identity() if identity else None,session_store=self.sessions if identity else None,handoff_host=self.host,ledger_bridge=self.bridge)
        return captured,binding,observed
    def test_script_main_loads_config_and_binds_bridge_to_returned_host(self):
        captured,binding,observed=self.run_main(['--handoff-backup-inventory-file',str(self.config)])
        configured,bridge=binding[0];self.assertIsNot(configured,self.host);self.assertIs(bridge.host,configured);self.assertIs(self.bridge.host,self.host)
        self.assertEqual(captured[0][0],200);self.assertEqual(captured[0][1]['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(captured[1][0],200);receipt=captured[1][1];self.assertEqual(receipt['backup_state'],'INCOMPLETE')
        self.assertNotIn('SOURCE',receipt['missing']);self.assertIn('CREDENTIAL_RECOVERY',receipt['missing']);self.assertEqual(receipt['alert_delivery'],'UNKNOWN')
        self.assertEqual(observed,[False])
    def test_disabled_config_keeps_existing_host_bridge_and_unknown(self):
        self.write_config({'schema_version':1,'enabled':False,'policies':[]})
        captured,binding,observed=self.run_main(['--handoff-backup-inventory-file',str(self.config)])
        self.assertIs(binding[0][0],self.host);self.assertIs(binding[0][1],self.bridge);self.assertEqual(observed,[])
        self.assertEqual(captured[1][1]['backup_state'],'UNKNOWN')
    def test_no_formal_identity_never_reads_backup_or_grants(self):
        captured,binding,observed=self.run_main(['--handoff-backup-inventory-file',str(self.config)],identity=False)
        self.assertEqual([item[0] for item in captured],[503,503]);self.assertEqual(observed,[])
        self.assertFalse(self.s.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
    def test_no_config_preserves_original_injected_host_and_bridge(self):
        captured,binding,observed=self.run_main([])
        self.assertIs(binding[0][0],self.host);self.assertIs(binding[0][1],self.bridge)
        self.assertEqual(observed,[]);self.assertEqual(captured[1][1]['backup_state'],'UNKNOWN')
    def test_mismatched_injected_bridge_rejected_before_listener(self):
        other=HandoffHost(self.s.db,'tenant-1','formal-fixture',self.auth,mcp_config=fixture.CONFIG,role_contract=self.host.role_contract)
        wrong=HandoffLedgerBridge(other,str(self.root/'other-ledger'),'tenant-ledger','writer')
        with patch.object(app,'make_server',side_effect=AssertionError('must not bind')) as listener:
            with self.assertRaisesRegex(ValueError,'HANDOFF_LEDGER_HOST_BINDING_REQUIRED'):
                app.main(self.argv+['--handoff-backup-inventory-file',str(self.config)],identity_provider=IdentityStub(),session_store=self.sessions,handoff_host=self.host,ledger_bridge=wrong)
            self.assertFalse(listener.called)

    def test_main_rejects_config_without_existing_host_before_listener(self):
        with self.assertRaisesRegex(ValueError,'HANDOFF_HOST_REQUIRED_FOR_BACKUP_CONFIG'):
            app.main(self.argv+['--handoff-backup-inventory-file',str(self.config)],identity_provider=IdentityStub(),session_store=self.sessions)

class IdentityStub(FormalHandoffIdentityProvider):
    def is_formal_session(self,session):return True

if __name__=='__main__':unittest.main()
