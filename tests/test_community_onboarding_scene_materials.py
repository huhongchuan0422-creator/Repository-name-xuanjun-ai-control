"""Real original Center/transactions with synthetic files; no provider network."""
import unittest
from scripts.community_merchant_onboarding import MINI_SCENE,STORE_SCENE,profile_scenes
import test_community_merchant_onboarding as fixture
class SceneMaterials(unittest.TestCase):
    def setUp(self):self.f=fixture.MerchantAdmissionJourney();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def draft(self,scenes):return self.f.draft(sales_scenes_type=scenes)
    def fill(self,app):
        for kind in app['required_materials']:app=self.f.upload(app,kind)
        return app
    def submit(self,app):return self.f.call('submit',dict(application=app['application'],revision=app['revision']))
    def test_pure_mini_approves_without_store_photos_or_settlement_proof(self):
        app=self.draft([MINI_SCENE]);self.assertIn('mini_program_screenshot',app['required_materials'])
        self.assertTrue({'storefront_photo','interior_photo','settlement_proof','operator_authorization'}.isdisjoint(app['required_materials']))
        app=self.f.review(self.submit(self.fill(app)),'APPROVE')
        self.assertEqual(app['status'],'APPROVED');self.assertFalse(app['payment_enabled'])
    def test_store_and_mixed_require_actual_scene_materials(self):
        for scenes in ([STORE_SCENE],[MINI_SCENE,STORE_SCENE]):
            with self.subTest(scenes=scenes):
                app=self.draft(scenes)
                self.assertTrue({'storefront_photo','interior_photo'}<=set(app['required_materials']))
                self.assertEqual('mini_program_screenshot' in app['required_materials'],MINI_SCENE in scenes)
                for kind in app['required_materials']:
                    if kind!='storefront_photo':app=self.f.upload(app,kind)
                with self.assertRaisesRegex(ValueError,'storefront_photo'):self.submit(app)
                app=self.f.upload(app,'storefront_photo');self.assertEqual(self.submit(app)['status'],'SUBMITTED')
    def test_optional_material_can_need_correction_without_blocking_approval(self):
        app=self.fill(self.draft([MINI_SCENE]));app=self.f.upload(app,'settlement_proof');app=self.submit(app)
        app=self.f.call('review_material',dict(application=app['application'],revision=app['revision'],kind='settlement_proof',decision='NEEDS_CORRECTION',note='Synthetic optional evidence'),True)
        app=self.f.review(app,'APPROVE');self.assertEqual(app['status'],'APPROVED')
        self.assertEqual(app['materials']['settlement_proof']['review'],'NEEDS_CORRECTION')
        self.assertEqual(self.f.call('download',dict(application=app['application'],kind='settlement_proof'))['mime'],'application/pdf')
    def test_scene_change_retains_uploaded_objects_and_versions(self):
        app=self.fill(self.draft([STORE_SCENE]));old=app['materials']['storefront_photo']
        app=self.f.draft(app,sales_scenes_type=[MINI_SCENE])
        self.assertNotIn('storefront_photo',app['required_materials']);self.assertEqual(app['materials']['storefront_photo'],old)
        self.assertEqual(self.f.call('download',dict(application=app['application'],kind='storefront_photo'))['mime'],'application/pdf')
        self.assertEqual(self.f.fx.center.db.execute('SELECT count(*) FROM versions WHERE project=? AND item=?',(app['application'],'storefront_photo')).fetchone()[0],1)
    def test_invalid_scene_declarations_never_create_application(self):
        for scenes in ([],[MINI_SCENE,MINI_SCENE],['unknown'],'SALES_SCENES_STORE',[None]):
            with self.subTest(scenes=scenes),self.assertRaises(ValueError):self.draft(scenes)
        self.assertEqual(self.f.call('mine')['applications'],[])
    def test_current_same_application_provider_draft_controls_requirements(self):
        from types import SimpleNamespace
        app=self.draft([STORE_SCENE]);application=app['application']
        service=self.f.service
        service.wechat_applyment=SimpleNamespace(_read=lambda key: {'profile':{'business_info':{'sales_info':{'sales_scenes_type':[MINI_SCENE]}}}} if key==application else None)
        _,meta,_=service._load(application,self.f.fx.uid1)
        required=service._required(meta);self.assertIn('mini_program_screenshot',required);self.assertNotIn('storefront_photo',required)
    def test_delegated_letter_optional_but_actual_document_sides_required(self):
        app=self.f.draft(sales_scenes_type=[MINI_SCENE],delegated=True)
        self.assertNotIn('operator_authorization',app['required_materials'])
        self.assertTrue({'operator_identity','operator_identity_back'}<=set(app['required_materials']))
    def test_partial_profile_has_no_declared_scene_and_unknown_is_rejected(self):
        self.assertIsNone(profile_scenes({'business_info':None}))
        with self.assertRaises(ValueError):profile_scenes({'business_info':{'sales_info':{'sales_scenes_type':['UNKNOWN']}}})
if __name__=='__main__':unittest.main()
