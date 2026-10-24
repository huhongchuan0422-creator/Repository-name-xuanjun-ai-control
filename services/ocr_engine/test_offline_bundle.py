import hashlib
import json
import tempfile
import unittest
import zipfile
import os
import sys
import subprocess
from unittest import mock
import services.ocr_engine.build_offline_bundle as builder
from services.ocr_engine.build_offline_bundle import validate_deb_cache
from pathlib import Path
from services.ocr_engine.build_offline_bundle import BundleError, validate_inputs
from services.ocr_engine.verify_offline_runtime import verify_shared_libraries

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
        self.assertIn("generate_deb_runtime_lock.py",text)

    def test_deb_lock_generator_reads_real_synthetic_package_and_official_source(self):
        root=self.root/"generated-debs"; root.mkdir()
        apt=root/"apt-lists"; apt.mkdir()
        (apt/"InRelease").write_bytes(b"synthetic apt metadata; not asserting signature")
        source=self.root/"debian.sources"
        source.write_text(chr(10).join(["Types: deb","URIs: https://deb.debian.org/debian","Suites: bookworm bookworm-updates","Components: main",""]))
        pkgroot=self.root/"generator-package"; (pkgroot/"DEBIAN").mkdir(parents=True)
        (pkgroot/"DEBIAN"/"control").write_text(chr(10).join(["Package: libxcb1","Version: 1.0","Architecture: amd64","Maintainer: OCR test <test@example.invalid>","Description: synthetic test package",""]))
        deb=root/"libxcb1_1.0_amd64.deb"
        subprocess.run(["dpkg-deb","--build",str(pkgroot),str(deb)],check=True,capture_output=True,text=True)
        script=Path(__file__).with_name("generate_deb_runtime_lock.py")
        result=subprocess.run([sys.executable,str(script),str(root),str(source),str(apt)],check=True,capture_output=True,text=True)
        lock=json.loads((root/"system-deb-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"][0]["package"],"libxcb1")
        self.assertEqual(lock["packages"][0]["version"],"1.0")
        self.assertEqual(lock["packages"][0]["architecture"],"amd64")
        self.assertEqual(lock["packages"][0]["sha256"],hashlib.sha256(deb.read_bytes()).hexdigest())
        self.assertEqual(lock["apt_source"]["path"],"debian.sources")
        self.assertEqual(lock["apt_source"]["content"],source.read_text(encoding="utf-8"))
        self.assertEqual(lock["apt_lists"][0]["path"],"InRelease")
        self.assertIn("LOCKED",result.stdout)

    def test_deb_runtime_closure_lock_is_hash_bound(self):
        debs=self.root/"debs"; debs.mkdir()
        apt=(debs/"apt-lists"); apt.mkdir()
        apt_index=apt/"bookworm-main-Packages"; apt_index.write_bytes(b"synthetic apt index")
        pkgroot=self.root/"pkgroot"; (pkgroot/"DEBIAN").mkdir(parents=True)
        (pkgroot/"DEBIAN"/"control").write_text(chr(10).join(["Package: libxcb1","Version: 1.0","Architecture: amd64","Maintainer: OCR test <test@example.invalid>","Description: synthetic test package",""]))
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
        (pkgroot/"DEBIAN"/"control").write_text(chr(10).join(["Package: libxcb1","Version: 1.0","Architecture: amd64","Maintainer: OCR test <test@example.invalid>","Description: synthetic test package",""]))
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
        (pkgroot/"DEBIAN"/"control").write_text(chr(10).join(["Package: libxcb1","Version: 1.0","Architecture: amd64","Maintainer: OCR test <test@example.invalid>","Description: synthetic test package",""]))
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
        self.assertIn("digest == trusted_model_hashes[path.name]",script)
        self.assertIn('"sha256":digest',script)
        self.assertIn("downloaded-and-self-hashed-only-not-trusted-by-model-manifest",script)
    def test_ldd_nonzero_one_fails_even_without_missing_text(self):
        candidate=self.root/"cv2.abi3.so"; candidate.write_bytes(b"fake ELF placeholder")
        result=subprocess.CompletedProcess(["ldd",str(candidate)],1,"not a dynamic executable\\n","")
        with self.assertRaisesRegex(RuntimeError,"LDD_FAILED"):
            verify_shared_libraries([candidate],runner=lambda *a,**k:result)
    def test_ldd_missing_library_fails(self):
        candidate=self.root/"cv2.abi3.so"; candidate.write_bytes(b"fake ELF placeholder")
        result=subprocess.CompletedProcess(["ldd",str(candidate)],0,"libxcb.so.1 => not found\\n","")
        with self.assertRaisesRegex(RuntimeError,"SHARED_LIBRARY_NOT_FOUND"):
            verify_shared_libraries([candidate],runner=lambda *a,**k:result)
    def test_ldd_zero_with_complete_closure_passes(self):
        candidate=self.root/"cv2.abi3.so"; candidate.write_bytes(b"fake ELF placeholder")
        result=subprocess.CompletedProcess(["ldd",str(candidate)],0,"libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1)\\n","")
        self.assertEqual(verify_shared_libraries([candidate],runner=lambda *a,**k:result),{candidate.name})
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
    def test_candidate_manifest_never_claims_signature_from_release_filename(self):
        root=self.root/"candidate"; (root/"ocr-deb-cache"/"apt-lists").mkdir(parents=True)
        release=root/"ocr-deb-cache"/"apt-lists"/"debian_dists_bookworm_InRelease"
        release.write_bytes(b"not verified signed metadata")
        out=root/"ocr-candidate-inputs"/"candidate-input-manifest.json"
        script=Path(__file__).with_name("write_candidate_input_manifest.py")
        env=dict(os.environ,RUNNER_TEMP=str(root),GITHUB_SHA="a"*40,GITHUB_RUN_ID="123")
        subprocess.run([sys.executable,str(script),str(root),str(out)],env=env,check=True,capture_output=True,text=True)
        manifest=json.loads(out.read_text(encoding="utf-8"))
        entry=next(x for x in manifest["files"] if x["path"].endswith("debian_dists_bookworm_InRelease"))
        self.assertIn("signature-verification-not-independently-proven",entry["provenance"])
        self.assertNotIn("signature-checked",entry["provenance"])

    def test_deb_lock_generator_excludes_apt_lock_partial_and_auxfiles(self):
        root=self.root/"apt-filter"; root.mkdir()
        apt=root/"apt-lists"; (apt/"partial").mkdir(parents=True); (apt/"auxfiles").mkdir()
        (apt/"InRelease").write_bytes(b"index")
        (apt/"lock").write_bytes(b"runtime lock")
        (apt/"partial"/"download.part").write_bytes(b"partial")
        (apt/"auxfiles"/"aux").write_bytes(b"aux")
        pkgroot=self.root/"filter-package"; (pkgroot/"DEBIAN").mkdir(parents=True)
        (pkgroot/"DEBIAN"/"control").write_text(chr(10).join(["Package: libxcb1","Version: 1.0","Architecture: amd64","Maintainer: Test <test@example.invalid>","Description: synthetic",""]))
        deb=root/"libxcb1.deb"
        subprocess.run(["dpkg-deb","--build",str(pkgroot),str(deb)],check=True,capture_output=True,text=True)
        source=self.root/"debian.sources"
        source.write_text(chr(10).join(["Types: deb","URIs: https://deb.debian.org/debian","Suites: bookworm","Components: main",""]))
        script=Path(__file__).with_name("generate_deb_runtime_lock.py")
        subprocess.run([sys.executable,str(script),str(root),str(source),str(apt)],check=True,capture_output=True,text=True)
        lock=json.loads((root/"system-deb-lock.json").read_text())
        names={x["path"] for x in lock["apt_lists"]}
        self.assertEqual(names,{"InRelease"})
        self.assertFalse((apt/"lock").stat().st_mode & 0o111)
    def test_candidate_export_copies_only_whitelisted_readable_inputs(self):
        root=self.root/"candidate-root"
        (root/"ocr-deb-cache"/"apt-lists"/"partial").mkdir(parents=True)
        index_path=root/"ocr-deb-cache"/"apt-lists"/"Packages"; index_path.write_bytes(b"index")
        (root/"ocr-deb-cache"/"apt-lists"/"lock").write_bytes(b"lock")
        (root/"ocr-deb-cache"/"partial.deb.tmp").write_bytes(b"partial")
        deb_path=root/"ocr-deb-cache"/"libxcb1.deb"; deb_path.write_bytes(b"deb")
        lock_data={"packages":[{"filename":"libxcb1.deb","sha256":hashlib.sha256(deb_path.read_bytes()).hexdigest()}],
                   "apt_lists":[{"path":"Packages","bytes":index_path.stat().st_size,"sha256":hashlib.sha256(index_path.read_bytes()).hexdigest()}]}
        (root/"ocr-deb-cache"/"system-deb-lock.json").write_text(json.dumps(lock_data))
        os.chmod(root/"ocr-deb-cache"/"apt-lists"/"lock",0o000)
        dest=root/"ocr-candidate-inputs"/"payload"
        manifest=root/"ocr-candidate-inputs"/"candidate-input-manifest.json"
        script=Path(__file__).with_name("write_candidate_input_manifest.py")
        env=dict(os.environ,RUNNER_TEMP=str(root),GITHUB_SHA="a"*40,GITHUB_RUN_ID="123")
        subprocess.run([sys.executable,str(script),str(root),str(dest)],env=env,check=True,capture_output=True,text=True)
        data=json.loads(manifest.read_text())
        paths={x["path"] for x in data["files"]}
        self.assertIn("system-debs/libxcb1.deb",paths)
        self.assertIn("apt-lists/Packages",paths)
        self.assertNotIn("apt-lists/lock",paths)
        self.assertNotIn("partial.deb.tmp",json.dumps(data))
        self.assertEqual(data["classification"],"CANDIDATE_INPUTS_ONLY_NOT_A_RELEASE_PACKAGE")
        self.assertTrue((dest/"system-debs/libxcb1.deb").is_file())
        self.assertTrue((dest/"apt-lists/Packages").is_file())
    def test_failed_candidate_upload_uses_only_controlled_payload_not_raw_cache(self):
        workflow=Path(__file__).resolve().parents[2]/".github"/"workflows"/"ocr-engine-tests.yml"
        text=workflow.read_text(encoding="utf-8")
        start=text.index("Upload reusable candidate inputs and their digest manifest")
        end=text.index("Upload failure diagnostics",start)
        block=text[start:end]
        self.assertIn("ocr-candidate-inputs/payload/**",block)
        self.assertIn("candidate-input-manifest.json",block)
        self.assertNotIn("ocr-deb-cache/**",block)
        self.assertNotIn("ocr-wheelhouse/**",block)
        self.assertIn("if: always()",block)

    def test_offline_deb_installer_stops_on_unpack_failure_without_configure(self):
        root=self.root/"offline-debs"; root.mkdir()
        deb=root/"libxcb1_1.0_amd64.deb"; deb.write_bytes(b"synthetic package bytes")
        lock={"packages":[{"filename":deb.name,"package":"libxcb1","version":"1.0","architecture":"amd64","sha256":hashlib.sha256(deb.read_bytes()).hexdigest()}]}
        (root/"system-deb-lock.json").write_text(json.dumps(lock))
        bindir=self.root/"fake-dpkg-bin"; bindir.mkdir()
        log=self.root/"dpkg-calls.jsonl"
        dpkgdeb=bindir/"dpkg-deb"
        dpkgdeb.write_text(chr(10).join(["#!/usr/bin/env python3","import sys","field=sys.argv[-1]","print({'Package':'libxcb1','Version':'1.0','Architecture':'amd64'}[field])",""]))
        dpkgdeb.chmod(0o755)
        dpkg=bindir/"dpkg"
        dpkg.write_text(chr(10).join(["#!/usr/bin/env python3","import json,os,sys","with open(os.environ['DPKG_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+chr(10))","sys.exit(17 if sys.argv[1:2]==['--unpack'] else 0)",""]))
        dpkg.chmod(0o755)
        query=bindir/"dpkg-query"
        query.write_text(chr(10).join(["#!/usr/bin/env python3","import sys","print('libxcb1=1.0')",""]))
        query.chmod(0o755)
        env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ.get("PATH",""),DPKG_LOG=str(log))
        script=Path(__file__).with_name("install_deb_closure.py")
        result=subprocess.run([sys.executable,str(script),str(root)],env=env,text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(calls,[["--unpack",str(deb)]])
        self.assertNotIn(["--configure","-a"],calls)
    def test_offline_deb_installer_rejects_tampered_package_before_dpkg(self):
        root=self.root/"offline-debs-tampered"; root.mkdir()
        deb=root/"libxcb1.deb"; deb.write_bytes(b"tampered")
        lock={"packages":[{"filename":deb.name,"package":"libxcb1","version":"1.0","architecture":"amd64","sha256":"0"*64}]}
        (root/"system-deb-lock.json").write_text(json.dumps(lock))
        script=Path(__file__).with_name("install_deb_closure.py")
        result=subprocess.run([sys.executable,str(script),str(root)],text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("DEB_LOCK_SHA_MISMATCH",result.stderr+result.stdout)

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
