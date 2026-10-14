import json, os, pathlib, sqlite3, sys, tempfile, unittest
if 'P2_SOURCE_ROOT' not in os.environ:
    raise unittest.SkipTest('Exact frozen producer fixture absent: integration NOT_RUN')
ROOT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT.parent/'scripts'))
sys.path.insert(0,os.environ['P2_SOURCE_ROOT']+'/stage1')
from owner_feishu_transport import OwnerFeishuTransport
from execution_supervision import ExecutionSupervisor

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/ledger.sqlite';self.now=100;self.calls=[]
        db=sqlite3.connect(self.path);db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,fence INTEGER)');db.execute("INSERT INTO tasks VALUES('T1',4)");db.commit();db.close()
        self.active={'ledger_uuid':'fixture','instance':'fixture','generation':1,'epoch':2,'db_path':self.path}
        owner=self
        class Activation:
            def read(self,require_active=False):return dict(owner.active)
        self.supervisor=ExecutionSupervisor(self.path,lambda:self.now,activation_store=Activation())
        db=self.supervisor._tx();self.key=self.supervisor._event(db,'T1','COMPLETED',{'secret':'NEVER_EXPORT'},destinations=('OWNER',));self.supervisor._commit(db);db.close()
        self.mode='ok'
        self.transport=OwnerFeishuTransport('oc_fixture','a'*64,self.api,self.authorize)
    def authorize(self,claim):
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row
        try:
            row=db.execute('SELECT * FROM supervision_delivery WHERE event_key=? AND destination=?',(claim['event_key'],'OWNER')).fetchone()
            fence=db.execute('SELECT fence FROM tasks').fetchone()[0]
            return (row is not None and row['state']=='SENDING' and self.active['epoch']==claim['authority_epoch'] and fence==claim['authority_fence'] and
                    all(row[k]==claim.get(k) for k in ('claim_token','claim_epoch','claim_attempt','authority_epoch','authority_fence')))
        finally:db.close()
    def api(self,path,body):
        self.calls.append((path,body))
        if self.mode=='lost':raise TimeoutError('credential URL must never be exported')
        if self.mode=='changed':
            db=sqlite3.connect(self.path);db.execute('UPDATE tasks SET fence=99');db.commit();db.close()
        answer={'code':0,'data':{'message_id':'om_fixture','chat_id':body['receive_id'],'msg_type':'text','body':{'content':body['content']}}}
        if self.mode=='wrong_chat':answer['data']['chat_id']='oc_other'
        if self.mode=='wrong_text':answer['data']['body']['content']='{"text":"wrong"}'
        if self.mode=='missing_receipt':answer['data'].pop('message_id')
        if self.mode=='wrong_type':answer['data']['msg_type']='image'
        if self.mode=='missing_type':answer['data'].pop('msg_type')
        if self.mode=='error':answer={'code':999}
        return answer
    def state(self):
        db=sqlite3.connect(self.path)
        try:return db.execute('SELECT state,receipt_id,send_attempts FROM supervision_delivery').fetchone()
        finally:db.close()
    def send(self):return self.supervisor.deliver_once('fixture-worker','OWNER',self.transport)
    def test_actual_existing_outbox_success(self):
        self.assertEqual(self.send(),'om_fixture');self.assertEqual(self.state(),('ACKED','om_fixture',1));self.assertNotIn('NEVER_EXPORT',json.dumps(self.calls))
    def test_send_receipt_equivalent_json_different_bytes_rejected(self):
        for variant in ('spaces', 'unicode', 'trailing', 'duplicate'):
            def api(path, body):
                answer = self.api(path, body)
                value = json.loads(body['content'])
                content = json.dumps(value, ensure_ascii=False, indent=2)
                if variant == 'unicode': content = json.dumps(value, ensure_ascii=True)
                if variant == 'trailing': content = body['content'] + ' '
                if variant == 'duplicate': content = '{"text":"ignored","text":' + json.dumps(value['text'], ensure_ascii=False) + '}'
                self.assertEqual(json.loads(content), value)
                self.assertNotEqual(content, body['content'])
                answer['data']['body']['content'] = content
                return answer
            transport, claim, unused = self.reconciliation_fixture()
            transport.api = api
            with self.assertRaises(RuntimeError):
                transport('OWNER', self.key, 'COMPLETED', {}, claim)

    def test_ack_no_duplicate_on_restart(self):
        self.send();self.supervisor=ExecutionSupervisor(self.path,lambda:self.now)
        self.assertIsNone(self.send());self.assertEqual(len(self.calls),1)
    def test_unknown_send_not_replayed(self):
        self.mode='lost';self.assertEqual(self.send(),'DELIVERY_UNCERTAIN');self.assertEqual(self.state()[0],'SENDING_UNCERTAIN')
        self.now=200;self.assertIsNone(self.send());self.assertEqual(len(self.calls),1)
    def test_uncertain_reconciliation_holds(self):
        self.mode='lost';self.send();self.now=200
        self.assertEqual(self.supervisor.reconcile_delivery(self.key,'OWNER','fixture-reconciler',lambda d,k:'UNKNOWN'),'HELD');self.assertIsNone(self.send())
    def test_bad_receipts_never_ack(self):
        for mode in ('wrong_chat','wrong_text','missing_receipt','wrong_type','missing_type','error'):
            with self.subTest(mode=mode):
                claim={'destination':'OWNER','event_key':'T1:COMPLETED:1','delivery_identity':'T1:COMPLETED:1','authority_fence':4,'authority_epoch':2,'claim_epoch':1,'claim_attempt':1}
                transport=OwnerFeishuTransport('oc_fixture','a'*64,self.api,lambda c:True);self.mode=mode
                with self.assertRaises(RuntimeError):transport('OWNER',claim['event_key'],'COMPLETED',{},claim)
    def test_stale_fence_no_external_call(self):
        db=sqlite3.connect(self.path);db.execute('UPDATE tasks SET fence=99');db.commit();db.close()
        self.assertEqual(self.send(),'DELIVERY_UNCERTAIN');self.assertEqual(self.calls,[])
    def test_fence_changes_after_send_no_false_ack(self):
        self.mode='changed';self.assertEqual(self.send(),'DELIVERY_UNCERTAIN');self.assertEqual(self.state()[0],'SENDING_UNCERTAIN')
    def test_wrong_destination_rejected(self):
        with self.assertRaises(ValueError):self.transport('OTHER','T1:COMPLETED:1','COMPLETED',{}, {})
        self.assertEqual(self.calls,[])
    def test_identity_mismatch_no_send(self):
        with self.assertRaises(ValueError):self.transport('OWNER','T1:COMPLETED:1','COMPLETED',{}, {'event_key':'other'})
        self.assertEqual(self.calls,[])
    def test_unknown_history_never_not_sent(self):
        self.assertEqual(self.transport.reconcile(self.key,'COMPLETED',lambda *a:None),'UNKNOWN')
    def test_no_new_tables_in_delivery(self):
        db=sqlite3.connect(self.path);before=db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall();self.send();after=db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall();db.close();self.assertEqual(before,after)

    def reconciliation_fixture(self, msg_type='text'):
        claim={'destination':'OWNER','event_key':self.key,'delivery_identity':self.key,
               'authority_fence':4,'authority_epoch':2,'claim_epoch':1,'claim_attempt':1}
        transport=OwnerFeishuTransport('oc_fixture','a'*64,self.api,lambda c:True)
        result={'chat_id':'oc_fixture','message_id':'om_fixture',
                'content':transport._body(self.key,'COMPLETED')}
        if msg_type is not None:result['msg_type']=msg_type
        return transport,claim,result
    def test_reconcile_matching_text_receipt(self):
        transport,claim,result=self.reconciliation_fixture()
        self.assertEqual(transport.reconcile(self.key,'COMPLETED',lambda *a:result,claim),'om_fixture')
        self.assertEqual(self.calls,[])
    def test_reconcile_wrong_message_type(self):
        transport,claim,result=self.reconciliation_fixture('image')
        self.assertEqual(transport.reconcile(self.key,'COMPLETED',lambda *a:result,claim),'UNKNOWN')
        self.assertEqual(self.calls,[])
    def test_reconcile_missing_message_type(self):
        transport,claim,result=self.reconciliation_fixture(None)
        self.assertEqual(transport.reconcile(self.key,'COMPLETED',lambda *a:result,claim),'UNKNOWN')
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()

