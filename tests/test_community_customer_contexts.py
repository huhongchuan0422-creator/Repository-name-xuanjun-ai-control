"""Isolated real Center tests; all identities/merchants are synthetic fixtures."""
import unittest
import test_community_mini_center_identity as fixtures

class CustomerContexts(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.ExistingCenterComposition();self.fx.setUp()
        self.token=self.fx.token()
    def tearDown(self):self.fx.tearDown()
    def call(self,params=None,scene=''):
        return self.fx.gateway.dispatch(self.token,dict(scene=scene,operation='customer.contexts',params={} if params is None else params))
    def test_only_existing_public_fields_no_new_tables_or_writes(self):
        before=self.fx.center.db.total_changes
        result=self.call();row=result['contexts'][0]
        self.assertEqual(row['scene'],'shop1')
        self.assertEqual(row['merchant'],dict(name='Demo Merchant A',description='Simulated storefront, not a real merchant'))
        self.assertIsNone(row['category']);self.assertIsNone(row['storefront_photo'])
        self.assertEqual(row['public_assets_state'],'NOT_CONNECTED')
        self.assertNotIn('contact',row['merchant']);self.assertNotIn('project',row)
        self.assertEqual(before,self.fx.center.db.total_changes)
    def test_revoke_project_hides_context_not_permission_bypass(self):
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        self.assertEqual(self.call()['contexts'],[])
    def test_revoked_provider_or_session_denied(self):
        self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI'")
        with self.assertRaises(PermissionError):self.call()
    def test_paused_store_keeps_authorized_order_context_without_listing(self):
        self.fx.stage.api.demo.merchant_db.execute("UPDATE merchant_profiles SET status='PAUSED'")
        row=self.call()['contexts'][0]
        self.assertIsNone(row['merchant']);self.assertEqual(row['storefront_state'],'UNAVAILABLE')
    def test_cursor_and_fields_no_client_authority(self):
        for params in ({'tenant':'tenant2'},{'after_scene':None},{'after_scene':'../../x'}):
            with self.assertRaises(ValueError):self.call(params)
        self.assertEqual(self.call({'after_scene':'shop1'})['contexts'],[])
        with self.assertRaises(ValueError):self.call(scene='shop1')
        with self.assertRaises(ValueError):self.fx.gateway.dispatch(self.token,dict(scene='',operation='commerce.orders',params={'after_id':''}))
    def add_private_scenes(self, count=151):
        from scripts.community_saas_phase2 import Principal
        foreign = Principal('tenant2', 'CUSTOMER')
        self.fx.stage.api.bindings[foreign] = dict(tenant_id='tenant2',merchant_id='foreign',store_id='foreign')
        for n in range(count):
            # Half lack project/session authority; half have a cross-tenant
            # principal against project1, rejected by the original resolver.
            self.fx.identity.scenes['private%03d'%n] = dict(
                project='private_project' if n % 2 else 'project1',
                principal=foreign)
    def test_only_private_scenes_never_leak_names_or_more(self):
        self.add_private_scenes()
        self.fx.identity.scenes.pop('shop1')
        result=self.call()
        self.assertEqual(result['contexts'],[])
        self.assertFalse(result['has_more']);self.assertIsNone(result['next_cursor'])
        self.assertNotIn('private',str(result));self.assertNotIn('tenant2',str(result))
    def test_many_private_scenes_do_not_starve_authorized_page(self):
        self.add_private_scenes()
        result=self.call()
        self.assertEqual([r['scene'] for r in result['contexts']],['shop1'])
        self.assertFalse(result['has_more']);self.assertIsNone(result['next_cursor'])
        self.assertNotIn('private',str(result))
    def test_pagination_cursor_only_authorized_and_rechecked_next_page(self):
        self.add_private_scenes()
        self.fx.identity.scenes.pop('shop1')
        for n in range(51):
            self.fx.identity.scenes['visible%03d'%n]=dict(project='project1',principal=self.fx.stage.customer)
        first=self.call()
        self.assertEqual(len(first['contexts']),50);self.assertTrue(first['has_more'])
        self.assertEqual(first['next_cursor'],'visible049')
        second=self.call({'after_scene':first['next_cursor']})
        self.assertEqual([r['scene'] for r in second['contexts']],['visible050'])
        self.assertFalse(second['has_more']);self.assertIsNone(second['next_cursor'])
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        revoked=self.call({'after_scene':first['next_cursor']})
        self.assertEqual(revoked['contexts'],[]);self.assertFalse(revoked['has_more']);self.assertIsNone(revoked['next_cursor'])
    def test_expired_session_is_not_empty_success(self):
        self.fx.identity.revoke(self.token,self.fx.center.now())
        with self.assertRaises(PermissionError):self.call()

if __name__=='__main__':unittest.main()
