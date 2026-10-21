'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {endpoint,verifyReadiness}=require('../deploy/community-preview/endpoint.cjs');
const {createSession}=require('../clients/community-mini/session.js');
test('UK prefix carries code-only login, scoped business and logout on same base',async()=>{
 const target=endpoint('uk-path-candidate'),calls=[];
 const wx={login:o=>o.success({code:'synthetic-once'}),request:o=>{
  calls.push(o);
  o.success({statusCode:200,data:{payment_enabled:false,result:o.url.endsWith('/mini/login')?
   {session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}:{simulation_only:true}}});
 }};
 const s=createSession(wx,target.baseUrl,()=>100);
 await s.login();await s.transport('shop1',{operation:'community.storefront',params:{}});await s.logout();
 assert.deepEqual(calls.map(x=>x.url),['/mini/login','/mini/api','/mini/logout'].map(x=>target.baseUrl+x));
 assert.deepEqual(calls[0].data,{code:'synthetic-once'});
 assert.equal(calls[1].header['X-Community-Session'],'s'.repeat(32));
});
test('only exact UK prefix is admitted, malformed roots and alternate paths denied before I/O',()=>{
 for(const base of ['https://uk.wenwenwenyiyiyi.work/community-preview/','https://uk.wenwenwenyiyiyi.work/other',
  'https://evil.invalid/community-preview','http://uk.wenwenwenyiyiyi.work/community-preview',
  'https://uk.wenwenwenyiyiyi.work/community-preview?x=1','https://uk.wenwenwenyiyiyi.work/community-preview#x',
  'https://uk.wenwenwenyiyiyi.work/community-preview/../mini','https://uk.wenwenwenyiyiyi.work/%63ommunity-preview',
  'https://user@uk.wenwenwenyiyiyi.work/community-preview','https://uk.wenwenwenyiyiyi.work:444/community-preview']){
  assert.throws(()=>createSession({},base),/TRUSTED_BACKEND_REQUIRED/);
 }
 assert.throws(()=>endpoint('unknown'),/EXACT_PREVIEW_PROFILE_REQUIRED/);
});
test('health proof is bound to exact target, source and freshness; UNKNOWN never qualifies',()=>{
 const target=endpoint('uk-path-candidate'),head='a'.repeat(40);
 const report={...target,status:'BACKEND_HEALTH_VERIFIED',http_status:200,login_verified:false,customer_acceptance:false,
  payment_enabled:false,source_sha:head,observed_at:100};
 verifyReadiness(report,target,head,100);
 for(const patch of [{...endpoint('legacy')},{status:'BACKEND_NOT_READY'}, {http_status:503}, {source_sha:'b'.repeat(40)},
  {observed_at:701},{observed_at:-501},{login_verified:true},{customer_acceptance:true},{payment_enabled:true}]){
  assert.throws(()=>verifyReadiness({...report,...patch},target,head,100),/MATCHING_FRESH_BACKEND_READINESS_REQUIRED/);
 }
 assert.throws(()=>verifyReadiness(report,target,null,100));
});
test('UNKNOWN login at UK prefix is not replayed and cannot reach business',async()=>{
 let calls=0;
 const s=createSession({login:o=>o.success({code:'synthetic-once'}),request:o=>{calls++;o.fail();}},endpoint('uk-path-candidate').baseUrl);
 await assert.rejects(s.login(),/SERVICE_RESULT_UNKNOWN/);
 assert.equal(calls,1);
 await assert.rejects(s.transport('shop1',{}),/SESSION_EXPIRED/);
 assert.equal(calls,1);
});
