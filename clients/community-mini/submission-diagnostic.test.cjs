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
