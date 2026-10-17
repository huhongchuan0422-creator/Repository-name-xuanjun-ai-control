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
        self.assertEqual(a,self.j.read("prj1","cust1","contract1","req1"))
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
            self.j.read("otherproject","cust1","contract1","req1")
    def test_same_project_different_customer_denied(self):
        self.j.submit("prj1","cust1","req1",sample())
        with self.assertRaisesRegex(ContractHold,"CANDIDATE_ACCESS_DENIED"):
            self.j.read("prj1","othercustomer","contract1","req1")

    def test_corrupt_blob_detected_without_signature_or_payment(self):
        self.j.submit("prj1","cust1","req1",sample())
        # Simulate privileged filesystem tampering after removing local triggers.
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER contract_frozen_no_update")
            db.execute("UPDATE contract_frozen_candidate SET candidate_sha=?",("f"*64,))
        with self.assertRaisesRegex(ContractHold,"CORRUPT_CANDIDATE_DIGEST"):
            self.j.read("prj1","cust1","contract1","req1")

    def test_candidate_wrapper_digest_tamper_rejected(self):
        self.j.submit("prj1","cust1","req1",sample())
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER contract_frozen_no_update")
            row = db.execute("SELECT candidate_json FROM contract_frozen_candidate").fetchone()
            import json
            candidate = json.loads(bytes(row[0]).decode("utf-8"))
            candidate["contract_document_hash"] = "0"*64
            db.execute("UPDATE contract_frozen_candidate SET candidate_json=?",
                       (json.dumps(candidate,sort_keys=True).encode("utf-8"),))
        with self.assertRaisesRegex(ContractHold,"CORRUPT_CANDIDATE_DIGEST"):
            self.j.read("prj1","cust1","contract1","req1")

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


    def test_replace_paths_rejected_and_old_row_preserved(self):
        from single_contract_freeze import canonical_bytes, freeze
        self.j.submit("prj1","cust1","req1",sample())
        data=sample();data["quote_version"]="q2"
        changed=freeze(data)
        old=self.j.read("prj1","cust1","contract1","req1")
        for verb,request,payload in [
            ("INSERT OR REPLACE","req1",changed),
            ("REPLACE INTO","req1",changed),
            ("INSERT OR REPLACE","req2",old),
            ("REPLACE INTO","req2",old)]:
            with sqlite3.connect(self.path) as db:
                with self.assertRaises(sqlite3.DatabaseError):
                    db.execute(verb+" contract_frozen_candidate (project_id,contract_id,request_id,candidate_sha,candidate_json) VALUES (?,?,?,?,?)",
                        ("prj1","contract1",request,payload["contract_document_hash"],canonical_bytes(payload)))
            self.assertEqual(old,self.j.read("prj1","cust1","contract1","req1"))

    def test_corrupted_digest_replay_is_rejected(self):
        self.j.submit("prj1","cust1","req1",sample())
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER contract_frozen_no_update")
            db.execute("UPDATE contract_frozen_candidate SET candidate_sha=?",("0"*64,))
        with self.assertRaisesRegex(ContractHold,"CORRUPT_CANDIDATE_DIGEST"):
            self.j.submit("prj1","cust1","req1",sample())

if __name__=="__main__":
    unittest.main()
