"""Real nginx parser, isolated temporary config; never start a service."""
import re,shutil,subprocess,tempfile,unittest
from pathlib import Path
class IsolatedUIRoute(unittest.TestCase):
    def test_real_nginx_exact_static_allowlist(self):
        root=Path(__file__).resolve().parents[1]
        fragment=root/'deploy/community-preview/nginx-ui-preview-candidate.inc'
        raw=fragment.read_text();pattern=re.search(r'location ~ (.+) \{',raw).group(1)
        for name in ('','index.html','route-gallery.html','preview.js','sources.js','preview.css','original.css'):
            self.assertIsNotNone(re.fullmatch(pattern,'/community-preview/community/ui-preview/'+name))
        for path in ('/owner/','/community-preview/mini/login','/community-preview/community/session/login','/community-preview/community/ui-preview/private.json','/community-preview/community/ui-preview/../index.html'):
            self.assertIsNone(re.fullmatch(pattern,path))
        nginx=shutil.which('nginx') or '/usr/sbin/nginx'
        self.assertTrue(Path(nginx).is_file(),'CI must install actual nginx; no skipped route validation')
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'nginx.conf'
            config.write_text('pid '+tmp+'/pid; error_log stderr; events {} http { access_log off; client_body_temp_path '+tmp+'/body; proxy_temp_path '+tmp+'/proxy; server { listen 127.0.0.1:18888; include '+str(fragment)+'; } }')
            result=subprocess.run([nginx,'-t','-p',tmp+'/', '-c',str(config)],capture_output=True,text=True,timeout=8)
            self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
