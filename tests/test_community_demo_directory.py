"""All material/account fixtures synthetic; original approval workflow exercised."""
import unittest
import test_community_merchant_opening as fixture
from scripts.community_commerce import Commerce

class DemoDirectory(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.AdmittedMerchantOpening();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.inner=self.fx.fx.fx
        self.inner.gateway.commerce=Commerce(self.fx.operations,self.inner.identity)
        self.token=self.inner.token()
    def call(self,op='customer.directory',params=None):
        return self.inner.gateway.dispatch(self.token,dict(scene='',operation=op,params=params or {}))
    def test_empty_authoritative_source_demo_is_separate_nontransactional_object(self):
        before=self.inner.center.db.total_changes
        r=self.call();d=r['demo'];self.assertEqual(d['state'],'VISIBLE')
        self.assertEqual(r['records'],[]);self.assertEqual(r['categories'],[])
        item=d['record'];self.assertTrue(item['is_demo']);self.assertTrue(item['display_only'])
        self.assertFalse(item['payment_enabled']);self.assertFalse(item['purchasing_enabled']);self.assertFalse(item['include_in_real_statistics'])
        self.assertIsNone(item['storefront_photo']);self.assertEqual(item['photo_asset_id'],'community-demo-storefront-v1')
        self.assertEqual(self.call('customer.store',{'id':item['id']}),item)
        self.assertEqual(before,self.inner.center.db.total_changes)
    def test_first_actual_approval_hides_without_publication_and_never_returns_on_correction(self):
        demo_id=self.call()['demo']['record']['id']
        app=self.fx.approve()
        self.assertEqual(self.call()['demo']['state'],'HIDDEN_REAL_APPROVAL_OBSERVED')
        self.assertEqual(self.call()['records'],[]) # still PAUSED, not published
        self.fx.fx.review(app,'CORRECTION','Synthetic later correction')
        self.assertEqual(self.call()['demo']['state'],'HIDDEN_REAL_APPROVAL_OBSERVED')
        with self.assertRaises(PermissionError):self.call('customer.store',{'id':demo_id})
        self.inner.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_MERCHANT_OPENING'")
        self.assertEqual(self.call(params={'after_id':'f'*64})['demo']['state'],'HIDDEN_REAL_APPROVAL_OBSERVED')
    def test_missing_service_unknown_not_visible(self):
        self.fx.operations.onboarding=None
        self.assertEqual(self.call()['demo'],dict(state='UNKNOWN',record=None))
    def test_missing_approval_event_does_not_resurrect(self):
        self.fx.approve()
        self.inner.center.db.execute("DELETE FROM onboarding_events WHERE event='APPROVE'")
        self.assertEqual(self.call()['demo'],dict(state='HIDDEN_REAL_APPROVAL_OBSERVED',record=None))
    def test_missing_mapping_does_not_resurrect(self):
        self.fx.approve()
        self.inner.center.db.execute("DELETE FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'")
        self.assertEqual(self.call()['demo'],dict(state='HIDDEN_REAL_APPROVAL_OBSERVED',record=None))
    def test_proven_other_project_approval_does_not_hide_current_project_demo(self):
        from unittest.mock import patch
        with patch('scripts.community_demo_directory.retire_on_approval'):
            self.fx.approve() # legacy approval before retirement evidence existed
        c=self.inner.center
        key,app,raw=c.db.execute("SELECT subject_idx,project,payload FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'").fetchone()
        record=self.fx.fx.service._decode(raw,'community-opening:'+key+':'+app)
        record['project']='other_project'
        c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_MERCHANT_OPENING'",(self.fx.fx.service._encode(record,'community-opening:'+key+':'+app),))
        self.assertEqual(self.call()['demo']['state'],'VISIBLE')
    def test_ambiguous_current_project_is_not_guessed(self):
        # A second legitimate authorization needs a selected current-project
        # transport contract; until then this endpoint must not guess one.
        from unittest.mock import patch
        original=self.inner.identity._resolve
        self.inner.identity.scenes['other']=dict(project='project1',principal=self.inner.stage.customer)
        def resolve(token,scene):
            uid,project,p=original(token,scene)
            return uid,('other_project' if scene=='other' else project),p
        with patch.object(self.inner.identity,'_resolve',side_effect=resolve):
            self.assertEqual(self.call()['demo'],dict(state='NOT_CURRENT_PROJECT',record=None))
    def test_marker_and_approval_roll_back_together(self):
        from unittest.mock import patch
        original=self.inner.center.audit
        def audit(project,actor,event,obj):
            if event=='COMMUNITY_DEMO_RETIRED_REAL_APPROVAL':raise RuntimeError('fixture interruption')
            return original(project,actor,event,obj)
        with patch.object(self.inner.center,'audit',side_effect=audit):
            with self.assertRaises(RuntimeError):self.fx.approve()
        self.assertIsNone(self.inner.center.db.execute("SELECT 1 FROM onboarding_events WHERE event='APPROVE'").fetchone())
        self.assertEqual(self.call()['demo']['state'],'VISIBLE')
    def test_legacy_unmapped_approval_is_unknown_not_zero(self):
        from unittest.mock import patch
        with patch('scripts.community_demo_directory.retire_on_approval'):
            self.fx.approve()
        self.inner.center.db.execute("DELETE FROM links WHERE channel='COMMUNITY_MERCHANT_OPENING'")
        self.assertEqual(self.call()['demo'],dict(state='UNKNOWN',record=None))
    def test_forged_demo_and_revoked_customer_denied(self):
        with self.assertRaises(PermissionError):self.call('customer.store',{'id':'demo_'+'0'*64})
        self.inner.identity.revoke(self.token,self.inner.center.now())
        with self.assertRaises(PermissionError):self.call()

if __name__=='__main__':unittest.main()
