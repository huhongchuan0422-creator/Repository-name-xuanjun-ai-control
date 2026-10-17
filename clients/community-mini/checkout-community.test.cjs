const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function page(failProducts=false){
 let definition;const calls=[];
 const session={login:async()=>{},clear:()=>{},transport:async()=>{},payment:async()=>{},commerce:async(scene,operation,params)=>{calls.push({scene,operation,params});if(operation==='products'){if(failProducts)throw Error('暂停交易');return {products:[]};}if(operation==='communities')return {records:[{id:'co_fixture',name:'fixture'}],has_more:false,next_cursor:null};return {community_id:'co_fixture',active:true};}};
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
