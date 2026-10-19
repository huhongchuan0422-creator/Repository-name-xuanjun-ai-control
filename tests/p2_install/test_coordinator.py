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
        self.mode = "COMMITTED"
    def _report(self, r, observation=False):
        p = Path(r["root"]) / "effect.txt"
        if not observation and self.mode == "COMMITTED":
            p.write_text("durable-effect")
        commit = Path(r["root"]) / ("commit-" + r["batch_id"] + "-" + r["attempt_id"] + ".json")
        observed = Path(r["root"]) / ("observed-" + r["batch_id"] + "-" + r["attempt_id"] + ".json")
        if observation and commit.exists():
            from production.p2_install.coordinator import digest
            content = {
                "installation_id": r["installation_id"],
                "batch_id": r["batch_id"], "attempt_id": r["attempt_id"],
                "request_sha256": digest(r),
                "commit_receipt_sha256": hashlib.sha256(commit.read_bytes()).hexdigest(),
                "effect_verified": p.exists() == (self.mode == "COMMITTED")
            }
            target = observed
        else:
            content = {"effect":p.exists(),"status":self.mode}
            target = commit if not observation else observed
        payload = json.dumps(content).encode()
        target.write_bytes(payload)
        return {"schema":1, "scope":r["scope"],
                "installation_id":r["installation_id"],"batch_id":r["batch_id"],
                "attempt_id":r["attempt_id"],"status":self.mode,
                "receipt":{"path":str(target),"sha256":hashlib.sha256(payload).hexdigest()}}
    def execute(self,r):
        return self._report(r)
    def inspect(self,r):
        p = Path(r["root"]) / "effect.txt"
        self.mode = "COMMITTED" if p.exists() else "NO_EFFECT"
        return self._report(r,True)
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
    def test_subprocess_call_timeout_does_not_repeat_execute(self):
        import subprocess
        class BlockingEffects(Effects):
            def execute(self,request):
                subprocess.run(["/usr/bin/sleep","2"],check=True)
                return super().execute(request)
        blocked = BlockingEffects()
        request = self.request("blocked")
        request["deadline_utc"] = 1
        with Coordinator(self.root,self.plan,{"one":blocked},
                         now=lambda:1,component_roots={"one":self.component},
                         grant=Grant()) as c:
            result = c.execute(request)
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(c.journal.latest("one")[1],"RUNNING")
            recovery = c.recover(request)
            self.assertIn(recovery["status"],("HOLD","NO_EFFECT"))
            self.assertEqual(c.journal.latest("one")[1],"RETRYABLE")

    def test_failure_threshold_persists_across_reopen(self):
        req = self.request("failure-trace")
        with self.open() as c:
            c._store(req)
            for i in range(6):
                c.failure(req,"same-cause",{"sequence":i})
        with self.open() as c:
            for i in range(6,10):
                c.failure(req,"same-cause",{"sequence":i})
            records = c.tick()
            alerts = [x for x in records if x.get("event") == "REPORT_DOTS_10_OR_60"]
            self.assertEqual(len(alerts),1)
            self.assertEqual(alerts[0]["delivery"],"UNAVAILABLE")
            c.tick()
            saved = c.journal.db.execute("SELECT COUNT(*) FROM coordinator_outbox WHERE event='REPORT_DOTS_10_OR_60'").fetchone()[0]
            self.assertEqual(saved,1)

    def test_more_than_five_isolated_node_attempts_not_quota(self):
        self.effect.mode="NO_EFFECT"
        for number in range(7):
            with self.open() as c:
                req=self.request("a"+str(number));req["round_id"]="r"+str(number)
                self.assertEqual(c.execute(req)["status"],"NO_EFFECT")

if __name__=="__main__":
    unittest.main()
