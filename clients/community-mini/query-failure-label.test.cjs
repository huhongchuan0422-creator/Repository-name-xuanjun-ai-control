'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.QUERY_LABEL_SOURCE||__dirname;
const {submitApplicantApplication:submit}=require(path.join(root,'merchant-submit'));
const id='a'.repeat(32),privateValue='PRIVATE_error_body_not_for_UI';
const diagnostic=(operation='wechat_status')=>({operation,stage:operation==='wechat_status'?'PROVIDER_QUERY':'PROVIDER_POST',code:operation==='wechat_status'?'SERVICE_UNAVAILABLE':'PROVIDER_RESULT_UNKNOWN',correlation_id:id,timestamp:1794679200,status:'FAILED'});
function failure(d=diagnostic()){return Object.assign(Error(privateValue),{submissionDiagnostic:d});}
function page(){let definition;vm.runInNewContext(fs.readFileSync(path.join(root,'pages/merchant-join/index.js'),'utf8'),{Page:x=>definition=x,require:p=>['../../session','../../chain-telemetry'].includes(p)?require(path.join(root,p.slice(6))):{},wx:{}});return {...definition,data:{pending:false,application:{application:'synthetic'}},current:()=>true,setData(v){Object.assign(this.data,v);},finishConfirmedOcrSave:async()=>{},presentStepOcrReview:()=>{}};}
for(const reviewState of ['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'])test(reviewState+' original submit controller only queries and failure says query',async()=>{
 const p=page(),calls=[];const state={application:'synthetic',revision:1,version:1,platformState:'SUBMITTED',reviewState};
 await p.run(()=>submit({read:async()=>{calls.push('read');return {...state};},current:()=>true,submitProvider:async()=>{calls.push('POST');assert.fail('must not post');},queryProvider:async()=>{calls.push('query');throw failure();}}),'提交审核');
 assert.deepEqual(calls,['read','query']);assert.match(p.data.status,/^查询原申请进度失败：/);assert.doesNotMatch(p.data.status,/提交审核失败|PRIVATE/);assert.ok(p.data.status.includes('wechat_status/PROVIDER_QUERY/SERVICE_UNAVAILABLE'));assert.ok(p.data.status.includes(id));assert.match(p.data.status,/不代表微信已受理或未受理/);assert.match(p.data.status,/勿重复提交/);assert.equal(p.data.pending,false);
});
test('new submission failure remains submission failure and original unknown handling',async()=>{
 const p=page();await p.run(async()=>{throw failure(diagnostic('wechat_apply'));},'提交审核');
 assert.match(p.data.status,/^提交审核失败：/);assert.doesNotMatch(p.data.status,/查询原申请进度失败|PRIVATE/);assert.ok(p.submitUnknownUntil>Date.now());assert.equal(p.submitUnknownApplication,'synthetic');assert.ok(p.data.status.includes(id));
});
for(const d of [null,{operation:'wechat_status'},{...diagnostic(),correlation_id:'PRIVATE'},{...diagnostic(),extra:privateValue}])test('invalid diagnostic cannot reclassify label '+JSON.stringify(d),async()=>{
 const p=page();await p.run(async()=>{throw failure(d);},'提交审核');assert.match(p.data.status,/^提交审核失败：/);assert.doesNotMatch(p.data.status,/查询原申请进度失败|PRIVATE|编号/);
});
test('material upload stage remains unchanged even with valid status diagnostic',async()=>{const p=page();await p.run(async()=>{throw failure();},'照片上传');assert.match(p.data.status,/^照片上传失败：/);assert.ok(p.data.status.includes(id));assert.doesNotMatch(p.data.status,/查询原申请进度失败|PRIVATE/);});
test('preflight wording is not relabelled by a query diagnostic',async()=>{const p=page();await p.run(async()=>{throw Object.assign(Error('合成必填项'),{submitPreflight:true,submissionDiagnostic:diagnostic()});},'提交审核');assert.match(p.data.status,/^提交审核未完成：合成必填项/);assert.doesNotMatch(p.data.status,/查询原申请进度失败/);});
test('rendering does not change the original exception or diagnostic',async()=>{const p=page(),e=failure(),before=JSON.stringify(e);await p.run(async()=>{throw e;},'提交审核');assert.equal(JSON.stringify(e),before);assert.equal(e.message,privateValue);});
