"""Source integration: genuinely active ads, scope and success receipt gate."""
import unittest
from scripts.community_merchant_store import open_store,upsert_profile
from scripts.community_ad_store import open_offline,create_campaign,change_campaign_state,review_creative
from scripts.community_storefront_snapshot import storefront_snapshot
from scripts.community_ad_contract import AMOUNT,SUCCESS,result_slot_for_payment

S={'tenant_id':'tenant1','merchant_id':'merchant1','store_id':'store1'}
T={'tenant_id':'tenant2','merchant_id':'merchant2','store_id':'store2'}
P={'name':'Merchant','description':'Description','contact':'Contact','status':'ACTIVE'}
def actor(scope):
 return {'authenticated':True,'role':'MERCHANT_ADMIN','actor_id':'owner',**{k:scope[k] for k in ('tenant_id','merchant_id')}}
MOD={'authenticated':True,'role':'PLATFORM_ADMIN','actor_id':'moderator'}
class IntegratedAdTests(unittest.TestCase):
 def setUp(self):
  self.m=open_store();self.a=open_offline()
  for s in (S,T):upsert_profile(self.m,s,actor(s),P)
 def tearDown(self):self.m.close();self.a.close()
 def active(self,s,slot,cid,priority):
  record={'id':cid,'slot':slot,'starts_at':100,'ends_at':300,'title':'Approved','target_url':'https://example.org/approved','priority':priority}
  create_campaign(self.a,s,record,actor(s),100)
  change_campaign_state(self.a,s,cid,'REVIEW',actor(s),101,1)
  review_creative(self.a,s,cid,True,MOD,102,2)
  change_campaign_state(self.a,s,cid,'APPROVED',actor(s),103,3)
  change_campaign_state(self.a,s,cid,'ACTIVE',actor(s),104,4)
 def test_approved_slots_are_independent(self):
  self.active(S,AMOUNT,'amountad',10);self.active(S,SUCCESS,'receiptad',2)
  r=storefront_snapshot(self.m,self.a,S,150)
  self.assertEqual(r['ads'][AMOUNT]['id'],'amountad')
  self.assertEqual(r['ads'][SUCCESS]['id'],'receiptad')
  self.assertFalse(r['provider_settlement_verified'])
 def test_scope_priority_and_expiry(self):
  self.active(S,AMOUNT,'low',1);self.active(S,AMOUNT,'high',10)
  self.active(T,AMOUNT,'foreign',100)
  self.assertEqual(storefront_snapshot(self.m,self.a,S,150)['ads'][AMOUNT]['id'],'high')
  self.assertEqual(storefront_snapshot(self.m,self.a,T,150)['ads'][AMOUNT]['id'],'foreign')
  self.assertIsNone(storefront_snapshot(self.m,self.a,S,300)['ads'][AMOUNT])
 def test_unapproved_ad_is_never_selected(self):
  create_campaign(self.a,S,{'id':'draft','slot':AMOUNT,'starts_at':100,'ends_at':300,
    'title':'Draft','target_url':'https://example.org/draft','priority':100},actor(S),100)
  self.assertIsNone(storefront_snapshot(self.m,self.a,S,150)['ads'][AMOUNT])
 def test_success_candidate_does_not_mean_success_page_allowed(self):
  self.active(S,SUCCESS,'receiptad',10)
  snapshot=storefront_snapshot(self.m,self.a,S,150)
  self.assertIsNotNone(snapshot['ads'][SUCCESS])
  self.assertIsNone(result_slot_for_payment({'state':'SUCCESS','server_verified':False,
                                               'provider_reconciled':True}))
if __name__=='__main__':unittest.main()
