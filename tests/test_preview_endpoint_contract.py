"""Offline endpoint/ZIP/upload-boundary checks; no real provider or host calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import zipfile
from email.message import Message
from scripts.community_stage_package import build
from scripts.community_preview_readiness import check, target_for

ROOT = Path(__file__).resolve().parents[1]
HEAD = 'a' * 40


class EndpointContract(unittest.TestCase):
    def response(self, url):
        body = io.BytesIO(json.dumps(dict(status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False)).encode())
        body.status=200
        body.headers=Message()
        body.headers['Content-Type']='application/json'
        body.geturl=lambda:url
        return body

    def test_profiles_health_exact_url_and_unknown_never_connects(self):
        for profile in ('legacy','uk-path-candidate'):
            target=target_for(profile)
            calls=[]
            def opener(request,timeout):
                calls.append(request.full_url)
                return self.response(target['health_url'])
            report=check(opener,profile)
            self.assertEqual(calls,[target['health_url']])
            self.assertEqual(report['status'],'BACKEND_HEALTH_VERIFIED')
            self.assertEqual(report['baseUrl'],target['baseUrl'])
            self.assertFalse(report['customer_acceptance'])
        def forbidden(*a,**k):
            self.fail('unknown profile must not make network request')
        self.assertEqual(check(forbidden,'unknown')['status'],'BACKEND_NOT_READY')

    def test_uk_health_cannot_use_old_origin_response(self):
        report=check(lambda *a,**k:self.response(target_for('legacy')['health_url']),'uk-path-candidate')
        self.assertEqual(report['status'],'BACKEND_NOT_READY')

    def extracted(self, root):
        data,digest=build(ROOT)
        archive_path=root/'actual-source.zip'
        archive_path.write_bytes(data)
        self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(),digest)
        source=root/'source'
        source.mkdir()
        self.assertFalse(list(source.iterdir()))
        with zipfile.ZipFile(archive_path) as z:
            manifest=json.loads(z.read('MANIFEST.json'))
            self.assertEqual(set(z.namelist()),set(manifest['files'])|{'MANIFEST.json'})
            for name,expected in manifest['files'].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),expected)
            z.extractall(source)
        return source

    def test_both_profiles_prepare_from_real_zip_and_upload_requires_bound_proof(self):
        for profile in ('legacy','uk-path-candidate'):
            with self.subTest(profile=profile),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=self.extracted(root);out=root/'connected'
                env=dict(os.environ,COMMUNITY_PREVIEW_PROFILE=profile,
                    COMMUNITY_CONNECTED_MINI_OUTPUT=str(out),GITHUB_SHA=HEAD)
                prepare=subprocess.run(['node','deploy/community-preview/prepare-mini.cjs'],cwd=source,
                    env=env,capture_output=True,text=True,timeout=15)
                self.assertEqual(prepare.returncode,0,prepare.stderr)
                receipt=json.loads((out/'CONNECTED_PREVIEW_RECEIPT.json').read_text())
                target=target_for(profile)
                self.assertEqual(receipt['baseUrl'],target['baseUrl'])
                self.assertEqual(receipt['profile'],profile)
                self.assertIn("baseUrl: '"+target['baseUrl']+"'",(out/'app.js').read_text())
                proof=root/'health.json'
                report=dict(target,status='BACKEND_HEALTH_VERIFIED',http_status=200,login_verified=False,
                    customer_acceptance=False,payment_enabled=False,source_sha=HEAD,observed_at=int(time.time()))
                proof.write_text(json.dumps(report))
                env.update(COMMUNITY_MINI_PROJECT_PATH=str(out),COMMUNITY_PREVIEW_OUTPUT=str(root/'receipt'),
                    COMMUNITY_PREVIEW_READINESS_RECEIPT=str(proof))
                env.pop('WECHAT_MINIPROGRAM_PRIVATE_KEY',None)
                env.pop('WECHAT_MINIPROGRAM_APPID',None)
                attempts=0
                def upload():
                    nonlocal attempts
                    attempts+=1
                    env['COMMUNITY_PREVIEW_OUTPUT']=str(root/('receipt-'+str(attempts)))
                    return subprocess.run(['node','scripts/community_mini_preview.cjs'],cwd=source,
                        env=env,capture_output=True,text=True,timeout=15)
                valid=upload()
                self.assertEqual(valid.returncode,2,valid.stdout+valid.stderr)
                self.assertEqual(json.loads((root/'receipt-1/receipt.json').read_text())['status'],'UPLOAD_KEY_NOT_AVAILABLE')
                for patch in ({'profile':'unknown'},{'source_sha':'b'*40},{'observed_at':0},
                              {'baseUrl':target['baseUrl']+'/wrong'},{'status':'BACKEND_NOT_READY'}):
                    proof.write_text(json.dumps(dict(report,**patch)))
                    self.assertEqual(upload().returncode,4)
                proof.write_text(json.dumps(report))
                for relative in ('session.js','app.wxss','pages/home/index.wxml'):
                    p=out/relative;original=p.read_bytes()
                    p.write_bytes(original+b'\n// changed after preparation')
                    self.assertEqual(upload().returncode,4)
                    p.write_bytes(original)
                missing=out/'pages/home/index.wxml';original=missing.read_bytes();missing.unlink()
                self.assertEqual(upload().returncode,4)
                missing.write_bytes(original)
                extra=out/'unexpected.js';extra.write_text('unexpected')
                self.assertEqual(upload().returncode,4);extra.unlink()
                linked=out/'session.js';original=linked.read_bytes();linked.unlink()
                linked.symlink_to(source/'clients/community-mini/session.js')
                self.assertEqual(upload().returncode,4);linked.unlink();linked.write_bytes(original)
                (out/'app.js').write_text((out/'app.js').read_text()+'\n// modified after preparation')
                self.assertEqual(upload().returncode,4)
                self.assertFalse(list(root.glob('receipt-*/preview.png')))

    def test_existing_qr_is_not_reused_or_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'output';out.mkdir()
            qr=out/'preview.png';qr.write_bytes(b'old synthetic marker')
            env=dict(os.environ,COMMUNITY_PREVIEW_OUTPUT=str(out))
            env.pop('WECHAT_MINIPROGRAM_PRIVATE_KEY',None)
            result=subprocess.run(['node','scripts/community_mini_preview.cjs'],cwd=ROOT,
                env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,4)
            self.assertEqual(qr.read_bytes(),b'old synthetic marker')

    def test_uk_route_candidate_is_scoped_and_keeps_source_header_boundary(self):
        candidate=(ROOT/'deploy/community-preview/nginx-uk-path-candidate.conf').read_text()
        self.assertNotRegex(candidate,r'(?m)^\s*(listen|server_name|ssl_certificate)\s')
        self.assertIn('location ^~ /community-preview/mini/',candidate)
        self.assertIn('location = /community-preview/community/health',candidate)
        self.assertNotIn('location / {',candidate)
        self.assertEqual(candidate.count('proxy_set_header X-Xuanjun-Client-IP "";'),2)
        self.assertEqual(candidate.count('proxy_set_header X-Xuanjun-Client-IP $remote_addr;'),2)

    def test_helpers_are_required_zip_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.extracted(Path(tmp))
            for name in ('endpoint.cjs','endpoint-profiles.json'):
                p=source/'deploy/community-preview'/name
                original=p.read_bytes();p.unlink()
                with self.assertRaisesRegex(ValueError,'REQUIRED_SOURCE_MISSING'):
                    build(source)
                p.write_bytes(original)

    def test_workflow_uses_one_profile_and_retains_manifest_gate(self):
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        self.assertEqual(workflow.count('COMMUNITY_PREVIEW_PROFILE: uk-path-candidate'),1)
        self.assertNotIn('COMMUNITY_PREVIEW_PROFILE: legacy',workflow)
        self.assertIn('COMMUNITY_PREVIEW_READINESS_RECEIPT:',workflow)
        job_config=workflow.split('  mini-preview:\n',1)[1].split('    steps:',1)[0]
        self.assertNotIn('runner.temp',job_config)
        self.assertIn("hashlib.sha256(data).hexdigest()==manifest['files'][item.filename]",workflow)
        self.assertIn("'deploy/community-preview/endpoint-profiles.json'",workflow)
        self.assertIn('stat.S_ISREG(item.external_attr >> 16)',workflow)


if __name__=='__main__':
    unittest.main()
