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
let requests=[],hold=null,fail=false,networkFailure=false;
const response=result=>({ok:true,json:async()=>({result})}),cursor='staff_'+'0'.repeat(39)+'1';
const record={workspace:'staff_'+'a'.repeat(40),user_id:'original_user',active:false,operations:['community.orders_page','community.summary']};
const context={window:{},document,fetch:async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,options,body});if(hold)return new Promise(resolve=>hold.resolve=resolve);if(networkFailure){networkFailure=false;throw Error("network result unknown");}if(fail){fail=false;return {ok:false,status:403,json:async()=>({})};}switch(body.operation){
 case 'community.staff_list':return response(body.params.after_id?{records:[record],has_more:false,next_cursor:null}:{records:[],has_more:true,next_cursor:cursor});
 case 'community.staff_grant':record.active=true;return response({workspace:record.workspace,operations:body.params.operations});
 case 'community.staff_remove':record.active=false;return response({workspace:record.workspace,active:false});
 default:throw Error(body.operation);
}}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunityWorkbench,flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
(async()=>{
 configure({csrf:'csrf-original',workspace:'merchant'});nodes.staffList.click();await flush();assert.equal(requests.length,1);assert.equal(nodes.staffRecords.children.length,0);assert(nodes.staffRecords.textContent.includes('仍有记录待查'));assert(!nodes.moreStaff.hidden);await flush();assert.equal(requests.length,1);
 nodes.moreStaff.click();await flush();assert.equal(requests.at(-1).body.params.after_id,cursor);assert(nodes.moreStaff.hidden);assert(nodes.staffRecords.children[0].textContent.includes('已撤销'));
 const beforeSelect=requests.length;nodes.staffRecords.children[0].children[0].click();await flush();assert.equal(requests.length,beforeSelect);assert.equal(nodes.staffUser.value,record.user_id);assert.equal(nodes.staffWorkspace.value,record.workspace);assert.equal(nodes.staffOrders.checked,false);assert.equal(nodes.staffOrderPages.checked,true);assert.equal(nodes.staffOrderDetail.checked,false);assert.equal(nodes.staffSummary.checked,true);assert.equal(nodes.staffSettings.checked,false);assert(nodes.staffSelected.textContent.includes('重新授权'));
 nodes.staffGrantForm.onsubmit({preventDefault(){}});await flush();assert.deepEqual(requests.at(-1).body.params,{user_id:record.user_id,operations:['community.orders_page','community.summary']});

 assert.equal(nodes.staffRecords.children.length,0);assert.equal(nodes.staffSelected.textContent,'');assert.equal(nodes.staffWorkspace.value,'');assert(nodes.staffResult.textContent.includes('重新读取'));assert(nodes.moreStaff.hidden);
 nodes.staffList.click();await flush();nodes.moreStaff.click();await flush();assert(nodes.staffRecords.children[0].textContent.includes('有效'));nodes.staffRecords.children[0].children[0].click();await flush();
 nodes.staffRemove.click();await flush();assert.deepEqual(requests.at(-1).body.params,{workspace:record.workspace});assert.equal(nodes.staffRecords.children.length,0);assert.equal(nodes.staffSelected.textContent,'');assert.equal(nodes.staffWorkspace.value,'');assert(nodes.staffResult.textContent.includes('已记录'));
 // Neither a known denial nor a lost response can leave an obsolete status or report success.
 for(const failure of ['denial','unknown']){
  nodes.staffList.click();await flush();nodes.moreStaff.click();await flush();nodes.staffRecords.children[0].children[0].click();await flush();
  const before=requests.length;if(failure==='denial')fail=true;else networkFailure=true;
  nodes.staffGrantForm.onsubmit({preventDefault(){}});await flush();assert.equal(requests.length,before+1);assert.equal(nodes.staffSelected.textContent,'');assert.equal(nodes.staffRecords.children.length,0);assert(nodes.staffResult.textContent.includes('待确认'));assert(!nodes.staffResult.textContent.includes('已记录'));assert(!nodes.staffResult.textContent.includes('有效'));
 }

 fail=true;nodes.staffList.click();await flush();assert(nodes.notice.textContent.includes('无此权限'));assert.equal(nodes.staffRecords.children.length,0);assert.equal(nodes.staffWorkspace.value,'');assert.equal(nodes.staffUser.value,'');assert(!nodes.staffSummary.checked);
 // Old-identity page cannot restore employee data or cursor after logout.
 hold={};nodes.staffList.click();await flush();const pending=hold;hold=null;configure(null);pending.resolve(response({records:[record],has_more:true,next_cursor:cursor}));await flush();assert.equal(nodes.staffRecords.children.length,0);assert.equal(nodes.staffSelected.textContent,'');assert(nodes.moreStaff.hidden);assert(nodes.staffList.disabled);assert.equal(nodes.staffWorkspace.value,'');
 for(const r of requests){assert.equal(r.options.credentials,'same-origin');assert.equal(r.options.headers['X-CSRF-Token'],'csrf-original');assert.equal(r.body.workspace,'merchant');assert.equal(r.url,'/community/operations');}
 assert(!fs.readFileSync(process.argv[2],'utf8').match(/innerHTML|localStorage|sessionStorage/));console.log('Workbench staff pagination and exact permissions DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
