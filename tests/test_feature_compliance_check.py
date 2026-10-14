"""Positive and negative governance gate tests without GitHub/API requests."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.feature_compliance_check import validate, check_changed_paths

class GovernanceTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root=Path(self.temp.name)
    (self.root/"docs/development").mkdir(parents=True)
    (self.root/"tests").mkdir()
    (self.root/"governance").mkdir()
    (self.root/"docs/development/spec.md").write_text("### 6.15 Design\n### 12.9 Delivery\n",encoding="utf-8")
    (self.root/"tests/test_feature.py").write_text("pass\n")
    self.feature={"feature_id":"EXAMPLE_FEATURE","status":"IN_DEVELOPMENT",
      "design":{"document":"docs/development/spec.md","section":"6.15"},
      "development":{"document":"docs/development/spec.md","section":"12.9","phase":3},
      "acceptance":{"criteria":["works"],"tests":["tests/test_feature.py"]},
      "reuse":["existing module"]}
 def check(self):
    (self.root/"governance/features.json").write_text(json.dumps({"schema_version":1,"features":[self.feature]}))
    return validate(self.root,"governance/features.json")
 def test_compliant(self):self.assertEqual(self.check(),[])
 def test_missing_development(self):
    del self.feature["development"]
    self.assertTrue(any("DEVELOPMENT" in x for x in self.check()))
 def test_missing_acceptance(self):
    self.feature["acceptance"]["criteria"]=[]
    self.assertIn("EXAMPLE_FEATURE: MISSING_ACCEPTANCE_CRITERIA",self.check())
 def test_missing_test_file(self):
    self.feature["acceptance"]["tests"]=["tests/absent.py"]
    self.assertIn("EXAMPLE_FEATURE: ACCEPTANCE_TEST_NOT_FOUND",self.check())
 def test_premature_deployment(self):
    self.feature["status"]="DEPLOYED"
    self.assertIn("EXAMPLE_FEATURE: DEPLOYED_WITHOUT_RECEIPT",self.check())
 def test_no_evidence_claim(self):
    self.feature["status"]="VERIFIED"
    self.assertIn("EXAMPLE_FEATURE: VERIFIED_WITHOUT_EVIDENCE",self.check())
 def test_new_executable_requires_feature_mapping(self):
    self.check()
    self.assertIn("UNREGISTERED_ADDED_CODE: scripts/new_feature.py",
        check_changed_paths(self.root,"governance/features.json",[("A","scripts/new_feature.py")]))
    self.assertEqual(check_changed_paths(self.root,"governance/features.json",[("M","scripts/old.py")]),[])
 def test_registered_executable_passes(self):
    self.feature["paths"]=["scripts/new_feature.py"]
    self.check()
    self.assertEqual(check_changed_paths(self.root,"governance/features.json",[("A","scripts/new_feature.py")]),[])
 def test_unrelated_document_not_blocked(self):
    self.check()
    self.assertEqual(check_changed_paths(self.root,"governance/features.json",[("A","docs/readme.md")]),[])
 def test_no_path_escape(self):
    self.feature["design"]["document"]="docs/../../etc/passwd"
    self.assertIn("EXAMPLE_FEATURE: DESIGN_DOCUMENT_NOT_FOUND",self.check())

if __name__=="__main__":unittest.main()
