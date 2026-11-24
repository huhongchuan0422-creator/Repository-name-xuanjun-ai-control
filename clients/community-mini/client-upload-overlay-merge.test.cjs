'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm');
const evidence=process.env.CLIENT_OVERLAY_MERGE_EVIDENCE_ROOT||path.resolve(__dirname,'../../../../community-mini-three-fixes-20261125/client-overlay-merge');
const read=(group,name)=>fs.readFileSync(path.join(evidence,group,name));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const JS_PATH='pages/merchant-join/index.js',CSS_PATH='pages/checkout/index.wxss';
const source=fs.readFileSync(path.join(__dirname,JS_PATH),'utf8');
function fixture({fail=false}={}){
 let definition,release,entered;const gate=new Promise(r=>release=r),seen=new Promise(r=>entered=r),calls=[];
 const session={ensureLogin:async()=>{},isAuthenticated:()=>true,getGeneration:()=>1};
 vm.runInNewContext(source,{Page:p=>definition=p,wx:{},getApp:()=>({globalData:{}}),
  require(p){if(p==='../../session')return {getSharedSession:()=>session,customerError:()=> 'synthetic read failure'};
   if(p==='../../customer-auth')return {current:()=>1};if(p==='../../chain-telemetry')return require('./chain-telemetry');
   if(p==='../../merchant-form')return require('./merchant-form');if(p==='../../merchant-submit')return {};
   if(p==='../../merchant-official-fields')return require('./merchant-official-fields');
   if(p==='../../merchant-platform-reference-data')return require('./merchant-platform-reference-data');
   if(p==='./direct-ocr'||p==='./direct-proof')return {};
   throw Error('unexpected dependency '+p);}});
 const p={...definition,data:structuredClone(definition.data),setData(v){Object.assign(this.data,v);}};
 p.current=()=>true;p.scene='synthetic';p.verifyPlatformAppid=()=>{};p.refresh=()=>{};
 p.request=async op=>{calls.push(op);if(op==='catalog')return {materials:[]};if(op==='mine')return {applications:[{application:'approved-original',status:'APPROVED',revision:2},{application:'draft-cursor',status:'DRAFT',revision:1}],current_cursor:{application:'draft-cursor'}};throw Error('unexpected operation');};
 p.load=async id=>{calls.push(['load',id]);entered();await gate;if(fail)throw Error('synthetic');p.loadedDisplayApplication=id;p.setData({application:{application:id},step:3,wechatState:'APPLYMENT_STATE_TO_BE_SIGNED'});};
 return {page:p,calls,seen,release,allowRetry(){fail=false;}};
}

test('merge bases are exact two receipt-pinned upload bytes, not current working source',()=>{
 assert.equal(sha(read('upload-base',JS_PATH)),'6f1e1eed443e23c27a700402318f71064c318e36d79990d6e705e3d19628e531');
 assert.equal(sha(read('upload-base',CSS_PATH)),'f63346034db90edbe61ac2cafd6ae4c9a4697d89af2fe39f3529f6af09979e99');
 const proof=JSON.parse(fs.readFileSync(path.join(evidence,'UPLOAD-SOURCE-PROVENANCE.json'),'utf8'));
 assert.equal(proof.control_commit,'9fa4e5feb6ee42cc7b841bc8164c4120f80b78ba');
 assert.equal(proof.manifest_sha256,'a571d0a7d81c67ef5be7e00d1e464828714d84662304e3c75ecb13349a4ca725');assert.equal(proof.exact_receipt_matches,true);
});

test('merged JS differs from approved 8a3 only by preserving original uploaded selection overlay',()=>{
 const old=read('reviewed-8a3',JS_PATH).toString();
 const clause='.filter(a=>!result.current_cursor||a.application===result.current_cursor.application)';
 assert.equal(old.split(clause).length,2);assert.equal(source,old.replace(clause,''));
 assert.match(source,/ready:!selected,readState:selected\?'LOADING':'READY'/);
 assert.match(source,/recognizeCurrentDocument\(kind,options=\{\}\)\{\n  if\(kind==='bank_card'\)return/);
});

test('merged CSS preserves every uploaded style byte and appends only approved symbol rule',()=>{
 const uploaded=read('upload-base',CSS_PATH),review=read('reviewed-8a3',CSS_PATH).toString();
 const rule=review.match(/\.storefront-symbol\{[^}]+\}/)[0];
 const actual=fs.readFileSync(path.join(__dirname,CSS_PATH));
 assert.deepEqual(actual,Buffer.concat([uploaded,Buffer.from('\n'+rule+'\n')]));
 assert.equal((actual.toString().match(/\.storefront-symbol\{/g)||[]).length,1);
});

test('original uploaded selection overlay and new neutral-loading gate coexist for pending signing',async()=>{
 const f=fixture(),opening=f.page.connectApplicant({automatic:true});await f.seen;
 assert.deepEqual(f.calls.find(x=>Array.isArray(x)),['load','approved-original']);
 assert.equal(f.page.data.ready,false);assert.equal(f.page.data.readState,'LOADING');
 assert.equal(f.page.data.canEditPlatform,false);f.release();await opening;
 assert.equal(f.page.data.ready,true);assert.equal(f.page.data.step,3);
 assert.equal(f.page.data.application.application,'approved-original');
 assert.equal(f.page.data.wechatState,'APPLYMENT_STATE_TO_BE_SIGNED');
 assert.ok(!f.calls.some(x=>['save','wechat_submit_review','wechat_apply'].includes(x)));
});

test('merged selection path keeps read failure retry without changing or creating an application',async()=>{
 const f=fixture({fail:true}),opening=f.page.connectApplicant({automatic:true});await f.seen;f.release();await opening;
 assert.equal(f.page.data.ready,false);assert.equal(f.page.data.readState,'FAILED');assert.equal(f.page.data.application,null);
 f.allowRetry();await f.page.retryApplicantRead();assert.equal(f.page.data.ready,true);assert.equal(f.page.data.step,3);
 assert.deepEqual(f.calls.filter(x=>Array.isArray(x)),[['load','approved-original'],['load','approved-original']]);
 assert.ok(!f.calls.some(x=>['save','wechat_submit_review','wechat_apply'].includes(x)));
});
