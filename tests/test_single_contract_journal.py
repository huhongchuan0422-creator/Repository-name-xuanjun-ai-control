"""Offline journal regressions, no production DB or signing provider."""
import copy
import importlib.util
import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from single_contract_journal import Journal
from single_contract_freeze import ContractHold
spec=importlib.util.spec_from_file_location("test_freeze",(str(ROOT/"tests/test_single_contract_freeze.py")))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sample=module.sample

class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(pathlib.Path(self.tmp.name)/"candidate.db")
        self.j=Journal(self.path)
        self.j.setup()
    def tearDown(self):
        self.tmp.cleanup()
    def test_idempotency_and_read(self):
        a=self.j.submit("prj1","cust1","req1",sample())
        self.assertEqual(a,self.j.submit("prj1","cust1","req1",sample()))
        self.assertEqual(a,self.j.read("prj1","contract1","req1"))
        self.assertEqual(a["payment"],"HOLD")
    def test_conflicting_request_rejected(self):
        self.j.submit("prj1","cust1","req1",sample())
        x=sample();x["quote_version"]="q2"
        with self.assertRaisesRegex(ContractHold,"IDEMPOTENCY_CONFLICT"):
            self.j.submit("prj1","cust1","req1",x)
    def test_duplicate_version_rejected(self):
        self.j.submit("prj1","cust1","req1",sample())
        with self.assertRaisesRegex(ContractHold,"DUPLICATE_CONTRACT_VERSION"):
            self.j.submit("prj1","cust1","req2",sample())
    def test_cross_customer_rejected(self):
        with self.assertRaisesRegex(ContractHold,"IDENTITY_SCOPE_MISMATCH"):
            self.j.submit("prj1","other","req1",sample())
        with self.assertRaisesRegex(ContractHold,"CANDIDATE_NOT_FOUND"):
            self.j.read("otherproject","contract1","req1")
    def test_append_only(self):
        self.j.submit("prj1","cust1","req1",sample())
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("DELETE FROM contract_frozen_candidate")
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("UPDATE contract_frozen_candidate SET candidate_sha='x'")
    def test_invalid_input_never_writes(self):
        with self.assertRaises(ContractHold):
            self.j.submit("prj1","cust1","req1",dict(sample(),quote_valid=False))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(0,db.execute("SELECT count(*) FROM contract_frozen_candidate").fetchone()[0])

if __name__=="__main__":
    unittest.main()
