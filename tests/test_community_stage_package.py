import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path
from scripts.community_stage_package import build

class SourcePackage(unittest.TestCase):
    def test_deterministic_complete_package_matches_original_bytes(self):
        root=Path(__file__).resolve().parents[1]
        data,digest=build(root)
        self.assertEqual((data,digest),build(root))
        self.assertEqual(digest,hashlib.sha256(data).hexdigest())
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest=json.loads(archive.read('MANIFEST.json'))
            self.assertEqual(set(archive.namelist()),set(manifest['files'])|{'MANIFEST.json'})
            for name,expected in manifest['files'].items():
                raw=archive.read(name)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),expected)
                self.assertEqual(raw,(root/name).read_bytes())
            self.assertEqual(manifest['production_payment'],'HOLD')
            for name in ('tests/test_community_portal_pagination.mjs',
                         'tests/community_project_review_dom.cjs',
                         'scripts/community_project_materials.py',
                         'demos/community-stage/project-review.js'):
                self.assertIn(name, manifest['files'])
            self.assertFalse(any(name.endswith(('.pem','.sqlite','.env')) for name in archive.namelist()))

if __name__=='__main__':unittest.main()
