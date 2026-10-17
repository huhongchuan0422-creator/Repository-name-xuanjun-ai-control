"""Actual original Center identity/ACL and original SaaS ownership composition."""
import unittest
import test_community_mini_center_identity as fixture
from scripts.community_center_saas import CenterSaas
from scripts.community_saas_offer_catalog import create_offer,approve_offer

class CustomerSaas(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterComposition();self.fx.setUp()
        self.one=self.fx.center.login('one@example.org','FixturePassword123!');self.two=self.fx.center.login('two@example.org','FixturePassword123!')
        self.grants={name:dict(user_id=uid,project='project1',principal=self.fx.stage.customer) for name,uid in [('one',self.fx.uid1),('two',self.fx.uid2)]}
        self.api=CenterSaas(self.fx.center,self.fx.stage.api,self.grants)
        create_offer(self.fx.stage.q,'sku',1,'storefront_catalog','MONTHLY',[dict(type='MODULE_FEE',label='License',cycle='MONTH',quantity=1,cny_minor=1000,usd_minor=200,cost_cny_minor=100,cost_usd_minor=20)],term_days=30)
        approve_offer(self.fx.stage.q,'sku',1,'approval','costref',self.fx.stage.now)
    def tearDown(self):self.fx.tearDown()
    def call(self,op,params=None,other=False):
        web=self.two if other else self.one
        return self.api.dispatch(web['token'],web['csrf'],dict(workspace='two' if other else 'one',operation=op,params=params or {}))
    def quote(self):return self.call('quote',dict(offer_id='sku',version=1))
    def test_existing_account_prices_quote_order_and_repeat_recovery(self):
        q=self.quote();self.assertNotIn('cost_evidence_ref',q);self.assertNotIn('cost_cny_minor',q['lines'][0])
        order=self.call('order_prepare',dict(quote_id=q['quote_id'],currency='CNY'))
        self.assertEqual(order['amounts_by_cycle_minor'],{'MONTH':1000});self.assertFalse(order['entitlement_granted'])
        again=self.call('order_prepare',dict(quote_id=q['quote_id'],currency='CNY'));self.assertEqual(order['order_id'],again['order_id'])
        self.assertEqual(self.call('order_status',dict(order_id=order['order_id']))['state'],'PREPARED')
        self.assertEqual(len(self.call('mine',dict(kind='ORDER',after_id=''))['records']),1)
    def test_same_tenant_second_customer_cannot_read_or_claim_quotes_and_orders(self):
        q=self.quote();o=self.call('order_prepare',dict(quote_id=q['quote_id'],currency='USD'))
        for op,p in [('quote_read',dict(quote_id=q['quote_id'])),('order_prepare',dict(quote_id=q['quote_id'],currency='USD')),('order_read',dict(order_id=o['order_id'])),('order_status',dict(order_id=o['order_id'])),('renewal_plan',dict(order_id=o['order_id'],valid_until=None))]:
            with self.assertRaises(PermissionError):self.call(op,p,True)
        self.assertEqual(self.call('mine',dict(kind='ORDER',after_id=''),True)['records'],[])
        with self.assertRaises(PermissionError):self.call('order_read',dict(order_id='legacy_order'))
    def test_project_revoke_csrf_grant_mutation_and_admin_injection_deny(self):
        with self.assertRaises(PermissionError):self.api.dispatch(self.one['token'],None,dict(workspace='one',operation='catalog',params={}))
        with self.assertRaises(ValueError):self.call('owner_approve_offer',{})
        with self.assertRaises(ValueError):self.call('quote',dict(offer_id='sku',version=1,tenant_id='other'))
        with self.assertRaises(PermissionError):self.api.dispatch(self.two['token'],self.two['csrf'],dict(workspace='one',operation='catalog',params={}))
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.call('catalog')
    def test_owner_pricing_requires_protected_owner_grant_and_original_project_owner(self):
        grants=dict(self.grants,owner=dict(user_id=self.fx.uid1,project='project1',principal=self.fx.stage.owner),bad_owner=dict(user_id=self.fx.uid2,project='project1',principal=self.fx.stage.owner))
        api=CenterSaas(self.fx.center,self.fx.stage.api,grants)
        args=dict(offer_id='newsku',version=1,module_id='storefront_catalog',kind='BUYOUT',lines=[dict(type='MODULE_FEE',label='Buyout',cycle='ONCE',quantity=1,cny_minor=100,usd_minor=20,cost_cny_minor=0,cost_usd_minor=0)],term_days=None,tenant_scope=None,supplier_payment='NONE')
        with self.assertRaises(PermissionError):self.call('owner_create_offer',args)
        with self.assertRaises(PermissionError):api.dispatch(self.two['token'],self.two['csrf'],dict(workspace='bad_owner',operation='owner_create_offer',params=args))
        r=api.dispatch(self.one['token'],self.one['csrf'],dict(workspace='owner',operation='owner_create_offer',params=args));self.assertFalse(r['payment_authorized'])
        api.dispatch(self.one['token'],self.one['csrf'],dict(workspace='owner',operation='owner_approve_offer',params=dict(offer_id='newsku',version=1,approval_ref='approval2',cost_evidence_ref='cost2')))
        self.assertIn('newsku',[o['offer_id'] for o in self.call('offers',dict(module_id='storefront_catalog'))['offers']])
    def test_expired_new_quote_orders_rejected_but_own_records_recover_after_reopen(self):
        q=self.quote();self.fx.stage.now+=1801
        with self.assertRaises(ValueError):self.call('order_prepare',dict(quote_id=q['quote_id'],currency='CNY'))
        self.fx.reopen();self.api=CenterSaas(self.fx.center,self.fx.stage.api,self.grants)
        records=self.call('mine',dict(kind='QUOTE',after_id=''))['records'];self.assertEqual(records[0]['quote_id'],q['quote_id'])
        self.assertEqual(self.call('quote_read',dict(quote_id=q['quote_id']))['quote_id'],q['quote_id'])

if __name__=='__main__':unittest.main()
