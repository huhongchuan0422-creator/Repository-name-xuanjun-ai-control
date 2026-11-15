'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {createSession,customerError}=require('./session');

for(const status of [400,401,403,404,503])for(const code of ['STOREFRONT_UNAVAILABLE','INVALID_REQUEST','PRIVATE_DETAIL']){
  test(`storefront failure ${status}/${code} classifies only the exact safe reply`,async()=>{
    const calls=[];
    const wx={login:o=>o.success({code:'synthetic'}),request(o){calls.push(o);o.success(o.url.endsWith('/mini/login')?
      {statusCode:200,data:{payment_enabled:false,result:{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:'s'.repeat(32),expires_at:200}}}:
      {statusCode:status,data:{error:code,message:'PRIVATE_DETAIL',scope:'PRIVATE_SCOPE',contact:'PRIVATE_CONTACT'}});}};
    const session=createSession(wx,'https://fixture.invalid',()=>100);await session.login();
    await assert.rejects(session.transport('owner-test-354d1fac',{operation:'community.storefront',params:{}}),error=>{
      const known=status===400&&code==='STOREFRONT_UNAVAILABLE';
      assert.equal(error.storefrontCode,known?'STOREFRONT_UNAVAILABLE':undefined);
      assert.equal(error.message,'SERVICE_REQUEST_REJECTED');
      assert.doesNotMatch(JSON.stringify(error),/PRIVATE/);assert.doesNotMatch(customerError(error),/PRIVATE/);
      if(known)assert.match(customerError(error),/当前门店资料暂不可用.*联系项目负责人核对/);
      else assert.doesNotMatch(customerError(error),/当前门店资料暂不可用/);
      return true;
    });
    assert.equal(calls.length,2);assert.equal(calls[1].timeout,5000);
    assert.deepEqual(calls[1].data,{scene:'owner-test-354d1fac',operation:'community.storefront',params:{}});
  });
}

test('other operations cannot inherit typed storefront failure feedback',async()=>{
  const wx={login:o=>o.success({code:'synthetic'}),request(o){o.success(o.url.endsWith('/mini/login')?
    {statusCode:200,data:{payment_enabled:false,result:{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:'s'.repeat(32),expires_at:200}}}:
    {statusCode:400,data:{error:'STOREFRONT_UNAVAILABLE'}});}};
  const session=createSession(wx,'https://fixture.invalid',()=>100);await session.login();
  for(const call of [()=>session.transport('shop1',{operation:'community.qr',params:{context:'mini'}}),
                    ()=>session.customer('store',{id:'a'.repeat(64)}),
                    ()=>session.merchant('shop1','read',{})]){
    await assert.rejects(call(),error=>{assert.equal(error.storefrontCode,undefined);assert.doesNotMatch(customerError(error),/当前门店资料暂不可用/);return true;});
  }
});
