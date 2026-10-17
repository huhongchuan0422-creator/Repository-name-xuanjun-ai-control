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
