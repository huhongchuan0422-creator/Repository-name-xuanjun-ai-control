"""Offline fixed-product admission matrices. No provider/host/upload I/O.
Metadata records are synthetic fixtures; optional exact artifact bytes are real inputs.
"""
import copy, hashlib, importlib.util, io, json, os, pathlib, shutil, subprocess, tempfile, time, unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fixed_product',ROOT/'scripts/community_preview_fixed_product.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
spec=importlib.util.spec_from_file_location('readiness',ROOT/'scripts/community_preview_readiness.py')
health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health)
CONTROL='a'*40

def environment(temp):
    return dict(PATH=os.environ['PATH'],GITHUB_SHA=CONTROL,GITHUB_EVENT_NAME='workflow_dispatch',
      GITHUB_REPOSITORY=p.REPO,GITHUB_REF='refs/heads/'+p.BRANCH,GITHUB_RUN_ID='99999999999',
      GITHUB_RUN_ATTEMPT='1',PREVIEW_CONTROL_SHA=CONTROL,PREVIEW_SOURCE_SHA=p.PRODUCT_SHA,
      PREVIEW_TARGET=p.PROFILE,PREVIEW_EVIDENCE_RUN_ID=str(p.PRODUCT_RUN),
      PREVIEW_ENABLED='true',IMAGE_BUILD_ENABLED='false',RUNNER_TEMP=str(temp),
      COMMUNITY_FIXED_PRODUCT_PREVIEW='true',COMMUNITY_PREVIEW_PROFILE=p.PROFILE)

def metadata():
    run=dict(id=p.PRODUCT_RUN,head_sha=p.PRODUCT_SHA,head_branch=p.BRANCH,path=p.WORKFLOW,
      event='push',status='completed',conclusion='success',repository={'full_name':p.REPO},
      head_repository={'full_name':p.REPO})
    jobs=dict(total_count=1,jobs=[dict(id=p.PRODUCT_JOB,name='test',status='completed',conclusion='success',
      steps=[dict(name='Preview entry evidence affected scope (offline only)',status='completed',conclusion='success')])])
    artifacts=dict(total_count=1,artifacts=[dict(id=p.ARTIFACT_ID,name='community-phase-integration-evidence',
      expired=False,expires_at='2030-01-01T00:00:00Z',size_in_bytes=p.ARTIFACT_SIZE,
      digest='sha256:'+p.ARTIFACT_SHA256,workflow_run=dict(id=p.PRODUCT_RUN,head_sha=p.PRODUCT_SHA,
      head_branch=p.BRANCH,repository_id=1413132159,head_repository_id=1413132159))])
    return run,jobs,artifacts

