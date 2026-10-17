const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function page(failProducts=false,receipt=null){
 let definition;const calls=[];
 const session={login:async()=>{},clear:()=>{},transport:async()=>{},payment:async()=>{},commerce:async(scene,operation,params)=>{calls.push({scene,operation,params});if(operation==='products'){if(failProducts)throw Error('暂停交易');return {products:[]};}if(operation==='receipt_ad'){if(typeof receipt==='function')return receipt(scene,params);return {payment_success_verified:false,creative:null};}if(operation==='communities')return {records:[{id:'co_fixture',name:'fixture'}],has_more:false,next_cursor:null};return {community_id:'co_fixture',active:true};}};
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{Page:value=>{definition=value;},require:path=>path==='../../client'?{makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})}:path==='../../payment'?{createPaymentFlow:()=>({reset(){}})}:{parseScene:o=>o.scene,createSession:()=>session},getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid',commerce:true,payments:true}}),wx:{}});
 const result={...definition,data:{...definition.data},setData(values){Object.assign(this.data,values);}};
 return {result,calls};
}
test('paused storefront keeps original order recovery and after-sales available',async()=>{
 const {result,calls}=page(true);await result.onLoad({scene:'shop1'});
 assert.equal(result.data.commerceEnabled,true);assert.equal(result.data.paymentsEnabled,true);assert.ok(result.paymentFlow);assert.ok(result.client);
 assert.deepEqual(calls.map(c=>c.operation),['products']);
});
test('promotion URL prefill does not join until authenticated consumer confirms',async()=>{
 const {result,calls}=page();const code='cp_'+'a'.repeat(32);await result.onLoad({scene:'shop1',promotion:code});
 assert.equal(result.data.promotionCode,code);assert.deepEqual(calls.map(c=>c.operation),['products']);
 await result.communityAction({currentTarget:{dataset:{operation:'promotion_redeem'}}});
 assert.equal(calls.at(-1).operation,'promotion_redeem');assert.equal(calls.at(-1).params.code,code);assert.equal(result.data.communityId,'co_fixture');
});


test('simulated or pending provider result never requests verified success creative',async()=>{
 const {result,calls}=page(false,()=>({payment_success_verified:true,creative:{title:'must not display'}}));
 await result.onLoad({scene:'shop1'});result.setData({reference:'order1'});
 await result.showPayment({provider_state:'PROCESSING',amount_minor:101});
 assert.equal(result.data.afterAd,'');assert.equal(result.data.afterAdVerified,false);
 assert.equal(calls.filter(c=>c.operation==='receipt_ad').length,0);
});
test('signed success advertisement is scoped to current reference',async()=>{
 const {result,calls}=page(false,(scene,params)=>({payment_success_verified:true,creative:{title:'verified fixture'}}));
 await result.onLoad({scene:'shop1'});result.setData({reference:'order1'});
 await result.showPayment({provider_state:'SUCCESS',amount_minor:101});
 assert.equal(result.data.afterAd,'verified fixture');assert.equal(result.data.afterAdVerified,true);
 assert.deepEqual(calls.at(-1).params,{reference:'order1'});
});
test('unverified or unavailable creative never changes paid status',async()=>{
 for(const mode of ['unverified','error']){
  const {result}=page(false,()=>{if(mode==='error')throw Error('ads offline');return {payment_success_verified:false,creative:{title:'forged'}};});
  await result.onLoad({scene:'shop1'});result.setData({reference:'order1'});
  await result.showPayment({provider_state:'SUCCESS',amount_minor:101});
  assert.equal(result.data.afterAd,'');assert.equal(result.data.afterAdVerified,false);
  assert.match(result.data.status,/微信查单已支付/);
 }
});
