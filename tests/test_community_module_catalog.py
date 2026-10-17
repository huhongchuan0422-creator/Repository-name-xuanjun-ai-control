"""New source modules reuse original pricing, approval and cost components."""
import unittest
from pathlib import Path
from scripts.community_saas_modules import catalog,connect,offers
from scripts.community_saas_offer_catalog import install,create_offer,quote

class ModulePackaging(unittest.TestCase):
    def test_stable_unique_metadata_dependencies_and_source_registration(self):
        modules=catalog();by_id={m['id']:m for m in modules}
        self.assertEqual(len({m['module_number'] for m in modules}),len(modules))
        for module in modules:
            self.assertEqual(module['author'],'玄钧AI实验室');self.assertIsNone(module['co_creator_nickname'])
            self.assertEqual(module['supported_currencies'],['CNY','USD'])
            self.assertTrue(all(d in by_id for d in module['dependencies']))
            if module['source']:self.assertTrue(Path(module['source']).is_file())
        self.assertEqual(by_id['wechat_partner_payments']['ownership'],'GENERAL_MODULE')
        self.assertEqual(by_id['community_rules']['ownership'],'BUSINESS_MODULE')
        self.assertEqual(by_id['original_project_center']['ownership'],'GENERAL_MODULE')
        self.assertIn('wechat_partner_payments',by_id['verified_receipt_ad']['dependencies'])
        self.assertIn('advertising',by_id['verified_receipt_ad']['dependencies'])
    def test_new_module_has_no_invented_price_and_reuses_itemized_dual_currency_quote(self):
        db=connect()
        try:
            self.assertIsNone(next(m for m in offers(db) if m['id']=='provider_reconciliation')['offer'])
            install(db)
            lines=[dict(type=kind,label=kind,cycle='ONCE',quantity=1,cny_minor=cny,usd_minor=usd) for kind,cny,usd in [('MODULE_FEE',1000,200),('SUPPLIER_COST',500,100),('AGENCY_FEE',100,20),('DEPLOYMENT',200,40),('MAINTENANCE',300,60)]]
            create_offer(db,'fixture_reconciliation',1,'provider_reconciliation','BUYOUT',lines)
            result=quote(db,'fixture_quote','tenantA','fixture_reconciliation',1,100,200)
            self.assertEqual(result['totals'],dict(cny_minor=2100,usd_minor=420))
            self.assertEqual(len(result['lines']),5);self.assertFalse(result['payment_authorized'])
        finally:db.close()
