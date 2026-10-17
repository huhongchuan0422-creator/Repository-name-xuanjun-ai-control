const {test}=require('node:test');const assert=require('node:assert/strict');
const {parseScene,createSession}=require('./session');
function fixture(change=x=>x){
 const calls=[];let clock=100;
 const wx={login:o=>{calls.push('wx.login');o.success({code:'oncecode'});},request:o=>{
  calls.push(o);let result=o.url.endsWith('/mini/login')?{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}:o.url.endsWith('/mini/logout')?{logged_out:true}:{simulation_only:true};
  o.success({statusCode:200,data:change({result,payment_enabled:false})});
 }};
 return{calls,session:createSession(wx,'https://example.org',()=>clock),time:n=>clock=n};
}
test('strict scene parse rejects query injection and malformed escape',()=>{
 assert.equal(parseScene({scene:'shop%31'}),'shop1');
 for(const value of [undefined,'','%ZZ','shop1&tenant_id=x','../shop1','x'.repeat(33)])assert.throws(()=>parseScene({scene:value}));
});
test('wx.login -> code-only request -> in-memory token business transport',async()=>{
 const {calls,session}=fixture();await session.login();const reply=await session.transport('shop1',{operation:'community.storefront',params:{}});
 assert.equal(calls[0],'wx.login');assert.deepEqual(calls[1].data,{code:'oncecode'});
 assert.equal(calls[2].header['X-Community-Session'],'s'.repeat(32));assert.equal(reply.offline_only,true);
 assert.deepEqual(calls[2].data,{scene:'shop1',operation:'community.storefront',params:{}});
});
test('expired or logged-out session cannot request business',async()=>{
 const f=fixture();await f.session.login();f.time(200);await assert.rejects(f.session.transport('shop1',{}),/SESSION_EXPIRED/);
 f.time(100);await f.session.login();await f.session.logout();await assert.rejects(f.session.transport('shop1',{}),/SESSION_EXPIRED/);
});
test('provider session_key or role in reply rejected',async()=>{
 for(const key of ['session_key','role','openid']){const{session}=fixture(r=>({...r,result:{...r.result,[key]:'injected'}}));await assert.rejects(session.login(),/UNTRUSTED_SESSION/);}
});
test('failed login has no retry using same wx code',async()=>{
 let count=0;const wx={login:o=>o.success({code:'oncecode'}),request:o=>{count++;o.fail({errMsg:'sensitive'});}};
 const s=createSession(wx,'https://example.org');await assert.rejects(s.login(),/SERVICE_RESULT_UNKNOWN/);assert.equal(count,1);
 await assert.rejects(s.transport('shop1',{}),/SESSION_EXPIRED/);
});
test('clearing while login in flight drops late result',async()=>{
 let done;const wx={login:o=>o.success({code:'oncecode'}),request:o=>{done=o;}};
 const s=createSession(wx,'https://example.org',()=>100);const pending=s.login();await Promise.resolve();s.clear();
 done.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
 await assert.rejects(pending,/STALE_LOGIN/);
});
