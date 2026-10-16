import unittest
from scripts.customer_project_intake_contract import *
class ContractTests(unittest.TestCase):
 def test_verified_original_project(self):
  m={("u","p"):"project_editor"}
  self.assertTrue(can_submit("u","p","c","c",m))
  self.assertFalse(can_submit("u","other","c","c",m))
  self.assertFalse(can_submit("u","p","c","attacker",m))
  self.assertFalse(can_submit("u","p","c","c",{}))
 def test_incremental_flow(self):
  self.assertEqual(transition("NOT_STARTED","save_draft",True),"PARTIAL")
  self.assertEqual(transition("PARTIAL","submit",True),"SUBMITTED")
  self.assertEqual(transition("SUBMITTED","start_review",True),"UNDER_REVIEW")
  self.assertEqual(transition("UNDER_REVIEW","request_changes",True),"NEEDS_CORRECTION")
  with self.assertRaises(IntakeRejected):transition("PARTIAL","submit",False)
  with self.assertRaises(IntakeRejected):transition("ACCEPTED","save_draft",True)
 def test_guides(self):
  self.assertIn("SecretRef",GUIDES["wechat_miniapp"][1])
  self.assertIn("OAuth",GUIDES["douyin_oauth"][1])
if __name__=="__main__":unittest.main()

class AdditionalAuthorizationTests(unittest.TestCase):
 def test_reviewer_separation(self):
  from scripts.customer_project_intake_contract import apply_action,IntakeRejected
  m={("user","p"):"project_editor",("auditor","p"):"independent_reviewer"}
  self.assertEqual(apply_action("NOT_STARTED","save_draft","user","p","c","c",m,authenticated=True),"PARTIAL")
  with self.assertRaises(IntakeRejected):apply_action("UNDER_REVIEW","approve","user","p","c","c",m,submitter="user",authenticated=True)
  self.assertEqual(apply_action("UNDER_REVIEW","approve","auditor","p","c","c",m,submitter="user",authenticated=True),"ACCEPTED")
  with self.assertRaises(IntakeRejected):apply_action("UNDER_REVIEW","approve","auditor","p","c","c",m,submitter="auditor",authenticated=True)
  with self.assertRaises(IntakeRejected):apply_action("UNDER_REVIEW","approve","auditor","p","c","c",{},submitter="user",authenticated=True)
 def test_truthy_string_rejected(self):
  from scripts.customer_project_intake_contract import transition,IntakeRejected
  with self.assertRaises(IntakeRejected):transition("PARTIAL","submit","false")
