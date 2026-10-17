"""Isolated current-stage integration; collector payload is a declared test fixture."""
import contextlib,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_site_hub_stage as stage
from scripts import pr122_community_experience_package as mobile

def digest(b):return hashlib.sha256(b).hexdigest()
class StageNavigationTests(unittest.TestCase):
    def setup_fixture(self,folder):
        root=folder/'source';fixture=folder/'shell';fixture.mkdir();root.mkdir()
        shell='<html lang="zh-CN"><head><title>Fixture</title></head><body><header>Header</header><main>Home</main><footer>Footer</footer></body></html>'
        pins={}
        for locale in ('','zh-cn/','en/'):
            p=fixture/(locale+'index.html');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(shell.replace('zh-CN','en') if locale=='en/' else shell);pins[locale+'index.html']=digest(p.read_bytes())
        (fixture/'PINS.json').write_text(json.dumps(pins))
        paths=['/visual/community-local-e2e/index.html','/visual/community-payment/merchant-dashboard/']+['/visual/community-local-e2e/'+r+'.html' for r in ('platform','community','beneficiary')]
        entry='<html lang="zh-CN"><head></head><body><header></header><main><p>LATEST-COPY-MUST-SURVIVE</p>'+''.join('<a href="'+p+'">Role</a>' for p in paths)+'<p>SAAS-NOT-CONNECTED</p><a href="/visual/community-local-e2e/saas-panel.html">SaaS guidance</a></main><footer></footer></body></html>'
        p=root/'demos/xuanjun-site-hub/visual/community-payment/index.html';p.parent.mkdir(parents=True);p.write_text(entry)
        assets=root/'demos/xuanjun-site-hub/assets';assets.mkdir()
        for n in ('ecv-quote.js','ecv-quote-ui.js','community-preview-session.js'):(assets/n).write_text('//fixture')
        p=root/'demos/community-local-e2e/app.js';p.parent.mkdir(parents=True);p.write_text('//dependency')
        files={mobile.TARGET+n:(b'<html><body>mobile<script>const reviewedFixture=1;</script></body></html>' if n.endswith('.html') else b'/*fixture*/') for n in ('index.html','merchant.html','community.html','beneficiary.html','platform.html','experience.css','experience.js','role.css','role.js')}
        provenance={'files':[{'path':n,'size':len(b),'sha256':digest(b)} for n,b in files.items()],'dependencies':[{'path':'visual/community-local-e2e/app.js','sha256':digest(b'//dependency')}],'state':'TEST_FIXTURE_ONLY'}
        return root,fixture,files,provenance
    def test_current_copy_final_csp_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);root,fixture,files,provenance=self.setup_fixture(folder);output=folder/'stage'
            with patch.object(mobile,'collect_mobile_files',return_value=(files,provenance)),patch.object(stage,'menu_patch',side_effect=lambda x:x),patch.object(stage,'improve_home',side_effect=lambda x,locale:x),contextlib.redirect_stdout(io.StringIO()):
                stage.build(root,None,output,fixture,derive_navigation=True)
            manifest=json.loads((output/'MANIFEST.json').read_text());public=output/'public'
            self.assertFalse(manifest['production_approved']);self.assertEqual('HOSTED_BROWSER_FIXTURE_ONLY',manifest['status'])
            self.assertEqual({p.relative_to(public).as_posix():digest(p.read_bytes()) for p in public.rglob('*') if p.is_file()},manifest['files'])
            self.assertEqual(len(list(public.rglob('*.html'))),manifest['csp']['html_count'])
            self.assertEqual(1,manifest['csp']['script_hash_count'])
            for locale in ('','zh-cn/','en/'):
                s=(public/(locale+'visual/community-payment/index.html')).read_text()
                self.assertIn('LATEST-COPY-MUST-SURVIVE',s);self.assertIn('SAAS-NOT-CONNECTED',s)
                self.assertIn('/visual/community-local-e2e/saas-panel.html',s)
                if locale:self.assertEqual(5,s.count('?lang='+locale.rstrip('/')))
    def test_hash_collision_and_path_fail_before_writes(self):
        for failure in ('hash','collision','path'):
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);root,fixture,files,provenance=self.setup_fixture(folder);public=folder/'public';public.mkdir()
                p=public/'visual/community-local-e2e/app.js';p.parent.mkdir(parents=True);p.write_bytes(b'wrong' if failure=='hash' else b'//dependency')
                if failure=='collision':p=public/(mobile.TARGET+'role.js');p.parent.mkdir(parents=True);p.write_bytes(b'existing')
                if failure=='path':files['../escape']=b'unsafe'
                before={str(p):p.read_bytes() for p in public.rglob('*') if p.is_file()}
                with patch.object(mobile,'collect_mobile_files',return_value=(files,provenance)),self.assertRaises(ValueError):stage.integrate_mobile_navigation(root,public)
                self.assertEqual(before,{str(p):p.read_bytes() for p in public.rglob('*') if p.is_file()})
if __name__=='__main__':unittest.main()
