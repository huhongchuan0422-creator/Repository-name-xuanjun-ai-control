"""Real original Center/session and scoped grants; no provider IO or funds."""
import copy,json,unittest
from email.message import Message
import test_community_reports as fixture
from scripts.community_web_session import WebSession,COOKIE
from scripts.community_merchant_bills import MerchantBills,PERMISSION
from scripts.community_saas_phase2 import Principal

class FinanceBootstrap(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixture.CommunityReportJourney.setUpClass()
 def setUp(self):
  self.fx=fixture.CommunityReportJourney();self.fx.setUp();self.addCleanup(self.fx.tearDown)
  self.c,self.ops,self.actions=self.fx.c,self.fx.ops,self.fx.actions
  self.actions._call=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NO_PROVIDER_IO'))
  self.fx.reader._fetch=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NO_PROVIDER_IO'))
  g,p=self.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance')
  self.billgrant=dict(finance_workspace='finance',user_id=g['user_id'],project=g['project'],tenant_id=g['scope']['tenant_id'],merchant_id=g['scope']['merchant_id'],sp_mchid=self.actions.reader._mchid,sub_mchid=p['sub_mchid'],revision=1,permission=PERMISSION)
  self.bills=MerchantBills(self.actions,{'bill':self.billgrant})
  self.service=WebSession(self.c,self.ops,self.fx.communities,provider_actions=self.actions,merchant_bills=self.bills)
  self.h=Message();self.h['Cookie']=COOKIE+'='+self.fx.web['token'];self.h['X-CSRF-Token']=self.fx.web['csrf']
 def check(self):return self.service.dispatch('/community/session/check',self.h,{},'127.0.0.1')[0]
 def options(self):return next(w['finance_options'] for w in self.check()['workspaces'] if w['workspace']=='merchant' and w['kind']=='MERCHANT')
 def test_same_scope_separate_authority_is_options_only_no_auto_selection(self):
  result=self.check();self.assertEqual(self.options(),{'provider':[{'workspace':'finance'}],'merchant_bill':[{'workspace':'bill'}]})
  self.assertNotIn('providerWorkspace',json.dumps(result));self.assertNotIn('sub_mchid',json.dumps(result));self.assertNotIn('123456789',json.dumps(result))
 def test_absent_backend_and_absent_explicit_bill_grant(self):
  self.service=WebSession(self.c,self.ops,self.fx.communities)
  self.assertEqual(self.options(),{'provider':[],'merchant_bill':[]})
  self.service=WebSession(self.c,self.ops,self.fx.communities,provider_actions=self.actions,merchant_bills=MerchantBills(self.actions))
  self.assertEqual(self.options(),{'provider':[{'workspace':'finance'}],'merchant_bill':[]})
 def test_merchant_role_never_finance_and_foreign_user_excluded(self):
  self.ops.grants['finance']['user_id']=self.fx.fx.uid2
  self.assertEqual(self.options(),{'provider':[],'merchant_bill':[]})
 def test_multiple_same_scope_options_remain_distinct(self):
  self.ops.grants['finance2']=dict(self.ops.grants['finance'])
  self.bills.grants['bill2']=dict(self.billgrant)
  self.assertEqual(self.options(),{'provider':[{'workspace':'finance'},{'workspace':'finance2'}],'merchant_bill':[{'workspace':'bill'},{'workspace':'bill2'}]})
 def foreign_scope(self,field):
  original=self.ops.grants['finance'];scope=dict(original['scope']);scope[field]='foreign_'+field
  principal=Principal(scope['tenant_id'],'FINANCE_APPROVER');self.ops.runtime.bindings[principal]=scope
  self.ops.grants['foreignfinance']={**original,'principal':principal,'role':principal.role,'tenant':scope['tenant_id'],'scope':scope}
  _,policy=self.actions._authorize(self.fx.web['token'],self.fx.web['csrf'],'finance');policy=copy.deepcopy(policy);policy['sub_mchid']='1234567899'
  self.actions.bindings[tuple(scope[k] for k in ('tenant_id','merchant_id','store_id'))]=policy
  self.assertEqual(self.options()['provider'],[{'workspace':'finance'}])
 def test_other_tenant_not_project_admitted(self):self.foreign_scope('tenant_id')
 def test_same_tenant_other_merchant_not_selected_scope(self):self.foreign_scope('merchant_id')
 def test_same_tenant_merchant_other_store_not_selected_scope(self):self.foreign_scope('store_id')
 def test_bill_anchor_scope_is_independent_not_provider_selection(self):
  self.bills.grants['bill']['merchant_id']='foreign'
  self.assertEqual(self.options(),{'provider':[{'workspace':'finance'}],'merchant_bill':[]})
 def test_revocation_and_client_scope_injection_denied(self):
  self.options();self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.fx.uid1,))
  with self.assertRaises(PermissionError):self.check()
  with self.assertRaises(ValueError):self.service.dispatch('/community/session/check',self.h,{'providerWorkspace':'finance'},'127.0.0.1')
 def test_original_composition_identity_mismatch_rejected(self):
  with self.assertRaises(ValueError):WebSession(self.c,None,provider_actions=self.actions)
  with self.assertRaises(ValueError):WebSession(self.c,self.ops,merchant_bills=self.bills)
if __name__=='__main__':unittest.main()
