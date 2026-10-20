import unittest
from scripts.contract_anchor_batch import monthly_cost,due
class CostTests(unittest.TestCase):
 def test_full_month(self):
  for days,batches in ((28,8064),(30,8640),(31,8928)):
   r=monthly_cost(days,300,batches,10);self.assertEqual(r['scheduled_batches'],batches);self.assertEqual(r['total_cost_minor'],batches*10)
 def test_empty_and_sparse(self):
  self.assertEqual(monthly_cost(30,300,0,10)['total_cost_minor'],0)
  self.assertEqual(monthly_cost(30,300,30,10,100)['total_cost_minor'],400)
  self.assertFalse(due(0,99999))
 def test_reject_invalid(self):
  for args in ((30,0,0,1),(30,300,8641,1),(True,300,1,1),(30,300,1,-1)):
   with self.assertRaises(ValueError):monthly_cost(*args)
if __name__=='__main__':unittest.main()
