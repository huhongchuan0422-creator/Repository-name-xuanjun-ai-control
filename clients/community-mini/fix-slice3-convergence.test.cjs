'use strict';
// 切片v3回归：收敛只认 provider 回读观察值；文案按 request_retained 条件化；UNEXPECTED_FAILURE 入桶。
// 修复 C（身份证四字段去重）结构护栏同置本件，防后续切片无声回退。
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const ROOT=__dirname;
const {errorBucket,readbackReconciled,shouldBlockResubmit,SUBMIT_READBACK_COOLDOWN_MS,OCR_STAGES}=require('./chain-telemetry');
const {customerError,safeOcrDiagnostic}=require('./session');

function loadPage(){
 let definition;
 vm.runInNewContext(fs.readFileSync(path.join(ROOT,'pages/merchant-join/index.js'),'utf8'),{
  Page:v=>definition=v,
  require:p=>p==='../../session'?{customerError:()=>'SYNTHETIC ERROR',parseScene:()=> 'shop1',getSharedSession:()=>({})}:
   p==='../../customer-auth'?{current:()=>1,active:()=>true,navigate(){}}:
   require(path.join(ROOT,p.replace('../../',''))),
  getApp:()=>({globalData:{}}),
  wx:{pageScrollTo(o){if(o&&o.success)o.success({});}},
  Date,Math,structuredClone,
  setTimeout(fn,ms){return 0;},clearTimeout(id){},
 });
 const page={...definition,data:structuredClone(definition.data)};
 page.setData=function(value){Object.assign(page.data,value);};
 return page;
}
const queueDiag=(retained,retryable)=>safeOcrDiagnostic({version:1,diagnostic_id:'b'.repeat(32),stage:'QUEUE',reason:'UNEXPECTED_FAILURE',retryable:retryable===undefined?false:retryable,request_retained:retained});

test('收敛白名单：本地平台态（SUBMITTED/IN_REVIEW/APPROVED）不得视为微信已确认',()=>{
 assert.equal(readbackReconciled({reviewState:'SUBMITTED'}),false);
 assert.equal(readbackReconciled({reviewState:'IN_REVIEW'}),false);
 assert.equal(readbackReconciled({reviewState:'APPROVED'}),false);
 assert.equal(readbackReconciled({reviewState:'SUBMISSION_UNKNOWN'}),false);
});

test('收敛白名单：provider 回读观察态域（进件审核实测态）仍算收敛',()=>{
 for(const s of ['SUBMITTED_TO_PROVIDER','CORRECTION'])
  assert.equal(readbackReconciled({reviewState:s}),true,s);
 assert.equal(readbackReconciled(null),false);
});

test('页面级：冷却窗口内本地 SUBMITTED 回读不清态（仅 SUBMIT_05 回读）',()=>{
 const page=loadPage();
 page.data.application={application:'APP-S3'};
 page.submitUnknownUntil=Date.now()+SUBMIT_READBACK_COOLDOWN_MS;
 page.submitUnknownApplication='APP-S3';
 page.reconcileSubmitReadback({reviewState:'SUBMITTED'});
 assert.ok(page.submitUnknownUntil>0,'未核实态必须保留');
 assert.equal(page.submitUnknownApplication,'APP-S3');
 const snaps=page.chainTelemetry.snapshot();
 assert.equal(snaps.at(-1).stage,'SUBMIT_05');
 assert.ok(!snaps.some(e=>e.stage==='SUBMIT_06'),'不得误记 RECONCILED');
});

test('页面级：冷却到期本身不是确认——无 provider 收敛观察值则保持未核实与仅回读，不自动重提',()=>{
 const page=loadPage();
 page.data.application={application:'APP-S3'};
 page.submitUnknownUntil=Date.now()-1; // 已到期
 page.submitUnknownApplication='APP-S3';
 const calls=[];
 page.request=(op)=>{calls.push(op);return Promise.resolve({});};
 page.reconcileSubmitReadback({reviewState:'SUBMISSION_UNKNOWN'});
 assert.ok(page.submitUnknownUntil>0&&page.submitUnknownUntil<Date.now(),'保持未核实（到期态不清零、不刷新）');
 assert.equal(calls.length,0,'回读收敛路径不得触发任何提交类请求');
 assert.equal(page.chainTelemetry.snapshot().at(-1).stage,'SUBMIT_05');
});

test('页面级：到期后回读到 provider 实测收敛态才清态并记 SUBMIT_06',()=>{
 const page=loadPage();
 page.data.application={application:'APP-S3'};
 page.submitUnknownUntil=Date.now()-1;
 page.submitUnknownApplication='APP-S3';
 page.reconcileSubmitReadback({reviewState:'SUBMITTED_TO_PROVIDER'});
 assert.equal(page.submitUnknownUntil,0);
 assert.equal(page.submitUnknownApplication,null);
 assert.equal(page.chainTelemetry.snapshot().at(-1).stage,'SUBMIT_06');
});

test('后端防重原样保留：窗口内拒发、窗口外放行（shouldBlockResubmit 与 assertSubmitCooldown 未改）',()=>{
 const now=Date.now();
 assert.equal(shouldBlockResubmit({until:now+1,application:'A'},now),true);
 assert.equal(shouldBlockResubmit({until:now-1,application:'A'},now),false);
 const page=loadPage();
 page.data.application={application:'APP-S3'};
 page.submitUnknownUntil=now+SUBMIT_READBACK_COOLDOWN_MS;
 page.submitUnknownApplication='APP-S3';
 assert.throws(()=>page.assertSubmitCooldown('wechat_apply'),/仅允许回读/);
 page.submitUnknownUntil=now-1;
 page.assertSubmitCooldown('wechat_apply'); // 到期后按原 5min 窗口口径放行（本切片不改）
});

