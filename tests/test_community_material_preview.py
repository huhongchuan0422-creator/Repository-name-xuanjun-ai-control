"""Synthetic owner-only retained-image preview; no real materials."""
import base64
import hashlib
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as onboarding_fixture

class MaterialPreview(unittest.TestCase):
    def setUp(self):
        self.fx=onboarding_fixture.MerchantAdmissionJourney();self.fx.setUp()
        self.raw=b'\xff\xd8\xffSYNTHETIC-PRIVATE-IMAGE'
        self.app=self.fx.upload(self.fx.draft(),'business_license',self.raw)
    def tearDown(self):self.fx.tearDown()
    def preview(self,**changes):
        p={'application':self.app['application'],'revision':self.app['revision'],'kind':'business_license'};p.update(changes)
        return self.fx.call('material_preview',p)
    def test_exact_owner_image_binding_and_no_writes(self):
        before=self.fx.fx.center.db.total_changes
        r=self.preview();self.assertEqual(base64.b64decode(r['content_base64']),self.raw)
        self.assertEqual(r['sha256'],hashlib.sha256(self.raw).hexdigest());self.assertEqual(r['revision'],self.app['revision'])
        self.assertEqual(r['cache'],'PRIVATE_TEMPORARY_ONLY');self.assertEqual(self.fx.fx.center.db.total_changes,before)
    def test_reviewer_is_not_owner(self):
        with self.assertRaises(PermissionError):self.fx.call('material_preview',{'application':self.app['application'],'revision':self.app['revision'],'kind':'business_license'},review=True)
    def test_revision_kind_and_generic_bank_proof_rejected(self):
        for changes,code in [({'revision':True},'INVALID_REVISION'),({'kind':'storefront_photo'},'KIND_DENIED')]:
            with self.subTest(changes=changes),self.assertRaisesRegex((ValueError,PermissionError),code):self.preview(**changes)
    def test_source_or_unclassified_bank_returns_safe_no_content_state(self):
        self.assertEqual(self.preview(revision=0),{'status':'UNAVAILABLE','reason':'MATERIAL_PREVIEW_SOURCE_CHANGED'})
        self.assertEqual(self.preview(kind='settlement_proof'),{'status':'UNAVAILABLE','reason':'BANK_CARD_BINDING_UNAVAILABLE'})
    def test_bank_unavailable_requires_real_owner_and_application_first(self):
        p={'application':self.app['application'],'revision':self.app['revision'],'kind':'settlement_proof'}
        with self.assertRaises(PermissionError):self.fx.call('material_preview',p,review=True)
        with self.assertRaises((ValueError,PermissionError)):self.preview(application='ma_'+'0'*32,kind='settlement_proof')
    def test_mime_must_match_decrypted_image_signature(self):
        self.fx.fx.center.db.execute("UPDATE objects SET mime='image/png' WHERE project=?",(self.app['application'],))
        self.assertEqual(self.preview(),{'status':'UNAVAILABLE','reason':'MATERIAL_INTEGRITY'})
    def test_explicit_bank_photo_upload_marks_only_new_exact_object_and_previews(self):
        old=self.fx.upload(self.app,'settlement_proof',self.raw)
        self.app=self.fx.upload(old,'bank_card',self.raw)
        c=self.fx.fx.center;owner,meta,data=self.fx.service._load(self.app['application'],self.fx.fx.uid1)
        self.assertEqual(meta['materials']['bank_card']['purpose'],'BANK_CARD')
        self.assertNotIn('purpose',meta['materials']['settlement_proof'])
        r=self.preview(kind='bank_card');self.assertEqual(base64.b64decode(r['content_base64']),self.raw)
        self.assertEqual(r['object_id'],meta['materials']['bank_card']['object_id'])
        self.assertEqual(self.preview(kind='settlement_proof')['reason'],'BANK_CARD_BINDING_UNAVAILABLE')
        self.assertNotIn('bank_card',self.app['required_materials'])
    def test_new_bank_type_never_enters_old_reviewer_download_or_provider_upload(self):
        self.app=self.fx.upload(self.app,'bank_card',self.raw)
        for review in (False,True):
            with self.assertRaisesRegex(PermissionError,'PRIVATE_PREVIEW_ONLY'):self.fx.call('download',{'application':self.app['application'],'kind':'bank_card'},review=review)
        from scripts.community_wechat_applyment import WechatApplyment
        with self.assertRaisesRegex(PermissionError,'PRIVATE_PREVIEW_ONLY'):WechatApplyment.media(object(),None,None,None,None,'bank_card',None)
    def test_bank_card_kind_without_trusted_upload_marker_not_reclassified(self):
        self.app=self.fx.upload(self.app,'bank_card',self.raw)
        owner,meta,data=self.fx.service._load(self.app['application'],self.fx.fx.uid1)
        del meta['materials']['bank_card']['purpose'];self.fx.service._meta(self.app['application'],owner,meta)
        self.assertEqual(self.preview(kind='bank_card')['reason'],'BANK_CARD_BINDING_UNAVAILABLE')
    def test_bank_pdf_rejected_without_new_retained_object(self):
        c=self.fx.fx.center;before=c.db.execute('SELECT count(*) FROM objects').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'BANK_CARD_IMAGE_REQUIRED'):self.fx.upload(self.app,'bank_card',b'%PDF-synthetic')
        self.assertEqual(c.db.execute('SELECT count(*) FROM objects').fetchone()[0],before)
    def test_pdf_not_misrepresented_as_image(self):
        self.app=self.fx.upload(self.app,'business_license',b'%PDF-synthetic')
        self.assertEqual(self.preview(),{'status':'UNAVAILABLE','reason':'MATERIAL_PREVIEW_IMAGE_REQUIRED'})
    def test_changed_material_after_decrypt_rejected(self):
        c=self.fx.fx.center;original=c.decrypt;changed=False
        def decrypt(raw,label):
            nonlocal changed
            value=original(raw,label)
            if str(label).startswith('object:') and not changed:
                changed=True;c.db.execute('UPDATE onboarding SET revision=revision+1 WHERE application=?',(self.app['application'],))
            return value
        with patch.object(c,'decrypt',side_effect=decrypt):self.assertEqual(self.preview()['reason'],'MATERIAL_PREVIEW_SOURCE_CHANGED')
    def test_scan_and_expiry(self):
        c=self.fx.fx.center;c.db.execute("UPDATE objects SET scan='BLOCKED' WHERE project=?",(self.app['application'],))
        self.assertEqual(self.preview()['reason'],'MATERIAL_INTEGRITY')
    def test_revocation_after_decrypt_rejected(self):
        c=self.fx.fx.center;original=c.decrypt
        def decrypt(raw,label):
            value=original(raw,label)
            if str(label).startswith('object:'):c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ONBOARDING' AND subject_idx=?",(self.app['application'],))
            return value
        with patch.object(c,'decrypt',side_effect=decrypt),self.assertRaises(PermissionError):self.preview()

    def test_expired_retained_image(self):
        c=self.fx.fx.center;expiry=c.now()+20
        self.app=self.fx.upload(self.app,'business_license',self.raw,expires_at=expiry)
        with patch.object(c,'now',return_value=expiry):self.assertEqual(self.preview()['reason'],'MATERIAL_PREVIEW_EXPIRED')
    def test_original_digest_and_decrypted_bytes_must_match(self):
        c=self.fx.fx.center;original=c.decrypt
        def decrypt(raw,label):
            value=original(raw,label)
            return b'changed' if str(label).startswith('object:') else value
        with patch.object(c,'decrypt',side_effect=decrypt):self.assertEqual(self.preview()['reason'],'MATERIAL_INTEGRITY')
    def test_late_scan_block_rejected(self):
        c=self.fx.fx.center;original=c.decrypt
        def decrypt(raw,label):
            value=original(raw,label)
            if str(label).startswith('object:'):c.db.execute("UPDATE objects SET scan='BLOCKED' WHERE project=?",(self.app['application'],))
            return value
        with patch.object(c,'decrypt',side_effect=decrypt):self.assertEqual(self.preview()['reason'],'MATERIAL_INTEGRITY')

