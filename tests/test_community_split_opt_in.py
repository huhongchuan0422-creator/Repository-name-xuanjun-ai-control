"""Merchant split opt-in tests; no provider network or real payment mutation."""
import base64
import unittest

from scripts.community_merchant_onboarding import MerchantOnboarding
from scripts.community_wechat_sp_actions import ProviderActions
import test_community_mini_center_identity as center_fixture


class _ProtectedPolicies:
    def __init__(self,scope,max_bps=1200):
        self.bindings={tuple(scope[k] for k in ('tenant_id','merchant_id','store_id')):{
            'profit_sharing':True,'max_total_bps':max_bps}}


class SplitOptIn(unittest.TestCase):
    def setUp(self):
        self.fx=center_fixture.ExistingCenterComposition();self.fx.setUp()
        self.applicant=self.fx.center.login('one@example.org','FixturePassword123!')
        self.reviewer=self.fx.center.login('two@example.org','FixturePassword123!')
        self.fx.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.fx.uid2,))
        self.fx.center.scanner=lambda raw:True
        self.service=MerchantOnboarding(self.fx.center,{self.fx.uid2:'project1'})
        self.scope={'tenant_id':'tenant1','merchant_id':'merchant1','store_id':'store1'}
        self.service.provider_actions=_ProtectedPolicies(self.scope)
        self.fields={'legal_name':'Synthetic Merchant','store_name':'Fixture Store','address':'Fixture Address','contact':'Fixture Contact'}
    def tearDown(self):self.fx.tearDown()
    def call(self,op,params,review=False,origin=None):
        web=self.reviewer if review else self.applicant
        return self.service.dispatch(web['token'],web['csrf'],{'operation':op,'params':params},source_origin=origin)
    def draft(self,participates=False,bps=0):
        return self.call('save',{'application':None,'revision':0,'fields':self.fields,'entity_type':'ENTERPRISE','category':'GENERAL','delegated':False,
            'redemption_percent':25,'split_participation':participates,'requested_split_bps':bps},origin={'project':'project1','scene':'shop1','scope':self.scope})
    def submit(self,app):
        for kind in app['required_materials']:
            app=self.call('upload',{'application':app['application'],'revision':app['revision'],'kind':kind,
                'content_base64':base64.b64encode(b'%PDF-synthetic').decode(),'expires_at':None})
        return self.call('submit',{'application':app['application'],'revision':app['revision']})
    def approve(self,app):
        for kind in app['required_materials']:
            app=self.call('review_material',{'application':app['application'],'revision':app['revision'],'kind':kind,
                'decision':'ACCEPTED','note':'checked'},True)
        return self.call('review',{'application':app['application'],'revision':app['revision'],'action':'APPROVE','note':'approved'},True)

    def test_default_is_no_split_and_points_ratio_remains_independent(self):
        app=self.draft()
        self.assertEqual((app['split_participation'],app['requested_split_bps'],app['effective_split_bps']),(False,0,0))
        self.assertEqual(app['redemption_percent'],25)
        approved=self.approve(self.submit(app))
        self.assertEqual((approved['provider_max_split_bps'],approved['effective_split_bps'],approved['approved_redemption_percent']),(1200,0,25))
        self.assertFalse(self.service.split_admission_for_application(app['application'])['participates'])

    def test_requested_ratio_is_bounded_by_protected_wechat_policy(self):
        app=self.draft(True,1200)
        approved=self.approve(self.submit(app))
        self.assertEqual((approved['requested_split_bps'],approved['provider_max_split_bps'],approved['effective_split_bps']),(1200,1200,1200))
        with self.assertRaisesRegex(ValueError,'SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM'):
            self.draft(True,1201)
        # A later configuration reduction still exercises the final approval gate.
        self.service.provider_actions=_ProtectedPolicies(self.scope,1201)
        excessive=self.submit(self.draft(True,1201))
        self.service.provider_actions=_ProtectedPolicies(self.scope,1200)
        for kind in excessive['required_materials']:
            excessive=self.call('review_material',{'application':excessive['application'],'revision':excessive['revision'],'kind':kind,
                'decision':'ACCEPTED','note':'checked'},True)
        with self.assertRaisesRegex(ValueError,'SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM'):
            self.call('review',{'application':excessive['application'],'revision':excessive['revision'],'action':'APPROVE','note':'approved'},True)

    def edit(self,app,**changes):
        params=dict(application=app['application'],revision=app['revision'],fields=self.fields,entity_type='ENTERPRISE',category='GENERAL',delegated=False)
        params.update(changes)
        return self.call('save',params)

    def test_known_cap_rejects_explicit_edit_without_mutating_original(self):
        app=self.draft(True,50)
        with self.assertRaisesRegex(ValueError,'SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM'):
            self.edit(app,split_participation=True,requested_split_bps=1201)
        after=self.call('read',dict(application=app['application']))
        self.assertEqual(after['revision'],app['revision']);self.assertEqual(after['requested_split_bps'],50)
        with self.assertRaises(ValueError):self.edit(app,revision=app['revision']-1,split_participation=True,requested_split_bps=60)
        self.assertEqual(self.call('read',dict(application=app['application']))['requested_split_bps'],50)
        saved=self.edit(app,split_participation=False,requested_split_bps=0)
        self.assertEqual(saved['requested_split_bps'],0);self.assertFalse(saved['split_participation'])

    def test_submit_rechecks_lowered_cap_and_keeps_draft(self):
        app=self.draft(True,50)
        self.service.provider_actions=_ProtectedPolicies(self.scope,49)
        with self.assertRaisesRegex(ValueError,'SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM'):
            self.call('submit',dict(application=app['application'],revision=app['revision']))
        after=self.call('read',dict(application=app['application']))
        self.assertEqual(after['status'],'DRAFT');self.assertEqual(after['revision'],app['revision'])
        self.assertEqual(after['requested_split_bps'],50)

    def test_unknown_cap_keeps_draft_but_cannot_be_approved(self):
        self.service.provider_actions=None
        app=self.draft(True,50)
        self.assertIsNone(app['provider_max_split_bps']);self.assertEqual(app['requested_split_bps'],50)
        submitted=self.submit(app)
        with self.assertRaisesRegex(ValueError,'WECHAT_SPLIT_MAXIMUM_NOT_VERIFIED'):
            self.approve(submitted)
        current=self.call('read',dict(application=app['application']))
        self.assertNotEqual(current['status'],'APPROVED');self.assertEqual(current['effective_split_bps'],0)

    def test_old_ratio_read_and_unrelated_save_do_not_migrate_or_default(self):
        app=self.draft(True,50)
        self.service.provider_actions=_ProtectedPolicies(self.scope,40)
        self.assertEqual(self.call('read',dict(application=app['application']))['requested_split_bps'],50)
        saved=self.edit(app,redemption_percent=10)
        self.assertEqual(saved['requested_split_bps'],50);self.assertEqual(saved['redemption_percent'],10)
        with self.assertRaisesRegex(ValueError,'SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM'):
            self.edit(saved,split_participation=True,requested_split_bps=50)
        zero=self.draft(False,0);self.assertEqual(zero['requested_split_bps'],0)

    def test_profit_sharing_disabled_is_known_zero_not_an_invented_default(self):
        policy=next(iter(self.service.provider_actions.bindings.values()));policy['profit_sharing']=False
        with self.assertRaisesRegex(ValueError,'SPLIT_RATIO_EXCEEDS_WECHAT_APPROVED_MAXIMUM'):self.draft(True,1)
        self.assertEqual(self.draft(False,0)['provider_max_split_bps'],0)

    def test_provider_split_gate_denies_nonparticipant(self):
        actions=ProviderActions.__new__(ProviderActions)
        class Admission:
            def split_admission_for_scope(self,scope):
                return {'participates':False,'effective_bps':0}
        actions.onboarding=Admission()
        with self.assertRaisesRegex(PermissionError,'MERCHANT_DID_NOT_OPT_IN_TO_SPLIT'):
            actions._require_split_admission({'scope':self.scope},{'max_total_bps':1200})

    def test_ui_keeps_split_and_points_controls_separate(self):
        from pathlib import Path
        root=Path(__file__).parents[1]
        html=(root/'demos/community-stage/onboarding.html').read_text()
        js=(root/'demos/community-stage/onboarding.js').read_text()
        for value in ('0','10','20','25','30'):
            self.assertIn('<option value="'+value+'">',html)
        self.assertIn('id="split_participation"',html);self.assertIn('id="requested_split_percent"',html)
        for label in ('分账参与意愿','申请分账比例','微信核定最高比例','最终生效分账比例'):
            self.assertIn(label,js)
        self.assertIn('不与分账比例混用',js)


if __name__=='__main__':unittest.main()
