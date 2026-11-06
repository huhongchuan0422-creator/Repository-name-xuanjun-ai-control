'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {createSession,customerError}=require('./session');
for(const operation of ['submit','wechat_submit_review'])test('typed mini region errors preserve draft/session and never display server address: '+operation,async()=>{
 let calls=0,reason='DIRECTORY_MISMATCH';
 const wx={login:o=>o.success({code:'synthetic'}),request:o=>{calls++;o.success(o.url.endsWith('/mini/login')?{statusCode:200,data:{payment_enabled:false,result:{session_token:'x'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}}:{statusCode:400,data:{error:'MINI_LICENSE_REGION_INVALID',reason,message:'PRIVATE STREET SECRET'}});}};
 const session=createSession(wx,'https://example.invalid',()=>100);await session.login();
 for(const value of ['DIRECTORY_MISMATCH','AMBIGUOUS_ADDRESS','INVALID_REGION_CODE','REGION_CODE_MISMATCH','UNKNOWN_SECRET']){
  reason=value;
  await assert.rejects(session.merchant('','onboarding',{operation,params:{application:'synthetic'}}),e=>{const shown=customerError(e);assert.ok(!shown.includes('SECRET'));assert.equal(e.regionReason,value==='UNKNOWN_SECRET'?undefined:value);if(value==='DIRECTORY_MISMATCH')assert.match(shown,/不要改成旧地名/);else if(value!=='UNKNOWN_SECRET')assert.match(shown,/返回第一步/);return true;});
  assert.equal(session.isAuthenticated(),true);
 }
 assert.equal(calls,6);
});
