import test from "node:test";import assert from "node:assert/strict";
import {presentAmount,safeText,modelToView,renderDashboard,offerCycles,parseOwnerInteger} from "./saas-panel.mjs";
test("dual currency integer minor units",()=>{assert.equal(presentAmount(1999,"CNY"),"¥19.99");assert.equal(presentAmount(500,"USD"),"$5.00")});
test("unknown costs and invalid numerics stay UNKNOWN",()=>{assert.equal(presentAmount(null,"USD"),"UNKNOWN");assert.equal(presentAmount(-1,"CNY"),"UNKNOWN");assert.equal(presentAmount(1.5,"USD"),"UNKNOWN")});
test("currency never implicitly converted",()=>assert.throws(()=>presentAmount(100,"JPY"),/INVALID_CURRENCY/));
test("untrusted values become data not markup",()=>assert.equal(safeText("<img src=x onerror=alert(1)>"),"<img src=x onerror=alert(1)>"));
test("review and order mapping",()=>{const v=modelToView({modules:[{id:"cat",title:"Catalog"}],orders:[{order_id:"o",state:"PREPARED",cny_minor:100,usd_minor:20}],reviews:[{kind:"FINANCE",state:"PENDING"}]});assert.equal(v.orders[0].cny,"¥1.00");assert.equal(v.reviews[0].state,"PENDING");assert.match(v.label,/OFFLINE_ONLY/)});
test("invalid model rejected",()=>assert.throws(()=>modelToView([]),/INVALID_MODEL/));
test("DOM rendering only via textContent and document.createTextNode",()=>{let usedHTML=false;const els=new Map();function el(){return {nodes:[],replaceChildren(){this.nodes=[]},append(x){this.nodes.push(x)},set textContent(v){this.txt=v},get textContent(){return this.txt}}}const document={getElementById(id){if(!els.has(id))els.set(id,el());return els.get(id)},createElement(){return el()},createTextNode(v){return {value:v}}}; const result=renderDashboard(document,{modules:[{id:"<script>",title:"Unsafe"}],orders:[],reviews:[]});assert.equal(result.modules[0].id,"<script>");assert.ok(els.get("moduleCatalog").nodes.length>0);assert.equal(usedHTML,false)});

test("different cycles must not be shown as one payable total",()=>{
 const view=offerCycles({lines:[{cycle:"ONCE",quantity:1,cny_minor:5000,usd_minor:800},
    {cycle:"MONTH",quantity:1,cny_minor:1000,usd_minor:200}]});
 assert.match(view,/ONCE ¥50.00/);assert.match(view,/MONTH ¥10.00/);
 assert.doesNotMatch(view,/¥60.00/);
});
test("unknown cost must remain visible as unknown",()=>{
 const view=offerCycles({lines:[{cycle:"MONTH",quantity:1,cny_minor:null,usd_minor:200}]});
 assert.match(view,/UNKNOWN/);
});


test("quote quantity multiplication overflow fails closed per currency",()=>{
 const view=offerCycles({lines:[{cycle:"MONTH",quantity:3,cny_minor:Number.MAX_SAFE_INTEGER,usd_minor:100}]});
 assert.match(view,/MONTH UNKNOWN \/ \$3\.00/);
});
test("quote accumulation overflow fails closed and does not affect other cycles",()=>{
 const view=offerCycles({lines:[
 {cycle:"ONCE",quantity:1,cny_minor:Number.MAX_SAFE_INTEGER-10,usd_minor:100},
 {cycle:"ONCE",quantity:1,cny_minor:20,usd_minor:100},
 {cycle:"MONTH",quantity:1,cny_minor:300,usd_minor:300}
 ]});
 assert.match(view,/ONCE UNKNOWN \/ \$2\.00/);
 assert.match(view,/MONTH ¥3\.00 \/ \$3\.00/);
});


test("quote prototype-like cycle keys remain data and cannot pollute totals",()=>{
 const view=offerCycles({lines:[
  {cycle:"__proto__",quantity:1,cny_minor:100,usd_minor:50},
  {cycle:"MONTH",quantity:1,cny_minor:200,usd_minor:100}
 ]});
 assert.match(view,/UNKNOWN ¥1\.00 \/ \$0\.50/);
 assert.match(view,/MONTH ¥2\.00 \/ \$1\.00/);
 assert.equal(Object.prototype.cny,undefined);
});
test("malformed quote lines reject without silent zero prices",()=>{
 for(const line of [null,undefined,4,[],false])
  assert.throws(()=>offerCycles({lines:[line]}),/INVALID_QUOTE_LINE/);
});
test("unknown quote cycle remains visibly unknown without affecting known cycle",()=>{
 const view=offerCycles({lines:[
  {cycle:{"toString":"unexpected"},quantity:1,cny_minor:75,usd_minor:80},
  {cycle:"ONCE",quantity:1,cny_minor:120,usd_minor:150}
 ]});
 assert.match(view,/UNKNOWN ¥0\.75 \/ \$0\.80/);
 assert.match(view,/ONCE ¥1\.20 \/ \$1\.50/);
});

test("Owner integer price input rejects decimals, scientific notation and overflow",()=>{
 for(const raw of ["", " ", "-1", "1.5", "1e3", "01", "Infinity", "9007199254740992", "0x10"])
  assert.throws(()=>parseOwnerInteger(raw),/INVALID_OWNER_INTEGER/);
 assert.equal(parseOwnerInteger("0"),0);
 assert.equal(parseOwnerInteger("500"),500);
});
test("Owner offer version must be a positive safe integer",()=>{
 assert.equal(parseOwnerInteger("2",true),2);
 for(const raw of ["0","-1","1.1","99999999999999999"])
  assert.throws(()=>parseOwnerInteger(raw,true),/INVALID_OWNER_INTEGER/);
});
