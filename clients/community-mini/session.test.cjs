const {test}=require('node:test');const assert=require('node:assert/strict');
const {parseScene,createSession}=require('./session');
const {customerError}=require('./session');
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
test('login transport outlasts bounded upstream and classifies failures without replay or raw text',async()=>{
 for(const [message,kind,label] of [
  ['request:fail url not in domain list https://private.invalid/?code=SECRET','DOMAIN','NET_DOMAIN'],
  ['request:fail ssl hand shake error SECRET','TLS','NET_TLS'],
  ['request:fail timeout SECRET','TIMEOUT','NET_TIMEOUT'],
  ['request:fail SECRET',undefined,null]]){
  let calls=0;
  const wx={login:o=>o.success({code:'single-use'}),request:o=>{
   calls++;assert.equal(o.timeout,15000);o.fail({errMsg:message});
  }};
  const session=createSession(wx,'https://uk.wenwenwenyiyiyi.work/community-preview');
  await assert.rejects(session.login(),e=>{
   assert.equal(e.message,'SERVICE_RESULT_UNKNOWN');assert.equal(e.networkKind,kind);
   assert.ok(!JSON.stringify(e).includes('SECRET'));
   const shown=customerError(e);assert.ok(!shown.includes('SECRET'));if(label)assert.ok(shown.includes(label));
   return true;
  });
  assert.equal(calls,1);await assert.rejects(session.commerce('shop1','profile_read',{}),/SESSION_EXPIRED/);
 }
});
test('clearing while login in flight drops late result',async()=>{
 let done;const wx={login:o=>o.success({code:'oncecode'}),request:o=>{done=o;}};
 const s=createSession(wx,'https://example.org',()=>100);const pending=s.login();await Promise.resolve();s.clear();
 done.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
 await assert.rejects(pending,/STALE_LOGIN/);
});
test('payment uses dedicated authenticated endpoint and explicit enabled envelope',async()=>{
 const calls=[];const wx={login:o=>o.success({code:'once'}),request:o=>{calls.push(o);o.success({statusCode:200,data:o.url.endsWith('/mini/login')?{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}:{payment_enabled:true,result:{package:'prepay_id=fixture'}}});}};
 const session=createSession(wx,'https://example.org',()=>100);await session.login();const r=await session.payment('shop1','recover','order1');assert.equal(r.package,'prepay_id=fixture');assert.equal(calls[1].url,'https://example.org/mini/payment');assert.equal(calls[1].header['X-Community-Session'],'s'.repeat(32));assert.deepEqual(calls[1].data,{scene:'shop1',operation:'recover',reference:'order1'});
});
test('payment disabled response or identity change cannot release payment parameters',async()=>{
 let pending;const wx={login:o=>o.success({code:'once'}),request:o=>{if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});else pending=o;}};
 const session=createSession(wx,'https://example.org',()=>100);await session.login();let task=session.payment('shop1','prepare','order1');pending.success({statusCode:200,data:{payment_enabled:false,result:{}}});await assert.rejects(task,/NOT_ENABLED/);task=session.payment('shop1','recover','order1');session.clear();pending.success({statusCode:200,data:{payment_enabled:true,result:{package:'prepay_id=fixture'}}});await assert.rejects(task,/STALE_SESSION/);
});


test('owned success ad uses read-only mini commerce route, not payment operations',async()=>{
 const {calls,session}=fixture();await session.login();
 const result=await session.commerce('shop1','receipt_ad',{reference:'order1'});
 assert.equal(result.simulation_only,true);
 assert.equal(calls[2].url,'https://example.org/mini/api');
 assert.deepEqual(calls[2].data,{scene:'shop1',operation:'commerce.receipt_ad',params:{reference:'order1'}});
 await assert.rejects(session.commerce('shop1','release_funds',{}),/INVALID_COMMERCE_REQUEST/);
});


