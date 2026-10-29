"""Synthetic local DB projections only; no actual WeChat signature/financial claim."""
import json,hashlib,unittest
from test_community_reports import CommunityReportJourney
from scripts.community_order_provider_projection import project_verified_query,project_verified_refund
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.pr122_customer_core import canonical
class RefundObservations(unittest.TestCase):
 @classmethod
 def setUpClass(cls):CommunityReportJourney.setUpClass()
 def setUp(self):
  self.fx=CommunityReportJourney();self.fx.setUp();self.fx.basket();self.db=self.fx.fx.stage.demo.db
  self.fx.reader._fetch=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NO_NETWORK'))
  expected=dict(sp_mchid='1234567890',sub_mchid='1234567891',out_trade_no='fixture_order',amount_minor=101)
  observation=dict(source='SIGNED_PROVIDER_ORDER_QUERY',signature_key_id='fixture',out_trade_no='fixture_order',amount_minor=101,currency='CNY',provider_state='SUCCESS',transaction_id='123456789',body_sha256='a'*64)
  project_verified_query(self.db,DEMO_SCOPE,'basket',expected,observation,100,'fixture')
 def tearDown(self):self.fx.tearDown()
 def read(self,**kwargs):return self.fx.call('community_refunds',dict(community_id=self.fx.cid,after_id=''),**kwargs)
 def refund(self,number='refund1',amount=11):return project_verified_refund(self.db,DEMO_SCOPE,'basket',number,amount,101,'b'*64,101)
 def corrupt(self,**changes):
  value=dict(source='WECHAT_SIGNED_REFUND_RESULT',out_refund_no='corrupt',refund_minor=11,body_sha256='b'*64,observed_at=101,transaction_id='123456789');value.update(changes)
  key='wr_'+hashlib.sha256(canonical([DEMO_SCOPE,'basket',value['out_refund_no']])).hexdigest()[:48]
  self.db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',(key,*[DEMO_SCOPE[k] for k in ('tenant_id','merchant_id','store_id')],'basket','SUCCESS','SUCCESS',canonical(value).decode()));self.db.commit()
 def test_partial_refund_success_visible_and_no_sensitive_payload(self):
  self.refund();r=self.read();row=r['records'][0];self.assertEqual(row['order_state'],'SUCCESS');self.assertEqual(row['refund_observations'][0]['refund_minor'],11);self.assertEqual(row['refund_observations'][0]['currency'],'CNY');self.assertEqual(row['finance_status'],'UNCONFIRMED');self.assertFalse(row['funds_operation_executed']);self.assertEqual(r['page_returns_minor'],11)
  data=json.dumps(r);self.assertNotIn('transaction_id',data);self.assertNotIn('body_sha256',data);self.assertNotIn('123456789',data)
 def test_full_refund_and_duplicate_original_projection_not_double_count(self):
  self.refund(amount=101);self.refund(amount=101);row=self.read()['records'][0];self.assertEqual(row['order_state'],'REFUNDED');self.assertEqual(len(row['refund_observations']),1)
 def test_no_event_is_not_no_refund_claim_and_old_contract_unchanged(self):
  row=self.read()['records'][0];self.assertEqual(row['refund_observation_status'],'NO_RECORDED_VERIFIED_REFUND');self.assertEqual(row['refund_observations'],[])
  old=self.fx.call('community_orders',dict(community_id=self.fx.cid,after_id=''))['records'][0];self.assertNotIn('refund_observations',old)
 def test_other_community_same_actor_does_not_obtain_original_refund(self):
  self.refund();other=self.fx.call('register',dict(name='Other',description='Fixture',contact='private'))
  r=self.fx.call('community_refunds',dict(community_id=other['id'],after_id=''));self.assertEqual(r['records'],[])
 def test_foreign_actor_denied(self):
  self.refund()
  with self.assertRaises(PermissionError):self.read(workspace='other',web=self.fx.reviewer)
 def test_scope_fields_never_client_controlled(self):
  with self.assertRaises(ValueError):self.fx.call('community_refunds',dict(community_id=self.fx.cid,after_id='',tenant_id='foreign'))
 def test_foreign_scope_malformed_events_not_read(self):
  self.db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',('foreign','foreign','merchant1','store1','basket','SUCCESS','SUCCESS','secret-invalid'));self.db.commit();self.assertEqual(self.read()['records'][0]['refund_observations'],[])
 def foreign_event(self,field):
  identity=dict(DEMO_SCOPE);identity[field]='foreign_'+field
  self.db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',('foreign_'+field,*[identity[k] for k in ('tenant_id','merchant_id','store_id')],'basket','SUCCESS','SUCCESS','secret-invalid'))
  self.db.commit()
  self.refund()
  rows=self.read()['records'][0]['refund_observations']
  self.assertEqual([r['out_refund_no'] for r in rows],['refund1'])
  self.assertEqual(sum(r['refund_minor'] for r in rows),11)
 def test_same_merchant_store_other_tenant_event_isolated(self):self.foreign_event('tenant_id')
 def test_same_tenant_store_other_merchant_event_isolated(self):self.foreign_event('merchant_id')
 def test_same_tenant_merchant_other_store_event_isolated(self):self.foreign_event('store_id')
 def test_multiple_partial_refunds_accumulate_without_claiming_full_refund(self):
  self.refund('partial_one',11);self.refund('partial_two',20);self.refund('partial_two',20)
  r=self.read();row=r['records'][0]
  self.assertEqual(row['order_state'],'SUCCESS')
  self.assertEqual([v['out_refund_no'] for v in row['refund_observations']],['partial_one','partial_two'])
  self.assertEqual([v['refund_minor'] for v in row['refund_observations']],[11,20])
  self.assertEqual(r['page_returns_minor'],31)
 def test_source_is_saved_verified_projection_not_new_verification_or_settlement(self):
  self.refund();r=self.read();row=r['records'][0];event=row['refund_observations'][0]
  self.assertEqual(event['evidence_source'],'WECHAT_SIGNED_REFUND_RESULT')
  self.assertEqual(event['observation_status'],'RECORDED_SIGNED_SUCCESS')
  self.assertEqual(event['finance_status'],'UNCONFIRMED')
  self.assertEqual(row['refund_observation_status'],'RECORDED_SIGNED_REFUND_OBSERVATIONS')
  self.assertFalse(row['funds_operation_executed'])
  self.assertEqual(set(event),{'reference','out_refund_no','refund_minor','currency','observed_at','evidence_source','observation_status','finance_status'})
 def test_invalid_cursor_rejected(self):
  with self.assertRaises(ValueError):self.fx.call('community_refunds',dict(community_id=self.fx.cid,after_id='invalid'))
 def test_unknown_event_key_rejected(self):
  value=dict(source='WECHAT_SIGNED_REFUND_RESULT',out_refund_no='corrupt',refund_minor=11,body_sha256='b'*64,observed_at=101,transaction_id='123456789')
  self.db.execute('INSERT INTO order_events VALUES(?,?,?,?,?,?,?,?)',('incorrect',*[DEMO_SCOPE[k] for k in ('tenant_id','merchant_id','store_id')],'basket','SUCCESS','SUCCESS',canonical(value).decode()));self.db.commit()
  with self.assertRaisesRegex(ValueError,'COMMUNITY_REFUND_OBSERVATION_INTEGRITY_CONFLICT'):self.read()

def bad_case(changes):
 def test(self):
  self.corrupt(**changes)
  with self.assertRaisesRegex(ValueError,'COMMUNITY_REFUND_OBSERVATION_INTEGRITY_CONFLICT'):self.read()
 return test
for n,v in enumerate([{'refund_minor':True},{'refund_minor':1.5},{'refund_minor':-1},{'refund_minor':102},{'observed_at':True},{'body_sha256':'invalid'},{'transaction_id':'other'}]):setattr(RefundObservations,'test_bad_record_'+str(n),bad_case(v))
if __name__=='__main__':unittest.main()
