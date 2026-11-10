'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {safeSubmissionDiagnostic,submissionDiagnosticFeedback}=require('./submission-diagnostic');
const {createSession}=require('./session');
const value={operation:'wechat_apply',stage:'PROVIDER_POST',correlation_id:'a'.repeat(32),timestamp:1794270000,status:'FAILED',code:'PROVIDER_RESULT_UNKNOWN'};
test('fixed diagnostic roundtrip contains only approved fields',()=>{assert.deepEqual(safeSubmissionDiagnostic(value),value);assert.match(submissionDiagnosticFeedback({submissionDiagnostic:value}),/PROVIDER_RESULT_UNKNOWN/);});
for(const [key,v] of [['operation','secret'],['stage','secret'],['code','secret'],['correlation_id','token'],['timestamp',Infinity],['status','secret'],['address','secret']])test('invalid diagnostic '+key+' is discarded entirely',()=>{assert.equal(safeSubmissionDiagnostic({...value,[key]:v}),null);assert.equal(submissionDiagnosticFeedback({submissionDiagnostic:{...value,[key]:v}}),'');});
test('session exposes only validated diagnostic and never retries provider request',async()=>{
 let count=0;const wx={login:o=>o.success({code:'synthetic'}),request:o=>{
  if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
  count++;o.success({statusCode:408,data:{error:'REQUEST_TIMEOUT',secret:'NEVER_RETAIN',submission_diagnostic:value}});
 }};
 const s=createSession(wx,'https://example.org',()=>100);await s.login();
 await assert.rejects(s.merchant('shop1','onboarding',{operation:'wechat_apply',params:{application:'synthetic',expected_version:1}}),e=>{assert.deepEqual(e.submissionDiagnostic,value);assert.doesNotMatch(JSON.stringify(e),/NEVER_RETAIN/);return true;});assert.equal(count,1);
});
for(const stage of ['REQUEST_BODY','BODY_PARSE'])test('authenticated body stage remains visible: '+stage,()=>{const diagnostic={...value,operation:'UNKNOWN',stage,code:'INVALID_REQUEST'};assert.deepEqual(safeSubmissionDiagnostic(diagnostic),diagnostic);assert.match(submissionDiagnosticFeedback({submissionDiagnostic:diagnostic}),new RegExp(stage));});
const profileValue={...value,stage:'PROFILE',code:'PROFILE_CHECK_FAILED',profile_issue:{reason:'MISSING_OFFICIAL_FIELDS',fields:['contact_info.contact_email']}};
test('profile diagnosis shows only fixed reason and field paths; legacy six keys still accepted',()=>{
 assert.deepEqual(safeSubmissionDiagnostic(profileValue),profileValue);
 assert.deepEqual(safeSubmissionDiagnostic(value),value);
 const feedback=submissionDiagnosticFeedback({submissionDiagnostic:profileValue});
 assert.match(feedback,/MISSING_OFFICIAL_FIELDS/);assert.match(feedback,/contact_info.contact_email/);
 const saved=safeSubmissionDiagnostic(profileValue);saved.profile_issue.fields.push('contact_info.mobile_phone');assert.equal(profileValue.profile_issue.fields.length,1);
});
for(const issue of [null,[],{reason:'PRIVATE_VALUE',fields:[]},{reason:'MISSING_OFFICIAL_FIELDS',fields:['PRIVATE_VALUE']},{reason:'MISSING_OFFICIAL_FIELDS',fields:['contact_info.contact_email','PRIVATE_VALUE']},{reason:'MISSING_OFFICIAL_FIELDS',fields:['contact_info.contact_email','contact_info.contact_email']},{reason:'MISSING_OFFICIAL_FIELDS',fields:[],value:'PRIVATE_VALUE'},{reason:'MISSING_OFFICIAL_FIELDS',fields:Array(33).fill('contact_info.contact_email')}])test('malformed profile detail is discarded, not displayed '+JSON.stringify(issue),()=>{const v={...profileValue,profile_issue:issue};assert.equal(safeSubmissionDiagnostic(v),null);assert.equal(submissionDiagnosticFeedback({submissionDiagnostic:v}),'');});
for(const change of [{stage:'PROVIDER_POST'},{code:'INVALID_REQUEST'},{status:'SUCCEEDED'}])test('profile detail cannot be attached to other phases '+JSON.stringify(change),()=>assert.equal(safeSubmissionDiagnostic({...profileValue,...change}),null));
test('profile-detail error survives session adapter without retry or private response fields',async()=>{
 let count=0;const wx={login:o=>o.success({code:'synthetic'}),request:o=>{
  if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
  count++;o.success({statusCode:400,data:{error:'INVALID_REQUEST',secret:'NEVER_RETAIN',submission_diagnostic:profileValue}});
 }};
 const s=createSession(wx,'https://example.org',()=>100);await s.login();
 await assert.rejects(s.merchant('shop1','onboarding',{operation:'wechat_apply',params:{application:'synthetic',expected_version:1}}),e=>{assert.deepEqual(e.submissionDiagnostic,profileValue);assert.doesNotMatch(JSON.stringify(e),/NEVER_RETAIN/);return true;});assert.equal(count,1);
});
const {profileValidationDetails}=require('./submission-diagnostic');
const groups=[{id:'contact',title:'联系资料',step:0,items:[{path:'contact_info.contact_email',label:'联系邮箱'},{path:'contact_info.mobile_phone',label:'联系电话'}]},{id:'bank',title:'结算账户',step:2,items:[{path:'bank_account_info.account_name',label:'结算开户名称'}]}];
test('authoritative profile reason maps to original field without replacing applicant data',()=>{
 const result=profileValidationDetails({submissionDiagnostic:profileValue},groups);
 assert.match(result.feedback,/本次资料校验未通过，未发送本次微信进件/);
 assert.equal(result.issues[0].path,'contact_info.contact_email');assert.equal(result.issues[0].group,'contact');assert.equal(result.issues[0].step,0);assert.match(result.issues[0].message,/联系邮箱/);
});
test('internal profile exception never asks owner to fill all fields again',()=>{const result=profileValidationDetails({submissionDiagnostic:{...profileValue,profile_issue:{reason:'LOCAL_TYPE_ERROR',fields:[]}}},groups);assert.match(result.feedback,/内部.*不必重新填写/);assert.deepEqual(result.issues,[]);});
test('legacy PROFILE triple is identified as pre-POST without guessing a field',()=>{const legacy={...profileValue};delete legacy.profile_issue;const result=profileValidationDetails({submissionDiagnostic:legacy},groups);assert.match(result.feedback,/未发送本次微信进件/);assert.match(result.feedback,/具体原因尚未确定/);assert.deepEqual(result.issues,[]);});
for(const diagnostic of [value,{...profileValue,operation:'read'},{...profileValue,stage:'PROVIDER_POST'},null])test('uncertain or other operation must not claim pre-POST '+JSON.stringify(diagnostic),()=>assert.equal(profileValidationDetails({submissionDiagnostic:diagnostic},groups),null));
function feedbackPage(){
 const fs=require('node:fs'),vm=require('node:vm');let page;
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8'),{Page:v=>{page=v;},require:p=>p==='../../session'?require('./session'):p==='../../customer-auth'?{}:(()=>{throw Error('not needed');})()});
 page.data=structuredClone(page.data);page.data.reviewGroups=groups;page.profile={preserved:'SYNTHETIC_PRIVATE_ORIGINAL'};
 page.setData=function(values){Object.assign(this.data,values);};page.current=()=>!page.dead;page.finishConfirmedOcrSave=async()=>{};page.presentStepOcrReview=()=>{};
 return page;
}
test('actual page distinguishes local PROFILE rejection, retains values and never retries',async()=>{
 const page=feedbackPage();let attempts=0;const error=Object.assign(Error('INVALID_REQUEST'),{submissionDiagnostic:profileValue});
 await page.run(async()=>{attempts++;throw error;},'提交审核');
 assert.equal(attempts,1);assert.equal(page.profile.preserved,'SYNTHETIC_PRIVATE_ORIGINAL');assert.equal(page.data.pending,false);
 assert.match(page.data.status,/未发送本次微信进件/);assert.match(page.data.status,/未自动重试/);assert.doesNotMatch(page.data.status,/提交进度尚未核实|当前提示不代表微信已受理|请先重新读取原申请|SYNTHETIC_PRIVATE/);
 assert.equal(page.data.submitIssues[0].path,'contact_info.contact_email');
});
test('actual page keeps provider result unknown query-only message with no automatic replay',async()=>{
 const page=feedbackPage();let attempts=0;
 await page.run(async()=>{attempts++;throw Object.assign(Error('REQUEST_TIMEOUT'),{submissionDiagnostic:value});},'提交审核');
 assert.equal(attempts,1);assert.match(page.data.status,/提交进度尚未核实/);assert.match(page.data.status,/勿重复提交/);assert.doesNotMatch(page.data.status,/未发送本次微信进件/);assert.equal(page.profile.preserved,'SYNTHETIC_PRIVATE_ORIGINAL');
});
test('page logout/leave suppresses stale profile failure, and repeated pending click is not replayed',async()=>{
 const page=feedbackPage();let attempts=0,release;
 const work=page.run(async()=>{attempts++;await new Promise(r=>release=r);throw Object.assign(Error('INVALID_REQUEST'),{submissionDiagnostic:profileValue});},'提交审核');
 await page.run(async()=>{attempts++;},'提交审核');assert.equal(attempts,1);page.dead=true;release();await work;
 assert.doesNotMatch(page.data.status,/PROFILE_CHECK_FAILED|未发送本次微信进件/);assert.equal(page.data.submitIssues.length,0);
});
for(const change of ['session','epoch','application','scene','generation'])test('old PROFILE failure cannot overwrite newer '+change+' view or pending state',async()=>{
 const page=feedbackPage();let generation=1,release;page.session={getGeneration:()=>generation};page.epoch=1;page.scene='shop1';page.data.application={application:'original'};
 const work=page.run(async()=>{await new Promise(r=>release=r);throw Object.assign(Error('INVALID_REQUEST'),{submissionDiagnostic:profileValue});},'提交审核');
 if(change==='session')page.session={getGeneration:()=>1};if(change==='epoch')page.epoch=2;if(change==='application')page.data.application={application:'new'};if(change==='scene')page.scene='shop2';if(change==='generation')generation++;
 page.setData({status:'NEWER_REQUEST_PENDING',pending:true,submitIssues:[]});release();await work;
 assert.equal(page.data.status,'NEWER_REQUEST_PENDING');assert.equal(page.data.pending,true);assert.equal(page.data.submitIssues.length,0);
});
test('group-level contact format and media diagnostics navigate the actual existing cards',()=>{
 const view=[{id:'applicant',title:'办理人',step:0,items:[{path:'contact_info.contact_type',label:'办理人类型'}]},...groups,{id:'mini',title:'小程序',step:1,items:[{path:'material:mini_program_screenshot',label:'截图'}]},{id:'store',title:'实体门店',step:1,items:[{path:'material:storefront_photo',label:'门头'}]}];
 for(const [reason,path,group] of [['INVALID_OFFICIAL_TEXT','contact_info','contact'],['INVALID_OFFICIAL_MEDIA_LIST','business_info.sales_info.mini_program_info.mini_program_pics','mini'],['INVALID_OFFICIAL_MEDIA_LIST','business_info.sales_info.biz_store_info.store_entrance_pic','store']]){
  const result=profileValidationDetails({submissionDiagnostic:{...profileValue,profile_issue:{reason,fields:[path]}}},view);assert.equal(result.issues[0].group,group);
 }
});
