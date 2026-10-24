import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from services.ocr_engine.build_offline_bundle import BundleError, validate_inputs

class OfflineBundleInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.models=self.root/"models"; self.models.mkdir()
        self.wheels=self.root/"wheelhouse"; self.wheels.mkdir()
        self.requirements=self.root/"requirements.txt"; self.requirements.write_text("demo==1.0\n")
        self.manifest=self.root/"model_manifest.json"
        self.model_files={}
        for name in ("det","rec","cls"):
            filename=name+".onnx"; data=("synthetic-"+name).encode()
            (self.models/filename).write_bytes(data)
            self.model_files[name]={"filename":filename,"sha256":hashlib.sha256(data).hexdigest()}
        self.manifest.write_text(json.dumps({"model_set":{"files":self.model_files}}))
        self.license=self.root/"LICENSE-2.0.txt"; self.license.write_text("Apache License Version 2.0")
        self.notice=self.root/"NOTICE.md"
        self.notice.write_text("\n".join(x["filename"]+" "+x["sha256"] for x in self.model_files.values()))
        self.schema=self.root/"schema.json"; self.schema.write_text("{}")
        wheel=self.wheels/"demo-1.0-py3-none-any.whl"; wheel.write_bytes(b"synthetic wheel")
        self.lock=self.root/"lock.json"
        self.lock.write_text(json.dumps({"target_platform":"linux-x86_64-cp311","python_implementation":"CPython","python_version":"3.11","abi":"cp311","requirements_sha256":hashlib.sha256(self.requirements.read_bytes()).hexdigest(),"wheels":[{"filename":wheel.name,"sha256":hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
    def tearDown(self): self.tmp.cleanup()
    def check(self,platform="linux-x86_64-cp311"):
        return validate_inputs(platform,self.lock,self.wheels,self.models,self.requirements,self.manifest,self.license,self.notice,self.schema)
    def test_valid_explicit_platform_and_all_pinned_assets_pass(self):
        result=self.check()
        self.assertEqual(result["target_platform"],"linux-x86_64-cp311")
        self.assertEqual(len(result["verified_models"]),3)
        self.assertEqual(len(result["verified_wheels"]),1)
    def test_platform_mismatch_rejected(self):
        with self.assertRaisesRegex(BundleError,"TARGET_PLATFORM_MISMATCH"): self.check("win-amd64-cp311")
    def test_missing_model_rejected(self):
        (self.models/"rec.onnx").unlink()
        with self.assertRaisesRegex(BundleError,"MODEL_NOT_REGULAR_FILE"): self.check()
    def test_tampered_model_rejected(self):
        (self.models/"det.onnx").write_bytes(b"tampered")
        with self.assertRaisesRegex(BundleError,"MODEL_SHA256_MISMATCH:det"): self.check()
    def test_tampered_wheel_rejected(self):
        (self.wheels/"demo-1.0-py3-none-any.whl").write_bytes(b"tampered wheel")
        with self.assertRaisesRegex(BundleError,"WHEEL_SHA256_MISMATCH"): self.check()
    def test_requirements_change_invalidates_lock(self):
        self.requirements.write_text("demo==2.0\n")
        with self.assertRaisesRegex(BundleError,"REQUIREMENTS_LOCK_INPUT_SHA_MISMATCH"): self.check()
    def test_notice_missing_model_attribution_rejected(self):
        self.notice.write_text("Apache License only")
        with self.assertRaisesRegex(BundleError,"MODEL_NOTICE_MISSING_ATTRIBUTION:det"): self.check()

if __name__=="__main__": unittest.main()
