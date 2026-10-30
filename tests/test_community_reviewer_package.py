"""The actual source packager must retain the complete reviewer composition."""
import hashlib,io,json,unittest,zipfile
from pathlib import Path
from scripts.community_stage_package import build
from scripts import community_reviewer_maintenance
class Package(unittest.TestCase):
    def test_complete_new_source_binding(self):
        root=Path(__file__).resolve().parents[1]
        payload,sha=build(root)
        self.assertEqual(hashlib.sha256(payload).hexdigest(),sha)
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            manifest=json.loads(z.read('MANIFEST.json'))
            paths=['scripts/community_platform_reviewer_admission.py','scripts/community_reviewer_maintenance.py',
                'scripts/community_reviewer_web_bridge.py','scripts/community_mini_http.py',
                'deploy/community-preview/Dockerfile','deploy/community-preview/nginx-uk-path-candidate.conf',
                'demos/community-stage/web-session.js','clients/community-mini/session.js',
                'clients/community-mini/pages/profile/index.js','clients/community-mini/pages/profile/index.wxml']
            for name in paths:
                self.assertEqual(z.read(name),(root/name).read_bytes())
                self.assertEqual(manifest['files'][name],hashlib.sha256(z.read(name)).hexdigest())
        self.assertIsNone(community_reviewer_maintenance.OWNER_CONFIRMATION_PIN)
        self.assertEqual(hashlib.sha256((root/'scripts/pr122_customer_core.py').read_bytes()).hexdigest(),
            'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0')
