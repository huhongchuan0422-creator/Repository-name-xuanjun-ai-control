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
from unittest.mock import patch
import zipfile
from email.message import Message
from scripts.community_stage_package import build
from scripts.community_preview_readiness import check, target_for

ROOT = Path(__file__).resolve().parents[1]
HEAD = 'a' * 40


class EndpointContract(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,GITHUB_SHA=HEAD);env.start();self.addCleanup(env.stop)

    def response(self, url):
        body = io.BytesIO(json.dumps(dict(status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=HEAD,version_source='IMAGE_BUILD_STAMP',observed_at=int(time.time()))).encode())
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
                    customer_acceptance=False,payment_enabled=False,frontend_source_sha=HEAD,backend_source_sha=HEAD,
                    backend_version_source='IMAGE_BUILD_STAMP',compatibility='EXACT_SOURCE_MATCH',
                    backend_observed_at=int(time.time()),observed_at=int(time.time()))
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
                upload_receipt=json.loads((root/'receipt-1/receipt.json').read_text())
                self.assertEqual(upload_receipt['status'],'UPLOAD_KEY_NOT_AVAILABLE')
                self.assertEqual(upload_receipt['frontend_source_sha'],HEAD)
                self.assertEqual(upload_receipt['backend_source_sha'],HEAD)
                self.assertIsNone(upload_receipt['scene'])
                self.assertEqual(upload_receipt['search_query'],'')
                for patch in ({'profile':'unknown'},{'backend_source_sha':'b'*40},{'observed_at':0},
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
        self.assertEqual(candidate.count('proxy_set_header X-Xuanjun-Client-IP "";'),3)
        self.assertEqual(candidate.count('proxy_set_header X-Xuanjun-Client-IP $remote_addr;'),3)

    def test_helpers_are_required_zip_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.extracted(Path(tmp))
            for name in ('endpoint.cjs','endpoint-profiles.json','native-backend-compatibility.json'):
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

    def test_existing_manual_preview_is_default_off_exact_head_and_fixed_target(self):
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        dispatch=workflow.split('  workflow_dispatch:\n',1)[1].split('permissions:',1)[0]
        self.assertIn("preview_enabled:",dispatch)
        self.assertIn('type: boolean\n        default: false',dispatch)
        self.assertIn('options: [uk-path-candidate]',dispatch)
        sdk=workflow.split('  mini-sdk:\n',1)[1].splitlines()[0].strip().removeprefix('if: ')
        preview=workflow.split('  mini-preview:\n',1)[1].splitlines()[0].strip().removeprefix('if: ')
        self.assertEqual(sdk,preview)
        branch='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017'
        contexts=[]
        def case(expected,event='workflow_dispatch',enabled=False,sha=HEAD,target='uk-path-candidate',ref=branch,message=''):
            contexts.append(dict(expected=expected,github=dict(event_name=event,sha=HEAD,ref=ref,
                event=dict(head_commit=dict(message=message))),inputs=dict(preview_enabled=enabled,
                preview_source_sha=sha,preview_target=target,preview_evidence_run_id='40956400516')))
        case(False);case(False,enabled=True,sha='b'*40)
        case(False,enabled=True,target='legacy');case(False,enabled=True,ref='refs/heads/main')
        case(True,enabled=True);case(False,event='push')
        case(True,event='push',message='original [mini-preview] request')
        # Evaluate the actual job expression offline, not a copied policy helper.
        program="""const p=JSON.parse(process.argv[1]);
        const run=new Function('github','inputs','contains','return ('+p.expression+')');
        for(const c of p.contexts){const value=run(c.github,c.inputs,(s,t)=>String(s||'').includes(t));
          if(value!==c.expected)throw Error('PREVIEW_TRIGGER_POLICY_MISMATCH');}
        """
        result=subprocess.run(['node','-e',program,json.dumps(dict(expression=sdk,contexts=contexts))],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('miniprogram-ci@2.1.31',workflow)
        self.assertIn('runs-on: [self-hosted, Linux, X64, xuanjun-domestic-ops]',workflow)
        self.assertIn("test \"$(id -un)\" = githubrunner",workflow)

    def test_original_image_binds_env_and_stamp_to_same_build_revision(self):
        docker=(ROOT/'deploy/community-preview/Dockerfile').read_text()
        self.assertIn('ENV COMMUNITY_SOURCE_SHA=$SOURCE_SHA',docker)
        self.assertIn('"$SOURCE_SHA" > /app/COMMUNITY_SOURCE_SHA',docker)
        self.assertIn('chmod 0444 /app/COMMUNITY_SOURCE_SHA',docker)
        self.assertIn('LABEL org.opencontainers.image.revision=$SOURCE_SHA',docker)
        preview=(ROOT/'scripts/community_mini_preview.cjs').read_text()
        self.assertNotIn('scene=shop1',preview)
        self.assertIn("pagePath:'pages/home/index',searchQuery:''",preview)



class HostedEvidence(unittest.TestCase):
    """Execute the actual workflow validator offline; no success claims for WeChat."""
    def setUp(self):
        import textwrap
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        code=textwrap.dedent(workflow.split("python - <<'EVIDENCE'\n",1)[1].split('          EVIDENCE',1)[0])
        self.ns={'__name__':'offline_contract_fixture'}
        exec(compile(code,'actual-workflow-evidence-block','exec'),self.ns)
        self.workflow=workflow
        repo='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
        branch='feature/chatgpt-community-wechat-sp-offline-20261017'
        self.run=dict(id=101,head_sha=HEAD,head_branch=branch,path='.github/workflows/chatgpt-community-wechat-sp-offline.yml',
            event='push',status='completed',conclusion='success',repository={'full_name':repo},head_repository={'full_name':repo})
        self.jobs=dict(total_count=1,jobs=[dict(id=202,name='test',status='completed',conclusion='success',
            steps=[dict(name='Preview entry evidence affected scope (offline only)',status='completed',conclusion='success')])])
        self.artifacts=dict(total_count=1,artifacts=[dict(id=303,name='community-phase-integration-evidence',expired=False,
            expires_at='2030-01-01T00:00:00Z',size_in_bytes=1000,digest='sha256:'+'a'*64,
            workflow_run=dict(id=101,head_sha=HEAD,head_branch=branch,repository_id=1413132159,head_repository_id=1413132159))])
    def validate(self,**kw):
        args=dict(run=self.run,jobs=self.jobs,artifacts=self.artifacts,head=HEAD,evidence_id=101,current_id=102,now=1000)
        args.update(kw)
        return self.ns['validate'](**args)
    def test_success_reuses_test_evidence_but_does_not_claim_artifact_bytes_downloaded(self):
        result=self.validate()
        self.assertEqual(result['head_sha'],HEAD)
        self.assertEqual(result['artifact']['id'],303)
        self.assertFalse(result['artifact_bytes_reverified'])
        self.assertEqual(result['source_package'],'REBUILD_FROM_CURRENT_EXACT_CHECKOUT')
    def test_wrong_sha_branch_workflow_event_repo_or_incomplete_run_denied(self):
        for patch in ({'head_sha':'b'*40},{'head_branch':'main'},{'path':'other.yml'},{'event':'workflow_dispatch'},
                      {'status':'in_progress'},{'conclusion':'failure'},{'id':999},
                      {'repository':{'full_name':'other/repo'}},{'head_repository':{'full_name':'other/repo'}}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.validate(run=dict(self.run,**patch))
    def test_missing_skipped_failed_or_unrelated_test_step_cannot_replace_test_gate(self):
        import copy
        for patch in ({'conclusion':'skipped'},{'status':'in_progress'},{'name':'other-scope'}):
            data=copy.deepcopy(self.jobs);data['jobs'][0]['steps'][0].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.validate(jobs=data)
        with self.assertRaises(ValueError):self.validate(jobs={'jobs':[],'total_count':0})
    def test_artifact_expiry_digest_missing_or_foreign_binding_denied(self):
        import copy
        for patch in ({'expired':True},{'expires_at':'1970-01-01T00:01:00Z'},
                      {'digest':'unknown'},{'size_in_bytes':0},{'workflow_run':{'id':101,'head_sha':'b'*40}},
                      {'name':'other-source'}):
            data=copy.deepcopy(self.artifacts);data['artifacts'][0].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.validate(artifacts=data)
    def test_current_run_duplicate_artifact_and_pagination_unknown_denied(self):
        with self.assertRaises(ValueError):self.validate(current_id=101)
        with self.assertRaises(ValueError):self.validate(jobs=dict(self.jobs,total_count=101))
        with self.assertRaises(ValueError):self.validate(artifacts=dict(self.artifacts,total_count=101))
        with self.assertRaises(ValueError):self.validate(artifacts=dict(self.artifacts,artifacts=self.artifacts['artifacts']*2))
    def test_manual_enabled_reuses_gate_instead_of_full_old_regression(self):
        full=self.workflow.split('      - name: Complete Phase1 and Phase2 source regression',1)[1].split('        run:',1)[0]
        self.assertIn("!(github.event_name == 'workflow_dispatch' && inputs.preview_enabled)",full)
        self.assertIn("inputs.preview_evidence_run_id",self.workflow)
        self.assertIn('  mini-sdk:\n',self.workflow)
        sdk=self.workflow.split('  mini-sdk:\n',1)[1].split('    steps:',1)[0]
        self.assertIn('needs: test',sdk)
        preview=self.workflow.split('  mini-preview:\n',1)[1].split('    steps:',1)[0]
        self.assertIn('needs: [test, mini-sdk]',preview)
        self.assertIn('contents: read',self.workflow)
        self.assertNotIn('actions: write',self.workflow)
        # Already present on the current control baseline; needed for fixed artifact read.
        self.assertIn('actions: read',self.workflow)
    def test_exact_ocr_host_step_success_is_admitted_and_matches_actual_step(self):
        name='Original host OCR lifecycle and Mini feedback affected scope'
        self.assertIn('      - name: '+name+'\n',self.workflow)
        self.jobs['jobs'][0]['steps'][0]['name']=name
        self.assertEqual(self.validate()['test_job_id'],202)
        self.assertFalse(self.validate()['artifact_bytes_reverified'])

    def test_accepted_names_are_exactly_the_four_original_scopes_plus_ocr_host(self):
        import ast,textwrap
        source=textwrap.dedent(self.workflow.split("python - <<'EVIDENCE'\n",1)[1].split('          EVIDENCE',1)[0])
        assignments=[node for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Assign)
                     and any(isinstance(target,ast.Name) and target.id=='accepted' for target in node.targets)]
        self.assertEqual(len(assignments),1)
        self.assertEqual(ast.literal_eval(assignments[0].value),{
            'Complete Phase1 and Phase2 source regression',
            'Preview version and entry affected scope (no provider or host I/O)',
            'Preview entry evidence affected scope (offline only)',
            'UK read-only inspection candidate affected scope (no site execution)',
            'Original host OCR lifecycle and Mini feedback affected scope'})

    def test_ocr_host_near_names_and_arbitrary_success_are_not_admitted(self):
        import copy
        exact='Original host OCR lifecycle and Mini feedback affected scope'
        for name in (exact+' ',exact+' extra','prefix '+exact,exact.lower(),'OCR','Set up job','success'):
            data=copy.deepcopy(self.jobs);data['jobs'][0]['steps'][0]['name']=name
            data['jobs'][0]['steps'].append(dict(name='Upload artifact',status='completed',conclusion='success'))
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'SUCCESSFUL_TEST_GATE_REQUIRED'):
                self.validate(jobs=data)

    def test_ocr_host_requires_completed_successful_step_and_exact_test_job(self):
        import copy
        self.jobs['jobs'][0]['steps'][0]['name']='Original host OCR lifecycle and Mini feedback affected scope'
        for patch in ({'conclusion':'failure'},{'conclusion':'cancelled'},{'conclusion':'skipped'},
                      {'conclusion':None},{'status':'in_progress'},{'status':'queued'}):
            data=copy.deepcopy(self.jobs);data['jobs'][0]['steps'][0].update(patch)
            with self.subTest(step=patch),self.assertRaises(ValueError):self.validate(jobs=data)
        for patch in ({'name':'other-job'},{'status':'in_progress'},{'conclusion':'failure'},{'conclusion':'cancelled'}):
            data=copy.deepcopy(self.jobs);data['jobs'][0].update(patch)
            with self.subTest(job=patch),self.assertRaises(ValueError):self.validate(jobs=data)
        data=copy.deepcopy(self.jobs);data['jobs']*=2;data['total_count']=2
        with self.assertRaisesRegex(ValueError,'SUCCESSFUL_TEST_GATE_REQUIRED'):self.validate(jobs=data)

    def test_new_ocr_host_scope_preserves_all_existing_bindings_and_artifact_gates(self):
        self.jobs['jobs'][0]['steps'][0]['name']='Original host OCR lifecycle and Mini feedback affected scope'
        # Run the original full negative matrices with this newly accepted scope:
        # a successful OCR step must never override SHA/repo/event/artifact proof.
        self.test_wrong_sha_branch_workflow_event_repo_or_incomplete_run_denied()
        self.test_artifact_expiry_digest_missing_or_foreign_binding_denied()
        self.test_current_run_duplicate_artifact_and_pagination_unknown_denied()

    def test_read_is_fixed_public_github_only_without_token_or_dispatch(self):
        import inspect
        # AST/function code, not a request to the live provider.
        names=set(self.ns['read'].__code__.co_names)
        self.assertIn('build_opener',names)
        self.assertNotIn('environ',names)
        self.assertIn('https://api.github.com/repos/',str(self.ns['read'].__code__.co_consts))
        self.assertNotIn('Authorization',str(self.ns['read'].__code__.co_consts))

if __name__=='__main__':
    unittest.main()

