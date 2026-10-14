"""Stage5 Phase1 cross-module simulation smoke checks, no real payment."""
import unittest
from scripts.community_merchant_contract import signed_qr
from scripts.community_checkout import begin, result, split_preview
from scripts.community_order_store import connect, create_order, state, simulated_transition
from scripts.community_ad_contract import AMOUNT, SUCCESS

S={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
K=b"k"*32
class Phase1Smoke(unittest.TestCase):
    def setUp(self):
        self.db=connect()
    def tearDown(self):
        self.db.close()
    def test_scope_qr_checkout_storage_and_simulated_terminal(self):
        qr=signed_qr(S,"scan",200,K)
        checkout=begin(qr,S,"scan",100,K,125,"r1","mini")
        self.assertEqual(checkout["ad_slot"],AMOUNT)
        self.assertFalse(checkout["provider_started"])
        create_order(self.db,S,"r1",125)
        self.assertEqual(state(self.db,S,"r1")["state"],"PENDING")
        evidence={"simulation_only":True,"scope":dict(S),"reference":"r1","amount_minor":125,"provider_transaction_id":"tx1"}
        simulated_transition(self.db,S,"r1","event1","SUCCESS",evidence)
        self.assertEqual(state(self.db,S,"r1")["state"],"SUCCESS")
        # The real receipt guard must NOT elevate the simulated transaction.
        self.assertFalse(result(checkout,{"state":"SUCCESS","reference":"r1","amount_minor":125,
                                          "currency":"CNY","scope":S})["paid"])
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_PAYMENT"):
            split_preview(checkout,evidence,{"merchant":10000})
    def test_cross_store_scope_denied(self):
        qr=signed_qr(S,"scan",200,K)
        with self.assertRaises(ValueError):
            begin(qr,dict(S,store_id="s2"),"scan",100,K,125,"r1","mini")
    def test_two_ad_slots_require_distinct_payment_truth(self):
        self.assertNotEqual(AMOUNT,SUCCESS)
        self.assertFalse(result(begin(signed_qr(S,"scan",200,K),S,"scan",100,K,100,"r2","official_h5"),
                                {"state":"SUCCESS","server_verified":True,"provider_reconciled":False})["paid"])
if __name__=="__main__":
    unittest.main()
