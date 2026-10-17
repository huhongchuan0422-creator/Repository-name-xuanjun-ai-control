"""Conditional UI and original private-material contracts; synthetic/offline only."""
from pathlib import Path
import subprocess
import unittest
import test_community_merchant_onboarding as fixture

ROOT=Path(__file__).resolve().parents[1]

class ConditionalMaterialsDOM(unittest.TestCase):
    def test_applicant_conditions_history_and_stale_responses(self):
        subprocess.run(['node',str(ROOT/'tests/community_onboarding_conditional_dom.cjs'),str(ROOT/'demos/community-stage/onboarding.js')],check=True,capture_output=True,text=True)
    def test_reviewer_can_review_historical_optional_materials(self):
        subprocess.run(['node',str(ROOT/'tests/community_onboarding_conditional_dom.cjs'),str(ROOT/'demos/community-stage/onboarding.js'),'/merchant/review'],check=True,capture_output=True,text=True)

class ConditionalMaterialsOriginalBackend(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.MerchantAdmissionJourney();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def test_all_registered_optional_materials_upload_download_and_review(self):
        f=self.fx;app=f.draft()
        kinds=['operator_identity_back']+['ubo_'+str(i)+'_'+side for i in range(1,5) for side in ('front','back')]
        for kind in list(app['required_materials'])+kinds:app=f.upload(app,kind)
        app=f.call('submit',dict(application=app['application'],revision=app['revision']))
        for kind in kinds:
            self.assertEqual(f.call('download',dict(application=app['application'],kind=kind),True)['mime'],'application/pdf')
            app=f.call('review_material',dict(application=app['application'],revision=app['revision'],kind=kind,decision='ACCEPTED',note='Synthetic optional review'),True)
            self.assertEqual(app['materials'][kind]['review'],'ACCEPTED')
        self.assertFalse(app['payment_enabled'])
    def test_optional_documents_still_enforce_reviewer_revocation_and_scanner(self):
        f=self.fx;app=f.draft();f.fx.center.scanner=None
        with self.assertRaises(RuntimeError):f.upload(app,'ubo_4_back')
        f.fx.center.scanner=lambda raw:True;app=f.upload(app,'ubo_4_back')
        with self.assertRaises(PermissionError):f.call('review_material',dict(application=app['application'],revision=app['revision'],kind='ubo_4_back',decision='ACCEPTED',note='Cannot self review'))
        f.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(f.fx.uid2,))
        with self.assertRaises(PermissionError):f.call('download',dict(application=app['application'],kind='ubo_4_back'),True)

if __name__=='__main__':unittest.main()
