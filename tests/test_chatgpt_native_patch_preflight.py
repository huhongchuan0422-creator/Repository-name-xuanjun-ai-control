"""Issue19 source-only input preflight regressions."""
import hashlib
import importlib.util
from pathlib import Path
import copy
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("preflight",str(ROOT/"scripts/chatgpt_native_patch_preflight.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sample():
    text='print("hello")\n';raw=text.encode()
    return {"task_id":"task-19","entry":"CHATGPT",
            "execution_path":"CHATGPT_NATIVE",
            "control_repository":"owner/control",
            "target_repository":"owner/target",
            "target_base_sha":"a"*40,
            "spec_sha256":"b"*64,"checkpoint_sha256":"c"*64,
            "files":[{"path":"scripts/safe.py","sha256":hashlib.sha256(raw).hexdigest(),
                      "size":len(raw),"content_utf8":text}]}
class PreflightTests(unittest.TestCase):
    def test_valid_receipt_never_executes(self):
        r=m.inspect(sample(),["scripts/safe.py"])
        self.assertEqual(r["decision"],"SYNTAX_DATA_PRECHECK_ONLY")
        self.assertEqual(r["execution"],"FORBIDDEN")
        self.assertEqual(r["writer_permission"],"NOT_GRANTED")
    def test_bad_hash_and_changed_bytes(self):
        s=sample();s["files"][0]["content_utf8"]="print('changed')\n"
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/safe.py"])
    def test_path_traversal_and_private_targets(self):
        for p in ("../secrets","/root/.ssh/id_rsa",".git/config",
                  ".github/workflows/malicious.yml","a//b","a\\b"):
            s=sample();s["files"][0]["path"]=p
            with self.assertRaises(m.NativePatchHold):m.inspect(s,[p])
    def test_different_entry_or_branch(self):
        s=sample();s["execution_path"]="WORK_NATIVE"
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/safe.py"])
        s=sample();s["target_base_sha"]="invalid"
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/safe.py"])
    def test_duplicate_paths(self):
        s=sample();s["files"].append(copy.deepcopy(s["files"][0]))
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/safe.py"])
    def test_size_and_allowlist(self):
        s=sample();s["files"][0]["size"]=0
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/safe.py"])
        s=sample()
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/other.py"])
    def test_unknown_fields_fails_closed(self):
        s=sample();s["shell"]="sudo bash"
        with self.assertRaises(m.NativePatchHold):m.inspect(s,["scripts/safe.py"])
if __name__=="__main__":unittest.main()