class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.env=environment(self.root)
        self.records=metadata()
    def test_control_product_separate_and_fixed_literals(self):
        r=p.evidence(*self.records,self.env)
        self.assertEqual(r['control_source_sha'],CONTROL)
        self.assertEqual(r['product_source_sha'],'f13155ed63a3137d41766ee587d9b4b96a81477f')
        self.assertEqual(self.env['GITHUB_SHA'],CONTROL)
        self.assertEqual(r['artifact_id'],12546258346)
        self.assertFalse(r['upload_performed'])
    def test_context_rejects_wrong_branch_control_product_mode_run_and_target(self):
        for key,value in [('GITHUB_EVENT_NAME','push'),('GITHUB_REPOSITORY','other/repo'),
          ('GITHUB_REF','refs/heads/main'),('GITHUB_REF','refs/tags/f131'),('GITHUB_SHA','unknown'),
          ('PREVIEW_CONTROL_SHA','b'*40),('PREVIEW_SOURCE_SHA','b'*40),
          ('PREVIEW_TARGET','legacy'),('PREVIEW_EVIDENCE_RUN_ID','40059478387'),
          ('PREVIEW_ENABLED','false'),('IMAGE_BUILD_ENABLED','true'),('GITHUB_RUN_ID',str(p.PRODUCT_RUN)),
          ('GITHUB_RUN_ID','0'),('GITHUB_RUN_ATTEMPT','')]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                p.context(dict(self.env,**{key:value}))
    def test_push_evidence_requires_exact_original_success(self):
        for key,value in [('id',123),('head_sha',CONTROL),('head_branch','main'),('path','other.yml'),
          ('event','workflow_dispatch'),('status','in_progress'),('conclusion','failure'),
          ('repository',{'full_name':'other/repo'}),('head_repository',{'full_name':'other/repo'})]:
            records=copy.deepcopy(self.records);records[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.evidence(*records,self.env)
    def test_test_job_and_step_must_be_exact_success_not_skip_or_near_name(self):
        for patch_value in ({'id':123},{'name':'not-test'},{'status':'queued'},{'conclusion':'skipped'}):
            records=copy.deepcopy(self.records);records[1]['jobs'][0].update(patch_value)
            with self.subTest(patch=patch_value),self.assertRaises(ValueError):p.evidence(*records,self.env)
        for patch_value in ({'name':'Preview entry evidence affected scope (offline only) '},
                            {'status':'queued'},{'conclusion':'skipped'}):
            records=copy.deepcopy(self.records);records[1]['jobs'][0]['steps'][0].update(patch_value)
            with self.subTest(patch=patch_value),self.assertRaises(ValueError):p.evidence(*records,self.env)
    def test_artifact_exact_digest_id_expiry_size_and_origin(self):
        for patch_value in ({'id':123},{'name':'other'},{'expired':True},{'expires_at':'2020-01-01T00:00:00Z'},
           {'size_in_bytes':1},{'digest':'sha256:'+'0'*64},{'workflow_run':{'id':p.PRODUCT_RUN,'head_sha':CONTROL}}):
            records=copy.deepcopy(self.records);records[2]['artifacts'][0].update(patch_value)
            with self.subTest(patch=patch_value),self.assertRaises(ValueError):p.evidence(*records,self.env)
    def test_pagination_duplicates_and_partial_evidence_rejected(self):
        for index,key in [(1,'jobs'),(2,'artifacts')]:
            for count in (0,2,101):
                records=copy.deepcopy(self.records);records[index]['total_count']=count
                with self.subTest(index=index,count=count),self.assertRaises(ValueError):
                    p.evidence(*records,self.env)
            records=copy.deepcopy(self.records);records[index][key]*=2;records[index]['total_count']=2
            with self.assertRaises(ValueError):p.evidence(*records,self.env)
    def test_changed_source_archive_and_duplicate_json_rejected(self):
        with self.assertRaisesRegex(ValueError,'FIXED_ARTIFACT_BYTES_SHA_REQUIRED'):p.archive_source(b'not the pinned archive')
        with self.assertRaisesRegex(ValueError,'FIXED_PRODUCT_SOURCE_SHA_REQUIRED'):p.source_files(b'not the pinned source')
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):p.strict_json('{"a":1,"a":2}')
    def test_expired_or_foreign_receipt_cannot_stage_or_resume(self):
        receipt=p.evidence(*self.records,self.env)
        for key,value in [('control_source_sha','b'*40),('product_source_sha',CONTROL),
          ('product_run_id',1),('artifact_id',1),('artifact_sha256','0'*64),
          ('source_zip_sha256','0'*64),('source_manifest_sha256','0'*64),
          ('workflow_run_id','1'),('workflow_run_attempt','2'),('appid','wx0000000000000000'),
          ('baseUrl','https://evil.invalid'),('profile','legacy'),('artifact_bytes_reverified',False),
          ('upload_performed',True),('expires_at','2020-01-01T00:00:00Z')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                p.verify_receipt(dict(receipt,**{key:value}),self.env)
    def test_legacy_fallback_never_accepts_fixed_context_or_unknown_mode(self):
        env=dict(self.env,COMMUNITY_FIXED_PRODUCT_PREVIEW='false')
        self.assertEqual(p.identity(env)['product_source_sha'],CONTROL)
        for values in ({'COMMUNITY_PREVIEW_PRODUCT_CONTEXT':'anything'},{'COMMUNITY_FIXED_PRODUCT_PREVIEW':'maybe'}):
            with self.assertRaises(ValueError):p.identity(dict(env,**values))
    def test_health_exact_product_and_freshness_not_control_sha(self):
        identity=dict(product_source_sha=p.PRODUCT_SHA,control_source_sha=CONTROL,fixed_product=True)
        class Headers:
            def get_content_type(self):return 'application/json'
        class Response:
            status=200;headers=Headers()
            def __init__(self,body):self.body=body
            def geturl(self):return p.BASE_URL+'/community/health'
            def read(self,n):return json.dumps(self.body).encode()[:n]
            def __enter__(self):return self
            def __exit__(self,*args):pass
        now=int(time.time())
        body=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
          runtime_source_sha=p.PRODUCT_SHA,version_source='IMAGE_BUILD_STAMP',observed_at=now)
        report=health.check(lambda *a,**k:Response(body),p.PROFILE,identity)
        self.assertEqual(report['status'],'BACKEND_HEALTH_VERIFIED')
        self.assertEqual(report['frontend_source_sha'],p.PRODUCT_SHA)
        self.assertEqual(report['control_source_sha'],CONTROL)
        class Opener:
            def open(self,*args,**kwargs):return Response(body)
        with patch.object(health,'build_opener',return_value=Opener()) as builder:
            self.assertEqual(health.check(None,p.PROFILE,identity)['status'],'BACKEND_HEALTH_VERIFIED')
            handlers=builder.call_args.args
            self.assertTrue(any(isinstance(h,health.ProxyHandler) and h.proxies=={} for h in handlers))
            self.assertTrue(any(isinstance(h,health.NoRedirect) for h in handlers))
        for values in ({'runtime_source_sha':CONTROL},{'observed_at':now-601},{'observed_at':now+31},
                       {'observed_at':True},{'production_acceptance':True},{'version_source':'CLIENT_ENV'}):
            report=health.check(lambda *a,**k:Response(dict(body,**values)),p.PROFILE,identity)
            self.assertEqual(report['status'],'BACKEND_NOT_READY')
    def test_original_workflow_guards_secret_order_and_no_sha_rewrite(self):
        w=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        preview=w.split('  mini-preview:\n',1)[1]
        self.assertIn("inputs.preview_source_sha == github.sha",preview)
        self.assertIn("inputs.preview_evidence_run_id == '40058542631'",preview)
        self.assertIn("github.ref == 'refs/heads/"+p.BRANCH+"'",preview)
        self.assertIn('runs-on: [self-hosted, Linux, X64, xuanjun-domestic-ops]',preview)
        self.assertIn('test "$(hostname -s)" = iZvt5t8tlrm8oiZ',preview)
        self.assertIn('test "$(id -un)" = githubrunner',preview)
        self.assertLess(preview.index('Require live backend health'),preview.index('WECHAT_MINIPROGRAM_PRIVATE_KEY:'))
        self.assertLess(preview.index('Bind fixed product tree'),preview.index('Require live backend health'))
        self.assertIn('secrets.WECHAT_MINIPROGRAM_PRIVATE_KEY',preview)
        self.assertNotIn('GITHUB_SHA:',w)
        self.assertNotIn('GITHUB_SHA=',w)
        self.assertNotIn('actions: write',w)
        self.assertEqual(w.count('COMMUNITY_PREVIEW_PROFILE: uk-path-candidate'),1)
    def test_actual_job_guard_matrix_and_disabled_mode(self):
        w=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        sdk=w.split('  mini-sdk:\n',1)[1].splitlines()[0].strip().removeprefix('if: ')
        preview=w.split('  mini-preview:\n',1)[1].splitlines()[0].strip().removeprefix('if: ')
        self.assertEqual(sdk,preview)
        base=dict(github=dict(event_name='workflow_dispatch',sha=CONTROL,ref='refs/heads/'+p.BRANCH,
           event={'head_commit':{'message':''}}),inputs=dict(preview_enabled=True,backend_image_enabled=False,
           preview_source_sha=CONTROL,preview_evidence_run_id=str(p.PRODUCT_RUN),preview_target=p.PROFILE))
        cases=[dict(expected=True,**copy.deepcopy(base))]
        for key,value in [('preview_enabled',False),('backend_image_enabled',True),('preview_source_sha',p.PRODUCT_SHA),
                          ('preview_evidence_run_id','123'),('preview_target','legacy')]:
            row=copy.deepcopy(base);row['inputs'][key]=value;cases.append(dict(expected=False,**row))
        for ref in ['refs/heads/main','refs/tags/f131']:
            row=copy.deepcopy(base);row['github']['ref']=ref;cases.append(dict(expected=False,**row))
        program="const p=JSON.parse(process.argv[1]);const f=new Function('github','inputs','contains','return ('+p.expr+')');for(const c of p.cases){if(f(c.github,c.inputs,(s,t)=>String(s||'').includes(t))!==c.expected)throw Error('GUARD');}"
        r=subprocess.run(['node','-e',program,json.dumps(dict(expr=sdk,cases=cases))],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_download_only_fixed_github_token_request_then_clean_storage_request(self):
        from urllib.error import HTTPError
        requests=[]
        class Response:
            status=200
            def geturl(self):return 'https://signed.blob.core.windows.net/artifact?fixture=1'
            def read(self,n):return b'fixture bytes'
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class Opener:
            def open(self,request,timeout):
                requests.append(request)
                if len(requests)==1:
                    raise HTTPError(request.full_url,302,'fixture',{'Location':'https://signed.blob.core.windows.net/artifact?fixture=1'},None)
                return Response()
        with patch.object(p,'build_opener',return_value=Opener()):
            self.assertEqual(p.download_archive('SYNTHETIC_TOKEN'),b'fixture bytes')
        self.assertEqual(requests[0].full_url,'https://api.github.com/repos/'+p.REPO+'/actions/artifacts/12546258346/zip')
        self.assertEqual(requests[0].get_header('Authorization'),'Bearer SYNTHETIC_TOKEN')
        self.assertIsNone(requests[1].get_header('Authorization'))
    def test_download_rejects_untrusted_redirect_and_missing_token(self):
        from urllib.error import HTTPError
        for location in ('http://signed.blob.core.windows.net/x','https://evil.invalid/x',
          'https://user@signed.blob.core.windows.net/x','https://signed.blob.core.windows.net:444/x'):
            class Opener:
                def open(self,request,timeout):
                    raise HTTPError(request.full_url,302,'fixture',{'Location':location},None)
            with self.subTest(location=location),patch.object(p,'build_opener',return_value=Opener()),self.assertRaises(ValueError):
                p.download_archive('SYNTHETIC_TOKEN')
        with self.assertRaises(ValueError):p.download_archive('')
    def test_readiness_context_binds_control_before_credential_load(self):
        target=dict(profile=p.PROFILE,baseUrl=p.BASE_URL,origin='https://uk.wenwenwenyiyiyi.work',health_url=p.BASE_URL+'/community/health')
        now=int(time.time())
        report=dict(target,status='BACKEND_HEALTH_VERIFIED',http_status=200,login_verified=False,
          customer_acceptance=False,payment_enabled=False,frontend_source_sha=p.PRODUCT_SHA,
          backend_source_sha=p.PRODUCT_SHA,backend_version_source='IMAGE_BUILD_STAMP',compatibility='EXACT_SOURCE_MATCH',
          control_source_sha=CONTROL,backend_observed_at=now,observed_at=now)
        program="const {verifyReadiness}=require(process.argv[1]);const x=JSON.parse(process.argv[2]);verifyReadiness(x.report,x.target,x.head,x.now,x.control);for(const v of [undefined,'b'.repeat(40)]){try{verifyReadiness({...x.report,control_source_sha:v},x.target,x.head,x.now,x.control);}catch(e){if(e.message==='MATCHING_CONTROL_READINESS_REQUIRED')continue;throw e;}throw Error('missing control gate');}"
        result=subprocess.run(['node','-e',program,str(ROOT/'deploy/community-preview/endpoint.cjs'),json.dumps(dict(report=report,target=target,head=p.PRODUCT_SHA,now=now,control=CONTROL))],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_node_identity_child_does_not_receive_credentials(self):
        script="""const cp=require('node:child_process');let called=false;
cp.execFileSync=(bin,args,opts)=>{called=true;if('WECHAT_MINIPROGRAM_PRIVATE_KEY' in opts.env||'GITHUB_TOKEN' in opts.env)throw Error('credential leaked');
return JSON.stringify({fixed_product:true,control_source_sha:process.env.GITHUB_SHA,product_source_sha:'f13155ed63a3137d41766ee587d9b4b96a81477f',source_root:'/fixture'});};
const p=require(process.argv[1]);p.sourceIdentity();if(!called)throw Error('identity admission missing');"""
        env=dict(self.env,WECHAT_MINIPROGRAM_PRIVATE_KEY='SYNTHETIC_CANARY_NOT_A_KEY',GITHUB_TOKEN='SYNTHETIC_CANARY_NOT_A_TOKEN')
        r=subprocess.run(['node','-e',script,str(ROOT/'deploy/community-preview/endpoint.cjs')],
                         env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_missing_context_stops_before_upload(self):
        env=dict(self.env,COMMUNITY_MINI_PROJECT_PATH=str(self.root/'missing'),COMMUNITY_PREVIEW_OUTPUT=str(self.root/'out'))
        r=subprocess.run(['node',str(ROOT/'scripts/community_mini_preview.cjs')],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,4)
        self.assertFalse((self.root/'out/receipt.json').exists())

class ExactArtifact(unittest.TestCase):
    """Real source bytes optional for CI push; required in local/manual acceptance."""
    def setUp(self):
        Contracts.setUp(self)
        path=os.environ.get('COMMUNITY_FIXED_PRODUCT_TEST_SOURCE','')
        if not path:self.skipTest('EXACT_PRODUCT_SOURCE_FIXTURE_NOT_PROVIDED')
        self.raw=pathlib.Path(path).read_bytes()
        self.receipt=p.evidence(*self.records,self.env)
    def stage(self):
        p.stage(self.raw,self.receipt,self.env)
        destination,context=p.paths(self.env)
        self.env['COMMUNITY_PREVIEW_PRODUCT_CONTEXT']=str(context)
        return destination,context
    def test_actual_frozen_source_set_and_appid(self):
        files=p.source_files(self.raw)
        self.assertEqual(len(files),428)
        self.assertEqual(json.loads(files['clients/community-mini/project.config.json'])['appid'],p.APPID)
    def test_exact_stage_identity_and_duplicate_stage_denial(self):
        destination,context=self.stage()
        identity=p.identity(self.env)
        self.assertEqual(identity['product_source_sha'],p.PRODUCT_SHA)
        self.assertEqual(identity['control_source_sha'],CONTROL)
        before=context.read_bytes()
        with self.assertRaises(ValueError):p.stage(self.raw,self.receipt,self.env)
        self.assertEqual(context.read_bytes(),before)
        self.assertFalse(list(self.root.glob('.fixed-product-*')))
    def test_source_mutation_symlink_and_wrong_receipt_fail_closed(self):
        destination,context=self.stage()
        source=destination/'clients/community-mini/session.js';original=source.read_bytes()
        source.write_bytes(original+b'\nchanged')
        with self.assertRaises(ValueError):p.identity(self.env)
        source.unlink();source.symlink_to(destination/'clients/community-mini/app.js')
        with self.assertRaises(ValueError):p.identity(self.env)
        source.unlink();source.write_bytes(original)
        value=json.loads(context.read_text());value['control_source_sha']='b'*40;context.write_text(json.dumps(value))
        with self.assertRaises(ValueError):p.identity(self.env)
    def test_prepared_product_bytes_control_receipt_and_no_secret_upload(self):
        destination,context=self.stage()
        out=self.root/'prepared'
        env=dict(self.env,COMMUNITY_CONNECTED_MINI_OUTPUT=str(out))
        before=hashlib.sha256(self.raw).hexdigest()
        r=subprocess.run(['node',str(ROOT/'deploy/community-preview/prepare-mini.cjs')],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        prepared=json.loads((out/'CONNECTED_PREVIEW_RECEIPT.json').read_text())
        self.assertEqual(prepared['frontend_source_sha'],p.PRODUCT_SHA)
        self.assertEqual(prepared['control_source_sha'],CONTROL)
        self.assertEqual(len(prepared['prepared_files']),27)
        self.assertEqual(before,p.SOURCE_SHA256)
        self.assertFalse(prepared['upload_performed']);self.assertIsNone(prepared['scene'])
        self.assertEqual(self.env['GITHUB_SHA'],CONTROL)
        for name,digest in prepared['prepared_files'].items():
            self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            if name!='app.js':self.assertEqual((out/name).read_bytes(),(destination/'clients/community-mini'/name).read_bytes())
        now=int(time.time());proof=self.root/'health.json'
        proof.write_text(json.dumps(dict(status='BACKEND_HEALTH_VERIFIED',http_status=200,profile=p.PROFILE,
          baseUrl=p.BASE_URL,origin='https://uk.wenwenwenyiyiyi.work',health_url=p.BASE_URL+'/community/health',
          login_verified=False,customer_acceptance=False,payment_enabled=False,frontend_source_sha=p.PRODUCT_SHA,
          backend_source_sha=p.PRODUCT_SHA,control_source_sha=CONTROL,backend_version_source='IMAGE_BUILD_STAMP',
          compatibility='EXACT_SOURCE_MATCH',backend_observed_at=now,observed_at=now)))
        env.update(COMMUNITY_MINI_PROJECT_PATH=str(out),COMMUNITY_PREVIEW_READINESS_RECEIPT=str(proof),
                   COMMUNITY_PREVIEW_OUTPUT=str(self.root/'preview'))
        r=subprocess.run(['node',str(ROOT/'scripts/community_mini_preview.cjs')],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,2,r.stdout+r.stderr)
        actual=json.loads((self.root/'preview/receipt.json').read_text())
        self.assertEqual(actual['status'],'UPLOAD_KEY_NOT_AVAILABLE')
        self.assertEqual(actual['control_source_sha'],CONTROL)
        self.assertEqual(actual['frontend_source_sha'],p.PRODUCT_SHA)
        self.assertFalse((self.root/'preview/preview.png').exists())
        # Changed prepared source is rejected even with a synthetically valid health fixture.
        (out/'session.js').write_text('changed')
        env['COMMUNITY_PREVIEW_OUTPUT']=str(self.root/'preview-mutated')
        r=subprocess.run(['node',str(ROOT/'scripts/community_mini_preview.cjs')],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,4)
        self.assertFalse((self.root/'preview-mutated/receipt.json').exists())
        # Self-reported manifest edits cannot turn changed code into pinned f131.
        prepared['prepared_files']['session.js']=hashlib.sha256((out/'session.js').read_bytes()).hexdigest()
        (out/'CONNECTED_PREVIEW_RECEIPT.json').write_text(json.dumps(prepared))
        env['COMMUNITY_PREVIEW_OUTPUT']=str(self.root/'preview-forged-manifest')
        r=subprocess.run(['node',str(ROOT/'scripts/community_mini_preview.cjs')],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,4)
        self.assertFalse((self.root/'preview-forged-manifest/receipt.json').exists())

if __name__=='__main__':unittest.main()

