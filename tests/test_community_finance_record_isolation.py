"""Finance-view regression: corrupt or cross-scope provider records never leak."""
import unittest
import test_community_reports as fixtures
from scripts.pr122_customer_core import canonical


class FinanceRecordIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.CommunityReportJourney.setUpClass()

    def setUp(self):
        self.fx=fixtures.CommunityReportJourney()
        self.fx.setUp()

    def tearDown(self):
        self.fx.tearDown()

    def test_malformed_persisted_provider_action_does_not_leak(self):
        c=self.fx.c
        key='e'*64
        with c.tx():
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",
                (key,self.fx.fx.uid1,'project1',
                 c.encrypt(canonical(dict(kind='REFUND',scope_hash='different')),
                           'provider-action:'+key)))
        result=self.fx.actions.dispatch(self.fx.web['token'],self.fx.web['csrf'],
            dict(workspace='finance',operation='financial_records',
                 params=dict(kind='REFUND',after_id='')))
        self.assertEqual(result['records'],[])
        self.assertEqual(result['finance_status'],'UNCONFIRMED')

    def test_matching_scope_digest_but_foreign_scope_payload_is_not_disclosed(self):
        import hashlib
        c=self.fx.c
        g,_=self.fx.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
        scope_hash=hashlib.sha256(canonical(g['scope'])).hexdigest()
        key='c'*64
        foreign=dict(tenant_id='tenant1',merchant_id='different',store_id='other')
        saved=dict(kind='REFUND',scope_hash=scope_hash,scope=foreign,
                   reference='foreign_reference',request_id='foreign_request',
                   provider_reference='foreign_provider')
        with c.tx():
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",
                (key,self.fx.fx.uid1,'project1',
                 c.encrypt(canonical(saved),'provider-action:'+key)))
        result=self.fx.actions.dispatch(self.fx.web['token'],self.fx.web['csrf'],
            dict(workspace='finance',operation='financial_records',
                 params=dict(kind='REFUND',after_id='')))
        self.assertEqual(result['records'],[])

    def test_unreadable_original_order_evidence_fails_reconciliation_closed(self):
        from scripts.community_financial_views import verified_refund_total
        class DB:
            def execute(self, sql, params):
                return [('not-json',)]
        scope=dict(tenant_id='tenant1',merchant_id='merchant1',store_id='store1')
        with self.assertRaisesRegex(ValueError,'UNREADABLE_ORDER_EVIDENCE_RECONCILIATION_DENIED'):
            verified_refund_total(DB(),scope,'order1')

    def test_malformed_return_scope_skipped(self):
        c=self.fx.c
        key='d'*64
        with c.tx():
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_RETURN',?,?,?,?,1)",
                (key,self.fx.fx.uid1,'project1',
                 c.encrypt(canonical(dict(scope=None)),
                           'community-provider-return:'+key)))
        result=self.fx.actions.dispatch(self.fx.web['token'],self.fx.web['csrf'],
            dict(workspace='finance',operation='financial_records',
                 params=dict(kind='RETURN',after_id='')))
        self.assertEqual(result['records'],[])
        self.assertEqual(result['finance_status'],'UNCONFIRMED')


if __name__=='__main__':
    unittest.main()
