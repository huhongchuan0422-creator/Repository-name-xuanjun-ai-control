'use strict';
// Actual lifecycle/session/OCR recovery methods, wholly synthetic API replies.
// Preview rendering/filesystem and UI projection are deliberately stubbed.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=__dirname;
const source=fs.readFileSync(path.join(root,'pages/merchant-join/index.js'),'utf8');
function fixture(options={}){
  let now=100,definition,page,nextTimer=0;
  const calls=[],timers=new Map(),modules={};
  const application={application:'synthetic-application',revision:34,status:'DRAFT',fields:{store_name:'',address:''},entity_type:'ENTERPRISE',identity_type:'IDENTIFICATION_TYPE_IDCARD',category:'GENERAL',materials:{identity_back:{uploaded:true}},declarations:{scene:'unknown',ubos:'unknown'}};
  class MockDate extends Date {static now(){return now*1000;}}
  function load(name){
    assert.ok(['session','submission-diagnostic','chain-telemetry','customer-auth'].includes(name));
    if(modules[name])return modules[name];
    const module={exports:{}};modules[name]=module.exports;
    vm.runInNewContext(fs.readFileSync(path.join(root,name+'.js'),'utf8'),{module,exports:module.exports,Date:MockDate,require:p=>load(p.replace(/^\.\//,''))},{filename:name+'.js'});
    return modules[name]=module.exports;
  }
  const session=load('session'),auth=load('customer-auth'),config={baseUrl:'https://example.invalid',scene:''};
  const wx={login(o){calls.push('wx.login');o.success({code:'synthetic-code'});},getStorageSync(){return options.signedOut===true;},setStorageSync(){},
    request(o){
      if(o.url.endsWith('/mini/login')){calls.push('login');o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'A'.repeat(32),expires_at:now+100,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});return;}
      const p=o.data.params,operation=p.operation||p.action;calls.push(operation);
      let result;
      if(operation==='catalog')result={materials:[]};
      else if(operation==='mine')result={applications:[structuredClone(application)]};
      else if(operation==='read'&&o.data.operation==='onboarding')result=structuredClone(application);
      else if(operation==='save')result=structuredClone(application);
      else if(operation==='wechat_save')result={version:5};
      else if(operation==='wechat_read')result={version:5,state:'DRAFT',profile:{}};
      else if(operation==='recover_view')result={result:{recovery_id:p.recovery_key,binding:{document_type:p.document_type,application_revision:'34',provider_version:5},job_id:'synthetic-job',status:'needs_review',fields:{}}};
      else throw Error('Unexpected mock operation '+operation);
      o.success({statusCode:200,data:{payment_enabled:false,result}});
    }
  };
  const form={put(object,key,value){const parts=key.split('.');let target=object;for(const part of parts.slice(0,-1))target=target[part]||(target[part]={});target[parts.at(-1)]=value;},materialGroups(){return [];},syncReusedFields(){},platformFields(){return {};},get(object,key){return key.split('.').reduce((v,k)=>v&&v[k],object);},reusedFieldLinks(){return {};}};
  vm.runInNewContext(source,{Page:d=>{definition=d;},Date:MockDate,wx,getApp:()=>({globalData:config}),setTimeout(fn){timers.set(++nextTimer,fn);return nextTimer;},clearTimeout(id){timers.delete(id);},
    require(p){if(p==='../../session')return session;if(p==='../../customer-auth')return auth;if(p==='../../chain-telemetry')return load('chain-telemetry');if(p==='../../merchant-form')return form;if(p==='../../merchant-submit')return {submitApplicantApplication(){}};if(['../../merchant-official-fields','../../merchant-platform-reference-data'].includes(p))return {};throw Error('Unexpected import');}
  },{filename:'merchant-join/index.js'});
  page={...definition,data:{...structuredClone(definition.data),materialGroups:[]},epoch:auth.current(),scene:'',profile:{},version:0,ocrHidden:false,
    setData(p){Object.assign(this.data,p);},verifyPlatformAppid(){},refresh(){},cancelReuse(){},cancelStepOcrReview(){},beginStepScroll(){},presentStepOcrReview(){},privatePreviewCleanup(){},privateOcrDraftUpdates(){return {};},projectOcrGroups:g=>g||[],
    restoreUploadedMaterialPreviews(){calls.push('preview-stub');},scheduleProviderPoll(){},
    updateOcrView(p){if(p)this.setData(p);},retainOcrDisplay(){},createSubmitReadback(){return null;},async finishConfirmedOcrSave(){}
  };
  return {page,definition,calls,timers,expire(){now+=101;},async connect(){await page.connectApplicant({automatic:true});},async tick(){const next=timers.entries().next().value;if(!next)return;timers.delete(next[0]);await next[1]();},async flush(max=10){for(let n=0;n<max&&timers.size;n++)await this.tick();assert.equal(timers.size,0);}};
}

test('normal connect reads catalog, mine, original application and WeChat draft; background OCR only recover_view',async()=>{
  const f=fixture();await f.connect();await f.flush();
  assert.deepEqual(f.calls,['wx.login','login','catalog','mine','read','wechat_read','preview-stub','recover_view']);
  assert.equal(f.page.data.application.revision,34);assert.equal(f.page.data.authenticated,true);assert.equal(f.page.data.pending,false);
  assert.equal(f.calls.includes('submit'),false);assert.equal(f.calls.includes('upload'),false);
});

test('expired registered session is revoked on reconnect, clears old OCR cache, then recovers existing material without submit',async()=>{
  const f=fixture();await f.connect();await f.flush();
  f.page.ocrHeldCaptures={id_front:{idempotency_key:'synthetic-old-key'}};
  const generation=f.page.session.getGeneration();f.expire();f.calls.length=0;
  await f.connect();await f.flush();
  assert.equal(f.page.session.isAuthenticated(),true);assert.ok(f.page.session.getGeneration()>generation);
  assert.equal(f.page.ocrHeldCaptures,null);assert.equal(f.page.data.application.revision,34);
  assert.deepEqual(f.calls,['wx.login','login','catalog','mine','read','wechat_read','preview-stub','recover_view']);
  assert.equal(f.calls.includes('submit'),false);assert.equal(f.calls.includes('upload'),false);
});

test('onShow calls automatic reconnect only for expired non-pending session',async()=>{
  const f=fixture();await f.connect();await f.flush();f.expire();
  const options=[];f.page.connectApplicant=o=>{options.push(o.automatic);};
  f.page.onShow();assert.deepEqual(options,[true]);
  f.page.data.pending=true;f.page.onShow();assert.deepEqual(options,[true]);
});

test('background restoration has no explicitRecognition and current-material miss does not start submit',async()=>{
  const f=fixture();await f.connect();await f.flush();
  f.page.ocrCapture=null;f.page.ocrHeldCaptures=null;f.page.data.ocrRows=[];
  let submits=0,recoveries=0;
  f.page.recoverCurrentDocument=async capture=>{recoveries++;return capture;};
  f.page.resumeOcrSubmit=async()=>{submits++;};
  await f.page.recognizeCurrentDocument('id_back',{newIntent:true,existingMaterial:true});
  assert.equal(recoveries,1);assert.equal(submits,0);
});

test('same-session retained pending key may resume submit despite background existingMaterial path',async()=>{
  const f=fixture();await f.connect();await f.flush();
  const capture=f.page.ocrCapture;capture.recovery=false;capture.job_id='';capture.idempotency_key='synthetic-pending-key';f.page.data.ocrJob='';
  let key;f.page.resumeOcrSubmit=async c=>{key=c.idempotency_key;};
  await f.page.recognizeCurrentDocument('id_back',{newIntent:true,existingMaterial:true});
  assert.equal(key,'synthetic-pending-key');
});

test('refreshApplication does not renew session and can query provider for submitted review states',()=>{
  const f=fixture();assert.match(f.page.refreshApplication.toString(),/wechat_status/);assert.doesNotMatch(f.page.refreshApplication.toString(),/ensureLogin|connectApplicant/);
});

test('entry then dwell to expiry then no-row save exposes recovery feedback',async()=>{
  const f=fixture();await f.connect();await f.flush();f.calls.length=0;
  f.page.data.application.revision=35;f.expire();
  assert.equal(f.page.current(),true);assert.equal(f.page.session.isAuthenticated(),false);
  assert.equal(f.page.data.authenticated,true);assert.equal(f.page.data.ready,true);
  await f.page.reviewAndNext();
  assert.equal(f.calls.some(x=>['save','wechat_save','submit','upload','recover_confirm','recover_apply','login','wx.login'].includes(x)),false);
  assert.equal(f.page.data.application.revision,35);assert.equal(f.page.data.pending,false);
  assert.equal(f.page.data.sessionRecoveryRequired,true);assert.equal(f.page.data.authenticated,false);assert.match(f.page.data.status,/登录已失效/);
});

test('expired with dynamic review rows exposes recovery instead of changed-data prompt',async()=>{
  const f=fixture();await f.connect();await f.flush();f.expire();f.calls.length=0;
  f.page.stepOcrReviewRows=()=>[{kind:'id_back',fields:[{key:'valid_from',value:'SYNTHETIC',required:false}]}];
  f.page.stepOcrReviewIntent=null;await f.page.reviewAndNext();
  assert.equal(f.page.data.sessionRecoveryRequired,true);assert.match(f.page.data.status,/登录已失效/);
  assert.equal(f.calls.some(x=>['save','wechat_save','submit','upload','login','wx.login'].includes(x)),false);
});

test('healthy session still saves on explicit next with no auto-login',async()=>{
  const f=fixture();await f.connect();await f.flush();f.calls.length=0;
  f.page.ocrCapture=null;f.page.ocrHeldCaptures=null;f.page.data.ocrConfirmed=false;
  f.page.showStepTop=step=>f.page.setData({step});
  await f.page.reviewAndNext();assert.ok(f.calls.includes('save'));assert.ok(f.calls.includes('wechat_save'));assert.equal(f.page.data.step,1);assert.equal(f.calls.includes('login'),false);
});

test('first unauthenticated requirement browsing still advances with no login or save',async()=>{
  const f=fixture();f.page.data.canEditPlatform=false;f.page.data.canEditWechat=false;f.page.showStepTop=step=>f.page.setData({step});
  await f.page.reviewAndNext();assert.equal(f.page.data.step,1);assert.deepEqual(f.calls,[]);
});

test('explicitly signed out automatic reconnect never signs back in',async()=>{
  const f=fixture({signedOut:true});await f.connect();assert.equal(f.page.data.authenticated,false);assert.equal(f.calls.includes('login'),false);assert.equal(f.calls.includes('wx.login'),false);assert.match(f.page.data.status,/已退出登录/);
});

test('expiry recovery does not change original session lifetime or authentication checks',async()=>{
  const f=fixture();await f.connect();await f.flush();f.expire();
  const before=f.page.session.getGeneration();await f.page.reviewAndNext();
  assert.equal(f.page.session.isAuthenticated(),false);assert.equal(f.page.session.getGeneration(),before);
});

test('expired upload does not even open picker and keeps original local state',async()=>{
  const f=fixture();await f.connect();await f.flush();f.expire();f.calls.length=0;
  f.page.profile={syntheticDraft:'KEEP'};f.page.ocrSuggestionEdits={syntheticField:'KEEP'};f.page.data.dirty=true;
  await f.page.upload({currentTarget:{dataset:{kind:'identity_front'}}});
  assert.deepEqual(f.calls,[]);assert.equal(f.page.profile.syntheticDraft,'KEEP');assert.equal(f.page.ocrSuggestionEdits.syntheticField,'KEEP');assert.equal(f.page.data.dirty,true);assert.equal(f.page.data.sessionRecoveryRequired,true);
});

test('expired direct confirmation does not send or clear pending original intent',async()=>{
  const f=fixture();await f.connect();await f.flush();f.expire();f.calls.length=0;
  const capture=f.page.ocrCapture;await f.page.confirmStepOcrReview();assert.deepEqual(f.calls,[]);assert.equal(f.page.ocrCapture,capture);assert.equal(f.page.data.sessionRecoveryRequired,true);
});

test('expiry between run preflight and local merchant check is caught with visible recovery',async()=>{
  const f=fixture();await f.connect();await f.flush();f.calls.length=0;
  await f.page.run(async()=>{f.expire();await f.page.request('save',{application:'synthetic-application',revision:35,fields:{}});},'保存资料');
  assert.equal(f.calls.includes('save'),false);assert.equal(f.calls.includes('login'),false);assert.equal(f.page.data.pending,false);assert.equal(f.page.data.sessionRecoveryRequired,true);assert.equal(f.page.data.authenticated,false);
});

test('partial save before expiry is not claimed unsent and is never replayed',async()=>{
  const f=fixture();await f.connect();await f.flush();f.calls.length=0;
  await f.page.run(async()=>{await f.page.request('save',{application:'synthetic-application',revision:35,fields:{}});f.expire();await f.page.request('wechat_save',{application:'synthetic-application',expected_version:5,profile:{}});},'保存资料');
  assert.equal(f.calls.filter(x=>x==='save').length,1);assert.equal(f.calls.includes('wechat_save'),false);assert.equal(f.calls.includes('login'),false);assert.doesNotMatch(f.page.data.status,/未发送|未送达|未上传/);assert.match(f.page.data.status,/本次操作未完成/);
});

test('repeated failed save remains feedback-only until explicit reconnect; reconnect does not replay',async()=>{
  const f=fixture();await f.connect();await f.flush();f.expire();f.calls.length=0;
  await f.page.reviewAndNext();await f.page.reviewAndNext();assert.deepEqual(f.calls,[]);
  await f.page.connectApplicant();await f.flush();
  assert.equal(f.page.data.sessionRecoveryRequired,false);assert.equal(f.page.data.authenticated,true);
  assert.equal(f.calls.some(x=>['save','wechat_save','upload','submit','recover_confirm','recover_apply'].includes(x)),false);
  assert.ok(f.calls.includes('login'));assert.ok(f.calls.includes('read'));
});

test('expired UI exposes existing reconnect control and explains local unsaved content risk',()=>{
  const markup=fs.readFileSync(path.join(root,'pages/merchant-join/index.wxml'),'utf8');
  assert.match(markup,/wx:if="{{!authenticated}}"/);assert.match(markup,/重新登录并读取原申请/);assert.match(markup,/未保存内容不会自动提交，请先自行保留/);assert.match(markup,/bindtap="connectApplicant"/);
});


// Independent review regressions: actual finally guard, receipts, and recovery limits.
test('actual finally helper cannot autosave after expiry',async()=>{
 const f=fixture();await f.connect();await f.flush();f.calls.length=0;
 f.page.finishConfirmedOcrSave=f.definition.finishConfirmedOcrSave;
 f.page.ocrCapture={...f.page.ocrCapture,auto_save_fields:{synthetic:'KEEP'}};f.page.data.ocrConfirmed=true;
 let fills=0;f.page.fillOcrDraft=async()=>{fills++};
 await f.page.run(async()=>{f.expire();throw Error('SESSION_EXPIRED')},'保存资料');
 assert.equal(fills,0);assert.equal(f.page.data.pending,false);assert.equal(f.page.data.sessionRecoveryRequired,true);assert.deepEqual(f.calls,[]);
});
test('expired preflight preserves pending receipt binding and draft objects',async()=>{
 const f=fixture();await f.connect();await f.flush();
 const c=f.page.ocrCapture;c.recovery_apply_pending=true;
 f.page.profile={synthetic:'UNSAVED'};f.page.data.dirty=true;f.page.data.splitSaveUnknown=true;
 const profile=f.page.profile;f.expire();f.calls.length=0;
 await f.page.reviewAndNext();await f.page.confirmStepOcrReview();
 assert.equal(f.page.ocrCapture,c);assert.equal(c.recovery_apply_pending,true);assert.equal(f.page.profile,profile);
 assert.equal(f.page.data.dirty,true);assert.equal(f.page.data.splitSaveUnknown,true);assert.deepEqual(f.calls,[]);
 assert.doesNotMatch(f.page.data.status,/未发送|未送达|未上传|保存成功/);
});
test('unknown network outcome at expiry is not converted into unsent claim or replay',async()=>{
 const f=fixture();await f.connect();await f.flush();f.calls.length=0;
 await f.page.run(async()=>{f.expire();const e=Error('SERVICE_RESULT_UNKNOWN');e.networkKind='TIMEOUT';throw e},'保存资料');
 assert.doesNotMatch(f.page.data.status,/未发送|未送达|保存成功/);assert.deepEqual(f.calls,[]);
 await f.page.reviewAndNext();assert.equal(f.page.data.sessionRecoveryRequired,true);assert.deepEqual(f.calls,[]);
});
test('reconnect reads saved draft and does not preserve unsaved profile across renewal',async()=>{
 const f=fixture();await f.connect();await f.flush();
 f.page.profile={synthetic:'UNSAVED'};f.page.data.dirty=true;f.expire();await f.page.reviewAndNext();
 assert.equal(f.page.profile.synthetic,'UNSAVED');f.calls.length=0;
 await f.page.connectApplicant();await f.flush();
 assert.equal(f.page.profile.synthetic,undefined);assert.equal(f.page.data.dirty,false);
 assert.equal(f.calls.some(x=>['save','wechat_save','upload','submit','recover_confirm','recover_apply'].includes(x)),false);
});
test('recovery never runs a blocked saveAndLeave navigation',async()=>{
 const f=fixture();await f.connect();await f.flush();f.expire();f.calls.length=0;
 f.page.data.dirty=true;f.page.data.leavePrompt=true;f.page.data.leaveTarget='home';
 let nav=0;f.page.navigateToSection=()=>{nav++};await f.page.saveAndLeave();
 assert.equal(nav,0);assert.equal(f.page.data.dirty,true);assert.equal(f.page.data.leavePrompt,true);assert.deepEqual(f.calls,[]);
});
