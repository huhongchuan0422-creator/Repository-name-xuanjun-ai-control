"""Protected composition contract only; synthetic inputs, no provider or site IO."""
import base64,copy,unittest
from unittest.mock import patch,Mock
from scripts.community_platform_host import _commerce_policy,_wire_commerce

class HostCommercePolicy(unittest.TestCase):
 def policy(self):
  return dict(version=1,applyment_submission_enabled=True,provider_bindings=[],payment_admissions={},notifications=None,merchant_bill_grants={})
 def read(self,value):
  with patch('scripts.community_platform_host.load_protected',return_value=value):return _commerce_policy('/existing/private/policy.json')
 def test_exact_optin_without_inventing_grants(self):
  value,bindings,key=self.read(self.policy());self.assertTrue(value['applyment_submission_enabled']);self.assertEqual(bindings,{});self.assertIsNone(key)
 def test_malformed_or_extra_fields_rejected(self):
  for change in ({'version':True},{'applyment_submission_enabled':'yes'},{'provider_bindings':{}},{'payment_admissions':[]},{'merchant_bill_grants':[]},{'unknown':1}):
   with self.assertRaises(ValueError):self.read(dict(self.policy(),**change))
 def test_tuple_scope_is_lossless_and_duplicate_refused(self):
  item={'scope':dict(tenant_id='t',merchant_id='m',store_id='s'),'policy':{'original':'unchanged'}}
  p=dict(self.policy(),provider_bindings=[item]);_,bindings,_=self.read(p);self.assertEqual(bindings,{('t','m','s'):item['policy']})
  p['provider_bindings'].append(copy.deepcopy(item))
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.read(p)
 def test_notifications_require_original_admissions_and_32bytes(self):
  p=self.policy();p['notifications']={'api_v3_key_base64':base64.b64encode(b'x'*32).decode(),'path':'/wechat/community/notify'}
  with self.assertRaisesRegex(ValueError,'ADMISSIONS'):self.read(p)
  p['payment_admissions']={'original_scene':{'original':'policy'}};self.assertEqual(self.read(p)[2],b'x'*32)
  for raw in ('?',base64.b64encode(b'x'*31).decode()):
   p['notifications']['api_v3_key_base64']=raw
   with self.assertRaises(ValueError):self.read(p)
 def test_bill_grants_do_not_create_provider_authority(self):
  p=dict(self.policy(),merchant_bill_grants={'workspace':{'original':'grant'}})
  with self.assertRaisesRegex(ValueError,'BINDINGS'):self.read(p)
 def test_original_capability_order_and_exact_inputs(self):
  p=self.policy();p.update(provider_bindings=[{'scope':dict(tenant_id='t',merchant_id='m',store_id='s'),'policy':{'original':'policy'}}],payment_admissions={'scene':{'original':'admission'}},notifications={'api_v3_key_base64':base64.b64encode(b'x'*32).decode(),'path':'/wechat/community/notify'},merchant_bill_grants={'finance':{'original':'grant'}})
  app=Mock();reader=object();policy=self.read(p);_wire_commerce(app,reader,policy)
  self.assertEqual([c[0] for c in app.mock_calls],['configure_provider_actions','configure_dynamic_payments_from_applyments','configure_payment_notifications','configure_merchant_bills'])
  app.configure_provider_actions.assert_called_once_with(reader,policy[1]);app.configure_dynamic_payments_from_applyments.assert_called_once_with(reader,p['payment_admissions']);app.configure_payment_notifications.assert_called_once_with(b'x'*32,p['notifications']['path']);app.configure_merchant_bills.assert_called_once_with(p['merchant_bill_grants'])
 def test_absent_grants_are_not_enabled(self):
  app=Mock();_wire_commerce(app,object(),self.read(self.policy()));self.assertEqual(app.mock_calls,[])
if __name__=='__main__':unittest.main()
