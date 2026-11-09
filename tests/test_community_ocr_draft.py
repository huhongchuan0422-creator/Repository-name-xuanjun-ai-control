import unittest
from scripts.community_ocr_draft import merge_drafts, current_pending, resolve_confirmed

class PrivateDraftTests(unittest.TestCase):
    def setUp(self):
        self.material={'object_id':'original-object','sha256':'a'*64}
        self.materials={'business_license':self.material}
        self.update={'business_license':dict(self.material,fields={'company_name':'human edit'})}
    def test_save_is_unconfirmed_and_omission_preserves(self):
        draft=merge_drafts({},self.update,self.materials)
        self.assertTrue(draft['business_license']['needs_confirmation'])
        self.assertEqual(draft,merge_drafts(draft,None,self.materials))
        self.assertEqual(draft,merge_drafts(draft,{},self.materials))
    def test_client_cannot_confirm_or_clear(self):
        for update in ({'business_license':dict(self.update['business_license'],confirmed=True)}, {'business_license':None}):
            with self.assertRaises(ValueError):merge_drafts({},update,self.materials)
    def test_replaced_material_never_rebinds(self):
        draft=merge_drafts({},self.update,self.materials)
        changed={'business_license':dict(self.material,object_id='new-object')}
        self.assertEqual({},current_pending(draft,changed))
        with self.assertRaises(ValueError):merge_drafts(draft,self.update,changed)
        self.assertEqual(draft,resolve_confirmed(draft,'business_license',changed['business_license'],{'company_name':'human edit'}))
    def test_confirmation_exact_values_only(self):
        draft=merge_drafts({},self.update,self.materials)
        self.assertEqual(draft,resolve_confirmed(draft,'business_license',self.material,{'company_name':'old OCR'}))
        self.assertEqual({},resolve_confirmed(draft,'business_license',self.material,{'company_name':'human edit'}))
    def test_partial_update_preserves_other_same_material_fields(self):
        draft=merge_drafts({}, {'business_license':dict(self.material,fields={'company_name':'human edit','registered_address':'kept address'})},self.materials)
        updated=merge_drafts(draft,self.update,self.materials)
        self.assertEqual('kept address',updated['business_license']['fields']['registered_address'])
    def test_blank_is_saved_but_not_an_impossible_confirmation(self):
        from scripts.community_ocr_draft import current_drafts
        draft=merge_drafts({}, {'business_license':dict(self.material,fields={'company_name':''})},self.materials)
        self.assertEqual({},current_pending(draft,self.materials))
        self.assertEqual('',current_drafts(draft,self.materials)['business_license']['fields']['company_name'])
    def test_type_whitelist_and_length(self):
        for fields in ({'confirmed':True},{'id_number':'wrong document'},{'company_name':'x'*513},{}):
            with self.assertRaises(ValueError):merge_drafts({}, {'business_license':dict(self.material,fields=fields)},self.materials)

if __name__=='__main__':unittest.main()