class MiniPreviewBoundary(unittest.TestCase):
    def test_real_mini_transport_uses_narrow_owner_path_not_download(self):
        import test_community_mini_merchant as mini_fixture
        fx=mini_fixture.SameMiniMerchant();fx.setUp()
        try:
            fx.fx.center.scanner=lambda raw:True
            app=fx.draft();raw=b'\xff\xd8\xffSYNTHETIC'
            app=fx.call('onboarding',{'operation':'upload','params':{'application':app['application'],'revision':app['revision'],'kind':'business_license','content_base64':base64.b64encode(raw).decode(),'expires_at':None}})
            p={'application':app['application'],'revision':app['revision'],'kind':'business_license'}
            r=fx.call('onboarding',{'operation':'material_preview','params':p});self.assertEqual(base64.b64decode(r['content_base64']),raw)
            with self.assertRaises(PermissionError):fx.call('onboarding',{'operation':'download','params':{'application':app['application'],'kind':'business_license'}})
            other=fx.fx.token('othercode','openid2')
            with self.assertRaises(PermissionError):fx.call('onboarding',{'operation':'material_preview','params':p},other)
            with self.assertRaises(PermissionError):fx.service.dispatch(fx.token,'unknown',{'operation':'onboarding','params':{'operation':'material_preview','params':p}})
        finally:fx.tearDown()
