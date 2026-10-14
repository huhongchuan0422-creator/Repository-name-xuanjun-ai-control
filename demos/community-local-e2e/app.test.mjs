import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('./app.js',import.meta.url),'utf8');
function setup(fetchMock){
 const ids=['tenant','merchant','store','reference','amount','create','query','complete','fail','merchantQuery','status','merchantResult','error','successAd','loadStorefront','storefrontStatus','storefrontName','storefrontProducts','adAmount'];
 const els={},events={};
 for(const id of ids)els[id]={value:({tenant:'t1',merchant:'m1',store:'s1',reference:'ref1',amount:'150'})[id]||'',hidden:id==='successAd',textContent:'',addEventListener(type,fn){events[id+':'+type]=fn;}};
 let nonce=0;
 const crypto={randomUUID:()=>`00000000-0000-4000-8000-${(++nonce).toString(16).padStart(12,"0")}`};
 const context=vm.createContext({document:{getElementById:id=>els[id]},fetch:fetchMock,crypto,JSON,Number,Object,String,Error});
 vm.runInContext(source,context);
 return {els,input:(id,value)=>{els[id].value=value;events[id+':input']();},click:async id=>{events[id+':click']();await new Promise(resolve=>setImmediate(resolve));},events,context};
}
const ok=value=>({status:200,json:async()=>value});
const created={reference:'ref1',state:'PENDING',provider_payment_started:false};
const success={state:'SUCCESS',duplicate:false,provider_settlement_verified:false};
test('normal simulated success shows success-only ad',async()=>{
 const ui=setup(async(url)=>ok(url.endsWith('/orders')?created:success));
 await ui.click('create');await ui.click('complete');
 assert.equal(ui.els.successAd.hidden,false);
 assert.match(ui.els.status.textContent,/非真实支付凭证/);
});
test('malformed simulated responses never display success',async()=>{
 for(const value of [{state:'SUCCESS'}, {state:'SUCCESS',duplicate:'false'}, {state:'FAILED',duplicate:false},
                      {state:'SUCCESS',duplicate:false,provider_settlement_verified:true},
                      {state:'SUCCESS',duplicate:false,execution_granted:true}]){
  const ui=setup(async(url)=>ok(url.endsWith('/orders')?created:value));
  await ui.click('create');await ui.click('complete');
  assert.equal(ui.els.successAd.hidden,true);
  assert.match(ui.els.error.textContent,/不匹配|格式错误/);
 }
});
test('changing order after success clears stale state and ad',async()=>{
 const ui=setup(async(url)=>ok(url.endsWith('/orders')?created:success));
 await ui.click('create');await ui.click('complete');
 assert.equal(ui.els.successAd.hidden,false);
 ui.input('merchant','other');
 assert.equal(ui.els.successAd.hidden,true);
 assert.equal(ui.els.status.textContent,'未核实当前订单');
 await ui.click('complete');
 assert.match(ui.els.error.textContent,/请先创建/);
});
test('late success for changed order must not render',async()=>{
 let resolve;
 const ui=setup(async(url)=>url.endsWith('/orders')?ok(created):new Promise(r=>{resolve=r;}));
 await ui.click('create');
 ui.events['complete:click']();
 ui.input('reference','other_ref');
 resolve(ok(success));
 await new Promise(r=>setImmediate(r));
 assert.equal(ui.els.successAd.hidden,true);
 assert.equal(ui.els.status.textContent,'未核实当前订单');
});
test('old response cannot overwrite newly created order',async()=>{
 let resolveOld;
 const ui=setup(async(url,opts)=>{
  const data=JSON.parse(opts.body);
  if(url.endsWith('/simulate'))return new Promise(r=>{resolveOld=r;});
  return ok({reference:data.reference,state:'PENDING',provider_payment_started:false});
 });
 await ui.click('create');
 ui.events['complete:click']();
 ui.input('reference','ref2');
 await ui.click('create');
 resolveOld(ok(success));
 await new Promise(r=>setImmediate(r));
 assert.equal(ui.els.successAd.hidden,true);
 assert.match(ui.els.status.textContent,/PENDING/);
});
test('query never enables success ad even if state is SUCCESS',async()=>{
 const reply={amount_minor:150,currency:'CNY',state:'SUCCESS',provider_transaction_id:'tx1',provider_settlement_verified:false};
 const ui=setup(async(url)=>ok(url.endsWith('/orders')?created:reply));
 await ui.click('create');await ui.click('query');
 assert.equal(ui.els.successAd.hidden,true);
});

