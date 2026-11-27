"""Runtime selection tests, not bubblewrap or production execution evidence."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from native_sandbox_runner import _python_runtime,plan_manifest,digest,BubblewrapNativeRunner,HARNESS

ROOT=Path(__file__).resolve().parents[1]

class NativeRunnerPythonRuntime(unittest.TestCase):
    def test_default_uses_declared_actual_interpreter_not_python36(self):
        runtime=_python_runtime()
        self.assertEqual(runtime["executable"],os.path.realpath(sys.executable))
        self.assertGreaterEqual(tuple(runtime["version"]),(3,11,0))
        self.assertEqual(runtime["sha256"],hashlib.sha256(Path(runtime["executable"]).read_bytes()).hexdigest())
    def test_explicit_host_interpreter_is_same_canonical_runtime(self):
        self.assertEqual(_python_runtime(sys.executable),_python_runtime())
    def test_unmounted_or_missing_interpreter_cannot_run_on_host(self):
        with patch("native_sandbox_runner.subprocess.run",side_effect=AssertionError("must not spawn")):
            for path in ("/tmp/untrusted-python","/usr/nonexistent-tc-python"):
                with self.assertRaisesRegex(ValueError,"FIXED_SYSTEM_PYTHON_REQUIRED"):_python_runtime(path)
    def test_manifest_pins_runtime_and_does_not_accept_legacy_plan_digest(self):
        commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip()
        manifest=plan_manifest(str(ROOT),commit,python_executable=sys.executable)
        self.assertEqual(manifest["plan"],"TC_NATIVE_INTAKE_READONLY_V3")
        self.assertEqual(manifest["harness_sha256"],hashlib.sha256(HARNESS.encode()).hexdigest())
        legacy=dict(manifest);legacy.pop("python_runtime");legacy["plan"]="TC_NATIVE_INTAKE_READONLY_V2"
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"fixture.sqlite";path.touch()
            runner=BubblewrapNativeRunner(str(path),str(ROOT),commit,digest(manifest),python_executable=sys.executable)
            self.assertEqual(runner.python,manifest["python_runtime"]["executable"])
            with self.assertRaisesRegex(ValueError,"PINNED_FIXED_PLAN_DIGEST_REQUIRED"):
                BubblewrapNativeRunner(str(path),str(ROOT),commit,digest(legacy),python_executable=sys.executable)

    def test_runtime_drift_rejects_before_sandbox_send(self):
        from test_native_sandbox_runner import SandboxRunnerTests
        fixture=SandboxRunnerTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.runner.manifest['python_runtime']['sha256']='0'*64
        original=subprocess.Popen
        def forbid_sandbox(command,**kwargs):
            if command[0]=='/usr/bin/bwrap':raise AssertionError('must not send sandbox')
            return original(command,**kwargs)
        with patch('native_sandbox_runner.subprocess.Popen',side_effect=forbid_sandbox):
            with self.assertRaisesRegex(ValueError,'PINNED_PYTHON_RUNTIME_CHANGED'):
                fixture.run_plan()
        self.assertEqual(fixture.s.db.execute("SELECT count(*) FROM events WHERE kind='SANDBOX_INTENT'").fetchone()[0],0)

if __name__=="__main__":unittest.main()
