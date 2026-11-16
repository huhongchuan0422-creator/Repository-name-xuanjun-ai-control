"""Synthetic only: no unselected identity transmission or unnecessary screenshot gate."""
import copy,json,unittest
from test_community_applicant_applyment import ApplicantApplyment
from scripts.community_wechat_applyment import provider_submission_profile,mini_program_is_live,mini_program_appids,DEFAULT_MINI_PROGRAM_APPID

class MiniSceneContract(ApplicantApplyment):
    def save_profile(self,profile,**extra):
        return self.call('wechat_save',expected_version=self.read()['version'],profile=profile,**extra)
    def test_live_mini_no_screenshot_uses_real_signed_flow_without_new_metadata_on_wire(self):
        profile=copy.deepcopy(self.read()['profile']);profile['business_info']['sales_info']['mini_program_info'].pop('mini_program_pics')
        record=self.save_profile(profile,mini_program_live=True)
        self.assertTrue(mini_program_is_live(record))
        self.assertNotIn('mini_program_screenshot',self.call('read')['required_materials'])
        with self.wire_response(self.signed_wire({'applyment_id':123456789})) as wire:
            self.apply()
        body=json.loads(wire.call_args.args[0].data)
        self.assertNotIn('mini_program_live',body)
        self.assertNotIn('mini_program_live_appids',body)
        self.assertNotIn('mini_program_pics',body['business_info']['sales_info']['mini_program_info'])
        self.assertEqual(self.read()['profile'],profile)
    def test_unconfirmed_mini_keeps_original_screenshot_requirement(self):
        profile=copy.deepcopy(self.read()['profile']);profile['business_info']['sales_info']['mini_program_info'].pop('mini_program_pics')
        self.save_profile(profile)
        self.assertIn('mini_program_screenshot',self.call('read')['required_materials'])
        with self.assertRaisesRegex(ValueError,'INVALID_OFFICIAL_MEDIA_LIST'):self.apply()
        self.provider.assert_not_called();self.assertEqual(self.attempts(),[])
    def test_changed_appid_does_not_inherit_old_live_attestation(self):
        profile=copy.deepcopy(self.read()['profile']);self.save_profile(profile,mini_program_live=True)
        profile['business_info']['sales_info']['mini_program_info']['mini_program_appid']='wxsyntheticreplacement'
        record=self.save_profile(profile)
        self.assertFalse(mini_program_is_live(record));self.assertNotIn('mini_program_live',record)
        self.assertIn('mini_program_screenshot',self.call('read')['required_materials'])
    def test_live_flag_requires_boolean_and_explicit_attestation_for_default(self):
        profile=copy.deepcopy(self.read()['profile']);before=self.read()
        with self.assertRaisesRegex(ValueError,'MINI_PROGRAM_LIVE_DECLARATION_REQUIRED'):self.save_profile(profile,mini_program_live='true')
        self.assertEqual(self.read(),before)
        profile['business_info']['sales_info']['mini_program_info'].pop('mini_program_appid',None)
        profile['business_info']['sales_info']['mini_program_info'].pop('mini_program_sub_appid',None)
        saved=self.save_profile(profile)
        self.assertEqual(mini_program_appids(saved['profile']),{'mini_program_appid':DEFAULT_MINI_PROGRAM_APPID})
        self.assertFalse(mini_program_is_live(saved))
        self.assertIn('mini_program_screenshot',self.call('read')['required_materials'])
        confirmed=self.save_profile(profile,mini_program_live=True)
        self.assertTrue(mini_program_is_live(confirmed));self.provider.assert_not_called()
    def test_selected_mini_keeps_legal_id_and_prunes_historical_store_only_on_wire(self):
        profile=copy.deepcopy(self.read()['profile']);profile['business_info']['sales_info']['biz_store_info']={'store_entrance_pic':['OLD_UNSELECTED_MEDIA'],'biz_store_address':'SYNTHETIC OLD STORE'}
        self.save_profile(profile)
        with self.wire_response(self.signed_wire({'applyment_id':123456789})) as wire:self.apply()
        body=json.loads(wire.call_args.args[0].data)
        self.assertNotIn('biz_store_info',body['business_info']['sales_info'])
        self.assertEqual(body['business_info']['sales_info']['mini_program_info'],profile['business_info']['sales_info']['mini_program_info'])
        self.assertEqual(self.read()['profile'],profile)
    def test_selected_store_prunes_historical_mini_identity_without_changing_draft(self):
        profile=copy.deepcopy(self.read()['profile']);sales=profile['business_info']['sales_info'];sales['sales_scenes_type']=['SALES_SCENES_STORE'];sales['biz_store_info']={'biz_store_name':'SYNTHETIC SHOP'}
        before=copy.deepcopy(profile);body=provider_submission_profile(profile)
        self.assertNotIn('mini_program_info',body['business_info']['sales_info']);self.assertEqual(body['business_info']['sales_info']['biz_store_info'],sales['biz_store_info']);self.assertEqual(profile,before)
    def test_both_scenes_retained(self):
        profile=copy.deepcopy(self.read()['profile']);sales=profile['business_info']['sales_info'];sales['sales_scenes_type']=['SALES_SCENES_STORE','SALES_SCENES_MINI_PROGRAM'];sales['biz_store_info']={'biz_store_name':'SYNTHETIC SHOP'}
        self.assertEqual(provider_submission_profile(profile),profile)
    def test_live_supplied_screenshot_still_requires_clean_bound_original(self):
        profile=copy.deepcopy(self.read()['profile']);self.save_profile(profile,mini_program_live=True)
        _,meta,_=self.fx.service._load(self.application,self.fx.fx.uid1)
        oid=meta['materials']['mini_program_screenshot']['object_id']
        self.center.db.execute("UPDATE objects SET scan='REJECTED' WHERE id=?",(oid,))
        with self.assertRaisesRegex(PermissionError,'PRIVATE_MATERIAL_BINDING_INVALID'):self.apply()
        self.provider.assert_not_called();self.assertEqual(self.attempts(),[])
        self.assertEqual(self.read()['profile'],profile)
    def test_live_unsubmitted_optional_original_does_not_block_or_get_sent(self):
        profile=copy.deepcopy(self.read()['profile']);profile['business_info']['sales_info']['mini_program_info'].pop('mini_program_pics');self.save_profile(profile,mini_program_live=True)
        _,meta,_=self.fx.service._load(self.application,self.fx.fx.uid1)
        oid=meta['materials']['mini_program_screenshot']['object_id'];self.center.db.execute("UPDATE objects SET scan='REJECTED' WHERE id=?",(oid,))
        with self.wire_response(self.signed_wire({'applyment_id':123456789})) as wire:self.apply()
        self.assertNotIn('mini_program_pics',json.loads(wire.call_args.args[0].data)['business_info']['sales_info']['mini_program_info'])
        self.assertEqual(self.center.db.execute('SELECT scan FROM objects WHERE id=?',(oid,)).fetchone()[0],'REJECTED')
    def test_read_live_fact_uses_binding_and_never_repairs_persistent_record(self):
        profile=copy.deepcopy(self.read()['profile']);saved=self.save_profile(profile,mini_program_live=True)
        self.assertTrue(self.read()['mini_program_live'])
        for binding in (None,{'mini_program_appid':'SYNTHETIC DIFFERENT ID'}):
            with self.subTest(binding_missing=binding is None):
                stored=copy.deepcopy(self.service._read(self.application));stored['mini_program_live']=True
                if binding is None:stored.pop('mini_program_live_appids',None)
                else:stored['mini_program_live_appids']=binding
                with self.center.tx():self.service._save(self.application,self.fx.fx.uid1,stored)
                before=copy.deepcopy(self.service._read(self.application));result=self.call('wechat_read')
                self.assertFalse(result['mini_program_live'])
                self.assertEqual(result['version'],before['version'])
                self.assertIn('mini_program_screenshot',self.call('read')['required_materials'])
                self.assertEqual(self.service._read(self.application),before)
        self.provider.assert_not_called();self.assertEqual(self.attempts(),[])

    def test_merchant_priority_preserves_history_and_projects_only_merchant_on_wire(self):
        profile=copy.deepcopy(self.read()['profile'])
        mini=profile['business_info']['sales_info']['mini_program_info']
        mini.update(mini_program_appid='wxsyntheticprovider',mini_program_sub_appid='wxsyntheticmerchant')
        self.save_profile(profile)
        with self.wire_response(self.signed_wire({'applyment_id':123456789})) as wire:self.apply()
        body=json.loads(wire.call_args.args[0].data)['business_info']['sales_info']['mini_program_info']
        self.assertEqual(body['mini_program_sub_appid'],'wxsyntheticmerchant');self.assertNotIn('mini_program_appid',body)
        self.assertEqual(self.read()['profile'],profile)
    def test_default_and_explicit_provider_are_not_runtime_identity(self):
        for mini,expected in [({},DEFAULT_MINI_PROGRAM_APPID),({'mini_program_appid':'wxexplicitprovider'},'wxexplicitprovider')]:
            profile={'business_info':{'sales_info':{'sales_scenes_type':['SALES_SCENES_MINI_PROGRAM'],'mini_program_info':mini}}}
            projected=provider_submission_profile(profile)
            self.assertEqual(projected['business_info']['sales_info']['mini_program_info'],{'mini_program_appid':expected})
            self.assertEqual(profile['business_info']['sales_info']['mini_program_info'],mini)
    def test_effective_id_switch_invalidates_live_and_keeps_both_saved_ids(self):
        profile=copy.deepcopy(self.read()['profile']);self.save_profile(profile,mini_program_live=True)
        mini=profile['business_info']['sales_info']['mini_program_info'];mini['mini_program_sub_appid']='wxsyntheticmerchant'
        saved=self.save_profile(profile)
        self.assertFalse(mini_program_is_live(saved));self.assertEqual(saved['profile'],profile)
        self.assertIn('mini_program_screenshot',self.call('read')['required_materials'])
    def test_no_merchant_id_defaults_on_original_save_and_signed_outbound(self):
        profile=copy.deepcopy(self.read()['profile']);mini=profile['business_info']['sales_info']['mini_program_info']
        mini.pop('mini_program_appid',None);mini.pop('mini_program_sub_appid',None)
        saved=self.save_profile(profile)
        self.assertFalse(mini_program_is_live(saved))
        self.assertEqual(saved['profile']['business_info']['sales_info']['mini_program_info']['mini_program_appid'],DEFAULT_MINI_PROGRAM_APPID)
        with self.wire_response(self.signed_wire({'applyment_id':123456789})) as wire:self.apply()
        body=json.loads(wire.call_args.args[0].data)['business_info']['sales_info']['mini_program_info']
        self.assertEqual(body['mini_program_appid'],DEFAULT_MINI_PROGRAM_APPID);self.assertNotIn('mini_program_sub_appid',body)
        self.assertEqual(body['mini_program_pics'],mini['mini_program_pics'])

    def test_historical_dual_id_attestation_keeps_same_effective_merchant(self):
        profile=copy.deepcopy(self.read()['profile'])
        mini=profile['business_info']['sales_info']['mini_program_info']
        mini.update(mini_program_appid='wxoldprovider',mini_program_sub_appid='wxmerchant')
        record={'profile':profile,'mini_program_live':True,'mini_program_live_appids':dict(mini_program_appid='wxoldprovider',mini_program_sub_appid='wxmerchant')}
        before=copy.deepcopy(record)
        self.assertTrue(mini_program_is_live(record));self.assertEqual(record,before)
        mini['mini_program_appid']='wxunusedproviderchanged'
        self.assertTrue(mini_program_is_live(record))
        mini['mini_program_sub_appid']='wxchangedmerchant'
        self.assertFalse(mini_program_is_live(record))
    def test_missing_or_empty_attestation_does_not_borrow_default(self):
        record={'profile':{'business_info':{'sales_info':{'mini_program_info':{}}}},'mini_program_live':True}
        self.assertFalse(mini_program_is_live(record))
        for snapshot in (None,{},[],{'mini_program_appid':''},{'mini_program_appid':'  '},{'mini_program_sub_appid':None}):
            record['mini_program_live_appids']=snapshot
            self.assertFalse(mini_program_is_live(record))
