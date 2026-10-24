import hashlib
import json
import tempfile
import unittest
import zipfile
import os
from unittest import mock
import services.ocr_engine.build_offline_bundle as builder
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
        wheel=self.wheels/"demo-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel,"w") as z:
            z.writestr("demo-1.0.dist-info/WHEEL","Wheel-Version: 1.0\nGenerator: synthetic\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
            z.writestr("demo.py","synthetic")
        self.lock=self.root/"lock.json"
        self.lock.write_text(json.dumps({"target_platform":"linux-x86_64-cp311","python_implementation":"CPython","python_version":"3.11","abi":"cp311","target_tags":["cp311-cp311-manylinux_2_17_x86_64","py3-none-any"],"requirements_sha256":hashlib.sha256(self.requirements.read_bytes()).hexdigest(),"wheels":[{"filename":wheel.name,"sha256":hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
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
    def test_cp312_windows_wheel_rejected_for_linux_cp311_target(self):
        wheel=self.wheels/'demo-1.0-cp312-cp312-win_amd64.whl'
        with zipfile.ZipFile(wheel,'w') as z:
            z.writestr('demo-1.0.dist-info/WHEEL','Wheel-Version: 1.0\nTag: cp312-cp312-win_amd64\n')
        self.lock.write_text(json.dumps({'target_platform':'linux-x86_64-cp311','python_implementation':'CPython','python_version':'3.11','abi':'cp311','target_tags':['cp311-cp311-manylinux_2_17_x86_64','py3-none-any'],'requirements_sha256':hashlib.sha256(self.requirements.read_bytes()).hexdigest(),'wheels':[{'filename':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
        with self.assertRaisesRegex(BundleError,'WHEEL_TARGET_TAG_MISMATCH'): self.check()
    def test_filename_and_internal_wheel_tags_must_match(self):
        wheel=self.wheels/'demo-1.0-py3-none-any.whl'
        with zipfile.ZipFile(wheel,'w') as z:
            z.writestr('demo-1.0.dist-info/WHEEL','Wheel-Version: 1.0\nTag: cp312-cp312-win_amd64\n')
        self.lock.write_text(json.dumps({'target_platform':'linux-x86_64-cp311','python_implementation':'CPython','python_version':'3.11','abi':'cp311','target_tags':['cp311-cp311-manylinux_2_17_x86_64','py3-none-any'],'requirements_sha256':hashlib.sha256(self.requirements.read_bytes()).hexdigest(),'wheels':[{'filename':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
        with self.assertRaisesRegex(BundleError,'WHEEL_FILENAME_INTERNAL_TAG_MISMATCH'): self.check()
    def test_default_cli_is_closed_without_explicit_build_flag(self):
        with mock.patch.object(builder,'build_bundle',side_effect=AssertionError('must not build')):
            self.assertEqual(builder.main(['--target-platform','linux-x86_64-cp311','--lock-json','x','--wheelhouse','w','--model-cache','m','--output','/tmp/new.tar.gz']),3)
    def test_output_existing_target_is_never_overwritten(self):
        output=self.root/'existing.tar.gz'; output.write_bytes(b'preserve-me')
        with self.assertRaisesRegex(BundleError,'OUTPUT_MUST_BE_ABSOLUTE_AND_NOT_EXIST'):
            builder.build_bundle('linux-x86_64-cp311',self.lock,self.wheels,self.models,output)
        self.assertEqual(output.read_bytes(),b'preserve-me')
    def test_output_name_race_fails_without_overwriting_winner(self):
        temp=self.root/'staged.tmp'; temp.write_bytes(b'our archive')
        output=self.root/'winner.tar.gz'
        def race_link(src,dst,follow_symlinks=False):
            Path(dst).write_bytes(b'concurrent winner')
            raise FileExistsError(str(dst))
        with mock.patch.object(builder.os,'link',side_effect=race_link):
            with self.assertRaisesRegex(BundleError,'OUTPUT_ALREADY_EXISTS_NO_CLOBBER'): builder.publish_no_clobber(temp,output)
        self.assertEqual(output.read_bytes(),b'concurrent winner')
        self.assertTrue(temp.exists())
    def test_validate_to_freeze_model_change_is_rejected_against_validated_digest(self):
        model=self.models/"det.onnx"
        original=model.read_bytes()
        output=self.root/"race-before-freeze.tar.gz"
        original_validate=builder.validate_inputs
        def validate_then_mutate(*args,**kwargs):
            checked=original_validate(*args,**kwargs)
            model.write_bytes(b"B-after-validate-before-freeze")
            return checked
        try:
            with (mock.patch.object(builder,"HERE",self.root/"package"),
                  mock.patch.object(builder,"MODEL_MANIFEST",self.manifest),
                  mock.patch.object(builder,"REQUIREMENTS",self.requirements),
                  mock.patch.object(builder,"LICENSE",self.license),
                  mock.patch.object(builder,"NOTICE",self.notice),
                  mock.patch.object(builder,"CONFIG_SCHEMA",self.schema),
                  mock.patch.object(builder,"validate_inputs",side_effect=validate_then_mutate)):
                package=self.root/"package"; (package/"model_distribution").mkdir(parents=True,exist_ok=True)
                for name in ("api.py","ocr_core.py","secure_store.py","startup_selfcheck.py"):
                    (package/name).write_text("# synthetic "+name)
                with self.assertRaisesRegex(BundleError,"VALIDATE_FREEZE_SHA256_MISMATCH:models/det.onnx"):
                    builder.build_bundle("linux-x86_64-cp311",self.lock,self.wheels,self.models,output)
        finally:
            model.write_bytes(original)
        self.assertFalse(output.exists())

    def test_archive_member_tampering_between_validation_and_packaging_is_detected(self):
        package=self.root/'package'; (package/'model_distribution').mkdir(parents=True)
        for name in ('api.py','ocr_core.py','secure_store.py','startup_selfcheck.py'): (package/name).write_text('# synthetic source '+name)
        manifest_path=package/'model_manifest.json'; manifest_path.write_text(self.manifest.read_text())
        req_path=package/'requirements.txt'; req_path.write_text(self.requirements.read_text())
        license_path=package/'model_distribution'/'LICENSE-2.0.txt'; license_path.write_text(self.license.read_text())
        notice_path=package/'model_distribution'/'NOTICE.md'; notice_path.write_text(self.notice.read_text())
        schema_path=package/'deployment_config.schema.json'; schema_path.write_text('{}')
        output=self.root/'bundle.tar.gz'
        original_add=builder.tarfile.TarFile.add
        mutated={'done':False}
        def mutate_while_adding(archive,name,arcname=None,recursive=True,filter=None):
            path=Path(name)
            if arcname=='models/det.onnx' and not mutated['done']:
                original=path.read_bytes(); path.write_bytes(b'B-after-freeze');
                try: return original_add(archive,name,arcname=arcname,recursive=recursive,filter=filter)
                finally: path.write_bytes(original); mutated['done']=True
            return original_add(archive,name,arcname=arcname,recursive=recursive,filter=filter)
        with (mock.patch.object(builder,'HERE',package),
              mock.patch.object(builder,'MODEL_MANIFEST',manifest_path),
              mock.patch.object(builder,'REQUIREMENTS',req_path),
              mock.patch.object(builder,'LICENSE',license_path),
              mock.patch.object(builder,'NOTICE',notice_path),
              mock.patch.object(builder,'CONFIG_SCHEMA',schema_path),
              mock.patch.object(builder.tarfile.TarFile,'add',new=mutate_while_adding)):
            with self.assertRaisesRegex(BundleError,'ARCHIVE_MEMBER_SHA256_MISMATCH:models/det.onnx'):
                builder.build_bundle('linux-x86_64-cp311',self.lock,self.wheels,self.models,output)
        self.assertTrue(mutated['done'])
        self.assertFalse(output.exists())
    def test_notice_missing_model_attribution_rejected(self):
        self.notice.write_text("Apache License only")
        with self.assertRaisesRegex(BundleError,"MODEL_NOTICE_MISSING_ATTRIBUTION:det"): self.check()

if __name__=="__main__": unittest.main()
