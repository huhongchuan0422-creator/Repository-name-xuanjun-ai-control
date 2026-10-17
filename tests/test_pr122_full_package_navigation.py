"""Isolated package-control tests, never original-source acceptance."""
import ast,gzip,hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
class FullPackageNavigation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        source=ast.parse((ROOT/'scripts/pr122_site_hub_package.py').read_text())
        functions=[n for n in source.body if isinstance(n,ast.FunctionDef)]
        self.ns=dict(Path=Path,tempfile=tempfile,tarfile=tarfile,gzip=gzip,io=io,json=json,hashlib=hashlib)
        exec(compile(ast.Module(body=functions,type_ignores=[]),'<package-functions>','exec'),self.ns)
        self.manifest=json.dumps({'files':[{'path':'index.html','sha256':hashlib.sha256(b'old').hexdigest()}]}).encode()
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            info=tarfile.TarInfo('package/MANIFEST.json');info.size=len(self.manifest);archive.addfile(info,io.BytesIO(self.manifest))
        self.source=self.root/'source.tar.gz';self.source.write_bytes(stream.getvalue())
        self.ns['SOURCE_HASH']=hashlib.sha256(stream.getvalue()).hexdigest()
        real_sha=self.ns['sha']
        self.ns['sha']=lambda b:'d9157976ae67e89aba90a8de0d2c606ec62268c6b649d9ebe578f6c2619e0d6a' if b==self.manifest else real_sha(b)
        self.ns['BASE_SHA256']='test-only-publisher';self.ns['publisher_source']=lambda root:b'fake-publisher'
        self.status='ISOLATED_INTEGRATION_CANDIDATE';self.drift=False;self.binding_overrides={}
        def stage(root,source,out,**kwargs):
            (out/'public').mkdir(parents=True);(out/'public/index.html').write_bytes(b'new')
            binding={'status':self.status,'source_archive_sha256':self.ns['SOURCE_HASH'],'production_approved':False,'files':{'index.html':real_sha(b'wrong' if self.drift else b'new')},'navigation_derivation':{'state':'TEST_ONLY'}}
            binding.update(self.binding_overrides)
            (out/'MANIFEST.json').write_text(json.dumps(binding))
        self.builder=Mock(side_effect=stage);self.ns['build']=self.builder
        for name in ['scripts/pr122_site_hub_package.py','scripts/pr122_site_hub_stage.py','scripts/pr122_community_experience_package.py','scripts/pr122_site_hub_unified_package.py','demos/work-community-experience/role.js','scripts/pr122_site_hub_preview.py']:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'test mechanism')
    def run_package(self,derive=False):return self.ns['package'](self.root,self.source,self.root/'out',derive)
    def test_default_preserves_original_stage_call_and_entries(self):
        self.run_package();self.assertEqual(self.builder.call_args.kwargs,{})
        self.assertFalse((self.root/'out/bundle/BUILD_PROVENANCE.json').exists())
    def test_opt_in_binds_stage_and_all_manifest_bytes(self):
        self.run_package(True);self.assertEqual(self.builder.call_args.kwargs,{'derive_navigation':True})
        bundle=self.root/'out/bundle';manifest=json.loads((bundle/'PACKAGE_MANIFEST.json').read_bytes())
        for item in manifest['files']:
            data=(bundle/item['path']).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256']);self.assertEqual(len(data),item['size'])
        p=json.loads((bundle/'BUILD_PROVENANCE.json').read_bytes());self.assertFalse(p['production_approved']);self.assertEqual(p['stage_manifest_sha256'],hashlib.sha256((bundle/'FULL_SOURCE_STAGE_MANIFEST.json').read_bytes()).hexdigest())
        self.assertFalse(json.loads((bundle/'RELEASE_GATE.json').read_bytes())['production_approved'])
    def test_unpinned_input_rejected_before_stage(self):
        self.source.write_bytes(b'synthetic');
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):self.run_package(True)
        self.builder.assert_not_called()
    def test_synthetic_stage_rejected(self):
        self.status='HOSTED_BROWSER_FIXTURE_ONLY'
        with self.assertRaisesRegex(ValueError,'FULL_SOURCE_STAGE_REQUIRED'):self.run_package(True)
        self.assertFalse((self.root/'out').exists())
    def test_source_binding_mismatch_rejected(self):
        self.binding_overrides={'source_archive_sha256':'wrong'}
        with self.assertRaisesRegex(ValueError,'FULL_SOURCE_STAGE_REQUIRED'):self.run_package(True)
        self.assertFalse((self.root/'out').exists())
    def test_production_approval_rejected(self):
        self.binding_overrides={'production_approved':True}
        with self.assertRaisesRegex(ValueError,'FULL_SOURCE_STAGE_REQUIRED'):self.run_package(True)
        self.assertFalse((self.root/'out').exists())
    def test_missing_navigation_provenance_rejected(self):
        self.binding_overrides={'navigation_derivation':{}}
        with self.assertRaisesRegex(ValueError,'NAVIGATION_PROVENANCE_REQUIRED'):self.run_package(True)
        self.assertFalse((self.root/'out').exists())
    def test_manifest_drift_rejected(self):
        self.drift=True
        with self.assertRaisesRegex(ValueError,'FINAL_STAGE_MANIFEST_MISMATCH'):self.run_package(True)
        self.assertFalse((self.root/'out').exists())
if __name__=='__main__':unittest.main()
