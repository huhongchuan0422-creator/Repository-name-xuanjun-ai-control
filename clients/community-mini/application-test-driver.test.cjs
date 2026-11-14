'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const root='./';
const {getSharedSession}=require(root+'session');
const {createDraftTestDriver}=require(root+'draft-test-driver');
function fixture(options={}) {
  let now=1000,loginCalls=0,loginExchanges=0,backendCalls=0,storageWrites=[],requests=[],alive=true;
  const store=new Map(),config={baseUrl:'https://example.com',mode:'WECHAT_LOGIN'};
  const remote={application:'synthetic_private_draft',revision:1},record={version:1,profile:{synthetic:'private_value'}};
  const wx={getStorageSync:key=>store.get(key),setStorageSync(key,value){storageWrites.push({key,value});store.set(key,value);},
    login(o){loginCalls++;const reply=()=>o.success({code:'SYNTHETIC_CODE_DO_NOT_EXPORT'});options.delayLogin?options.delayLogin(reply):reply();},
    request(o){requests.push(o.data);if(o.url.endsWith('/mini/login')){loginExchanges++;o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'S'.repeat(32),provider:'WECHAT_MINIPROGRAM',payment_enabled:false,expires_at:now+3600}}});return;}
      if(o.url.endsWith('/mini/logout')){o.success({statusCode:200,data:{payment_enabled:false,result:{}}});return;}
      backendCalls++;const params=o.data.params;
      if(options.denied){o.success({statusCode:403,data:{error:'NOT_YOURS'}});return;}
      if(params.operation==='save'){Object.assign(remote,params.params,{application:'synthetic_private_draft',revision:remote.revision+1});}
      if(params.operation==='wechat_save'){record.version++;record.profile=structuredClone(params.params.profile);}
      const result=['read','save'].includes(params.operation)?structuredClone(remote):structuredClone(record);
      o.success({statusCode:200,data:{payment_enabled:false,result}});
    }};
  const session=getSharedSession(wx,config,()=>now);
  const page={data:{ready:false,pending:false,dirty:false,ocrRows:[],application:null,catalog:[{id:'business_license'}]},session:null,scene:'',version:1,profile:structuredClone(record.profile),
    current:()=>alive,
    async connectApplicant(o){this.session=session;try{await session.ensureLogin(o);this.data.ready=true;this.data.application=structuredClone(remote);}catch(_){this.data.ready=false;}},
    request(operation,params){return session.merchant('','onboarding',{operation,params});},
    async upload(e){this.data.uploadFeedback={phase:'uploaded'};this.ocrPolling=true;this.lastUpload=e.currentTarget.dataset.kind;},
    async recognizeDocument(e){this.ocrPolling=true;this.lastRecognition=e.currentTarget.dataset.kind;},
    async readOcr(){this.ocrPolling=false;this.data.ocrRows=[{key:'synthetic',value:'SECRET_VALUE_NOT_FOR_REPORT'}];},
    async confirmAndSaveOcr(){this.data.ocrConfirmed=true;this.profile={synthetic:'accepted_private_value'};await this.save();},
    async save(){if(options.swallowedSave)return;const saved=await this.request('save',{application:this.data.application&&this.data.application.application,revision:this.data.application?this.data.application.revision:0});this.data.application=saved;const reply=await this.request('wechat_save',{application:saved.application,expected_version:this.version,profile:this.profile});this.version=reply.version;this.data.dirty=false;}
  };
  const driver=createDraftTestDriver({page,wx,config,now:()=>now});
  return {wx,config,page,session,driver,remote,record,options,store,requests,storageWrites,
    get loginCalls(){return loginCalls;},get loginExchanges(){return loginExchanges;},get backendCalls(){return backendCalls;},
    advance:seconds=>now+=seconds,close:()=>alive=false};
}

