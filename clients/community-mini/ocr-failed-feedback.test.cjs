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



const codeGroups={
 unknown:['OCR_INFERENCE_FAILED','ALIYUN_CALL_OUTCOME_UNKNOWN'],
 response_received:['ALIYUN_HTTP_ERROR','ALIYUN_PROVIDER_ERROR','ALIYUN_PERMISSION_DENIED','ALIYUN_RATE_LIMITED','ALIYUN_DOCUMENT_TYPE_MISMATCH','ALIYUN_RESPONSE_INVALID','ALIYUN_DUPLICATE_JSON_KEY','ALIYUN_DATA_JSON_INVALID','ALIYUN_ID_SIDE_MISMATCH','ALIYUN_FIELD_EVIDENCE_INVALID'],
 not_sent:['INVALID_IMAGE_SIZE','UNSUPPORTED_IMAGE_MAGIC','IMAGE_PIXEL_LIMIT','IMAGE_DECODE_FAILED','ALIYUN_IMAGE_DIMENSIONS_UNSUPPORTED','EXPLICIT_SINGLE_ATTEMPT_RUNTIME_REQUIRED','UNSUPPORTED_DOCUMENT_TYPE','SERVER_CONTEXT_REQUIRED','SERVER_CONTEXT_MISMATCH']
};
const phrases={unknown:'本次调用是否完成尚未确定，不能据此判断是否计费',response_received:'已收到识别服务响应，不代表识别成功',not_sent:'本次失败发生在调用前'};
const privateValue='PRIVATE_SENTINEL_do_not_render';
const result=[];
for(const [outcome,codes] of Object.entries(codeGroups))for(const code of codes)test('public failed read displays existing classification '+code,async()=>{
 const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:code,failure_outcome:outcome,message:privateValue,provider_trace:{body:privateValue},ocr_diagnostic:{diagnostic_id:privateValue}}});
 await manual(h);
 assert.deepEqual(actions(h),['login','recover_view','submit','read']); // missing job -> original explicit first-submit path
 assert.equal(h.page.data.ocrProgressState,'failed');assert.equal(h.page.ocrPolling,false);
 assert.ok(h.page.data.ocrStatus.includes(code));assert.ok(h.page.data.ocrStatus.includes(phrases[outcome]));
 assert.equal(h.page.data.ocrDiagnostic,null);assert.ok(!h.page.data.ocrStatus.includes(privateValue));
 assert.equal(h.page.data.ocrConfirmed,false);assert.ok(!h.page.ocrTimer);
 result.push({code,outcome,status:h.page.data.ocrStatus,actions:actions(h),diagnostic:h.page.data.ocrDiagnostic});
});
test('unknown, private, prototype-named, missing and malformed fields never render raw strings',async()=>{
 for(const code of [undefined,null,privateValue,'constructor','__proto__',{},['ALIYUN_HTTP_ERROR'],42]){
  const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:code,failure_outcome:privateValue,message:privateValue,warnings:[privateValue],provider_request_id:privateValue}});await manual(h);
  assert.match(h.page.data.ocrStatus,/识别任务失败或已中断/);assert.ok(!h.page.data.ocrStatus.includes(privateValue));assert.ok(!h.page.data.ocrStatus.includes('失败分类'));assert.equal(h.page.data.ocrDiagnostic,null);
 }
});
test('missing, malformed or contradictory outcome never claims not-sent or a received response',async()=>{
 for(const outcome of [undefined,null,privateValue,'not_sent','response_received',{},[]]){
  const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:'ALIYUN_CALL_OUTCOME_UNKNOWN',failure_outcome:outcome}});await manual(h);
  assert.match(h.page.data.ocrStatus,/ALIYUN_CALL_OUTCOME_UNKNOWN/);assert.match(h.page.data.ocrStatus,/本次调用状态尚未核实/);
  assert.ok(!h.page.data.ocrStatus.includes('本次失败发生在调用前'));assert.ok(!h.page.data.ocrStatus.includes('已收到识别服务响应'));assert.ok(!h.page.data.ocrStatus.includes(privateValue));
 }
});
test('pending request diagnostic cannot masquerade as the final failed-job diagnostic',async()=>{
 const h=await harness({remote:saved(),submitPendingOnce:true,resultStatus:'failed',payloadExtra:{error_code:'ALIYUN_CALL_OUTCOME_UNKNOWN',failure_outcome:'unknown'}});
 await manual(h);assert.equal(h.page.data.ocrDiagnostic.reason,'REQUEST_IN_PROGRESS');await manual(h);
 assert.equal(h.page.data.ocrProgressState,'failed');assert.equal(h.page.data.ocrDiagnostic,null);
 assert.deepEqual(actions(h),['login','recover_view','submit','submit','read']);assert.equal(new Set(h.calls.filter(c=>c.action==='submit').map(c=>c.params.idempotency_key)).size,1);
});
test('repeat clicks and duplicate reads retain same job without a new OCR submit',async()=>{
 const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:'ALIYUN_HTTP_ERROR',failure_outcome:'response_received'}});await manual(h);const key=h.page.ocrCapture.idempotency_key;
 await Promise.all([manual(h),manual(h)]);await manual(h);assert.equal(h.page.ocrCapture.idempotency_key,key);
 assert.equal(h.calls.filter(c=>c.action==='submit').length,1);assert.equal(h.page.ocrPolling,false);assert.ok(actions(h).filter(a=>a!=='login'&&a!=='recover_view'&&a!=='submit').every(a=>a==='read'));
});
test('successful and processing results do not show failed classifications',async()=>{
 for(const status of ['needs_review','processing','queued']){
  const h=await harness({remote:saved(),resultStatus:status,payloadExtra:{error_code:'ALIYUN_HTTP_ERROR',failure_outcome:'response_received'}});await manual(h);
  assert.ok(!h.page.data.ocrStatus.includes('ALIYUN_HTTP_ERROR'));assert.ok(!h.page.data.ocrStatus.includes('失败分类'));
  assert.equal(h.page.ocrPolling,['processing','queued'].includes(status));
 }
});
test('failed exact recovery remains existing error route, no invented failed recovery view',async()=>{
 const diagnostic={version:1,diagnostic_id:'d'.repeat(32),stage:'RESULT_READ',reason:'RESULT_READ_FAILED',retryable:false,request_retained:true};
 const h=await harness({remote:saved(),recoveryDiagnostic:diagnostic});await manual(h);
 assert.deepEqual(actions(h),['login','recover_view']);assert.equal(h.page.data.ocrDiagnostic.diagnostic_id,'d'.repeat(32));assert.equal(h.page.data.ocrDiagnostic.reason,'RESULT_READ_FAILED');assert.equal(h.page.ocrPolling,false);
});
for(const [label,change] of Object.entries({application:({page})=>page.data.application.application='changed',revision:({page})=>page.data.application.revision++,material:({page})=>page.data.application.materials.business_license.sha256='a'.repeat(64),scene:({page})=>page.scene='changed',session:({session})=>session.clear(),dirty:({page})=>page.data.dirty=true}))test('stale '+label+' read does not expose failure details',async()=>{
 const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:'ALIYUN_HTTP_ERROR',failure_outcome:'response_received'},onReadReply:change});await manual(h);
 assert.ok(!h.page.data.ocrStatus.includes('ALIYUN_HTTP_ERROR'));assert.equal(h.calls.filter(c=>c.action==='submit').length,1);
});
test('read permission refusal does not display result or launch replacement job',async()=>{
 const h=await harness({remote:saved(),resultStatus:'failed',payloadExtra:{error_code:'ALIYUN_HTTP_ERROR',failure_outcome:'response_received'},readDenied:true});await manual(h);
 assert.ok(!h.page.data.ocrStatus.includes('ALIYUN_HTTP_ERROR'));assert.equal(h.calls.filter(c=>c.action==='submit').length,1);assert.equal(h.page.ocrPolling,false);
});
