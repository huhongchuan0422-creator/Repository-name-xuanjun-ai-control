"""Offline contract tests. No provider call, credential, live login or real QR."""
import pathlib, subprocess, unittest, tempfile, shutil, os, json
ROOT=pathlib.Path(__file__).resolve().parents[1]

class IsolatedPreview354(unittest.TestCase):
    def test_fixed_source_and_negative_boundaries(self):
        script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),events=require('node:events');
const helper=require('./scripts/community_mini_isolated_preview_354.cjs');
const {sourceManifest,verifySource}=require('./deploy/community-preview/endpoint.cjs');
let checks=0;function check(fn){fn();checks++;}
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'preview354-offline-'));
const eventPath=path.join(tmp,'event.json'),control='a'.repeat(40);
fs.writeFileSync(eventPath,JSON.stringify({after:control,head_commit:{message:'bind [mini-test-preview-354]'}}));
const env={GITHUB_EVENT_NAME:'push',GITHUB_REPOSITORY:'huhongchuan0422-creator/Repository-name-xuanjun-ai-control',GITHUB_REF:'refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017',GITHUB_SHA:control,GITHUB_EVENT_PATH:eventPath,COMMUNITY_MINI_OPERATION:'preview',COMMUNITY_MINI_PROJECT_PATH:path.join(tmp,'project'),COMMUNITY_PREVIEW_OUTPUT:path.join(tmp,'receipts'),COMMUNITY_MINI_CI_MODULE_ROOT:path.join(tmp,'sdk')};
const ready={status:'READY',scope:'PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance:false,runtime_source_sha:helper.SOURCE,version_source:'IMAGE_BUILD_STAMP',observed_at:1000};
check(()=>assert.equal(helper.context(env),control));
check(()=>assert.equal(helper.SOURCE,'6b3e78112da13d766a6d68e4ceafc0c301e004ac'));
check(()=>assert.throws(()=>helper.verifyHealth({...ready,runtime_source_sha:'a942fe4511b26d7c7923dd1307eb40062bcbd36d'},1000)));
check(()=>assert(Object.hasOwn(helper.HASHES,'submission-diagnostic.js')));
for(const [key,value] of Object.entries({GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'wrong/repo',GITHUB_REF:'refs/heads/main',GITHUB_SHA:'invalid',COMMUNITY_MINI_OPERATION:'upload'}))check(()=>assert.throws(()=>helper.context({...env,[key]:value})));
for(const message of ['[mini-upload]','[mini-preview]','[mini-test-preview-354] [mini-upload]','[mini-test-preview-354] [mini-preview]']){fs.writeFileSync(eventPath,JSON.stringify({after:control,head_commit:{message}}));check(()=>assert.throws(()=>helper.context(env)));}
fs.writeFileSync(eventPath,JSON.stringify({after:control,head_commit:{message:'bind [mini-test-preview-354]'}}));
check(()=>assert.equal(helper.verifyHealth(ready,1000),ready));
for(const [key,value] of Object.entries({status:'NOT_READY',runtime_source_sha:'b'.repeat(40),version_source:'CALLER',production_acceptance:true,observed_at:0}))check(()=>assert.throws(()=>helper.verifyHealth({...ready,[key]:value},1000)));
check(()=>assert.throws(()=>helper.verifyHealth({...ready,observed_at:1031},1000)));
check(()=>assert.deepEqual(sourceManifest('./clients/community-mini'),Object.assign(Object.create(null),helper.HASHES)));
// Reject the stale historical frontend pin against the exact current frontend.
check(()=>assert.throws(()=>verifySource(path.join(CURRENT_ROOT,'clients/community-mini'),{...helper.HASHES,'merchant-form.js':'912cf6b8f746ec5a3027f9df667bf882e5344ccd1aa3085d7f67ff1bba8a6ca2'}),/PREPARED_SOURCE_CHANGED/));
// Mock only in this offline test. No real network or SDK.
const https=require('node:https');let requests=0;
https.get=(url,opts,cb)=>{assert.equal(url,helper.BASE+'/community/health');requests++;const req=new events.EventEmitter();req.setTimeout=()=>{};req.destroy=()=>{};process.nextTick(()=>{const res=new events.EventEmitter();res.statusCode=200;res.headers={'content-type':'application/json'};cb(res);res.emit('data',Buffer.from(JSON.stringify({...ready,observed_at:Math.floor(Date.now()/1000)})));res.emit('end');});return req;};
(async()=>{
 await helper.prepare(env);checks++;
 check(()=>assert.equal(requests,1));
 check(()=>assert(!fs.existsSync(path.join(env.COMMUNITY_MINI_PROJECT_PATH,'merchant-fields.test.cjs'))));
 check(()=>assert.equal(helper.preparedSource(env.COMMUNITY_MINI_PROJECT_PATH)['pages/home/index.js'],helper.HASHES['pages/home/index.js']));
 const appPath=path.join(env.COMMUNITY_MINI_PROJECT_PATH,'app.js'),original=fs.readFileSync(appPath,'utf8');
 for(const bad of [original.replace(helper.BASE,'https://uk.wenwenwenyiyiyi.work/community-preview'),original.replace(helper.SCENE,'shop1'),original.replace('payments: false','payments: true')]){fs.writeFileSync(appPath,bad);check(()=>assert.throws(()=>helper.preparedSource(env.COMMUNITY_MINI_PROJECT_PATH)));}fs.writeFileSync(appPath,original);
 const cfg=path.join(env.COMMUNITY_MINI_PROJECT_PATH,'project.config.json'),config=fs.readFileSync(cfg);fs.writeFileSync(cfg,'{}');check(()=>assert.throws(()=>helper.preparedSource(env.COMMUNITY_MINI_PROJECT_PATH)));fs.writeFileSync(cfg,config);
 assert.notEqual(control,helper.SOURCE);const out=env.COMMUNITY_PREVIEW_OUTPUT,proofPath=path.join(out,'backend-readiness.json'),proof=fs.readFileSync(proofPath);const binding=JSON.parse(proof);assert.equal(binding.frontend_source_sha,helper.SOURCE);assert.equal(binding.backend_source_sha,helper.SOURCE);assert.equal(binding.compatibility,'EXACT_SOURCE_MATCH');for(const [field,value] of Object.entries({baseUrl:'https://uk.wenwenwenyiyiyi.work/community-preview',frontend_source_sha:control,backend_source_sha:control,compatibility:'FRONTEND_ONLY_PINNED_BACKEND'})){const bad=JSON.parse(proof);bad[field]=value;fs.writeFileSync(proofPath,JSON.stringify(bad));await assert.rejects(()=>helper.preview(env));checks++;}fs.writeFileSync(proofPath,proof);
 const keyModule=require.resolve('./scripts/community_mini_key.cjs'); // Use generated throwaway test key, never credential.
 const crypto=require('node:crypto');env.WECHAT_MINIPROGRAM_PRIVATE_KEY=crypto.generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}}).privateKey;env.WECHAT_MINIPROGRAM_APPID=helper.APPID;
 const moduleDir=path.join(env.COMMUNITY_MINI_CI_MODULE_ROOT,'node_modules/miniprogram-ci');fs.mkdirSync(moduleDir,{recursive:true});
 fs.writeFileSync(path.join(moduleDir,'index.js'),`const fs=require('node:fs');module.exports={Project:class {constructor(x){if(x.appid!=='wx1d5f8873eaea5392')throw Error('badappid');}},getCompiledResult:async()=>Object.fromEntries(['pages/merchant-join/index.js','merchant-fields-data.js','merchant-official-areas-data.js','merchant-official-industries-data.js','merchant-platform-reference-data.js','submission-diagnostic.js'].map(n=>[n,'module.exports={}'])),preview:async x=>{if(x.searchQuery!=='scene=owner-test-354d1fac'||x.pagePath!=='pages/home/index')throw Error('badentry');fs.writeFileSync(x.qrcodeOutputDest,'OFFLINE_SYNTHETIC_NOT_A_QR');},upload:async()=>{throw Error('UPLOAD_MUST_NEVER_BE_CALLED');}};`);
 // A missing compiled diagnostic is rejected before the preview SDK can run.
 const sdk=require(moduleDir),compile=sdk.getCompiledResult,originalPreview=sdk.preview;let previewCalls=0;
 sdk.preview=async value=>{previewCalls++;return originalPreview(value);};
 sdk.getCompiledResult=async value=>{const result=await compile(value);delete result['submission-diagnostic.js'];return result;};
 const missingOutput=path.join(tmp,'missing-diagnostic');fs.mkdirSync(missingOutput);fs.writeFileSync(path.join(missingOutput,'backend-readiness.json'),proof);
 await assert.rejects(()=>helper.preview({...env,COMMUNITY_PREVIEW_OUTPUT:missingOutput}),/COMPILED_RUNTIME_INVALID/);checks++;
 check(()=>assert.equal(previewCalls,0));check(()=>assert(!fs.existsSync(path.join(missingOutput,'preview.png'))));
 check(()=>assert.equal(JSON.parse(fs.readFileSync(path.join(missingOutput,'receipt.json'))).status,'COMPILED_RUNTIME_INVALID'));
 sdk.getCompiledResult=compile;
 await helper.preview(env);checks++;check(()=>assert.equal(previewCalls,1));const receipt=JSON.parse(fs.readFileSync(path.join(out,'receipt.json')));
 check(()=>assert.equal(receipt.status,'ISOLATED_TEST_PREVIEW_GENERATED'));check(()=>assert.equal(receipt.head,control));check(()=>assert.equal(receipt.frontend_source_sha,helper.SOURCE));check(()=>assert.equal(receipt.backend_source_sha,helper.SOURCE));check(()=>assert.equal(receipt.compatibility,'EXACT_SOURCE_MATCH'));check(()=>assert.equal(receipt.development_upload,false));check(()=>assert.equal(receipt.public_release,false));check(()=>assert.equal(receipt.login_verified,false));check(()=>assert.equal(receipt.scene,helper.SCENE));
 await assert.rejects(()=>helper.preview(env));checks++;
 console.log('OFFLINE_PREVIEW_BOUNDARY_CHECKS='+checks);
})().finally(()=>fs.rmSync(tmp,{recursive:true,force:true})).catch(e=>{console.error(e);process.exitCode=1;});
'''
        # Positive fixture uses this exact reviewed frontend; stale pins are rejected above.
        with tempfile.TemporaryDirectory(prefix='mini354-current-') as directory:
            frozen=pathlib.Path(directory)
            shutil.copytree(ROOT/'clients/community-mini',frozen/'clients/community-mini')
            for name in ('scripts/community_mini_isolated_preview_354.cjs','scripts/community_mini_key.cjs','deploy/community-preview/endpoint.cjs','deploy/community-preview/endpoint-profiles.json'):
                target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            script='const CURRENT_ROOT='+json.dumps(str(ROOT))+';\n'+script
            result=subprocess.run(['node','-e',script],cwd=frozen,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('OFFLINE_PREVIEW_BOUNDARY_CHECKS=',result.stdout)

    def test_workflow_preserves_production_route(self):
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        job=workflow.split('  mini-isolated-test-preview-354:',1)[1]
        self.assertIn('needs: [test, mini-sdk]',job)
        job_env=job.split('    env:',1)[1].split('    steps:',1)[0]
        self.assertNotIn('runner.',job_env)
        self.assertEqual(job_env.strip(),'COMMUNITY_MINI_OPERATION: preview')
        self.assertIn("printf 'COMMUNITY_MINI_PROJECT_PATH=%s/community-mini-isolated-354-%s-%s\\n'",job)
        self.assertIn("printf 'COMMUNITY_PREVIEW_OUTPUT=%s/community-mini-isolated-354-receipt-%s-%s\\n'",job)
        self.assertIn("printf 'COMMUNITY_MINI_CI_MODULE_ROOT=%s/community-mini-ci\\n'",job)
        self.assertIn('xuanjun-domestic-ops',job)
        self.assertIn('community_mini_isolated_preview_354.cjs prepare',job)
        self.assertIn('community_mini_isolated_preview_354.cjs preview',job)
        self.assertLess(job.index('cjs prepare'),job.index('WECHAT_MINIPROGRAM_PRIVATE_KEY:'))
        self.assertNotIn('cjs upload',job)
        self.assertNotIn('community-preview/endpoint-profiles.json\'',job.split('steps:',1)[0])
        original=workflow.split('  mini-preview:',1)[1].split('  mini-isolated-test-preview-354:',1)[0]
        self.assertNotIn('[mini-test-preview-354]',original)

    def test_real_prepared_home_login_and_read_transport(self):
        script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const helper=require('./scripts/community_mini_isolated_preview_354.cjs');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'real-home-offline-'));
const source=path.resolve('clients/community-mini');fs.cpSync(source,root,{recursive:true});
const sessionPath=path.join(root,'session.js'),raw=fs.readFileSync(sessionPath,'utf8');
const appPath=path.join(root,'app.js');fs.writeFileSync(appPath,fs.readFileSync(appPath,'utf8').replace("baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false","baseUrl: '"+helper.BASE+"', token: '', mode: 'WECHAT_LOGIN', payments: false, commerce: true, scene: '"+helper.SCENE+"'"));
function reset(){for(const k of Object.keys(require.cache))if(k.startsWith(root+path.sep))delete require.cache[k];}
async function home(failure){
 reset();let app,page,logins=0,requests=[];
 global.App=x=>app=x;require(appPath);global.getApp=()=>app;global.Page=x=>page=x;global.getCurrentPages=()=>[page];
 global.wx={getStorageSync:()=>false,login:o=>{logins++;o.success({code:'OFFLINE_SYNTHETIC_CODE'});},request:o=>{requests.push(o);if(failure){o.fail({errMsg:failure});return;}if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:'S'.repeat(40),expires_at:Math.floor(Date.now()/1000)+3600}}});else o.success({statusCode:200,data:{payment_enabled:false,result:{synthetic_only:true}}});}};
 require(path.join(root,'pages/home/index.js'));page.data={...page.data};page.setData=v=>Object.assign(page.data,v);
 await page.onLoad({scene:helper.SCENE});return {app,page,logins,requests};
}
(async()=>{
 const baseline=await home();assert.equal(baseline.logins,0);assert.equal(baseline.requests.length,0);assert.equal(baseline.page.data.authenticated,false);
 fs.writeFileSync(sessionPath,helper.derivedSession(raw));
 const good=await home();assert.equal(good.logins,1);assert.equal(good.requests.length,1);assert.equal(good.requests[0].url,helper.BASE+'/mini/login');assert.deepEqual(good.requests[0].data,{code:'OFFLINE_SYNTHETIC_CODE'});assert.equal(good.page.scene,helper.SCENE);assert.equal(good.app.globalData.scene,helper.SCENE);assert.equal(good.page.data.authenticated,true);assert.equal(good.page.data.pending,false);
 await good.page.session.merchant(helper.SCENE,'onboarding',{operation:'mine'});assert.equal(good.requests[1].url,helper.BASE+'/mini/merchant');assert.equal(good.requests[1].header['X-Community-Scene'],helper.SCENE);
 await good.page.session.commerce(helper.SCENE,'profile_read',{});assert.equal(good.requests[2].url,helper.BASE+'/mini/api');assert.equal(good.requests[2].data.scene,helper.SCENE);
 assert(good.requests.every(x=>x.url.startsWith(helper.BASE+'/mini/')));
 const api=require(sessionPath);for(const base of [helper.BASE+'-evil',helper.BASE+'/extra','https://uk.wenwenwenyiyiyi.work/community-preview','https://evil.invalid/community-test-354d1fac'])assert.throws(()=>api.createSession({},base),/TRUSTED_BACKEND_REQUIRED/);
 for(const [reason,label] of [['request:fail url not in domain list','NET_DOMAIN'],['request:fail certificate','NET_TLS'],['request:fail timeout','NET_TIMEOUT'],['request:fail connection lost','暂时无法连接服务']]){
  const bad=await home(reason);assert.equal(bad.logins,1);assert.equal(bad.requests.length,1);assert.equal(bad.page.data.authenticated,false);assert.equal(bad.page.data.pending,false);assert(bad.page.data.status.includes(label),bad.page.data.status);
 }
 // Both derived-file tampering and an additional trust condition fail hash verification.
 const patched=fs.readFileSync(sessionPath,'utf8');for(const bad of [raw,patched+'\n// changed',patched.replace(helper.BASE,helper.BASE+'-evil')]){fs.writeFileSync(sessionPath,bad);assert.throws(()=>helper.sessionBinding(root));}fs.writeFileSync(sessionPath,patched);
 const binding=helper.sessionBinding(root);assert.equal(binding.source_sha256,helper.HASHES['session.js']);assert.notEqual(binding.source_sha256,binding.derived_sha256);assert.equal(binding.trusted_path,helper.BASE);
 assert.equal(fs.readFileSync(path.join(source,'session.js'),'utf8'),raw);
 console.log('REAL_HOME_LOGIN_CHAIN_AND_FAILURES_PASS_OFFLINE');
})().finally(()=>{reset();fs.rmSync(root,{recursive:true,force:true});}).catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('REAL_HOME_LOGIN_CHAIN_AND_FAILURES_PASS_OFFLINE',result.stdout)

if __name__=='__main__':unittest.main()
