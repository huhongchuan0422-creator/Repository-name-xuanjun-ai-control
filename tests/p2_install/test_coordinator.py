import hashlib
import shutil
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))
from production.p2_install.coordinator import Coordinator, Hold

class Effects:
    def __init__(self):
        self.calls = 0
        self.mode = "COMMITTED"
    def _report(self, r):
        p = Path(r["root"]) / "effect.txt"
        if self.mode == "COMMITTED":
            p.write_text("durable-effect")
        receipt = Path(r["root"]) / "receipt.json"
        payload = json.dumps({"effect":p.exists(),"status":self.mode}).encode()
        receipt.write_bytes(payload)
        return {"schema":1, "scope":r["scope"],
                "installation_id":r["installation_id"],"batch_id":r["batch_id"],
                "attempt_id":r["attempt_id"],"status":self.mode,
                "receipt":{"path":str(receipt),"sha256":hashlib.sha256(payload).hexdigest()}}
    def execute(self, r):
        self.calls += 1
        return self._report(r)
    def inspect(self,r):
        p = Path(r["root"]) / "effect.txt"
        self.mode = "COMMITTED" if p.exists() else "NO_EFFECT"
        return self._report(r)
    def recover(self,r):
        return self.inspect(r)

class Grant:
    def admit_round(self, request, ordinal):
        return True

class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        self.component = self.root + "/component"
        os.mkdir(self.component, 0o700)
        self.plan = {"schema":1,"release":"a"*64,"batches":["one","two"]}
        self.effect = Effects()
    def request(self, attempt="a1",batch="one"):
        return {"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"install",
                "batch_id":batch,"attempt_id":attempt,"root":self.component,"round_id":"round-1",
                "version":"a"*64,"deadline_utc":4102444800,
                "inputs":{"operation":"start"}}
    def open(self):
        return Coordinator(self.root,self.plan,{"one":self.effect,"two":self.effect},component_roots={"one":self.component,"two":self.component},grant=Grant())
    def test_real_effect_and_restart_no_duplicate(self):
        with self.open() as c:
            self.assertEqual(c.execute(self.request())["status"],"COMMITTED")
        with self.open() as c:
            self.assertEqual(c.recover(self.request())["status"],"COMMITTED")
            self.assertEqual(c.execute(self.request("a2"))["status"],"HOLD")
        self.assertEqual((Path(self.component)/"effect.txt").read_text(),"durable-effect")
    def test_no_provider_never_executes(self):
        with Coordinator(self.root,self.plan,component_roots={"one":self.component,"two":self.component}) as c:
            with self.assertRaises(Hold):
                c.execute(self.request())
    def test_different_payload_same_attempt_rejected(self):
        with self.open() as c:
            c.execute(self.request())
            r=self.request();r["inputs"]["operation"]="stop"
            with self.assertRaises(Hold):
                c.recover(r)
    def test_predecessor_drift_rejected(self):
        with self.open() as c:
            c.execute(self.request())
            (Path(self.component)/"effect.txt").unlink()
            with self.assertRaises(Hold):
                c.execute(self.request("b1","two"))
    def test_no_effect_then_retry(self):
        self.effect.mode="NO_EFFECT"
        with self.open() as c:
            self.assertEqual(c.execute(self.request())["status"],"NO_EFFECT")
        with self.open() as c:
            self.effect.mode="COMMITTED"
            self.assertEqual(c.execute(self.request("a2"))["status"],"COMMITTED")
    def test_threshold_dedup_and_unavailable(self):
        with self.open() as c:
            # A persisted intent with no durable terminal result.
            c._store(self.request())
        # Deterministic clock, no external service claims.
        with Coordinator(self.root,self.plan,{"one":self.effect},now=lambda:4102444700,component_roots={"one":self.component},grant=Grant()) as c:
            rows = c.tick()
            self.assertTrue(rows)
            self.assertTrue(all(r["delivery"]=="UNAVAILABLE" for r in rows))
            c.tick()
            count = c.journal.db.execute("SELECT COUNT(*) FROM coordinator_outbox").fetchone()[0]
            self.assertEqual(count,len(set(x["id"] for x in rows)))
    def test_five_attempts_preserved(self):
        self.effect.mode="NO_EFFECT"
        for number in range(5):
            with self.open() as c:
                req=self.request("a"+str(number));req["round_id"]="r"+str(number)
                self.assertEqual(c.execute(req)["status"],"NO_EFFECT")
        with self.open() as c:
            with self.assertRaises(Hold):
                req=self.request("six");req["round_id"]="six"
                c.execute(req)

if __name__=="__main__":
    unittest.main()
