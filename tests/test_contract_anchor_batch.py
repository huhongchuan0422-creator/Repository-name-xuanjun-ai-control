import unittest,hashlib,copy
from scripts.contract_anchor_batch import due,batch,verify
class BatchTests(unittest.TestCase):
 def test_either_threshold_and_empty(self):
  self.assertFalse(due(0,999));self.assertFalse(due(1,299));self.assertTrue(due(100,0));self.assertTrue(due(1,300))
 def test_odd_even_single(self):
  for n in (1,2,3,100):
   c=[hashlib.sha256(str(i).encode()).hexdigest() for i in range(n)];b=batch(c)
   self.assertEqual(b['chain_status'],'NOT_SUBMITTED')
   for i in range(n):self.assertTrue(verify(c[i],b['proofs'][i],b['root']))
   self.assertFalse(verify('0'*64,b['proofs'][0],b['root']))
 def test_invalid(self):
  for c in ([],['z'*64],['a'*64,'a'*64]):
   with self.assertRaises(ValueError):batch(c)
  with self.assertRaises(ValueError):due(True,1)
if __name__=='__main__':unittest.main()
