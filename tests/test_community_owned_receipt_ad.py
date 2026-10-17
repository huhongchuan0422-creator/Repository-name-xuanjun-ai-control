"""Original-Center consumer-owned payment-success creative, synthetic provider evidence."""
import unittest
import test_community_reports as fixtures
from scripts.community_order_provider_projection import project_verified_query
from scripts.community_provider_reference import provider_order_reference
from scripts.community_demo_bootstrap import DEMO_SCOPE


class OwnedSuccessAdJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):
        self.fx=fixtures.CommunityReportJourney()
        self.fx.setUp()
        self.fx.basket()
    def tearDown(self):
        self.fx.tearDown()
    def read(self, token=None, **extras):
        return self.fx.commerce.consumer(token or self.fx.token,'shop1','receipt_ad',
                                         dict(reference='basket',**extras))
    def verify_payment(self):
        g,policy=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        expected=dict(sp_mchid=self.fx.reader._mchid,sub_mchid=policy['sub_mchid'],
                      sp_appid=policy['sp_appid'],
                      out_trade_no=provider_order_reference(self.fx.reader._mchid,DEMO_SCOPE,'basket'),
                      amount_minor=101,currency='CNY')
        signed=dict(source='SIGNED_PROVIDER_ORDER_QUERY',
                    signature_key_id=self.fx.reader._kid,
                    out_trade_no=expected['out_trade_no'],
                    amount_minor=101,currency='CNY',provider_state='SUCCESS',
                    transaction_id='420000000000000001',body_sha256='a'*64)
        project_verified_query(self.fx.fx.stage.o,DEMO_SCOPE,'basket',expected,
                               signed,self.fx.c.now(),self.fx.reader._kid)
    def test_pending_and_injected_paid_flag_never_unlock_success_creative(self):
        reply=self.read()
        self.assertIsNone(reply['creative'])
        self.assertFalse(reply['payment_success_verified'])
        with self.assertRaises(ValueError):
            self.read(paid=True)
    def test_exact_owner_can_read_after_signed_provider_projection(self):
        self.verify_payment()
        reply=self.read()
        self.assertTrue(reply['payment_success_verified'])
        self.assertIsNotNone(reply['creative'])
        self.assertEqual(reply['creative']['slot'],'AD_SLOT_PAYMENT_SUCCESS')
        self.assertEqual(reply['finance_status'],'UNCONFIRMED')
    def test_second_member_cannot_read_someone_elses_order_ad(self):
        self.verify_payment()
        second=self.fx.fx.token('another-code','openid2')
        with self.assertRaises(PermissionError):
            self.read(token=second)
    def test_ads_database_failure_does_not_change_paid_evidence(self):
        self.verify_payment()
        self.fx.fx.stage.a.execute('DROP TABLE campaigns')
        reply=self.read()
        self.assertTrue(reply['payment_success_verified'])
        self.assertIsNone(reply['creative'])


if __name__ == '__main__':
    unittest.main()