test('same order: delayed old PENDING query cannot overwrite later SUCCESS',async()=>{
 let resolveOldQuery;
 const pending={amount_minor:150,currency:'CNY',state:'PENDING',provider_transaction_id:null,provider_settlement_verified:false};
 const ui=setup(async(url)=>{
  if(url.endsWith('/orders'))return ok(created);
  if(url.endsWith('/orders/state'))return new Promise(resolve=>{resolveOldQuery=resolve;});
  if(url.endsWith('/orders/simulate'))return ok(success);
  throw Error('unexpected request');
 });
 await ui.click('create');
 ui.events['query:click']();
 await ui.click('complete');
 assert.match(ui.els.status.textContent,/SUCCESS/);
 assert.equal(ui.els.successAd.hidden,false);
 resolveOldQuery(ok(pending));
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(ui.els.status.textContent,/SUCCESS/);
 assert.equal(ui.els.successAd.hidden,false);
 assert.equal(ui.els.error.textContent,'');
});
test('same order: stale failed query must not clear later success',async()=>{
 let rejectOldQuery;
 const ui=setup(async(url)=>{
  if(url.endsWith('/orders'))return ok(created);
  if(url.endsWith('/orders/state'))return new Promise((_,reject)=>{rejectOldQuery=reject;});
  return ok(success);
 });
 await ui.click('create');
 ui.events['query:click']();
 await ui.click('complete');
 rejectOldQuery(Error('late network failure'));
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(ui.els.status.textContent,/SUCCESS/);
 assert.equal(ui.els.successAd.hidden,false);
 assert.equal(ui.els.error.textContent,'');
});
test('same order: earlier simulation success cannot resurrect after later query',async()=>{
 let resolveOldSuccess;
 const pending={amount_minor:150,currency:'CNY',state:'PENDING',provider_transaction_id:null,provider_settlement_verified:false};
 const ui=setup(async(url)=>{
  if(url.endsWith('/orders'))return ok(created);
  if(url.endsWith('/orders/simulate'))return new Promise(resolve=>{resolveOldSuccess=resolve;});
  return ok(pending);
 });
 await ui.click('create');
 ui.events['complete:click']();
 await ui.click('query');
 resolveOldSuccess(ok(success));
 await new Promise(resolve=>setImmediate(resolve));
 assert.match(ui.els.status.textContent,/PENDING/);
 assert.equal(ui.els.successAd.hidden,true);
});

const scopedStorefront={merchant:{name:"Shop A",description:"Intro",contact:"tel"},products:[{id:"p1",name:"Item A",sort:1}],
 ads:{AD_SLOT_PAYMENT_AMOUNT:{id:"ad1",title:"Approved A",url:"https://example.org/ad",slot:"AD_SLOT_PAYMENT_AMOUNT"},AD_SLOT_PAYMENT_SUCCESS:null},
 simulation_only:true,provider_settlement_verified:false,escape_text_required:true};
test('storefront load presents approved amount creative as text, never success ad',async()=>{
 const ui=setup(async(path)=>{assert.equal(path,"/demo/storefront");return ok(scopedStorefront);});
 await ui.click('loadStorefront');
 assert.equal(ui.els.storefrontName.textContent,"Shop A");
 assert.equal(ui.els.storefrontProducts.textContent,"Item A");
 assert.match(ui.els.adAmount.textContent,/Approved A/);
 assert.equal(ui.els.successAd.hidden,true);
});
test('storefront cannot render injected success placement or unknown properties',async()=>{
 for(const data of [{...scopedStorefront,ads:{...scopedStorefront.ads,AD_SLOT_PAYMENT_SUCCESS:{id:"forged"}}},
                      {...scopedStorefront,provider_settlement_verified:true},
                      {...scopedStorefront,unexpected:"unsafe"}]){
  const ui=setup(async()=>ok(data));
  await ui.click('loadStorefront');
  assert.equal(ui.els.storefrontName.textContent,"");
  assert.equal(ui.els.successAd.hidden,true);
  assert.match(ui.els.storefrontStatus.textContent,/不可信|格式错误/);
 }
});
test('merchant scope change invalidates late catalog result and creative',async()=>{
 let release;
 const ui=setup(()=>new Promise(resolve=>{release=resolve;}));
 ui.events['loadStorefront:click']();
 ui.input('merchant','other');
 release(ok(scopedStorefront));
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ui.els.storefrontName.textContent,"");
 assert.equal(ui.els.adAmount.textContent,"金额页广告位：当前无广告（模拟）");
});
