"""Offer pricing cost evidence regressions: no price with unknown underlying cost."""
import unittest
from scripts.community_saas_offers import open_offer_store,register_offer,add_component,change_offer_status,quote_offers
from scripts.community_saas_cost_pricing import open_cost_store,save_cost,preview,assert_publishable_cost
class Costs(unittest.TestCase):
 def setUp(self):
  self.offers=open_offer_store();self.costs=open_cost_store()
  register_offer(self.offers,"cloud","merchant_operations","MONTHLY",1,30,True,"one-tenant","ratebook-1")
 def tearDown(self):self.offers.close();self.costs.close()
 def test_supplier_plus_agency_setup_maintenance_itemization(self):
  for cid,kind,cadence,cny,usd in [
   ("supplier","THIRD_PARTY_CLOUD_BASE","MONTHLY",9000,1200),
   ("agency","AGENCY_SERVICE_FEE","MONTHLY",1000,200),
   ("deploy","DEPLOYMENT_ONCE","ONCE",2000,300),
   ("maintenance","MAINTENANCE_RECURRING","MONTHLY",500,100)]:
   add_component(self.offers,"cloud",cid,kind,cadence,cny,usd,"approved-pricebook",
                 "aliyun" if cid=="supplier" else None)
  initial=preview(self.offers,self.costs,"cloud")
  self.assertTrue(initial["cost_unknown"])
  self.assertIsNone(initial["by_cadence"]["MONTHLY"]["gross_margin_cny_minor"])
  with self.assertRaisesRegex(ValueError,"COST_INCOMPLETE"):
   assert_publishable_cost(self.offers,self.costs,"cloud")
  with self.assertRaisesRegex(ValueError,"UNKNOWN_COST"):
   save_cost(self.costs,"cloud","supplier","UNKNOWN",0,0)
  save_cost(self.costs,"cloud","supplier","VERIFIED_ACTUAL",8000,1000,"supplier-invoice","MONTHLY")
  save_cost(self.costs,"cloud","agency","EVIDENCED_ESTIMATE",350,50,"labor-estimate","MONTHLY")
  save_cost(self.costs,"cloud","deploy","EVIDENCED_ESTIMATE",1400,180,"work-order","ONCE")
  save_cost(self.costs,"cloud","maintenance","EVIDENCED_ESTIMATE",200,35,"maintenance-budget","MONTHLY")
  result=assert_publishable_cost(self.offers,self.costs,"cloud")
  self.assertTrue(result["contains_estimates"])
  self.assertEqual(result["by_cadence"]["MONTHLY"]["sale_cny_minor"],10500)
  self.assertEqual(result["by_cadence"]["MONTHLY"]["cost_cny_minor"],8550)
  self.assertEqual(result["by_cadence"]["MONTHLY"]["gross_margin_cny_minor"],1950)
  self.assertEqual(result["by_cadence"]["ONCE"]["gross_margin_cny_minor"],600)
  self.assertFalse(result["commissions_payable"])
 def test_unknown_monthly_does_not_erase_evidenced_once_margin(self):
  add_component(self.offers,"cloud","deployment","DEPLOYMENT_ONCE","ONCE",5000,700,"verified-list")
  add_component(self.offers,"cloud","support","SUPPORT_RECURRING","MONTHLY",2000,300,"verified-list")
  save_cost(self.costs,"cloud","deployment","VERIFIED_ACTUAL",2000,250,"work-order","ONCE")
  v=preview(self.offers,self.costs,"cloud")
  self.assertTrue(v["cost_unknown"])
  self.assertFalse(v["publishable_cost_evidence"])
  self.assertEqual(v["by_cadence"]["ONCE"]["gross_margin_cny_minor"],3000)
  self.assertEqual(v["by_cadence"]["ONCE"]["gross_margin_usd_minor"],450)
  self.assertIsNone(v["by_cadence"]["MONTHLY"]["gross_margin_cny_minor"])
  self.assertIsNone(v["by_cadence"]["MONTHLY"]["cost_cny_minor"])
  with self.assertRaisesRegex(ValueError,"COST_INCOMPLETE"):
   assert_publishable_cost(self.offers,self.costs,"cloud")
 def test_effective_offer_uses_separate_cadence_totals(self):
  add_component(self.offers,"cloud","license","MODULE_LICENSE","MONTHLY",2000,300,"pricing-v1")
  add_component(self.offers,"cloud","setup","DEPLOYMENT_ONCE","ONCE",4000,600,"pricing-v1")
  save_cost(self.costs,"cloud","license","VERIFIED_ACTUAL",500,60,"real-usage","MONTHLY")
  save_cost(self.costs,"cloud","setup","VERIFIED_ACTUAL",1000,100,"real-deployment","ONCE")
  for state in ("PREVIEW","APPROVED","EFFECTIVE"):
   change_offer_status(self.offers,"cloud",state,self.costs)
  record=quote_offers(self.offers,"merchant_operations",cost_db=self.costs)[0]
  self.assertTrue(record["mixed_billing_cadences"])
  self.assertFalse(record["totals_are_payable"])
  self.assertEqual(record["totals_by_cadence"]["MONTHLY"]["cny_minor"],2000)
  self.assertEqual(record["totals_by_cadence"]["ONCE"]["cny_minor"],4000)
  self.assertEqual(record["total_cny_minor"],6000)
 def test_discount_cannot_hide_negative_monthly_with_positive_setup(self):
  add_component(self.offers,"cloud","setup","DEPLOYMENT_ONCE","ONCE",5000,700,"pricing-v1")
  add_component(self.offers,"cloud","discount","DISCOUNT","MONTHLY",1000,100,"pricing-v1")
  save_cost(self.costs,"cloud","setup","VERIFIED_ACTUAL",1000,100,"work-order","ONCE")
  save_cost(self.costs,"cloud","discount","VERIFIED_ACTUAL",0,0,"promotion-evidence","MONTHLY")
  for state in ("PREVIEW","APPROVED","EFFECTIVE"):
   change_offer_status(self.offers,"cloud",state,self.costs)
  with self.assertRaisesRegex(ValueError,"NEGATIVE_QUOTE_TOTAL"):
   quote_offers(self.offers,"merchant_operations",cost_db=self.costs)
 def test_currency_specific_negative_discount_is_not_offset_by_setup(self):
  add_component(self.offers,"cloud","setup","DEPLOYMENT_ONCE","ONCE",1000,2000,"pricing-v1")
  add_component(self.offers,"cloud","discount","DISCOUNT","MONTHLY",0,200,"pricing-v1")
  save_cost(self.costs,"cloud","setup","VERIFIED_ACTUAL",200,100,"work-order","ONCE")
  save_cost(self.costs,"cloud","discount","VERIFIED_ACTUAL",0,0,"campaign-evidence","MONTHLY")
  for state in ("PREVIEW","APPROVED","EFFECTIVE"):
   change_offer_status(self.offers,"cloud",state,self.costs)
  with self.assertRaisesRegex(ValueError,"NEGATIVE_QUOTE_TOTAL"):
   quote_offers(self.offers,"merchant_operations",cost_db=self.costs)
 def test_unknown_is_not_free_zero(self):
  add_component(self.offers,"cloud","subscription","THIRD_PARTY_SUBSCRIPTION_BASE",
                "MONTHLY",1000,150,"official-verified","provider")
  save_cost(self.costs,"cloud","subscription","UNKNOWN",cadence="MONTHLY")
  check=preview(self.offers,self.costs,"cloud")
  self.assertIsNone(check["lines"][0]["cost_cny_minor"])
  self.assertIsNone(check["by_cadence"]["MONTHLY"]["gross_margin_cny_minor"])
 def test_offer_cannot_publish_without_verified_cost_lines(self):
  add_component(self.offers,"cloud","license","MODULE_LICENSE","MONTHLY",3000,500,"approved-pricebook")
  change_offer_status(self.offers,"cloud","PREVIEW")
  change_offer_status(self.offers,"cloud","APPROVED")
  with self.assertRaisesRegex(ValueError,"COST_EVIDENCE_GATE_REQUIRED"):
   change_offer_status(self.offers,"cloud","EFFECTIVE")
  with self.assertRaisesRegex(ValueError,"COST_INCOMPLETE"):
   change_offer_status(self.offers,"cloud","EFFECTIVE",self.costs)
  save_cost(self.costs,"cloud","license","EVIDENCED_ESTIMATE",900,120,"documented-cost-estimate","MONTHLY")
  change_offer_status(self.offers,"cloud","EFFECTIVE",self.costs)
  self.assertEqual(self.offers.execute("SELECT status FROM offers WHERE offer_id='cloud'").fetchone()[0],"EFFECTIVE")
if __name__=="__main__":unittest.main()
