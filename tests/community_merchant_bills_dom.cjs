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
 const both=()=>{configure({csrf:'csrf',workspace:'merchant',providerWorkspace:'store-finance',merchantBillWorkspace:'all-stores'});select('billKind','TRADE');select('billDate','2026-10-16');};
 configure({csrf:'readonly',workspace:'merchant',merchantBillWorkspace:'all-stores'});select('billKind','TRADE');select('billDate','2026-10-16');
 assert(nodes.providerActions.hidden);assert(!nodes.billSection.hidden);assert.equal(nodes.billScope.value,'MERCHANT');
 let read=await start('readBill');assert.equal(read.url,'/community/merchant-bills');assert.equal(read.body.workspace,'all-stores');await finish(read,'merchant-page');
 let next=await start('moreBill');assert.equal(next.url,'/community/merchant-bills');assert.equal(next.body.params.offset,50);await finish(next,'merchant-next');
 const count=requests.length;nodes.providerRefundForm.onsubmit({preventDefault(){}});await flush();assert.equal(requests.length,count,'read-only workspace must never become funds authority');
 select('billScope','STORE');assertEmpty();nodes.readBill.click();await flush();assert.equal(requests.length,count,'missing store grant must not fall back to merchant grant');
 configure({csrf:'store-only',workspace:'merchant',providerWorkspace:'store-finance'});select('billKind','TRADE');select('billDate','2026-10-16');select('billScope','MERCHANT');nodes.readBill.click();await flush();assert.equal(requests.length,count,'store grant must not become merchant authority');
 both();select('billScope','MERCHANT');const old=await start('readBill');select('billScope','STORE');assertEmpty();const current=await start('readBill');assert.equal(current.url,'/community/provider-actions');assert.equal(current.body.workspace,'store-finance');
 await finish(old,'forbidden-old-merchant');assertEmpty();assert(nodes.readBill.disabled);await finish(current,'current-store');assert(nodes.billResult.textContent.includes('current-store'));
 select('billScope','MERCHANT');assertEmpty();await finish(await start('billAudit'),'merchant-audit');assert(!nodes.moreBillAudit.hidden);
 const denial=await start('readBill');await finish(denial,'revoked-private-data',false);assertEmpty();assert(!nodes.notice.textContent.includes('revoked-private-data'));
 both();select('billScope','MERCHANT');await finish(await start('readBill'),'private-before-malformed');
 let parsedDenied=false;const malformedDenied=await start('readBill');malformedDenied.resolve({ok:false,status:403,json:()=>{parsedDenied=true;throw Error('private-html-body');}});await flush();assert(!parsedDenied);assertEmpty();assert(!nodes.notice.textContent.includes('private-html'));
 await finish(await start('readBill'),'private-before-json-error');const invalidJson=await start('readBill');invalidJson.resolve({ok:true,json:async()=>{throw Error('private-json-fragment');}});await flush();assertEmpty();assert(!nodes.notice.textContent.includes('private-json'));
 const staleJson=await start('readBill');let rejectOld;staleJson.resolve({ok:true,json:()=>new Promise((resolve,reject)=>{rejectOld=reject;})});await flush();select('billScope','STORE');await finish(await start('readBill'),'new-store-survives');rejectOld(Error('stale-private-json'));await flush();assert(nodes.billResult.textContent.includes('new-store-survives'));
 both();select('billScope','MERCHANT');const oldIdentity=await start('readBill');configure(null);await finish(oldIdentity,'old-identity-private');assertEmpty();assert(nodes.readBill.disabled);assert(nodes.providerActions.hidden);assert(nodes.billSection.hidden);
 both();nodes.providerOrder.value='order';nodes.providerRequest.value='request';nodes.providerRefundAmount.value='1';nodes.providerRefundReason.value='synthetic';
 const beforeFunds=requests.length;nodes.providerRefundForm.onsubmit({preventDefault(){}});await flush();const funds=requests.at(-1);assert.equal(funds.body.operation,'refund');assert.equal(funds.url,'/community/provider-actions');
 select('billScope','MERCHANT');assert(nodes.readBill.disabled);nodes.readBill.click();await flush();assert.equal(requests.length,beforeFunds+1);await finish(funds,'funds-result');assert(nodes.providerActionResult.textContent.includes('funds-result'));
 const merchant=await start('reconcileBill');assert.equal(merchant.url,'/community/merchant-bills');await finish(merchant,'pending-merchant');assert(nodes.providerActionResult.textContent.includes('funds-result'));
 both();select('billScope','MERCHANT');const bounced=await start('readBill');select('billScope','STORE');select('billScope','MERCHANT');await finish(bounced,'same-values-obsolete');assertEmpty();
 for(const request of requests){assert.equal(request.options.credentials,'same-origin');assert.equal(request.options.cache,'no-store');assert.equal(request.options.redirect,'error');if(request.url==='/community/merchant-bills')assert(['bill_fetch','bill_rows','bill_reconcile','bill_audit'].includes(request.body.operation));}
 console.log('Merchant bill scope, grant separation, revocation and stale response DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
