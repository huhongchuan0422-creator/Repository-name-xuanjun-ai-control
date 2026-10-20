"""Runs with EXACT window-two source staged read-only by CI. No network."""
import json, multiprocessing, os, pathlib, signal, subprocess, sys, tempfile, time, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from production.p2_install.coordinator import Coordinator
from production import p2_runtime


class RuntimeAdapter:
    execute=staticmethod(p2_runtime.execute)
    inspect=staticmethod(p2_runtime.inspect)
    recover=staticmethod(p2_runtime.recover)

class DelayedFailureRuntimeAdapter:
    @staticmethod
    def execute(request):
        result=p2_runtime.execute(request)
        time.sleep(1.5)
        return result
    inspect=staticmethod(p2_runtime.inspect)
    recover=staticmethod(p2_runtime.recover)

class ResponseLossRuntimeAdapter:
    @staticmethod
    def execute(request):
        result=p2_runtime.execute(request)
        pathlib.Path(request["root"],"response-loss-ready.json").write_text(json.dumps(result))
        time.sleep(0.75)
        return result
    inspect=staticmethod(p2_runtime.inspect)
    recover=staticmethod(p2_runtime.recover)

def run_interrupted_coordinator(coord,plan,runtime,request):
    with Coordinator(coord,plan,{"service":ResponseLossRuntimeAdapter()},
                     component_roots={"service":runtime}) as c:
        c.execute(request)

