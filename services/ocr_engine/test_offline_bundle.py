import hashlib
import json
import tempfile
import unittest
import zipfile
import os
import subprocess
from unittest import mock
import services.ocr_engine.build_offline_bundle as builder
from services.ocr_engine.build_offline_bundle import validate_deb_cache
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
        self.lock.write_text(json.dumps({"target_platform":"linux-x86_64-cp311","python_implementation":"CPython","python_version":"3.11.17","abi":"cp311","soabi":"cpython-311-x86_64-linux-gnu","base_image":"python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199","base_image_manifest_sha256":"8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199","base_image_config_sha256":"c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee","glibc_version":"glibc 2.36","target_tags":["cp311-cp311-manylinux_2_17_x86_64","py3-none-any"],"requirements_sha256":hashlib.sha256(self.requirements.read_bytes()).hexdigest(),"wheels":[{"filename":wheel.name,"sha256":hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
    def tearDown(self): self.tmp.cleanup()
    def check(self,platform="linux-x86_64-cp311"):
        return validate_inputs(platform,self.lock,self.wheels,self.models,self.requirements,self.manifest,self.license,self.notice,self.schema)
    def test_valid_explicit_platform_and_all_pinned_assets_pass(self):
        result=self.check()
        self.assertEqual(result["target_platform"],"linux-x86_64-cp311")
        self.assertEqual(len(result["verified_models"]),3)
        self.assertEqual(len(result["verified_wheels"]),1)
    def test_base_image_manifest_or_config_mismatch_rejected(self):
        lock=json.loads(self.lock.read_text())
        lock["base_image_manifest_sha256"]="0"*64
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(BundleError,"LOCK_BASE_MANIFEST_MISMATCH"): self.check()

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
        self.lock.write_text(json.dumps({'target_platform':'linux-x86_64-cp311','python_implementation':'CPython','python_version':'3.11.17','abi':'cp311','soabi':'cpython-311-x86_64-linux-gnu','base_image':'python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199','base_image_manifest_sha256':'8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199','base_image_config_sha256':'c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee','glibc_version':'glibc 2.36','target_tags':['cp311-cp311-manylinux_2_17_x86_64','py3-none-any'],'requirements_sha256':hashlib.sha256(self.requirements.read_bytes()).hexdigest(),'wheels':[{'filename':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
        with self.assertRaisesRegex(BundleError,'WHEEL_TARGET_TAG_MISMATCH'): self.check()
    def test_filename_and_internal_wheel_tags_must_match(self):
        wheel=self.wheels/'demo-1.0-py3-none-any.whl'
        with zipfile.ZipFile(wheel,'w') as z:
            z.writestr('demo-1.0.dist-info/WHEEL','Wheel-Version: 1.0\nTag: cp312-cp312-win_amd64\n')
        self.lock.write_text(json.dumps({'target_platform':'linux-x86_64-cp311','python_implementation':'CPython','python_version':'3.11.17','abi':'cp311','soabi':'cpython-311-x86_64-linux-gnu','base_image':'python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199','base_image_manifest_sha256':'8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199','base_image_config_sha256':'c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee','glibc_version':'glibc 2.36','target_tags':['cp311-cp311-manylinux_2_17_x86_64','py3-none-any'],'requirements_sha256':hashlib.sha256(self.requirements.read_bytes()).hexdigest(),'wheels':[{'filename':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
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
    def test_manual_hosted_build_is_default_closed_and_pinned(self):
        workflow=Path(__file__).resolve().parents[2]/".github"/"workflows"/"ocr-engine-tests.yml"
        text=workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:",text)
        self.assertIn("default: false",text)
        self.assertIn("inputs.build_enabled == true",text)
        self.assertIn("if: ${{ github.event_name != 'workflow_dispatch' }}",text)
        self.assertIn("refs/heads/docs/self-hosted-ocr-architecture-20261024",text)
        self.assertIn('test "$INPUT_SOURCE_SHA" = "$GITHUB_SHA"',text)
        self.assertIn("python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199",text)
        self.assertIn("c8bff6acecbf3f8b9f87bc3193032b39ead42bcc39fb76a4875ebd89975874ee",text)
        self.assertIn("permissions:\n      contents: read",text)
        self.assertNotIn("runs-on: self-hosted",text)
        self.assertNotIn("secrets.",text)
        self.assertIn("docker run --rm --network none --platform linux/amd64",text)

    def test_requirements_use_only_one_official_opencv_distribution(self):
        req=(Path(__file__).with_name("requirements.txt")).read_text(encoding="utf-8")
        self.assertIn("opencv-python==4.11.0.86",req)
        self.assertNotIn("opencv-python-headless",req)
        self.assertEqual(sum(1 for line in req.splitlines() if line.lower().startswith("opencv-python")),1)
    def test_workflow_captures_hashed_deb_closure_and_failed_candidate_inputs(self):
        workflow=Path(__file__).resolve().parents[2]/".github"/"workflows"/"ocr-engine-tests.yml"
        text=workflow.read_text(encoding="utf-8")
        self.assertIn("Resolve official Debian runtime shared-library closure for OpenCV",text)
        self.assertIn("system-deb-lock.json",text)
        self.assertIn("--system-deb-cache",text)
        self.assertIn("xuanjun-ocr-candidate-inputs-not-release-",text)
        self.assertIn("if: always()",text)
        self.assertIn("ocr-deb-cache",text)
        self.assertIn("apt-get install -y --download-only",text)
        self.assertIn("dpkg-deb",text)

    def test_deb_runtime_closure_lock_is_hash_bound(self):
        debs=self.root/"debs"; debs.mkdir()
        apt=(debs/"apt-lists"); apt.mkdir()
        apt_index=apt/"bookworm-main-Packages"; apt_index.write_bytes(b"synthetic apt index")
        pkgroot=self.root/"pkgroot"; (pkgroot/"DEBIAN").mkdir(parents=True)
        (pkgroot/"DEBIAN"/"control").write_text("Package: libxcb1\\nVersion: 1.0\\nArchitecture: amd64\\nMaintainer: OCR test <test@example.invalid>\\nDescription: synthetic test package\\n")
        package=debs/"libxcb1_1.0_amd64.deb"
        subprocess.run(["dpkg-deb","--build",str(pkgroot),str(package)],check=True,capture_output=True,text=True)
        source_content="Types: deb\nURIs: https://deb.debian.org/debian\nSuites: bookworm bookworm-updates\nComponents: main\n"
        lock={"base_image":"python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199",
              "apt_source":{"path":"debian.sources","sha256":hashlib.sha256(source_content.encode()).hexdigest(),"content":source_content},
              "packages":[{"filename":package.name,"package":"libxcb1","version":"1.0","architecture":"amd64","sha256":hashlib.sha256(package.read_bytes()).hexdigest()}],
              "apt_lists":[{"path":apt_index.name,"bytes":apt_index.stat().st_size,"sha256":hashlib.sha256(apt_index.read_bytes()).hexdigest()}]}
        (debs/"system-deb-lock.json").write_text(json.dumps(lock))
        verified,lock_path,verified_apt,lock_snapshot,lock_sha=validate_deb_cache(debs)
        self.assertEqual(len(verified),1)
        self.assertEqual(lock_snapshot,(debs/"system-deb-lock.json").read_bytes())
        self.assertEqual(lock_sha,hashlib.sha256(lock_snapshot).hexdigest())
        self.assertEqual(verified[0][1],"system-debs/"+package.name)
        self.assertEqual(len(verified_apt),1)
        self.assertEqual(verified_apt[0][1],"system-apt-lists/"+apt_index.name)
        self.assertEqual(lock_path,debs/"system-deb-lock.json")
        package.write_bytes(b"tampered deb")
        with self.assertRaisesRegex(BundleError,"DEB_SHA256_MISMATCH"): validate_deb_cache(debs)

    def test_deb_lock_change_after_validation_is_not_retrusted(self):
        debs=self.root/"debs"; debs.mkdir()
        apt=debs/"apt-lists"; apt.mkdir()
        apt_index=apt/"Packages"; apt_index.write_bytes(b"index")
        pkgroot=self.root/"pkgroot2"; (pkgroot/"DEBIAN").mkdir(parents=True)
        (pkgroot/"DEBIAN"/"control").write_text("Package: libxcb1\\nVersion: 1.0\\nArchitecture: amd64\\nMaintainer: OCR test <test@example.invalid>\\nDescription: synthetic test package\\n")
        package=debs/"libxcb1_1.0_amd64.deb"
        subprocess.run(["dpkg-deb","--build",str(pkgroot),str(package)],check=True,capture_output=True,text=True)
        source_content="Types: deb\nURIs: https://deb.debian.org/debian\nSuites: bookworm\nComponents: main\n"
        lock={"base_image":"python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199",
              "apt_source":{"path":"debian.sources","sha256":hashlib.sha256(source_content.encode()).hexdigest(),"content":source_content},
              "packages":[{"filename":package.name,"package":"libxcb1","version":"1.0","architecture":"amd64","sha256":hashlib.sha256(package.read_bytes()).hexdigest()}],
              "apt_lists":[{"path":"Packages","bytes":apt_index.stat().st_size,"sha256":hashlib.sha256(apt_index.read_bytes()).hexdigest()}]}
        lock_path=debs/"system-deb-lock.json"; lock_path.write_text(json.dumps(lock))
        _,_,_,snapshot,digest=validate_deb_cache(debs)
        lock_path.write_text(json.dumps({**lock,"packages":[]}))
        self.assertNotEqual(hashlib.sha256(lock_path.read_bytes()).hexdigest(),digest)
        self.assertNotEqual(lock_path.read_bytes(),snapshot)
    def test_builder_rejects_deb_lock_mutation_after_validation_before_freeze(self):
        package=self.root/"runtime-package"; (package/"model_distribution").mkdir(parents=True)
        for name in ("api.py","ocr_core.py","secure_store.py","startup_selfcheck.py"):
            (package/name).write_text("# synthetic "+name)
        (package/"model_manifest.json").write_text(self.manifest.read_text())
        (package/"requirements.txt").write_text(self.requirements.read_text())
        (package/"model_distribution"/"LICENSE-2.0.txt").write_text(self.license.read_text())
        (package/"model_distribution"/"NOTICE.md").write_text(self.notice.read_text())
        (package/"deployment_config.schema.json").write_text("{}")
        debs=self.root/"deb-race"; debs.mkdir()
        apt=debs/"apt-lists"; apt.mkdir()
        index=apt/"Packages"; index.write_bytes(b"synthetic apt index")
        pkgroot=self.root/"deb-package"; (pkgroot/"DEBIAN").mkdir(parents=True)
        (pkgroot/"DEBIAN"/"control").write_text("Package: libxcb1\\nVersion: 1.0\\nArchitecture: amd64\\nMaintainer: OCR test <test@example.invalid>\\nDescription: synthetic test package\\n")
        deb=debs/"libxcb1_1.0_amd64.deb"
        subprocess.run(["dpkg-deb","--build",str(pkgroot),str(deb)],check=True,capture_output=True,text=True)
        source_content="Types: deb\nURIs: https://deb.debian.org/debian\nSuites: bookworm\nComponents: main\n"
        lock={"base_image":"python:3.11-slim-bookworm@sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199",
              "apt_source":{"path":"debian.sources","sha256":hashlib.sha256(source_content.encode()).hexdigest(),"content":source_content},
              "packages":[{"filename":deb.name,"package":"libxcb1","version":"1.0","architecture":"amd64","sha256":hashlib.sha256(deb.read_bytes()).hexdigest()}],
              "apt_lists":[{"path":"Packages","bytes":index.stat().st_size,"sha256":hashlib.sha256(index.read_bytes()).hexdigest()}]}
        lock_path=debs/"system-deb-lock.json"; lock_path.write_text(json.dumps(lock))
        original_validate=builder.validate_deb_cache
        def validate_then_mutate(path):
            result=original_validate(path)
            lock_path.write_text(json.dumps({**lock,"packages":[]}))
            return result
        output=self.root/"deb-lock-race.tar.gz"
        with (mock.patch.object(builder,"HERE",package),
              mock.patch.object(builder,"MODEL_MANIFEST",package/"model_manifest.json"),
              mock.patch.object(builder,"REQUIREMENTS",package/"requirements.txt"),
              mock.patch.object(builder,"LICENSE",package/"model_distribution"/"LICENSE-2.0.txt"),
              mock.patch.object(builder,"NOTICE",package/"model_distribution"/"NOTICE.md"),
              mock.patch.object(builder,"CONFIG_SCHEMA",package/"deployment_config.schema.json"),
              mock.patch.object(builder,"validate_deb_cache",side_effect=validate_then_mutate)):
            with self.assertRaisesRegex(BundleError,"VALIDATE_FREEZE_SHA256_MISMATCH:system-deb-lock.json"):
                builder.build_bundle("linux-x86_64-cp311",self.lock,self.wheels,self.models,output,system_deb_cache=debs)
        self.assertFalse(output.exists())

    def test_candidate_manifest_classifies_model_by_actual_pinned_sha(self):
        manifest=Path(__file__).with_name("model_manifest.json")
        data=json.loads(manifest.read_text(encoding="utf-8"))
        expected={v["filename"]:v["sha256"] for v in data["model_set"]["files"].values()}
        self.assertEqual(len(expected),3)
        script=Path(__file__).with_name("write_candidate_input_manifest.py").read_text(encoding="utf-8")
        self.assertIn("actual == trusted_model_hashes[path.name]",script)
        self.assertIn("downloaded-and-self-hashed-only-not-trusted-by-model-manifest",script)
    def test_runtime_check_requires_ldd_closure_and_single_opencv_distribution(self):
        script=Path(__file__).with_name("verify_offline_runtime.py").read_text(encoding="utf-8")
        self.assertIn("ldd",script)
        self.assertIn("not found",script)
        self.assertIn("opencv-python-headless",script)
        self.assertIn("pip"," ".join(script.split()))
    def test_workflow_uses_scripts_instead_of_inline_python_heredocs(self):
        workflow=Path(__file__).resolve().parents[2]/".github"/"workflows"/"ocr-engine-tests.yml"
        text=workflow.read_text(encoding="utf-8")
        self.assertIn("generate_deb_runtime_lock.py",text)
        self.assertIn("verify_offline_runtime.py",text)
        self.assertIn("write_candidate_input_manifest.py",text)
        self.assertNotIn("python - <<'PY'",text)
        self.assertIn("ocr-build/**",text)
        self.assertIn('source-pins/"',text)
        self.assertIn("model_distribution/NOTICE.md",text)
        self.assertIn("model_manifest.json",text)
    def test_candidate_artifact_is_always_uploaded_but_not_release(self):
        workflow=Path(__file__).resolve().parents[2]/".github"/"workflows"/"ocr-engine-tests.yml"
        text=workflow.read_text(encoding="utf-8")
        self.assertIn("xuanjun-ocr-candidate-inputs-not-release-",text)
        self.assertIn("Upload reusable candidate inputs and their digest manifest",text)
        self.assertIn("Upload verified package only after successful build",text)
        self.assertIn("if: success()",text)
        self.assertIn("ocr-deb-cache/**",text)

    def test_notice_missing_model_attribution_rejected(self):
        self.notice.write_text("Apache License only")
        with self.assertRaisesRegex(BundleError,"MODEL_NOTICE_MISSING_ATTRIBUTION:det"): self.check()

if __name__=="__main__": unittest.main()
