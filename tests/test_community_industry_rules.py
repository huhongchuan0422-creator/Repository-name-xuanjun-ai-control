import copy
import json
import unittest
from scripts.community_industry_rules import TABLE, validate_selection, validate_review_evidence

class IndustryRulesTests(unittest.TestCase):
    def setUp(self):
        self.rows=json.loads(TABLE.read_text())['rows']
        self.binding=dict(kind='industry_permit',sha256='a'*64,media_id='synthetic-media')
    def profile(self,row,bindings):
        return dict(settlement_info=dict(settlement_id=row['settlement_id'],qualification_type=row['qualification_type'],qualifications=[b['media_id'] for b in bindings]))
    def plan(self):
        row=next(r for r in self.rows if r['qualification_type']=='宠物医院')
        return validate_selection(self.profile(row,[self.binding]),row['subject'],'GENERAL',[self.binding])
    def evidence(self,plan):
        return dict(application='synthetic-app',application_revision=7,profile_version=3,reviewer_id='reviewer',
                    **{k:plan[k] for k in ('rule_sha256','materials_sha256','profile_sha256')},decision='CONDITIONS_CONFIRMED',
                    branch_assessments=[dict(branch_index=i,applicability='APPLICABLE_SATISFIED',material_kinds=['industry_permit'],rationale='Synthetic reviewer evidence, not real qualification') for i in range(len(plan['branches']))])
    def review(self,plan,evidence,**kw):
        args=dict(application='synthetic-app',application_revision=7,profile_version=3,owner_id='owner',authorized_reviewer_id='reviewer');args.update(kw)
        return validate_review_evidence(plan,evidence,**args)
    def test_all_91_keys_and_all_source_conditions_preserved(self):
        self.assertEqual(len(self.rows),91)
        for row in self.rows:
            bindings=[self.binding] if row['special_qualification_required'] else []
            profile=self.profile(row,bindings);before=copy.deepcopy(profile)
            p=validate_selection(profile,row['subject'],'GENERAL',bindings)
            self.assertEqual(p['rule']['row'],row)
            self.assertEqual(p['branches'],row['special_qualification_branches'])
            self.assertEqual(profile,before)
            self.assertEqual(p['qualification_adequacy'],'NOT_AUTOMATICALLY_DETERMINED')
    def test_unknown_cross_subject_wrong_rule_rejected(self):
        row=next(r for r in self.rows if r['subject']=='ENTERPRISE' and r['qualification_type']=='餐饮')
        profile=self.profile(row,[])
        for entity in ('SOLE_PROPRIETOR','UNKNOWN'):
            with self.assertRaises(ValueError):validate_selection(profile,entity,'GENERAL',[])
        for key,value in [('settlement_id','unknown'),('qualification_type','fictional industry')]:
            bad=copy.deepcopy(profile);bad['settlement_info'][key]=value
            with self.assertRaises(ValueError):validate_selection(bad,row['subject'],'GENERAL',[])
    def test_required_and_food_minimum_not_adequacy(self):
        required=next(r for r in self.rows if r['special_qualification_required'])
        with self.assertRaisesRegex(ValueError,'SPECIAL_QUALIFICATION'):validate_selection(self.profile(required,[]),required['subject'],'GENERAL',[])
        simple=next(r for r in self.rows if r['qualification_type']=='餐饮')
        with self.assertRaisesRegex(ValueError,'FOOD'):validate_selection(self.profile(simple,[]),simple['subject'],'FOOD',[])
        plan=validate_selection(self.profile(simple,[self.binding]),simple['subject'],'FOOD',[self.binding])
        self.assertTrue(plan['requires_explicit_review'])
    def test_conditional_false_required_still_needs_review(self):
        retail=next(r for r in self.rows if r['qualification_type']=='零售')
        plan=validate_selection(self.profile(retail,[]),retail['subject'],'GENERAL',[])
        self.assertTrue(plan['requires_explicit_review'])
        self.assertIn('烟草',str(plan['branches']))
    def test_current_media_binding_and_duplicates(self):
        row=self.rows[0];profile=self.profile(row,[self.binding])
        with self.assertRaises(PermissionError):validate_selection(profile,row['subject'],'GENERAL',[])
        with self.assertRaises(ValueError):validate_selection(self.profile(row,[self.binding]*2),row['subject'],'GENERAL',[self.binding]*2)
        wrong=dict(self.binding,kind='identity_front')
        with self.assertRaises(ValueError):validate_selection(self.profile(row,[wrong]),row['subject'],'GENERAL',[wrong])
    def test_explicit_original_reviewer_receipt(self):
        plan=self.plan();self.assertTrue(self.review(plan,self.evidence(plan)))
        with self.assertRaises(PermissionError):self.review(plan,None)
        with self.assertRaises(PermissionError):self.review(plan,self.evidence(plan),authorized_reviewer_id='owner')
    def test_stale_or_changed_evidence_rejected(self):
        plan=self.plan()
        for key,value in [('rule_sha256','b'*64),('materials_sha256','b'*64),('profile_sha256','b'*64),('application','other'),('application_revision',8),('profile_version',4),('reviewer_id','owner'),('decision','UNKNOWN')]:
            proof=self.evidence(plan);proof[key]=value
            with self.assertRaises(PermissionError):self.review(plan,proof)
    def test_branch_coverage_without_automatic_and_or(self):
        row=next(r for r in self.rows if len(r['special_qualification_branches'])>1)
        plan=validate_selection(self.profile(row,[self.binding]),row['subject'],'GENERAL',[self.binding])
        proof=self.evidence(plan)
        proof['branch_assessments'][0].update(applicability='NOT_APPLICABLE',material_kinds=[],rationale='Original reviewer explicitly checked this alternative is inapplicable')
        self.assertTrue(self.review(plan,proof))
        proof['branch_assessments'].pop()
        with self.assertRaises(PermissionError):self.review(plan,proof)
    def test_unknown_material_in_assessment_rejected(self):
        plan=self.plan();proof=self.evidence(plan);proof['branch_assessments'][0]['material_kinds']=['industry_permit_5']
        with self.assertRaises(PermissionError):self.review(plan,proof)

if __name__=='__main__':unittest.main()
