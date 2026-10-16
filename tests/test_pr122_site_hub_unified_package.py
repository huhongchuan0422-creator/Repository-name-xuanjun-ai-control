import io,json,os,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_community_experience_package as mobile
from scripts import pr122_site_hub_unified_package as u

class UnifiedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t=tempfile.TemporaryDirectory();cls.folder=Path(cls.t.name)
        with patch.dict(os.environ,{'GITHUB_SHA':'790937a5c96afcf3b3660e36cf36cfaab2002a72'}):mobile.build(cls.folder/'mobile')
        cls.static=(u.ROOT/'evidence/pr122-public-presentation/PR122_PUBLIC_PRESENTATION_REVIEW_ONLY.tar.gz').read_bytes()
        cls.phone=(cls.folder/'mobile/COMMUNITY_EXPERIENCE_REVIEW_ONLY.tar.gz').read_bytes()
        cls.files=u.compose(cls.static,cls.phone)
    @classmethod
    def tearDownClass(cls):cls.t.cleanup()
    def test_reviewed_mobile_reproduces_exact_bytes(self):self.assertEqual(u.sha(self.phone),u.MOBILE_SHA)
    def test_all_manifest_files_bind(self):
        u.verify(self.files,json.loads(self.files['PACKAGE_MANIFEST.json'])['files'],['PACKAGE_MANIFEST.json'])
        self.assertEqual(len(self.files),459)
        self.assertEqual(len(json.loads(self.files['candidate-manifest.json'])['files']),1288)
    def test_phone_bytes_preserved_not_redeveloped(self):
        phone=u.unpack(self.phone,u.MOBILE_SHA,'pr122-community-experience/',10)
        for p,b in phone.items():
            if p!='MANIFEST.json':self.assertEqual(self.files['overlay/public/'+p],b)
    def test_entry_roles_point_to_one_mobile_version(self):
        for locale in ('','zh-cn/','en/'):
            page=self.files['overlay/public/'+locale+'visual/community-payment/index.html'].decode()
            for role in ('merchant','community','beneficiary','platform'):
                self.assertIn('href="/'+u.TARGET+role+'.html"',page)
            self.assertIn('href="/'+u.TARGET+'"',page)
            self.assertIn('/visual/community-local-e2e/saas-panel.html',page)
    def test_original_runtime_and_publisher_unchanged(self):
        old=u.unpack(self.static,u.STATIC_SHA,'pr122-site-hub/',449)
        for p,b in old.items():
            if p.startswith(('runtime/','runtime-config/')) or p=='bin/pr122_website_release.py':self.assertEqual(self.files[p],b)
    def test_corruption_and_nonregular_members_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'INPUT_HASH'):u.compose(self.static+b'x',self.phone)
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as a:
            m=tarfile.TarInfo('test/link');m.type=tarfile.SYMTYPE;m.linkname='/etc/passwd';a.addfile(m)
        with self.assertRaisesRegex(ValueError,'PATH_OR_TYPE'):u.unpack(buf.getvalue(),u.sha(buf.getvalue()),'test/',1)
    def test_archive_deterministic_and_gate_closed(self):
        self.assertEqual(u.archive(self.files),u.archive(self.files))
        p=json.loads(self.files['COMPOSITION_MANIFEST.json']);self.assertFalse(p['production_approved']);self.assertFalse(p['customer_data_open'])
    def test_original_paths_and_new_collision_baselines(self):
        p=json.loads(self.files['source-pin.json']);self.assertEqual(sum(v is None for v in p['overlay_baselines'].values()),101)
        self.assertEqual(sum(k.startswith('overlay/public/') for k in self.files),416)
        self.assertIn('overlay/public/visual/community-local-e2e/index.html',self.files)
