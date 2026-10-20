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


    def test_repeated_progress_survives_multiple_reopens(self):
        req = self.request("progress-reopen")
        with self.open() as c:
            c._store(req)
            c.event(req, "PROGRESS", {"step": 1})
            c.event(req, "PROGRESS", {"step": 2})
            self.assertEqual(
                c.journal.db.execute(
                    "SELECT COUNT(*) FROM coordinator_events WHERE attempt=? AND kind='PROGRESS'",
                    (req["attempt_id"],)).fetchone()[0], 2)
        with self.open() as c:
            c.event(req, "PROGRESS", {"step": 3})
            self.assertEqual(
                c.journal.db.execute(
                    "SELECT COUNT(*) FROM coordinator_events WHERE attempt=? AND kind='PROGRESS'",
                    (req["attempt_id"],)).fetchone()[0], 3)
        with self.open() as c:
            rows = c.journal.db.execute(
                "SELECT evidence FROM coordinator_events WHERE attempt=? AND kind='PROGRESS' ORDER BY id",
                (req["attempt_id"],)).fetchall()
            self.assertEqual([json.loads(x[0])["step"] for x in rows], [1, 2, 3])

    def test_failure_threshold_persists_across_reopen(self):
        req = self.request("failure-trace")
        with self.open() as c:
            c._store(req)
            for i in range(6):
                c.failure(req,"same-cause",{"event_id":"event-"+str(i),"sequence":i})
        with self.open() as c:
            for i in range(6,10):
                c.failure(req,"same-cause",{"event_id":"event-"+str(i),"sequence":i})
            records = c.tick()
            alerts = [x for x in records if x.get("event") == "REPORT_DOTS_10_OR_60"]
            self.assertEqual(len(alerts),1)
            self.assertEqual(alerts[0]["delivery"],"UNAVAILABLE")
            c.tick()
            saved = c.journal.db.execute("SELECT COUNT(*) FROM coordinator_outbox WHERE event='REPORT_DOTS_10_OR_60'").fetchone()[0]
            self.assertEqual(saved,1)

    def test_failure_identity_evidence_and_reopen(self):
        req=self.request("evidence")
        original_time=100
        log=Path(self.component)/"error.log"
        log.write_text("actual-error")
        payload={"event_id":"actual-failure-1","error":{"code":"PROCESS_EXITED"},
                 "operation_id":"operation-1","log":str(log)}
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:original_time) as c:
            c._store(req)
            self.assertTrue(c.failure(req,"PROCESS_EXITED",payload))
            self.assertFalse(c.failure(req,"PROCESS_EXITED",payload))
            first=c.journal.db.execute("SELECT observed,evidence FROM coordinator_failures").fetchone()
            details=json.loads(first[1])
            self.assertEqual(details["references"]["log"]["sha256"],hashlib.sha256(b"actual-error").hexdigest())
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:original_time+100) as c:
            self.assertFalse(c.failure(req,"PROCESS_EXITED",payload))
            self.assertEqual(c.journal.db.execute("SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)
            self.assertEqual(first,c.journal.db.execute("SELECT observed,evidence FROM coordinator_failures").fetchone())

    def test_round_across_causes_and_nodes(self):
        req=self.request("failed-base")
        with self.open() as c:
            c._store(req)
            for index in range(10):
                cause="CAUSE_A" if index%2 else "CAUSE_B"
                c.failure(req,cause,{"event_id":"distinct-"+str(index)})
            alerts=c.tick()
            self.assertEqual(len([x for x in alerts if x.get("event")=="REPORT_DOTS_10_OR_60"]),1)
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox WHERE event='REPORT_DOTS_10_OR_60'").fetchone()[0],1)

    def test_root_cause_30m_and_round_60m_exact_boundaries(self):
        req=self.request("boundary")
        clock=[1000]
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:clock[0]) as c:
            c._store(req)
            c.failure(req,"REAL_CAUSE",{"event_id":"boundary-failure"})
        clock[0]=2799
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:clock[0]) as c:
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox WHERE event='CHANGE_METHOD_30M'").fetchone()[0],0)
        clock[0]=2800
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:clock[0]) as c:
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox WHERE event='CHANGE_METHOD_30M'").fetchone()[0],1)
        clock[0]=4599
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:clock[0]) as c:
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox WHERE event='REPORT_DOTS_10_OR_60'").fetchone()[0],0)
        clock[0]=4600
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:clock[0]) as c:
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox WHERE event='REPORT_DOTS_10_OR_60'").fetchone()[0],1)

    def test_actual_cross_node_round_count_and_distinct_root_causes(self):
        component2=self.root+"/component2"
        os.mkdir(component2,0o700)
        roots={"one":self.component,"two":component2}
        req1=self.request("node-one","one")
        req2=dict(self.request("node-two","two")); req2["root"]=component2
        with Coordinator(self.root,self.plan,component_roots=roots,now=lambda:100) as c:
            c._store(req1); c._store(req2)
            for index in range(5):
                c.failure(req1,"ROOT_A",{"event_id":"one-"+str(index)})
                c.failure(req2,"ROOT_B",{"event_id":"two-"+str(index)})
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],10)
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox WHERE event='REPORT_DOTS_10_OR_60'").fetchone()[0],1)
            evidence=[json.loads(x[0]) for x in c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures ORDER BY seq")]
            self.assertEqual({x["root_cause"] for x in evidence},{"ROOT_A","ROOT_B"})

    def test_unknown_automatic_failures_do_not_merge_across_attempts(self):
        first=self.request("unknown-a")
        second=self.request("unknown-b")
        with self.open() as c:
            c._store(first); c._store(second)
            c._automatic_failure(first,"RECONCILE_REQUIRED",
                                 {"error":{"code":"TIMEOUT_UNKNOWN"}})
            c._automatic_failure(second,"RECONCILE_REQUIRED",
                                 {"error":{"code":"TIMEOUT_UNKNOWN"}})
            rows=c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures ORDER BY seq").fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual(
                {json.loads(x[0])["attempt_id"] for x in rows},
                {"unknown-a","unknown-b"})

    def test_more_than_five_isolated_node_attempts_not_quota(self):
        self.effect.mode="NO_EFFECT"
        for number in range(7):
            with self.open() as c:
                req=self.request("a"+str(number));req["round_id"]="r"+str(number)
                self.assertEqual(c.execute(req)["status"],"NO_EFFECT")

if __name__=="__main__":
    unittest.main()
