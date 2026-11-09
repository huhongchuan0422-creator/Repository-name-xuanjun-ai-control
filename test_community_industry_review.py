"""Original encrypted Center/auth fixtures; no provider or funds requests."""
import copy
import unittest
import test_community_industry_materials as material_fixture

class IndustryReview(unittest.TestCase):
    def setUp(self):
        self.f=material_fixture.IndustryMaterials();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.api=self.f.api;self.c=self.f.c;self.id=self.f.id
    def store(self,industry='宠物医院',state='PENDING_INTERNAL_REVIEW',material=True):
        if material:
            self.f.upload('industry_permit');self.f.select('industry_permit',self.f.receipt('industry_permit'))
        record=self.api._read(self.id)
        record['profile']['settlement_info'].update(settlement_id='716',qualification_type=industry)
        record['state']=state
        with self.c.tx():self.api._save(self.id,self.f.fx.fx.uid1,record)
        return record
    def call(self,op,review=True,**p):
        return self.f.fx.call(op,dict(application=self.id,**p),review)
    def assessments(self,plan):
        return [dict(branch_index=i,applicability='APPLICABLE_SATISFIED',material_kinds=['industry_permit'],rationale='Synthetic original reviewer assessed applicable branch') for i in range(len(plan['branches']))]
    def approve(self,record,assessments=None):
        p=dict(expected_version=record['version'],decision='INTERNAL_APPROVED',opinion='合成审核测试')
        if assessments is not None:p['industry_branch_assessments']=assessments
        return self.call('wechat_review',**p)
    def context(self):return self.f.fx.service._load(self.id,self.f.fx.fx.uid1)
    def test_review_read_incomplete_and_ready(self):
        result=self.call('wechat_review_read')
        self.assertEqual(result['industry_review']['status'],'INCOMPLETE')
        self.store();result=self.call('wechat_review_read')
        self.assertEqual(result['industry_review']['status'],'READY')
        self.assertIn('动物诊疗许可证',str(result['industry_review']['plan']['branches']))
        self.assertNotIn('industry_review',self.api._read(self.id))
    def test_complex_approval_requires_explicit_evidence(self):
        record=self.store();before=copy.deepcopy(record)
        with self.assertRaises(PermissionError):self.approve(record)
        self.assertEqual(self.api._read(self.id),before)
        plan=self.call('wechat_review_read')['industry_review']['plan']
        result=self.approve(record,self.assessments(plan))
        evidence=result['industry_review_evidence']
        self.assertEqual(evidence['profile_version'],result['version'])
        owner,meta,platform=self.context()
        self.assertEqual(evidence['application_revision'],platform['revision'])
        self.api.check_industry_review(result,self.id,owner,meta,platform)
    def test_correction_works_with_incomplete_draft(self):
        record=self.api._read(self.id);record['state']='PENDING_INTERNAL_REVIEW'
        with self.c.tx():self.api._save(self.id,self.f.fx.fx.uid1,record)
        result=self.call('wechat_review',expected_version=record['version'],decision='CORRECTION',opinion='需补正真实行业')
        self.assertEqual(result['state'],'CORRECTION')
        self.assertNotIn('industry_review_evidence',result)
    def test_simple_legacy_approval_without_extra_fields(self):
        record=self.store('餐饮',material=False);result=self.approve(record)
        self.assertEqual(result['state'],'INTERNAL_APPROVED')
        self.assertNotIn('industry_review_evidence',result)
        owner,meta,platform=self.context();self.api.check_industry_review(result,self.id,owner,meta,platform)
    def test_owner_cannot_review_or_inject_server_binding(self):
        record=self.store();plan=self.call('wechat_review_read')['industry_review']['plan']
        with self.assertRaises(PermissionError):self.call('wechat_review',review=False,expected_version=record['version'],decision='INTERNAL_APPROVED',opinion='not reviewer',industry_branch_assessments=self.assessments(plan))
        with self.assertRaises(ValueError):self.call('wechat_review',expected_version=record['version'],decision='INTERNAL_APPROVED',opinion='test',reviewer_id='injected')
    def test_missing_branch_and_invalid_material_rejected(self):
        record=self.store();plan=self.call('wechat_review_read')['industry_review']['plan']
        with self.assertRaises(PermissionError):self.approve(record,[])
        branches=self.assessments(plan);branches[0]['material_kinds']=['industry_permit_5']
        with self.assertRaises(PermissionError):self.approve(record,branches)
    def test_status_only_progress_allowed_but_content_and_material_changes_rejected(self):
        record=self.store();plan=self.call('wechat_review_read')['industry_review']['plan'];result=self.approve(record,self.assessments(plan))
        owner,meta,platform=self.context()
        bad=copy.deepcopy(platform);bad['revision']+=1
        self.api.check_industry_review(result,self.id,owner,meta,bad)
        backwards=copy.deepcopy(platform);backwards['revision']=result['industry_review_evidence']['application_revision']-1
        with self.assertRaises(PermissionError):self.api.check_industry_review(result,self.id,owner,meta,backwards)
        changed_meta=copy.deepcopy(meta);changed_meta['category']='FOOD'
        with self.assertRaises(PermissionError):self.api.check_industry_review(result,self.id,owner,changed_meta,platform)
        changed_meta=copy.deepcopy(meta);changed_meta['entity_type']='SOLE_PROPRIETOR'
        with self.assertRaises(ValueError):self.api.check_industry_review(result,self.id,owner,changed_meta,platform)
        bad=copy.deepcopy(result);bad['profile']['changed']='synthetic'
        with self.assertRaises(PermissionError):self.api.check_industry_review(bad,self.id,owner,meta,platform)
        bad=copy.deepcopy(meta);bad['materials']['industry_permit']['expires_at']=self.c.now()
        with self.assertRaises(PermissionError):self.api.check_industry_review(result,self.id,owner,bad,platform)
    def test_complex_legacy_approved_record_not_implicitly_certified(self):
        record=self.store(state='INTERNAL_APPROVED');record['reviewer']=self.f.fx.fx.uid2
        owner,meta,platform=self.context()
        with self.assertRaises(PermissionError):self.api.check_industry_review(record,self.id,owner,meta,platform)
    def legacy_expired(self):
        self.f.upload('industry_permit');media=self.f.receipt('industry_permit')
        record=self.api._read(self.id)
        record['profile']['settlement_info']['qualifications']=[media]
        record.pop('industry_qualification_bindings',None)
        owner,meta,_=self.context();meta['materials']['industry_permit']['expires_at']=self.c.now()
        with self.c.tx():
            self.api._save(self.id,owner,record)
            self.f.fx.service._meta(self.id,owner,meta)
        return media,meta
    def test_legacy_expired_single_slot_can_only_be_removed(self):
        media,meta=self.legacy_expired()
        before=self.c.db.execute("SELECT * FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA'").fetchall()
        with self.assertRaises(PermissionError):self.f.select('industry_permit',media)
        self.f.select('industry_permit',None,False)
        record=self.api._read(self.id)
        self.assertNotIn('qualifications',record['profile']['settlement_info'])
        self.assertEqual(record['industry_qualification_bindings'],[])
        self.assertEqual(before,self.c.db.execute("SELECT * FROM links WHERE channel='COMMUNITY_WECHAT_MEDIA'").fetchall())
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects WHERE project=?',(self.id,)).fetchone()[0],1)
        with self.assertRaises(PermissionError):self.f.select('industry_permit',media)
    def test_legacy_removal_requires_exact_server_receipt_scope(self):
        self.legacy_expired();record=copy.deepcopy(self.api._read(self.id))
        with self.assertRaises(PermissionError):self.f.select('industry_permit_2',None,False)
        self.c.db.execute("UPDATE links SET project='foreign' WHERE channel='COMMUNITY_WECHAT_MEDIA'")
        with self.assertRaises(PermissionError):self.f.select('industry_permit',None,False)
        self.assertEqual(record,self.api._read(self.id))
    def test_legacy_removal_rejects_changed_current_sha(self):
        _,meta=self.legacy_expired()
        meta['materials']['industry_permit']['sha256']='f'*64
        with self.c.tx():self.f.fx.service._meta(self.id,self.f.fx.fx.uid1,meta)
        with self.assertRaises(PermissionError):self.f.select('industry_permit',None,False)

    def test_unknown_or_cross_subject_cannot_be_approved(self):
        record=self.store('fictional industry')
        with self.assertRaises(ValueError):self.approve(record)
        record['profile']['settlement_info'].update(qualification_type='餐饮',settlement_id='719')
        with self.c.tx():self.api._save(self.id,self.f.fx.fx.uid1,record)
        with self.assertRaises(ValueError):self.approve(record)

if __name__=='__main__':unittest.main()
