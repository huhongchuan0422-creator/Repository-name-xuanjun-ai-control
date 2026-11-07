"""Offline contract tests. No provider call, credential, live login or real QR."""
import pathlib, subprocess, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class IsolatedPreview354(unittest.TestCase):
    def test_fixed_source_and_negative_boundaries(self):
        script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),events=require('node:events');
const helper=require('./scripts/community_mini_isolated_preview_354.cjs');
const {sourceManifest}=require('./deploy/community-preview/endpoint.cjs');
let checks=0;function check(fn){fn();checks++;}
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'preview354-offline-'));
const eventPath=path.join(tmp,'event.json'),control='a'.repeat(40);
fs.writeFileSync(eventPath,JSON.stringify({after:control,head_commit:{message:'bind [mini-test-preview-354]'}}));
const env={GITHUB_EVENT_NAME:'push',GITHUB_REPOSITORY:'huhongchuan0422-creator/Repository-name-xuanjun-ai-control',GITHUB_REF:'refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017',GITHUB_SHA:control,GITHUB_EVENT_PATH:eventPath,COMMUNITY_MINI_OPERATION:'preview',COMMUNITY_MINI_PROJECT_PATH:path.join(tmp,'project'),COMMUNITY_PREVIEW_OUTPUT:path.join(tmp,'receipts'),COMMUNITY_MINI_CI_MODULE_ROOT:path.join(tmp,'sdk')};
const ready={status:'READY',scope:'PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance:false,runtime_source_sha:helper.SOURCE,version_source:'IMAGE_BUILD_STAMP',observed_at:1000};
check(()=>assert.equal(helper.context(env),control));
for(const [key,value] of Object.entries({GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'wrong/repo',GITHUB_REF:'refs/heads/main',GITHUB_SHA:'invalid',COMMUNITY_MINI_OPERATION:'upload'}))check(()=>assert.throws(()=>helper.context({...env,[key]:value})));
for(const message of ['[mini-upload]','[mini-preview]','[mini-test-preview-354] [mini-upload]','[mini-test-preview-354] [mini-preview]']){fs.writeFileSync(eventPath,JSON.stringify({after:control,head_commit:{message}}));check(()=>assert.throws(()=>helper.context(env)));}
fs.writeFileSync(eventPath,JSON.stringify({after:control,head_commit:{message:'bind [mini-test-preview-354]'}}));
check(()=>assert.equal(helper.verifyHealth(ready,1000),ready));
for(const [key,value] of Object.entries({status:'NOT_READY',runtime_source_sha:'b'.repeat(40),version_source:'CALLER',production_acceptance:true,observed_at:0}))check(()=>assert.throws(()=>helper.verifyHealth({...ready,[key]:value},1000)));
check(()=>assert.throws(()=>helper.verifyHealth({...ready,observed_at:1031},1000)));
check(()=>assert.deepEqual(sourceManifest('./clients/community-mini'),Object.assign(Object.create(null),helper.HASHES)));
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
 const out=env.COMMUNITY_PREVIEW_OUTPUT,proofPath=path.join(out,'backend-readiness.json'),proof=fs.readFileSync(proofPath);const bad=JSON.parse(proof);bad.baseUrl='https://uk.wenwenwenyiyiyi.work/community-preview';fs.writeFileSync(proofPath,JSON.stringify(bad));await assert.rejects(()=>helper.preview(env));checks++;fs.writeFileSync(proofPath,proof);
 const keyModule=require.resolve('./scripts/community_mini_key.cjs'); // Use generated throwaway test key, never credential.
 const crypto=require('node:crypto');env.WECHAT_MINIPROGRAM_PRIVATE_KEY=crypto.generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}}).privateKey;env.WECHAT_MINIPROGRAM_APPID=helper.APPID;
 const moduleDir=path.join(env.COMMUNITY_MINI_CI_MODULE_ROOT,'node_modules/miniprogram-ci');fs.mkdirSync(moduleDir,{recursive:true});
 fs.writeFileSync(path.join(moduleDir,'index.js'),`const fs=require('node:fs');module.exports={Project:class {constructor(x){if(x.appid!=='wx1d5f8873eaea5392')throw Error('badappid');}},getCompiledResult:async()=>Object.fromEntries(['pages/merchant-join/index.js','merchant-fields-data.js','merchant-official-areas-data.js','merchant-official-industries-data.js','merchant-platform-reference-data.js'].map(n=>[n,'module.exports={}'])),preview:async x=>{if(x.searchQuery!=='scene=owner-test-354d1fac'||x.pagePath!=='pages/home/index')throw Error('badentry');fs.writeFileSync(x.qrcodeOutputDest,'OFFLINE_SYNTHETIC_NOT_A_QR');},upload:async()=>{throw Error('UPLOAD_MUST_NEVER_BE_CALLED');}};`);
 await helper.preview(env);checks++;const receipt=JSON.parse(fs.readFileSync(path.join(out,'receipt.json')));
 check(()=>assert.equal(receipt.status,'ISOLATED_TEST_PREVIEW_GENERATED'));check(()=>assert.equal(receipt.development_upload,false));check(()=>assert.equal(receipt.public_release,false));check(()=>assert.equal(receipt.login_verified,false));check(()=>assert.equal(receipt.scene,helper.SCENE));
 await assert.rejects(()=>helper.preview(env));checks++;
 console.log('OFFLINE_PREVIEW_BOUNDARY_CHECKS='+checks);
})().finally(()=>fs.rmSync(tmp,{recursive:true,force:true})).catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('OFFLINE_PREVIEW_BOUNDARY_CHECKS=',result.stdout)

    def test_workflow_preserves_production_route(self):
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        job=workflow.split('  mini-isolated-test-preview-354:',1)[1]
        self.assertIn('needs: [test, mini-sdk]',job)
        self.assertIn('xuanjun-domestic-ops',job)
        self.assertIn('community_mini_isolated_preview_354.cjs prepare',job)
        self.assertIn('community_mini_isolated_preview_354.cjs preview',job)
        self.assertLess(job.index('cjs prepare'),job.index('WECHAT_MINIPROGRAM_PRIVATE_KEY:'))
        self.assertNotIn('cjs upload',job)
        self.assertNotIn('community-preview/endpoint-profiles.json\'',job.split('steps:',1)[0])
        original=workflow.split('  mini-preview:',1)[1].split('  mini-isolated-test-preview-354:',1)[0]
        self.assertNotIn('[mini-test-preview-354]',original)

if __name__=='__main__':unittest.main()
