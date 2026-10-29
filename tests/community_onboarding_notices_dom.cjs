'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.dataset={};this.listeners={};this.textContent='';}
 append(...nodes){for(const n of nodes){n.parentNode=this;this.children.push(n);}}
 replaceChildren(...nodes){this.children=[];this.textContent='';this.append(...nodes);}
 setAttribute(){}addEventListener(event,fn){this.listeners[event]=fn;}
 querySelectorAll(selector){return walk(this).slice(1).filter(n=>selector.split(',').includes(n.tagName));}
 click(){if(!this.disabled)return(this.onclick||this.listeners.click)?.({preventDefault(){}});}
 set innerHTML(value){throw Error('NO_UNSAFE_HTML');}
}
const walk=e=>[e,...e.children.flatMap(walk)],nodes={},markup=fs.readFileSync(process.argv[3],'utf8');
for(const id of ['applicationNotices','loadAdmissionNotices','admissionNoticeStatus','admissionNotices','moreAdmissionNotices'])assert(markup.includes('id="'+id+'"'));
for(const m of markup.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g))nodes[m[2]]=new Element(m[1]);
const actions=[...markup.matchAll(/<button[^>]*data-action="([^"]+)"/g)].map(m=>Object.assign(new Element('button'),{dataset:{action:m[1]}}));
const document={getElementById:id=>nodes[id]??=(new Element()),createElement:tag=>new Element(tag),createTextNode:t=>Object.assign(new Element(),{textContent:t}),querySelectorAll:s=>s==='[data-action]'?actions:s==='button'?[...Object.values(nodes).flatMap(walk).filter(n=>n.tagName==='button'),...actions]:[]};
const makeApp=id=>({application:id,revision:200,status:'CORRECTION_REQUIRED',entity_type:'ENTERPRISE',fields:{store_name:id},required_materials:[],materials:{},reviewer_note:'PRIVATE_DETAIL_NOT_IN_NOTICE'});
let app=makeApp('app1'),calls=[],deferred=[],hold=false,deny=false,denyRead=false,badJSON=false,override=null,markOverride=null;
const id=n=>n.toString(16).padStart(64,'0');
const record=(application,n)=>({id:id(n),application,revision:n,kind:'MERCHANT_ONBOARDING_RESULT_V1',reference:application+':'+n,event:'CORRECTION',status:'CORRECTION_REQUIRED',message:'第'+n+'版需要补件；说明请查看受保护详情',read:false,created_at:100});
const page=(application,after)=>({application,records:Array.from({length:after?1:50},(_,i)=>record(application,(after?50:0)+i+1)),has_more:!after,next_cursor:after?null:id(50),payment_enabled:false});
const reply=result=>({ok:true,status:200,json:async()=>({result:structuredClone(result),payment_enabled:false})});
const context={document,window:{},location:{pathname:process.argv[4]||'/merchant/join'},structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(body.operation==='catalog')return reply({materials:[]});
 if(['mine','review_list'].includes(body.operation))return reply({applications:[app],next_cursor:null});
 if(['read','review_read'].includes(body.operation))return denyRead?{ok:false,status:403,json:async()=>{throw Error('READ_DENIED_PRIVATE_BODY');}}:reply(app);
 if(['notices','notice_read'].includes(body.operation)){
  if(hold)return new Promise(resolve=>deferred.push(resolve));
  if(deny)return{ok:false,status:403,json:async()=>{throw Error('DENIED_PRIVATE_BODY_MUST_NOT_BE_READ');}};
  if(badJSON)return{ok:true,status:200,json:async()=>{throw Error('PRIVATE_JSON_ERROR');}};
  if(body.operation==='notice_read'){
   assert.deepEqual(Object.keys(body.params).sort(),['application','notice_id']);
   return reply(markOverride||{...record(body.params.application,parseInt(body.params.notice_id,16)),read:true});
  }
  assert.deepEqual(Object.keys(body.params).sort(),['after_id','application']);
  return reply(override||page(body.params.application,body.params.after_id));
 }
 throw Error('Unexpected operation '+body.operation);
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const flush=async()=>{for(let n=0;n<80;n++)await Promise.resolve();};
const reload=async()=>{await context.window.configureCommunityOnboarding({csrf:'original-current-csrf'});await flush();if(context.location.pathname==='/merchant/review'){walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();}};
const text=node=>walk(node).map(n=>n.textContent).join('\n');
const firstMark=()=>walk(nodes.admissionNotices.children[0]).find(n=>n.tagName==='button');
(async()=>{
 await flush();await reload();
 if(context.location.pathname==='/merchant/review'){
  assert.equal(nodes.applicationNotices.hidden,true);nodes.loadAdmissionNotices.click();await flush();assert(!calls.some(c=>['notices','notice_read'].includes(c.operation)));return;
 }
 assert.equal(nodes.applicationNotices.hidden,false);nodes.loadAdmissionNotices.click();await flush();
 assert.equal(nodes.admissionNotices.children.length,50);assert.equal(nodes.moreAdmissionNotices.hidden,false);assert.equal(calls.at(-1).params.application,'app1');
 nodes.moreAdmissionNotices.click();await flush();assert.equal(nodes.admissionNotices.children.length,51);assert.equal(nodes.moreAdmissionNotices.hidden,true);assert.equal(calls.at(-1).params.after_id,id(50));
 assert(!text(nodes.admissionNotices).includes('PRIVATE_DETAIL'));const oldButton=firstMark();oldButton.click();oldButton.click();await flush();assert.equal(calls.filter(c=>c.operation==='notice_read').length,1);assert(nodes.admissionNotices.children[0].children[0].textContent.endsWith('已读'));
 oldButton.click();await flush();assert.equal(calls.filter(c=>c.operation==='notice_read').length,1);
 deny=true;nodes.loadAdmissionNotices.click();await flush();assert.equal(nodes.admissionNotices.children.length,0);assert.equal(nodes.moreAdmissionNotices.hidden,true);assert(!nodes.status.textContent.includes('PRIVATE_BODY'));deny=false;
 hold=true;nodes.loadAdmissionNotices.click();await flush();const old=deferred.shift();app=makeApp('app2');await reload();nodes.loadAdmissionNotices.click();await flush();const fresh=deferred.shift();
 old(reply(page('app1','')));await flush();assert.equal(nodes.admissionNotices.children.length,0);assert.equal(nodes.loadAdmissionNotices.disabled,true);
 fresh(reply(page('app2','')));await flush();assert.equal(nodes.admissionNotices.children.length,50);assert.equal(nodes.loadAdmissionNotices.disabled,false);hold=false;
 for(const value of [{...page('foreign','')},{...page('app2',''),next_cursor:id(1)},{...page('app2',''),records:[{...record('app2',1),revision:true}]}]){
  override=value;nodes.loadAdmissionNotices.click();await flush();assert.equal(nodes.admissionNotices.children.length,0);assert.equal(nodes.moreAdmissionNotices.hidden,true);
 }
 override=null;nodes.loadAdmissionNotices.click();await flush();markOverride={...record('other',1),read:true};firstMark().click();await flush();assert.equal(nodes.admissionNotices.children.length,0);markOverride=null;
 nodes.loadAdmissionNotices.click();await flush();hold=true;firstMark().click();await flush();const oldMark=deferred.shift();app=makeApp('app3');await reload();nodes.loadAdmissionNotices.click();await flush();const freshAgain=deferred.shift();
 oldMark(reply({...record('app2',1),read:true}));await flush();assert.equal(nodes.admissionNotices.children.length,0);assert.equal(nodes.loadAdmissionNotices.disabled,true);
 freshAgain(reply(page('app3','')));await flush();assert(nodes.admissionNotices.children[0].children[0].textContent.endsWith('未读'));hold=false;
 badJSON=true;nodes.moreAdmissionNotices.click();await flush();assert.equal(nodes.admissionNotices.children.length,0);assert(!nodes.status.textContent.includes('PRIVATE_JSON_ERROR'));badJSON=false;
 override={...page('app3',id(50)),records:[{...record('app3',1),message:'<img src=x onerror=unsafe()> fixture text'}]};nodes.loadAdmissionNotices.click();await flush();assert(text(nodes.admissionNotices).includes('<img src=x'));
 // A newly reviewed version must be readable even when the form still shows an older revision.
 override={...page('app3',id(50)),records:[record('app3',201)]};nodes.loadAdmissionNotices.click();await flush();assert.equal(nodes.admissionNotices.children.length,1);assert(text(nodes.admissionNotices).includes('第201版'));
 app={...app,revision:201};walk(nodes.admissionNotices).find(n=>n.tagName==='button'&&n.textContent==='查看申请最新状态').click();await flush();assert(nodes.applicationVersion.textContent.includes('201'));assert.equal(nodes.admissionNotices.children.length,0);
 nodes.loadAdmissionNotices.click();await flush();denyRead=true;walk(nodes.admissionNotices).find(n=>n.tagName==='button'&&n.textContent==='查看申请最新状态').click();await flush();assert.equal(nodes.admissionNotices.children.length,0);assert(!nodes.status.textContent.includes('PRIVATE_BODY'));
 assert(!calls.some(c=>['download','wechat_execute'].includes(c.operation)));
 console.log('Original application notice paging, read acknowledgement and identity context DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
