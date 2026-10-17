import copy
import importlib.util
from pathlib import Path
import unittest

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("guard",str(root/"scripts/community_wechat_sp_offline_guard.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture():
    return {"tenant_id":"tenant1","store_id":"store1","order_id":"order1",
            "sp_mchid":"1234567890","sub_mchid":None,
            "app_id":"wx1234567890abcdef","amount_fen":1250,"currency":"CNY",
            "payer_type":"UNVERIFIED_OFFLINE",
            "ad_slots":{"PREPAY_AD":{"creative_id":"before1","revision":"v1","enabled":True},
                        "POSTPAY_AD":{"creative_id":"after1","revision":"v2","enabled":False}},
            "merchant_binding_revision":"v1","price_revision":"v3"}

class OfflineGuardTests(unittest.TestCase):
    def test_no_merchant_is_offline_only(self):
        o=m.validate_checkout_snapshot(fixture())
        self.assertEqual(o["sub_merchant_status"],"ABSENT")
        self.assertEqual(o["payment"],"HOLD")
        self.assertEqual(o["profitsharing"],"HOLD")
        self.assertEqual(o["ad_pre_payment"],"before1")
        self.assertEqual(o["ad_post_payment"],"after1")
    def test_stable_digest(self):
        self.assertEqual(m.validate_checkout_snapshot(fixture()),m.validate_checkout_snapshot(fixture()))
    def test_amount_rejects_bool_negative_zero_and_float(self):
        for bad in (True,0,-1,0.1,100000001):
            x=fixture();x["amount_fen"]=bad
            with self.assertRaises(m.PaymentHold):m.validate_checkout_snapshot(x)
    def test_never_trusts_submerchant(self):
        x=fixture();x["sub_mchid"]="2345678901"
        self.assertEqual(m.validate_checkout_snapshot(x)["sub_merchant_status"],"UNVERIFIED")
        self.assertEqual(m.validate_checkout_snapshot(x)["payment"],"HOLD")
    def test_both_ads_required(self):
        for slot in ("PREPAY_AD","POSTPAY_AD"):
            x=fixture();del x["ad_slots"][slot]
            with self.assertRaises(m.PaymentHold):m.validate_checkout_snapshot(x)
    def test_ad_boolean_cannot_be_integer(self):
        x=fixture();x["ad_slots"]["POSTPAY_AD"]["enabled"]=1
        with self.assertRaises(m.PaymentHold):m.validate_checkout_snapshot(x)
    def test_cross_tenant_idempotency_scoped(self):
        a=fixture();b=copy.deepcopy(a);b["tenant_id"]="tenant2"
        self.assertNotEqual(m.validate_checkout_snapshot(a)["idempotency_scope"],
                            m.validate_checkout_snapshot(b)["idempotency_scope"])
        self.assertNotEqual(m.validate_checkout_snapshot(a)["snapshot_sha256"],
                            m.validate_checkout_snapshot(b)["snapshot_sha256"])
    def test_callback_never_posts_money(self):
        result=m.classify_payment_notification({"trade_state":"SUCCESS","transaction_id":"fake"})
        self.assertEqual(result["finance_effect"],"NONE")
        self.assertEqual(result["refund"],"HOLD")
    def test_callback_authentication_claim_denied(self):
        for name in ("verified","paid","success","authenticated"):
            with self.assertRaises(m.PaymentHold):m.classify_payment_notification({name:True})
    def test_stray_schema_refused(self):
        x=fixture();x["api_v3_key"]="unsafe"
        with self.assertRaises(m.PaymentHold):m.validate_checkout_snapshot(x)
if __name__=="__main__":unittest.main()
