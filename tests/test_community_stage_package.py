import hashlib
import io
import json
import subprocess
import sys
import tempfile
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
                         'docs/development/COMMUNITY_BILL_CONTRACT_EVIDENCE.json',
                         'scripts/community_project_materials.py',
                         'demos/community-stage/project-review.js'):
                self.assertIn(name, manifest['files'])
            bill='docs/development/COMMUNITY_BILL_CONTRACT_EVIDENCE.json'
            bill_raw=archive.read(bill)
            self.assertEqual(bill_raw,(root/bill).read_bytes())
            self.assertEqual(manifest['files'][bill],hashlib.sha256(bill_raw).hexdigest())
            self.assertIn('tests/test_community_bill_contract_evidence.py',manifest['files'])
            self.assertFalse(any(name.endswith(('.pem','.sqlite','.env')) for name in archive.namelist()))
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                isolated=subprocess.run(
                    [sys.executable,'-B','-m','unittest','discover','-s','tests',
                     '-p','test_community_bill_contract_evidence.py','-v'],
                    cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,timeout=60,check=False)
                self.assertEqual(isolated.returncode,0,isolated.stdout)
                self.assertIn('Ran 5 tests',isolated.stdout)
                self.assertIn('OK',isolated.stdout)

if __name__=='__main__':unittest.main()
