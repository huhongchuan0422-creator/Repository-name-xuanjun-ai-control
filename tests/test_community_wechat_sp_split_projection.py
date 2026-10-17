import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from community_wechat_sp_offline_guard import PaymentHold
from community_wechat_sp_split_projection import project_split
spec=importlib.util.spec_from_file_location("fixtures",str(ROOT/"tests/test_community_wechat_sp_offline_guard.py"))
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
def entries(): return [{"receiver_id":"store","amount_fen":700},{"receiver_id":"community","amount_fen":300}]
class OfflineSplitTests(unittest.TestCase):
    def test_conservation(self):
        r=project_split(fixtures.fixture(),entries(),100)
        self.assertEqual(r["gross_fen"],1250)
        self.assertEqual(r["available_fen"],1150)
        self.assertEqual(r["undistributed_fen"],150)
        self.assertEqual(r["real_split"],"HOLD")
        self.assertEqual(r["finance_write"],"DENIED")
    def test_too_much_split(self):
        with self.assertRaisesRegex(PaymentHold,"ALLOCATION_EXCEEDS_AVAILABLE"):
            project_split(fixtures.fixture(),[{"receiver_id":"a","amount_fen":1251}])
    def test_refund_bounds(self):
        for amount in (True,-1,1251,0.5,"100"):
            with self.assertRaises(PaymentHold):project_split(fixtures.fixture(),entries(),amount)
    def test_boolean_money_rejected(self):
        with self.assertRaises(PaymentHold):
            project_split(fixtures.fixture(),[{"receiver_id":"a","amount_fen":True}])
    def test_duplicate_receiver(self):
        with self.assertRaises(PaymentHold):
            project_split(fixtures.fixture(),[{"receiver_id":"a","amount_fen":10},{"receiver_id":"a","amount_fen":10}])
    def test_negative_split(self):
        with self.assertRaises(PaymentHold):
            project_split(fixtures.fixture(),[{"receiver_id":"a","amount_fen":-1}])
    def test_fully_refunded_zero_split(self):
        r=project_split(fixtures.fixture(),[{"receiver_id":"a","amount_fen":0}],1250)
        self.assertEqual(r["available_fen"],0)
        self.assertEqual(r["undistributed_fen"],0)
    def test_cross_tenant_scope(self):
        s=fixtures.fixture();s["tenant_id"]="other"
        a=project_split(fixtures.fixture(),entries())
        b=project_split(s,entries())
        self.assertNotEqual(a["idempotency_scope"],b["idempotency_scope"])
    def test_deterministic_no_payment(self):
        s=fixtures.fixture()
        self.assertEqual(project_split(s,entries()),project_split(s,entries()))
        self.assertEqual(project_split(s,entries())["provider_confirmation"],"NOT_VERIFIED")
if __name__=="__main__":unittest.main()
