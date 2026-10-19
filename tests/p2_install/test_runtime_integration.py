"""Runs with EXACT window-two source staged read-only by CI. No network."""
import json, os, pathlib, signal, subprocess, sys, tempfile, time, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from production.p2_install.coordinator import Coordinator
from production import p2_runtime

class RuntimeIntegration(unittest.TestCase):
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
