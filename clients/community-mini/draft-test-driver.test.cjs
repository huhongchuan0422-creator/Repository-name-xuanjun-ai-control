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
test('same-runtime connect uses original login once, then reuses session',async()=>{
  const f=fixture();const first=await f.driver.connect(),second=await f.driver.connect();
  assert.equal(first.outcome,'SESSION_AVAILABLE');assert.equal(first.session_reused,false);assert.equal(second.session_reused,true);
  assert.equal(f.loginCalls,1);assert.equal(f.loginExchanges,1);assert.deepEqual(f.storageWrites,[]);
});
test('probe verifies backend acceptance without exporting original draft',async()=>{
  const f=fixture();await f.driver.connect();const r=await f.driver.probe();
  assert.equal(r.outcome,'READ_OBSERVED');assert.equal(r.backend_session_accepted,true);assert.equal(f.backendCalls,2);
  assert(!JSON.stringify(r).includes(f.remote.application));
});
test('two drivers in same runtime share login and keep independent evidence',async()=>{
  const f=fixture();await f.driver.connect();const second=createDraftTestDriver({page:f.page,wx:f.wx,config:f.config,now:()=>1000});
  assert.equal((await second.connect()).session_reused,true);assert.equal(f.loginCalls,1);assert.equal(second.report().events.length,1);
});
test('original concurrent ensureLogin uses one wx.login code and exchange',async()=>{
  let release;const f=fixture({delayLogin:fn=>release=fn});
  const one=f.session.ensureLogin({automatic:true}),two=f.session.ensureLogin({automatic:true});
  assert.equal(one,two);release();await Promise.all([one,two]);assert.equal(f.loginCalls,1);assert.equal(f.loginExchanges,1);
});
test('duplicate test action is not replayed',async()=>{
  let release;const f=fixture({delayLogin:fn=>release=fn});const first=f.driver.connect();const second=await f.driver.connect();
  assert.equal(second.reason,'DRAFT_TEST_BUSY');release();await first;assert.equal(f.loginCalls,1);
});
test('explicit sign-out is respected; automatic test does not log back in',async()=>{
  const f=fixture();await f.driver.connect();await f.session.logout();const r=await f.driver.connect();
  assert.equal(r.outcome,'NOT_VERIFIED');assert.equal(f.loginCalls,1);assert.equal(f.session.isSignedOut(),true);
  assert(f.storageWrites.every(x=>typeof x.value==='boolean'));
});
test('expired session cannot silently continue a pinned draft after new login',async()=>{
  const f=fixture();await f.driver.connect();f.advance(3601);const r=await f.driver.connect();
  assert.equal(r.reason,'DRAFT_CHANGED');assert.equal(f.loginCalls,2);
});
test('fresh driver can bind normally restored original draft after expiry',async()=>{
  const f=fixture();await f.driver.connect();f.advance(3601);await f.driver.connect();
  const fresh=createDraftTestDriver({page:f.page,wx:f.wx,config:f.config,now:()=>4601});
  assert.equal((await fresh.connect()).outcome,'SESSION_AVAILABLE');assert.equal((await fresh.probe()).outcome,'READ_OBSERVED');
});
test('backend denial clears original session and is not retried',async()=>{
  const f=fixture({denied:true});await f.driver.connect();const r=await f.driver.probe();
  assert.equal(r.reason,'ACCESS_DENIED');assert.equal(f.session.isAuthenticated(),false);assert.equal(f.backendCalls,1);
});
test('application switch stops old driver before a request',async()=>{
  const f=fixture();await f.driver.connect();f.page.data.application.application='other_draft';const r=await f.driver.probe();
  assert.equal(r.reason,'DRAFT_CHANGED');assert.equal(f.backendCalls,0);
});
test('scene switch stops old driver before a request',async()=>{
  const f=fixture();await f.driver.connect();f.page.scene='different';assert.equal((await f.driver.probe()).reason,'DRAFT_CHANGED');assert.equal(f.backendCalls,0);
});
test('another session cannot be supplied to impersonate original page',async()=>{
  const f=fixture();await f.driver.connect();f.page.session={};assert.equal((await f.driver.probe()).reason,'TEST_SESSION_MISMATCH');assert.equal(f.backendCalls,0);
});
test('backend reconfiguration and page close invalidate the driver',async()=>{
  const f=fixture();await f.driver.connect();f.config.baseUrl='https://other.example';assert.equal((await f.driver.probe()).reason,'PAGE_UNAVAILABLE');
  const g=fixture();await g.driver.connect();g.close();assert.equal((await g.driver.probe()).reason,'PAGE_UNAVAILABLE');
});
test('offline mode cannot be labelled a normal WeChat runtime',()=>{
  const f=fixture();assert.throws(()=>createDraftTestDriver({page:f.page,wx:f.wx,config:{...f.config,mode:'OFFLINE'}}),/NON_WECHAT_RUNTIME/);
});
test('original upload triggers its existing automatic OCR, but is not called verified',async()=>{
  const f=fixture();await f.driver.connect();const r=await f.driver.upload('business_license');
  assert.equal(f.page.lastUpload,'business_license');assert.equal(r.state.ocr_polling,true);assert.equal(r.outcome,'OBSERVED_ONLY');
});
test('existing-material recognition, result read and original confirm/save read back',async()=>{
  const f=fixture();await f.driver.connect();await f.driver.recognize('business_license');await f.driver.readOcr();
  const r=await f.driver.confirmAndSave();assert.equal(r.readback_available,true);
  assert.equal((await f.driver.verifySaved()).outcome,'READBACK_MATCHED');assert.equal(f.loginCalls,1);
});
test('save with swallowed failure/no-op cannot manufacture successful readback',async()=>{
  const f=fixture({swallowedSave:true});await f.driver.connect();assert.equal((await f.driver.save()).readback_available,false);
  assert.equal((await f.driver.verifySaved()).reason,'NO_SAVED_EXPECTATION');
});
test('OCR confirm/save no-op cannot manufacture successful readback',async()=>{
  const f=fixture({swallowedSave:true});await f.driver.connect();assert.equal((await f.driver.confirmAndSave()).readback_available,false);
  assert.equal((await f.driver.verifySaved()).reason,'NO_SAVED_EXPECTATION');
});
test('readback catches altered values, including values same length',async()=>{
  const f=fixture();await f.driver.connect();await f.driver.save();f.record.profile.synthetic='PRIVATE_VALUE';
  assert.equal((await f.driver.verifySaved()).reason,'SAVED_WRITE_MISMATCH');
});
test('readback ignores object key order but detects different nesting',async()=>{
  const f=fixture();await f.driver.connect();f.page.profile={a:{x:1,y:2},b:[1,2]};await f.driver.save();
  f.record.profile={b:[1,2],a:{y:2,x:1}};assert.equal((await f.driver.verifySaved()).outcome,'READBACK_MATCHED');
  f.record.profile={b:[2,1],a:{y:2,x:1}};assert.equal((await f.driver.verifySaved()).reason,'SAVED_WRITE_MISMATCH');
});
test('revision conflict is distinct from successful saved readback',async()=>{
  const f=fixture();await f.driver.connect();await f.driver.save();f.record.version++;
  assert.equal((await f.driver.verifySaved()).reason,'READBACK_VERSION_CHANGED');
});
test('all reports are credential/content free and make no real-device acceptance claim',async()=>{
  const f=fixture();await f.driver.connect();await f.driver.probe();await f.driver.readOcr();await f.driver.confirmAndSave();await f.driver.verifySaved();
  const r=f.driver.report(),json=JSON.stringify(r);
  for(const secret of ['S'.repeat(32),'SYNTHETIC_CODE_DO_NOT_EXPORT','synthetic_private_draft','private_value','SECRET_VALUE_NOT_FOR_REPORT','https://example.com'])assert(!json.includes(secret));
  assert.equal(r.real_device_acceptance,'NOT_ESTABLISHED_BY_THIS_REPORT');assert.equal(r.credentials_exported,false);
  assert.equal(r.environment_attestation,'NOT_SUPPLIED');
});
test('no direct API submission, financial shortcut, credential export or token import method exists',()=>{
  const f=fixture();for(const key of ['submit','wechat_apply','payment','exportToken','importToken','refreshToken'])assert.equal(f.driver[key],undefined);
});
test('malformed readback cannot become a successful probe',async()=>{
  const f=fixture();await f.driver.connect();f.remote.application='unrelated';assert.equal((await f.driver.probe()).reason,'UNTRUSTED_DRAFT_READBACK');
});
test('unsupported material and busy page cause no original write',async()=>{
  const f=fixture();await f.driver.connect();assert.equal((await f.driver.upload('other')).reason,'UNSUPPORTED_TEST_ACTION');
  f.page.data.pending=true;assert.equal((await f.driver.upload('business_license')).reason,'PAGE_BUSY');assert.equal(f.page.lastUpload,undefined);
});
test('returned report cannot mutate internal evidence',async()=>{
  const f=fixture();await f.driver.connect();const r=f.driver.report();r.events[0].outcome='FAKE';assert.equal(f.driver.report().events[0].outcome,'SESSION_AVAILABLE');
  assert.equal(f.driver.clearReport(),true);assert.equal(f.driver.report().events.length,0);
});
test('two drivers cannot concurrently write through the same original session',async()=>{
  const f=fixture();await f.driver.connect();let release;f.page.upload=()=>new Promise(resolve=>release=resolve);
  const second=createDraftTestDriver({page:f.page,wx:f.wx,config:f.config,now:()=>1000});
  const pending=f.driver.upload('business_license');assert.equal((await second.save()).reason,'DRAFT_TEST_BUSY');release();await pending;
});
test('save observation is restored when the original method throws',async()=>{
  const f=fixture();await f.driver.connect();const original=f.session.merchant;
  f.page.save=async()=>{throw Error('PRIVATE_ERROR_DO_NOT_EXPORT');};
  const r=await f.driver.save();assert.equal(r.reason,'ORIGINAL_PAGE_OPERATION_FAILED');assert.equal(f.session.merchant,original);
  assert(!JSON.stringify(f.driver.report()).includes('PRIVATE_ERROR_DO_NOT_EXPORT'));
});
test('platform change between platform and provider reads invalidates saved readback',async()=>{
  const f=fixture();await f.driver.connect();await f.driver.save();const original=f.page.request;
  f.page.request=async function(action,params){const result=await original.call(this,action,params);if(action==='wechat_read')f.remote.revision++;return result;};
  assert.equal((await f.driver.verifySaved()).reason,'READBACK_VERSION_CHANGED');
});
test('observer captures original transport-added platform choices, not only profile',async()=>{
  const f=fixture();await f.driver.connect();const original=f.page.request;
  f.page.request=function(action,params){return original.call(this,action,action==='save'?{...params,redemption_percent:20,split_participation:false,requested_split_bps:0}:params);};
  await f.driver.save();const ok=await f.driver.verifySaved();assert.equal(ok.outcome,'READBACK_MATCHED');
  assert(ok.verified_components.includes('platform.redemption_percent'));f.remote.redemption_percent=30;
  assert.equal((await f.driver.verifySaved()).reason,'SAVED_WRITE_MISMATCH');
});
test('source method replacement during observation is not overwritten or counted verified',async()=>{
  const f=fixture();await f.driver.connect();const original=f.page.save;const replacement=async()=>{};
  f.page.save=async function(){await original.call(this);f.session.merchant=replacement;};
  assert.equal((await f.driver.save()).readback_available,false);assert.equal(f.session.merchant,replacement);
});
test('version changes without an observed original write cannot establish saved evidence',async()=>{
  const f=fixture();await f.driver.connect();f.page.save=async()=>{f.remote.revision++;f.record.version++;f.page.version++;f.page.data.application.revision++;};
  assert.equal((await f.driver.save()).readback_available,false);
});
test('unrelated same-session save cannot be attributed to waiting OCR confirmation',async()=>{
  const f=fixture();await f.driver.connect();let release;
  f.page.confirmAndSaveOcr=()=>new Promise(resolve=>release=resolve);
  const pending=f.driver.confirmAndSave();
  const result=await f.session.merchant('','onboarding',{operation:'wechat_save',params:{application:f.remote.application,expected_version:f.record.version,profile:{unrelated:'private'}}});
  f.page.version=result.version;f.page.profile=result.profile;release();
  assert.equal((await pending).readback_available,false);assert.equal((await f.driver.verifySaved()).reason,'NO_SAVED_EXPECTATION');
});
test('input observation clone failure never blocks the original operation',async()=>{
  const f=fixture();await f.driver.connect();let calls=0;const circular={};circular.self=circular;
  const saved={version:2,profile:{}};f.session.merchant=async()=>{calls++;return saved;};
  f.page.save=async()=>{const result=await f.page.request('wechat_save',circular);assert.equal(result,saved);};
  assert.equal((await f.driver.save()).readback_available,false);assert.equal(calls,1);
});
test('output observation clone failure preserves the original successful result',async()=>{
  const f=fixture();await f.driver.connect();let calls=0;const circular={};circular.self=circular;
  f.session.merchant=async()=>{calls++;return circular;};
  f.page.save=async()=>{const result=await f.page.request('wechat_save',{application:f.remote.application,expected_version:1,profile:{}});assert.equal(result,circular);};
  assert.equal((await f.driver.save()).readback_available,false);assert.equal(calls,1);
});
