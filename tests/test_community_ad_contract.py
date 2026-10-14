import unittest
from datetime import datetime, timedelta, timezone
from scripts.community_ad_contract import *

class CommunityAdOfflineTests(unittest.TestCase):
    def test_01_slots(self):
        self.assertTrue(slots_valid([AMOUNT, SUCCESS]))
        self.assertFalse(slots_valid([AMOUNT, AMOUNT]))
    def test_02_provider_truth(self):
        self.assertFalse(verified_receipt({"state":"SUCCESS","server_verified":False,"provider_reconciled":True}))
        self.assertTrue(verified_receipt({"state":"SUCCESS","server_verified":True,"provider_reconciled":True}))
    def test_03_tenant_scope(self):
        a={"tenant_id":"a","merchant_id":"m","store_id":"s"}
        self.assertTrue(within_scope(a,dict(a)))
        self.assertFalse(within_scope(a,dict(a,tenant_id="b")))
    def test_04_schedule(self):
        now=datetime.now(timezone.utc)
        req={"tenant_id":"a","merchant_id":"m","store_id":"s"}
        a=dict(req,id="a",slot=AMOUNT,status="ACTIVE",priority=2,starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=1))
        self.assertEqual(select_active([dict(a,id="b"),a],req,AMOUNT,now)["id"],"a")
        self.assertIsNone(select_active([a],dict(req,tenant_id="b"),AMOUNT,now))
    def test_05_url(self):
        self.assertTrue(safe_creative_url("https://example.org/campaign"))
        for u in ("javascript:alert(1)","http://example.org","https://127.0.0.1","https://user:pass@example.org","https://localhost"):
            self.assertFalse(safe_creative_url(u))
    def test_06_fallback(self):
        self.assertTrue(fallback(AMOUNT,None)["payment_enabled"])
        self.assertIsNone(fallback(SUCCESS,None)["creative"])
    def test_07_metric_dedup(self):
        e={"event_id":"evt","tenant_id":"a","merchant_id":"m","slot":AMOUNT,"kind":"CLICK"}
        self.assertTrue(accept_metric(e,set()))
        self.assertFalse(accept_metric(e,{("a","m",AMOUNT,"CLICK","evt")}))
    def test_08_audit(self):
        actor={"authenticated":True,"role":"MERCHANT_ADMIN","actor_id":"x"}
        self.assertTrue(audit_transition("APPROVED","ACTIVE",actor))
        self.assertFalse(audit_transition("ARCHIVED","ACTIVE",actor))
    def test_09_hosted(self):
        p={"state":"SUCCESS","server_verified":True,"provider_reconciled":True}
        self.assertTrue(ad_surface_allowed("OWN_SUCCESS_RECEIPT",p))
        self.assertFalse(ad_surface_allowed("PROVIDER_HOSTED",p))
    def test_10_refund(self):
        p={"amount_minor":100,"currency":"CNY","refund_minor":0,"settlement_state":"PAID"}
        self.assertTrue(refund_invariant(p,dict(p,ad_slot="new")))
        self.assertFalse(refund_invariant(p,dict(p,refund_minor=100)))

if __name__=="__main__":
    unittest.main()