test('noteSubmitOutcome 不变：仅 PROVIDER_RESULT_UNKNOWN 起 5min 冷却并绑定申请号',()=>{
 const page=loadPage();
 page.data.application={application:'APP-S3'};
 page.noteSubmitOutcome({submissionDiagnostic:{operation:'wechat_apply',code:'OTHER_FAILURE',stage:'PROVIDER_POST'}});
 assert.equal(page.submitUnknownUntil,undefined);
 page.noteSubmitOutcome({submissionDiagnostic:{operation:'wechat_apply',code:'PROVIDER_RESULT_UNKNOWN',correlation_id:'c'.repeat(32),stage:'PROVIDER_POST'}});
 assert.ok(page.submitUnknownUntil>=Date.now()+SUBMIT_READBACK_COOLDOWN_MS-2000);
 assert.equal(page.submitUnknownApplication,'APP-S3');
 const snap=page.chainTelemetry.snapshot().at(-1);
 assert.equal(snap.stage,'SUBMIT_04');
 assert.equal(snap.bucket,'result_unknown');
});

test('文案条件化：request_retained=false 说「未建立/未保留，需重新上传」且不自动上传；true/未知保留原文案',()=>{
 const falseText=customerError({message:'OCR_EMPTY_RESPONSE',ocrCode:'OCR_EMPTY_RESPONSE',ocrDiagnostic:queueDiag(false)});
 assert.match(falseText,/未建立/);
 assert.match(falseText,/未被保留/);
 assert.match(falseText,/重新上传/);
 assert.match(falseText,/不会自动上传/);
 assert.ok(!falseText.includes('已保留'),'不得声称原任务已保留');
 const trueText=customerError({message:'OCR_EMPTY_RESPONSE',ocrCode:'OCR_EMPTY_RESPONSE',ocrDiagnostic:queueDiag(true)});
 assert.equal(trueText,'识别服务本次返回空结果，原识别任务已保留，正在继续自动查询；无需重新上传。');
 const noDiag=customerError({message:'OCR_EMPTY_RESPONSE',ocrCode:'OCR_EMPTY_RESPONSE'});
 assert.ok(noDiag.includes('原识别任务已保留'),'无回读观察值时维持原文案（如实：未证伪保留）');
});

test('UNEXPECTED_FAILURE 入错误码桶（internal），冻结枚举未改',()=>{
 assert.equal(errorBucket('UNEXPECTED_FAILURE'),'internal');
 assert.equal(errorBucket('自由文本不入库'),'unclassified');
 assert.deepEqual([...OCR_STAGES],['OCR_01','OCR_02','OCR_03','OCR_04','OCR_05']);
 assert.ok(queueDiag(false)!==null,'safeOcrDiagnostic 仍接受 UNEXPECTED_FAILURE@QUEUE 白名单观察值');
});

test('修复 C 结构护栏：wxml 只读卡仍排除 ocrInReview，视图模型仍计算该标志',()=>{
 const wxml=fs.readFileSync(path.join(ROOT,'pages/merchant-join/index.wxml'),'utf8');
 assert.ok(wxml.includes('item.ocrResultPresent && !item.ocrInReview'),'身份证四字段去重条件不得回退');
 const js=fs.readFileSync(path.join(ROOT,'pages/merchant-join/index.js'),'utf8');
 assert.ok(js.includes('ocrInReview:'),'ocrInReview 计算必须保留');
});


test('internal review states never clear unknown submission, before or after cooldown',()=>{
 for(const reviewState of ['PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED']){
  assert.equal(readbackReconciled({reviewState}),false);
  for(const offset of [-1,300000]){
   const page=loadPage();page.data.application={application:'APP-LOCAL'};
   const until=Date.now()+offset;page.submitUnknownUntil=until;page.submitUnknownApplication='APP-LOCAL';
   page.reconcileSubmitReadback({reviewState});
   assert.equal(page.submitUnknownUntil,until);assert.equal(page.submitUnknownApplication,'APP-LOCAL');
   assert.equal(page.chainTelemetry.snapshot().at(-1).stage,'SUBMIT_05');
   assert.ok(!page.chainTelemetry.snapshot().some(x=>x.stage==='SUBMIT_06'));
  }
 }
});

// Regression: diagnostic takes precedence over the empty-response fallback.
test('OCR wait preserves server error bucket and correlation without retaining private fields',()=>{
 const page=loadPage();page.updateOcrView=()=>{};
 page.waitForOcr({ocrDiagnostic:{version:1,diagnostic_id:'b'.repeat(32),stage:'QUEUE',reason:'UNEXPECTED_FAILURE',retryable:false,request_retained:false,private_field:'DO_NOT_RETAIN'}});
 const event=page.chainTelemetry.snapshot().at(-1);
 assert.equal(event.bucket,'internal');assert.equal(event.correlation,'b'.repeat(16));
 assert.ok(!JSON.stringify(event).includes('DO_NOT_RETAIN'));
});
test('OCR empty response fallback applies only without a server diagnostic',()=>{
 const page=loadPage();page.updateOcrView=()=>{};page.waitForOcr({ocrCode:'OCR_EMPTY_RESPONSE'});
 assert.equal(page.chainTelemetry.snapshot().at(-1).bucket,'empty_response');
});

test('unified visible editor forwards ordinary non-review fields unchanged',()=>{
 const page=loadPage();let actual;page.inputUnifiedField=e=>{actual=e;};
 const event={currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'SYNTHETIC'}};
 page.editStepOcrReview(event);assert.equal(actual,event);
});
