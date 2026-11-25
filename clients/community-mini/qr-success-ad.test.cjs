'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {makeClient}=require('./client'),auth=require('./customer-auth');
const SUCCESS='AD_SLOT_PAYMENT_SUCCESS',AMOUNT='AD_SLOT_PAYMENT_AMOUNT';
const ad=(slot=SUCCESS)=>({slot,title:'Synthetic merchant ad',image_data:'data:image/png;base64,YWQ='});
function receipt({state='SUCCESS',verified=true,creative=ad(),reference='order-a'}={}){
 return {simulation_only:!verified,provider_order_verified:verified,provider_payment_verified:verified&&['SUCCESS','REFUNDED'].includes(state),
  provider_settlement_verified:false,financial_receipt_issued:false,finance_effect:'NONE',
  order:{reference,amount_minor:120,currency:'CNY',state,provider_settlement_verified:false},
  payment_state:verified?'PROVIDER_'+state:state==='SUCCESS'?'MOCK_PAID_SIMULATED':'MOCK_'+state,ads:{[AMOUNT]:null,[SUCCESS]:creative}};
}
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function harness({result=receipt(),commerce=false,receiptReply={payment_success_verified:true,creative:ad()},purchaseState='SUCCESS',purchaseReference='order-a'}={}){
 let definition,generation=1,authenticated=true;const calls=[],received=deferred();
 const session={getGeneration:()=>generation,isAuthenticated:()=>authenticated,
  async commerce(scene,operation,params){calls.push({scene,operation,params});
   if(operation==='purchase_read')return {reference:purchaseReference,amount_minor:120,order:{state:purchaseState,amount_minor:120,currency:'CNY'}};
   if(operation==='receipt_ad'){received.resolve();return typeof receiptReply==='function'?receiptReply():receiptReply;}
   throw Error('unexpected operation');}};
 const source=fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8');
 vm.runInNewContext(source,{Page:p=>definition=p,require:p=>p==='../../client'?{makeClient}:p==='../../payment'?require('./payment'):p==='../../customer-auth'?auth:{},wx:{requestPayment(){throw Error('REAL_OR_SDK_PAYMENT_FORBIDDEN');}},getApp:()=>({globalData:{scene:'shop-a'}})});
 const page={...definition,data:structuredClone(definition.data),setData(v){Object.assign(this.data,v);}};
 page.session=session;page.scene='shop-a';page._authEpoch=auth.current();page._pageGeneration=1;page.data.reference='order-a';page.data.commerceEnabled=commerce;
 page.client=makeClient(async body=>{calls.push(body);assert.equal(body.operation,'community.receipt');return {offline_only:true,result};});
 return {page,calls,received,generation(){generation++;},expire(){authenticated=false;}};
}
const signedQuery=(extra={})=>({reference:'order-a',amount_minor:120,provider_state:'SUCCESS',provider_signature_verified:true,...extra});

