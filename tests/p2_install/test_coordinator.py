import hashlib
import subprocess
import shutil
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))
from production.p2_install.coordinator import Coordinator, Hold, canonical, digest

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

    def test_explicit_failure_with_known_operation_is_not_swallowed(self):
        req=self.request("explicit-after-auto")
        with self.open() as c:
            c._store(req)
            c._automatic_failure(req,"RECONCILE_REQUIRED",
                                 {"error":{"code":"TIMEOUT_UNKNOWN"}})
            first=c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures").fetchone()
            self.assertEqual(json.loads(first[0])["operation_id"],"UNKNOWN")

            # Automatic reconciliation discovers the concrete operation and
            # enriches the original failure without incrementing the count.
            c._automatic_failure(req,"START_OUTCOME_UNKNOWN",
                                 {"operation_id":"operation-X",
                                  "error":{"code":"START_OUTCOME_UNKNOWN"}})
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)

            explicit={"event_id":"explicit-new-failure",
                      "operation_id":"operation-X",
                      "error":{"code":"EXPLICIT_INDEPENDENT"}}
            self.assertTrue(c.failure(req,"EXPLICIT_INDEPENDENT",explicit))
            self.assertFalse(c.failure(req,"EXPLICIT_INDEPENDENT",explicit))
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],2)

        with self.open() as c:
            self.assertFalse(c.failure(req,"EXPLICIT_INDEPENDENT",explicit))
            rows=c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures ORDER BY seq").fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual(
                {json.loads(x[0])["event_id"] for x in rows},
                {"auto-"+digest([req["attempt_id"],"UNKNOWN"])[:32],
                 "explicit-new-failure"})

    def test_failure_log_real_path_boundaries(self):
        req=self.request("log-boundary")
        inside=Path(self.component)/"inside.log"
        inside.write_bytes(b"inside-log")
        outside=Path(self.root)/"outside.log"
        outside.write_bytes(b"outside-secret")
        escape_dir=Path(self.root)/"escape"
        escape_dir.mkdir()
        (escape_dir/"secret.log").write_bytes(b"symlink-secret")
        link=Path(self.component)/"linked"
        link.symlink_to(escape_dir, target_is_directory=True)

        cases=[
            ("inside",str(inside),"VERIFIED",None),
            ("outside",str(outside),"UNKNOWN","FAILURE_LOG_OUTSIDE_ROOT"),
            ("dotdot",str(Path(self.component)/"sub"/".."/"inside.log"),
             "UNKNOWN","FAILURE_LOG_DOTDOT"),
            ("symlink",str(link/"secret.log"),"UNKNOWN",None),
        ]
        with self.open() as c:
            c._store(req)
            for label,path,status,reason in cases:
                event={"event_id":"log-"+label,"log":path,
                       "error":{"code":"LOG_CASE_"+label.upper()}}
                self.assertTrue(c.failure(req,"LOG_CASE_"+label.upper(),event))
            rows=[json.loads(x[0]) for x in c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures ORDER BY seq")]
            self.assertEqual(len(rows),4)
            refs={x["event_id"]:x["references"]["log"] for x in rows}
            self.assertEqual(refs["log-inside"]["status"],"VERIFIED")
            self.assertEqual(
                refs["log-inside"]["sha256"],
                hashlib.sha256(b"inside-log").hexdigest())
            self.assertEqual(refs["log-outside"],
                             {"status":"UNKNOWN","reason":"FAILURE_LOG_OUTSIDE_ROOT"})
            self.assertEqual(refs["log-dotdot"],
                             {"status":"UNKNOWN","reason":"FAILURE_LOG_DOTDOT"})
            self.assertEqual(refs["log-symlink"]["status"],"UNKNOWN")
            self.assertTrue(refs["log-symlink"]["reason"].startswith(
                "FAILURE_LOG_OSERROR_"))

        # Reopen does not change identities, counts, or first timestamps.
        with self.open() as c:
            before=c.journal.db.execute(
                "SELECT seq,observed,evidence,event_key FROM coordinator_failures ORDER BY seq").fetchall()
            self.assertFalse(c.failure(
                req,"LOG_CASE_INSIDE",
                {"event_id":"log-inside","log":str(inside),
                 "error":{"code":"LOG_CASE_INSIDE"}}))
            after=c.journal.db.execute(
                "SELECT seq,observed,evidence,event_key FROM coordinator_failures ORDER BY seq").fetchall()
            self.assertEqual(before,after)

    def test_failure_log_fifo_and_nul_are_unknown_without_blocking(self):
        req=self.request("log-special")
        fifo=Path(self.component)/"blocked.fifo"
        os.mkfifo(fifo,0o600)
        valid=Path(self.component)/"normal.log"
        valid.write_bytes(b"normal")
        with self.open() as c:
            c._store(req)
            start=__import__("time").monotonic()
            self.assertTrue(c.failure(
                req,"FIFO_LOG",
                {"event_id":"fifo-log","log":str(fifo),
                 "error":{"code":"FIFO_LOG"}}))
            elapsed=__import__("time").monotonic()-start
            self.assertLess(elapsed,1.0)
            self.assertTrue(c.failure(
                req,"NUL_LOG",
                {"event_id":"nul-log","log":str(valid)+"\x00suffix",
                 "error":{"code":"NUL_LOG"}}))
            rows=[json.loads(x[0]) for x in c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures ORDER BY seq")]
            refs={x["event_id"]:x["references"]["log"] for x in rows}
            self.assertEqual(refs["fifo-log"]["status"],"UNKNOWN")
            self.assertIn(refs["fifo-log"]["reason"],
                          ("FAILURE_LOG_NOT_REGULAR","FAILURE_LOG_OSERROR_6"))
            self.assertEqual(refs["nul-log"],
                             {"status":"UNKNOWN","reason":"FAILURE_LOG_INVALID_PATH"})
            self.assertEqual(len(rows),2)

        # Existing normal log hashing behavior is unchanged.
        req2=self.request("log-normal")
        with self.open() as c:
            c._store(req2)
            self.assertTrue(c.failure(
                req2,"NORMAL_LOG",
                {"event_id":"normal-log","log":str(valid),
                 "error":{"code":"NORMAL_LOG"}}))
            ref=json.loads(c.journal.db.execute(
                "SELECT evidence FROM coordinator_failures WHERE cause='NORMAL_LOG'"
            ).fetchone()[0])["references"]["log"]
            self.assertEqual(ref["status"],"VERIFIED")
            self.assertEqual(ref["sha256"],hashlib.sha256(b"normal").hexdigest())

    def test_legacy_failure_schema_upgrade_redelivery_and_outbox_dedup(self):
        req=self.request("legacy-auto")
        with self.open() as c:
            c._store(req)

        db_path=os.path.join(self.root,"journal.sqlite3")
        db=sqlite3.connect(db_path)
        try:
            db.execute("DROP INDEX IF EXISTS coordinator_failure_event_key")
            db.execute("DROP TABLE coordinator_failures")
            db.execute("CREATE TABLE coordinator_failures("
                       "seq INTEGER PRIMARY KEY, installation TEXT, cause TEXT,"
                       "observed INTEGER, evidence TEXT)")
            original=canonical({"attempt_id":req["attempt_id"],
                                "request_sha256":digest(req)}).decode("ascii")
            db.execute("INSERT INTO coordinator_failures VALUES(?,?,?,?,?)",
                       (1,req["installation_id"],"LEGACY_CAUSE",100,original))
            old_change=digest([req["installation_id"],"LEGACY_CAUSE",
                               "CHANGE_METHOD_30M"])
            old_report=digest([req["installation_id"],"LEGACY_CAUSE",
                               "REPORT_DOTS_10_OR_60"])
            db.execute("INSERT INTO coordinator_outbox VALUES(?,?,?,?,?)",
                       (old_change,req["installation_id"],"CHANGE_METHOD_30M",
                        "UNAVAILABLE",canonical(
                            {"cause":"LEGACY_CAUSE","failures":1,"first_utc":100,
                             "recipient":"DOTS",
                             "next":"propose alternative and evaluate"}
                        ).decode("ascii")))
            db.execute("INSERT INTO coordinator_outbox VALUES(?,?,?,?,?)",
                       (old_report,req["installation_id"],"REPORT_DOTS_10_OR_60",
                        "UNAVAILABLE",canonical(
                            {"cause":"LEGACY_CAUSE","failures":1,"first_utc":100,
                             "recipient":"DOTS",
                             "next":"propose alternative and evaluate"}
                        ).decode("ascii")))
            db.commit()
        finally:
            db.close()

        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:3700) as c:
            cols=[x[1] for x in c.journal.db.execute(
                "PRAGMA table_info(coordinator_failures)")]
            self.assertIn("event_key",cols)
            self.assertIn("compatibility",cols)
            before=c.journal.db.execute(
                "SELECT observed,evidence FROM coordinator_failures WHERE seq=1"
            ).fetchone()
            self.assertEqual(before,(100,original))
            compatibility=c.journal.db.execute(
                "SELECT compatibility FROM coordinator_failures WHERE seq=1"
            ).fetchone()[0]
            self.assertEqual(compatibility,"LEGACY_AUTO")

            c._automatic_failure(
                req,"LEGACY_CAUSE",{"error":{"code":"LEGACY_CAUSE"}})
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)
            after=c.journal.db.execute(
                "SELECT observed,evidence,compatibility,event_key "
                "FROM coordinator_failures WHERE seq=1").fetchone()
            self.assertEqual(after[0:2],before)
            self.assertEqual(after[2],"MIGRATED_AUTO_MATCH")
            self.assertTrue(after[3])

            emitted=c.tick()
            self.assertFalse(any(
                x.get("event") in ("CHANGE_METHOD_30M","REPORT_DOTS_10_OR_60")
                for x in emitted))
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox").fetchone()[0],2)

        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:3800) as c:
            c._automatic_failure(
                req,"LEGACY_CAUSE",{"error":{"code":"LEGACY_CAUSE"}})
            c.tick()
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox").fetchone()[0],2)
            self.assertEqual(c.journal.db.execute(
                "SELECT observed,evidence FROM coordinator_failures WHERE seq=1"
            ).fetchone(),(100,original))

    def test_legacy_explicit_migrates_and_unknown_identity_stays_unknown(self):
        req=self.request("legacy-explicit")
        with self.open() as c:
            c._store(req)
            explicit={"attempt_id":req["attempt_id"],
                      "event_id":"old-event",
                      "request_sha256":digest(req),
                      "error":{"code":"OLD_EXPLICIT"}}
            c.journal.db.execute(
                "INSERT INTO coordinator_failures("
                "installation,cause,observed,evidence,event_key,compatibility) "
                "VALUES(?,?,?,?,NULL,NULL)",
                (req["installation_id"],"OLD_EXPLICIT",123,
                 canonical(explicit).decode("ascii")))
            unknown_raw=canonical({"unidentified":"legacy"}).decode("ascii")
            c.journal.db.execute(
                "INSERT INTO coordinator_failures("
                "installation,cause,observed,evidence,event_key,compatibility) "
                "VALUES(?,?,?,?,NULL,NULL)",
                (req["installation_id"],"MYSTERY",124,unknown_raw))

        with self.open() as c:
            rows=c.journal.db.execute(
                "SELECT cause,observed,evidence,event_key,compatibility "
                "FROM coordinator_failures ORDER BY seq").fetchall()
            by_cause={x[0]:x for x in rows}
            self.assertEqual(by_cause["OLD_EXPLICIT"][1],123)
            self.assertEqual(by_cause["OLD_EXPLICIT"][2],
                             canonical(explicit).decode("ascii"))
            self.assertTrue(by_cause["OLD_EXPLICIT"][3])
            self.assertEqual(by_cause["OLD_EXPLICIT"][4],"MIGRATED_EXPLICIT")
            self.assertIsNone(by_cause["MYSTERY"][3])
            self.assertEqual(by_cause["MYSTERY"][4],"UNKNOWN")
            self.assertEqual(by_cause["MYSTERY"][2],unknown_raw)

            self.assertFalse(c.failure(
                req,"OLD_EXPLICIT",
                {"event_id":"old-event","error":{"code":"OLD_EXPLICIT"}}))
            self.assertTrue(c.failure(
                req,"MYSTERY",
                {"event_id":"new-real-event","error":{"code":"MYSTERY"}}))
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],3)
            unknown=c.journal.db.execute(
                "SELECT observed,evidence,compatibility FROM coordinator_failures "
                "WHERE event_key IS NULL").fetchall()
            self.assertEqual(unknown,[(124,unknown_raw,"UNKNOWN")])

    def test_legacy_duplicate_rows_do_not_inflate_failure_threshold(self):
        req=self.request("legacy-duplicates")
        with self.open() as c:
            c._store(req)

        db=sqlite3.connect(os.path.join(self.root,"journal.sqlite3"))
        try:
            db.execute("DROP INDEX IF EXISTS coordinator_failure_event_key")
            db.execute("DROP TABLE coordinator_failures")
            db.execute("CREATE TABLE coordinator_failures("
                       "seq INTEGER PRIMARY KEY, installation TEXT, cause TEXT,"
                       "observed INTEGER, evidence TEXT)")
            raw=canonical({"attempt_id":req["attempt_id"],
                           "event_id":"same-old-event",
                           "request_sha256":digest(req),
                           "error":{"code":"OLD_DUP"}}).decode("ascii")
            for seq in range(1,11):
                db.execute("INSERT INTO coordinator_failures VALUES(?,?,?,?,?)",
                           (seq,req["installation_id"],"OLD_DUP",100,raw))
            db.commit()
        finally:
            db.close()

        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:101) as c:
            rows=c.journal.db.execute(
                "SELECT seq,observed,evidence,event_key,compatibility "
                "FROM coordinator_failures ORDER BY seq").fetchall()
            self.assertEqual(len(rows),10)
            self.assertEqual(sum(1 for x in rows if x[4]=="MIGRATED_EXPLICIT"),1)
            self.assertEqual(sum(1 for x in rows if x[4]=="DUPLICATE_KNOWN"),9)
            self.assertEqual({x[1] for x in rows},{100})
            self.assertEqual({x[2] for x in rows},{raw})
            groups=c._counted_failure_groups()
            self.assertEqual(groups[(req["installation_id"],"round-1")]["count"],1)
            emitted=c.tick()
            self.assertFalse(any(
                x.get("event")=="REPORT_DOTS_10_OR_60" for x in emitted))

    def test_legacy_report_link_persists_across_independent_processes(self):
        req=self.request("legacy-report")
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:100) as c:
            c._store(req)
            for i in range(10):
                c.failure(req,"ROOT_CAUSE",
                          {"event_id":"old-real-"+str(i),
                           "error":{"code":"ROOT_CAUSE"}})
            old_id="legacy-report-id"
            c.journal.db.execute(
                "INSERT INTO coordinator_outbox VALUES(?,?,?,?,?)",
                (old_id,req["installation_id"],"REPORT_DOTS_10_OR_60",
                 "UNAVAILABLE",
                 canonical({"failures":10,"first_utc":100,
                            "recipient":"DOTS",
                            "next":"propose alternative and evaluate"}
                          ).decode("ascii")))

        child = (
            "import json,sys;"
            "from production.p2_install.coordinator import Coordinator;"
            "root,component,now=sys.argv[1],sys.argv[2],int(sys.argv[3]);"
            "plan={'schema':1,'release':'"+"a"*64+"','batches':['one','two']};"
            "c=Coordinator(root,plan,component_roots={'one':component},"
            "now=lambda:now);c.__enter__();"
            "out=c.tick();c.__exit__(None,None,None);"
            "print(json.dumps(out,sort_keys=True))"
        )
        first=subprocess.run(
            [sys.executable,"-c",child,self.root,self.component,"100"],
            cwd=str(ROOT),capture_output=True,text=True,timeout=20)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertFalse(any(
            x.get("event")=="REPORT_DOTS_10_OR_60"
            for x in json.loads(first.stdout)))

        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:200) as c:
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox").fetchone()[0],1)
            links=c.journal.db.execute(
                "SELECT stable_id,legacy_id,round_id "
                "FROM coordinator_outbox_links").fetchall()
            self.assertEqual(len(links),1)
            self.assertEqual(links[0][1],"legacy-report-id")
            self.assertEqual(links[0][2],"round-1")
            c.failure(req,"OTHER_REAL",
                      {"event_id":"new-eleventh",
                       "error":{"code":"OTHER_REAL"}})

        second=subprocess.run(
            [sys.executable,"-c",child,self.root,self.component,"200"],
            cwd=str(ROOT),capture_output=True,text=True,timeout=20)
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertFalse(any(
            x.get("event")=="REPORT_DOTS_10_OR_60"
            for x in json.loads(second.stdout)))
        with Coordinator(self.root,self.plan,component_roots={"one":self.component},
                         now=lambda:200) as c:
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox").fetchone()[0],1)
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_outbox_links").fetchone()[0],1)
            self.assertEqual(c.journal.db.execute(
                "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],11)

    def test_more_than_five_isolated_node_attempts_not_quota(self):
        self.effect.mode="NO_EFFECT"
        for number in range(7):
            with self.open() as c:
                req=self.request("a"+str(number));req["round_id"]="r"+str(number)
                self.assertEqual(c.execute(req)["status"],"NO_EFFECT")

if __name__=="__main__":
    unittest.main()
