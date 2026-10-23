import unittest
from scripts.community_saas_unit_economics import project_unit_economics

class UnitEconomicsTests(unittest.TestCase):
 def test_reusable_hundred_yuan_development_ten_yuan_price(self):
  # Amounts in fen. R&D 100 CNY is shared; sale 10 CNY per buyer.
  v=project_unit_economics(10000,1000,100,1000)
  self.assertEqual(v["projected_sales_minor"],1000000)
  self.assertEqual(v["unit_contribution_before_rnd_minor"],900)
  self.assertEqual(v["projected_contribution_after_rnd_minor"],890000)
  self.assertFalse(v["requires_subsidy_approval"])
  self.assertFalse(v["financial_profit_recognized"])
  self.assertIsNone(v["realized_sales_minor"])
 def test_below_unit_variable_cost_needs_subsidy(self):
  v=project_unit_economics(10000,1000,1200,1000)
  self.assertEqual(v["unit_contribution_before_rnd_minor"],-200)
  self.assertTrue(v["requires_subsidy_approval"])
 def test_recurring_costs_cannot_be_ignored(self):
  v=project_unit_economics(10000,1000,800,1000,recurring_commitment_minor=300)
  self.assertEqual(v["unit_variable_cost_minor"],1100)
  self.assertTrue(v["requires_subsidy_approval"])
 def test_invalid_inputs_rejected(self):
  for args in [(-1,100,0,2),(100,True,0,2),(100,100,0,0),(100,100,0,2,-1)]:
   with self.assertRaises(ValueError):project_unit_economics(*args)
if __name__=="__main__":unittest.main()
