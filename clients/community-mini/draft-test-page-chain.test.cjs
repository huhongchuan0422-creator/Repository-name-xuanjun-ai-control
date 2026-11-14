'use strict';
// Merged actual page/session/driver; only the
// wx platform/server boundary is synthetic. Not a real-account acceptance run.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=__dirname;
const {createDraftTestDriver}=require(root+'/draft-test-driver');
const form=require(root+'/merchant-form');
async function fixture(options={}){
 const trace=[];
 const app={globalData:{baseUrl:'https://example.com',mode:'WECHAT_LOGIN'}};
 let draft={application:'synthetic_draft',revision:options.firstDraft?0:1,fields:{store_name:'',address:''},entity_type:'ENTERPRISE',identity_type:'IDENTIFICATION_TYPE_IDCARD',status:'DRAFT',materials:{},required_materials:['business_license'],declarations:{scene:'mini',ubos:0},sales_scenes_type:['SALES_SCENES_MINI_PROGRAM'],category:'GENERAL',redemption_percent:0,opening_state:'NOT_OPENED',wechat_submerchant_state:'NOT_SUBMITTED',split_participation:false,requested_split_bps:0};
 let record={profile:{},version:options.firstDraft?0:1,state:'DRAFT'},job=null,confirmation=0;
 const values={company_name:'Synthetic Company',credit_code:'SYNTHETIC_CREDIT',legal_representative:'Synthetic Owner',registered_address:'北京市东城区合成地址1号'};
 const clone=x=>structuredClone(x),reply=(o,result)=>o.success({statusCode:200,data:{payment_enabled:false,result:clone(result)}});
 const payload=()=>({...(options.failure||{}),job_id:'synthetic_job',document_type:'business_license',application_revision:String(draft.revision),provider_version:record.version,status:options.failure?'failed':confirmation?'confirmed':'needs_review',confirmation_revision:confirmation,...(confirmation?{confirmed_fields:values}:{}),fields:options.failure?{}:Object.fromEntries(Object.entries(values).map(([k,v])=>[k,{value:v}]))});
 const wx={getAccountInfoSync:()=>({miniProgram:{appId:'wx1d5f8873eaea5392'}}),
  login:o=>{trace.push('login');o.success({code:'SYNTHETIC_CODE'});},
  chooseMedia:o=>o.success({tempFiles:[{tempFilePath:'/synthetic/image'}]}),
  getFileSystemManager:()=>({stat:o=>o.success({stats:{size:3}}),readFile:o=>o.success({data:'YWJj'})}),
  request(o){if(o.url.endsWith('/mini/login'))return reply(o,{session_token:'s'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false});
   const p=o.data.params,action=o.data.operation==='ocr'?'ocr.'+p.action:p.operation;trace.push(action);
   if(action==='catalog')return reply(o,{materials:[{id:'business_license',name:'营业执照'}]});
   if(action==='mine')return reply(o,{applications:options.firstDraft?[]:[draft]});
   if(action==='read')return reply(o,draft);
   if(action==='wechat_read')return reply(o,record);
   if(action==='save'){const v=p.params;draft={...draft,...v,application:'synthetic_draft',revision:draft.revision+1};if(options.dropPlatformField)draft.fields={};return reply(o,draft);}
   if(action==='wechat_save'){const v=p.params;if(options.saveUnknown){o.fail({errMsg:'request:fail timeout'});return;}
     assert.equal(v.expected_version,record.version);record={...record,profile:clone(v.profile),version:record.version+1};if(options.dropWechatField)record.profile={};return reply(o,record);}
   if(action==='upload'){draft.revision++;draft.materials.business_license={uploaded:true,review:'PENDING',expires_at:null,object_id:'o_'+'a'.repeat(32),sha256:'b'.repeat(64)};
     if(options.uploadUnknown){o.fail({errMsg:'request:fail timeout'});return;}return reply(o,draft);}
   if(action==='ocr.submit'){job=payload();return reply(o,{result:{job_id:'synthetic_job'}});}
   if(action==='ocr.read')return reply(o,{result:payload()});
   if(action==='ocr.confirm'){confirmation=p.revision;return reply(o,{result:{job_id:'synthetic_job',status:'confirmed',recorded:true,revision:p.revision,application_revision:p.application_revision,provider_version:p.provider_version}});}
   if(action==='ocr.recover_view'){o.success({statusCode:403,data:{error:'OCR_UNAVAILABLE',ocr_diagnostic:{version:1,diagnostic_id:'c'.repeat(32),stage:'RESULT_READ',reason:'MATERIAL_JOB_NOT_FOUND',retryable:false,request_retained:false}}});return;}
   if(action==='material_preview'){o.success({statusCode:400,data:{error:'SYNTHETIC_PREVIEW_NOT_RENDERED'}});return;}
   throw Error('Unexpected test action '+action);
  },navigateTo(){},redirectTo(){}};
 let definition;vm.runInNewContext(fs.readFileSync(root+'/pages/merchant-join/index.js','utf8'),{
   Page:p=>definition=p,wx,getApp:()=>app,require:p=>p.startsWith('.')?require(path.resolve(root+'/pages/merchant-join',p)):require(p),encodeURIComponent
 });
 const page={...definition,data:clone(definition.data),setData(p,callback){Object.assign(this.data,p);if(callback)callback();}};
 await page.onLoad({});
 assert.equal(page.data.ready,true,page.data.status);
 let appEntry;vm.runInNewContext(fs.readFileSync(root+'/app.js','utf8'),{App:x=>appEntry=x,wx,require:p=>require(path.resolve(root,p))});
 const driver=appEntry.createDraftTestDriver.call(app,page);
 return {page,driver,trace,get draft(){return draft;},get record(){return record;},values};
}

