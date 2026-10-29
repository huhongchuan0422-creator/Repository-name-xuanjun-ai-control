'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.dataset={};this.listeners={};this.textContent='';}
 append(...nodes){for(const n of nodes){n.parentNode=this;this.children.push(n);}}
 replaceChildren(...nodes){this.children=[];this.textContent='';this.append(...nodes);}
 setAttribute(){} addEventListener(event,fn){this.listeners[event]=fn;}
 querySelectorAll(selector){return walk(this).slice(1).filter(n=>selector.split(',').includes(n.tagName));}
 click(){if(!this.disabled)return (this.onclick||this.listeners.click)?.({preventDefault(){}});}
 set innerHTML(value){throw Error('NO_UNSAFE_HTML');}
}
const walk=e=>[e,...e.children.flatMap(walk)],nodes={},markup=fs.readFileSync(process.argv[3],'utf8');
for(const id of ['applicationVersion','loadHistory','historyStatus','historyRows','moreHistory','historyMaterials'])assert(markup.includes('id="'+id+'"'));
for(const match of markup.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g))nodes[match[2]]=new Element(match[1]);
const actions=[...markup.matchAll(/<button[^>]*data-action="([^"]+)"/g)].map(match=>{const button=new Element('button');button.dataset.action=match[1];return button;});
const document={getElementById:id=>nodes[id]??=(new Element()),createElement:tag=>new Element(tag),createTextNode:t=>Object.assign(new Element(),{textContent:t}),querySelectorAll:s=>s==='[data-action]'?actions:s==='button'?[...Object.values(nodes).flatMap(walk).filter(n=>n.tagName==='button'),...actions]:[]};
const makeApp=id=>({application:id,revision:51,status:'DRAFT',entity_type:'ENTERPRISE',fields:{store_name:id},required_materials:[],materials:{},reviewer_note:'CURRENT_NOTE_NOT_HISTORICAL'});
let denyRead=false,holdRead=false,readDeferred=[];
let app=makeApp('app1'),calls=[],deferred=[],hold=false,deny=false,override=null;
const material={kind:'business_license',version:'v_'+'a'.repeat(32),sequence:1,actor:'original-user',created_at:100,expires_at:null,review:null};
const record=n=>({revision:n,event:'CORRECTION',actor:'original-reviewer',occurred_at:100,previous_revision:n-1,status_before:'IN_REVIEW',status_after:'CORRECTION_REQUIRED',note:'original reason '+n,decision:null,material_kind:null,materials:[material],evidence:'CAPTURED_AT_EVENT',unavailable:[]});
const page=(application,after)=>({application,records:Array.from({length:after?1:50},(_,i)=>record(after+i+1)),has_more:!after,next_revision:after?null:50,material_versions:[material],material_versions_truncated:false,legacy_material_event_linkage:'NOT_ESTABLISHED',payment_enabled:false});
const reply=result=>({ok:true,status:200,json:async()=>({result:structuredClone(result),payment_enabled:false})});
const context={document,window:{},location:{pathname:process.argv[4]||'/merchant/join'},structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(body.operation==='catalog')return reply({materials:[{id:'business_license',title:'营业执照'}]});
 if(['mine','review_list'].includes(body.operation))return reply({applications:[app],next_cursor:null});
 if(['read','review_read'].includes(body.operation)){if(holdRead)return new Promise(resolve=>readDeferred.push(resolve));if(denyRead)return {ok:false,status:403,json:async()=>{throw Error('SECRET_BODY');}};return reply(app);}
 if(body.operation==='review'){
  assert.equal(body.params.action,'REOPEN');assert.equal(body.params.application,app.application);assert.equal(body.params.revision,app.revision);assert.equal(body.params.note,'REOPEN_EXPLICIT_REASON');
  app={...app,status:'CORRECTION_REQUIRED',revision:app.revision+1,reviewer_note:body.params.note};return reply(app);
 }
 if(['history','review_history'].includes(body.operation)){
  assert.deepEqual(Object.keys(body.params).sort(),['after_revision','application']);
  if(hold)return new Promise(resolve=>deferred.push(resolve));
  if(deny)return{ok:false,status:403,json:async()=>{throw Error('MUST_NOT_PARSE_DENIED_PRIVATE_BODY');}};
  return reply(override||page(body.params.application,body.params.after_revision));
 }
 throw Error('Unexpected operation '+body.operation);
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const flush=async()=>{for(let i=0;i<80;i++)await Promise.resolve();};
const reload=async()=>{await context.window.configureCommunityOnboarding({csrf:'current-original-csrf'});await flush();if(context.location.pathname==='/merchant/review'){walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();}};
const text=node=>walk(node).map(n=>n.textContent).join('\n');
(async()=>{
 await flush();await reload();assert.equal(nodes.detail.hidden,false);
 nodes.note.value='old private reason';nodes.wechatState.textContent='old private provider';
 denyRead=true;walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();
 assert.equal(nodes.detail.hidden,true);assert.equal(nodes.summary.children.length,0);assert.equal(nodes.materials.children.length,0);
 assert.equal(nodes.applicationVersion.textContent,'');assert.equal(nodes.wechatState.textContent,'');assert.equal(nodes.note.value,'');assert.equal(nodes.reviewActions.hidden,true);assert.equal(nodes.openingActions.hidden,true);
 // Failure leaves no selected application from which a new financial/review action can proceed.
 assert(!calls.some(c=>['review','wechat_execute','open_workbench'].includes(c.operation)));
 denyRead=false;walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();assert.equal(nodes.detail.hidden,false);assert(nodes.applicationVersion.textContent.includes('app1'));
 holdRead=true;walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();assert.equal(nodes.detail.hidden,true);const old=readDeferred.shift();
 app=makeApp('app2');await context.window.configureCommunityOnboarding({csrf:'new-original-csrf'});await flush();
 old(reply(makeApp('app1')));await flush();assert.equal(nodes.detail.hidden,true);assert.equal(nodes.summary.children.length,0);
 holdRead=false;walk(nodes.applications).find(n=>n.tagName==='button').click();await flush();assert(nodes.applicationVersion.textContent.includes('app2'));
 console.log('SCOPED_MOCK_DOM_PASS reviewer denied clear, request-start clear, stale identity, successful reread; no business submission');
})().catch(e=>{console.error(e);process.exitCode=1;});
