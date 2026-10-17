"""Server-registered staff, moderation and finance-view roles on original stores."""
import unittest
import test_community_stage_runtime as stage_fixture
from scripts.community_saas_phase2 import Principal

class ScopedCommunityRoles(unittest.TestCase):
    def setUp(self):
        self.fx=stage_fixture.RuntimeJourney('test_scope_injection_and_forged_payment_rejected');self.fx.setUp()
        self.staff=self.register('STORE_STAFF');self.reviewer=self.register('PLATFORM_REVIEWER');self.finance=self.register('FINANCE_APPROVER')
    def register(self,role,store='store1'):
        p=Principal('tenant1',role);self.fx.api.bindings[p]=dict(self.fx.api.bindings[self.fx.customer],store_id=store);return p
    def tearDown(self):self.fx.tearDown()
    def call(self,p,op,params=None):return self.fx.api.dispatch(p,'community.'+op,params or {},0)
    def test_staff_reads_only_registered_store_orders(self):
        self.fx.checkout()
        self.assertEqual(len(self.call(self.staff,'orders')['orders']),1)
        other=self.register('STORE_STAFF','store2')
        self.assertEqual(self.call(other,'orders')['orders'],[])
    def test_staff_cannot_edit_ads_or_view_finance(self):
        for op,params in [('ads',{}),('reconciliation',{}),('item',{'item':{}}),
                          ('ad_review',{'campaign_id':'x','approved':True,'expected_version':1})]:
            with self.assertRaises(PermissionError):self.call(self.staff,op,params)
    def test_reviewer_can_moderate_but_not_edit_merchant_or_finance(self):
        self.assertIsInstance(self.call(self.reviewer,'ads'),dict)
        campaign={'id':'review_me','slot':'AD_SLOT_PAYMENT_AMOUNT','starts_at':self.fx.now-5,
                  'ends_at':self.fx.now+100,'title':'Review fixture','target_url':'https://example.org/a','priority':1}
        self.call(self.fx.merchant,'ad_create',{'record':campaign})
        self.call(self.fx.merchant,'ad_state',{'campaign_id':'review_me','state':'REVIEW','expected_version':1})
        self.assertTrue(self.call(self.reviewer,'ad_review',{'campaign_id':'review_me','approved':True,'expected_version':2})['admin_command_executed'])
        for op,params in [('item',{'item':{}}),('reconciliation',{})]:
            with self.assertRaises(PermissionError):self.call(self.reviewer,op,params)
    def test_finance_role_reads_reconciliation_without_administration_or_money(self):
        result=self.call(self.finance,'reconciliation')
        self.assertIsNone(result['provider_settlement_minor'])
        self.assertTrue(result['simulation_only'])
        for op,params in [('ads',{}),('item',{'item':{}}),('refund_record',{'reference':'x','event_id':'e','amount_minor':1})]:
            with self.assertRaises(PermissionError):self.call(self.finance,op,params)
        with self.assertRaises(ValueError):self.call(self.finance,'execute_split')
    def test_community_roles_do_not_inherit_saas_owner_or_customer_operations(self):
        for p in (self.staff,self.reviewer,self.finance):
            with self.assertRaises(PermissionError):self.fx.api.dispatch(p,'catalog',{},0)
    def test_copied_unregistered_role_and_client_actor_fields_are_rejected(self):
        with self.assertRaises(PermissionError):self.call(Principal('tenant1','STORE_STAFF'),'orders')
        with self.assertRaises(ValueError):self.call(self.staff,'orders',{'role':'PLATFORM_OWNER'})

if __name__=='__main__':unittest.main()
