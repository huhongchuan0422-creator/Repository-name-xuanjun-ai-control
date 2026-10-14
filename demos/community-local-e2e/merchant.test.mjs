import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import {readFileSync} from "node:fs";
const source=readFileSync(new URL("./merchant.js",import.meta.url),"utf8");
function setup(fetchFn){
 const keys=["tenant","merchant","store","reference","load","amount","currency","state","transaction","verified","status","error"];
 const els={},events={};
 for(const id of keys)els[id]={value:({tenant:"t1",merchant:"m1",store:"s1",reference:"r1"})[id]||"",textContent:"",addEventListener(type,fn){events[id+":"+type]=fn;}};
 vm.runInNewContext(source,{document:{getElementById:id=>els[id]},fetch:fetchFn,JSON,Object,Number,String,Error});
 return {els,events,async click(){events["load:click"]();await new Promise(resolve=>setImmediate(resolve));},input(id,val){els[id].value=val;events[id+":input"]();}};
}
const sample={amount_minor:120,currency:"CNY",state:"SUCCESS",provider_transaction_id:"sim1",provider_settlement_verified:false};
const ok=data=>({status:200,json:async()=>data});
test("reads actual state endpoint but never upgrades simulation to verified",async()=>{
 const ui=setup(async(path,opts)=>{assert.equal(path,"/demo/orders/state");assert.equal(JSON.parse(opts.body).reference,"r1");return ok(sample);});
 await ui.click();
 assert.match(ui.els.state.textContent,/SUCCESS/);
 assert.equal(ui.els.verified.textContent,"否");
 assert.match(ui.els.status.textContent,/当前模拟订单/);
});
test("rejects forged settlement and unexpected fields",async()=>{
 for(const malformed of [{...sample,provider_settlement_verified:true},{...sample,secret:"bad"},{...sample,amount_minor:"120"}]){
  const ui=setup(async()=>ok(malformed));await ui.click();
  assert.equal(ui.els.verified.textContent,"否");
  assert.equal(ui.els.state.textContent,"—");
  assert.match(ui.els.error.textContent,/不可信/);
 }
});
test("input change clears and stale response cannot expose old merchant",async()=>{
 let release;
 const ui=setup(()=>new Promise(r=>{release=r;}));
 ui.events["load:click"]();
 ui.input("merchant","other");
 release(ok(sample));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ui.els.state.textContent,"—");
 assert.equal(ui.els.verified.textContent,"否");
 assert.equal(ui.els.status.textContent,"尚未查询");
});
test("new lookup supersedes stale first lookup",async()=>{
 let old;
 const ui=setup((path,opts)=>JSON.parse(opts.body).reference==="r1"?new Promise(r=>{old=r;}):ok({...sample,state:"PENDING",provider_transaction_id:null}));
 ui.events["load:click"]();
 ui.input("reference","r2");await ui.click();
 old(ok(sample));await new Promise(resolve=>setImmediate(resolve));
 assert.match(ui.els.state.textContent,/PENDING/);
 assert.doesNotMatch(ui.els.state.textContent,/SUCCESS/);
});
