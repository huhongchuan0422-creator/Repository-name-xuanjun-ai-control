import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {makeApi} from '../src/api.js';
import {createIntentJournal} from '../src/submission.js';
import {ProjectJourney} from '../src/journey.js';
const v1='a'.repeat(64),v2='b'.repeat(64);
const storage=()=>{const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};
function boundary(){
 const state={member:true,expired:false,current:v1,cases:[],messages:[{id:'m0',channel:'WEB',body:'原项目问题',status:'ARCHIVED',created:1700000000}],lost:false};
 const server=http.createServer(async(req,res)=>{
  const send=(code,obj)=>{res.writeHead(code,{'content-type':'application/json'});res.end(JSON.stringify(obj));};
  let body={};if(req.method==='POST'){let raw='';for await(const x of req)raw+=x;if(req.headers['x-csrf-token']!=='csrf')return send(403,{error:'CSRF_REQUIRED'});body=JSON.parse(raw||'{}');}
  const path=req.url;const project=body.project||path.split('/').at(-1);
  if(path==='/customer/center/api/me')return send(200,{user_id:'u1',projects:state.member&&!state.expired?[{id:'own',title:'客户首批项目',role:'OWNER',tenant:'tenant-A',customer:'customer-A'}]:[],channels:{}});
  if(project==='tenant-B'||!state.member||state.expired)return send(403,{error:'PROJECT_PERMISSION_REQUIRED'});
  if(path==='/customer/center/api/checklist/own')return send(200,{project:'own',overall:'PARTIAL',requirements_revision:7,items:[{id:'REQ-1',title:'首页需求',purpose:'展示客户确认内容',required:true,category:'CUSTOMER',submission_type:'PRIVATE_DOCUMENT',state:'PARTIAL',revision:2,accepted_revision:1,needs_reverification:false,versions:[{id:'v_1',seq:1,actor:'u1',kind:'DOCUMENT',created:1700000001,expires:null,details:{}}]}]});
  if(path==='/customer/center/api/previews/own')return send(200,{project:'own',pages:[{path:'/index.html',sha256:state.current,url:'/customer/center/preview/own/key/'+state.current}]});
  if(path==='/customer/center/api/changes/own')return send(200,{project:'own',cases:state.cases});
  if(path==='/customer/center/api/messages/own')return send(200,{messages:state.messages});
  if(path==='/customer/center/api/message'){state.messages.push({id:'m'+state.messages.length,channel:'WEB',body:body.body,status:'ARCHIVED',created:1700000020});return send(200,{id:state.messages.at(-1).id,status:'ARCHIVED',ai_response:'PENDING_PROVIDER'});}
  if(['change_context','change_submit','change_updates','change_retest'].some(x=>path.endsWith('/'+x))){
   if(body.version!==state.current)return send(409,{error:'AUTHORITY_CHANGED'});
   if(path.endsWith('/change_context'))return send(200,{project:'own',page:body.page,version:body.version,execution_scope:'TRUSTED_CUSTOMER_FRONTEND'});
   if(path.endsWith('/change_submit')){const n=state.cases.length+1,r={id:'case-'+n,event_id:'event-'+n};state.cases.push({id:r.id,events:[{id:r.event_id,seq:1,kind:'REQUEST',payload:{state:'REQUESTED',page:body.page,page_sha256:body.version,request:body.text,intent:body.intent}}]});if(state.lost){state.lost=false;req.socket.destroy();return;}return send(200,r);}
   if(path.endsWith('/change_updates'))return send(200,{updates:state.cases.map(c=>({project:'own',case:c.id,page:body.page,before_sha256:v1,after_sha256:v2,revision:c.events.at(-1).seq,delivery_sha256:'d'.repeat(64),state:'AWAIT_RETEST',label:'已按您的建议调整，待您复验'}))});
   if(path.endsWith('/change_retest')){const c=state.cases.find(x=>x.id===body.case);if(!c||body.delivery_sha256!=='d'.repeat(64))return send(403,{error:'CURRENT_DELIVERY_REQUIRED'});c.events.push({id:'retest-1',seq:2,kind:'RETEST',payload:{state:body.action==='ACCEPT'?'RETEST_ACCEPTED':'RETEST_FEEDBACK',delivery_sha256:body.delivery_sha256,page:body.page,page_sha256:body.version,reason:body.reason,automatic_charge:false}});return send(200,{id:'retest-1',revision:2,state:c.events.at(-1).payload.state});}
  }
  send(404,{error:'NOT_FOUND'});
 });
 return {server,state};
}
async function withBoundary(fn){const {server,state}=boundary();await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;const fetcher=(url,opts)=>fetch(origin+url,opts);try{return await fn({state,api:makeApi(fetcher,()=> 'csrf')});}finally{await new Promise(r=>server.close(r));}}

