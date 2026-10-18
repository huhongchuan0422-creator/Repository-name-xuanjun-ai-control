"""Multi-store writes retain CRM authority, live ACL and original catalog stores."""
import unittest
import test_community_mini_center_identity as fixtures
from scripts.community_center_operations import CenterOperations
from scripts.community_saas_phase2 import Principal
from scripts.community_demo_bootstrap import DEMO_SCOPE

class StoresJourney(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.ExistingCenterComposition();self.fx.setUp()
        self.web=self.fx.center.login('one@example.org','FixturePassword123!')
        self.second=Principal('tenant1','MERCHANT_ADMIN');self.other=Principal('tenant1','MERCHANT_ADMIN')
        self.fx.stage.api.bindings[self.second]=dict(DEMO_SCOPE,store_id='store2')
        self.fx.stage.api.bindings[self.other]=dict(DEMO_SCOPE,merchant_id='foreign',store_id='store3')
        def grant(p):return dict(user_id=self.fx.uid1,project='project1',project_roles=['OWNER'],principal=p)
        self.ops=CenterOperations(self.fx.center,self.fx.stage.api,{'first':grant(self.fx.stage.merchant),'second':grant(self.second),'foreign':grant(self.other)})
    def tearDown(self):self.fx.tearDown()
    def call(self,op,p=None,workspace='first'):
        return self.ops.dispatch(self.web['token'],self.web['csrf'],dict(workspace=workspace,operation='community.'+op,params=p or {}))
    def save(self,version=None):return self.call('store_save',dict(store_workspace='second',expected_version=version,record=dict(name='Store 2',description='Second original store',contact='contact',status='ACTIVE')))
    def test_create_and_edit_original_admitted_store_and_real_catalog(self):
        self.assertIsNone(next(s for s in self.call('stores')['stores'] if s['workspace']=='second')['profile'])
        self.assertEqual(self.save()['version'],1)
        self.call('item',dict(item=dict(id='second_item',name='Second Item',status='ACTIVE',sort=1)),workspace='second')
        row=self.fx.stage.m.execute("SELECT store_id,name FROM catalog_items WHERE item_id='second_item'").fetchone()
        self.assertEqual(row,('store2','Second Item'))
        self.assertEqual(self.save(1)['version'],2)
        with self.assertRaises(ValueError):self.save(1)
    def test_foreign_merchant_destination_and_client_scope_injection_rejected(self):
        self.assertNotIn('foreign',[s['workspace'] for s in self.call('stores')['stores']])
        args=dict(store_workspace='foreign',expected_version=None,record=dict(name='x',description='x',contact='x',status='ACTIVE'))
        with self.assertRaises(PermissionError):self.call('store_save',args)
        with self.assertRaises(ValueError):self.call('store_save',dict(args,merchant_id='foreign'))
    def test_original_acl_revocation_blocks_new_store_and_catalog_writes(self):
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.save()
        with self.assertRaises(PermissionError):self.call('item',dict(item=dict(id='bad',name='bad',status='ACTIVE',sort=0)),workspace='second')

    def test_entry_editor_cannot_borrow_target_owner_role_for_store_creation_or_listing(self):
        self.ops.grants['first']['project_roles']=('EDITOR',)
        self.fx.center.db.execute("UPDATE members SET role='EDITOR' WHERE user_id=?",(self.fx.uid1,))
        self.assertEqual([s['workspace'] for s in self.call('stores')['stores']],['first'])
        with self.assertRaisesRegex(PermissionError,'PROJECT_PERMISSION_REQUIRED'):self.save()
        self.assertIsNone(self.fx.stage.m.execute("SELECT 1 FROM merchant_profiles WHERE store_id='store2'").fetchone())

    def test_target_role_downgrade_denies_existing_profile_update_without_hiding_allowed_store(self):
        self.save()
        self.ops.grants['first']['project_roles']=('OWNER','EDITOR')
        self.fx.center.db.execute("UPDATE members SET role='EDITOR' WHERE user_id=?",(self.fx.uid1,))
        with self.assertRaisesRegex(PermissionError,'PROJECT_PERMISSION_REQUIRED'):self.save(1)
        self.assertEqual(self.fx.stage.m.execute("SELECT version FROM merchant_profiles WHERE store_id='store2'").fetchone()[0],1)
        self.assertEqual([s['workspace'] for s in self.call('stores')['stores']],['first'])
        self.fx.center.db.execute("UPDATE members SET role='OWNER' WHERE user_id=?",(self.fx.uid1,))
        self.assertEqual(self.save(1)['version'],2)

    def test_changed_target_binding_is_excluded_from_list_and_cannot_be_written(self):
        self.fx.stage.api.bindings[self.second]=dict(DEMO_SCOPE,store_id='changed')
        self.assertNotIn('second',[s['workspace'] for s in self.call('stores')['stores']])
        with self.assertRaises(PermissionError):self.save()
