import unittest
from email.message import Message
from test_community_mini_merchant import SameMiniMerchant
from scripts.community_h5 import H5
from scripts.community_h5_context import current
class H5Recovery(unittest.TestCase):
 def setUp(self):
  self.f=SameMiniMerchant();self.f.setUp();self.h=H5(self.f.fx.gateway,self.f.onboarding,self.f.service)
  self.headers=Message();r,c=self.h.dispatch('/h5/session/login',self.headers,{'email':'one@example.org','password':'FixturePassword123!'})
  self.headers['Cookie']=c.split(';')[0];self.headers['X-CSRF-Token']=r['csrf'];self.token=c.split(';')[0].split('=',1)[1]
 def tearDown(self):self.f.tearDown()
 def test_context_ends_and_original_mini_denies_web_token(self):
  r,_=self.h.dispatch('/h5/merchant',self.headers,{'scene':'shop1','operation':'onboarding','params':{'operation':'mine','params':{}}});self.assertEqual(r['applications'],[])
  self.assertIsNone(current(self.f.fx.identity,self.token))
  with self.assertRaises(PermissionError):self.f.fx.identity.applicant_context(self.token)
 def test_live_project_removal_denied_and_context_reset(self):
  from scripts.community_h5_context import authorized,resolve
  with authorized(self.f.fx.identity,self.token,self.headers['X-CSRF-Token']):
   self.assertEqual(resolve(self.f.fx.identity,self.token,'shop1')[0],self.f.fx.uid1)
  self.f.fx.center.db.execute("DELETE FROM members WHERE user_id=?",(self.f.fx.uid1,))
  with self.assertRaises(PermissionError):
   with authorized(self.f.fx.identity,self.token,self.headers['X-CSRF-Token']):resolve(self.f.fx.identity,self.token,'shop1')
  self.assertIsNone(current(self.f.fx.identity,self.token))
 def test_logout_revokes_future_h5_use(self):
  self.h.dispatch('/h5/session/logout',self.headers,{})
  with self.assertRaises(PermissionError):self.h.dispatch('/h5/api',self.headers,{'scene':'','operation':'customer.directory','params':{}})
 def test_other_account_cannot_read_application_or_merchant_workspace(self):
  application=self.f.draft()['application']
  r,c=self.h.dispatch('/h5/session/login',Message(),{'email':'two@example.org','password':'FixturePassword123!'})
  h=Message();h['Cookie']=c.split(';')[0];h['X-CSRF-Token']=r['csrf']
  for scene in ('','shop1'):
   with self.assertRaises(PermissionError):self.h.dispatch('/h5/merchant',h,{'scene':scene,'operation':'onboarding','params':{'operation':'read','params':{'application':application}}})
  with self.assertRaises(PermissionError):self.h.dispatch('/h5/merchant',h,{'scene':'shop1','operation':'read','params':{'workspace':'merchant','operation':'community.orders','params':{}}})
  self.assertIsNone(current(self.f.fx.identity,self.token))
 def test_reviewer_does_not_gain_original_consumer_scene(self):
  from scripts.community_h5_context import authorized,resolve
  self.f.fx.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.f.fx.uid1,))
  with self.assertRaises(PermissionError):
   with authorized(self.f.fx.identity,self.token,self.headers['X-CSRF-Token']):resolve(self.f.fx.identity,self.token,'shop1')
 def test_ocr_original_source_same_owner_and_other_account_denied(self):
  import base64
  from scripts.community_h5_context import authorized
  app=self.f.draft();self.f.fx.center.scanner=lambda data:True
  raw=b'\x89PNG\r\n\x1a\nSynthetic document, not a real credential'
  app,_=self.h.dispatch('/h5/merchant',self.headers,{'scene':'shop1','operation':'onboarding','params':{'operation':'upload','params':{'application':app['application'],'revision':app['revision'],'kind':'business_license','content_base64':base64.b64encode(raw).decode(),'expires_at':None}}})
  with authorized(self.f.fx.identity,self.token,self.headers['X-CSRF-Token']):
   source=self.f.service.ocr_source(self.token,'shop1',app['application'],'business_license');self.assertEqual(source['data'],raw);self.assertEqual(source['subject'],self.f.fx.uid1)
  session=self.f.fx.center.login('two@example.org','FixturePassword123!')
  with self.assertRaises(PermissionError):
   with authorized(self.f.fx.identity,session['token'],session['csrf']):self.f.service.ocr_source(session['token'],'shop1',app['application'],'business_license')
 def test_platform_identity_comes_from_original_center_configuration(self):
  r,_=self.h.dispatch('/h5/platform',self.headers,{})
  self.assertEqual(r,{'appid':self.f.fx.identity.appid,'source':'ORIGINAL_CENTER_CONFIGURATION'})
  with self.assertRaises(ValueError):self.h.dispatch('/h5/platform',self.headers,{'appid':'wx0000000000000000'})
  with self.assertRaises(PermissionError):self.h.dispatch('/h5/platform',Message(),{})
 def test_duplicate_csrf_denied(self):
  self.headers['X-CSRF-Token']='second'
  with self.assertRaises(PermissionError):self.h.dispatch('/h5/api',self.headers,{'scene':'','operation':'customer.directory','params':{}})
 def test_duplicate_cookie_denied(self):
  self.headers['Cookie']=self.headers['Cookie']
  with self.assertRaises(PermissionError):self.h.dispatch('/h5/api',self.headers,{'scene':'','operation':'customer.directory','params':{}})
 def test_unknown_route_denied(self):
  with self.assertRaises(PermissionError):self.h.dispatch('/h5/admin',self.headers,{})
 def test_check_is_consumer_identity_only(self):
  r,_=self.h.dispatch('/h5/session/check',self.headers,{});self.assertEqual(set(r),{'user_id'})
if __name__=='__main__':unittest.main()
