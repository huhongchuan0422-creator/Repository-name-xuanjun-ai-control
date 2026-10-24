import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ocr-engine-tests.yml"
EXPECTED_REF = "refs/heads/docs/self-hosted-ocr-architecture-20261024"

def load_build_job():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["build-offline-ocr-artifact"]["steps"]

def run_step(step, env):
    return subprocess.run(["bash", "-euo", "pipefail", "-c", step["run"]], env=env, text=True, capture_output=True)

class HostedBuildFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.log"
        docker = self.bin / "docker"
        fake_script_text = chr(10).join([
            "#!/usr/bin/env python3",
            "import json,os,sys",
            "with open(os.environ['FAKE_CALL_LOG'],'a',encoding='utf-8') as stream:",
            " stream.write(json.dumps(sys.argv[1:])+chr(10))",
            "args=sys.argv[1:]",
            "if args and args[0]=='pull': sys.exit(int(os.environ.get('FAKE_PULL_EXIT','0')))",
            "sys.exit(0)",
            "",
        ])
        compile(fake_script_text, str(docker), "exec")
        docker.write_text(fake_script_text, encoding="utf-8")
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin)+os.pathsep+os.environ.get("PATH",""), FAKE_CALL_LOG=str(self.calls),
                        RUNNER_TEMP=str(self.root), GITHUB_WORKSPACE=str(self.root), OCR_BASE_IMAGE="python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199",
                        OCR_BASE_CONFIG_SHA256="c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee",
                        OCR_TARGET_PLATFORM="linux-x86_64-cp311", GITHUB_SHA="a"*40, INPUT_SOURCE_SHA="a"*40,
                        GITHUB_REF=EXPECTED_REF)
    def tearDown(self):
        self.tmp.cleanup()
    def step(self, steps, name):
        return next(x for x in steps if x.get("name")==name)
    def test_source_gate_precedes_checkout_and_syntax_script_runs_after_checkout(self):
        steps=load_build_job()
        names=[x.get("name") or "checkout" for x in steps]
        gate=names.index("Validate explicit source, branch and target")
        checkout=next(i for i,x in enumerate(steps) if x.get("uses")=="actions/checkout@v4")
        syntax=names.index("Validate workflow YAML and all embedded shell blocks")
        pull=names.index("Pull and verify exact official base image")
        self.assertLess(gate,checkout)
        self.assertLess(checkout,syntax)
        self.assertLess(syntax,pull)
        self.assertEqual(steps[checkout]["with"]["ref"],"${{ inputs.source_sha }}")
    def test_wrong_ref_or_sha_stops_before_any_pull_or_run(self):
        steps=load_build_job()
        gate=self.step(steps,"Validate explicit source, branch and target")
        for key,value in (("GITHUB_REF","refs/heads/main"),("INPUT_SOURCE_SHA","b"*40)):
            with self.subTest(key=key):
                self.calls.write_text("")
                env=dict(self.env); env[key]=value
                result=run_step(gate,env)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                calls=[json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
                self.assertEqual(calls,[])
    def test_pull_failure_is_logged_and_never_runs_or_retries_base(self):
        steps=load_build_job()
        pull=self.step(steps,"Pull and verify exact official base image")
        self.calls.write_text("")
        env=dict(self.env,FAKE_PULL_EXIT="17")
        result=run_step(pull,env)
        self.assertNotEqual(result.returncode,0)
        calls=[json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls),1,calls)
        self.assertEqual(calls[0][0],"pull",calls)
        diagnostics=self.step(steps,"Record non-secret build/runtime diagnostics")["run"]
        self.assertNotIn("docker run",diagnostics)
        self.assertNotIn("docker pull",diagnostics)
        self.assertIn("docker image inspect",diagnostics)
    def test_actual_offline_install_step_uses_python_dpkg_query_and_network_none(self):
        steps=load_build_job()
        step=self.step(steps,"Install and import-check only from the offline wheelhouse in the same pinned base")
        self.calls.write_text("")
        result=run_step(step,self.env)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        calls=[json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls),1,calls)
        argv=calls[0]
        self.assertEqual(argv[0],"run",argv)
        self.assertIn("--network",argv,argv)
        self.assertEqual(argv[argv.index("--network")+1],"none",argv)
        self.assertIn("verify_offline_runtime.py"," ".join(argv))
        self.assertFalse(any("dpkg-query -W -f=" in arg for arg in argv))
    def test_workflow_has_no_always_run_or_pull_in_failure_diagnostics(self):
        steps=load_build_job()
        diag=self.step(steps,"Record non-secret build/runtime diagnostics")
        self.assertEqual(diag.get("if"),"always()")
        self.assertNotIn("docker run",diag["run"])
        self.assertNotIn("docker pull",diag["run"])
        self.assertIn("if: always()",WORKFLOW.read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()
