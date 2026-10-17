"""Real RSA/AES and original SQLite; provider network is a synthetic fixture."""
import json
import sqlite3
import concurrent.futures
import unittest
from unittest.mock import Mock,patch
import test_community_saas_provider_evidence as evidence_fixture
from cryptography.hazmat.primitives import serialization
from scripts.community_wechat_sp_readonly import PartnerOrderReader,ReadOnlyUnknown
from scripts.community_saas_reconciliation import reconcile
from scripts.community_saas_order_preparation import status
from scripts.community_saas_offline_handoff import change_review
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_phase2 import OfflineSaas


class SignedObservationReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):evidence_fixture.FrozenClaimEvidence.setUpClass()
    def setUp(self):
        self.fx=evidence_fixture.FrozenClaimEvidence();self.fx.setUp()
        self.crypto=self.fx.crypto
        private=self.crypto.key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        self.reader=PartnerOrderReader(self.crypto.order['sp_mchid'],'ABC',private,
            self.crypto.kid,self.crypto.pub,lambda:self.fx.fx.now)
        self.reader._fetch=Mock(return_value=self.query())
        self.body=self.fx.event();self.headers=self.crypto.signed(self.body)
    def tearDown(self):self.fx.tearDown()
    def query(self,changes=None):
        data={k:self.crypto.order[k] for k in ('sp_mchid','sub_mchid','sp_appid','out_trade_no')}
        data.update(amount={'total':1000,'currency':'CNY'},trade_state='SUCCESS',transaction_id='1234567890123')
        data.update(changes or {});raw=json.dumps(data).encode()
        return self.crypto.signed(raw),raw
    def run_match(self,principal=None):
        return reconcile(self.fx.inbox,self.reader,principal or self.fx.fx.owner,
            'ord1',self.headers,self.body)
    def count(self):return self.fx.fx.s.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0]
    def test_match_persists_pending_original_review_without_settlement(self):
        before=status(self.fx.fx.s,'ord1','tenant1');result=self.run_match()
        self.assertEqual(result['provider_observations'],'SIGNED_SUCCESS_MATCH')
        self.assertFalse(result['finance_write']);self.assertFalse(result['payment_settled'])
        self.assertFalse(result['entitlement_granted']);self.assertEqual(result['state'],'PENDING')
        self.assertEqual(status(self.fx.fx.s,'ord1','tenant1'),before)
        self.assertEqual(self.count(),2);self.reader._fetch.assert_called_once()
    def test_repeat_preserves_original_created_time_and_resolved_state(self):
        first=self.run_match();self.fx.fx.now+=1
        change_review(self.fx.fx.s,first['task_id'],'tenant1','resolve_match','RESOLVED',self.fx.fx.now)
        second=self.run_match()
        self.assertTrue(second['duplicate']);self.assertEqual(second['state'],'RESOLVED')
        self.assertEqual(first['task_id'],second['task_id']);self.assertEqual(self.count(),2)
    def test_different_transaction_or_non_success_cannot_create_match(self):
        for changes in ({'transaction_id':'99999'},{'trade_state':'REFUND'},{'trade_state':'NOTPAY'}):
            self.reader._fetch.return_value=self.query(changes)
            with self.assertRaises(ValueError):self.run_match()
        self.assertEqual(self.count(),0)
    def test_wrong_amount_or_tampered_query_is_unknown_without_retry(self):
        for response in (self.query({'amount':{'total':999,'currency':'CNY'}}),
                         (self.query()[0],self.query()[1]+b' ')):
            self.reader._fetch=Mock(return_value=response)
            with self.assertRaises(ReadOnlyUnknown):self.run_match()
            self.reader._fetch.assert_called_once()
        self.assertEqual(self.count(),0)
    def test_invalid_notification_and_customer_denied_before_query(self):
        with self.assertRaises(PermissionError):self.run_match(self.fx.fx.customer)
        self.body+=b' '
        with self.assertRaises(ValueError):self.run_match()
        self.reader._fetch.assert_not_called();self.assertEqual(self.count(),0)
    def test_provider_timeout_has_no_task_or_automatic_retry(self):
        self.reader._fetch.side_effect=TimeoutError('fixture')
        with self.assertRaises(ReadOnlyUnknown):self.run_match()
        self.reader._fetch.assert_called_once();self.assertEqual(self.count(),0)
    def test_binding_changed_during_query_denied(self):
        def fetch(request):
            self.fx.inbox.orders[('tenant1','ord1')]['out_trade_no']='changed'
            return self.query()
        self.reader._fetch.side_effect=fetch
        with self.assertRaisesRegex(PermissionError,'BINDING_CHANGED'):self.run_match()
        self.assertEqual(self.count(),0)
    def test_notification_expires_during_query_denied(self):
        def fetch(request):
            self.fx.fx.now+=301
            raw=self.query()[1]
            return self.crypto.signed(raw,stamp=self.fx.fx.now),raw
        self.reader._fetch.side_effect=fetch
        with self.assertRaisesRegex(ValueError,'SIGNATURE_TIME_WINDOW'):self.run_match()
        self.assertEqual(self.count(),0)
    def test_event_collision_with_existing_notification_cannot_create_match(self):
        self.fx.receive()
        self.body=self.fx.event({'transaction_id':'99999'})
        self.headers=self.crypto.signed(self.body)
        self.reader._fetch.return_value=self.query({'transaction_id':'99999'})
        with self.assertRaisesRegex(ValueError,'PROVIDER_EVENT_COLLISION'):self.run_match()
        self.assertEqual(self.count(),1)
    def test_interrupted_match_keeps_candidate_and_explicit_retry_finishes(self):
        with patch('scripts.community_saas_reconciliation.create_review',side_effect=sqlite3.OperationalError('fixture interruption')):
            with self.assertRaises(sqlite3.OperationalError):self.run_match()
        self.assertEqual(self.count(),1)
        result=self.run_match()
        self.assertFalse(result['duplicate']);self.assertEqual(self.count(),2)
        self.assertEqual(status(self.fx.fx.s,'ord1','tenant1')['state'],'PREPARED')
    def test_concurrent_connections_and_reopen_keep_one_matching_task(self):
        stage=self.fx.fx;path=stage.tmp.name+'/reconcile.sqlite'
        target=sqlite3.connect(path);stage.s.backup(target);target.close()
        def worker():
            db=sqlite3.connect(path,timeout=5)
            try:
                runtime=StageRuntime(stage.demo,OfflineSaas(stage.q,db,stage.q),stage.api.bindings,lambda:stage.now)
                inbox=self.fx.make(runtime)
                return reconcile(inbox,self.reader,stage.owner,'ord1',self.headers,self.body)
            finally:db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(worker()['duplicate'])
        db=sqlite3.connect(path)
        try:
            self.assertEqual(db.execute('SELECT count(*) FROM saas_review_tasks').fetchone()[0],2)
            self.assertEqual(status(db,'ord1','tenant1')['state'],'PREPARED')
        finally:db.close()

if __name__=='__main__':unittest.main()
