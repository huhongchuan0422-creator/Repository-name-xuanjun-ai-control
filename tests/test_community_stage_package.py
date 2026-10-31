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
    def test_connection_scope_installs_existing_host_dependency_before_package_import(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        name='      - name: Community fixed action candidate affected scope\n'
        block=workflow.split(name,1)[1].split('      - name:',1)[0]
        self.assertIn("if: contains(github.event.head_commit.message, '[community-connection-scope]')",block)
        self.assertIn('NODE_OPTIONS: --test-reporter=tap',block)
        install='python -m pip install cryptography==50.0.2'
        self.assertEqual(block.count(install),1)
        self.assertLess(block.index(install),block.index("-p 'test_community_connection_collect.py'"))
        self.assertLess(block.index(install),block.index("-p 'test_community_stage_package.py'"))

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
                'clients/community-mini/assets/community-demo-storefront-v1.jpg',
                'deploy/community-preview/Dockerfile',
                'deploy/community-preview/requirements-runtime.lock',
                'deploy/community-preview/nginx-uk-path-candidate.conf',
                'scripts/community_platform_host.py',
                'scripts/community_web_entries.py',
                'scripts/community_web_session.py',
                'demos/community-stage/web-session.js',
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
                'clients/community-mini/pages/merchant/index.js',
                'clients/community-mini/pages/merchant/index.wxml',
                'clients/community-mini/pages/merchant-join/index.js',
                'clients/community-mini/pages/merchant-join/index.wxml',
                'clients/community-mini/merchant-form.js',
                'clients/community-mini/merchant-fields.json',
                'scripts/community_mini_merchant.py',
                'scripts/community_collection_code.py',
                'scripts/community_review_runtime.py',
                'demos/community-stage/review-runtime.html',
                'demos/community-stage/review-native.js',
            )
            for name in required_pages:
                raw=archive.read(name)
                self.assertEqual(raw,(root/name).read_bytes())
                self.assertEqual(manifest['files'][name],hashlib.sha256(raw).hexdigest())
            photo='clients/community-mini/assets/community-demo-storefront-v1.jpg'
            photo_sha='f8e066fc2153b5beff1ae65faf9be5383d877eb77336cc5e16c90468b13b65b6'
            self.assertEqual(len(archive.read(photo)),160523)
            self.assertEqual(manifest['files'][photo],photo_sha)
            self.assertEqual(hashlib.sha256(archive.read(photo)).hexdigest(),photo_sha)
            self.assertIn("'/assets/community-demo-storefront-v1.jpg'",archive.read('clients/community-mini/pages/checkout/index.js').decode())
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
                photo_target=output/'assets/community-demo-storefront-v1.jpg'
                self.assertEqual(photo_target.read_bytes(),archive.read(photo))
                self.assertEqual(hashlib.sha256(photo_target.read_bytes()).hexdigest(),photo_sha)
                self.assertEqual(receipt['prepared_files']['assets/community-demo-storefront-v1.jpg'],photo_sha)
                self.assertEqual(len(receipt['prepared_files']),36)
                prepared_names={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
                self.assertEqual(prepared_names,set(receipt['prepared_files'])|{'CONNECTED_PREVIEW_RECEIPT.json'})
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
            # One named asset only: sibling binary files must not expand the package scope.
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                unapproved=Path(tmp)/'clients/community-mini/assets/not-allowlisted.jpg'
                unapproved.write_bytes(b'not approved asset')
                self.assertEqual((data,digest),build(Path(tmp)))
                photo_path=Path(tmp)/photo
                photo_path.unlink()
                photo_path.symlink_to(unapproved)
                with self.assertRaisesRegex(ValueError,'PACKAGE_SYMLINK_DENIED'):
                    build(Path(tmp))
            for missing in required_pages:
                with tempfile.TemporaryDirectory() as tmp:
                    archive.extractall(tmp)
                    (Path(tmp)/missing).unlink()
                    with self.assertRaisesRegex(ValueError,'REQUIRED_SOURCE_MISSING'):
                        build(Path(tmp))

if __name__=='__main__':unittest.main()
