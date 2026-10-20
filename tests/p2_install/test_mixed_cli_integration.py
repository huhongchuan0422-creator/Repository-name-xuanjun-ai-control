"""Positive mixed CLI contract; failures are real FAIL, never expectedFailure.

Stage exact pinned files under P2_MIXED_CLI_SOURCE_ROOT before running.
No network, injected adapters, production configuration, or attempt quota.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PINS = {'production/p2_artifacts/__init__.py': {'commit': 'ea31dbbec2a8710b964efb38fa2975684bbd9739', 'git_blob': 'fd4d33afc0352f413c7a6d114759618f1a9fb6d8'}, 'production/p2_artifacts/__main__.py': {'commit': 'ea31dbbec2a8710b964efb38fa2975684bbd9739', 'git_blob': '9cb7e62c1ffb040149cf467460c084069a412a98'}, 'production/p2_artifacts/installer.py': {'commit': 'ea31dbbec2a8710b964efb38fa2975684bbd9739', 'git_blob': '2be13684afb604360e5db1acc2645a70d7fff20b'}, 'production/p2_runtime/__init__.py': {'commit': '499bcc43f4c992b21035c22446ccc4d915873fb1', 'git_blob': '61ae1b4fc311403ec6fa416464c4e71243b232b8'}, 'production/p2_install/coordinator.py': {'commit': 'a4a1614b985a3b45f050906f1768039f24453cf2', 'git_blob': 'd5bf5b5c2443f6daf71fee0cda6db61eafe4a486'}, 'production/p2_install/journal.py': {'commit': 'a4a1614b985a3b45f050906f1768039f24453cf2', 'git_blob': '6c4e198949d8e2379ed6d47b6882b47534d4dd46'}, 'tests/p2_install/test_component_chain_integration.py': {'commit': 'a4a1614b985a3b45f050906f1768039f24453cf2', 'git_blob': '74b380a6081a832d24af3d7a65667292adc36802'}}

class MixedCLIIntegration(unittest.TestCase):
    def check_chain(self, runtime_flag):
        source = Path(os.environ.get("P2_MIXED_CLI_SOURCE_ROOT", Path(__file__).resolve().parents[2]))
        evidence = Path(tempfile.mkdtemp(prefix="p2-mixed-cli-", dir=os.environ.get("P2_MIXED_CLI_EVIDENCE_DIR")))
        stage = evidence / "source"
        source_hashes = {}
        for relative, pin in PINS.items():
            raw = (source / relative).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            self.assertEqual(blob, pin["git_blob"], relative)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o400)
            source_hashes[relative] = dict(pin, sha256=hashlib.sha256(raw).hexdigest())
        sys.path.insert(0, str(stage))
        try:
            spec = importlib.util.spec_from_file_location("pinned_chain_fixture", stage / "tests/p2_install/test_component_chain_integration.py")
            fixture_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixture_module)
        finally:
            sys.path.remove(str(stage))
        fixture = fixture_module.ExactComponentChain()
        fixture.setUp()  # Reuse only filesystem/archive/service fixture, no injected calls.
        records = []
        try:
            fixture.plan["batches"] = ["artifact", "service"]
            plan = evidence / "plan.json"
            plan.write_text(json.dumps(fixture.plan))
            for batch, request in (("artifact", fixture.artifact_req), ("service", fixture.runtime_req)):
                request_path = evidence / (batch + "-request.json")
                raw = json.dumps(request, sort_keys=True).encode()
                request_path.write_bytes(raw)
                for action in ("execute", "inspect", "recover"):
                    command = [sys.executable, "-B", "-m", "production.p2_install.coordinator", action,
                        "--root", str(fixture.coord), "--plan", str(plan), "--request", str(request_path),
                        "--component-root", "artifact=" + str(fixture.artifacts),
                        "--component-root", "service=" + str(fixture.runtime)]
                    if runtime_flag:
                        command.append("--runtime")
                    result = subprocess.run(command, cwd=stage, capture_output=True, timeout=20,
                        env={"PATH": os.defpath, "HOME": str(evidence), "PYTHONDONTWRITEBYTECODE": "1"})
                    record = {"batch": batch, "action": action, "argv": command,
                        "request_sha256": hashlib.sha256(raw).hexdigest(), "exit_code": result.returncode,
                        "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace")}
                    try:
                        record["response"] = json.loads(record["stdout"])
                    except ValueError:
                        record["response"] = None
                    records.append(record)
            effects = {"program_exists": fixture.program.is_file(), "socket_exists": fixture.socket.exists()}
            shutil.copytree(fixture.coord.parent, evidence / "retained-state")
            report = {"scope": "ISOLATED_TEST_ONLY", "python": sys.version, "runtime_flag": runtime_flag,
                "sources": source_hashes, "calls": records, "effects": effects,
                "quota": "NONE", "production_executed": False}
            (evidence / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True))
            print("MIXED_CLI_EVIDENCE=" + str(evidence), flush=True)
            failures = [{"batch": r["batch"], "action": r["action"], "exit_code": r["exit_code"],
                "response": r["response"]} for r in records if r["exit_code"] != 0 or
                not isinstance(r["response"], dict) or r["response"].get("status") != "COMMITTED"]
            self.assertEqual(failures, [], json.dumps(failures, sort_keys=True))
            self.assertTrue(effects["program_exists"])
            self.assertTrue(effects["socket_exists"])
        finally:
            fixture.tearDown()

    def test_mixed_cli_default(self):
        self.check_chain(False)

    def test_mixed_cli_runtime_flag(self):
        self.check_chain(True)

if __name__ == "__main__":
    unittest.main()
