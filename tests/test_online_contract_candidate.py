import unittest,copy
from datetime import datetime,timezone
from scripts.online_contract_candidate import evaluate
class PolicyTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,15,tzinfo=timezone.utc)
  self.d=dict(identity_verified=True,regional_legal_review=True,material_terms_presented=True,customer_confirmed=True,provider_confirmed=True,downloadable_evidence=True,contract_id='p1',version_hash='v1',confirmed_version_hash='v1',tenant_id='t1',actor_id='a1',region_policy_id='fixture-only',customer_type='BUSINESS',amount_minor=100,currency='CNY',authority=dict(verified=True,revoked=False,tenant_id='t1',actor_id='a1',contract_id='p1',action='ACCEPT_CONTRACT',valid_from='2026-10-01T00:00:00+00:00',valid_until='2026-11-01T00:00:00+00:00',limit_minor=100,currency='CNY'))
 def test_ready_not_legal_or_live(self):
  x=evaluate(self.d,self.now);self.assertEqual(x['status'],'OFFLINE_POLICY_READY');self.assertFalse(x['production_enabled']);self.assertEqual(x['legal_validity'],'NOT_DETERMINED')
 def test_required_evidence_strict(self):
  for k in ('identity_verified','regional_legal_review','material_terms_presented','customer_confirmed','provider_confirmed','downloadable_evidence'):
   for v in (False,'true',1,None):
    d=copy.deepcopy(self.d);d[k]=v;self.assertEqual(evaluate(d,self.now)['status'],'HOLD')
 def test_scope_revocation_and_amount(self):
  for k,v in [('tenant_id','other'),('actor_id','other'),('contract_id','other'),('action','VIEW'),('revoked',True),('verified',1),('limit_minor',99),('limit_minor',True),('currency','USD'),('valid_until','2026-10-15T00:00:00+00:00'),('valid_from','2026-10-16T00:00:00+00:00'),('valid_until','bad')]:
   d=copy.deepcopy(self.d);d['authority'][k]=v;self.assertEqual(evaluate(d,self.now)['status'],'HOLD',(k,v))
 def test_version_and_missing(self):
  d=copy.deepcopy(self.d);d['confirmed_version_hash']='v2';self.assertEqual(evaluate(d,self.now)['status'],'HOLD')
  d=copy.deepcopy(self.d);del d['authority'];self.assertEqual(evaluate(d,self.now)['status'],'HOLD')
 def test_person_no_enterprise_authority(self):
  self.d['customer_type']='PERSON';del self.d['authority'];self.assertEqual(evaluate(self.d,self.now)['status'],'OFFLINE_POLICY_READY')
 def test_malformed_and_unknown(self):
  for d in (None,{},dict(self.d,customer_type='UNKNOWN')):self.assertEqual(evaluate(d,self.now)['status'],'HOLD')
if __name__=='__main__':unittest.main()
