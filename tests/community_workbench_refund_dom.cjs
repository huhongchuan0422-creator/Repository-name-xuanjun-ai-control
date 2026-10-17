'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.value='';this.hidden=false;this.dataset={};}
 append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;this.textContent='';}
 addEventListener(type,fn){this['on'+type]=fn;}click(){if(!this.disabled&&this.onclick)return this.onclick();}
 reset(){} // Standalone controls are deliberately not reset by a form.
 set innerHTML(_){throw Error('unsafe DOM');}
}
const html=fs.readFileSync(process.argv[3],'utf8'),nodes=Object.fromEntries([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
const walk=n=>[n,...n.children.flatMap(walk)],document={getElementById:id=>{assert(nodes[id],id);return nodes[id];},createElement:tag=>new Element(tag),querySelectorAll:tag=>Object.values(nodes).flatMap(walk).filter(n=>n.tagName===tag)};
let requests=[],hold=null,fail=false;const response=result=>({ok:true,json:async()=>({result})});
const record={application_id:'refund1',reference:'basket1',amount_minor:1200,reason:'<img onerror=alert(1)>',status:'SUBMITTED',revision:1};
const lines={reference:'basket1',amount_minor:1200,lines:[{item_id:'item1',name:'<script>unsafe</script>',quantity:2,unit_minor:600,subtotal_minor:1200,revision:3}]};
const context={window:{},document,fetch:async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,options,body});if(hold)return new Promise(resolve=>hold.resolve=resolve);if(fail){fail=false;return {ok:false,json:async()=>({})};}switch(body.operation){
 case 'refund_applications':return response({records:[record],has_more:!body.params.after_id,next_cursor:body.params.after_id?null:'f'.repeat(64)});
 case 'refund_application_read':return response(record);
 case 'refund_decide':return response({...record,status:body.params.decision,revision:2});
 case 'community.order_detail':return response({reference:body.params.reference,state:'SUCCESS'});
 case 'order_lines':if(body.params.reference==='plain')return {ok:false,json:async()=>({})};return response(lines);
 case 'order_complete':return response({...lines,fulfillment_revision:1});
 default:throw Error(body.operation);
}}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunityWorkbench,flush=async()=>{for(let n=0;n<70;n++)await Promise.resolve();};
(async()=>{
 configure({csrf:'csrf-original',workspace:'merchant'});nodes.loadRefundApplications.click();await flush();assert(!nodes.moreRefundApplications.hidden);assert(nodes.refundApplications.children[0].textContent.includes('<img'));
 nodes.refundApplications.children[0].children[0].click();await flush();assert.equal(nodes.refundApplicationId.value,'refund1');assert.equal(nodes.refundApplicationRevision.value,1);
 nodes.refundApplicationDecision.value='APPROVED';nodes.refundApplicationOpinion.value='Reviewed';nodes.decideRefundApplication.click();await flush();assert(nodes.refundApplicationResult.textContent.includes('未执行退款'));assert.equal(requests.at(-1).body.params.expected_revision,1);
 nodes.moreRefundApplications.click();await flush();assert.equal(requests.at(-1).body.params.after_id,'f'.repeat(64));assert(nodes.moreRefundApplications.hidden);assert.equal(nodes.refundApplicationId.value,'');
 nodes.refundApplicationId.value='refund1';nodes.readRefundApplication.click();await flush();fail=true;const count=requests.length;nodes.decideRefundApplication.click();await flush();assert.equal(requests.length,count+1);assert(nodes.refundApplicationResult.textContent.includes('结果未知'));
 // ABA application changes invalidate late reads and may not overwrite current revision.
 hold={};nodes.readRefundApplication.click();await flush();const pending=hold;hold=null;nodes.refundApplicationId.value='other';nodes.refundApplicationId.oninput();nodes.refundApplicationId.value='refund1';nodes.refundApplicationId.oninput();pending.resolve(response(record));await flush();assert.equal(nodes.refundApplicationRevision.value,'');assert.equal(nodes.refundApplicationResult.textContent,'');
 nodes.detailReference.value='basket1';nodes.detailForm.onsubmit({preventDefault(){}});await flush();assert(nodes.orderLines.children[0].textContent.includes('<script>'));assert(nodes.orderLines.children[0].textContent.includes('数量 2'));assert.equal(nodes.completionRevision.value,0);
 nodes.detailReference.value='plain';nodes.detailReference.oninput();nodes.readOrderLines.click();await flush();assert(nodes.orderLines.textContent.includes('普通金额订单'));assert.equal(nodes.completionRevision.value,'');
 // In-flight basket A cannot populate basket B or A after an ABA edit.
 nodes.detailReference.value='basket1';hold={};nodes.readOrderLines.click();await flush();const basket=hold;hold=null;nodes.detailReference.value='basket2';nodes.detailReference.oninput();nodes.detailReference.value='basket1';nodes.detailReference.oninput();basket.resolve(response(lines));await flush();assert.equal(nodes.orderLines.children.length,0);assert.equal(nodes.completionRevision.value,'');
 // A bounded sparse page is not terminal and never triggers automatic loading.
 hold={};const sparseCount=requests.length;nodes.loadRefundApplications.click();await flush();const sparse=hold;hold=null;
 sparse.resolve(response({records:[],has_more:true,next_cursor:'a'.repeat(64)}));await flush();
 assert.equal(requests.length,sparseCount+1);assert.equal(nodes.refundApplications.children.length,0);assert(!nodes.moreRefundApplications.hidden);assert(!nodes.moreRefundApplications.disabled);assert(nodes.refundApplications.textContent.includes('仍有记录待查'));assert(!nodes.refundApplications.textContent.includes('末页'));
 await flush();assert.equal(requests.length,sparseCount+1);
 nodes.moreRefundApplications.click();await flush();assert.equal(requests.length,sparseCount+2);assert.equal(requests.at(-1).body.params.after_id,'a'.repeat(64));assert.equal(nodes.refundApplications.children.length,1);assert(nodes.moreRefundApplications.hidden);
 for(const r of requests){assert.equal(r.body.workspace,'merchant');assert.equal(r.options.credentials,'same-origin');assert.equal(r.options.headers['X-CSRF-Token'],'csrf-original');assert(!r.body.operation.includes('execute_refund'));}
 hold={};nodes.loadRefundApplications.click();await flush();const page=hold;hold=null;configure(null);page.resolve(response({records:[record],has_more:true,next_cursor:'f'.repeat(64)}));await flush();assert.equal(nodes.refundApplications.children.length,0);assert(nodes.moreRefundApplications.hidden);assert(nodes.loadRefundApplications.disabled);assert.equal(nodes.orderLines.children.length,0);
 assert(!fs.readFileSync(process.argv[2],'utf8').match(/innerHTML|localStorage|sessionStorage/));console.log('Workbench refund and order snapshot DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
