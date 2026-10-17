import io,json,tarfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_site_hub_unified_package as package
from scripts.pr122_community_experience_package import prepare_mobile_page, BASELINE_ROLE_JS
ROOT=Path(__file__).resolve().parents[1]
T=package.TARGET

def tar(files,prefix):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as a:
        for name,b in files.items():
            m=tarfile.TarInfo(prefix+name);m.size=len(b);a.addfile(m,io.BytesIO(b))
    return out.getvalue()
def rows(files):return [{'path':p,'size':len(b),'sha256':package.sha(b)} for p,b in files.items()]

class NavigationTests(unittest.TestCase):
    def test_derived_stage_rejected_before_any_io(self):
        with self.assertRaisesRegex(ValueError,'CANNOT_OVERWRITE_CURRENT_STAGE'):
            package.build(Path('missing-static'),Path('missing-mobile'),Path('must-not-create'),Path('current-stage'),True)
    def test_current_entry_preserves_copy_and_nonrole_links(self):
        paths=['/visual/community-local-e2e/index.html','/visual/community-payment/merchant-dashboard/']+['/visual/community-local-e2e/'+r+'.html' for r in ('platform','community','beneficiary')]
        prefix='<main><p>Latest reviewed wording; SaaS is unavailable.</p>'
        suffix='<a href="/visual/community-local-e2e/saas-panel.html">SaaS guidance</a><script>const url="/visual/community-local-e2e/index.html";</script></main>'
        source=prefix+''.join('<a class="role" href="'+p+'"><h2>Approved role</h2></a>' for p in paths)+suffix
        result=package.derive_entry_navigation(source,'en/')
        self.assertTrue(result.startswith(prefix));self.assertTrue(result.endswith(suffix))
        self.assertEqual(5,result.count('?lang=en'))
        self.assertEqual(result,package.derive_entry_navigation(result,'en/'))
        # The only differences are five href attribute values.
        import re
        scrub=lambda x:re.sub(r'(<a class="role" href=")[^"]+',r'\1HREF',x)
        self.assertEqual(scrub(source),scrub(result))
        with self.assertRaisesRegex(ValueError,'NAVIGATION_LOCALE'):package.derive_entry_navigation(source,'https://evil.test/')
        with self.assertRaisesRegex(ValueError,'ROLE_LINK_DRIFT'):package.derive_entry_navigation(prefix+suffix,'en/')
    def test_exact_anchor_only_rewrite(self):
        old='/visual/community-local-e2e/community.html'
        source='<a href="'+old+'">role</a><iframe src="'+old+'"></iframe><script>const x=\'<a href="'+old+'">x</a>\';</script><a href="'+old+'?return=https://evil.test">keep</a>'
        result=prepare_mobile_page(source,'community.html')
        self.assertIn('<a href="/'+T+'community.html">role',result)
        self.assertIn('<iframe src="'+old+'">',result)
        self.assertIn('<script>const x=\'<a href="'+old+'">',result)
        self.assertIn(old+'?return=https://evil.test',result)
        self.assertEqual(result,prepare_mobile_page(result,'community.html'))
    def test_baseline_role_bytes_are_explicit(self):
        self.assertEqual("2d47cafdca509fa247ff8b21931af6bf3a69dfbd8ecfd2b61ddec1bf4d2849fa",package.sha(BASELINE_ROLE_JS))
    def test_role_scope_and_consumer_script(self):
        with self.assertRaises(ValueError):prepare_mobile_page('<body></body>','website-admin.html')
        result=prepare_mobile_page('<body></body>','index.html')
        self.assertEqual(1,result.count('src="./role.js"'))
        self.assertEqual(result,prepare_mobile_page(result,'index.html'))
    def fixtures(self):
        entries=[l+'visual/community-payment/index.html' for l in ('','zh-cn/','en/')]
        old=['/visual/community-local-e2e/index.html','/visual/community-payment/merchant-dashboard/']+['/visual/community-local-e2e/'+r+'.html' for r in ('platform','community','beneficiary')]
        html=''.join('<a href="'+p+'">role</a>' for p in old).encode()
        files={'overlay/public/'+n:html for n in entries}
        known=[{'path':n,'size':len(html),'sha256':package.sha(html)} for n in entries]
        known += [{'path':'existing/'+str(i),'size':0,'sha256':package.sha(b'')} for i in range(1276)]
        files['candidate-manifest.json']=package.canonical({'files':known})
        files['source-pin.json']=package.canonical({'overlay_baselines':{}})
        for i in range(443):files['untouched/'+str(i)]=b'unchanged source and CSP'
        files['PACKAGE_MANIFEST.json']=package.canonical({'files':rows(files)})
        self.assertEqual(449,len(files))
        phones={T+n:b'<body><a href="/visual/community-local-e2e/platform.html">platform</a></body>' for n in ['index.html','merchant.html','community.html','beneficiary.html','platform.html']}
        phones.update({T+n:b'original resource' for n in ['experience.css','experience.js','role.css','role.js']})
        phones['MANIFEST.json']=package.canonical({'files':rows(phones),'source_commit':'790937a5c96afcf3b3660e36cf36cfaab2002a72','real_payment':False,'private_feedback_open':False,'dependencies':[]})
        return files,phones,tar(files,'pr122-site-hub/'),tar(phones,'pr122-community-experience/')
    def test_compose_derivation_and_non_targets(self):
        original,phones,static,mobile=self.fixtures()
        with patch.object(package,'STATIC_SHA',package.sha(static)),patch.object(package,'MOBILE_SHA',package.sha(mobile)):
            result=package.compose(static,mobile,derive_navigation=True)
            legacy=package.compose(static,mobile)
            self.assertNotIn("navigation_derivation",json.loads(legacy["COMPOSITION_MANIFEST.json"]))
            for name,b in phones.items():
                if name!="MANIFEST.json":self.assertEqual(b,legacy["overlay/public/"+name])
            with self.assertRaisesRegex(ValueError,'INPUT_HASH'):package.compose(static+b'x',mobile)
        changed={'PACKAGE_MANIFEST.json','candidate-manifest.json','source-pin.json'}|{'overlay/public/'+l+'visual/community-payment/index.html' for l in ('','zh-cn/','en/')}
        for name,b in original.items():
            if name not in changed:self.assertEqual(b,result[name],name)
        for name,b in phones.items():
            if name.endswith(('experience.css','experience.js','role.css')):self.assertEqual(b,result['overlay/public/'+name])
        for locale in ('en','zh-cn'):
            entry=result['overlay/public/'+locale+'/visual/community-payment/index.html'].decode()
            self.assertEqual(5,entry.count('?lang='+locale))
        provenance=json.loads(result['COMPOSITION_MANIFEST.json'])
        self.assertEqual('NEW_CANDIDATE_PENDING_REVIEW',provenance['navigation_derivation']['state'])
        self.assertFalse(provenance['production_approved'])
        package.verify(result,json.loads(result['PACKAGE_MANIFEST.json'])['files'],['PACKAGE_MANIFEST.json'])
        known={r['path']:r for r in json.loads(result['candidate-manifest.json'])['files']}
        for name,b in result.items():
            if name.startswith('overlay/public/'):
                self.assertEqual(package.sha(b),known[name.removeprefix('overlay/public/')]['sha256'])

if __name__=='__main__':unittest.main()
