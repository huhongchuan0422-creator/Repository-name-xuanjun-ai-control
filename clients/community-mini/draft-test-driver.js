'use strict';
// A same-runtime test client for the ORIGINAL applicant page. It creates no
// identities, exports no credentials and adds no backend/permission bypass.
const {getSharedSession}=require('./session');
const {safeSubmissionDiagnostic}=require('./submission-diagnostic');
const pageFlights=new WeakMap(),sessionFlights=new WeakMap();
const SOURCE_REVISION='41e778ed12dc9dcbe710d32a191c1b06ecbab3b3';
const METHODS=['connectApplicant','request','upload','recognizeDocument','readOcr','confirmAndSaveOcr','save'];
const ERROR_CODES=new Set(['SIGNED_OUT','SESSION_EXPIRED','STALE_SESSION','STALE_LOGIN','ACCESS_DENIED','WECHAT_LOGIN_FAILED','LOGIN_CODE_REQUIRED','UNTRUSTED_SESSION','SERVICE_RESULT_UNKNOWN','SERVICE_REQUEST_REJECTED','UNTRUSTED_MERCHANT_REPLY','DRAFT_CHANGED','PAGE_NOT_READY','PAGE_BUSY','DRAFT_REQUIRED','DRAFT_TEST_BUSY','UNSUPPORTED_TEST_ACTION','READBACK_VERSION_CHANGED','UNTRUSTED_DRAFT_READBACK','NON_WECHAT_RUNTIME','PAGE_UNAVAILABLE','INVALID_TEST_PAGE','TEST_SESSION_MISMATCH']);
const clone=value=>JSON.parse(JSON.stringify(value));
const same=(left,right)=>{
  if(left===right)return true;
  if(!left||!right||typeof left!=='object'||typeof right!=='object'||Array.isArray(left)!==Array.isArray(right))return false;
  const a=Object.keys(left).sort(),b=Object.keys(right).sort();
  return a.length===b.length&&a.every((key,i)=>key===b[i]&&same(left[key],right[key]));
};
function createDraftTestDriver({page,wx,config,now}) {
  if(!page||!page.data||METHODS.some(key=>typeof page[key]!=='function')||typeof page.current!=='function')throw Error('INVALID_TEST_PAGE');
  if(!config||config.mode!=='WECHAT_LOGIN')throw Error('NON_WECHAT_RUNTIME');
  // The original session factory scopes by config identity, wx and backend.
  const session=getSharedSession(wx,config,now,page),baseUrl=config.baseUrl;
  let binding=null,flight=null,sequence=0,events=[],expected=null;
  const pageCurrent=()=>page.current()&&config.baseUrl===baseUrl&&config.mode==='WECHAT_LOGIN';
  function active(requireDraft=true) {
    if(!pageCurrent())throw Error('PAGE_UNAVAILABLE');
    if(page.session!==session)throw Error('TEST_SESSION_MISMATCH');
    if(!session.isAuthenticated())throw Error('SESSION_EXPIRED');
    if(!page.data.ready)throw Error('PAGE_NOT_READY');
    const id=page.data.application&&page.data.application.application;
    if(requireDraft&&!id)throw Error('DRAFT_REQUIRED');
    if(binding&&(binding.application!==id||binding.generation!==session.getGeneration()||binding.scene!==page.scene))throw Error('DRAFT_CHANGED');
  }
  function pin() {
    active();
    if(!binding)binding={application:page.data.application.application,generation:session.getGeneration(),scene:page.scene};
  }
  function snapshot() {
    const app=page.data.application;
    return {authenticated:pageCurrent()&&page.session===session&&session.isAuthenticated(),ready:page.data.ready===true,
      has_application:!!app,application_revision:app&&Number.isSafeInteger(app.revision)?app.revision:null,
      provider_version:Number.isSafeInteger(page.version)?page.version:null,
      same_bound_draft:!!binding&&!!app&&binding.application===app.application&&binding.generation===session.getGeneration()&&binding.scene===page.scene,
      pending:page.data.pending===true,dirty:page.data.dirty===true,ocr_polling:page.ocrPolling===true,
      ocr_rows:Array.isArray(page.data.ocrRows)?page.data.ocrRows.length:0,ocr_confirmed:page.data.ocrConfirmed===true,
      upload_phase:page.data.uploadFeedback&&['preparing','uploading','uploaded','unknown','failed'].includes(page.data.uploadFeedback.phase)?page.data.uploadFeedback.phase:null};
  }
  function receipt(action,outcome,reason,details={}) {
    // Deliberately no page status/error strings, personal fields, draft IDs,
    // token, login code, URLs, material IDs, OCR contents, or raw replies.
    const event={sequence:++sequence,action,outcome,...(reason?{reason}:{}),...details,state:snapshot()};
    events.push(event);return clone(event);
  }
  async function execute(action,work) {
    if(flight||pageFlights.has(page)||sessionFlights.has(session))return receipt(action,'NOT_STARTED','DRAFT_TEST_BUSY');
    const marker={};flight=marker;pageFlights.set(page,marker);sessionFlights.set(session,marker);
    try{return await work();}
    catch(error){const code=error&&error.code==='ACCESS_DENIED'?'ACCESS_DENIED':error&&error.message;
      return receipt(action,'NOT_VERIFIED',ERROR_CODES.has(code)?code:'ORIGINAL_PAGE_OPERATION_FAILED');}
    finally{if(flight===marker)flight=null;if(pageFlights.get(page)===marker)pageFlights.delete(page);if(sessionFlights.get(session)===marker)sessionFlights.delete(session);}
  }
  async function readback(action,compare) {
    active();pin();
    const app=await page.request('read',{application:binding.application});active();
    const record=await page.request('wechat_read',{application:binding.application});active();
    if(!app||app.application!==binding.application||!Number.isSafeInteger(app.revision)||!record||!Number.isSafeInteger(record.version)||!record.profile||typeof record.profile!=='object')throw Error('UNTRUSTED_DRAFT_READBACK');
    if(compare){
      if(!expected)return receipt(action,'NOT_VERIFIED','NO_SAVED_EXPECTATION');
      // The current API has no atomic platform+provider snapshot. Read the
      // platform revision again to catch writes between the two reads.
      const after=await page.request('read',{application:binding.application});active();
      if(!after||after.application!==app.application||after.revision!==app.revision||!same(after,app))throw Error('READBACK_VERSION_CHANGED');
      if(app.revision!==expected.applicationRevision||record.version!==expected.providerVersion)throw Error('READBACK_VERSION_CHANGED');
      const matches=Object.entries(expected.platform).every(([key,value])=>same(app[key],value))&&Object.entries(expected.wechat).every(([key,value])=>same(record[key],value));
      return receipt(action,matches?'READBACK_MATCHED':'NOT_VERIFIED',matches?null:'SAVED_WRITE_MISMATCH',{readback_matched:matches,verified_components:matches?expected.components:[]});
    }
    return receipt(action,'READ_OBSERVED',null,{backend_session_accepted:true});
  }
  async function observeSave(work,requiresWechat) {
    // Observe the exact original outbound write, NOT the page profile after its
    // original reload (which could conceal server-side loss of submitted data).
    const original=session.merchant,originalPageRequest=page.request,observed=[],generation=session.getGeneration(),scene=page.scene;
    let contaminated=false,origin=null;
    const observedPageRequest=function(operation,params) {
      // Original page.request synchronously dispatches its first merchant call.
      // Later delayed retries or unrelated session calls cannot inherit this
      // origin. They continue normally, but cannot count as this action's proof.
      const previous=origin;origin=this===page?{operation}:null;
      try{return originalPageRequest.call(this,operation,params);}
      finally{origin=previous;}
    };
    const observedRequest=async function(requestScene,category,body) {
      let entry=null;
      try{
        const operation=body&&body.operation,params=body&&body.params;
        if(category==='onboarding'&&['save','wechat_save'].includes(operation)){
          if(!origin||origin.operation!==operation||requestScene!==(scene||'')||generation!==session.getGeneration()||!pageCurrent()||page.session!==session)contaminated=true;
          const currentId=page.data.application&&page.data.application.application;
          if(!params||params.application!==null&&params.application!==currentId)contaminated=true;
          entry={operation,params:clone(params),applicationRevision:page.data.application&&page.data.application.revision};
          observed.push(entry);
        }
      }catch(_){contaminated=true;entry=null;}
      // Observation failures never suppress/repeat the original request or
      // replace its return value/error. No credentials enter this signature.
      const result=await original.call(this,requestScene,category,body);
      if(entry){try{entry.result=clone(result);}catch(_){contaminated=true;}}
      return result;
    };
    page.request=observedPageRequest;session.merchant=observedRequest;
    try{await work();}
    finally{
      if(session.merchant===observedRequest)session.merchant=original;else contaminated=true;
      if(page.request===observedPageRequest)page.request=originalPageRequest;else contaminated=true;
    }
    active();pin();
    if(contaminated||generation!==session.getGeneration()||scene!==page.scene||page.data.pending||page.data.dirty||page.ocrFlight)return false;
    const platform=observed.filter(item=>item.operation==='save'),wechat=observed.filter(item=>item.operation==='wechat_save');
    // Multiple writes are an ambiguous observation, never attributed as one
    // successful save. A lost response cannot establish persistence either.
    if(!observed.length||platform.length>1||wechat.length>1||observed.some(item=>!item.result)||requiresWechat&&wechat.length!==1)return false;
    const a=page.data.application,recordVersion=page.version;
    if(!a||!Number.isSafeInteger(a.revision)||!Number.isSafeInteger(recordVersion))return false;
    const p=platform[0],w=wechat[0];
    if(p&&(p.result.application!==a.application||p.result.revision!==a.revision||p.result.revision<=p.params.revision))return false;
    if(w&&(w.params.application!==a.application||w.result.version!==recordVersion||w.result.version<=w.params.expected_version))return false;
    const contract=(entry,omit)=>entry?Object.fromEntries(Object.entries(entry.params).filter(([key])=>!omit.includes(key))):{};
    const platformFields=contract(p,['application','revision']),wechatFields=contract(w,['application','expected_version','application_revision']);
    expected={applicationRevision:a.revision,providerVersion:recordVersion,platform:platformFields,wechat:wechatFields,
      components:[...Object.keys(platformFields).map(key=>'platform.'+key),...Object.keys(wechatFields).map(key=>'wechat.'+key)]};
    return true;
  }
  async function observeApplicationAction(action,method) {
    active();pin();if(page.data.pending)throw Error('PAGE_BUSY');
    if(typeof page[method]!=='function')return receipt(action,'NOT_STARTED','ORIGINAL_METHOD_UNAVAILABLE');
    const original=session.merchant,originalPageRequest=page.request,observed=[];
    const generation=session.getGeneration(),scene=page.scene,application=binding.application;
    let contaminated=false,origin=null;
    const safeState=(value,allowed)=>typeof value==='string'&&allowed.includes(value)?value:null;
    const progress=value=>value&&typeof value==='object'&&!Array.isArray(value)&&Number.isSafeInteger(value.version)&&value.version>=0&&['DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED','SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(value.state)?{
      provider_version:Number.isSafeInteger(value.version)?value.version:null,
      review_state:safeState(value.state,['DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED','SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER']),
      provider_state:safeState(value.provider_state,['APPLYMENT_STATE_EDITING','APPLYMENT_STATE_EDITTING','APPLYMENT_STATE_AUDITING','APPLYMENT_STATE_REJECTED','APPLYMENT_STATE_TO_BE_CONFIRMED','APPLYMENT_STATE_TO_BE_SIGNED','APPLYMENT_STATE_SIGNING','APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED']),
      has_applyment_id:Number.isSafeInteger(value.applyment_id)&&value.applyment_id>0||typeof value.applyment_id==='string'&&/^[0-9]+$/.test(value.applyment_id)
    }:null;
    const observedPageRequest=function(operation,params) {
      const previous=origin;origin=this===page?{operation}:null;
      try{return originalPageRequest.call(this,operation,params);}
      finally{origin=previous;}
    };
    const observedRequest=async function(requestScene,category,body) {
      let entry=null;
      try{
        const operation=body&&body.operation,params=body&&body.params;
        if(category==='onboarding'&&['wechat_apply','wechat_status','wechat_read','read'].includes(operation)){
          if(!origin||origin.operation!==operation||requestScene!==(scene||'')||generation!==session.getGeneration()||!pageCurrent()||page.session!==session||!params||params.application!==application)contaminated=true;
          entry={operation,response_observed:false};observed.push(entry);
        }
      }catch(_){contaminated=true;entry=null;}
      try{
        const result=await original.call(this,requestScene,category,body);
        if(entry){try{
          entry.response_observed=true;
          if(entry.operation==='read')entry.response_valid=!!result&&result.application===application&&Number.isSafeInteger(result.revision)&&result.revision>=0;
          else{entry.progress=progress(result);entry.response_valid=entry.progress!==null;}
        }catch(_){contaminated=true;}}
        return result;
      }catch(error){
        if(entry){try{
          const d=safeSubmissionDiagnostic(error&&error.submissionDiagnostic);
          entry.failed=true;
          if(d)entry.diagnostic={operation:d.operation,stage:d.stage,code:d.code,status:d.status,correlation_id:d.correlation_id,timestamp:d.timestamp};
        }catch(_){contaminated=true;}}
        throw error;
      }
    };
    page.request=observedPageRequest;session.merchant=observedRequest;
    try{await page[method]();}
    finally{
      if(session.merchant===observedRequest)session.merchant=original;else contaminated=true;
      if(page.request===observedPageRequest)page.request=originalPageRequest;else contaminated=true;
    }
    active();
    if(contaminated||generation!==session.getGeneration()||scene!==page.scene||page.data.pending)return receipt(action,'NOT_VERIFIED','UNATTRIBUTED_APPLICATION_OBSERVATION');
    const operations=observed.filter(v=>['wechat_apply','wechat_status'].includes(v.operation)),last=observed[observed.length-1];
    // These are observed original responses, not proof of real identity,
    // provider acceptance or financial activation. Never replay a lost response.
    const outcome=observed.some(v=>v.failed||v.response_observed&&!v.response_valid)?'NOT_VERIFIED':operations.some(v=>v.response_valid)?'PROVIDER_RESPONSE_OBSERVED':last&&last.response_valid?'ORIGINAL_READ_OBSERVED':'NOT_VERIFIED';
    return receipt(action,outcome,outcome==='NOT_VERIFIED'?'APPLICATION_RESULT_NOT_VERIFIED':null,{
      operations:observed,progress:[...observed].reverse().find(v=>v.progress)?.progress||null,
      provider_response_observed:operations.some(v=>v.response_valid),
      original_submit_calls:operations.filter(v=>v.operation==='wechat_apply').length,
      original_query_calls:operations.filter(v=>v.operation==='wechat_status').length,
      real_provider_acceptance:'NOT_ESTABLISHED_BY_THIS_REPORT'
    });
  }
  const driver={
    connect(){return execute('connect',async()=>{
      if(!pageCurrent())throw Error('PAGE_UNAVAILABLE');
      if(page.data.pending)throw Error('PAGE_BUSY');
      const reused=page.session===session&&session.isAuthenticated();
      // Existing explicit sign-out remains respected. This runner never resets
      // it or silently treats a test call as the owner's login-button click.
      if(!reused||!page.data.ready)await page.connectApplicant({automatic:true});
      active(false);if(page.data.application)pin();
      return receipt('connect','SESSION_AVAILABLE',null,{session_reused:reused});
    });},
    probe(){return execute('probe',()=>readback('probe',false));},
    upload(kind){return execute('upload',async()=>{
      active(false);if(page.data.pending)throw Error('PAGE_BUSY');if(page.data.application)pin();
      // Original picker, compression, upload, automatic OCR and original
      // binding checks run unchanged; kind is validated by the original page.
      if(typeof kind!=='string'||!page.data.catalog.some(item=>item.id===kind))throw Error('UNSUPPORTED_TEST_ACTION');
      expected=null;await page.upload({currentTarget:{dataset:{kind}}});active(false);if(page.data.application)pin();
      return receipt('upload','OBSERVED_ONLY');
    });},
    recognize(kind){return execute('recognize',async()=>{
      active();pin();if(page.data.pending)throw Error('PAGE_BUSY');
      if(!['business_license','id_front','id_back','bank_card'].includes(kind))throw Error('UNSUPPORTED_TEST_ACTION');
      expected=null;await page.recognizeDocument({currentTarget:{dataset:{kind}}});active();
      return receipt('recognize','OBSERVED_ONLY');
    });},
    readOcr(){return execute('read_ocr',async()=>{active();pin();if(page.data.pending)throw Error('PAGE_BUSY');await page.readOcr();active();return receipt('read_ocr','OBSERVED_ONLY');});},
    confirmAndSave(){return execute('confirm_and_save',async()=>{
      active();pin();if(page.data.pending)throw Error('PAGE_BUSY');
      expected=null;
      // The original page can catch failures or await a confirmation receipt.
      // A fulfilled promise alone is never a successful OCR/save acceptance.
      const captured=await observeSave(()=>page.confirmAndSaveOcr(),true);
      return receipt('confirm_and_save','OBSERVED_ONLY',null,{readback_available:captured});
    });},
    save(){return execute('save',async()=>{active(false);if(page.data.application)pin();if(page.data.pending)throw Error('PAGE_BUSY');expected=null;const captured=await observeSave(()=>page.save(),page.data.canEditWechat!==false);return receipt('save','OBSERVED_ONLY',null,{readback_available:captured});});},
    verifySaved(){return execute('verify_saved',()=>readback('verify_saved',true));},
    // Explicit original UI actions only: no direct API, retries or new identity.
    submitReview(){return execute('submit_review',()=>observeApplicationAction('submit_review','submitAllReview'));},
    queryStatus(){return execute('query_status',()=>observeApplicationAction('query_status','refreshApplication'));},
    snapshot(){return clone(snapshot());},
    report(){return clone({version:1,source_revision:SOURCE_REVISION,boundary:'ORIGINAL_APPLICANT_PAGE_AND_SHARED_SESSION',
      environment_attestation:'NOT_SUPPLIED',real_device_acceptance:'NOT_ESTABLISHED_BY_THIS_REPORT',
      credentials_exported:false,financial_or_review_submit_exposed:true,events});},
    clearReport(){if(flight)return false;events=[];sequence=0;expected=null;return true;}
  };
  return driver;
}
module.exports={createDraftTestDriver};
