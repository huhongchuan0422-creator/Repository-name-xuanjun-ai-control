"""Protected config revocation on a live isolated host; no real provider."""
import copy, http.client, json, os, sqlite3, threading, unittest
from unittest.mock import patch
import test_handoff_backup_configured_consumer_delta as fixture
import backup_component_hostcycle as component
from task_center_backup_v1_migration import build_v1_host
from task_center_handoff_host import FormalHandoffIdentityProvider
from task_center_handoff_ledger import HandoffLedgerBridge
from task_center_session_auth import SessionStore
from task_center_app import make_server

class ConfigRevocationDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ConfiguredConsumerDelta();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.host=build_v1_host(self.f.original,str(self.f.config));self.db=self.f.db
    def record(self):return self.host.record('alice',copy.deepcopy(self.f.f.req))
    def receipt(self):return self.host.read_receipt('bob','task-1','attempt-1',self.f.f.req['event_id'])
    def disabled(self):self.f.write({'schema_version':1,'enabled':False,'policies':[]})
    def test_old_host_honors_disable_and_recovers_original_configuration(self):
        self.assertEqual(self.record()['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertNotIn('SOURCE',self.receipt()['missing'])
        self.disabled()
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
            self.assertEqual(self.record()['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertFalse(read.called)
        receipt=self.receipt();self.assertEqual(receipt['backup_state'],'UNKNOWN')
        self.assertEqual([h['backup_state'] for h in receipt['history']],['INCOMPLETE','UNKNOWN'])
        self.f.write(self.f.doc)
        self.assertEqual(self.record()['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED');self.assertNotIn('SOURCE',self.receipt()['missing'])
        self.assertEqual([h['backup_state'] for h in self.receipt()['history']],['INCOMPLETE','UNKNOWN','INCOMPLETE'])
    def test_config_file_replaced_during_read_is_unknown_then_recovers(self):
        original=os.read;seen=[]
        def replace(fd,count):
            data=original(fd,count)
            if data and not seen:
                seen.append(True);temporary=self.f.f.root/'race-config.json'
                temporary.write_text(json.dumps(self.f.doc));temporary.chmod(0o600)
                os.replace(str(temporary),str(self.f.config))
            return data
        with patch('os.read',side_effect=replace),patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
            self.record();self.assertFalse(read.called)
        self.assertEqual(seen,[True]);self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
        self.record();self.assertNotIn('SOURCE',self.receipt()['missing'])

    def test_wrong_mode_and_missing_file_do_not_call_producer(self):
        for mutate in ('mode','missing'):
            if mutate=='mode':self.f.config.chmod(0o644)
            else:self.f.config.unlink()
            with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
                self.record();self.assertFalse(read.called)
            self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
            self.f.write(self.f.doc)
    def test_changed_enabled_policy_is_not_silently_adopted(self):
        changed=copy.deepcopy(self.f.doc);changed['policies'][0]['resources']['repo'][0]['relative_path']='other.py';self.f.write(changed)
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
            self.record();self.assertFalse(read.called)
        self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
        self.f.write(self.f.doc);self.record();self.assertNotIn('SOURCE',self.receipt()['missing'])
    def test_replaced_legacy_consumer_is_not_used(self):
        original=self.f.delegate.assess_backup;self.f.delegate.assess_backup=lambda binding:None
        try:
            with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
                self.record();self.assertFalse(read.called)
            self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
        finally:self.f.delegate.assess_backup=original
        self.record();self.assertNotIn('SOURCE',self.receipt()['missing'])

    def test_disabled_after_preparation_before_readback(self):
        from task_center_backup_bridge_v2 import PreparedBackupAssessment
        original=PreparedBackupAssessment.execute
        def change(obj,*args):self.disabled();return original(obj,*args)
        with patch.object(PreparedBackupAssessment,'execute',new=change),patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
            self.record();self.assertFalse(read.called)
        self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
    def test_replacement_after_remote_readback_is_rechecked_in_transaction(self):
        original=component.BackupComponent._readback;observed=[]
        def replace(obj,*args):
            result=original(obj,*args);temporary=self.f.f.root/'replacement.json'
            temporary.write_text(json.dumps(self.f.doc));temporary.chmod(0o600);os.replace(str(temporary),str(self.f.config))
            observed.append(obj.host.host.db.in_transaction);return result
        with patch.object(component.BackupComponent,'_readback',new=replace):self.record()
        self.assertEqual(observed,[False]);self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
        # Same verified content can recover on a fresh request, without rebuilding host.
        self.record();self.assertNotIn('SOURCE',self.receipt()['missing'])
    def test_disable_after_transactional_assessment_before_record_is_unknown(self):
        from task_center_backup_bridge_v2 import PreparedBackupAssessment
        original=PreparedBackupAssessment.__call__;observed=[]
        def revoke(obj,binding):
            result=original(obj,binding);observed.append(result['state']);self.disabled();return result
        with patch.object(PreparedBackupAssessment,'__call__',new=revoke):self.record()
        self.assertEqual(observed,['INCOMPLETE']);self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')

    def test_disable_after_outbox_insert_rolls_back_and_reauths_unknown(self):
        from task_supervisor import Supervisor
        original=Supervisor._enqueue;calls=[]
        def revoke(obj,*args):
            result=original(obj,*args);calls.append(True)
            if len(calls)==1:self.disabled()
            return result
        with patch.object(Supervisor,'_enqueue',new=revoke):result=self.record()
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(len(calls),2)
        receipt=self.receipt();self.assertEqual(receipt['backup_state'],'UNKNOWN')
        self.assertEqual([h['backup_state'] for h in receipt['history']],['UNKNOWN'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        self.assertIsNone(self.db.execute('SELECT delivered_at FROM outbox').fetchone()[0])

    def test_mid_readback_disable_and_read_failure_are_unknown(self):
        original=component.BackupComponent._readback
        def revoke(obj,*args):
            result=original(obj,*args);self.disabled();return result
        with patch.object(component.BackupComponent,'_readback',new=revoke):self.record()
        self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
        self.f.write(self.f.doc)
        with patch('task_center_backup_v1_migration._read_stable_owned_config',side_effect=OSError('private detail')):
            self.record()
        self.assertEqual(self.receipt()['backup_state'],'UNKNOWN')
        self.assertNotIn('private detail',json.dumps(self.receipt()))
    def test_original_http_old_host_rechecks_disable_without_rebuild(self):
        def connect():
            db=sqlite3.connect(self.f.f.f.path);db.row_factory=sqlite3.Row;return db
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('tenant_id')=='tenant-1'
        sessions=SessionStore(connect,'tenant-1',ttl_seconds=3600,clock=self.host.clock)
        token,csrf,_=sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        delegate=self.f.delegate;auth=delegate.authenticate_and_authorize
        delegate.authenticate_and_authorize=lambda session,action,binding:auth(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        bridge=HandoffLedgerBridge(self.host,str(self.f.f.root/'journal'),'tenant-ledger','writer')
        server=make_server(self.f.f.f.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,identity_provider=Identity(),session_store=sessions,outbound_enabled=False,handoff_host=self.host,ledger_bridge=bridge)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        def call(method,path,value=None):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':'localhost:%s'%server.server_port,'Cookie':sessions.COOKIE+'='+token,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
            try:
                client.request(method,path,json.dumps(value) if value is not None else None,headers)
                response=client.getresponse();return response.status,json.loads(response.read().decode())
            finally:client.close()
        try:
            status,_=call('POST','/api/admin/handoff-event',self.f.f.req);self.assertEqual(status,200)
            self.disabled()
            with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('must not read')) as read:
                status,_=call('POST','/api/admin/handoff-event',self.f.f.req);self.assertEqual(status,200);self.assertFalse(read.called)
            path='/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id='+self.f.f.req['event_id']
            status,receipt=call('GET',path);self.assertEqual(status,200);self.assertEqual(receipt['backup_state'],'UNKNOWN')
        finally:server.shutdown();thread.join(3);server.server_close()

if __name__=='__main__':unittest.main()
