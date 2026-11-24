import hashlib,importlib.util,json,os,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('tc477_build',Path(__file__).resolve().parents[1]/'tools/build_tc477_runtime_overlay.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
class OverlayBuild(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source';self.source.mkdir();self.base=self.root/'base';self.base.mkdir()
        for root in (self.source,self.base):(root/'scripts').mkdir()
        (self.source/'scripts/same.py').write_text('same');(self.base/'scripts/same.py').write_text('same')
        (self.source/'scripts/change.py').write_text('result');(self.base/'scripts/change.py').write_text('before')
        (self.source/'scripts/add.py').write_text('new')
        (self.source/'docs/backup').mkdir(parents=True)
        (self.source/'docs/backup/tc477-dependency-lock-20261124.json').write_text('{"files":[]}')
        self.entries=[dict(path='scripts/'+name,type='file',mode='0644',sha256=build.digest((self.base/'scripts'/name).read_bytes())) for name in ('same.py','change.py')]
        raw=json.dumps(dict(entries=self.entries)).encode();(self.base/'INSTALL_MANIFEST.json').write_bytes(raw)
        self.sha=build.digest(raw);self.cwd=os.getcwd();os.chdir(str(self.source));self.addCleanup(os.chdir,self.cwd)
        def git(*args):
            if args==('status','--porcelain'):return ''
            if args==('ls-files','scripts'):return 'scripts/add.py\nscripts/change.py\nscripts/same.py'
            return 'a'*40 if args[-1]=='HEAD' else 'b'*40
        p=patch.object(build,'git',side_effect=git);p.start();self.addCleanup(p.stop)
        p=patch.object(build,'BASE_MANIFEST',self.sha);p.start();self.addCleanup(p.stop)
    def test_exact_delta_tar_bytes_before_binding_and_no_overwrite(self):
        out=self.root/'artifact';r=build.build(self.base,out)
        manifest=json.loads((out/'RESULT-FILES.json').read_text())
        self.assertEqual([f['path'] for f in manifest['files']],['docs/backup/tc477-dependency-lock-20261124.json','scripts/add.py','scripts/change.py'])
        self.assertEqual(manifest['delete_files'],[]);self.assertTrue(manifest['preserve_all_unlisted_installed_paths'])
        with tarfile.open(str(out/'tc477-runtime-overlay.tar.gz')) as t:
            self.assertEqual(t.extractfile('payload/scripts/change.py').read(),b'result')
            self.assertNotIn('payload/scripts/same.py',t.getnames())
        self.assertEqual(r['ARTIFACT_HASH'],build.digest((out/'tc477-runtime-overlay.tar.gz').read_bytes()))
        before=(out/'tc477-runtime-overlay.tar.gz').read_bytes()
        with self.assertRaisesRegex(ValueError,'BUILD_OUTPUT_EXISTS_DO_NOT_OVERWRITE'):build.build(self.base,out)
        self.assertEqual((out/'tc477-runtime-overlay.tar.gz').read_bytes(),before)
        self.assertEqual((self.base/'scripts/change.py').read_text(),'before')
    def test_changed_before_and_add_collision_fail_without_artifact(self):
        (self.base/'scripts/change.py').write_text('drift');out=self.root/'artifact'
        with self.assertRaisesRegex(ValueError,'INSTALLED_BEFORE_BYTES_CHANGED'):build.build(self.base,out)
        self.assertFalse(out.exists())
        (self.base/'scripts/change.py').write_text('before');(self.base/'scripts/add.py').write_text('occupied')
        with self.assertRaisesRegex(ValueError,'ADD_PATH_ALREADY_EXISTS'):build.build(self.base,out)
        self.assertFalse(out.exists())
    def test_wrong_manifest_and_release_output_rejected(self):
        (self.base/'INSTALL_MANIFEST.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'INSTALLED_BASE_MANIFEST_CHANGED'):build.build(self.base,self.root/'artifact')
        with self.assertRaisesRegex(ValueError,'OUTPUT_MUST_NOT_TOUCH_RELEASE'):build.build(self.base,self.base/'out')
