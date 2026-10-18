"""Real Ed25519 signing in test only, no production credentials or enrollment."""
import unittest
from scripts import pr122_customer_review as review,pr122_static_workflow as static
from scripts.pr122_customer_core import canonical,digest,Denied
from tests import test_pr122_customer_workflow_signature as base
class StaticSignatureTests(unittest.TestCase):
 setUp=base.WholeWorkflowSignatureTests.setUp
 prepare=base.WholeWorkflowSignatureTests.prepare
 fetch=base.WholeWorkflowSignatureTests.fetch
 def configure(self):
  self.plan['workflow_contract']={'schema':1,'stages':[dict(stage=s,input_sha256='a'*64,implementation_sha256='b'*64,adopt_receipt_sha256=None,recovery_actions=['RECONCILE_STATIC']) for s in static.STAGES]}
  self.plan.update(deployment_profile=static.PROFILE,permit_window_seconds=18000,static_baseline_sha256='c'*64,host_pins_sha256='d'*64)
  self.approval.update(attempt_policy=static.POLICY,max_executions=5,workflow_contract_sha256=digest(canonical(self.plan['workflow_contract'])),deployment_profile=static.PROFILE,permit_window_seconds=18000,static_baseline_sha256='c'*64,host_pins_sha256='d'*64)
  self.approval['expires_unix']=self.approval['issued_unix']+18000
  self.payload.update(workflow_contract_sha256=self.approval['workflow_contract_sha256'],deployment_profile=static.PROFILE,permit_window_seconds=18000,static_baseline_sha256='c'*64,host_pins_sha256='d'*64)
  self.payload['findings']['R3']['evidence_sha256']=['c'*64]
 def verify(self):return review.verify(self.comments[5],self.comments[4],self.approval,self.plan,self.trust,self.fetch)
 def test_exact_static_signature(self):
  self.configure();self.prepare();self.assertEqual(self.verify()['deployment_profile'],static.PROFILE)
 def test_old_signature_cannot_extend(self):
  self.configure();self.payload.pop('deployment_profile');self.prepare()
  with self.assertRaisesRegex(Denied,'PAYLOAD_SCHEMA'):self.verify()
 def test_baseline_signature_binding(self):
  self.configure();self.payload['static_baseline_sha256']='e'*64;self.prepare()
  with self.assertRaisesRegex(Denied,'STATIC_BINDING'):self.verify()
 def test_signed_five_hours(self):
  self.configure();self.payload['permit_window_seconds']=7200;self.prepare()
  with self.assertRaisesRegex(Denied,'FIVE_HOUR_WINDOW'):self.verify()
 def test_signed_stage_contract(self):
  self.configure();self.payload['workflow_contract_sha256']='e'*64;self.prepare()
  with self.assertRaisesRegex(Denied,'WORKFLOW_SCOPE'):self.verify()
