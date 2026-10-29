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
for(const id of ['withdrawActions','withdrawConfirmed','withdrawApplication','withdrawalState'])assert(markup.includes('id="'+id+'"'));
assert(markup.includes('value="WITHDRAWN"'));assert(!markup.includes('value="EXPIRED"'));
for(const m of markup.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g))nodes[m[2]]=new Element(m[1]);
for(const id of ['legal_name','store_name','address','contact','identity_type','entity_type','category','delegated','saveDraft'])nodes.profile.append(nodes[id]);
nodes.wechatProfile.append(nodes.wechatFields,new Element('button'));
const actions=[...markup.matchAll(/<button[^>]*data-action="([^"]+)"/g)].map(m=>Object.assign(new Element('button'),{dataset:{action:m[1]}}));
const document={getElementById:id=>nodes[id]??=(new Element()),createElement:tag=>new Element(tag),createTextNode:t=>Object.assign(new Element(),{textContent:t}),querySelectorAll:s=>s==='[data-action]'?actions:s==='button'?[...new Set(Object.values(nodes).flatMap(walk).filter(n=>n.tagName==='button')),...actions]:[]};
const makeApp=(id,status='DRAFT')=>({application:id,revision:10,status,entity_type:'ENTERPRISE',fields:{store_name:id},required_materials:[],materials:{},reviewer_note:''});
let app=makeApp('app1'),calls=[],deferred=[],hold=false,mode='success';
const reply=result=>({ok:true,status:200,json:async()=>({result:structuredClone(result),payment_enabled:false})});
const context={document,window:{},location:{pathname:process.argv[4]||'/merchant/join'},structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(body.operation==='catalog')return reply({materials:[]});
 if(['mine','review_list'].includes(body.operation))return reply({applications:[app],next_cursor:null});
 if(['read','review_read'].includes(body.operation))return reply(app);
 if(body.operation==='withdraw'){
  assert.deepEqual(Object.keys(body.params).sort(),['application','revision']);
  if(hold)return new Promise((resolve,reject)=>deferred.push({resolve,reject}));
  if(['denied','conflict','network'].includes(mode))return{ok:false,status:mode==='denied'?403:mode==='conflict'?400:503,json:async()=>{throw Error('PRIVATE_FAILED_BODY_MUST_NOT_BE_READ');}};
  if(mode==='badJSON')return{ok:true,status:200,json:async()=>{throw Error('PRIVATE_PARSE_ERROR');}};
  const result={...app,revision:app.revision+1,status:'WITHDRAWN'};
  if(mode==='wrongApplication')result.application='foreign';if(mode==='wrongRevision')result.revision=app.revision;if(mode==='booleanRevision')result.revision=true;if(mode==='wrongState')result.status='APPROVED';
  return reply(result);
 }
 throw Error('Unexpected operation '+body.operation);
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const flush=async()=>{for(let n=0;n<100;n++)await Promise.resolve();};
const reload=async()=>{await context.window.configureCommunityOnboarding({csrf:'current-original-csrf'});await flush();if(context.location.pathname==='/merchant/review'){walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();}};
const withdrawals=()=>calls.filter(c=>c.operation==='withdraw');
(async()=>{
 await flush();await reload();
 if(context.location.pathname==='/merchant/review'){
  for(const status of ['DRAFT','CORRECTION_REQUIRED','WITHDRAWN']){
   app=makeApp('review-app',status);await reload();assert.equal(nodes.withdrawActions.hidden,true);const before=calls.length;nodes.withdrawConfirmed.checked=true;nodes.withdrawApplication.click();await flush();assert.equal(calls.length,before);
  }
  assert.equal(withdrawals().length,0);console.log('Reviewer cannot borrow applicant withdrawal DOM: PASS');return;
 }
 assert.equal(nodes.withdrawActions.hidden,false);assert.equal(nodes.withdrawConfirmed.checked,false);
 nodes.withdrawApplication.click();await flush();assert.equal(withdrawals().length,0);assert(nodes.status.textContent.includes('确认'));
 nodes.withdrawConfirmed.checked=true;nodes.withdrawApplication.click();nodes.withdrawApplication.click();await flush();
 assert.equal(withdrawals().length,1);assert.equal(nodes.applicationState.textContent,'已撤回');assert.equal(nodes.withdrawActions.hidden,true);assert.equal(nodes.withdrawConfirmed.checked,false);
 assert.equal(nodes.saveDraft.disabled,true);assert.equal(nodes.store_name.disabled,true);assert.equal(nodes.wechatExecute.disabled,true);assert.equal(nodes.wechatRead.disabled,false);assert.equal(nodes.wechatQuery.disabled,false);
 assert(nodes.wechatProfile.querySelectorAll('input,select,button').every(e=>e.disabled));assert(nodes.withdrawalState.textContent.includes('不可编辑'));assert(nodes.withdrawalState.textContent.includes('独立查询'));
 const before=calls.length;nodes.profile.listeners.submit({preventDefault(){}});await flush();nodes.wechatProfile.onsubmit({preventDefault(){}});await flush();nodes.submitApplication.click();await flush();assert.equal(calls.length,before);
 nodes.newApplication.click();await flush();assert.equal(nodes.detail.hidden,true);assert.equal(nodes.saveDraft.disabled,false);assert.equal(nodes.store_name.disabled,false);assert.equal(nodes.withdrawActions.hidden,true);assert.equal(nodes.withdrawConfirmed.checked,false);assert.equal(nodes.wechatExecute.disabled,false);
 for(const status of ['SUBMITTED','IN_REVIEW','APPROVED','REJECTED','WITHDRAWN']){
  app=makeApp('terminal-'+status,status);await reload();assert.equal(nodes.withdrawActions.hidden,true);const count=withdrawals().length;nodes.withdrawConfirmed.checked=true;nodes.withdrawApplication.click();await flush();assert.equal(withdrawals().length,count);
 }
 app=makeApp('correction','CORRECTION_REQUIRED');await reload();assert.equal(nodes.withdrawActions.hidden,false);
 for(mode of ['denied','conflict','network','badJSON','wrongApplication','wrongRevision','booleanRevision','wrongState']){
  await reload();const count=withdrawals().length;nodes.withdrawConfirmed.checked=true;nodes.withdrawApplication.click();await flush();assert.equal(withdrawals().length,count+1);assert.equal(nodes.applicationState.textContent,'待补件');assert.equal(nodes.withdrawConfirmed.checked,false);assert(nodes.status.textContent.includes('未确认'));assert(!nodes.status.textContent.includes('PRIVATE'));await flush();assert.equal(withdrawals().length,count+1);
 }
 mode='success';hold=true;
 // Old success, rejection, and malformed body cannot overwrite a newer account/app or unlock its pending operation.
 for(const outcome of ['success','reject','malformed']){
  app=makeApp('old-'+outcome);await reload();nodes.withdrawConfirmed.checked=true;nodes.withdrawApplication.click();await flush();const old=deferred.shift();
  app=makeApp('new-'+outcome);await reload();assert.equal(nodes.withdrawConfirmed.checked,false);nodes.withdrawConfirmed.checked=true;nodes.withdrawApplication.click();await flush();const fresh=deferred.shift();
  if(outcome==='reject')old.reject(Error('OLD_PRIVATE_ERROR'));else if(outcome==='malformed')old.resolve({ok:false,status:403,json:async()=>{throw Error('OLD_PRIVATE_BODY');}});else old.resolve(reply({...makeApp('old-'+outcome),revision:11,status:'WITHDRAWN'}));
  await flush();assert.equal(nodes.applicationState.textContent,'草稿');assert.equal(nodes.withdrawApplication.disabled,true);assert.equal(nodes.newApplication.disabled,true);assert.equal(nodes.withdrawConfirmed.checked,true);assert(!nodes.status.textContent.includes('OLD_PRIVATE'));
  fresh.resolve(reply({...app,revision:11,status:'WITHDRAWN'}));await flush();assert.equal(nodes.applicationState.textContent,'已撤回');assert.equal(nodes.withdrawApplication.disabled,false);assert.equal(nodes.withdrawConfirmed.checked,false);
 }
 hold=false;app=makeApp('filter','WITHDRAWN');await reload();nodes.statusFilter.value='WITHDRAWN';nodes.statusFilter.listeners.change();await flush();assert.equal(calls.at(-1).operation,'mine');assert.equal(calls.at(-1).params.status,'WITHDRAWN');
 assert(!calls.some(c=>['wechat_execute','wechat_media','wechat_cancel'].includes(c.operation)));
 console.log('Own draft/correction withdrawal confirmation, terminal state and stale response DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
