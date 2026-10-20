const test=require('node:test');
const auth=require('./customer-auth');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function page(failProducts=false,receipt=null){
 let definition;const calls=[];
 const session={login:async()=>{},clear:()=>{},transport:async()=>{},payment:async()=>{},commerce:async(scene,operation,params)=>{calls.push({scene,operation,params});if(operation==='products'){if(failProducts)throw Error('暂停交易');return {products:[]};}if(operation==='project_checklist')return {items:[{id:'material1',title:'准备证件',instructions:'根据原项目私有材料要求准备',submission_type:'SECRETREF',state:'PARTIAL',required:true,revision:1}]};if(operation==='receipt_ad'){if(typeof receipt==='function')return receipt(scene,params);return {payment_success_verified:false,creative:null};}if(operation==='project_messages')return {records:[{id:'m_fixture',body:'历史反馈',status:'ARCHIVED',channel:'WEB',created:100}],has_more:false,next_cursor:null,source:'ORIGINAL_CENTER_ARCHIVE',provider_reply_verified:false};if(operation==='communities')return {records:[{id:'co_fixture',name:'fixture'}],has_more:false,next_cursor:null};return {community_id:'co_fixture',active:true};}};
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{Page:value=>{definition=value;},require:path=>path==='../../customer-auth'?auth:path==='../../client'?{makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})}:path==='../../payment'?{createPaymentFlow:()=>({reset(){}})}:{parseScene:o=>o.scene,createSession:()=>session},getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid',commerce:true,payments:true}}),wx:{}});
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
 assert.equal(calls.at(-1).params.reference,'order1');
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


test('session exit clears checkout amount and verified creative while retained page instance stays inert',async()=>{
 const {result}=page(false,()=>({payment_success_verified:true,creative:{title:'verified fixture'}}));
 await result.onLoad({scene:'shop1'});
 result.setData({reference:'order1',amount:'101',afterAd:'verified fixture',afterAdVerified:true});
 const retained=result;
 retained.customerSessionRevoked();
 assert.equal(retained,result);
 assert.equal(result.data.reference,'');
 assert.equal(result.data.amount,'');
 assert.equal(result.data.afterAd,'');
 assert.equal(result.data.afterAdVerified,false);
 assert.equal(result.data.commerceEnabled,false);
 assert.equal(result.data.paymentsEnabled,false);
 assert.equal(result.session,null);
 assert.equal(result.client,null);
 assert.equal(result.paymentFlow,null);
});

test('project feedback archive read uses current mini session and remains archived',async()=>{
 const {result,calls}=page();await result.onLoad({scene:'shop1'});
 await result.projectAction({currentTarget:{dataset:{operation:'project_messages'}}});
 assert.equal(calls.at(-1).operation,'project_messages');
 assert.equal(result.data.projectMessages[0].status,'ARCHIVED');
 assert.match(result.data.status,/不代表已获得人工回复/);
});


test('customer private-material reference rejects empty and oversized input before sending',async()=>{
 const {result,calls}=page();await result.onLoad({scene:'shop1'});
 result.setData({projectReferenceItem:'material1',projectReferenceRevision:0,projectReferenceKind:'SECRETREF',projectReference:''});
 await result.saveProjectReference();
 assert.equal(calls.filter(c=>c.operation==='project_save_reference').length,0);
 result.setData({projectReference:'x'.repeat(257)});
 await result.saveProjectReference();
 assert.equal(calls.filter(c=>c.operation==='project_save_reference').length,0);
 result.setData({projectReference:'synthetic-ref'});
 await result.saveProjectReference();
 const req=calls.filter(c=>c.operation==='project_save_reference');
 assert.equal(req.length,1);
 assert.equal(req[0].params.reference,'synthetic-ref');
 assert.equal(req[0].params.item,'material1');
});

test('late reference-save reply cannot overwrite newly selected original requirement',async()=>{
 const {result}=page();await result.onLoad({scene:'shop1'});
 result.setData({projectReferenceItem:'material1',projectReferenceRevision:0,
   projectReferenceKind:'SECRETREF',projectReference:'synthetic-ref'});
 const pending=result.saveProjectReference();
 result.setData({projectReferenceItem:'material2',projectReferenceRevision:1,projectReference:'new-ref'});
 await pending;
 assert.equal(result.data.projectReferenceItem,'material2');
 assert.equal(result.data.projectReference,'new-ref');
});

test('project checklist displays exact original requirement title and instructions',async()=>{
 const {result,calls}=page();await result.onLoad({scene:'shop1'});
 await result.projectAction({currentTarget:{dataset:{operation:'project_checklist'}}});
 assert.equal(calls.at(-1).operation,'project_checklist');
 assert.equal(result.data.projectChecklist[0].title,'准备证件');
 assert.equal(result.data.projectChecklist[0].submission_type,'SECRETREF');
 assert.match(result.data.projectChecklist[0].instructions,/原项目私有材料要求/);
});

test('requirement picker locks original reference type and rejects document substitution',async()=>{
 const {result}=page();await result.onLoad({scene:'shop1'});
 result.setData({projectChecklist:[{id:'oauth1',revision:2,submission_type:'OAUTH'},
   {id:'pdf1',revision:1,submission_type:'PRIVATE_DOCUMENT'}]});
 result.selectProjectRequirement({currentTarget:{dataset:{item:'oauth1',revision:2}}});
 assert.equal(result.data.projectReferenceKind,'OAUTH');
 result.selectProjectRequirement({currentTarget:{dataset:{item:'pdf1',revision:1}}});
 assert.equal(result.data.projectReferenceItem,'oauth1');
 assert.match(result.data.status,/私有文件上传/);
 result.selectProjectRequirement({currentTarget:{dataset:{item:'oauth1',revision:1}}});
 assert.equal(result.data.projectReferenceRevision,2);
});
