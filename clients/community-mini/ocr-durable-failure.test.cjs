'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const root=__dirname,traces=[];
const clone=x=>JSON.parse(JSON.stringify(x));
const material={uploaded:true,review:'PENDING',expires_at:null,object_id:'o_'+'a'.repeat(32),sha256:'b'.repeat(64)};
const newApp=()=>({application:'synthetic_new_app',revision:1,fields:{store_name:'合成门店',address:'合成地址'},entity_type:'ENTERPRISE',identity_type:'IDENTIFICATION_TYPE_IDCARD',status:'DRAFT',materials:{},declarations:{scene:'mini',ubos:0},category:'GENERAL',redemption_percent:0,opening_state:'NOT_OPENED',wechat_submerchant_state:'NOT_SUBMITTED'});
const noJobDiagnostic={version:1,diagnostic_id:'c'.repeat(32),stage:'RESULT_READ',reason:'MATERIAL_JOB_NOT_FOUND',retryable:false,request_retained:false};
function makeModule(file,require){const module={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(root,file),'utf8'),{module,exports:module.exports,require,console},{filename:file});return module.exports;}
async function harness(options={}){
 const calls=[],timers=new Map();let submitAttempts=0;let timerId=0,remote=clone(options.remote||newApp()),createdJob=false;
 const payload=kind=>({job_id:'synthetic_job',document_type:kind,application_revision:String(remote.revision),provider_version:1,status:options.resultStatus||'needs_review',confirmation_revision:0,...(options.payloadExtra||{}),fields:{company_name:{value:'合成主体'},id_name:{value:'合成姓名'},valid_from:{value:'2020-01-01'},account_number:{value:'SYNTHETIC_ACCOUNT'}}});
 const reply=(o,result)=>o.success({statusCode:200,data:{payment_enabled:false,result}});
 const wx={login:o=>o.success({code:'SYNTHETIC_CODE'}),chooseMedia:o=>o.success({tempFiles:[{tempFilePath:'/synthetic/image'}]}),getFileSystemManager:()=>({stat:o=>o.success({stats:{size:3}}),readFile:o=>o.success({data:'YWJj'})}),request(o){
  if(o.url.endsWith('/mini/login')){calls.push({action:'login'});reply(o,{session_token:'s'.repeat(32),expires_at:2000,provider:'WECHAT_MINIPROGRAM',payment_enabled:false});return;}
  const p=o.data.params,action=o.data.operation==='ocr'?p.action:p.operation;calls.push({action,params:clone(p),timeout:o.timeout});
  if(action==='upload'){
   if(options.uploadMode!=='rejected'&&options.uploadMode!=='unknown_not_persisted'){remote.revision++;remote.materials[p.params.kind]=clone(material);}
   if(options.uploadMode==='unknown'||options.uploadMode==='unknown_not_persisted'){o.fail({errMsg:'request:fail timeout'});return;}
   if(options.uploadMode==='rejected'){o.success({statusCode:400,data:{error:'INVALID_REQUEST'}});return;}
   reply(o,clone(remote));return;
  }
  if(action==='read'&&o.data.operation==='onboarding'){reply(o,clone(remote));return;}
  if(action==='wechat_read'){reply(o,{profile:{},version:1,state:'DRAFT'});return;}
  if(action==='submit'){
   if(options.submitUnknownOnce&&submitAttempts++===0){createdJob=true;o.fail({errMsg:'request:fail timeout'});return;}
   if(options.submitPendingOnce&&submitAttempts++===0){createdJob=true;o.success({statusCode:403,data:{error:'OCR_REQUEST_PENDING',ocr_diagnostic:{...noJobDiagnostic,stage:'QUEUE',reason:'REQUEST_IN_PROGRESS',retryable:true,request_retained:true}}});return;}
   if(options.submitPermissionDenied){o.success({statusCode:403,data:{error:'OCR_AUTH_DENIED'}});return;}
   createdJob=true;reply(o,{result:{job_id:'synthetic_job'}});return;
  }
  if(action==='read'&&o.data.operation==='ocr'){if(options.onReadReply)options.onReadReply({page,session,remote});if(options.readDenied){o.success({statusCode:403,data:{error:'OCR_AUTH_DENIED'}});return;}reply(o,{result:payload(options.kind||'business_license')});return;}
  if(action==='recover_view'){
   if(options.onRecoveryReply)options.onRecoveryReply({page,session,remote});
   if(options.recoveryNetwork){o.fail({errMsg:'request:fail socket closed'});return;}
   if(options.recoveryPending){o.success({statusCode:403,data:{error:'OCR_REQUEST_PENDING',ocr_diagnostic:{...noJobDiagnostic,stage:'QUEUE',reason:'ANOTHER_REQUEST_IN_PROGRESS',retryable:true,request_retained:false}}});return;}
   if(options.recoverPermissionDenied){o.success({statusCode:403,data:{error:'OCR_AUTH_DENIED'}});return;}
   if(!createdJob&&!options.existingJob){o.success({statusCode:403,data:{error:'OCR_UNAVAILABLE',ocr_diagnostic:options.recoveryDiagnostic||noJobDiagnostic}});return;}
   reply(o,{result:{...payload(p.document_type),recovery_id:p.recovery_key,binding:{document_type:p.document_type,application_revision:String(remote.revision),provider_version:1}}});return;
  }
  throw Error('Unexpected synthetic request: '+action);
 }};
 const formatter=require(path.join(root,'submission-diagnostic.js'));
 const sessionExports=makeModule('session.js',name=>name==='./submission-diagnostic'?formatter:name==='./chain-telemetry'?{classifyOcrEmptyResponse:()=>false}:(()=>{throw Error(name);})());
 const session=sessionExports.createSession(wx,'https://example.com',()=>1000);await session.login();
 const get=(o,p)=>p.split('.').reduce((x,k)=>x&&x[k],o);
 const modules={'../../session':sessionExports,'../../chain-telemetry':{},'../../customer-auth':{},'../../merchant-form':{get,industryMaterialKind:()=>false,reusedFieldLinks:()=>({})},'../../merchant-submit':{},'../../merchant-official-fields':{},'../../merchant-platform-reference-data':{}};
 let page;vm.runInNewContext(fs.readFileSync(path.join(root,'pages/merchant-join/index.js'),'utf8'),{wx,Page:x=>{page=x;},require:n=>{if(!(n in modules))throw Error(n);return modules[n];},console,setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id)},{filename:'original-index.js'});
 page.data=clone(page.data);Object.assign(page.data,{application:options.noApplication?null:clone(remote),authenticated:true,ready:true,dirty:false,materialGroups:[{ocrKind:options.kind||'business_license'}]});
 Object.assign(page,{session,scene:'',epoch:1,version:1,profile:{},ocrDrafts:{},current:()=>true,setData(p){Object.assign(this.data,p);},updateOcrView(p){this.setData(p);},refresh(){},retainOcrDisplay(){},chainRecord(){},presentStepOcrReview(){},async finishConfirmedOcrSave(){},cancelReuse(){},restoreUploadedMaterialPreviews:async()=>{},
  async saveDraft(binding){const old=this.data.application;assert.equal(old,null);const saved=clone(remote);assert.equal(binding.accept(saved,old),true);this.setData({application:saved,dirty:false});calls.push({action:'synthetic_initial_draft_boundary'});return saved;}
 });
 async function runTimers(max=5){let n=0;while(timers.size&&n<max){const [id,t]=timers.entries().next().value;timers.delete(id);await t.fn();n++;}return n;}
 return {page,calls,remote,runTimers,get createdJob(){return createdJob;},record(name){traces.push({name,actions:calls.map(x=>x.action),ocrCalls:calls.filter(x=>['submit','recover_view','read'].includes(x.action)&&x.params&&x.params.action),uploadFeedback:page.data.uploadFeedback,ocrStatus:page.data.ocrStatus,ocrPolling:page.ocrPolling,ocrRows:page.data.ocrRows.length});}};
}
async function upload(h,kind='business_license'){await h.page.upload({currentTarget:{dataset:{kind}}});}
function actions(h){return h.calls.map(x=>x.action);}

