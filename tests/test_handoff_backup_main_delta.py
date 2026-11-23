"""Original host + reviewed producer in isolated temp DB/local bare Git only."""
import copy,fcntl,json,unittest
from unittest.mock import patch
import test_host_main_checkpoint as source_fixture
from task_center_handoff_host import REQUIRED_CONTEXT
from task_center_backup_bridge_v2 import PreparedBackupAssessment
from task_center_backup_local_resolver import LocalHostContract

class ActualBackupEntry(unittest.TestCase):
    def setUp(self):
        self.f=source_fixture.MainCheckpoint();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.host=self.f.f.host;self.auth=self.f.f.auth;self.db=self.f.f.db;self.component=self.f.c
        policy=self.host.role_contract.resolve('tenant-1','task-1','attempt-1','fixture-only')
        self.inventory={'tenant_id':'tenant-1','task_id':'task-1','attempt_id':'attempt-1','provider_ref':'fixture-only',
            'contract_sha256':policy['contract_sha256'],'resources':{'repo':[('SOURCE',self.f.source,'demo.py')]}}
        self.component.host=LocalHostContract(self.host,[self.inventory])
        self.assessor=PreparedBackupAssessment(self.component,'tenant-1',REQUIRED_CONTEXT,self.db)
        self.auth.prepare_backup_assessment=lambda host:self.assessor
    def record(self):return self.host.record('alice',copy.deepcopy(self.f.req))
    def test_actual_host_entry_preflights_outside_transaction_and_holds_lock(self):
        calls=[];snapshots=[];original=self.component._readback;old=self.assessor._snapshot
        def readback(*args):
            calls.append(self.db.in_transaction);return original(*args)
        def snapshot(*args):
            if self.db.in_transaction:
                with (self.component.home/'run.lock').open('a') as lock:
                    with self.assertRaises(BlockingIOError):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                snapshots.append(True)
            return old(*args)
        with patch.object(self.component,'_readback',side_effect=readback),patch.object(self.assessor,'_snapshot',side_effect=snapshot):
            result=self.record()
        self.assertEqual(calls,[False]);self.assertEqual(snapshots,[True]);self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        receipt=self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])
        self.assertNotIn('SOURCE',receipt['missing']);self.assertIn('CREDENTIAL_RECOVERY',receipt['missing']);self.assertEqual(receipt['alert_delivery'],'UNKNOWN')
        self.assertFalse(self.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
    def test_no_assessment_and_unissued_reference_fail_closed_without_readback(self):
        self.auth.prepare_backup_assessment=lambda host:None
        with patch.object(self.component,'_readback',side_effect=AssertionError('unexpected remote')) as readback, patch.object(self.auth,'assess_backup',side_effect=AssertionError('legacy callback forbidden')) as old:
            self.assertEqual(self.record()['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
            self.assertFalse(readback.called);self.assertFalse(old.called)
        self.auth.prepare_backup_assessment=lambda host:self.assessor
        value=copy.deepcopy(self.f.req);value['event_id']='ev-'+'0'*32
        with patch.object(self.component,'_readback',side_effect=AssertionError('unexpected remote')) as readback:
            with self.assertRaises(ValueError):self.host.record('alice',value)
            self.assertFalse(readback.called)
    def test_existing_http_post_invokes_preflight_before_transaction(self):
        import io
        from types import SimpleNamespace
        from task_center_app import build_handler
        from task_center_handoff_host import FormalHandoffIdentityProvider
        class Sessions:
            tenant_id='tenant-1';COOKIE='session'
            def get(self,token):return 'alice' if token == 'good' else None
            def verify_csrf(self,session,token):return token == 'csrf'
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session=='alice'
        handler=build_handler(self.f.f.path,b'0'*32,'tenant-1','viewer',identity_provider=Identity(),session_store=Sessions(),handoff_host=self.host)
        h=handler.__new__(handler);h.command='POST';h.path='/api/admin/handoff-event';h.server=SimpleNamespace(server_port=8765)
        raw=json.dumps(self.f.req).encode();h.headers={'Host':'localhost:8765','Cookie':'session='+'good','X-CSRF-Token':'csrf','Content-Length':str(len(raw))};h.rfile=io.BytesIO(raw);out=[]
        h._send=lambda status,data,kind,extra_headers=None:out.append((status,json.loads(data)))
        old=self.component._readback;observed=[]
        def readback(*args):observed.append(self.db.in_transaction);return old(*args)
        with patch.object(self.component,'_readback',side_effect=readback):h.do_POST()
        self.assertEqual(out[0][0],200);self.assertEqual(out[0][1]['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertEqual(observed,[False])
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)

    def test_busy_preflight_alerts_unknown_without_retrying_producer(self):
        self.assessor._guard.acquire()
        try:
            with patch.object(self.component,'_readback',side_effect=AssertionError('unexpected remote')) as readback:
                result=self.record();self.assertFalse(readback.called)
        finally:self.assessor._guard.release()
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
    def test_error_after_record_never_blindly_replays(self):
        calls=[]
        def commit_then_error(host,session,value,binding):
            calls.append(True);host.record(session,value)
            raise RuntimeError('assessment busy')
        with patch.object(self.assessor,'execute',side_effect=commit_then_error):
            with self.assertRaisesRegex(RuntimeError,'assessment busy'):self.record()
        self.assertEqual(len(calls),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)

    def test_invalid_binding_cannot_trigger_remote(self):
        for field,value in [('snapshot_digest','not-a-digest'),('checked',['unregistered'])]:
            request=copy.deepcopy(self.f.req);request[field]=value
            with patch.object(self.component,'_readback',side_effect=AssertionError('unexpected remote')) as readback:
                with self.assertRaises(ValueError):self.host.record('alice',request)
                self.assertFalse(readback.called)

    def test_unauthorized_session_never_triggers_remote(self):
        self.auth.enabled=False
        with patch.object(self.component,'_readback',side_effect=AssertionError('unexpected remote')) as readback:
            with self.assertRaises(ValueError):self.record()
            self.assertFalse(readback.called)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
    def test_fresh_request_connection_uses_own_local_resolver(self):
        import sqlite3
        from task_center_handoff_host import HandoffHost
        from task_center_role_contract import RoleContractResolver
        from backup_component_hostcycle import BackupComponent
        conn=sqlite3.connect(self.f.f.path);conn.row_factory=sqlite3.Row
        try:
            prior=self.host.role_contract
            role=RoleContractResolver(conn,prior.contracts,prior.intake_plans)
            host=HandoffHost(conn,self.host.tenant_id,self.host.issuer,self.auth,clock=self.host.clock,mcp_config=self.host.mcp_config,role_contract=role)
            def create(request_host):
                resolver=LocalHostContract(request_host,[self.inventory])
                component=BackupComponent(self.component.home,self.component.remote,self.component.branch,resolver,fixture_push=True)
                return PreparedBackupAssessment(component,request_host.tenant_id,REQUIRED_CONTEXT,request_host.db)
            self.auth.prepare_backup_assessment=create
            result=host.record('alice',copy.deepcopy(self.f.req))
            self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
            self.assertNotIn('SOURCE',host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['missing'])
        finally:conn.close()

    def test_local_record_changed_between_preflight_and_transaction(self):
        original=self.host._record_authenticated
        path=self.component.cyclepath(self.f.ref['backup_cycle_id'])/'record.json'
        def change(session,value,assessor):
            record=json.loads(path.read_text());record['result']='0'*40;path.write_text(json.dumps(record))
            return original(session,value,assessor)
        with patch.object(self.host,'_record_authenticated',side_effect=change):result=self.record()
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')
    def test_revoked_role_between_preflight_and_transaction_is_not_success(self):
        original=self.host._record_authenticated
        def revoke(session,value,assessor):
            self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='role-agent'");self.db.commit()
            return original(session,value,assessor)
        with patch.object(self.host,'_record_authenticated',side_effect=revoke):result=self.record()
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertFalse(self.db.execute("SELECT 1 FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone())
    def test_remote_failure_is_unknown_and_error_is_not_echoed(self):
        with patch.object(self.component,'_readback',side_effect=OSError('private-error-text')):result=self.record()
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        receipt=self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])
        self.assertEqual(receipt['backup_state'],'UNKNOWN');self.assertNotIn('private-error-text',json.dumps(receipt))

    def test_pending_or_changed_local_record_is_unknown(self):
        original=self.host._record_authenticated
        def pending(session,value,assessor):
            (self.component.home/'pending.json').write_text('{}')
            return original(session,value,assessor)
        with patch.object(self.host,'_record_authenticated',side_effect=pending):result=self.record()
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        receipt=self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])
        self.assertEqual(receipt['backup_state'],'UNKNOWN')
    def test_scope_inventory_mismatch_never_reads_remote(self):
        bad=copy.deepcopy(self.inventory);bad['resources']={'unrelated':bad['resources']['repo']}
        self.component.host=LocalHostContract(self.host,[bad])
        with patch.object(self.component,'_readback',side_effect=AssertionError('unexpected remote')) as readback:
            result=self.record();self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertFalse(readback.called)
        self.assertEqual(self.host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')

if __name__=='__main__':unittest.main()
