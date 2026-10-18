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
 // Both native event paths invalidate both cursor sets, independently for type/date.
 for(const [id,value,event] of [['billDate','2026-10-15','input'],['billDate','2026-10-14','change'],['billKind','TRADE','input'],['billKind','TRADE','change']]){
  reset();await finish(await start('readBill'),'old-rows');await finish(await start('billAudit'),'old-history');
  assert(!nodes.moreBill.hidden);assert(!nodes.moreBillAudit.hidden);select(id,value,event);assertEmpty();
  const before=requests.length;nodes.moreBill.click();await flush();nodes.moreBillAudit.click();await flush();assert.equal(requests.length,before);
  const fresh=await start('readBill');assert.equal(fresh.body.params.offset,0);assert.equal(fresh.body.params.kind,nodes.billKind.value);assert.equal(fresh.body.params.bill_date,nodes.billDate.value);await finish(fresh,'fresh');
  const next=await start('moreBill');assert.equal(next.body.params.offset,50);assert.equal(next.body.params.bill_date,nodes.billDate.value);assert.equal(next.body.params.kind,nodes.billKind.value);await finish(next,'next');
  const audit=await start('billAudit');assert.equal(audit.body.params.after_id,'');await finish(audit,'fresh-history');
  const moreAudit=await start('moreBillAudit');assert.equal(moreAudit.body.params.after_id,'audit-fresh-history');assert.equal(moreAudit.body.params.kind,nodes.billKind.value);assert.equal(moreAudit.body.params.bill_date,nodes.billDate.value);await finish(moreAudit,'next-history');
 }
 // All bill actions discard late success, server denial, and rejected transport.
 for(const button of ['fetchBill','readBill','reconcileBill','billAudit'])for(const outcome of ['success','denial','network']){
  reset();nodes.providerActionResult.textContent='unrelated-funds-observation';const old=await start(button);
  select('billDate','2026-10-15','input');assertEmpty();assert(!nodes.readBill.disabled);
  const fresh=await start('reconcileBill');
  if(outcome==='network')old.reject(Error('old-private-transport-error'));else old.resolve(response(result('old-private-result'),outcome==='success'));
  await flush();assertEmpty();assert(nodes.readBill.disabled,'old finally must not release a newer request');assert(!nodes.notice.textContent.includes('old-private'));
  await finish(fresh,'current-inventory');assert(nodes.billResult.textContent.includes('current-inventory'));assert(nodes.billResult.textContent.includes('local_inventory'));assert(!nodes.readBill.disabled);assert.equal(nodes.providerActionResult.textContent,'unrelated-funds-observation');
 }
 // Pending next pages cannot restore either obsolete cursor after a new selection.
 for(const [first,more] of [['readBill','moreBill'],['billAudit','moreBillAudit']]){
  reset();await finish(await start(first),'page-one');const oldPage=await start(more);
  select('billKind','TRADE','change');await finish(oldPage,'obsolete-next-page');assertEmpty();
  const next=await start(first);assert.equal(next.body.params.kind,'TRADE');assert.equal(next.body.params[first==='readBill'?'offset':'after_id'],first==='readBill'?0:'');await finish(next,'new-first-page');
 }
 // A late first response also cannot overwrite a newer request already completed.
 reset();const older=await start('readBill');select('billKind','TRADE','change');await finish(await start('readBill'),'already-current');
 const notice=nodes.notice.textContent;await finish(older,'must-not-reappear');assert(nodes.billResult.textContent.includes('already-current'));assert.equal(nodes.notice.textContent,notice);assert(!nodes.moreBill.hidden);
 // A type/date pair changed away and back is a new selection, even if values match.
 reset();const sameValues=await start('billAudit');select('billDate','2026-10-15');select('billDate','2026-10-16');await finish(sameValues,'obsolete-same-date');assertEmpty();
 // input followed by same-value change must not discard a valid current request.
 const sameSelection=await start('reconcileBill');select('billDate','2026-10-16','change');assert(nodes.readBill.disabled);await finish(sameSelection,'same-selection-valid');assert(nodes.billResult.textContent.includes('same-selection-valid'));
 // Selection changes while JSON is pending are guarded after body consumption too.
 reset();const bodyPending=await start('billAudit');let resolveJson;bodyPending.resolve({ok:true,json:()=>new Promise(resolve=>resolveJson=resolve)});await flush();
 select('billKind','TRADE','input');const newBody=await start('readBill');resolveJson({result:result('old-body')});await flush();assertEmpty();assert(nodes.readBill.disabled);await finish(newBody,'new-body');
 // Old-identity responses/errors cannot restore data, status, or enabled buttons.
 for(const outcome of ['success','network']){
  reset();const old=await start('reconcileBill');configure(null);const logoutNotice=nodes.notice.textContent;
  if(outcome==='network')old.reject(Error('old-identity-error'));else old.resolve(response(result('old-identity-result')));await flush();assertEmpty();assert(nodes.readBill.disabled);assert.equal(nodes.notice.textContent,logoutNotice);assert.equal(nodes.providerActionResult.textContent,'');
 }
 reset();const identityOld=await start('billAudit');configure({csrf:'csrf-new',workspace:'merchant-new',providerWorkspace:'finance-new'});
 const identityNew=await start('reconcileBill');await finish(identityOld,'wrong-identity');assert(nodes.readBill.disabled);assertEmpty();await finish(identityNew,'new-identity');assert(nodes.billResult.textContent.includes('new-identity'));assert.equal(identityNew.body.workspace,'finance-new');assert.equal(identityNew.options.headers['X-CSRF-Token'],'csrf-new');
 // Changing bill selectors cannot unlock an unrelated funds mutation or erase its result.
 reset();nodes.providerOrder.value='existing-order';nodes.providerRequest.value='existing-request';nodes.providerRefundAmount.value='1';nodes.providerRefundReason.value='synthetic';
 const count=requests.length;nodes.providerRefundForm.onsubmit({preventDefault(){}});await flush();assert.equal(requests.length,count+1);const funds=requests.at(-1);assert.equal(funds.body.operation,'refund');
 nodes.notice.textContent='funds action pending';select('billDate','2026-10-15');select('billKind','TRADE','change');assert.equal(nodes.notice.textContent,'funds action pending');assert(nodes.readBill.disabled);nodes.readBill.click();nodes.providerRefundForm.onsubmit({preventDefault(){}});await flush();assert.equal(requests.length,count+1);
 await finish(funds,'funds-observation');assert(nodes.providerActionResult.textContent.includes('funds-observation'));assert(!nodes.readBill.disabled);
 await finish(await start('reconcileBill'),'after-funds');assert(nodes.billResult.textContent.includes('after-funds'));assert(nodes.providerActionResult.textContent.includes('funds-observation'));
 // Current errors remain visible and allow explicit fresh reads without an auto-retry.
 const currentError=await start('readBill');currentError.reject(Error('current-explicit-read-failure'));await flush();assert.equal(nodes.notice.textContent,'current-explicit-read-failure');assert(!nodes.readBill.disabled);await finish(await start('readBill'),'recovered');assert(nodes.billResult.textContent.includes('recovered'));
 for(const request of requests){assert.equal(request.url,'/community/provider-actions');assert.equal(request.options.credentials,'same-origin');assert.equal(request.options.cache,'no-store');assert.equal(request.options.redirect,'error');}
 assert(!fs.readFileSync(process.argv[2],'utf8').match(/innerHTML|localStorage|sessionStorage/));
 console.log('Bill selection, stale results/errors, pagination, identity and funds-action ownership DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
