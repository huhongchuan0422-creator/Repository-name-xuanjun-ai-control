"""Original v1 consumer migrated to v2; only isolated local Git/SQLite."""
import copy, json, sqlite3, threading, unittest
from unittest.mock import patch
import test_host_main_checkpoint as prior
from task_center_backup_v1_migration import V1PreparedHostAdapter, migrate_v1_consumer
from task_center_handoff_host import HandoffHost
from task_center_role_contract import RoleContractResolver

class V1MigrationDelta(unittest.TestCase):
    def setUp(self):
        self.f=prior.MainCheckpoint();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.host=self.f.f.host;self.db=self.f.f.db;self.delegate=self.f.f.auth
        policy=self.host.role_contract.resolve('tenant-1','task-1','attempt-1','fixture-only')
        self.inventory={'tenant_id':'tenant-1','task_id':'task-1','attempt_id':'attempt-1','provider_ref':'fixture-only','contract_sha256':policy['contract_sha256'],'resources':{'repo':[('SOURCE',self.f.source,'demo.py')]}}
        self.v1=self.f.bridge
        # The actual existing caller installed this exact v1 object on the
        # original adapter; the migrated host installs the concrete wrapper.
        self.assertIs(self.delegate.assess_backup,self.v1)
        self.adapter=migrate_v1_consumer(self.delegate,[self.inventory]);self.host.adapter=self.adapter
    def test_existing_v1_caller_retains_original_source_assertions(self):
        # Reuse the original 8fe test method and its exact original assertions;
        # only the host's adapter registration has been migrated.
        self.f.test_source_readback_to_original_host_alert_and_receipt()
        self.assertIs(self.delegate.assess_backup,self.v1)
    def test_other_original_v1_consumer_assertions_remain_unchanged(self):
        self.f.test_wrong_manifest_rejected_and_unverified_source_stays_missing()
        self.f.test_unknown_cycle_not_forged()

    def test_existing_v1_unknown_can_recheck_after_explicit_migration(self):
        self.host.adapter=self.delegate
        with patch.object(type(self.v1),'__call__',side_effect=AssertionError('old in-transaction callback forbidden')):
            first=self.host.record('alice',copy.deepcopy(self.f.req))
        self.assertEqual(first['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')
        self.host.adapter=self.adapter
        second=self.host.record('alice',copy.deepcopy(self.f.req))
        self.assertEqual(second['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        receipt=self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])
        self.assertEqual([x['backup_state'] for x in receipt['history']],['UNKNOWN','INCOMPLETE'])
        self.assertNotIn('SOURCE',receipt['missing']);self.assertIn('CREDENTIAL_RECOVERY',receipt['missing'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],2)
        self.assertEqual(receipt['alert_delivery'],'UNKNOWN')

    def test_no_inventory_is_unknown_not_caller_attestation(self):
        self.host.adapter=V1PreparedHostAdapter(self.delegate,self.v1,[])
        result=self.host.record('alice',copy.deepcopy(self.f.req))
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')
    def test_fresh_host_db_is_rebound_without_mutating_v1(self):
        original_resolver=self.v1.component.host
        conn=sqlite3.connect(self.f.f.path);conn.row_factory=sqlite3.Row
        try:
            old=self.host.role_contract;role=RoleContractResolver(conn,old.contracts,old.intake_plans)
            fresh=HandoffHost(conn,self.host.tenant_id,self.host.issuer,self.adapter,clock=self.host.clock,mcp_config=self.host.mcp_config,role_contract=role)
            prepared=self.adapter.prepare_backup_assessment(fresh)
            self.assertIs(prepared.db,conn);self.assertIs(prepared.component.host.host.db,conn)
            self.assertIsNot(prepared.component,self.v1.component);self.assertIs(self.v1.component.host,original_resolver)
            outcome=fresh.record('alice',copy.deepcopy(self.f.req));self.assertEqual(outcome['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
            receipt=fresh.read_receipt('bob','task-1','attempt-1',self.f.req['event_id']);self.assertNotIn('SOURCE',receipt['missing']);self.assertIn('CREDENTIAL_RECOVERY',receipt['missing'])
        finally:conn.close()
    def test_migrated_v1_through_real_http_thread_and_fresh_db(self):
        import http.client
        from task_center_app import make_server
        from task_center_handoff_host import FormalHandoffIdentityProvider
        from task_center_handoff_ledger import HandoffLedgerBridge
        from task_center_session_auth import SessionStore
        import backup_component_hostcycle as component
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('tenant_id')=='tenant-1'
        def connect():
            db=sqlite3.connect(self.f.f.path);db.row_factory=sqlite3.Row;return db
        sessions=SessionStore(connect,'tenant-1',ttl_seconds=3600,clock=self.host.clock)
        token,csrf,_=sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        prior_auth=self.delegate.authenticate_and_authorize
        self.delegate.authenticate_and_authorize=lambda session,action,binding:prior_auth(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        ledger=HandoffLedgerBridge(self.host,str(self.f.root/'ledger'),'tenant-ledger','writer')
        server=make_server(self.f.f.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,
            identity_provider=Identity(),session_store=sessions,outbound_enabled=False,handoff_host=self.host,ledger_bridge=ledger)
        thread=threading.Thread(target=server.serve_forever);thread.start();observed=[]
        orig=component.BackupComponent._readback
        def readback(obj,*args):
            observed.append((threading.current_thread() is not threading.main_thread(),obj.host.host.db.in_transaction));return orig(obj,*args)
        try:
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':'localhost:%s'%server.server_port,'Cookie':sessions.COOKIE+'='+token,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
            with patch.object(component.BackupComponent,'_readback',new=readback):
                client.request('POST','/api/admin/handoff-event',json.dumps(self.f.req),headers)
                response=client.getresponse();body=json.loads(response.read().decode());client.close()
            self.assertEqual(response.status,200);self.assertEqual(body['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
            self.assertEqual(observed,[(True,False)])
            receipt=self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])
            self.assertEqual(receipt['backup_state'],'INCOMPLETE');self.assertNotIn('SOURCE',receipt['missing']);self.assertIn('CREDENTIAL_RECOVERY',receipt['missing'])
            self.assertEqual(receipt['alert_delivery'],'UNKNOWN')
        finally:server.shutdown();thread.join(3);server.server_close()

    def test_revoked_binding_and_source_mismatch_never_claim_complete(self):
        self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='role-agent'");self.db.commit()
        outcome=self.host.record('alice',copy.deepcopy(self.f.req));self.assertEqual(outcome['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')
        self.assertFalse(self.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
    def test_wrong_manifest_and_unissued_event_fail_closed(self):
        bad=copy.deepcopy(self.f.req);bad['backup_manifest_sha256']='0'*64
        outcome=self.host.record('alice',bad);self.assertEqual(outcome['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        receipt=self.host.read_receipt('bob','task-1','attempt-1',bad['event_id'])
        self.assertEqual(receipt['backup_state'],'UNKNOWN');self.assertEqual(receipt['alert_delivery'],'UNKNOWN')
        bad=copy.deepcopy(self.f.req);bad['event_id']='ev-'+'0'*32
        with self.assertRaises(ValueError):self.host.record('alice',bad)
        self.assertFalse(self.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())

    def test_readback_is_outside_transaction_and_legacy_not_called(self):
        import backup_component_hostcycle as component
        original=component.BackupComponent._readback;observed=[]
        def readback(obj,*args):observed.append(self.db.in_transaction);return original(obj,*args)
        with patch.object(component.BackupComponent,'_readback',new=readback),patch.object(type(self.v1),'__call__',side_effect=AssertionError('legacy callback forbidden')):
            result=self.host.record('alice',copy.deepcopy(self.f.req))
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertEqual(observed,[False])
        self.assertNotIn('SOURCE',self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['missing'])

if __name__=='__main__':unittest.main()
