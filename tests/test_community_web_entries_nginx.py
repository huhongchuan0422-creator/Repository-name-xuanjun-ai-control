import re,shutil,subprocess,tempfile,unittest
from pathlib import Path

class RoleProxy(unittest.TestCase):
    def test_real_nginx_syntax_and_exact_browser_route_boundary(self):
        fragment=Path(__file__).resolve().parents[1]/'deploy/community-preview/nginx-uk-path-candidate.conf'
        raw=fragment.read_text();pattern=re.search(r'location ~ (.+) \{',raw).group(1)
        for path in ['/merchant/join','/merchant/review','/merchant/workbench','/merchant/workbench.js',
                     '/merchant/workbench.css','/merchant/onboarding','/merchant/onboarding.js',
                     '/merchant/onboarding.css','/community/portal','/community/portal.js','/community/portal.css',
                     '/community/entrypoints','/community/operations','/community/directory','/community/commerce',
                     '/community/provider-actions','/community/merchant-bills','/community/session/login',
                     '/community/session/check','/community/session/logout','/community/web-session.js']:
            self.assertIsNotNone(re.fullmatch(pattern,'/community-preview'+path))
        for path in ['/owner/','/owner-callback','/owner/api/state','/community-preview/merchant/private',
                     '/community-preview/community/unknown','/community-preview/merchant/workbench/extra','/merchant/review']:
            self.assertIsNone(re.fullmatch(pattern,path))
        nginx=shutil.which('nginx') or '/usr/sbin/nginx'
        self.assertTrue(Path(nginx).is_file(),'CI must install real nginx, no skipped syntax verification')
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'nginx.conf'
            config.write_text('pid '+tmp+'/pid; error_log stderr; events {} http { access_log off; '
                              'client_body_temp_path '+tmp+'/body; proxy_temp_path '+tmp+'/proxy; '
                              'server { listen 127.0.0.1:18888; include '+str(fragment)+'; } }')
            r=subprocess.run([nginx,'-t','-p',tmp+'/', '-c',str(config)],capture_output=True,text=True,timeout=8)
            self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