test('qr ad: original durable provider receipt now reaches verified afterAd with no payment request',async()=>{
 const h=harness();await h.page.refresh();assert.equal(h.page.data.afterAd,'Synthetic merchant ad');assert.equal(h.page.data.afterAdVerified,true);
 assert.equal(h.page.data.afterAdImage,'data:image/png;base64,YWQ=');assert.equal(h.page.data.amount,'1.20');assert.match(h.page.data.status,/核验已支付.*尚未核销/);
 assert.deepEqual(h.calls.map(x=>x.operation),['community.receipt']);
});
test('qr ad: simulated success remains simulated and cannot supply paid creative',async()=>{
 for(const creative of [null,ad()]){const h=harness({result:receipt({verified:false,creative})});await h.page.refresh();assert.equal(h.page.data.afterAd,'');assert.equal(h.page.data.afterAdVerified,false);assert.doesNotMatch(h.page.data.status,/核验已支付/);}
});
test('qr ad: mismatched reference or slot and contradictory proof never populate success surface',async()=>{
 const values=[receipt({reference:'other-order'}),receipt({creative:ad(AMOUNT)}),{...receipt(),simulation_only:true}];
 for(const result of values){const h=harness({result});await h.page.refresh();assert.equal(h.page.data.afterAd,'');assert.equal(h.page.data.afterAdVerified,false);}
});
test('qr ad: refunded provider result cannot display success creative',async()=>{
 const h=harness({result:receipt({state:'REFUNDED',creative:null})});await h.page.refresh();assert.equal(h.page.data.afterAd,'');assert.equal(h.page.data.afterAdVerified,false);assert.match(h.page.data.status,/PROVIDER_REFUNDED/);
});
test('qr ad: verified paid no-ad response preserves amount and payment result',async()=>{
 const h=harness({result:receipt({creative:null})});await h.page.refresh();assert.equal(h.page.data.amount,'1.20');assert.equal(h.page.data.afterAd,'');assert.match(h.page.data.status,/核验已支付/);
});
test('qr ad: product order refresh consumes existing owner-verified SUCCESS supplier',async()=>{
 const h=harness({commerce:true});await h.page.refresh();assert.deepEqual(h.calls.map(x=>x.operation),['purchase_read','receipt_ad']);
 assert.equal(h.page.data.afterAdVerified,true);assert.equal(h.page.data.afterAd,'Synthetic merchant ad');assert.equal(h.calls[1].scene,'shop-a');assert.equal(h.calls[1].params.reference,'order-a');
});
test('qr ad: pending or mismatched product order never requests receipt placement',async()=>{
 for(const options of [{purchaseState:'PENDING'},{purchaseReference:'other-order'}]){const h=harness({commerce:true,...options});await h.page.refresh();assert.equal(h.calls.filter(x=>x.operation==='receipt_ad').length,0);assert.equal(h.page.data.afterAdVerified,false);}
});
test('qr ad: SDK success flag without signed query evidence is not a paid result',async()=>{
 const h=harness({commerce:true});await assert.rejects(h.page.showPayment(signedQuery({provider_signature_verified:false})),/UNTRUSTED_PAYMENT_QUERY/);
 assert.equal(h.calls.length,0);assert.equal(h.page.data.afterAdVerified,false);assert.doesNotMatch(h.page.data.status,/已支付/);
});
test('qr ad: signed query plus verified supplier displays only correct success slot',async()=>{
 for(const slot of [SUCCESS,AMOUNT]){const h=harness({commerce:true,receiptReply:{payment_success_verified:true,creative:ad(slot)}});await h.page.showPayment(signedQuery());
  assert.equal(h.page.data.afterAdVerified,slot===SUCCESS);assert.match(h.page.data.status,/微信查单已支付/);}
});
test('qr ad: advertisement outage does not turn verified payment into failure',async()=>{
 const h=harness({commerce:true,receiptReply:()=>{throw Error('synthetic ads outage');}});await h.page.showPayment(signedQuery());
 assert.equal(h.page.data.afterAd,'');assert.equal(h.page.data.afterAdImage,'');assert.equal(h.page.data.afterAdVerified,false);assert.match(h.page.data.status,/微信查单已支付/);
});
test('qr ad: late creative cannot cross merchant scene session generation reference or page lifecycle',async()=>{
 for(const change of ['scene','session','generation','reference','unload','expired']){
  const pending=deferred(),h=harness({commerce:true,receiptReply:()=>pending.promise}),reading=h.page.refresh();await h.received.promise;
  if(change==='scene')h.page.scene='shop-b';if(change==='session')h.page.session={};if(change==='generation')h.generation();
  if(change==='reference')h.page.data.reference='order-b';if(change==='unload')h.page._pageUnloaded=true;if(change==='expired')h.expire();
  pending.resolve({payment_success_verified:true,creative:ad()});await reading;assert.equal(h.page.data.afterAd,'',change);assert.equal(h.page.data.afterAdVerified,false,change);
 }
});
test('qr ad: amount change invalidates pending creative even if reference stays the same',async()=>{
 const pending=deferred(),h=harness({commerce:true,receiptReply:()=>pending.promise}),reading=h.page.refresh();await h.received.promise;
 h.page.inputAmount({detail:{value:'8.00'}});pending.resolve({payment_success_verified:true,creative:ad()});await reading;
 assert.equal(h.page.data.amount,'8.00');assert.equal(h.page.data.afterAd,'');assert.equal(h.page.data.afterAdVerified,false);
});
test('qr ad: current native amount guard and paid-only WXML surface remain intact',()=>{
 const source=fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),w=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
 assert.match(source,/if\(nativeEntry\)this.setData\(\{nativeCollectionEntry:true[^}]*commerceEnabled:false,paymentsEnabled:false/);
 assert.match(w,/disabled="{{pending\|\|productsPending\|\|nativeCollectionEntry}}"/);
 assert.match(w,/wx:if="{{afterAd&&afterAdVerified}}" class="payment-ad-slot payment-ad-success"/);assert.doesNotMatch(w,/广告 · 模拟结果/);
});

test('qr ad: readonly signed query consumes SUCCESS without invoking payment SDK',async()=>{
 const h=harness({commerce:true});let reads=0;
 h.page.paymentFlow={query:async reference=>{reads++;assert.equal(reference,'order-a');return signedQuery();}};
 await h.page.queryPayment();assert.equal(reads,1);assert.equal(h.page.data.pending,false);assert.equal(h.page.data.afterAdVerified,true);
});
test('qr ad: late signed payment query cannot restore another session or merchant view',async()=>{
 for(const kind of ['generation','scene']){
  const pending=deferred(),h=harness({commerce:true});h.page.paymentFlow={query:()=>pending.promise};const reading=h.page.queryPayment();
  if(kind==='generation')h.generation();else h.page.scene='shop-b';
  pending.resolve(signedQuery());await reading;assert.equal(h.calls.length,0);assert.equal(h.page.data.afterAd,'');assert.doesNotMatch(h.page.data.status,/已支付/);
 }
});
test('qr ad: mismatched signed-query reference cannot claim the current order paid',async()=>{
 const h=harness({commerce:true});await assert.rejects(h.page.showPayment(signedQuery({reference:'other-order'})),/UNTRUSTED_PAYMENT_QUERY/);
 assert.equal(h.calls.length,0);assert.equal(h.page.data.afterAd,'');assert.doesNotMatch(h.page.data.status,/已支付/);
});
