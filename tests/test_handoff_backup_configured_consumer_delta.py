"""Protected configuration into existing HTTP consumer, isolated fixtures only."""
import copy, http.client, json, os, sqlite3, threading, unittest
from unittest.mock import patch
import test_host_main_checkpoint as prior
import backup_component_hostcycle as component
from task_center_backup_v1_migration import build_v1_host, V1PreparedHostAdapter
from task_center_handoff_host import FormalHandoffIdentityProvider
from task_center_handoff_ledger import HandoffLedgerBridge
from task_center_session_auth import SessionStore
from task_center_app import make_server

class ConfiguredConsumerDelta(unittest.TestCase):
    def setUp(self):
        self.f=prior.MainCheckpoint();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.original=self.f.f.host;self.delegate=self.f.f.auth;self.db=self.f.f.db
        self.config=self.f.root/'inventory.json'
        contract=self.original.role_contract.resolve('tenant-1','task-1','attempt-1','fixture-only')
        self.doc={'schema_version':1,'enabled':True,'policies':[{'tenant_id':'tenant-1','task_id':'task-1','attempt_id':'attempt-1','provider_ref':'fixture-only','contract_sha256':contract['contract_sha256'],'resources':{'repo':[{'category':'SOURCE','root':str(self.f.source),'relative_path':'demo.py'}]}}]}
        self.write(self.doc)
    def write(self,value):
        self.config.write_text(json.dumps(value));self.config.chmod(0o600)
    def test_owner_config_through_original_threaded_http_consumer(self):
        old_adapter=self.original.adapter;configured=build_v1_host(self.original,str(self.config))
        self.assertIsNot(configured,self.original);self.assertIs(self.original.adapter,old_adapter)
        self.assertIsInstance(configured.adapter,V1PreparedHostAdapter)
        def connect():
            db=sqlite3.connect(self.f.f.path);db.row_factory=sqlite3.Row;return db
        class Identity(FormalHandoffIdentityProvider):
            def is_formal_session(self,session):return session.get('tenant_id')=='tenant-1'
        sessions=SessionStore(connect,'tenant-1',ttl_seconds=3600,clock=configured.clock)
        token,csrf,_=sessions.create({'tenant_id':'tenant-1','principal_id':'alice','roles':['TASK_CENTER_ADMIN']})
        auth=self.delegate.authenticate_and_authorize
        self.delegate.authenticate_and_authorize=lambda session,action,binding:auth(session['principal_id'] if isinstance(session,dict) else session,action,binding)
        bridge=HandoffLedgerBridge(configured,str(self.f.root/'journal'),'tenant-ledger','writer')
        server=make_server(self.f.f.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',port=0,
             identity_provider=Identity(),session_store=sessions,outbound_enabled=False,handoff_host=configured,ledger_bridge=bridge)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        original_prepare=V1PreparedHostAdapter.prepare_backup_assessment;original_read=component.BackupComponent._readback
        seen=[];read=[]
        def prepare(adapter,host):
            seen.append((threading.current_thread() is not threading.main_thread(),host.db is not self.db,host.db.in_transaction))
            return original_prepare(adapter,host)
        def readback(obj,*args):
            read.append((threading.current_thread() is not threading.main_thread(),obj.host.host.db.in_transaction))
            return original_read(obj,*args)
        def call(method,path,value=None):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':'localhost:%s'%server.server_port,'Cookie':sessions.COOKIE+'='+token,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
            try:
                client.request(method,path,json.dumps(value) if value is not None else None,headers)
                response=client.getresponse();return response.status,json.loads(response.read().decode())
            finally:client.close()
        try:
            with patch.object(V1PreparedHostAdapter,'prepare_backup_assessment',new=prepare),patch.object(component.BackupComponent,'_readback',new=readback):
                status,result=call('POST','/api/admin/handoff-event',self.f.req)
            self.assertEqual(status,200);self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
            self.assertEqual(seen,[(True,True,False)]);self.assertEqual(read,[(True,False)])
            status,receipt=call('GET','/api/admin/handoff-event?task_id=task-1&attempt_id=attempt-1&event_id='+self.f.req['event_id'])
            self.assertEqual(status,200);self.assertEqual(receipt['backup_state'],'INCOMPLETE')
            self.assertNotIn('SOURCE',receipt['missing']);self.assertIn('CREDENTIAL_RECOVERY',receipt['missing'])
            self.assertEqual(receipt['alert_delivery'],'UNKNOWN')
        finally:server.shutdown();thread.join(3);server.server_close()
    def test_unconfigured_and_disabled_keep_unknown(self):
        self.assertIs(build_v1_host(self.original,None),self.original)
        self.write({'schema_version':1,'enabled':False,'policies':[]})
        self.assertIs(build_v1_host(self.original,str(self.config)),self.original)
        with patch.object(type(self.f.bridge),'__call__',side_effect=AssertionError('old transaction callback forbidden')):
            result=self.original.record('alice',copy.deepcopy(self.f.req))
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(self.original.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')
    def test_untrusted_file_mode_symlink_and_malformed_config_rejected(self):
        self.config.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'BACKUP_INVENTORY_CONFIG_UNAVAILABLE_OR_INVALID'):build_v1_host(self.original,str(self.config))
        self.config.chmod(0o600)
        link=self.f.root/'link.json';link.symlink_to(self.config)
        with self.assertRaisesRegex(ValueError,'BACKUP_INVENTORY_CONFIG_UNAVAILABLE_OR_INVALID'):build_v1_host(self.original,str(link))
        bad=copy.deepcopy(self.doc);bad['policies'][0]['resources']['repo'][0]['relative_path']='../invalid'
        self.write(bad)
        with self.assertRaises(ValueError) as error:build_v1_host(self.original,str(self.config))
        self.assertNotIn(str(self.f.source),str(error.exception))
    def test_wrong_contract_policy_fails_closed_without_readback(self):
        bad=copy.deepcopy(self.doc);bad['policies'][0]['contract_sha256']='0'*64;self.write(bad)
        host=build_v1_host(self.original,str(self.config))
        with patch.object(component.BackupComponent,'_readback',side_effect=AssertionError('unexpected readback')) as read:
            result=host.record('alice',copy.deepcopy(self.f.req));self.assertFalse(read.called)
        self.assertEqual(result['state'],'HANDOFF_INCOMPLETE_ALERT_QUEUED')
        self.assertEqual(host.read_receipt('bob','task-1','attempt-1',self.f.req['event_id'])['backup_state'],'UNKNOWN')

if __name__=='__main__':unittest.main()
