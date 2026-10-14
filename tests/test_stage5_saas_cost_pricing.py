"""Offer pricing cost evidence regressions: no price with unknown underlying cost."""
import unittest
from scripts.community_saas_offers import open_offer_store,register_offer,add_component,change_offer_status
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
 def test_unknown_is_not_free_zero(self):
  add_component(self.offers,"cloud","subscription","THIRD_PARTY_SUBSCRIPTION_BASE",
                "MONTHLY",1000,150,"official-verified","provider")
  save_cost(self.costs,"cloud","subscription","UNKNOWN",cadence="MONTHLY")
  check=preview(self.offers,self.costs,"cloud")
  self.assertIsNone(check["lines"][0]["cost_cny_minor"])
  self.assertIsNone(check["by_cadence"]["MONTHLY"]["gross_margin_cny_minor"])
if __name__=="__main__":unittest.main()
