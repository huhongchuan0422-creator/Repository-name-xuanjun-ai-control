"""Synthetic transport at the official boundary, never an actual collectable code."""
import unittest,json
from unittest.mock import Mock
import test_community_wechat_payment_activation as fixtures
from scripts.community_collection_code import CollectionCodes,CollectionCodeUnknown
from scripts.community_mini_login import MiniGateway

class CollectionCodeBoundary(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.WechatPaymentActivation.setUpClass()
 def setUp(self):
  self.fx=fixtures.WechatPaymentActivation();self.fx.setUp()
  self.payments=self.fx.configured_client()
  original=self.fx.fx.fx.fx
  self.gateway=original.gateway;self.gateway.payments=self.payments
  self.token=original.token('collection-test')
  self.codes=CollectionCodes(self.gateway,self.fx.fx.fx.service,self.fx.fx.operations)
  self.workspace=next(name for name,g in self.fx.fx.operations.grants.items() if g['role']=='MERCHANT_ADMIN')
  self.requests=[]
  def boundary(target,body,maximum):
   self.requests.append((target,body,maximum))
   if target=='/cgi-bin/stable_token':return json.dumps(dict(access_token='fixture_token_123456789',expires_in=7200)).encode()
   return b'\x89PNG\r\n\x1a\n'+b'ISOLATED_NOT_A_REAL_QR_CODE'*5
  self.codes._fetch=boundary
 def tearDown(self):self.fx.tearDown()
 def read(self):return self.codes.read(self.token,'shop1',self.workspace)
 def test_release_code_only_and_store_identity_never_client_controlled(self):
  result=self.read();self.assertEqual(result['kind'],'RELEASE_MINI_COLLECTION_CODE');self.assertFalse(result['payment_completed'])
  _,body,_=self.requests[-1]
  self.assertEqual(body,dict(scene='shop1',page='pages/checkout/index',check_path=True,env_version='release',width=1280))
  self.assertNotIn('access_token',result);self.assertNotIn('secret',result)
 def test_different_app_provider_is_rejected_before_io(self):
  self.gateway.provider.appid='wx0000000000000000'
  with self.assertRaises(PermissionError):CollectionCodes(self.gateway,self.fx.fx.fx.service,self.fx.fx.operations)
  self.assertEqual(self.requests,[])
 def test_revocation_before_and_during_io_denies_image(self):
  self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_MERCHANT_OPENING'")
  with self.assertRaises(PermissionError):self.read()
  self.assertEqual(self.requests,[])
 def test_network_or_json_error_never_returns_a_preview_code(self):
  self.codes._fetch=lambda *args:json.dumps(dict(errcode=40013,errmsg='fixture')).encode()
  with self.assertRaises(CollectionCodeUnknown):self.read()
 def test_recheck_after_image_io_rejects_lost_authority(self):
  fetch=self.codes._fetch
  def changed(target,body,maximum):
   raw=fetch(target,body,maximum)
   if '/wxa/' in target:self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_MERCHANT_OPENING'")
   return raw
  self.codes._fetch=changed
  with self.assertRaises(PermissionError):self.read()

if __name__=='__main__':unittest.main()
