#!/usr/bin/env python3
"""Copy only public test inputs into a new protected local namespace.

Do not relax production ancestry/ACL/ownership checks for hosted workspaces.
No network, credentials, live host or admission is used by this runner.
"""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

def main():
    candidate=pathlib.Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='p2-r14-offline-',dir='/') as name:
        root=pathlib.Path(name);copied=root/'candidate'
        shutil.copytree(str(candidate),str(copied),ignore=shutil.ignore_patterns('baseline','__pycache__','*.pyc'))
        spec=importlib.util.spec_from_file_location('verified_fixture_builder',str(copied/'build/build_claim_successor_kit.py'))
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        archive=candidate.parent/'b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz'
        files,manifest=builder.authenticate_archive(archive.read_bytes())
        for relative,raw in files.items():
            path=copied/'baseline'/relative;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with open(str(path),'xb') as stream:stream.write(raw)
            path.chmod(0o444)
        # Extraction above authenticates all baseline names/bytes before fixture imports.
        target=copied/'delivery/test_r14_delivery.py'
        result=subprocess.run([sys.executable,'-I','-B','-S',str(target),'-v'],timeout=240)
        return result.returncode

if __name__=='__main__':sys.exit(main())
