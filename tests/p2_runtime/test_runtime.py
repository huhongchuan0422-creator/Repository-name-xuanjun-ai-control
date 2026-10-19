import hashlib, json, os, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "production"))
import p2_runtime
from p2_runtime import execute, inspect, recover

class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/"owned"; self.root.mkdir(mode=0o700)
        self.pids=[]
    def tearDown(self):
        for journal in self.root.glob("batch-*.json"):
            try:
                rec=json.loads(journal.read_text())
                if rec.get("pgid"):
                    try: os.killpg(rec["pgid"],signal.SIGKILL)
                    except ProcessLookupError: pass
                col=rec.get("collector")
                if col:
                    try: os.kill(col["pid"],signal.SIGKILL)
                    except ProcessLookupError: pass
            except (OSError,ValueError,KeyError):
                pass
        for pid in self.pids:
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        self.temp.cleanup()
    def req(self,batch="b1",operation="start",argv=None,env=None,timeout=.12):
        return {"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"install","batch_id":batch,
                "attempt_id":"attempt-"+batch,"root":str(self.root),
                "inputs":{"operation":operation,"argv":argv or [sys.executable,"-c","import time;time.sleep(60)"],
                          "cwd":str(self.root),"env":{} if env is None else env,
                          "health":{"type":"process"},"timeout":timeout}}
    def record(self,batch="b1"):
        return json.loads((self.root/("batch-"+batch+".json")).read_text())

    def test_start_duplicate_recover_stop_and_immutable_receipts(self):
        req=self.req()
        first=execute(req); self.assertEqual(first["status"],"COMMITTED",first)
        rec=self.record(); self.pids.append(rec["pid"])
        old=Path(first["receipt"]["path"]); old_hash=first["receipt"]["sha256"]
        self.assertEqual(inspect(req)["status"],"COMMITTED")
        self.assertEqual(recover(req)["status"],"COMMITTED")
        self.assertTrue(old.exists()); self.assertEqual(old_hash,hashlib.sha256(old.read_bytes()).hexdigest())
        self.assertNotEqual(first["receipt"]["path"],inspect(req)["receipt"]["path"])
        self.assertEqual(execute(self.req(operation="stop"))["status"],"COMMITTED")
        self.assertEqual(recover(req)["status"],"NO_EFFECT")
        self.assertEqual(execute(req)["error"]["code"],"ATTEMPT_ALREADY_USED")

    def test_config_conflict_argv_cwd_env_health(self):
        req=self.req(); self.assertEqual(execute(req)["status"],"COMMITTED")
        self.pids.append(self.record()["pid"])
        changed=self.req(argv=[sys.executable,"-c","import time;time.sleep(61)"])
        self.assertEqual(execute(changed)["error"]["code"],"CONFIG_CONFLICT")
        changed=self.req(env={"A":"B"})
        self.assertEqual(execute(changed)["error"]["code"],"CONFIG_CONFLICT")
        changed=self.req(); changed["inputs"]["cwd"]="/tmp"
        self.assertEqual(execute(changed)["error"]["code"],"CONFIG_CONFLICT")
        changed=self.req(); changed["inputs"]["health"]={"type":"process","grace":1}
        self.assertEqual(execute(changed)["error"]["code"],"CONFIG_CONFLICT")

    def test_child_group_cleanup_and_other_batch_survives(self):
        child_code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); time.sleep(60)"
        first=self.req("first",argv=[sys.executable,"-c",child_code])
        second=self.req("second")
        self.assertEqual(execute(first)["status"],"COMMITTED")
        self.assertEqual(execute(second)["status"],"COMMITTED")
        a,b=self.record("first"),self.record("second"); self.pids += [a["pid"],b["pid"]]
        time.sleep(.1)
        state,group=p2_runtime.workload_state(a); self.assertEqual(state,"LIVE"); self.assertGreaterEqual(len(group),2)
        self.assertEqual(execute(self.req("first","stop",argv=first["inputs"]["argv"]))["status"],"COMMITTED")
        self.assertEqual(inspect(second)["status"],"COMMITTED")

    def test_pid_identity_mismatch_refuses_signal(self):
        req=self.req(); self.assertEqual(execute(req)["status"],"COMMITTED")
        rec=self.record(); self.pids.append(rec["pid"])
        rec["start"]="0"; (self.root/"batch-b1.json").write_text(json.dumps(rec))
        out=execute(self.req(operation="stop"))
        self.assertEqual(out["status"],"HOLD"); self.assertEqual(out["error"]["code"],"PID_IDENTITY_MISMATCH")
        self.assertIsNotNone(p2_runtime.proc(self.pids[0]))

    def test_prepared_and_stopping_recovery(self):
        req=self.req()
        cfg=p2_runtime.config_payload(req["inputs"])
        prepared={"installation_id":"install","batch_id":"b1","attempt_id":"attempt-b1","phase":"PREPARED",
                  "config_sha256":p2_runtime.digest(cfg),"log":str(self.root/"run-b1.log"),
                  "limit_marker":str(self.root/"limit-b1.json"),"members":[]}
        (self.root/"batch-b1.json").write_text(json.dumps(prepared))
        self.assertEqual(recover(req)["error"]["code"],"START_OUTCOME_UNKNOWN")
        self.assertEqual(execute(req)["error"]["code"],"START_OUTCOME_UNKNOWN")
        (self.root/"batch-b1.json").unlink()
        self.assertEqual(execute(req)["status"],"COMMITTED"); rec=self.record(); self.pids.append(rec["pid"])
        rec["phase"]="STOPPING"; (self.root/"batch-b1.json").write_text(json.dumps(rec))
        self.assertEqual(recover(req)["error"]["code"],"STOP_OUTCOME_UNKNOWN")
        os.killpg(rec["pgid"],signal.SIGTERM)
        for _ in range(100):
            if p2_runtime.workload_state(rec)[0]=="GONE": break
            time.sleep(.02)
        self.assertEqual(recover(req)["status"],"COMMITTED")

    def test_log_limit_stops_entire_owned_group(self):
        old=p2_runtime.MAX_LOG; p2_runtime.MAX_LOG=2048
        try:
            code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); print('X'*100000,flush=True); time.sleep(60)"
            req=self.req(argv=[sys.executable,"-c",code],timeout=.4)
            out=execute(req); self.assertEqual(out["status"],"HOLD",out); self.assertEqual(out["error"]["code"],"LOG_LIMIT")
            rec=self.record(); self.assertEqual(p2_runtime.workload_state(rec)[0],"GONE")
        finally: p2_runtime.MAX_LOG=old

    def test_real_stop_timeout_holds_without_touching_other_batch(self):
        stubborn=[sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"]
        first=self.req("first",argv=stubborn); second=self.req("second")
        self.assertEqual(execute(first)["status"],"COMMITTED"); self.assertEqual(execute(second)["status"],"COMMITTED")
        a,b=self.record("first"),self.record("second"); self.pids += [a["pid"],b["pid"]]
        out=execute(self.req("first","stop",argv=stubborn,timeout=.08))
        self.assertEqual(out["status"],"HOLD",out); self.assertEqual(out["error"]["code"],"STOP_TIMEOUT")
        self.assertEqual(inspect(second)["status"],"COMMITTED")

    def test_leader_exit_with_child_alive_is_not_no_effect(self):
        code="import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])"
        req=self.req(argv=[sys.executable,"-c",code],timeout=.08)
        out=execute(req)
        self.assertEqual(out["status"],"COMMITTED",out)
        rec=self.record(); self.pids.append(rec["pid"])
        time.sleep(.15)
        state,group=p2_runtime.workload_state(rec)
        self.assertEqual(state,"LIVE")
        self.assertGreaterEqual(len(group),1)
        observed=inspect(req)
        self.assertEqual(observed["status"],"COMMITTED",observed)
        stopped=execute(self.req(operation="stop",argv=req["inputs"]["argv"]))
        self.assertEqual(stopped["status"],"COMMITTED",stopped)

    def test_short_process_failure_cleaned_and_no_effect_only_after_group_gone(self):
        out=execute(self.req(argv=[sys.executable,"-c","pass"]))
        self.assertEqual(out["status"],"HOLD")
        rec=self.record(); self.assertEqual(p2_runtime.workload_state(rec)[0],"GONE")
        self.assertEqual(recover(self.req())["status"],"NO_EFFECT")

    def test_cli_and_uniform_identity_fields(self):
        req=self.req()
        p=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[2]/"production/p2_runtime/__init__.py"),"inspect"],
                         input=json.dumps(req),text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        out=json.loads(p.stdout)
        for key in ("schema","scope","installation_id","batch_id","attempt_id","status","receipt","error"):
            self.assertIn(key,out)

if __name__=="__main__": unittest.main()
