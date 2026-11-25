// Actual Page/session/original HTTP/SQLite. Only Aliyun exchange and image are synthetic.
'use strict';
const fs=require('fs'),vm=require('vm'),path=require('path'),http=require('http'),assert=require('assert/strict');
const root=process.cwd()+'/clients/community-mini',session=require(root+'/session'),auth=require(root+'/customer-auth'),form=require(root+'/merchant-form');
const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64');
const app={globalData:{baseUrl:process.env.COMMUNITY_TEST_ORIGIN,mode:'WECHAT_LOGIN',payments:false,commerce:false,scene:''}};
let page,cloudCalls=0,signCalls=0;const trace=[];
const wx={getAccountInfoSync:()=>({miniProgram:{appId:'wx1d5f8873eaea5392'}}),login:o=>o.success({code:'synthetic-bank-direct-code'}),
 chooseMedia:o=>o.success({tempFiles:[{tempFilePath:'memory://synthetic-bank.png',size:image.length}]}),
 base64ToArrayBuffer:s=>{const b=Buffer.from(s,'base64');return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);},
 getFileSystemManager:()=>({stat:o=>o.success({stats:{size:image.length}}),readFile:o=>o.success({data:image.toString('base64')})}),
 request(o){if(o.url==='https://ocr-api.cn-hangzhou.aliyuncs.com/'){
  cloudCalls++;assert.equal(o.header['x-acs-action'],'RecognizeBankCard');assert.deepEqual(Buffer.from(o.data),image);
  process.nextTick(()=>o.success({statusCode:200,data:{RequestId:'SYNTHETIC_ONLY',Data:JSON.stringify({data:{cardNumber:'0000000000000000',bankName:'中国银行'}})}}));return;
 }
 assert.ok(o.url.startsWith(app.globalData.baseUrl+'/mini/'),'no other external origin allowed');
 const child=o.data.params?.operation;trace.push(child||o.data.operation||'login');if(child==='direct_ocr_sign')signCalls++;
 const raw=JSON.stringify(o.data),q=http.request(o.url,{method:o.method,headers:{...o.header,'Content-Length':Buffer.byteLength(raw)}},r=>{let body='';r.on('data',x=>body+=x);r.on('end',()=>{try{o.success({statusCode:r.statusCode,data:JSON.parse(body)});}catch(_){o.fail({errMsg:'synthetic reply parse failed'});}});});q.on('error',()=>o.fail({errMsg:'synthetic local HTTP failed'}));q.end(raw);
 }};
vm.runInNewContext(fs.readFileSync(root+'/pages/merchant-join/index.js','utf8'),{Page:p=>page=p,wx,ArrayBuffer,Uint8Array,getApp:()=>app,getCurrentPages:()=>[],require:p=>p==='../../session'?session:p==='../../customer-auth'?auth:require(path.resolve(root+'/pages/merchant-join',p)),performance,Date});
page={...page,data:structuredClone(page.data),setData(p,cb){Object.assign(this.data,p);cb?.();}};
(async()=>{await page.onLoad({});assert.equal(page.data.ready,true,page.data.status);const application=page.data.application.application;page.data.step=2;page.refresh();
await page.upload({currentTarget:{dataset:{kind:'bank_card'}}});assert.equal(signCalls,1);assert.equal(cloudCalls,1);assert.ok(page.data.application.materials.bank_card);assert.ok(page.directOcrHints.bank_card?.active());
assert.equal(form.get(page.profile,'bank_account_info.account_number'),undefined);let before=await page.request('wechat_read',{application});assert.equal(before.profile.bank_account_info.account_number,undefined);
assert.ok(page.acceptDisplayedDirectOcr()>0);await page.saveDraft();const after=await page.request('wechat_read',{application});assert.equal(after.profile.bank_account_info.account_number,'0000000000000000');assert.equal(after.profile.bank_account_info.account_bank,'中国银行');assert.ok(after.version>before.version);assert.equal(trace.includes('wechat_submit_review'),false);assert.equal(trace.includes('wechat_apply'),false);page.onUnload();
process.stdout.write(JSON.stringify({bank_direct:true,cloud_calls:cloudCalls,signature_calls:signCalls,photo_saved:true,fields_unchanged_before_human:true,human_save_readback:true,provider:'SYNTHETIC_NO_EXTERNAL_NETWORK',formal_submissions:0}));})().catch(e=>{console.error(e);process.exitCode=1;});
