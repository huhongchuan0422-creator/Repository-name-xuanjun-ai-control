"""Original MCP terminal path and real SOURCE-only producer, isolated only."""
import copy,hashlib,json,pathlib,subprocess,sys,types,unittest
from unittest.mock import patch
import test_mcp_acceptance_evidence_delta as fixture
from task_center_handoff_host import REQUIRED_CONTEXT
from task_center_role_contract import RoleContractResolver
from task_center_backup_local_resolver import LocalHostContract
from task_center_backup_v1_migration import V1PreparedHostAdapter
from task_center_backup_bridge import BackupAssessment
import backup_component_hostcycle as component

class TerminalPreflightDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixture.AcceptanceEvidence();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.host=self.f.host;self.db=self.f.h.control.db;self.adapter=self.f.adapter
        contracts=[copy.deepcopy(c) for c in self.f.contract.contracts]
        for c in contracts:
            if c['role_id']=='developer':
                c['required_categories']=['ARTIFACT','AUTH_ENTRY','CONFIG_REFERENCE','CONTEXT','SOURCE']
                c['not_applicable']={'INSTALL':'NO_INSTALLATION_SCOPE'}
        self.contract=RoleContractResolver(self.f.h.supervisor.db,contracts)
        self.f.contract=self.contract;self.host.role_contract=self.contract
        self.candidate=self.f.make_candidate();self.snapshot=self.db.execute('SELECT snapshot_sha256 FROM candidate_snapshots WHERE candidate_id=?',(self.candidate,)).fetchone()[0]
        self.root=pathlib.Path(self.f.h.f.root);self.source=self.root/'source';self.source.mkdir();(self.source/'demo.py').write_text('print(1)\n')
        subprocess.check_call(['git','init','--bare','-q',str(self.root/'remote.git')])
        self.ref=self.host.issue_reference('alice','demo-b','attempt-b',1)
        plan=self.contract.resolve('tenant-mcp','demo-b','attempt-b','fixture')
        self.policy={'tenant_id':'tenant-mcp','task_id':'demo-b','attempt_id':'attempt-b','provider_ref':'fixture','contract_sha256':plan['contract_sha256'],'resources':{'fake:demo-b':[('SOURCE',self.source,'demo.py')]}}
        self.component=component.BackupComponent(self.root/'backup-home',self.root/'remote.git','backup/terminal',LocalHostContract(self.host,[self.policy]),fixture_push=True)
        binding=dict(self.ref,task_id='demo-b',attempt_id='attempt-b',snapshot_digest=self.snapshot,provider_ref='fixture',contract_id=plan['contract_id'],contract_version=plan['contract_version'],contract_sha256=plan['contract_sha256'],applicability={k:plan[k] for k in ('role_id','role_version','role_scope','required_categories','not_applicable','required_checks')})
        cycle=self.component.prepare(binding);self.component.publish_candidate(binding,cycle);self.component.reconcile_settlement(binding,cycle)
        record=json.loads((self.component.cyclepath(cycle)/'record.json').read_text());self.manifest=record['manifest_sha256'];self.adapter.cycle=record['cycle_at']
        # Historical six-party fixtures are simulated identity/backup assertions,
        # not evidence of a production handoff. Real SOURCE-only producer below
        # must independently hold final acceptance.
        import threading
        module=types.ModuleType('task_center_backup_bridge_v2')
        class SimulatedPrepared:
            def __init__(self,host,adapter):self.db=host.db;self.adapter=adapter;self._guard=threading.Lock();self.expected=None
            def execute(self,host,session,value,binding):
                self.expected=copy.deepcopy(binding)
                try:return host.record(session,value)
                finally:self.expected=None
            def __call__(self,binding):
                if not self.db.in_transaction or binding!=self.expected:return None
                return self.adapter.assess_backup(binding)
        module.PreparedBackupAssessment=SimulatedPrepared
        self.adapter.prepare_backup_assessment=lambda host:SimulatedPrepared(host,self.adapter)
        refs={'p':self.ref}
        with patch.dict(sys.modules,{'task_center_backup_bridge_v2':module}):
            for action,label,actor,parent in [('PROPOSE','p','alice',None),('NOMINATE','n','alice','p'),('RECEIVE','r','bob','p'),('ALIGNED','a','bob','r'),('SUPERVISION_START','s','carol','n'),('VERIFIED','v','carol','s')]:
                if label!='p':refs[label]=self.host.issue_reference(actor,'demo-b','attempt-b',1,self.ref['event_id'])
                req=dict(refs[label],task_id='demo-b',attempt_id='attempt-b',action=action,causation=refs[parent]['event_id'] if parent else 'NONE',snapshot_digest=self.snapshot,backup_manifest_sha256=self.manifest,checked=list(plan['required_checks']),provider_ref='fixture')
                if action=='NOMINATE':req['target_ref']='acceptor'
                if action=='VERIFIED':req['alignment_ref']=refs['a']['event_id']
                self.assertEqual(self.host.record(actor,req)['state'],'RECORDED')
        self.adapter.event=refs['v']['event_id']
        self.adapter.assess_backup=BackupAssessment(self.component,'tenant-mcp',REQUIRED_CONTEXT)
        self.host.adapter=V1PreparedHostAdapter(self.adapter,self.adapter.assess_backup,[self.policy])
    def assert_hold_alert(self,reason):
        rows=self.db.execute("SELECT e.payload_json,o.delivered_at FROM events e JOIN outbox o ON o.task_id=e.task_id AND o.attempt_id=e.attempt_id AND o.event_id=e.event_id WHERE e.task_id='demo-b' AND e.evidence_ref='CANDIDATE_ACCEPTANCE_EVIDENCE_HOLD'").fetchall()
        self.assertTrue(any(json.loads(row[0])['reason']==reason and row[1] is None for row in rows))
    def test_busy_bridge_is_supervised_before_producer_read(self):
        adapter=self.host.adapter;original=adapter.prepare_backup_assessment
        def busy(host):
            prepared=original(host);prepared._guard.acquire();self.addCleanup(prepared._guard.release);return prepared
        adapter.prepare_backup_assessment=busy
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.call(self.candidate)
            self.assertFalse(readback.called)
        self.assert_hold_alert('CANDIDATE_BACKUP_COMPLETE_REQUIRED')

    def test_unprepared_legacy_adapter_is_not_called_inside_transaction(self):
        legacy=self.adapter.assess_backup;self.host.adapter=self.adapter
        with patch.object(type(legacy),'__call__',side_effect=AssertionError('old remote callback forbidden')) as callback,patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.call(self.candidate)
            self.assertFalse(callback.called);self.assertFalse(readback.called)
        self.assert_hold_alert('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_role_revoked_after_preflight_before_transaction_is_held(self):
        original=component.BackupComponent._readback;seen=[]
        def revoke(obj,*args):
            result=original(obj,*args)
            self.db.execute("UPDATE role_templates SET enabled=0 WHERE role_id='developer'");self.db.commit();seen.append(True)
            return result
        with patch.object(component.BackupComponent,'_readback',new=revoke):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_EXECUTOR_CONTRACT_REQUIRED'):self.f.call(self.candidate)
        self.assertEqual(seen,[True]);self.assert_hold_alert('CANDIDATE_EXECUTOR_CONTRACT_REQUIRED')
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')

    def test_changed_producer_record_holds_without_terminal_or_replay(self):
        original=component.BackupComponent._readback;record_path=self.component.cyclepath(self.ref['backup_cycle_id'])/'record.json';seen=[]
        def alter(obj,*args):
            result=original(obj,*args);data=json.loads(record_path.read_text());data['result']='0'*40;record_path.write_text(json.dumps(data));seen.append(True);return result
        with patch.object(component.BackupComponent,'_readback',new=alter):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.call(self.candidate)
        self.assertEqual(seen,[True]);self.assert_hold_alert('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.db.execute("SELECT state FROM delivery_candidates WHERE candidate_id=?",(self.candidate,)).fetchone()[0],'REVIEW_PASSED')

    def test_original_oauth_http_terminal_holds_incomplete_source_only(self):
        import threading
        from urllib.error import HTTPError
        from task_center_app import make_server
        import test_task_center_mcp_http as http_fixture
        h=self.f.h
        h.f.server.shutdown();h.f.server.server_close();h.f.thread.join(2)
        h.f.server=make_server(h.f.db,fixture.fx_key(),'tenant-mcp','owner',port=0,model_master_key=h.f.master,
            identity_provider=h.f.identity,session_store=h.f.sessions,outbound_enabled=False,
            external_origin='https://'+http_fixture.HOST,base_path='/task-center-test/',
            mcp_enabled=True,mcp_model_worker_enabled=False,mcp_dispatch_config=self.f.fx.config,handoff_host=self.host)
        h.f.thread=threading.Thread(target=h.f.server.serve_forever);h.f.thread.daemon=True;h.f.thread.start()
        h.f.base='http://127.0.0.1:%d/task-center-test'%h.f.server.server_port
        token=h.token(principal='acceptor');original=component.BackupComponent._readback;observed=[]
        def readback(obj,*args):observed.append(obj.host.host.db.in_transaction);return original(obj,*args)
        with patch.object(component.BackupComponent,'_readback',new=readback):
            with self.assertRaises(HTTPError):h.rpc(token,'task_accept_candidate',{'task_id':'demo-b','attempt_id':'attempt-b','candidate_id':self.candidate})
        self.assertEqual(observed,[False]);self.assert_hold_alert('CANDIDATE_BACKUP_COMPLETE_REQUIRED')
        self.assertEqual(h.supervisor._task('demo-b')['state'],'STARTED')

    def test_unbound_oauth_subject_never_reaches_producer_or_outbox(self):
        self.f.identity['principal_id']='unbound-principal'
        before=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaises(ValueError):self.f.call(self.candidate)
            self.assertFalse(readback.called)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],before)
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')

    def test_unknown_model_effects_original_oauth_http_hold(self):
        import threading
        from urllib.error import HTTPError
        from task_center_app import make_server
        import test_task_center_mcp_http as http_fixture
        h=self.f.h
        h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-http-unknown',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-http-unknown'");self.db.commit()
        h.f.server.shutdown();h.f.server.server_close();h.f.thread.join(2)
        h.f.server=make_server(h.f.db,fixture.fx_key(),'tenant-mcp','owner',port=0,model_master_key=h.f.master,
            identity_provider=h.f.identity,session_store=h.f.sessions,outbound_enabled=False,
            external_origin='https://'+http_fixture.HOST,base_path='/task-center-test/',
            mcp_enabled=True,mcp_model_worker_enabled=False,mcp_dispatch_config=self.f.fx.config,handoff_host=self.host)
        h.f.thread=threading.Thread(target=h.f.server.serve_forever);h.f.thread.daemon=True;h.f.thread.start()
        h.f.base='http://127.0.0.1:%d/task-center-test'%h.f.server.server_port
        access=h.token(principal='acceptor')
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaises(HTTPError):h.rpc(access,'task_accept_candidate',{'task_id':'demo-b','attempt_id':'attempt-b','candidate_id':self.candidate})
            self.assertFalse(readback.called)
        self.assert_hold_alert('MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED')
        self.assertEqual(h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.db.execute("SELECT state FROM model_requests WHERE idempotency_key='terminal-http-unknown'").fetchone()[0],'UNKNOWN')

    def test_unsettled_model_hold_is_idempotent_and_does_not_grant_takeover(self):
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-repeat',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-repeat'");self.db.commit()
        for iteration in range(2):
            with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):self.f.call(self.candidate)
            if iteration==0:
                self.db.execute("UPDATE model_requests SET updated_at=updated_at+1 WHERE idempotency_key='terminal-repeat'");self.db.commit()
        rows=self.db.execute("SELECT payload_json FROM events WHERE evidence_ref='CANDIDATE_ACCEPTANCE_EVIDENCE_HOLD'").fetchall()
        selected=[json.loads(row[0]) for row in rows if json.loads(row[0])['reason']=='MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED']
        self.assertEqual(len(selected),1);self.assertFalse(selected[0]['takeover_allowed']);self.assertTrue(selected[0]['requires_effect_reconciliation'])
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_new_unsettled_attempt_is_not_suppressed_as_duplicate(self):
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-new-effect',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN',attempts=1 WHERE idempotency_key='terminal-new-effect'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):self.f.call(self.candidate)
        self.db.execute("UPDATE model_requests SET state='SUCCEEDED',attempts=1 WHERE idempotency_key='terminal-new-effect'");self.db.commit()
        self.db.execute("UPDATE model_requests SET state='UNKNOWN',attempts=2 WHERE idempotency_key='terminal-new-effect'");self.db.commit()
        with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):self.f.call(self.candidate)
        rows=self.db.execute("SELECT e.payload_json,o.delivered_at FROM events e JOIN outbox o ON o.task_id=e.task_id AND o.attempt_id=e.attempt_id AND o.event_id=e.event_id WHERE e.evidence_ref='CANDIDATE_ACCEPTANCE_EVIDENCE_HOLD'").fetchall()
        selected=[row for row in rows if json.loads(row[0])['reason']=='MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED']
        self.assertEqual(len(selected),2);self.assertTrue(all(row[1] is None for row in selected))

    def test_stale_or_unbound_request_cannot_enqueue_unsettled_hold(self):
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-denied',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-denied'");self.db.commit()
        before=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
        with self.assertRaises(ValueError):self.f.call(self.candidate,attempt='wrong')
        self.f.identity['principal_id']='unbound-principal'
        with self.assertRaises(ValueError):self.f.call(self.candidate)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],before)
    def test_unsettled_hold_event_rolls_back_when_outbox_write_fails(self):
        from task_supervisor import Supervisor
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-outbox-error',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-outbox-error'");self.db.commit()
        before=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
        with patch.object(Supervisor,'_enqueue',side_effect=RuntimeError('outbox unavailable')):
            with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):self.f.call(self.candidate)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],before)
        self.assertFalse(self.db.execute("SELECT 1 FROM events WHERE evidence_ref='CANDIDATE_ACCEPTANCE_EVIDENCE_HOLD'").fetchone())
        self.assertEqual(self.db.execute("SELECT state FROM model_requests WHERE idempotency_key='terminal-outbox-error'").fetchone()[0],'UNKNOWN')

    def test_revoked_acceptor_assignment_cannot_enqueue_unsettled_hold(self):
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-revoked-role',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-revoked-role'")
        self.db.execute("UPDATE model_assignments SET state='REVOKED' WHERE task_id='demo-b' AND role_id='acceptor'");self.db.commit()
        before=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
        with self.assertRaises(ValueError):self.f.call(self.candidate)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],before)

    def test_revoked_writer_cannot_enqueue_unsettled_hold(self):
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-revoked',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-revoked'")
        self.db.execute("UPDATE tasks SET authority_state='REVOKED' WHERE task_id='demo-b'");self.db.commit()
        before=self.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
        with self.assertRaises(ValueError):self.f.call(self.candidate)
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],before)
        self.assertEqual(self.db.execute("SELECT state FROM model_requests WHERE idempotency_key='terminal-revoked'").fetchone()[0],'UNKNOWN')

    def test_unknown_model_effects_hold_and_notify_without_backup_read(self):
        self.f.h.control.queue_request('demo-b','developer',[{'role':'user','content':'local fixture'}],'terminal-unknown',8,'fixture-connection')
        self.db.execute("UPDATE model_requests SET state='UNKNOWN' WHERE idempotency_key='terminal-unknown'");self.db.commit()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaisesRegex(ValueError,'MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED'):self.f.call(self.candidate)
            self.assertFalse(readback.called)
        self.assert_hold_alert('MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED')
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.db.execute("SELECT state FROM model_requests WHERE idempotency_key='terminal-unknown'").fetchone()[0],'UNKNOWN')

    def test_unknown_writer_effects_hold_before_any_backup_read(self):
        now=self.f.h.control.clock()
        self.db.execute('INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)',('fixture-op','demo-b','attempt-b','fixture-event','fake:demo-b','a'*64,'b'*64,'{}','UNKNOWN',now,now));self.db.commit()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as readback:
            with self.assertRaisesRegex(ValueError,'UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED'):self.f.call(self.candidate)
            self.assertFalse(readback.called)
        self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.db.execute("SELECT state FROM writer_operations WHERE operation_id='fixture-op'").fetchone()[0],'UNKNOWN')
        self.assert_hold_alert('UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED')

    def test_source_only_preflight_outside_terminal_transaction_holds_completion(self):
        import fcntl
        from task_center_backup_bridge_v2 import PreparedBackupAssessment
        original=component.BackupComponent._readback;snapshot=PreparedBackupAssessment._snapshot;seen=[];locked=[]
        def readback(obj,*args):
            seen.append(obj.host.host.db.in_transaction);return original(obj,*args)
        def local_snapshot(obj,*args):
            if obj.db.in_transaction:
                with (obj.component.home/'run.lock').open('a') as lock:
                    with self.assertRaises(BlockingIOError):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                locked.append(True)
            return snapshot(obj,*args)
        with patch.object(component.BackupComponent,'_readback',new=readback),patch.object(PreparedBackupAssessment,'_snapshot',new=local_snapshot):
            with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.f.call(self.candidate)
        self.assertEqual(seen,[False]);self.assertEqual(locked,[True]);self.assertEqual(self.f.h.supervisor._task('demo-b')['state'],'STARTED')
        self.assertEqual(self.db.execute("SELECT state FROM delivery_candidates WHERE candidate_id=?",(self.candidate,)).fetchone()[0],'REVIEW_PASSED')
        self.assert_hold_alert('CANDIDATE_BACKUP_COMPLETE_REQUIRED')

if __name__=='__main__':unittest.main()
