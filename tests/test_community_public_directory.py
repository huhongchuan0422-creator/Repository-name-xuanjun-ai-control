"""Real isolated approved-opening/source services; synthetic identities/materials only."""
import unittest
import test_community_merchant_opening as fixture
from scripts.community_commerce import Commerce

class PublicDirectory(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.AdmittedMerchantOpening();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.inner=self.fx.fx.fx;self.ops=self.fx.operations
        self.inner.gateway.commerce=Commerce(self.ops,self.inner.identity)
        self.token=self.inner.token();self.app=self.fx.approve()
    def settings(self,op,p):
        w=self.fx.fx.applicant
        return self.ops.dispatch(w['token'],w['csrf'],dict(workspace='merchant',operation='community.public_profile_'+op,params=p))
    def publish(self,version=0,published=True):
        self.fx.db.execute("UPDATE merchant_profiles SET status='ACTIVE'");self.fx.db.commit()
        return self.settings('save',dict(expected_version=version,published=published,category_id='DINING',category_name='餐饮'))
    def directory(self,op='customer.directory',p=None):
        return self.inner.gateway.dispatch(self.token,dict(scene='',operation=op,params=p or {}))
    def test_explicit_publication_and_detail_only_public_fields(self):
        self.assertEqual(self.directory()['records'],[])
        self.publish();r=self.directory()['records'][0]
        self.assertEqual(self.directory()['categories'],[{'id':'DINING','name':'餐饮'}]);self.assertEqual(r['category_id'],'DINING');self.assertIsNone(r['storefront_photo'])
        for field in ('contact','scope','workspace','user_id','application','materials'):self.assertNotIn(field,r)
        self.assertEqual(r,self.directory('customer.store',{'id':r['id']}))
        self.assertEqual(self.directory(p={'category_id':'RETAIL'})['records'],[])
        self.assertEqual(self.directory(p={'after_id':r['id']})['records'],[])
    def test_paused_or_unapproved_cannot_publish(self):
        with self.assertRaises(ValueError):self.settings('save',dict(expected_version=0,published=True,category_id='',category_name=''))
        self.ops.grants['merchant']['onboarding_required']=False
        with self.assertRaises(PermissionError):self.publish()
    def test_revoked_admission_hides_previous_published_store(self):
        self.publish();self.fx.fx.review(self.app,'CORRECTION','fixture correction')
        self.assertEqual(self.directory()['records'],[])
    def test_unpublish_and_version_conflict(self):
        self.publish()
        with self.assertRaises(ValueError):self.publish()
        self.publish(1,False);self.assertEqual(self.directory()['records'],[])
        self.assertEqual(self.settings('read',{})['version'],2)
    def test_paused_live_profile_and_foreign_membership_hide(self):
        self.publish();self.fx.db.execute("UPDATE merchant_profiles SET status='PAUSED'")
        self.assertEqual(self.directory()['records'],[])
        self.fx.db.execute("UPDATE merchant_profiles SET status='ACTIVE'")
        self.inner.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.inner.uid1,))
        self.assertEqual(self.directory()['records'],[])
    def test_non_dict_params_are_uniform_value_error(self):
        for operation in ('customer.directory','customer.store'):
            for value in (None,False,1,[], 'x'):
                with self.subTest(operation=operation,value=value):
                    with self.assertRaisesRegex(ValueError,'INVALID_PUBLIC_DIRECTORY_FIELDS'):
                        self.inner.gateway.dispatch(self.token,dict(scene='',operation=operation,params=value))
    def test_no_material_url_or_contact_can_be_supplied(self):
        for field in ('storefront_photo','contact','scope'):
            with self.assertRaises(ValueError):self.settings('save',dict(expected_version=0,published=False,category_id='',category_name='',**{field:'private'}))
        with self.assertRaises(PermissionError):self.directory('customer.store',{'id':'a'*64})
        with self.assertRaises(ValueError):self.directory(p={'tenant':'other'})

if __name__=='__main__':unittest.main()