test('actual HTTP journey uses 4dc response shapes through project -> preview -> feedback -> case -> update -> retest -> Q&A',()=>withBoundary(async({api})=>{
 const j=new ProjectJourney(api,createIntentJournal(storage(),()=> 'A'.repeat(20)));
 const me=await j.projects();assert.deepEqual(me.projects[0],{id:'own',title:'客户首批项目',role:'OWNER',tenant:'tenant-A',customer:'customer-A'});
 const p=me.projects[0],d=await j.project(p);assert.equal(d.checklist.requirements_revision,7);assert.equal(d.checklist.items[0].purpose,'展示客户确认内容');assert.equal(d.previews.pages[0].sha256,v1);assert.equal(d.messages.messages[0].body,'原项目问题');
 await j.feedbackContext(p,d.previews.pages[0]);const submitted=await j.submitLegacy(p,d.previews.pages[0],'请调整首页版本');assert.deepEqual(submitted,{id:'case-1',event_id:'event-1'});
 const refreshed=await j.project(p);assert.equal(refreshed.changes.cases[0].events[0].payload.page_sha256,v1);assert.equal(refreshed.changes.cases[0].events[0].payload.request,'请调整首页版本');
 const ups=await j.updates(p,d.previews.pages[0]);assert.equal(ups.updates[0].after_sha256,v2);const r=await j.retest(p,d.previews.pages[0],ups.updates[0],'ACCEPT','本版修改已复核');assert.equal(r.state,'RETEST_ACCEPTED');
 const q=await j.ask(p,'这个需求对应原任务吗？');assert.equal(q.status,'ARCHIVED');assert.equal((await api.messages('own')).messages.at(-1).body,'这个需求对应原任务吗？');
}));

test('actual HTTP boundary rejects cross-tenant, revoke/expiry and version drift',()=>withBoundary(async({api,state})=>{
 await assert.rejects(api.previews('tenant-B'),e=>e.status===403);state.member=false;await assert.rejects(api.previews('own'),e=>e.status===403);state.member=true;state.expired=true;await assert.rejects(api.checklist('own'),e=>e.status===403);state.expired=false;state.current=v2;await assert.rejects(api.context('own','/index.html',v1),e=>e.status===409);
}));

test('legacy UI path loses response after server accepted: result stays unknown and does not resend',()=>withBoundary(async({api,state})=>{
 const store=storage(),j=new ProjectJourney(api,createIntentJournal(store,()=> 'B'.repeat(20))),p={id:'own',role:'OWNER'},page={path:'/index.html',sha256:v1};state.lost=true;
 await assert.rejects(j.submitLegacy(p,page,'只提交一次'),e=>e.uncertain===true);assert.equal(state.cases.length,1);
 await assert.rejects(j.submitLegacy(p,page,'只提交一次'),/LEGACY_SUBMISSION_ALREADY_ATTEMPTED/);assert.equal(state.cases.length,1);
 const cases=await api.changes('own');assert.equal(cases.cases[0].events[0].payload.request,'只提交一次');
}));
