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
let app=makeApp('app1'),calls=[],deferred=[],hold=false,deny=false,override=null;
const material={kind:'business_license',version:'v_'+'a'.repeat(32),sequence:1,actor:'original-user',created_at:100,expires_at:null,review:null};
const record=n=>({revision:n,event:'CORRECTION',actor:'original-reviewer',occurred_at:100,previous_revision:n-1,status_before:'IN_REVIEW',status_after:'CORRECTION_REQUIRED',note:'original reason '+n,decision:null,material_kind:null,materials:[material],evidence:'CAPTURED_AT_EVENT',unavailable:[]});
const page=(application,after)=>({application,records:Array.from({length:after?1:50},(_,i)=>record(after+i+1)),has_more:!after,next_revision:after?null:50,material_versions:[material],material_versions_truncated:false,legacy_material_event_linkage:'NOT_ESTABLISHED',payment_enabled:false});
const reply=result=>({ok:true,status:200,json:async()=>({result:structuredClone(result),payment_enabled:false})});
const context={document,window:{},location:{pathname:process.argv[4]||'/merchant/join'},structuredClone,Uint8Array,atob,btoa,Blob,URL,setTimeout,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(body.operation==='catalog')return reply({materials:[{id:'business_license',title:'营业执照'}]});
 if(['mine','review_list'].includes(body.operation))return reply({applications:[app],next_cursor:null});
 if(['read','review_read'].includes(body.operation))return reply(app);
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
 await flush();await reload();assert(nodes.applicationVersion.textContent.includes('app1'));assert(nodes.applicationVersion.textContent.includes('51'));
 nodes.loadHistory.click();await flush();assert.equal(nodes.historyRows.children.length,50);assert.equal(nodes.moreHistory.hidden,false);
 const operation=context.location.pathname==='/merchant/review'?'review_history':'history';assert.equal(calls.at(-1).operation,operation);assert.equal(calls.at(-1).params.after_revision,0);
 nodes.moreHistory.click();await flush();assert.equal(nodes.historyRows.children.length,51);assert.equal(nodes.moreHistory.hidden,true);assert.equal(calls.at(-1).params.after_revision,50);
 assert(text(nodes.historyRows).includes('original reason 1'));assert(text(nodes.historyMaterials).includes(material.version));assert(!text(nodes.historyRows).includes('CURRENT_NOTE_NOT_HISTORICAL'));
 // A legacy reason/time/material association is explicitly unknown.
 override={...page(app.application,50),records:[{...record(1),note:null,occurred_at:null,materials:null,evidence:'LEGACY_EVENT_ONLY'}]};
 nodes.loadHistory.click();await flush();assert(text(nodes.historyRows).includes('旧审核原因未完整留存'));assert(text(nodes.historyRows).includes('时间未能唯一关联'));assert(text(nodes.historyRows).includes('关联未留存'));
 override=null;nodes.loadHistory.click();await flush();deny=true;nodes.moreHistory.click();await flush();assert.equal(nodes.historyRows.children.length,0);assert.equal(nodes.moreHistory.hidden,true);assert(!nodes.status.textContent.includes('MUST_NOT_PARSE'));
 deny=false;hold=true;nodes.loadHistory.click();await flush();const old=deferred.shift();app=makeApp('app2');await reload();assert.equal(nodes.historyRows.children.length,0);
 nodes.loadHistory.click();await flush();const fresh=deferred.shift();old(reply(page('app1',0)));await flush();assert.equal(nodes.historyRows.children.length,0);assert.equal(nodes.loadHistory.disabled,true);
 fresh(reply(page('app2',0)));await flush();assert.equal(nodes.historyRows.children.length,50);assert.equal(nodes.loadHistory.disabled,false);assert(nodes.applicationVersion.textContent.includes('app2'));hold=false;
 // Wrong application, invalid cursor and malformed JSON fail closed, with no raw body in the error.
 for(const value of [{...page('foreign-app',0)}, {...page('app2',0),next_revision:1}, {...page('app2',0),records:[{...record(1),revision:true}]}]){
  override=value;nodes.loadHistory.click();await flush();assert.equal(nodes.historyRows.children.length,0);assert.equal(nodes.moreHistory.hidden,true);
 }
 override={...page('app2',50),records:[{...record(1),note:'<img src=x onerror=unsafe()> original private text'}]};nodes.loadHistory.click();await flush();assert(text(nodes.historyRows).includes('<img src=x'));assert(!calls.some(c=>['download','wechat_execute'].includes(c.operation)));
 if(context.location.pathname==='/merchant/review'){
  app={...app,status:'REJECTED'};await reload();assert.equal(nodes.reviewActions.hidden,false);
  assert.deepEqual(actions.filter(button=>!button.hidden).map(button=>button.dataset.action),['REOPEN']);
  const reopen=actions.find(button=>button.dataset.action==='REOPEN');nodes.note.value='';const count=calls.length;reopen.click();await flush();assert.equal(calls.length,count);
  nodes.note.value='REOPEN_EXPLICIT_REASON';reopen.click();await flush();assert.equal(app.status,'CORRECTION_REQUIRED');assert.equal(nodes.historyRows.children.length,0);assert.equal(reopen.hidden,true);
 }else assert.equal(nodes.reviewActions.hidden,true);
 console.log('Onboarding exact application history, paging, legacy evidence and stale identity DOM: PASS '+context.location.pathname);
})().catch(error=>{console.error(error);process.exitCode=1;});
