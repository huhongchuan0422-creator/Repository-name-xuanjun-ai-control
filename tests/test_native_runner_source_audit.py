"""Same-byte harness negatives; not bubblewrap isolation or a live receipt."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest
import native_sandbox_runner as runner

ROOT=Path(__file__).resolve().parents[1]

class NativeRunnerSourceAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/"scripts/development_entry_intake.py").read_bytes()
        text="import ast"+runner.HARNESS.split("import ast",1)[1]
        text=text.split("from development_entry_intake import validate_event",1)[0]
        text=text.replace("source=open('/work/scripts/development_entry_intake.py','rb').read()","source=CANDIDATE_BYTES")
        cls.audit=compile(text,"actual-pinned-harness-audit","exec")
        print("TESTED_RUNNER_BYTES "+json.dumps({
            "runner_sha256":hashlib.sha256((ROOT/"scripts/native_sandbox_runner.py").read_bytes()).hexdigest(),
            "runner_tests_sha256":hashlib.sha256((ROOT/"tests/test_native_sandbox_runner.py").read_bytes()).hexdigest(),
            "harness_sha256":hashlib.sha256(runner.HARNESS.encode()).hexdigest(),
            "intake_sha256":hashlib.sha256(cls.source).hexdigest(),
            "mode":"AUDIT_ONLY_NOT_ISOLATION_OR_LIVE_RECEIPT"},sort_keys=True))
    def audit_source(self,raw):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):exec(self.audit,{"CANDIDATE_BYTES":raw})
        return out.getvalue()
    def replace_validator(self,body):
        s=self.source.decode();start=s.index("def validate_event(");end=s.index("def bind_validated_receipt(",start)
        return (s[:start]+"def validate_event(event, control_repository, trusted_owner, destination=None):"+chr(10)+
            "".join("    "+line+chr(10) for line in body.splitlines())+s[end:]).encode()
    def reject(self,raw):
        with self.assertRaisesRegex(ValueError,"FIXED_PURE_VALIDATOR_PLAN_UNSUPPORTED_SOURCE"):
            self.audit_source(raw)
    def test_original_intake_is_supported_without_executing_candidate(self):
        self.assertIn("XJ_FIXED_PURE_CONTRACT_AUDITED",self.audit_source(self.source))
    def test_no_validator_cannot_forge_response(self):
        self.reject(("import os"+chr(10)+"os.write(1,b'XJ_FIXED_PURE_CONTRACT_AUDITED')"+chr(10)+"os._exit(0)").encode())
    def test_top_level_stdout_zero_exit_rejected_before_import(self):
        self.reject(self.source+(chr(10)+"os.write(1,b'XJ_SANDBOX_RESPONSE []')"+chr(10)+"os._exit(0)").encode())
    def test_validator_stdout_zero_exit_rejected_before_call(self):
        self.reject(self.replace_validator("os.write(1,b'XJ_SANDBOX_RESPONSE []')"+chr(10)+"os._exit(0)"))
    def test_globals_io_lookup_rejected(self):
        self.reject(self.replace_validator("return validate_event.__globals__['os']._exit(0)"))
    def test_json_hook_to_unaudited_main_rejected(self):
        self.reject(self.replace_validator("ignored = [0 for main in []]"+chr(10)+"return json.loads('[]', object_pairs_hook=main)"))
    def test_decorator_cannot_execute_before_audit(self):
        self.reject(self.source.replace(b"def validate_event(",("@os._exit(0)"+chr(10)+"def validate_event(").encode(),1))

if __name__=="__main__":unittest.main()
