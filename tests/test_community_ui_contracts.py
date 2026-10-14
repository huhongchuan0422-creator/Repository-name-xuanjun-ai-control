import unittest
from scripts.community_ui_contracts import (storefront_view, store_list, service_cards, mini_route, h5_route,
    amount_screen, pending_screen, merchant_orders, merchant_ads, platform_decision)
S={'tenant_id':'t1','merchant_id':'m1','store_id':'s1'}
A={'authenticated':True,'tenant_id':'t1','merchant_id':'m1','store_id':'s1','role':'MERCHANT_ADMIN'}
class UIContracts(unittest.TestCase):
    def test_21_storefront(self):
        self.assertTrue(storefront_view(S,{'status':'ACTIVE','name':'商户','description':'说明'})['escape_required'])
    def test_22_store_list(self):
        self.assertEqual(len(store_list(S,[{'tenant_id':'t1','merchant_id':'m1','store_id':'s2','name':'门店'}])),1)
        with self.assertRaises(ValueError): store_list(S,[{'tenant_id':'t2','merchant_id':'m1','store_id':'s1','name':'bad'}])
    def test_23_services(self):
        self.assertEqual(service_cards(S,[{'scope':S,'id':'p1','name':'服务','active':True}])[0]['id'],'p1')
        with self.assertRaises(ValueError): service_cards(S,[{'scope':dict(S,merchant_id='m2'),'id':'p1','name':'bad','active':True}])
    def test_24_mini(self):
        self.assertEqual(mini_route(S,'amount')['channel'],'mini')
    def test_25_h5(self):
        self.assertEqual(h5_route(S,'result')['channel'],'official_h5')
    def test_26_amount(self):
        self.assertEqual(amount_screen(S,100)['ad_slot'],'AD_SLOT_PAYMENT_AMOUNT')
        with self.assertRaises(ValueError): amount_screen(S,True)
    def test_27_pending(self):
        self.assertIsNone(pending_screen(S)['success_ad_slot'])
    def test_28_orders(self):
        self.assertEqual(merchant_orders(A,S,[{'scope':S,'reference':'r1','state':'PENDING'}])[0]['reference'],'r1')
        with self.assertRaises(ValueError): merchant_orders(A,S,[{'scope':dict(S,store_id='bad'),'reference':'r1','state':'SUCCESS'}])
        with self.assertRaises(ValueError): merchant_orders(dict(A,role='STORE_STAFF',store_id='elsewhere'),S,[])
    def test_29_ads(self):
        self.assertEqual(merchant_ads(A,S,[{'scope':S,'id':'ad1','status':'DRAFT'}])[0]['id'],'ad1')
        with self.assertRaises(ValueError): merchant_ads(dict(A,role='STORE_STAFF'),S,[])
    def test_30_platform(self):
        with self.assertRaises(ValueError):
            platform_decision({'authenticated':True,'role':'PLATFORM_REVIEWER'},'SPLIT_APPROVAL',{'id':'x'})
        self.assertEqual(platform_decision({'authenticated':True,'role':'FINANCE_APPROVER','second_factor':True},'SPLIT_APPROVAL',{'id':'x'})['action'],'SPLIT_APPROVAL')
if __name__=='__main__': unittest.main()