test('original customer-project requests retain mini session boundary and no reviewer shortcuts',async()=>{
 const {calls,session}=fixture();await session.login();
 for(const [operation,params] of [['project_summary',{}],['project_checklist',{}],
   ['project_feedback',{message:'fixture'}],['project_messages',{}],['project_submit',{item:'requirement1',revision:1}]]) {
   await session.commerce('shop1',operation,params);
   const call=calls[calls.length-1];
   assert.equal(call.url,'https://example.org/mini/api');
   assert.equal(call.header['X-Community-Session'],'s'.repeat(32));
   assert.deepEqual(call.data,{scene:'shop1',operation:'commerce.'+operation,params});
 }
 await assert.rejects(session.commerce('shop1','project_approve',{item:'requirement1',revision:1}),
   /INVALID_COMMERCE_REQUEST/);
});


test('mini reviewer bypass cannot use a customer mini bearer session',async()=>{
 const {session}=fixture();await session.login();
 await assert.rejects(session.commerce('shop1','project_review',
   {item:'material1',revision:2,action:'approve',reason:'forged'}),/INVALID_COMMERCE_REQUEST/);
});
test('only photo upload waits30s while OCR transport15s and ordinary requests5s',async()=>{const f=fixture();await f.session.login();for(const [op,p,timeout] of [['onboarding',{operation:'upload',params:{}},30000],['onboarding',{operation:'read',params:{}},5000],['ocr',{action:'read',application:'synthetic',job_id:'job'},15000],['collection_code',{workspace:'shop'},15000]]){await f.session.merchant('shop1',op,p);assert.equal(f.calls.at(-1).timeout,timeout);}});
test('photo upload timeout reports uncertain upload not failed login and never retries',async()=>{let count=0;const wx={login:o=>o.success({code:'code'}),request:o=>{count++;if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});else o.fail({errMsg:'request:fail timeout'});}};const session=createSession(wx,'https://example.org',()=>100);await session.login();await assert.rejects(session.merchant('shop1','onboarding',{operation:'upload',params:{}}),e=>{assert.equal(e.uploadResultUnknown,true);assert.match(customerError(e),/上传结果暂未确认.*重新读取原申请.*勿重复上传/);assert.doesNotMatch(customerError(e),/重新登录/);return true;});assert.equal(count,2);assert.equal(session.isAuthenticated(),true);await assert.rejects(session.merchant('shop1','onboarding',{operation:'read',params:{}}),e=>{assert.equal(e.uploadResultUnknown,undefined);assert.match(customerError(e),/登录连接超时/);return true;});});

for(const status of [408,502,503,504,400,401,403])for(const operation of ['upload','read'])test(`HTTP ${status} ${operation} preserves exact upload uncertainty and authentication rules`,async()=>{
 const {getSharedSession}=require('./session');const calls=[];
 const wx={login:o=>o.success({code:'synthetic'}),request(o){calls.push(o);o.success(o.url.endsWith('/mini/login')?{statusCode:200,data:{payment_enabled:false,result:{provider:'WECHAT_MINIPROGRAM',session_token:'S'.repeat(32),expires_at:200,payment_enabled:false}}}:{statusCode:status,data:{error:'synthetic failure'}});}};
 const session=getSharedSession(wx,{baseUrl:'https://example.org'},()=>100);await session.ensureLogin();let error;
 try{await session.merchant('shop1','onboarding',{operation,params:{}});}catch(e){error=e;}
 assert.ok(error);const unknown=operation==='upload'&&[408,502,503,504].includes(status);
 assert.equal(error.uploadResultUnknown===true,unknown);assert.equal(session.isAuthenticated(),![401,403].includes(status));assert.equal(calls.length,2);
 if(unknown){assert.match(customerError(error),/上传结果暂未确认.*重新读取原申请.*勿重复上传/);assert.doesNotMatch(customerError(error),/登录/);}
 else assert.notEqual(error.uploadResultUnknown,true);
});
