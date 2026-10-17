import copy
import importlib.util
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from community_wechat_sp_offline_guard import PaymentHold
from community_wechat_sp_mock_checkout_view import view
spec=importlib.util.spec_from_file_location("fixtures",str(ROOT/"tests/test_community_wechat_sp_offline_guard.py"))
fixtures=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

class MockCheckoutViews(unittest.TestCase):
    def checkout(self):
        x=fixtures.fixture()
        x["ad_slots"]["POSTPAY_AD"]["enabled"]=True
        return x
    def test_two_ads_simulated_success(self):
        x=self.checkout();v=view(x,"MOCK_PAID_SIMULATED","tenant1","store1")
        self.assertTrue(v["pre_payment_ad"]["visible"])
        self.assertTrue(v["post_payment_ad"]["visible"])
        self.assertFalse(v["payment_verified"])
        self.assertEqual(v["finance_effect"],"NONE")
        self.assertEqual(v["provider_payment"],"HOLD")
        self.assertEqual(v["profitsharing"],"HOLD")
    def test_unpaid_never_shows_after_ad(self):
        for s in ("MOCK_NOT_STARTED","MOCK_PENDING","MOCK_CANCELLED","MOCK_FAILED"):
            self.assertFalse(view(self.checkout(),s,"tenant1","store1")["post_payment_ad"]["visible"])
    def test_cross_tenant_denied(self):
        with self.assertRaisesRegex(PaymentHold,"TENANT_STORE_SCOPE_DENIED"):
            view(self.checkout(),"MOCK_PENDING","different","store1")
    def test_cross_store_denied(self):
        with self.assertRaisesRegex(PaymentHold,"TENANT_STORE_SCOPE_DENIED"):
            view(self.checkout(),"MOCK_PENDING","tenant1","another")
    def test_browser_payment_success_rejected(self):
        with self.assertRaisesRegex(PaymentHold,"UNTRUSTED_PAYMENT_STATE"):
            view(self.checkout(),"SUCCESS","tenant1","store1")
    def test_real_payment_cannot_be_claimed(self):
        with self.assertRaisesRegex(PaymentHold,"UNTRUSTED_PAYMENT_STATE"):
            view(self.checkout(),"PAID","tenant1","store1")
    def test_price_and_snapshot_immutable(self):
        x=self.checkout();before=copy.deepcopy(x)
        v=view(x,"MOCK_PAID_SIMULATED","tenant1","store1")
        self.assertEqual(v["display_amount_fen"],1250)
        self.assertEqual(x,before)
        self.assertEqual(v,view(x,"MOCK_PAID_SIMULATED","tenant1","store1"))
    def test_disabled_ads_stay_disabled(self):
        x=self.checkout()
        x["ad_slots"]["PREPAY_AD"]["enabled"]=False
        x["ad_slots"]["POSTPAY_AD"]["enabled"]=False
        v=view(x,"MOCK_PAID_SIMULATED","tenant1","store1")
        self.assertFalse(v["pre_payment_ad"]["visible"])
        self.assertFalse(v["post_payment_ad"]["visible"])
if __name__=="__main__":unittest.main()