test('original page upload automatic OCR confirmation writeback save and readback',async()=>{
 const f=await fixture();try{
  assert.equal((await f.driver.connect()).session_reused,true);
  await f.driver.upload('business_license');
  assert.equal(f.page.data.ocrRows.length,4,f.page.data.ocrStatus);
  assert.equal(f.trace.filter(x=>x==='ocr.submit').length,1);
  const saved=await f.driver.confirmAndSave();
  assert.equal(saved.readback_available,true,JSON.stringify({saved,status:f.page.data.status,ocr:f.page.data.ocrStatus,trace:f.trace}));
  assert.equal(form.get(f.record.profile,'subject_info.business_license_info.merchant_name'),f.values.company_name);
  assert.equal((await f.driver.verifySaved()).outcome,'READBACK_MATCHED');
  assert.equal(f.trace.filter(x=>x==='login').length,1);
  assert(!f.trace.some(x=>['wechat_apply','wechat_submit_review','submit','payment'].includes(x)));
 }finally{f.page.onUnload();}
});
test('original page unknown upload remains unknown and does not start OCR',async()=>{
 const f=await fixture({uploadUnknown:true});try{
  await f.driver.connect();const r=await f.driver.upload('business_license');
  assert.equal(r.outcome,'OBSERVED_ONLY');assert.equal(f.page.data.uploadFeedback.phase,'unknown');
  assert(!f.trace.includes('ocr.submit'));assert(!f.trace.includes('ocr.confirm'));
 }finally{f.page.onUnload();}
});
test('original page caught save timeout cannot become verified saved draft',async()=>{
 const f=await fixture({saveUnknown:true});try{
  await f.driver.connect();await f.driver.upload('business_license');const r=await f.driver.confirmAndSave();
  assert.equal(r.readback_available,false);assert.equal((await f.driver.verifySaved()).reason,'NO_SAVED_EXPECTATION');
  assert.equal(f.trace.filter(x=>x==='wechat_save').length,1);
 }finally{f.page.onUnload();}
});

test('original first applicant draft save remains supported',async()=>{
 const f=await fixture({firstDraft:true});try{
  assert.equal(f.page.data.application,null);await f.driver.connect();
  const r=await f.driver.save();assert.equal(r.readback_available,true,JSON.stringify(r));
  assert.equal((await f.driver.verifySaved()).outcome,'READBACK_MATCHED');
 }finally{f.page.onUnload();}
});
test('provider dropping fields during original reload cannot fake a successful readback',async()=>{
 const f=await fixture({dropWechatField:true});try{
  await f.driver.connect();await f.driver.upload('business_license');const r=await f.driver.confirmAndSave();
  assert.equal(r.readback_available,true);assert.deepEqual(f.page.profile,{});
  assert.equal((await f.driver.verifySaved()).reason,'SAVED_WRITE_MISMATCH');
 }finally{f.page.onUnload();}
});
test('platform fields dropped during original reload are detected too',async()=>{
 const f=await fixture({dropPlatformField:true});try{
  await f.driver.connect();await f.driver.upload('business_license');await f.driver.confirmAndSave();
  assert.equal((await f.driver.verifySaved()).reason,'SAVED_WRITE_MISMATCH');
 }finally{f.page.onUnload();}
});

const observations=[];
for(const [code,outcome] of [['ALIYUN_CALL_OUTCOME_UNKNOWN','unknown'],['IMAGE_DECODE_FAILED','not_sent'],['ALIYUN_HTTP_ERROR','response_received']])test('combined app entry and original driver preserve failed OCR '+code,async()=>{
 const f=await fixture({failure:{error_code:code,failure_outcome:outcome,provider_message:'PRIVATE_SENTINEL'}});try{
  assert.equal((await f.driver.connect()).session_reused,true);
  const observed=await f.driver.upload('business_license');
  assert.equal(observed.outcome,'OBSERVED_ONLY');assert.equal(f.page.data.ocrProgressState,'failed');
  assert.ok(f.page.data.ocrStatus.includes(code));assert.ok(!f.page.data.ocrStatus.includes('PRIVATE_SENTINEL'));
  assert.equal(f.page.data.ocrRows.length,0);assert.equal(f.page.ocrPolling,false);assert.equal(f.page.data.ocrDiagnostic,null);
  const before=f.trace.slice();const saved=await f.driver.confirmAndSave();
  assert.equal(saved.readback_available,false);assert.deepEqual(f.trace,before);
  assert.equal((await f.driver.verifySaved()).reason,'NO_SAVED_EXPECTATION');
  await f.driver.readOcr();assert.equal(f.trace.filter(x=>x==='ocr.submit').length,1);
  assert.ok(!f.trace.includes('ocr.confirm'));assert.ok(!f.trace.some(x=>['wechat_apply','wechat_submit_review','submit','payment'].includes(x)));
  const report=JSON.stringify(f.driver.report());assert.ok(!report.includes('PRIVATE_SENTINEL'));assert.ok(!report.includes('SYNTHETIC_CODE'));assert.ok(!report.includes('synthetic_draft'));
  observations.push({code,outcome,trace:f.trace,report:f.driver.report()});
 }finally{f.page.onUnload();}
});
