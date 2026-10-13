import copy
import os
import pathlib
import sqlite3
import sys
import unittest

if 'P2_SOURCE_ROOT' not in os.environ:
    raise unittest.SkipTest('Exact producer absent: integration NOT_RUN')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,os.environ['P2_SOURCE_ROOT']+'/stage1')
from owner_feishu_ledger_endpoint import OwnerFeishuLedgerEndpoint
from owner_feishu_bridge_cycle import run_cycle


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        from test_owner_feishu_claim_guard import ClaimGuardTests
        self.fixture=ClaimGuardTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.active['release_sha256']='a'*64
        with self.fixture.ledger._transaction() as db:
            db.execute("UPDATE supervision_delivery SET state='PENDING',send_attempts=0")
        self.endpoint=OwnerFeishuLedgerEndpoint(self.fixture.ledger)
        self.binding={'chat_id':'oc_fixture','app_id':'cli_fixture','package_sha256':'a'*64}
        self.calls=[];self.pages=[];self.verify=True;self.mode='success'
        owner=self
        class API:
            def verify_private_owner(self,binding):
                if not owner.verify:raise ValueError('fixture private owner rejected')
            def __call__(self,path,body):
                owner.calls.append(body)
                if owner.mode=='timeout':raise TimeoutError('SECRET_MUST_NOT_ESCAPE')
                if owner.mode=='fence':
                    with owner.fixture.ledger._transaction() as db:db.execute('UPDATE tasks SET fence=99')
                return {'code':0,'data':{'message_id':'om_runtime','chat_id':body['receive_id'],
                    'msg_type':'text','body':{'content':body['content']}}}
            def get(self,path):return owner.pages.pop(0)
        self.api=API()

    def state(self):
        with self.fixture.ledger._transaction() as db:
            row=db.execute('SELECT state,receipt_id,send_attempts FROM supervision_delivery').fetchone()
            return tuple(row)

    def cycle(self):return run_cycle(self.endpoint.execute,self.api,self.binding)

    def test_send_exact_receipt_persisted_and_restart_no_duplicate(self):
        self.assertEqual(self.cycle()['state'],'ACKED')
        self.assertEqual(self.state(),('ACKED','om_runtime',1))
        self.endpoint=OwnerFeishuLedgerEndpoint(self.fixture.ledger)
        self.assertEqual(self.cycle()['state'],'IDLE');self.assertEqual(len(self.calls),1)

    def test_private_owner_failure_never_claims_or_sends(self):
        self.verify=False
        with self.assertRaises(ValueError):self.cycle()
        self.assertEqual(self.state(),('PENDING',None,0));self.assertEqual(self.calls,[])

    def test_timeout_not_blindly_replayed(self):
        self.mode='timeout';self.assertEqual(self.cycle()['state'],'SENDING_UNCERTAIN')
        self.assertEqual(self.cycle()['state'],'IDLE');self.assertEqual(len(self.calls),1)

    def test_stale_task_fence_no_send(self):
        with self.fixture.ledger._transaction() as db:db.execute('UPDATE tasks SET fence=99')
        self.assertEqual(self.cycle()['state'],'HELD');self.assertEqual(self.calls,[])

    def test_fence_changes_after_external_send_never_ack(self):
        self.mode='fence'
        with self.assertRaises(ValueError):self.cycle()
        self.assertEqual(self.state(),('SENDING',None,1))

    def test_package_change_rejected_at_atomic_finish(self):
        work=self.endpoint.begin();claim=work['claim']
        self.fixture.active['release_sha256']='b'*64
        with self.assertRaises(ValueError):self.endpoint.execute({'operation':'finish','claim':claim,'status':'ACK','receipt_id':'om_test'})
        self.assertEqual(self.state()[0],'SENDING')

    def test_kind_change_rejected(self):
        claim=self.endpoint.begin()['claim'];claim['event_kind']='OTHER'
        self.assertFalse(self.endpoint.execute({'operation':'guard','claim':claim}))

    def test_current_guard_and_finish_lease_expiry(self):
        claim=self.endpoint.begin()['claim']
        self.assertTrue(self.endpoint.execute({'operation':'guard','claim':claim}))
        self.fixture.now=200
        self.assertFalse(self.endpoint.execute({'operation':'guard','claim':claim}))
        with self.assertRaises(ValueError):self.endpoint.execute({'operation':'finish','claim':claim,'status':'ACK','receipt_id':'om_test'})

    def test_uncertain_complete_history_reread_atomic_ack(self):
        self.mode='timeout';self.cycle();self.fixture.now=200
        item={'message_id':'om_runtime','chat_id':'oc_fixture','msg_type':'text',
              'sender':{'sender_type':'app','id':'cli_fixture','id_type':'app_id'},
              'body':{'content':self.calls[0]['content']}}
        self.pages=[{'code':0,'data':{'items':[item],'has_more':False}},
                    {'code':0,'data':{'items':[item]}}]
        self.assertEqual(self.cycle()['state'],'ACKED')
        self.assertEqual(self.state(),('ACKED','om_runtime',1));self.assertEqual(len(self.calls),1)

    def test_uncertain_absent_history_held_never_retry(self):
        self.mode='timeout';self.cycle();self.fixture.now=200
        self.pages=[{'code':0,'data':{'items':[],'has_more':False}}]
        self.assertEqual(self.cycle()['state'],'HELD');self.assertEqual(self.cycle()['state'],'IDLE')
        self.assertEqual(self.state(),('HELD',None,1));self.assertEqual(len(self.calls),1)

    def test_wrong_reconciliation_owner_rejected(self):
        self.mode='timeout';self.cycle();self.fixture.now=200
        claim=self.endpoint.begin()['claim'];claim['reconciliation_owner']='other'
        self.assertFalse(self.endpoint.execute({'operation':'guard','claim':claim}))

    def test_unsupported_operation_and_retry_proof_rejected(self):
        for request in ({'operation':'sql','query':'SELECT 1'}, {'operation':'begin','receiver':'other'}):
            with self.assertRaises(ValueError):self.endpoint.execute(request)
        claim=self.endpoint.begin()['claim']
        with self.assertRaises(ValueError):self.endpoint.execute({'operation':'finish','claim':claim,'status':'NOT_SENT','receipt_id':None})

    def test_db_clone_rejected_before_claim(self):
        import shutil
        shutil.copyfile(self.fixture.path,self.fixture.path+'.clone')
        os.replace(self.fixture.path+'.clone',self.fixture.path)
        with self.assertRaises(ValueError):self.endpoint.begin()
        self.assertEqual(self.state(),('PENDING',None,0))

    def test_finish_is_bound_to_current_claim_and_receipt_shape(self):
        claim=self.endpoint.begin()['claim']
        for change in ('claim_token','authority_epoch','claim_attempt'):
            altered=dict(claim);altered[change]='wrong'
            with self.assertRaises(ValueError):self.endpoint.execute({'operation':'finish','claim':altered,'status':'ACK','receipt_id':'om_test'})
        with self.assertRaises(ValueError):self.endpoint.execute({'operation':'finish','claim':claim,'status':'ACK','receipt_id':'not_receipt'})

    def test_no_new_state_tables(self):
        with self.fixture.ledger._transaction() as db:before=db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()
        self.cycle()
        with self.fixture.ledger._transaction() as db:after=db.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()
        self.assertEqual([tuple(r) for r in before],[tuple(r) for r in after])
