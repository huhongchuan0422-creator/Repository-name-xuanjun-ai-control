'use strict';
// Actual workbench source and HTML, with deterministic synthetic HTTP timing.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.value='';this.hidden=false;this.dataset={};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;this.textContent='';}
 addEventListener(type,fn){this['on'+type]=fn;}click(){if(!this.disabled&&this.onclick)return this.onclick();}
 reset(){}set innerHTML(_){throw Error('unsafe DOM');}
}
const html=fs.readFileSync(process.argv[3],'utf8');
const nodes=Object.fromEntries([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
const walk=node=>[node,...node.children.flatMap(walk)];
const document={getElementById:id=>{assert(nodes[id],id);return nodes[id];},createElement:tag=>new Element(tag),querySelectorAll:tag=>Object.values(nodes).flatMap(walk).filter(node=>node.tagName===tag)};
const requests=[];
const context={window:{},document,fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,body:JSON.parse(options.body),resolve,reject}))};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunityWorkbench,flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
const response=(result,ok=true)=>({ok,status:ok?200:403,json:async()=>({result})});
const result=label=>({label,local_inventory:{counts:{split_records:1},complete_reconciliation_available:false},finance_status:'UNCONFIRMED',has_more:true,next_offset:50,next_cursor:'audit-'+label});
function select(id,value,event='input'){nodes[id].value=value;assert.equal(typeof nodes[id]['on'+event],'function');nodes[id]['on'+event]();}
function reset(){configure({csrf:'csrf-original',workspace:'merchant',providerWorkspace:'finance'});select('billKind','SPLIT');select('billDate','2026-10-16');}
async function start(button){const before=requests.length;nodes[button].click();await flush();assert.equal(requests.length,before+1,button+' sends exactly once');return requests.at(-1);}
async function finish(request,label,ok=true){request.resolve(response(result(label),ok));await flush();}
function assertEmpty(){assert.equal(nodes.billResult.textContent,'');assert(nodes.moreBill.hidden);assert(nodes.moreBillAudit.hidden);}
(async()=>{
 configure({csrf:'original',workspace:'merchant',providerWorkspace:'finance'});
 nodes.providerOrder.value='orderA';nodes.providerRequest.value='requestA';nodes.financialKind.value='REFUND';
 // Existing successful provider receipt must disappear if the next call is refused.
 let q=await start('readReconciliation');q.resolve(response({reference:'orderA',secret:'old-receipt'}));await flush();assert(nodes.providerActionResult.textContent.includes('old-receipt'));
 q=await start('readReconciliation');q.resolve(response(null,false));await flush();assert.equal(nodes.providerActionResult.textContent,'');
 assert.equal(nodes.providerRequest.value,'requestA');
 // Independent cursor per group, no other-kind cursor reused.
 q=await start('financialRecords');q.resolve(response({records:[],has_more:true,next_cursor:'refund-page2'}));await flush();assert.equal(nodes.financialMore.hidden,false);
 select('financialKind','SPLIT','change');assert.equal(nodes.financialMore.hidden,true);assert.equal(nodes.providerActionResult.textContent,'');
 q=await start('financialRecords');q.resolve(response({records:[],has_more:true,next_cursor:'split-page2'}));await flush();
 select('financialKind','REFUND','change');assert.equal(nodes.financialMore.hidden,false);
 q=await start('financialMore');assert.equal(q.body.params.kind,'REFUND');assert.equal(q.body.params.after_id,'refund-page2');q.resolve(response({records:[],has_more:false,next_cursor:null}));await flush();
 select('financialKind','SPLIT','change');q=await start('financialMore');assert.equal(q.body.params.after_id,'split-page2');q.resolve(response({records:[],has_more:false,next_cursor:null}));await flush();
 // Selection changes while a read is pending cannot restore another group's private result.
 q=await start('financialRecords');select('financialKind','RETURN','change');q.resolve(response({records:[{secret:'old-kind'}],has_more:true,next_cursor:'old'}));await flush();assert.equal(nodes.providerActionResult.textContent,'');assert.equal(nodes.financialMore.hidden,true);
 // Order/request away and back is still a new selection; no auto retry or id replacement.
 q=await start('readReconciliation');select('providerOrder','orderB');select('providerOrder','orderA');q.resolve(response({secret:'stale-order'}));await flush();assert.equal(nodes.providerActionResult.textContent,'');
 const n=requests.length;q=await start('queryProviderRefund');select('providerRequest','requestB');q.reject(Error('private-network-detail'));await flush();assert.equal(nodes.providerActionResult.textContent,'');assert.equal(requests.length,n+1);assert.equal(nodes.providerRequest.value,'requestB');assert(!nodes.notice.textContent.includes('private-network-detail'));
 // Refusal clears all cached cursors; identity reset also clears them.
 q=await start('financialRecords');q.resolve(response({records:[],has_more:true,next_cursor:'return-next'}));await flush();q=await start('financialMore');q.resolve(response(null,false));await flush();assert.equal(nodes.financialMore.hidden,true);
 configure(null);assert.equal(nodes.providerActionResult.textContent,'');assert.equal(nodes.financialMore.hidden,true);
 console.log('SCOPED_MOCK_DOM_PASS provider refusal clear / separate group cursor / stale kind+order+request / no retry / identity reset');
})().catch(e=>{console.error(e);process.exitCode=1;});
