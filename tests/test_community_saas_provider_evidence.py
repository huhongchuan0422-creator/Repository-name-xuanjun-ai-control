"""Signed synthetic notification -> original frozen SaaS quote/review SQLite."""
import concurrent.futures
import json
import sqlite3
import unittest
import test_community_stage_runtime as stage_fixture
import test_community_wechat_sp_verification as crypto_fixture
import test_stage5_saas_offline_handoff as saas_fixture
from scripts.community_saas_offer_catalog import create_offer,approve_offer,quote
from scripts.community_saas_order_preparation import prepare,status
from scripts.community_saas_phase2 import OfflineSaas,Principal
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_provider_evidence import SaasProviderEvidence

class FrozenClaimEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):crypto_fixture.PublicKeyCandidate.setUpClass()
    def setUp(self):
        self.fx=stage_fixture.RuntimeJourney('test_scope_injection_and_forged_payment_rejected');self.fx.setUp()
        self.crypto=crypto_fixture.PublicKeyCandidate('test_valid_signature_and_decryption_no_money_effect');self.crypto.setUp()
        self.fx.now=self.crypto.now
        create_offer(self.fx.q,'offer1',1,'storefront_catalog','MONTHLY',[saas_fixture.fee()],term_days=30)
        approve_offer(self.fx.q,'offer1',1,'approved1','costref1',10)
        quote(self.fx.q,'q1','tenant1','offer1',1,10,200)
        prepare(self.fx.s,self.fx.q,'ord1','tenant1','q1','CNY',20)
        self.merchant={k:self.crypto.order[k] for k in ('sp_mchid','sub_mchid','sp_appid')}
        self.mapping={('tenant1','ord1'):{'out_trade_no':'provider_order1','cycle':'MONTH'}}
        self.crypto.order['out_trade_no']='provider_order1';self.crypto.order['amount_minor']=1000
        self.inbox=self.make(self.fx.api)
    def tearDown(self):self.fx.tearDown()
    def make(self,runtime,mapping=None):
        return SaasProviderEvidence(runtime,self.merchant,self.mapping if mapping is None else mapping,
            self.crypto.pub,self.crypto.kid,self.crypto.aes)
    def event(self,changes=None):
        return self.crypto.event(dict({'amount':{'total':1000,'currency':'CNY'}},**(changes or {})))
    def receive(self,body=None,principal=None):
        body=self.event() if body is None else body
        return self.inbox.receive(principal or self.fx.owner,'ord1',self.crypto.signed(body),body)
    def test_valid_notification_creates_only_original_pending_finance_review(self):
        before=status(self.fx.s,'ord1','tenant1')
        result=self.receive()
        self.assertEqual(result['state'],'PENDING');self.assertFalse(result['finance_write'])
        self.assertFalse(result['payment_settled']);self.assertFalse(result['entitlement_granted'])
        self.assertEqual(status(self.fx.s,'ord1','tenant1'),before)
        row=self.fx.s.execute('SELECT kind,order_id,tenant_id FROM saas_review_tasks').fetchone()
        self.assertEqual(row,('FINANCE_EVIDENCE','ord1','tenant1'))
    def test_repeat_later_preserves_created_at_and_single_review(self):
        first=self.receive();self.fx.now+=1;second=self.receive()
        self.assertTrue(second['duplicate']);self.assertEqual(first['task_id'],second['task_id'])
        self.assertEqual(self.fx.s.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],1)
    def test_same_event_different_signed_body_is_collision(self):
        self.receive()
        with self.assertRaisesRegex(ValueError,'PROVIDER_EVENT_COLLISION'):
            self.receive(self.event({'transaction_id':'999999999'}))
    def test_bad_signature_or_wrong_amount_creates_no_review(self):
        body=self.event();headers=self.crypto.signed(body)
        with self.assertRaises(ValueError):self.inbox.receive(self.fx.owner,'ord1',headers,body+b' ')
        with self.assertRaises(ValueError):self.receive(self.event({'amount':{'total':999,'currency':'CNY'}}))
        self.assertEqual(self.fx.s.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],0)
    def test_customer_copied_principal_or_unknown_invoice_denied(self):
        for p in (self.fx.customer,Principal('tenant1','PLATFORM_OWNER')):
            with self.assertRaises(PermissionError):self.receive(principal=p)
        body=self.event()
        with self.assertRaises(PermissionError):self.inbox.receive(self.fx.owner,'missing',self.crypto.signed(body),body)
    def test_currency_and_cycle_require_frozen_server_binding(self):
        with self.assertRaises(ValueError):self.make(self.fx.api,{('tenant1','ord1'):{'out_trade_no':'provider_order1','cycle':'YEAR'}})
        prepare(self.fx.s,self.fx.q,'usd_order','tenant1','q1','USD',20)
        with self.assertRaises(ValueError):self.make(self.fx.api,{('tenant1','usd_order'):{'out_trade_no':'provider_usd','cycle':'MONTH'}})
    def test_provider_order_reference_cannot_bind_two_invoices(self):
        quote(self.fx.q,'q2','tenant1','offer1',1,10,200)
        prepare(self.fx.s,self.fx.q,'ord2','tenant1','q2','CNY',20)
        mapping=dict(self.mapping);mapping[('tenant1','ord2')]=dict(mapping[('tenant1','ord1')])
        with self.assertRaisesRegex(ValueError,'REUSED_PROVIDER_ORDER'):self.make(self.fx.api,mapping)
    def test_resolved_review_replay_does_not_reopen_or_settle_order(self):
        from scripts.community_saas_offline_handoff import change_review
        first=self.receive();change_review(self.fx.s,first['task_id'],'tenant1','review_event','RESOLVED',self.fx.now)
        replay=self.receive();self.assertEqual(replay['state'],'RESOLVED');self.assertFalse(replay['payment_settled'])
        self.assertEqual(status(self.fx.s,'ord1','tenant1')['state'],'PREPARED')
    def test_concurrent_connections_and_restart_keep_one_task(self):
        path=self.fx.tmp.name+'/saas-persist.sqlite';target=sqlite3.connect(path)
        self.fx.s.backup(target);target.close();body=self.event();headers=self.crypto.signed(body)
        def worker():
            db=sqlite3.connect(path,timeout=5)
            try:
                runtime=StageRuntime(self.fx.demo,OfflineSaas(self.fx.q,db,self.fx.q),self.fx.api.bindings,lambda:self.fx.now)
                return self.make(runtime).receive(self.fx.owner,'ord1',headers,body)
            finally:db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(worker()['duplicate'])
        db=sqlite3.connect(path)
        try:self.assertEqual(db.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],1)
        finally:db.close()

if __name__=='__main__':unittest.main()