class RuntimeIntegration(unittest.TestCase):
    def test_real_runtime_failed_operation_is_durable_once(self):
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)
            coord=root/"coordinator"; runtime=root/"runtime"
            coord.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
            plan={"schema":1,"release":"a"*64,"batches":["service"]}
            req={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"failure-real",
                 "batch_id":"service","attempt_id":"error-one","root":str(runtime),
                 "version":"a"*64,"deadline_utc":int(time.time())+20,
                 "round_id":"round-1","inputs":{"operation":"start","argv":["/not-real-binary"],
                 "cwd":str(runtime),"env":{},"health":{"type":"process"}}}
            class Adapter:
                execute=staticmethod(p2_runtime.execute)
                inspect=staticmethod(p2_runtime.inspect)
                recover=staticmethod(p2_runtime.recover)
            with Coordinator(str(coord),plan,{"service":Adapter()},
                             component_roots={"service":str(runtime)}) as c:
                failed=c.execute(req)
                self.assertEqual(failed["status"],"HOLD",failed)
                rows=c.journal.db.execute("SELECT evidence FROM coordinator_failures").fetchall()
                self.assertEqual(len(rows),1)
                payload=json.loads(rows[0][0])
                self.assertEqual(payload["attempt_id"],"error-one")
                self.assertEqual(payload["references"]["receipt"]["status"],"VERIFIED")
            with Coordinator(str(coord),plan,{"service":Adapter()},
                             component_roots={"service":str(runtime)}) as c:
                c.recover(req)
                c.inspect(req)
                self.assertEqual(c.journal.db.execute(
                    "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)

    def test_real_runtime_error_code_changes_are_one_failure(self):
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)
            coord=root/"coordinator"; runtime=root/"runtime"
            coord.mkdir(mode=0o700); runtime.mkdir(mode=0o700)
            bad=runtime/"bad-exec"
            bad.write_text("#!/definitely/missing/interpreter\n")
            bad.chmod(0o700)
            plan={"schema":1,"release":"a"*64,"batches":["service"]}
            req={"schema":1,"scope":"ISOLATED_TEST_ONLY",
                 "installation_id":"error-change","batch_id":"service",
                 "attempt_id":"same-operation","root":str(runtime),
                 "version":"a"*64,"round_id":"round-1",
                 "deadline_utc":int(time.time())+20,
                 "inputs":{"operation":"start","argv":[str(bad)],
                           "cwd":str(runtime),"env":{},
                           "health":{"type":"process"},"timeout":0.2}}
            with Coordinator(str(coord),plan,{"service":RuntimeAdapter()},
                             component_roots={"service":str(runtime)}) as c:
                first=c.execute(req)
                self.assertEqual(first["status"],"HOLD",first)
                rows=c.journal.db.execute(
                    "SELECT cause,evidence FROM coordinator_failures").fetchall()
                self.assertEqual(len(rows),1)
                first_saved=json.loads(rows[0][1])
                self.assertEqual(first_saved["root_cause"],"LAUNCH_UNKNOWN")
                first_time=c.journal.db.execute(
                    "SELECT observed FROM coordinator_failures").fetchone()[0]
            with Coordinator(str(coord),plan,{"service":RuntimeAdapter()},
                             component_roots={"service":str(runtime)}) as c:
                again=c.recover(req)
                self.assertEqual(again["status"],"HOLD",again)
                self.assertEqual(c.journal.db.execute(
                    "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)
                saved=c.journal.db.execute(
                    "SELECT observed,evidence FROM coordinator_failures").fetchone()
                self.assertEqual(saved[0],first_time)
                self.assertEqual(json.loads(saved[1]),first_saved)
                # Runtime observation now reports START_OUTCOME_UNKNOWN, but
                # that is an observation of the same operation, not a new failure.
                direct=p2_runtime.recover(req)
                self.assertEqual(direct["error"]["code"],"START_OUTCOME_UNKNOWN")
                self.assertEqual(direct["operation_id"],first_saved["operation_id"])

    def test_timeout_unknown_then_real_operation_identity_merges_once(self):
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)
            coord=root/"coordinator"; runtime=root/"runtime"
            coord.mkdir(mode=0o700); runtime.mkdir(mode=0o700)
            bad=runtime/"bad-timeout-exec"
            bad.write_text("#!/definitely/missing/interpreter\n")
            bad.chmod(0o700)
            plan={"schema":1,"release":"a"*64,"batches":["service"]}
            req={"schema":1,"scope":"ISOLATED_TEST_ONLY",
                 "installation_id":"timeout-identity","batch_id":"service",
                 "attempt_id":"attempt-one","root":str(runtime),
                 "version":"a"*64,"round_id":"round-1","deadline_utc":1,
                 "inputs":{"operation":"start","argv":[str(bad)],
                           "cwd":str(runtime),"env":{},
                           "health":{"type":"process"},"timeout":0.2}}
            with Coordinator(str(coord),plan,{"service":DelayedFailureRuntimeAdapter()},
                             now=lambda:0,
                             component_roots={"service":str(runtime)}) as c:
                first=c.execute(req)
                self.assertEqual(first["status"],"HOLD",first)
                rows=c.journal.db.execute(
                    "SELECT observed,evidence FROM coordinator_failures").fetchall()
                self.assertEqual(len(rows),1)
                first_time=rows[0][0]
                first_saved=json.loads(rows[0][1])
                self.assertEqual(first_saved["operation_id"],"UNKNOWN")
                self.assertEqual(first_saved["error"]["code"],"TIMEOUT_UNKNOWN")
                original=dict(first_saved)
            with Coordinator(str(coord),plan,{"service":RuntimeAdapter()},
                             now=lambda:50,
                             component_roots={"service":str(runtime)}) as c:
                recovered=c.recover(req)
                self.assertEqual(recovered["status"],"HOLD",recovered)
                rows=c.journal.db.execute(
                    "SELECT observed,evidence FROM coordinator_failures").fetchall()
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0][0],first_time)
                merged=json.loads(rows[0][1])
                for key in ("event_id","event_key","cause","root_cause","error",
                            "references","checkpoint"):
                    self.assertEqual(merged[key],original[key])
                resolution=merged["identity_resolution"]
                self.assertNotEqual(resolution["operation_id"],"UNKNOWN")
                self.assertEqual(
                    resolution["observed_error"]["code"],"START_OUTCOME_UNKNOWN")
                again=c.recover(req)
                self.assertEqual(again["status"],"HOLD",again)
                self.assertEqual(c.journal.db.execute(
                    "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],1)

            # A different attempt remains a distinct failure; UNKNOWN identities
            # are not globally merged.
            runtime2=root/"runtime2"; runtime2.mkdir(mode=0o700)
            bad2=runtime2/"bad-timeout-exec"; bad2.write_text(
                "#!/definitely/missing/interpreter\n"); bad2.chmod(0o700)
            req2=dict(req); req2["attempt_id"]="attempt-two"; req2["root"]=str(runtime2)
            req2["inputs"]=dict(req["inputs"]); req2["inputs"]["argv"]=[str(bad2)]
            req2["inputs"]["cwd"]=str(runtime2)
            plan2={"schema":1,"release":"a"*64,"batches":["service","service2"]}
            req2["batch_id"]="service2"
            with Coordinator(str(coord),plan2,{"service":RuntimeAdapter(),
                                              "service2":DelayedFailureRuntimeAdapter()},
                             now=lambda:0,
                             component_roots={"service":str(runtime),
                                              "service2":str(runtime2)}) as c:
                second=c.execute(req2)
                self.assertEqual(second["status"],"HOLD",second)
                self.assertEqual(c.journal.db.execute(
                    "SELECT COUNT(*) FROM coordinator_failures").fetchone()[0],2)

    def test_cli_execute_inspect_and_recover(self):
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)
            coord=root/"coordinator";runtime=root/"runtime"
            coord.mkdir(mode=0o700);runtime.mkdir(mode=0o700)
            plan={"schema":1,"release":"a"*64,"batches":["service"]}
            req={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":"cli",
                 "batch_id":"service","attempt_id":"cli1","root":str(runtime),
                 "version":"a"*64,"deadline_utc":int(time.time())+30,
                 "inputs":{"operation":"start","argv":[sys.executable,"-c","import time;time.sleep(120)"],
                           "cwd":str(runtime),"env":{},"health":{"type":"process"},"timeout":0.2}}
            planfile=root/"plan.json";requestfile=root/"request.json"
            planfile.write_text(json.dumps(plan));requestfile.write_text(json.dumps(req))
            def run(action):
                args=[sys.executable,"-m","production.p2_install.coordinator",action,
                      "--root",str(coord),"--plan",str(planfile),
                      "--request",str(requestfile),"--runtime",
                      "--component-root","service="+str(runtime)]
                call=subprocess.run(args,capture_output=True,text=True,timeout=20,cwd=str(pathlib.Path(__file__).resolve().parents[2]))
                return json.loads(call.stdout)
            try:
                started=run("execute")
                self.assertEqual(started["status"],"COMMITTED",started)
                checked=run("inspect")
                self.assertEqual(checked["status"],"COMMITTED",checked)
                self.assertNotEqual(started["receipt"],checked["receipt"])
                entry=json.loads((runtime/"batch-service.json").read_text())
                os.kill(entry["pid"],signal.SIGKILL)
                time.sleep(0.2)
                hold=run("recover")
                self.assertEqual(hold["status"],"HOLD",hold)
            finally:
                try:
                    entry=json.loads((runtime/"batch-service.json").read_text())
                    for key in ("pid",):
                        try: os.kill(entry[key],signal.SIGTERM)
                        except (ProcessLookupError,KeyError): pass
                    try: os.kill(entry["collector"]["pid"],signal.SIGTERM)
                    except (ProcessLookupError,KeyError): pass
                except (FileNotFoundError,ValueError): pass


    def test_real_runtime_committed_response_loss_recovers_original_commit(self):
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)
            coord=root/"coordinator"; runtime=root/"runtime"
            coord.mkdir(mode=0o700); runtime.mkdir(mode=0o700)
            plan={"schema":1,"release":"a"*64,"batches":["service"]}
            req={"schema":1,"scope":"ISOLATED_TEST_ONLY",
                 "installation_id":"loss","batch_id":"service","attempt_id":"loss-a1",
                 "root":str(runtime),"version":"a"*64,
                 "deadline_utc":int(time.time())+30,
                 "inputs":{"operation":"start",
                           "argv":[sys.executable,"-c","import time;time.sleep(120)"],
                           "cwd":str(runtime),"env":{},
                           "health":{"type":"process"},"timeout":0.2}}
            manager=multiprocessing.Process(
                target=run_interrupted_coordinator,
                args=(str(coord),plan,str(runtime),req))
            manager.start()
            marker=runtime/"response-loss-ready.json"
            deadline=time.time()+10
            while time.time()<deadline and not marker.exists():
                if not manager.is_alive():
                    self.fail("coordinator exited before real runtime committed")
                time.sleep(.01)
            self.assertTrue(marker.exists())
            real_result=json.loads(marker.read_text())
            self.assertEqual(real_result["status"],"COMMITTED",real_result)
            original_commit=real_result["commit_receipt"]
            self.assertEqual(original_commit,real_result["receipt"])

            os.kill(manager.pid,signal.SIGKILL)
            manager.join(timeout=5)
            self.assertEqual(manager.exitcode,-signal.SIGKILL)

            entry_path=runtime/"batch-service.json"
            entry_before=json.loads(entry_path.read_text())
            identity=(entry_before["pid"],entry_before["start"],
                      entry_before["pgid"],entry_before["session"])
            self.assertEqual(entry_before["commit_receipt"],original_commit)
            self.assertEqual(p2_runtime.workload_state(entry_before)[0],"LIVE")
            original_bytes=pathlib.Path(original_commit["path"]).read_bytes()

            # The forked adapter invocation briefly inherits the coordinator lock.
            reopened=None
            end=time.time()+5
            while time.time()<end:
                try:
                    reopened=Coordinator(str(coord),plan,{"service":RuntimeAdapter()},
                                         component_roots={"service":str(runtime)})
                    reopened.__enter__()
                    break
                except (BlockingIOError,OSError):
                    time.sleep(.05)
            self.assertIsNotNone(reopened)
            try:
                recovered=reopened.recover(req)
                self.assertEqual(recovered["status"],"COMMITTED",recovered)
                self.assertEqual(recovered["receipt"],original_commit)
                first_inspect=reopened.inspect(req)
                second_recover=reopened.recover(req)
                self.assertEqual(first_inspect["status"],"COMMITTED",first_inspect)
                self.assertEqual(second_recover["status"],"COMMITTED",second_recover)
                self.assertEqual(reopened.journal.latest("service")[1],"COMMITTED")
            finally:
                reopened.__exit__(None,None,None)

            entry_after=json.loads(entry_path.read_text())
            self.assertEqual((entry_after["pid"],entry_after["start"],
                              entry_after["pgid"],entry_after["session"]),identity)
            self.assertEqual(entry_after["commit_receipt"],original_commit)
            self.assertEqual(p2_runtime.workload_state(entry_after)[0],"LIVE")
            self.assertEqual(pathlib.Path(original_commit["path"]).read_bytes(),original_bytes)
            direct1=p2_runtime.inspect(req); direct2=p2_runtime.recover(req)
            self.assertEqual(direct1["status"],"COMMITTED",direct1)
            self.assertEqual(direct2["status"],"COMMITTED",direct2)
            self.assertEqual(direct1["commit_receipt"],original_commit)
            self.assertEqual(direct2["commit_receipt"],original_commit)

            try: os.killpg(entry_after["pgid"],signal.SIGKILL)
            except ProcessLookupError: pass
            if entry_after.get("collector"):
                try: os.kill(entry_after["collector"]["pid"],signal.SIGKILL)
                except ProcessLookupError: pass

    def test_real_runtime_receipts_and_sigkill_reconcile(self):
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)
            coord=root/"coordinator";runtime=root/"runtime"
            coord.mkdir(mode=0o700); runtime.mkdir(mode=0o700)
            plan={"schema":1,"release":"a"*64,"batches":["service"]}
            req={"schema":1,"scope":"ISOLATED_TEST_ONLY",
                 "installation_id":"i1","batch_id":"service","attempt_id":"a1",
                 "root":str(runtime),"version":"a"*64,
                 "deadline_utc":int(time.time())+30,
                 "inputs":{"operation":"start",
                           "argv":[sys.executable,"-c","import time;time.sleep(120)"],
                           "cwd":str(runtime),"env":{},
                           "health":{"type":"process"},"timeout":0.2}}
            class Adapter:
                execute=staticmethod(p2_runtime.execute)
                inspect=staticmethod(p2_runtime.inspect)
                recover=staticmethod(p2_runtime.recover)
            with Coordinator(str(coord),plan,{"service":Adapter()},component_roots={"service":str(runtime)}) as c:
                executed=c.execute(req)
                self.assertEqual(executed["status"],"COMMITTED",executed)
                observed=c.inspect(req)
                self.assertEqual(observed["status"],"COMMITTED",observed)
                self.assertNotEqual(executed["receipt"],observed["receipt"])
            entry=json.loads((runtime/"batch-service.json").read_text())
            self.assertTrue(entry["operation_id"])
            self.assertTrue(entry["config_sha256"])
            self.assertEqual(entry["commit_receipt"],executed["receipt"])
            os.kill(entry["pid"],signal.SIGKILL)
            time.sleep(0.2)
            with Coordinator(str(coord),plan,{"service":Adapter()},component_roots={"service":str(runtime)}) as c:
                restored=c.recover(req)
                self.assertEqual(restored["status"],"HOLD",restored)
                self.assertEqual(c.journal.latest("service")[1],"COMMITTED")
            if p2_runtime.proc(entry["pid"]) is not None:
                try: os.waitpid(entry["pid"],os.WNOHANG)
                except ChildProcessError: pass
            if "collector" in entry:
                try: os.kill(entry["collector"]["pid"],signal.SIGTERM)
                except ProcessLookupError: pass

if __name__=="__main__": unittest.main()
