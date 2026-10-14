import unittest
from scripts.community_merchant_contract import *

class Stage5MerchantBatch2(unittest.TestCase):
    def setUp(self):
        self.sc={"tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
        self.key=b"K"*32
    def test_01_storefront(self):
        p={"name":"Store","description":"Services","contact":"123","status":"ACTIVE"}
        self.assertEqual(storefront(self.sc,p)["name"],"Store")
        with self.assertRaises(ValueError):storefront(self.sc,dict(p,status="SUSPENDED"))
    def test_02_hours(self):
        store={"scope":self.sc,"hours":[{"weekday":1,"start":480,"end":1020}]}
        self.assertTrue(opening_hours(self.sc,store,1,600))
        self.assertFalse(opening_hours(self.sc,store,1,1020))
        with self.assertRaises(ValueError):opening_hours(self.sc,dict(store,scope=dict(self.sc,tenant_id="t2")),1,600)
    def test_03_catalog(self):
        a={"scope":self.sc,"id":"A","name":"Service","status":"ACTIVE","sort":1}
        self.assertEqual(catalog(self.sc,[a])[0]["id"],"A")
        with self.assertRaises(ValueError):catalog(self.sc,[a,a])
        with self.assertRaises(ValueError):catalog(self.sc,[dict(a,scope=dict(self.sc,tenant_id="other"))])
    def test_04_qr_auth(self):
        token=signed_qr(self.sc,"pos1",500,self.key)
        self.assertTrue(verify_qr(token,self.sc,"pos1",499,self.key))
        self.assertFalse(verify_qr(token,self.sc,"pos1",500,self.key))
        self.assertFalse(verify_qr(token,dict(self.sc,merchant_id="m2"),"pos1",499,self.key))
        self.assertFalse(verify_qr(token,self.sc,"pos1",499,b"Z"*32))
    def test_05_amount(self):
        self.assertEqual(payment_amount(100,"CNY","order1")["amount_minor"],100)
        for a in (-1,0,True,10.5,100000001):
            with self.assertRaises(ValueError):payment_amount(a,"CNY","order1")
    def test_06_miniprogram_routes(self):
        self.assertEqual(route("mini","storefront",self.sc)["page"],"storefront")
        with self.assertRaises(ValueError):route("mini","unknown",self.sc)
    def test_07_official_h5_routes(self):
        self.assertEqual(route("official_h5","amount",self.sc)["page"],"amount")
        with self.assertRaises(ValueError):route("hosted_provider","amount",self.sc)
    def test_08_merchant_roles(self):
        user={"authenticated":True,"role":"STORE_STAFF","tenant_id":"t1","merchant_id":"m1","store_id":"s1"}
        self.assertTrue(merchant_authorized(user,self.sc,"VIEW"))
        self.assertFalse(merchant_authorized(user,self.sc,"EDIT"))
        self.assertFalse(merchant_authorized(dict(user,store_id="s2"),self.sc,"VIEW"))
    def test_09_platform_roles(self):
        reviewer={"authenticated":True,"role":"PLATFORM_REVIEWER"}
        self.assertTrue(platform_authorized(reviewer,"MERCHANT_APPROVAL"))
        self.assertFalse(platform_authorized(reviewer,"SPLIT_APPROVAL"))
        self.assertTrue(platform_authorized({"authenticated":True,"role":"FINANCE_APPROVER","second_factor":True},"SPLIT_APPROVAL"))
    def test_10_split_conservation(self):
        out=split_amounts(101,{"charity":3000,"merchant":7000})
        self.assertEqual(sum(out["shares_minor"].values()),101)
        self.assertFalse(out["provider_settlement_verified"])
        out=split_amounts(100,{"charity":1000,"merchant":9000},refund_minor=20)
        self.assertEqual(sum(out["shares_minor"].values()),80)
    def test_11_qr_tamper(self):
        token=signed_qr(self.sc,"pos1",500,self.key)
        token["payload"]["context"]="pos2"
        self.assertFalse(verify_qr(token,self.sc,"pos2",499,self.key))
    def test_12_invalid_splits(self):
        for x in ({"a":100,"b":9800},{"a":-1,"b":10001},{}):
            with self.assertRaises(ValueError):split_amounts(100,x)
    def test_13_tenant_roles(self):
        user={"authenticated":True,"role":"MERCHANT_ADMIN","tenant_id":"other","merchant_id":"m1"}
        self.assertFalse(merchant_authorized(user,self.sc,"EDIT"))
    def test_14_split_rounding(self):
        out=split_amounts(1,{"a":5000,"b":5000})
        self.assertEqual(out["shares_minor"],{"a":1,"b":0})
    def test_15_invalid_catalog_properties(self):
        a={"scope":self.sc,"id":"A","name":"Service","status":"ACTIVE","sort":True}
        with self.assertRaises(ValueError):catalog(self.sc,[a])
    def test_16_invalid_hour_overlap_not_allowed(self):
        store={"scope":self.sc,"hours":[{"weekday":1,"start":500,"end":100}]}
        with self.assertRaises(ValueError):opening_hours(self.sc,store,1,600)

if __name__=="__main__":unittest.main()