function applicationFixture(options={}) {
 const f=fixture(options);f.record.state='DRAFT';
 f.page.submitAllReview=async function(){
  if(['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(f.record.state))return this.request('wechat_status',{application:this.data.application.application});
  const r=await this.request('wechat_apply',{application:this.data.application.application,expected_version:this.version,application_revision:this.data.application.revision});
  await this.request('wechat_status',{application:this.data.application.application});return r;
 };
 f.page.refreshApplication=async function(){
  if(['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(f.record.state))await this.request('wechat_status',{application:this.data.application.application});
  await this.request('read',{application:this.data.application.application});await this.request('wechat_read',{application:this.data.application.application});
 };
 return f;
}
test('explicit submitReview calls only original page handler and observes original responses',async()=>{
 const f=applicationFixture();await f.driver.connect();f.record.state='SUBMITTED_TO_PROVIDER';f.record.provider_state='APPLYMENT_STATE_AUDITING';f.record.applyment_id=12345;
 // Stub is deliberately a new application handler; real UNKNOWN behavior is covered separately and by the original full chain.
 f.page.submitAllReview=async function(){await this.request('wechat_apply',{application:this.data.application.application});await this.request('wechat_status',{application:this.data.application.application});};
 const old=f.page.request,merchant=f.session.merchant;const r=await f.driver.submitReview();
 assert.equal(r.outcome,'PROVIDER_RESPONSE_OBSERVED');assert.equal(r.original_submit_calls,1);assert.equal(r.original_query_calls,1);
 assert.equal(r.progress.has_applyment_id,true);assert.equal(r.progress.provider_state,'APPLYMENT_STATE_AUDITING');
 assert.equal(r.real_provider_acceptance,'NOT_ESTABLISHED_BY_THIS_REPORT');assert.equal(f.page.request,old);assert.equal(f.session.merchant,merchant);
});
test('existing UNKNOWN page route is observed as query only without a new submit',async()=>{
 const f=applicationFixture();await f.driver.connect();f.record.state='SUBMISSION_UNKNOWN';const r=await f.driver.submitReview();
 assert.equal(r.original_submit_calls,0);assert.equal(r.original_query_calls,1);assert(!f.requests.some(x=>x.params?.operation==='wechat_apply'));
});
test('queryStatus calls original refresh and distinguishes local-only draft reads',async()=>{
 const f=applicationFixture();await f.driver.connect();const r=await f.driver.queryStatus();
 assert.equal(r.outcome,'ORIGINAL_READ_OBSERVED');assert.equal(r.original_submit_calls,0);assert.equal(r.original_query_calls,0);assert.equal(r.progress.review_state,'DRAFT');
});
test('fulfilled no-op or swallowed preflight is not a verified application',async()=>{
 const f=applicationFixture();await f.driver.connect();f.page.submitAllReview=async()=>{};const r=await f.driver.submitReview();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(r.original_submit_calls,0);
});
test('original caught server rejection exposes only validated fixed diagnostic',async()=>{
 const f=applicationFixture();await f.driver.connect();const wxRequest=f.wx.request;
 f.wx.request=o=>{if(o.data.params?.operation==='wechat_apply')return o.success({statusCode:503,data:{error:'SERVICE_UNAVAILABLE',submission_diagnostic:{operation:'wechat_apply',stage:'PROVIDER_POST',code:'PROVIDER_RESULT_UNKNOWN',correlation_id:'b'.repeat(32),timestamp:1000,status:'FAILED'},message:'SECRET_RAW_MESSAGE'}});return wxRequest(o);};
 f.page.submitAllReview=async function(){try{await this.request('wechat_apply',{application:this.data.application.application});}catch(_){};};
 const r=await f.driver.submitReview();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(r.operations[0].diagnostic.code,'PROVIDER_RESULT_UNKNOWN');assert.equal(r.original_submit_calls,1);assert(!JSON.stringify(r).includes('SECRET_RAW_MESSAGE'));
});
test('untrusted diagnostic and provider states never leak arbitrary fields',async()=>{
 const f=applicationFixture();await f.driver.connect();Object.assign(f.record,{state:'SECRET_STATE',provider_state:'SECRET_PROVIDER',applyment_id:'SECRET_ID',url:'SECRET_URL',profile:{value:'SECRET_PROFILE'}});
 const r=await f.driver.submitReview();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(r.progress,null);
 const text=JSON.stringify(f.driver.report());for(const secret of ['SECRET_STATE','SECRET_PROVIDER','SECRET_ID','SECRET_URL','SECRET_PROFILE','synthetic_private_draft'])assert(!text.includes(secret));assert.equal(f.driver.report().financial_or_review_submit_exposed,true);
});
test('page/session serialization covers submission and query without adding retries',async()=>{
 const f=applicationFixture();await f.driver.connect();let release;f.page.submitAllReview=()=>new Promise(resolve=>release=resolve);const pending=f.driver.submitReview();
 const other=createDraftTestDriver({page:f.page,wx:f.wx,config:f.config,now:()=>1000});assert.equal((await other.queryStatus()).outcome,'NOT_STARTED');release();await pending;
});
test('late application change cannot release observed result as verified',async()=>{
 const f=applicationFixture();await f.driver.connect();f.page.submitAllReview=async function(){await this.request('wechat_apply',{application:this.data.application.application});this.data.application={application:'other',revision:1};};
 assert.equal((await f.driver.submitReview()).reason,'DRAFT_CHANGED');
});
test('out-of-page shared session response cannot count as original page action',async()=>{
 const f=applicationFixture();await f.driver.connect();f.page.submitAllReview=()=>f.session.merchant('','onboarding',{operation:'wechat_apply',params:{application:f.page.data.application.application}});
 assert.equal((await f.driver.submitReview()).reason,'UNATTRIBUTED_APPLICATION_OBSERVATION');
});
test('wrong scene and wrong requested application contaminate only evidence, do not alter original call',async()=>{
 const f=applicationFixture();await f.driver.connect();f.page.submitAllReview=async function(){await this.request('wechat_apply',{application:'other'});};
 const r=await f.driver.submitReview();assert.equal(r.reason,'UNATTRIBUTED_APPLICATION_OBSERVATION');assert.equal(f.requests.at(-1).params.params.application,'other');
});
test('thrown original page error restores observers and exports no raw text',async()=>{
 const f=applicationFixture();await f.driver.connect();const p=f.page.request,m=f.session.merchant;f.page.submitAllReview=async()=>{throw Error('SECRET_THROW');};
 const r=await f.driver.submitReview();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(f.page.request,p);assert.equal(f.session.merchant,m);assert(!JSON.stringify(r).includes('SECRET_THROW'));
});
test('missing original submit or refresh method does not create direct API fallback',async()=>{
 const f=fixture();await f.driver.connect();const before=f.requests.length;assert.equal((await f.driver.submitReview()).reason,'ORIGINAL_METHOD_UNAVAILABLE');assert.equal((await f.driver.queryStatus()).reason,'ORIGINAL_METHOD_UNAVAILABLE');assert.equal(f.requests.length,before);
});

test('HTTP 200 empty or malformed records remain unverified after original page catches errors',async()=>{
 for(const value of [{},[],{version:1},{state:'DRAFT'},{version:true,state:'DRAFT'},{version:-1,state:'DRAFT'},'opaque']){
  const f=applicationFixture();await f.driver.connect();const request=f.wx.request;
  f.wx.request=o=>o.data.params?.operation==='wechat_apply'?o.success({statusCode:200,data:{payment_enabled:false,result:value}}):request(o);
  f.page.submitAllReview=async function(){try{await this.request('wechat_apply',{application:this.data.application.application});throw Error('ORIGINAL_PAGE_RECORD_ERROR');}catch(_){};};
  const r=await f.driver.submitReview();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(r.provider_response_observed,false);assert.equal(r.operations[0].response_observed,true);assert.equal(r.operations[0].response_valid,false);
 }
});
test('provider response followed by failed original readback cannot be a complete observed action',async()=>{
 const f=applicationFixture();await f.driver.connect();f.record.state='SUBMITTED_TO_PROVIDER';f.record.provider_state='APPLYMENT_STATE_AUDITING';const request=f.wx.request;
 f.wx.request=o=>o.data.params?.operation==='wechat_read'?o.success({statusCode:503,data:{error:'SERVICE_UNAVAILABLE'}}):request(o);
 f.page.refreshApplication=async function(){try{await this.request('wechat_status',{application:this.data.application.application});await this.request('wechat_read',{application:this.data.application.application});}catch(_){};};
 const r=await f.driver.queryStatus();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(r.provider_response_observed,true);assert.equal(r.original_query_calls,1);assert.equal(r.operations.at(-1).operation,'wechat_read');assert.equal(r.operations.at(-1).failed,true);
});

test('provider response followed by platform read failure or malformed readback is not complete',async()=>{
 for(const mode of ['reject','malformed']){
  const f=applicationFixture();await f.driver.connect();f.record.state='SUBMITTED_TO_PROVIDER';const request=f.wx.request;
  f.wx.request=o=>o.data.params?.operation==='read'?o.success(mode==='reject'?{statusCode:503,data:{error:'SERVICE_UNAVAILABLE'}}:{statusCode:200,data:{payment_enabled:false,result:{application:'OTHER_PRIVATE_APPLICATION',revision:1}}}):request(o);
  f.page.refreshApplication=async function(){try{await this.request('wechat_status',{application:this.data.application.application});await this.request('read',{application:this.data.application.application});}catch(_){};};
  const r=await f.driver.queryStatus();assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(r.provider_response_observed,true);assert.equal(r.original_query_calls,1);assert.equal(r.operations.at(-1).operation,'read');
  assert.equal(mode==='reject'?r.operations.at(-1).failed:r.operations.at(-1).response_valid,mode==='reject');assert(!JSON.stringify(r).includes('OTHER_PRIVATE_APPLICATION'));
 }
});

test('a final valid platform read does not erase the last observed provider progress',async()=>{
 const f=applicationFixture();await f.driver.connect();f.record.state='SUBMITTED_TO_PROVIDER';f.record.provider_state='APPLYMENT_STATE_AUDITING';
 f.page.submitAllReview=async function(){await this.request('wechat_status',{application:this.data.application.application});await this.request('read',{application:this.data.application.application});};
 const r=await f.driver.submitReview();assert.equal(r.outcome,'PROVIDER_RESPONSE_OBSERVED');assert.equal(r.progress.provider_state,'APPLYMENT_STATE_AUDITING');assert.equal(r.operations.at(-1).operation,'read');assert(!Object.hasOwn(r.operations.at(-1),'progress'));
});
