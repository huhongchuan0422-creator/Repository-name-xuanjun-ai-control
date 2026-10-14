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
        a=dict(req,id="a",slot=AMOUNT,status="ACTIVE",moderation="APPROVED",priority=2,starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=1))
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
        self.assertFalse(audit_transition("APPROVED","ACTIVE",actor))
        self.assertTrue(audit_transition("APPROVED","ACTIVE",dict(actor,role="PLATFORM_ADMIN")))
        self.assertFalse(audit_transition("ARCHIVED","ACTIVE",actor))
    def test_09_hosted(self):
        p={"state":"SUCCESS","server_verified":True,"provider_reconciled":True}
        self.assertTrue(ad_surface_allowed("OWN_SUCCESS_RECEIPT",p))
        self.assertFalse(ad_surface_allowed("PROVIDER_HOSTED",p))
    def test_10_refund(self):
        p={"amount_minor":100,"currency":"CNY","refund_minor":0,"settlement_state":"PAID"}
        self.assertTrue(refund_invariant(p,dict(p,ad_slot="new")))
        self.assertFalse(refund_invariant(p,dict(p,refund_minor=100)))

    def test_11_moderation_required(self):
        now=datetime.now(timezone.utc)
        req={"tenant_id":"a","merchant_id":"m","store_id":"s"}
        ad=dict(req,id="a",slot=AMOUNT,status="ACTIVE",priority=1,
                starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=1))
        self.assertIsNone(select_active([ad],req,AMOUNT,now))
        self.assertIsNotNone(select_active([dict(ad,moderation="APPROVED")],req,AMOUNT,now))

    def test_12_malformed_ad_list_and_scope(self):
        now=datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            select_active([None],{},AMOUNT,now)
        with self.assertRaises(ValueError):
            select_active([{}]*1001,{},AMOUNT,now)

    def test_13_url_rejects_ipv4_ipv6_trailing_period_unicode(self):
        for url in ("https://[::1]/","https://192.168.1.1/", "https://example.org./",
                    "https://exaｍple.org", "https://example.org:444/"):
            self.assertFalse(safe_creative_url(url))

    def test_14_tenant_admin_cannot_manage_other_merchant(self):
        actor={"authenticated":True,"role":"MERCHANT_ADMIN","actor_id":"actor",
               "tenant_id":"t1","merchant_id":"m1"}
        self.assertTrue(audit_transition("APPROVED","ACTIVE",actor,
                                        {"tenant_id":"t1","merchant_id":"m1"}))
        self.assertFalse(audit_transition("APPROVED","ACTIVE",actor,
                                         {"tenant_id":"t2","merchant_id":"m1"}))
        self.assertFalse(audit_transition("APPROVED","ACTIVE",actor,
                                         {"tenant_id":"t1","merchant_id":"m2"}))

    def test_15_result_slot_fail_closed(self):
        self.assertIsNone(result_slot_for_payment({"state":"SUCCESS","server_verified":True}))
        self.assertEqual(result_slot_for_payment({"state":"SUCCESS","server_verified":True,
                                                  "provider_reconciled":True}),SUCCESS)

    def test_16_metric_key_separates_slot_and_kind(self):
        event={"tenant_id":"t","merchant_id":"m","slot":AMOUNT,"kind":"CLICK","event_id":"id"}
        self.assertNotEqual(metric_key(event),metric_key(dict(event,slot=SUCCESS)))
        self.assertNotEqual(metric_key(event),metric_key(dict(event,kind="IMPRESSION")))
        with self.assertRaises(ValueError):
            metric_key(dict(event,event_id=""))

if __name__=="__main__":
    unittest.main()
