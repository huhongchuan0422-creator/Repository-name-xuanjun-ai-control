'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(process.argv[3],'utf8');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.value='';this.textContent='';this.hidden=false;this.dataset={};}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;this.textContent='';}
 reset(){for(const n of Object.values(nodes))if(['input','textarea','select'].includes(n.tagName))n.value='';}
 click(){if(!this.disabled&&this.onclick)return this.onclick();} remove(){}
 set innerHTML(_){throw Error('unsafe DOM');}
}
const nodes=Object.fromEntries([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
const walk=n=>[n,...n.children.flatMap(walk)];
const document={getElementById:id=>{assert(nodes[id],id);return nodes[id];},createElement:tag=>new Element(tag),querySelectorAll:tag=>Object.values(nodes).flatMap(walk).filter(n=>n.tagName===tag)};
let requests=[],hold=null,fail=false,taskState='PENDING';
const response=result=>({ok:true,status:200,json:async()=>({result})});
const snapshot=()=>({orders:[{order_id:'so_test',state:'PREPARED',currency:'CNY'}],review_tasks:[{task_id:'task1',order_id:'so_test',state:taskState,kind:'REFUND',reason:'<img src=x onerror=alert(1)>'}]});
const context={window:{},document,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);requests.push({url,options,body});
 if(hold)return new Promise(resolve=>hold.resolve=resolve);
 if(fail){fail=false;return {ok:false,status:403,json:async()=>({})};}
 switch(body.operation){
 case 'workspace_info':return response({role:body.workspace==='owner'?'PLATFORM_OWNER':'CUSTOMER',pricing_allowed:body.workspace==='owner'});
 case 'owner_admin_snapshot':return response(snapshot());
 case 'owner_review_open':return response({task_id:body.params.task_id,state:'PENDING'});
 case 'owner_review_close':taskState=body.params.state;return response({task_id:body.params.task_id,state:taskState});
 case 'owner_refund_reversal_plan':return response({action:'REFUND_REVIEW_ONLY',provider_refund_executed:false,entitlement_revoked:false,revenue_reversed:false});
 case 'owner_diagnostics':return response({status:'HOLD',automatic_repair_executed:false,production_release_authorized:false});
 default:throw Error(body.operation);
 }
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunitySaas,flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
const submit=async id=>{nodes[id].onsubmit({preventDefault(){}});await flush();};
(async()=>{
 assert(nodes.saasAdmin.hidden);assert(nodes.adminReload.disabled);
 configure({csrf:'owner-csrf',workspace:'owner'});await flush();assert(!nodes.saasAdmin.hidden);
 nodes.adminReload.click();await flush();assert(nodes.adminReviews.children[0].textContent.includes('<img'));assert.equal(nodes.adminReviews.children[0].children.length,1);
 nodes.adminOrders.children[0].children[0].click();await flush();assert.equal(nodes.refundOrderId.value,'so_test');
 nodes.reviewTaskId.value='task2';nodes.reviewKind.value='REFUND';nodes.reviewReason.value='Review only';await submit('reviewOpenForm');
 nodes.adminReviews.children[0].children[0].click();await flush();nodes.closeEventId.value='event1';nodes.closeState.value='RESOLVED';await submit('reviewCloseForm');assert.equal(taskState,'RESOLVED');assert.equal(nodes.adminReviews.children[0].children.length,0);
 nodes.refundReason.value='Review original receipt';await submit('refundPlanForm');assert(nodes.refundPlan.textContent.includes('未执行退款'));assert(nodes.refundPlan.textContent.includes('REFUND_REVIEW_ONLY'));
 nodes.adminDiagnostics.click();await flush();assert(nodes.diagnosticResult.textContent.includes('HOLD'));assert(nodes.diagnosticResult.textContent.includes('未自动修复'));
 for(const r of requests){assert.equal(r.url,'/customer/saas-api');assert.equal(r.options.credentials,'same-origin');assert.equal(r.options.redirect,'error');assert.equal(r.options.headers['X-CSRF-Token'],'owner-csrf');assert.equal(r.body.workspace,'owner');}
 assert.deepEqual(requests.find(r=>r.body.operation==='owner_review_close').body.params,{task_id:'task1',event_id:'event1',state:'RESOLVED'});
 fail=true;nodes.adminReload.click();await flush();assert.equal(nodes.adminOrders.children.length,0);assert(nodes.notice.textContent.includes('无权'));
 // Failed mutations are not retried or presented as successful.
 const beforeFailure=requests.filter(r=>r.body.operation==='owner_review_open').length;fail=true;await submit('reviewOpenForm');assert.equal(requests.filter(r=>r.body.operation==='owner_review_open').length,beforeFailure+1);assert(nodes.adminResult.textContent.includes('结果未确认'));
 // Customer cannot invoke hidden admin handlers, even through form dispatch.
 configure({csrf:'customer-csrf',workspace:'customer'});await flush();assert(nodes.saasAdmin.hidden);let count=requests.length;await submit('refundPlanForm');nodes.adminReload.click();await flush();assert.equal(requests.length,count);
 // A stale admin response cannot render in a new identity or unlock its controls.
 configure({csrf:'owner-csrf',workspace:'owner'});await flush();hold={};nodes.adminReload.click();await flush();const old=hold;hold=null;
 configure({csrf:'new-csrf',workspace:'customer'});await flush();old.resolve(response(snapshot()));await flush();assert(nodes.saasAdmin.hidden);assert.equal(nodes.adminOrders.children.length,0);assert.equal(nodes.adminReviews.children.length,0);
 configure({csrf:'owner-csrf',workspace:'owner'});await flush();hold={};nodes.adminDiagnostics.click();await flush();const diagnostic=hold;hold=null;configure(null);diagnostic.resolve(response({status:'STALE'}));await flush();assert.equal(nodes.diagnosticResult.textContent,'');assert(nodes.adminReload.disabled);assert.equal(nodes.reviewReason.value,'');assert.equal(nodes.closeEventId.value,'');
 // Corrupt-store HOLD reports have no report field and remain readable.
 configure({csrf:'owner-csrf',workspace:'owner'});await flush();hold={};nodes.adminDiagnostics.click();await flush();const corrupt=hold;hold=null;corrupt.resolve(response({status:'HOLD',reason:'OFFLINE_STORE_CHECK_FAILED',automatic_repair_executed:false}));await flush();assert(nodes.diagnosticResult.textContent.includes('OFFLINE_STORE_CHECK_FAILED'));configure(null);
 // Stale workspace_info cannot grant an owner's UI after logout.
 hold={};configure({csrf:'old',workspace:'owner'});await flush();const info=hold;hold=null;configure(null);info.resolve(response({role:'PLATFORM_OWNER',pricing_allowed:true}));await flush();assert(nodes.saasAdmin.hidden);assert(nodes.adminReload.disabled);
 assert(!fs.readFileSync(process.argv[2],'utf8').match(/innerHTML|localStorage|sessionStorage/));
 console.log('SaaS admin DOM contracts: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
