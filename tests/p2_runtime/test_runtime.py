import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "production"))
from p2_runtime import execute, inspect, recover

class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "owned"
        self.root.mkdir(mode=0o700)
        self.pids = []

    def tearDown(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.temp.cleanup()

    def req(self, batch="b1", operation="start", argv=None):
        return {"schema": 1, "scope": "ISOLATED_TEST_ONLY", "installation_id": "install",
                "batch_id": batch, "attempt_id": "attempt-" + batch, "root": str(self.root),
                "inputs": {"operation": operation, "argv": argv or
                           [sys.executable, "-c", "import time;time.sleep(60)"],
                           "cwd": str(self.root), "env": {}, "health": {"type": "process"}, "timeout": 0.1}}

    def test_real_start_duplicate_recover_stop(self):
        req = self.req()
        result = execute(req)
        self.assertEqual(result["status"], "COMMITTED", result)
        record = json.loads((self.root / "batch-b1.json").read_text())
        self.pids.append(record["pid"])
        self.assertEqual(execute(req)["status"], "COMMITTED")
        self.assertEqual(inspect(req)["status"], "COMMITTED")
        self.assertEqual(recover(req)["status"], "COMMITTED")
        stop = self.req(operation="stop")
        self.assertEqual(execute(stop)["status"], "COMMITTED")
        self.assertEqual(recover(req)["status"], "NO_EFFECT")
        self.assertEqual(execute(req)["status"], "HOLD")

    def test_wrong_pid_start_time_and_batch_isolation(self):
        first, second = self.req("first"), self.req("second")
        self.assertEqual(execute(first)["status"], "COMMITTED")
        self.assertEqual(execute(second)["status"], "COMMITTED")
        for batch in ("first", "second"):
            self.pids.append(json.loads((self.root / ("batch-" + batch + ".json")).read_text())["pid"])
        p = self.root / "batch-second.json"
        record = json.loads(p.read_text())
        record["start"] = "0"
        p.write_text(json.dumps(record))
        self.assertEqual(execute(self.req("second", "stop"))["error"]["code"], "PID_IDENTITY_MISMATCH")
        self.assertEqual(inspect(first)["status"], "COMMITTED")
        self.assertEqual(execute(self.req("first", "stop"))["status"], "COMMITTED")

    def test_invalid_shell_and_absent_batch(self):
        self.assertEqual(inspect(self.req())["status"], "NO_EFFECT")
        with self.assertRaises(Exception):
            execute(self.req(argv=["/bin/sh", "-c", "sleep 60"]))
        self.assertFalse((self.root / "batch-b1.json").exists())

    def test_real_short_lived_process_not_committed(self):
        result = execute(self.req(argv=[sys.executable, "-c", "pass"]))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(recover(self.req())["status"], "NO_EFFECT")

    def test_prepared_unknown_never_restarts(self):
        req = self.req()
        p = self.root / "batch-b1.json"
        p.write_text(json.dumps({"installation_id": "install", "attempt_id": "attempt-b1",
                                "batch_id": "b1", "phase": "PREPARED", "log": str(self.root / "test.log")}))
        self.assertEqual(recover(req)["status"], "HOLD")
        self.assertEqual(execute(req)["status"], "HOLD")

    def test_receipt_sha_and_cli(self):
        req = self.req()
        result = inspect(req)
        import hashlib
        self.assertEqual(result["receipt"]["sha256"], hashlib.sha256(Path(result["receipt"]["path"]).read_bytes()).hexdigest())
        process = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / "production/p2_runtime/__init__.py"), "inspect"],
                                 input=json.dumps(req), text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "NO_EFFECT")

if __name__ == "__main__":
    unittest.main()
