import hashlib, json, os, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "production"))
import p2_runtime
from p2_runtime import execute, inspect

SERVICE = r"""
import os,socket,sys,time
path,mode=sys.argv[1],sys.argv[2]
try: os.unlink(path)
except FileNotFoundError: pass
if mode=="exit":
    sys.exit(0)
if mode=="silent":
    time.sleep(60)
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.bind(path); s.listen(5)
while True:
    c,_=s.accept()
    try:
        data=c.recv(128)
        if mode=="timeout":
            time.sleep(2)
        elif mode=="bad":
            c.sendall(b"NOPE\n")
        else:
            c.sendall(b"PONG\n")
    finally:
        c.close()
"""

class Readiness(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/"root"; self.root.mkdir(mode=0o700)
    def tearDown(self):
        for j in self.root.glob("batch-*.json"):
            try:
                e=json.loads(j.read_text())
                if e.get("pgid"):
                    try: os.killpg(e["pgid"],signal.SIGKILL)
                    except ProcessLookupError: pass
                if e.get("collector"):
                    try: os.kill(e["collector"]["pid"],signal.SIGKILL)
                    except ProcessLookupError: pass
            except Exception:
                pass
        self.tmp.cleanup()

    def req(self,batch,mode="ready",health=True,timeout=.5):
        sock=str(self.root/(batch+".sock"))
        argv=[sys.executable,"-c",SERVICE,sock,mode]
        h={"type":"unix_socket","path":sock,"request":"PING\n","expect":"PONG\n",
           "connect_timeout":.08,"read_timeout":.08,"total_timeout":.35,"max_response":64} if health else {"type":"process"}
        return {"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"install",
                "batch_id":batch,"attempt_id":"attempt-"+batch,"root":str(self.root),
                "inputs":{"operation":"start","argv":argv,"cwd":str(self.root),"env":{},"health":h,"timeout":timeout}}

    def test_unix_socket_ready_and_new_cli_read(self):
        req=self.req("ready")
        out=execute(req)
        self.assertEqual(out["status"],"COMMITTED",out)
        self.assertTrue(out["operation_id"])
        self.assertTrue(out["config_sha256"])
        self.assertEqual(out["commit_receipt"],out["receipt"])
        original=Path(out["receipt"]["path"]); original_hash=out["receipt"]["sha256"]
        cli=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[2]/"production/p2_runtime/__init__.py"),"inspect"],
                           input=json.dumps(req),text=True,capture_output=True)
        self.assertEqual(cli.returncode,0,cli.stderr)
        observed=json.loads(cli.stdout)
        self.assertEqual(observed["status"],"COMMITTED",observed)
        self.assertEqual(observed["operation_id"],out["operation_id"])
        self.assertEqual(observed["config_sha256"],out["config_sha256"])
        self.assertEqual(observed["commit_receipt"],out["receipt"])
        self.assertNotEqual(observed["receipt"],out["receipt"])
        self.assertEqual(original_hash,hashlib.sha256(original.read_bytes()).hexdigest())

    def test_alive_but_not_ready(self):
        req=self.req("silent","silent")
        out=execute(req)
        self.assertEqual(out["status"],"HOLD",out)
        self.assertIn(out["error"]["code"],("APP_NOT_READY","HEALTH_TIMEOUT"))

    def test_response_timeout(self):
        req=self.req("timeout","timeout")
        out=execute(req)
        self.assertEqual(out["status"],"HOLD",out)
        self.assertEqual(out["error"]["code"],"HEALTH_TIMEOUT")

    def test_wrong_response(self):
        req=self.req("bad","bad")
        out=execute(req)
        self.assertEqual(out["status"],"HOLD",out)
        self.assertEqual(out["error"]["code"],"HEALTH_BAD_RESPONSE")

    def test_application_exit(self):
        req=self.req("exit","exit")
        out=execute(req)
        self.assertEqual(out["status"],"HOLD",out)
        self.assertIn(out["error"]["code"],("APPLICATION_EXITED","HEALTH_FAILED"))

    def test_readiness_is_rechecked_after_commit(self):
        req=self.req("recheck")
        out=execute(req); self.assertEqual(out["status"],"COMMITTED",out)
        e=json.loads((self.root/"batch-recheck.json").read_text())
        os.killpg(e["pgid"],signal.SIGKILL)
        for _ in range(100):
            if p2_runtime.workload_state(e)[0]=="GONE": break
            time.sleep(.02)
        seen=inspect(req)
        self.assertEqual(seen["status"],"HOLD",seen)
        self.assertEqual(seen["error"]["code"],"RUNNING_PROCESS_MISSING")

    def test_all_start_parameters_rejected_before_journal_or_process(self):
        req=self.req("invalid")
        req["inputs"]["health"]["path"]="/tmp/outside.sock"
        out=execute(req)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["error"]["code"],"HEALTH_SOCKET_OUTSIDE_ROOT")
        self.assertFalse((self.root/"batch-invalid.json").exists())
        req=self.req("invalid2"); req["inputs"]["timeout"]="bad"
        out=execute(req)
        self.assertEqual(out["error"]["code"],"INVALID_TIMEOUT")
        self.assertFalse((self.root/"batch-invalid2.json").exists())

    def test_cli_sigkill_does_not_disable_log_limit_or_touch_prior_batch(self):
        prior={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"install","batch_id":"prior",
               "attempt_id":"attempt-prior","root":str(self.root),
               "inputs":{"operation":"start","argv":[sys.executable,"-c","import time;time.sleep(60)"],
                         "cwd":str(self.root),"env":{},"health":{"type":"process"},"timeout":.1}}
        first=execute(prior); self.assertEqual(first["status"],"COMMITTED",first)
        receipt=Path(first["receipt"]["path"]); receipt_hash=first["receipt"]["sha256"]

        sock=str(self.root/"killed.sock")
        code="import sys,time; time.sleep(.5); sys.stdout.write('X'*(2*1024*1024)); sys.stdout.flush(); time.sleep(60)"
        req={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"install","batch_id":"killed",
             "attempt_id":"attempt-killed","root":str(self.root),
             "inputs":{"operation":"start","argv":[sys.executable,"-c",code],"cwd":str(self.root),"env":{},
                       "health":{"type":"unix_socket","path":sock,"request":"PING\n","expect":"PONG\n",
                                 "connect_timeout":.1,"read_timeout":.1,"total_timeout":5,"max_response":64},
                       "timeout":5}}
        request_file=self.root/"request.json"; request_file.write_text(json.dumps(req))
        manager=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[2]/"production/p2_runtime/__init__.py"),
                                  "execute","--request",str(request_file)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        journal=self.root/"batch-killed.json"
        entry=None
        for _ in range(150):
            try:
                entry=json.loads(journal.read_text())
                if entry.get("collector") and entry.get("phase")=="RUNNING": break
            except (FileNotFoundError,json.JSONDecodeError):
                pass
            time.sleep(.02)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.get("collector"),entry)
        os.kill(manager.pid,signal.SIGKILL); manager.wait(timeout=2)

        mark=self.root/"limit-killed.json"
        for _ in range(200):
            if mark.exists() and p2_runtime.workload_state(entry)[0]=="GONE": break
            time.sleep(.02)
        self.assertTrue(mark.exists())
        self.assertEqual(p2_runtime.workload_state(entry)[0],"GONE")
        # No inspect/recover call for killed batch occurred.
        self.assertEqual(inspect(prior)["status"],"COMMITTED")
        self.assertEqual(receipt_hash,hashlib.sha256(receipt.read_bytes()).hexdigest())

if __name__=="__main__":
    unittest.main()
