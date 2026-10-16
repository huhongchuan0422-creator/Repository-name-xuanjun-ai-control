import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts.pr122_site_hub_release_delta import publisher_source
from tests import test_pr122_website_release as legacy

class AdditionTests(unittest.TestCase):
    def setUp(self):
        self.f=legacy.ReleaseTest('runTest');self.f.setUp();self.addCleanup(self.f.tearDown)
        self.code=self.f.root/'candidate_release.py';self.code.write_bytes(publisher_source())
        spec=importlib.util.spec_from_file_location('hub_release',self.code)
        self.release=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.release)
        self.target=self.f.bundle/'overlay/public/marketplace/index.html';self.target.parent.mkdir(parents=True)
        self.target.write_text('<!doctype html><html><body>new page</body></html>')
        self.f.pin['overlay_baselines']['marketplace/index.html']=None
        self.f.manifest['files'].append({'path':'marketplace/index.html','size':self.target.stat().st_size,'sha256':self.release.digest(self.target)})
        self.f.write_bundle()
    def test_actual_new_publisher_cli_prepares_activates_checks_and_restores_old(self):
        old=self.f.existing_old()
        for command in ('prepare','activate','check','rollback'):
            args=[sys.executable,str(self.code),command,'--webroot-base',str(self.f.base),'--transaction-id','tx-1','--release-id','release-1','--allow-non-root-test']
            if command in ('prepare','activate','check'):
                args+=['--bundle',str(self.f.bundle),'--approved-package-manifest-sha256',self.f.package_hash]
            if command=='prepare':args+=['--source-archive',str(self.f.source)]
            result=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            if command=='prepare':
                page=self.f.base/'releases/release-1/public/marketplace/index.html'
                self.assertEqual(page.read_bytes(),self.target.read_bytes());self.assertEqual(page.stat().st_mode&0o777,0o644)
        self.assertEqual((self.f.base/'current').resolve(),old)
        self.assertEqual((old/'public/index.html').read_text(),'old')
    def test_claiming_existing_file_as_addition_is_rejected(self):
        self.f.pin['overlay_baselines']['assets/tiktok-integration.js']=None;self.f.write_bundle()
        with self.assertRaisesRegex(self.release.Hold,'OVERLAY_ADDITION_COLLISION'):
            self.release.prepare(self.f.args())
        self.assertFalse((self.f.base/'current').exists())
    def test_added_content_hash_mismatch_never_activates(self):
        self.target.write_text('tampered')
        with self.assertRaisesRegex(self.release.Hold,'RELEASE_CONTENT_MISMATCH'):
            self.release.prepare(self.f.args())
        self.assertFalse((self.f.base/'current').exists())
    def test_missing_added_overlay_and_writable_added_parent_rejected(self):
        os.chmod(self.target.parent,0o777)
        with self.assertRaises(self.release.Hold):self.release.prepare(self.f.args())
    def test_original_publisher_does_not_silently_accept_new_schema(self):
        with self.assertRaisesRegex(__import__('tests.test_pr122_website_release',fromlist=['release']).release.Hold,'OVERLAY_BASELINE_DRIFT'):
            __import__('tests.test_pr122_website_release',fromlist=['release']).release.prepare(self.f.args())

if __name__=='__main__':unittest.main()
