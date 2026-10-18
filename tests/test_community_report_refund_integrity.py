"""Community monetary reports reuse strict original refund history validation."""
import json
import unittest
from unittest.mock import patch
import test_community_reports as fixtures
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.pr122_customer_core import canonical


class CommunityRefundIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.CommunityReportJourney.setUpClass()

    def setUp(self):
        self.fx=fixtures.CommunityReportJourney();self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.fx.basket()
        self.db=self.fx.fx.stage.demo.db
        self.db.execute("UPDATE orders SET state='SUCCESS' WHERE reference='basket'")
        self.db.commit()

    def report(self):
        # Isolate report arithmetic; payment-signature journeys are inherited.
        with patch('scripts.community_reports.provider_evidence',return_value={'verified_fixture':True}):
            return self.fx.call('community_orders',dict(community_id=self.fx.cid,after_id=''))

    def insert(self,raw):
        identity=tuple(DEMO_SCOPE[k] for k in ('tenant_id','merchant_id','store_id'))
        self.db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',
                        ('refund-fixture',*identity,'basket','SUCCESS','SUCCESS',raw))
        self.db.commit()

    def test_valid_partial_refund(self):
        self.insert(canonical(dict(source='WECHAT_SIGNED_REFUND_RESULT',refund_minor=11)).decode())
        result=self.report()
        self.assertEqual((result['page_gross_minor'],result['page_returns_minor'],result['page_net_minor']),
                         (101,11,90))
        self.assertEqual(result['finance_status'],'UNCONFIRMED')

    def test_overpayment_bound(self):
        self.insert(canonical(dict(source='WECHAT_SIGNED_REFUND_RESULT',refund_minor=102)).decode())
        with self.assertRaisesRegex(ValueError,'COMMUNITY_ORDER_REFUND_TOTAL_CONFLICT'):self.report()


def invalid_amount_case(amount):
    def test(self):
        self.insert(canonical(dict(source='WECHAT_SIGNED_REFUND_RESULT',refund_minor=amount)).decode())
        with self.assertRaisesRegex(ValueError,'INVALID_SIGNED_REFUND_LEDGER_AMOUNT'):self.report()
    return test


def malformed_case(raw):
    def test(self):
        self.insert(raw)
        with self.assertRaisesRegex(ValueError,'UNREADABLE_ORDER_EVIDENCE') as raised:self.report()
        self.assertNotIn('private-invalid-json',str(raised.exception))
    return test


for index,amount in enumerate((True,False,0,-1,1.5,'1',None)):
    setattr(CommunityRefundIntegrity,'test_invalid_amount_'+str(index),invalid_amount_case(amount))
for index,raw in enumerate(('private-invalid-json','[]','null')):
    setattr(CommunityRefundIntegrity,'test_malformed_history_'+str(index),malformed_case(raw))


if __name__=='__main__':unittest.main()
