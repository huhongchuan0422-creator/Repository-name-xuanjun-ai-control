"""Final Owner UI selections persist in the original encrypted application only."""
import copy,unittest
from test_community_wechat_profile_reuse import SameProfileReuse
from scripts.community_merchant_onboarding import checked_declarations,require_confirmed_declarations

class ApplicationDeclarations(SameProfileReuse):
 def test_unknown_saved_reopened_and_conservative_materials_not_fake_mini(self):
  app=self.fx.draft(declarations=dict(scene='unknown',ubos='unknown'))
  self.fx.call('wechat_save',dict(application=app['application'],expected_version=0,profile={}))
  again=self.fx.call('read',dict(application=app['application']))
  self.assertEqual(again['declarations'],dict(scene='unknown',ubos='unknown'))
  self.assertIn('storefront_photo',again['required_materials']);self.assertIn('interior_photo',again['required_materials'])
  self.assertNotIn('mini_program_screenshot',again['required_materials'])
  for op,args in [('submit',dict(revision=again['revision'])),('wechat_submit_review',dict(expected_version=1))]:
   with self.assertRaisesRegex(ValueError,'CONDITIONS_NOT_CONFIRMED'):self.fx.call(op,dict(application=app['application'],**args))
 def test_confirmed_selection_saved_as_original_choice_not_duplicated_pii(self):
  app=self.fx.draft(sales_scenes_type=['SALES_SCENES_STORE'],declarations=dict(scene='store',ubos=0))
  self.assertEqual(app['declarations'],dict(scene='store',ubos=0));self.assertEqual(app['sales_scenes_type'],['SALES_SCENES_STORE'])
  self.assertEqual(set(app['fields']),{'legal_name','store_name','address','contact'})
 def test_unknown_or_wrong_shapes_do_not_bypass_existing_schema(self):
  for value in [{'scene':'any','ubos':0},{'scene':[],'ubos':0},{'scene':'mini','ubos':True},{'scene':'mini','ubos':5},{'scene':'mini','ubos':'not_applicable'},{'scene':'mini','ubos':0,'role':'MERCHANT'}]:
   with self.assertRaises(ValueError):checked_declarations(value,'ENTERPRISE')
 def test_selection_must_match_exact_official_scene(self):
  with self.assertRaisesRegex(ValueError,'SCENE_DECLARATION_MISMATCH'):self.fx.draft(sales_scenes_type=['SALES_SCENES_MINI_PROGRAM'],declarations=dict(scene='store',ubos=0))
 def test_complete_beneficiary_count_not_other_beneficiary_count(self):
  meta={'entity_type':'ENTERPRISE','declarations':dict(scene='mini',ubos=2)}
  p={'business_info':{'sales_info':{'sales_scenes_type':['SALES_SCENES_MINI_PROGRAM']}},'subject_info':{'ubo_info_list':[{},{}]}}
  require_confirmed_declarations(meta,p)
  p['subject_info']['ubo_info_list'].append({})
  with self.assertRaisesRegex(ValueError,'UBO_DECLARATION_MISMATCH'):require_confirmed_declarations(meta,p)
 def test_legal_only_must_not_have_unacknowledged_list(self):
  meta={'entity_type':'ENTERPRISE','declarations':dict(scene='mini',ubos=0)}
  p={'business_info':{'sales_info':{'sales_scenes_type':['SALES_SCENES_MINI_PROGRAM']}},'subject_info':{'ubo_info_list':[{}]}}
  with self.assertRaisesRegex(ValueError,'UBO_DECLARATION_MISMATCH'):require_confirmed_declarations(meta,p)
 def test_cross_account_and_stale_declaration_updates_rejected(self):
  app=self.fx.draft(declarations=dict(scene='unknown',ubos='unknown'))
  with self.assertRaises(PermissionError):self.fx.call('read',dict(application=app['application']),review=True)
  self.fx.draft(app,declarations=dict(scene='unknown',ubos='unknown'))
  with self.assertRaisesRegex(ValueError,'REVISION_CONFLICT'):self.fx.draft(app,declarations=dict(scene='unknown',ubos='unknown'))
 def test_individual_does_not_require_enterprise_beneficiary_declaration(self):
  self.assertEqual(checked_declarations(dict(scene='store',ubos='not_applicable'),'SOLE_PROPRIETOR')['ubos'],'not_applicable')

if __name__=='__main__':unittest.main()
