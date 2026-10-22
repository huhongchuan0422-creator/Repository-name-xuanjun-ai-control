import hashlib
import io
import json
import os
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
            required_pages=(
                'clients/community-mini/app.wxss',
                'deploy/community-preview/nginx-uk-path-candidate.conf',
                'scripts/community_platform_host.py',
                'scripts/community_persistent_runtime.py',
                'scripts/community_first_install.py',
                'scripts/community_wechat_registration.py',
                'deploy/community-preview/prepare-mini.cjs',
                'deploy/community-preview/endpoint.cjs',
                'deploy/community-preview/endpoint-profiles.json',
                'clients/community-mini/pages/home/index.js',
                'clients/community-mini/pages/home/index.json',
                'clients/community-mini/pages/home/index.wxml',
                'clients/community-mini/pages/profile/index.js',
                'clients/community-mini/pages/profile/index.json',
                'clients/community-mini/pages/profile/index.wxml',
            )
            for name in required_pages:
                raw=archive.read(name)
                self.assertEqual(raw,(root/name).read_bytes())
                self.assertEqual(manifest['files'][name],hashlib.sha256(raw).hexdigest())
            self.assertFalse(any(name.endswith(('.pem','.sqlite','.env')) for name in archive.namelist()))
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                host_help=subprocess.run(
                    [sys.executable,'-B','-m','scripts.community_platform_host','--help'],
                    cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,timeout=20,check=False)
                self.assertEqual(host_help.returncode,0,host_help.stdout)
                self.assertIn('--wechat-secret',host_help.stdout)
                output=Path(tmp)/'connected-preview'
                prepared=subprocess.run(
                    ['node','deploy/community-preview/prepare-mini.cjs'],cwd=tmp,
                    env=dict(os.environ,COMMUNITY_CONNECTED_MINI_OUTPUT=str(output)),
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
                self.assertEqual(prepared.returncode,0,prepared.stdout)
                receipt=json.loads((output/'CONNECTED_PREVIEW_RECEIPT.json').read_text())
                self.assertEqual(receipt['baseUrl'],'https://community-preview.wenwenwenyiyiyi.work')
                self.assertEqual(receipt['appid'],json.loads((output/'project.config.json').read_text())['appid'])
                self.assertTrue(receipt['commerce']);self.assertFalse(receipt['payments'])
                self.assertTrue((output/'pages/home/index.wxml').is_file())
                isolated=subprocess.run(
                    [sys.executable,'-B','-m','unittest','discover','-s','tests',
                     '-p','test_community_bill_contract_evidence.py','-v'],
                    cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,timeout=60,check=False)
                self.assertEqual(isolated.returncode,0,isolated.stdout)
                self.assertIn('Ran 5 tests',isolated.stdout)
                self.assertIn('OK',isolated.stdout)
                customer=subprocess.run(
                    ['node','--test','clients/community-mini/customer-pages.test.cjs'],
                    cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,timeout=60,check=False)
                self.assertEqual(customer.returncode,0,customer.stdout)
                self.assertIn('# fail 0',customer.stdout)
            for missing in required_pages:
                with tempfile.TemporaryDirectory() as tmp:
                    archive.extractall(tmp)
                    (Path(tmp)/missing).unlink()
                    with self.assertRaisesRegex(ValueError,'REQUIRED_SOURCE_MISSING'):
                        build(Path(tmp))

if __name__=='__main__':unittest.main()
