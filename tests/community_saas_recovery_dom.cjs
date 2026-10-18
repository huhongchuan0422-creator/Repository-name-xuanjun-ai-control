'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.value='';this.textContent='';this.hidden=false;this.dataset={};}
 append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;this.textContent='';}
 reset(){}click(){if(!this.disabled&&this.onclick)return this.onclick();}remove(){}
 set innerHTML(_){throw Error('unsafe DOM');}
}
const html=fs.readFileSync(process.argv[3],'utf8'),nodes=Object.fromEntries([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
const walk=n=>[n,...n.children.flatMap(walk)],document={getElementById:id=>{assert(nodes[id],id);return nodes[id];},createElement:tag=>new Element(tag),querySelectorAll:tag=>Object.values(nodes).flatMap(walk).filter(n=>n.tagName===tag)};
const qid='sq_'+'1'.repeat(32),oid='so_'+'2'.repeat(32),quote={quote_id:qid,totals_by_cycle:{ONCE:{cny_minor:101,usd_minor:10}}};
let calls=[],hold=null,fail=false;
const response=result=>({ok:true,json:async()=>({result})});
const context={window:{},document,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);calls.push({url,options,body});if(hold)return new Promise(resolve=>hold.resolve=resolve);
 if(fail){fail=false;return {ok:false,status:400,json:async()=>({})};}
 switch(body.operation){
 case 'workspace_info':return response({role:'CUSTOMER',pricing_allowed:false});
 case 'mine':return response({records:body.params.kind==='QUOTE'?[{reference:qid,quote_id:qid}]:[{reference:oid,order_id:oid,quote_id:qid,currency:'USD'}],has_more:false,next_cursor:null});
 case 'quote_recover':return response(quote);
 case 'order_prepare':return response({order_id:oid,currency:'USD',entitlement_granted:false});
 default:throw Error(body.operation);
 }
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunitySaas,flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
(async()=>{
 configure({csrf:'original',workspace:'one'});await flush();nodes.myQuotes.click();await flush();
 const recover=nodes.records.children[0].children.find(b=>b.textContent==='恢复原报价');assert(recover);recover.click();await flush();
 assert.deepEqual(calls.at(-1).body.params,{quote_id:qid});assert.equal(calls.at(-1).body.operation,'quote_recover');assert(nodes.selected.textContent.includes(qid));
 nodes.myOrders.click();await flush();nodes.currency.value='CNY';const recoverOrder=nodes.records.children[0].children.find(b=>b.textContent==='恢复原订单');assert(recoverOrder);recoverOrder.click();await flush();
 assert.deepEqual(calls.at(-1).body.params,{quote_id:qid,currency:'USD'});assert.equal(calls.at(-1).body.operation,'order_prepare');assert(nodes.order.textContent.includes(oid));
 const before=calls.length;fail=true;recoverOrder.click();await flush();assert.equal(calls.length,before+1);assert(nodes.notice.textContent.includes('我的记录'));assert.equal(calls.filter(c=>c.body.operation==='quote').length,0);
 hold={};recoverOrder.click();await flush();const old=hold;hold=null;recoverOrder.click();await flush();assert.equal(calls.length,before+2);
 configure(null);old.resolve(response({order_id:'private',currency:'USD'}));await flush();assert.equal(nodes.order.textContent,'');assert.equal(nodes.records.children.length,0);assert(nodes.myOrders.disabled);
 for(const c of calls){assert.equal(c.body.workspace,'one');assert.equal(c.options.headers['X-CSRF-Token'],'original');assert.equal(c.url,'/customer/saas-api');}
 console.log('SaaS explicit original quote/order recovery DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