function saved(){const a=newApp();a.materials.business_license=clone(material);return a;}
async function manual(h){await h.page.recognizeDocument({currentTarget:{dataset:{kind:'business_license'}}});}
function submits(h){return h.calls.filter(x=>x.action==='submit');}
function assertNoSubmit(h){assert.equal(submits(h).length,0);}



const safeID='e'.repeat(32),privateText='PRIVATE_DIAGNOSTIC_DO_NOT_RENDER';
const finalDiagnostic=reason=>({version:1,diagnostic_id:safeID,stage:'EXECUTION',reason,retryable:false,request_retained:true});
for(const reason of ['INFERENCE_FAILED','RESULT_PROCESSING_FAILED','RESULT_PERSISTENCE_FAILED'])test('failed snapshot displays its original safe diagnostic '+reason,async()=>{
 const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:'OCR_INFERENCE_FAILED',failure_outcome:'unknown',ocr_diagnostic:{...finalDiagnostic(reason),message:privateText,token:privateText}}});await manual(h);
 assert.deepEqual(actions(h),['login','recover_view','submit','read']);assert.deepEqual(JSON.parse(JSON.stringify(h.page.data.ocrDiagnostic)),finalDiagnostic(reason));assert.equal(h.page.ocrPolling,false);assert.equal(h.page.data.ocrConfirmed,false);
 assert.ok(!JSON.stringify(h.page.data.ocrDiagnostic).includes(privateText));assert.ok(!h.page.data.ocrStatus.includes(privateText));
 const id=h.page.data.ocrDiagnostic.diagnostic_id;await manual(h);assert.equal(h.page.data.ocrDiagnostic.diagnostic_id,id);assert.equal(submits(h).length,1);
 assert.ok(h.page.data.ocrStatus.includes(safeID));assert.ok(h.page.data.ocrStatus.includes(reason));
 const wxml=fs.readFileSync(path.join(root,'pages/merchant-join/index.wxml'),'utf8');assert.match(wxml,/\{\{ocrStatus\}\}/);
});
for(const change of [{diagnostic_id:privateText},{reason:privateText},{stage:'QUEUE'},{retryable:true},{request_retained:false},{reason:'REQUEST_IN_PROGRESS'}])test('invalid final failure diagnostic cannot impersonate persisted cause '+JSON.stringify(change),async()=>{
 const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:'OCR_INFERENCE_FAILED',failure_outcome:'unknown',ocr_diagnostic:{...finalDiagnostic('INFERENCE_FAILED'),...change}}});await manual(h);assert.equal(h.page.data.ocrDiagnostic,null);assert.ok(!h.page.data.ocrStatus.includes(privateText));assert.equal(submits(h).length,1);
});
test('denied read cannot expose a valid persisted diagnostic',async()=>{
 const h=await harness({remote:saved(),readDenied:true,resultStatus:'failed',payloadExtra:{error_code:'OCR_INFERENCE_FAILED',failure_outcome:'unknown',ocr_diagnostic:finalDiagnostic('INFERENCE_FAILED')}});await manual(h);assert.notEqual(h.page.data.ocrDiagnostic&&h.page.data.ocrDiagnostic.diagnostic_id,safeID);assert.equal(submits(h).length,1);
});

for(const reason of ['INFERENCE_FAILED','RESULT_PROCESSING_FAILED','RESULT_PERSISTENCE_FAILED'])test('reopened authorized failed job displays original safe ID without resubmission '+reason,async()=>{
 const h=await harness({remote:saved(),recoveryDiagnostic:finalDiagnostic(reason)});await manual(h);assert.deepEqual(actions(h),['login','recover_view']);assert.ok(h.page.data.ocrStatus.includes(reason));assert.ok(h.page.data.ocrStatus.includes(safeID));assert.equal(h.page.ocrPolling,false);assertNoSubmit(h);
});
