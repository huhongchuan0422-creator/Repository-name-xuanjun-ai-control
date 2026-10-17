"""End-to-end offline candidate only: provider port -> frozen journal -> plain preview.

Fixtures are synthetic. Does not attest actual Customer/Finance or legal signing.
"""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from single_contract_freeze import ContractHold
from single_contract_journal import Journal
from single_contract_preview import render
from single_contract_trusted_source_port import stage_from_trusted_source
spec=importlib.util.spec_from_file_location("source_fixture",str(ROOT/"tests/test_single_contract_trusted_source_port.py"))
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

class StagedE2ETests(unittest.TestCase):
    def test_full_offline_readback_and_no_external_effect(self):
        source=fixture.FakeSource()
        with tempfile.TemporaryDirectory() as d:
            db=Journal(str(pathlib.Path(d)/"frozen.sqlite"))
            db.setup()
            staging=stage_from_trusted_source(source,"actor-one","prj1","contract1")
            stored=db.submit("prj1","cust1","request1",source.snapshot)
            self.assertEqual(stored,staging["staging"]["candidate"])
            reread=db.read("prj1","cust1","contract1","request1")
            preview=render(reread)
            self.assertEqual(preview["content_type"],"text/plain; charset=utf-8")
            self.assertIn("4150.00",preview["text"])
            self.assertIn("3000.00",preview["text"])
            self.assertEqual(preview["contract_snapshot_sha256"],
                             staging["staging"]["candidate"]["contract_document_hash"])
            for key in ("contract_sign","payment","procurement","development_start"):
                self.assertEqual(stored[key],"HOLD")
                self.assertEqual(staging[key],"HOLD")
    def test_revoked_context_no_insert(self):
        source=fixture.FakeSource();source.allow=False
        with tempfile.TemporaryDirectory() as d:
            db=Journal(str(pathlib.Path(d)/"frozen.sqlite"));db.setup()
            with self.assertRaisesRegex(ContractHold,"SOURCE_REVISION_REVOKED"):
                stage_from_trusted_source(source,"actor-one","prj1","contract1")
            with self.assertRaisesRegex(ContractHold,"CANDIDATE_NOT_FOUND"):
                db.read("prj1","cust1","contract1","request1")

if __name__=="__main__":
    unittest.main()
