"""Offline encrypted Center fixtures; no real documents/provider requests."""
import hashlib
import unittest
import test_community_merchant_onboarding as original
from scripts.pr122_customer_core import canonical
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader
from scripts.community_merchant_onboarding import INDUSTRY_MATERIAL_KINDS, MATERIALS

class IndustryMaterials(unittest.TestCase):
    def setUp(self):
        self.fx=original.MerchantAdmissionJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.c=self.fx.fx.center;reader=PartnerOrderReader.__new__(PartnerOrderReader);reader._mchid='123456'
        self.api=WechatApplyment(self.fx.service,reader);self.fx.service.wechat_applyment=self.api
        self.app=self.fx.draft();self.id=self.app['application']
        with self.c.tx():self.api._save(self.id,self.fx.fx.uid1,{'version':1,'state':'DRAFT','profile':{'settlement_info':{}}})
    def upload(self,kind,raw=None):
        self.app=self.fx.upload(self.app,kind,raw or b'%PDF-synthetic-'+kind.encode())
        return self.fx.service._load(self.id,self.fx.fx.uid1)[1]
    def receipt(self,kind,meta=None,media=None):
        meta=meta or self.fx.service._load(self.id,self.fx.fx.uid1)[1]
        sha=meta['materials'][kind]['sha256'];media=media or 'synthetic-'+kind
        key=hashlib.sha256(canonical([self.api.reader._mchid,self.id,kind,sha])).hexdigest()
        with self.c.tx():self.c.db.execute("INSERT OR REPLACE INTO links VALUES('COMMUNITY_WECHAT_MEDIA',?,?,?,?,1)",(key,self.fx.fx.uid1,self.id,self.c.encrypt(canonical(dict(kind=kind,sha256=sha,media_id=media,provider_response_sha256='a'*64)),'wechat-media:'+key)))
        return media
    def select(self,kind,media,selected=True,**changes):
        p=dict(application=self.id,expected_version=self.api._read(self.id)['version'],application_revision=self.app['revision'],kind=kind,media_id=media,selected=selected);p.update(changes)
        return self.fx.call('wechat_qualifications_select',p)
    def test_five_independent_slots_preserve_versions(self):
        self.assertEqual(len(INDUSTRY_MATERIAL_KINDS),5)
        for kind in INDUSTRY_MATERIAL_KINDS:
            self.upload(kind);self.select(kind,self.receipt(kind))
        r=self.api._read(self.id);self.assertEqual(len(r['profile']['settlement_info']['qualifications']),5)
        self.assertEqual(len(self.c.db.execute("SELECT * FROM versions WHERE project=? AND item LIKE 'industry_permit%'",(self.id,)).fetchall()),5)
        self.assertEqual(self.fx.service._load(self.id,self.fx.fx.uid1)[1]['materials'].keys(),set(INDUSTRY_MATERIAL_KINDS))
        self.assertNotIn('industry_permit_6',MATERIALS)
    def test_replace_only_one_slot_clears_its_selection(self):
        for kind in INDUSTRY_MATERIAL_KINDS[:2]:self.upload(kind);self.select(kind,self.receipt(kind))
        old_version=self.api._read(self.id)['version']
        self.upload('industry_permit',b'%PDF-replacement')
        r=self.api._read(self.id)
        self.assertEqual(r['version'],old_version+1)
        self.assertEqual(r['profile']['settlement_info']['qualifications'],['synthetic-industry_permit_2'])
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM versions WHERE project=? AND item='industry_permit'",(self.id,)).fetchone()[0],2)
        with self.assertRaises(PermissionError):self.select('industry_permit','synthetic-industry_permit')
    def test_deselect_no_object_deletion(self):
        self.upload('industry_permit');self.select('industry_permit',self.receipt('industry_permit'))
        self.select('industry_permit',None,False)
        self.assertNotIn('qualifications',self.api._read(self.id)['profile']['settlement_info'])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects WHERE project=?',(self.id,)).fetchone()[0],1)
    def test_wrong_kind_and_versions_rejected(self):
        self.upload('industry_permit');m=self.receipt('industry_permit')
        with self.assertRaises(PermissionError):self.select('industry_permit_2',m)
        with self.assertRaises(ValueError):self.select('industry_permit',m,expected_version=0)
        with self.assertRaises(ValueError):self.select('industry_permit',m,application_revision=0)
    def test_other_document_media_is_not_qualification(self):
        meta=self.upload('identity_front');media=self.receipt('identity_front')
        profile={'settlement_info':{'qualifications':[media]}}
        with self.assertRaises(PermissionError):self.api.validate_industry_materials(profile,self.id,meta)
    def test_current_scan_sha_and_expiry(self):
        meta=self.upload('industry_permit');media=self.receipt('industry_permit');profile={'settlement_info':{'qualifications':[media]}}
        self.assertEqual(len(self.api.validate_industry_materials(profile,self.id,meta)),1)
        self.c.db.execute("UPDATE objects SET scan='REJECTED' WHERE project=?",(self.id,))
        with self.assertRaises(PermissionError):self.api.validate_industry_materials(profile,self.id,meta)
        self.c.db.execute("UPDATE objects SET scan='CLEAN' WHERE project=?",(self.id,))
        meta['materials']['industry_permit']['expires_at']=self.c.now()
        with self.assertRaises(PermissionError):self.api.validate_industry_materials(profile,self.id,meta)
    def test_food_and_old_general_compatibility(self):
        meta=self.fx.service._load(self.id,self.fx.fx.uid1)[1]
        self.assertEqual(self.api.validate_industry_materials({'settlement_info':{}},self.id,meta),[])
        meta['category']='FOOD'
        with self.assertRaises(ValueError):self.api.validate_industry_materials({'settlement_info':{}},self.id,meta)
        self.assertIn('industry_permit',self.fx.service._required(meta));self.assertNotIn('industry_permit_2',self.fx.service._required(meta))
    def test_pending_review_not_overwritten(self):
        self.upload('industry_permit');self.select('industry_permit',self.receipt('industry_permit'))
        r=self.api._read(self.id);r['state']='PENDING_INTERNAL_REVIEW'
        with self.c.tx():self.api._save(self.id,self.fx.fx.uid1,r)
        with self.assertRaises(PermissionError):self.upload('industry_permit',b'%PDF-new')
        self.assertEqual(self.api._read(self.id),r)
    def test_reviewer_cannot_select(self):
        self.upload('industry_permit');m=self.receipt('industry_permit')
        with self.assertRaises(PermissionError):self.fx.call('wechat_qualifications_select',dict(application=self.id,expected_version=1,application_revision=self.app['revision'],kind='industry_permit',media_id=m,selected=True),True)
    def test_official_five_cap_and_duplicate(self):
        meta=self.upload('industry_permit');media=self.receipt('industry_permit')
        with self.assertRaises(ValueError):self.api.validate_industry_materials({'settlement_info':{'qualifications':[media]*6}},self.id,meta)
        with self.assertRaises(PermissionError):self.api.validate_industry_materials({'settlement_info':{'qualifications':[media]*2}},self.id,meta)

    def test_expired_selected_slot_replacement_recovers(self):
        self.upload('industry_permit');self.select('industry_permit',self.receipt('industry_permit'))
        _,meta,_=self.fx.service._load(self.id,self.fx.fx.uid1)
        meta['materials']['industry_permit']['expires_at']=self.c.now()
        with self.c.tx():self.fx.service._meta(self.id,self.fx.fx.uid1,meta)
        self.upload('industry_permit',b'%PDF-fresh')
        self.assertNotIn('qualifications',self.api._read(self.id)['profile']['settlement_info'])
        self.select('industry_permit',self.receipt('industry_permit',media='new-media'))
        self.assertEqual(self.api._read(self.id)['profile']['settlement_info']['qualifications'],['new-media'])
    def test_receipt_foreign_application_not_admitted(self):
        meta=self.upload('industry_permit');media=self.receipt('industry_permit')
        self.c.db.execute("UPDATE links SET project='another-application' WHERE channel='COMMUNITY_WECHAT_MEDIA'")
        with self.assertRaises(PermissionError):self.api.validate_industry_materials({'settlement_info':{'qualifications':[media]}},self.id,meta)

    def test_unselected_backup_does_not_expand_required_materials(self):
        meta=self.upload('industry_permit_2')
        self.assertNotIn('industry_permit_2',self.fx.service._required(meta,self.id))
        self.select('industry_permit_2',self.receipt('industry_permit_2'))
        self.assertIn('industry_permit_2',self.fx.service._required(meta,self.id))
        self.select('industry_permit_2',None,False)
        self.assertNotIn('industry_permit_2',self.fx.service._required(meta,self.id))
    def test_expired_selections_can_be_removed_without_readmission(self):
        for kind in INDUSTRY_MATERIAL_KINDS[:2]:
            self.upload(kind);self.select(kind,self.receipt(kind))
        owner,meta,_=self.fx.service._load(self.id,self.fx.fx.uid1)
        for kind in INDUSTRY_MATERIAL_KINDS[:2]:meta['materials'][kind]['expires_at']=self.c.now()
        with self.c.tx():self.fx.service._meta(self.id,owner,meta)
        self.select('industry_permit',None,False)
        record=self.api._read(self.id)
        self.assertEqual(record['profile']['settlement_info']['qualifications'],['synthetic-industry_permit_2'])
        with self.assertRaises(PermissionError):self.api.validate_industry_materials(record['profile'],self.id,meta)
        self.select('industry_permit_2',None,False)
        self.assertNotIn('qualifications',self.api._read(self.id)['profile']['settlement_info'])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects WHERE project=?',(self.id,)).fetchone()[0],2)

if __name__=='__main__':unittest.main()
