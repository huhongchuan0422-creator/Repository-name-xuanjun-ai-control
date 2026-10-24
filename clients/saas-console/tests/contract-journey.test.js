import test from 'node:test';
import assert from 'node:assert/strict';
import {makeApi,verifiedPreviewUrl} from '../src/api.js';
import {createIntentJournal,submitIntent,IntentConflict} from '../src/submission.js';
const sha='a'.repeat(64),newSha='b'.repeat(64);
const storage=()=>{const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};
const x=(project='own',version=sha,text='fix footer')=>({project,page:'/index.html',version,text,intent:'RECTIFICATION'});
function server({owner='own',version=sha,idempotent=true,loseResponse=false}={}){
 const cases=[],seen=new Map(),calls=[],claims=new Set(['own']);let count=0,expired=false;
 const send=async(url,opts)=>{
  calls.push({url,opts});const route=url.replace('/customer/center/api/','');const data=opts.body?JSON.parse(opts.body):{};
  const reply=(status,obj)=>({ok:status<400,status,json:async()=>obj});
  if(route==='me')return reply(200,{user_id:'u1',projects:[...claims].map(id=>({id,title:'Project '+id,role:'OWNER'}))});
  const project=data.project??route.split('/')[1];
  if(project&&(!claims.has(project)||expired))return reply(403,{error:'PROJECT_PERMISSION_REQUIRED'});
  if(route.startsWith('checklist/'))return reply(200,{project,overall:'PARTIAL'});
  if(route.startsWith('previews/'))return reply(200,{project,pages:[{path:'/index.html',sha256:version,url:'/customer/center/preview/'+project+'/key/'+version}]});
  if(route.startsWith('changes/'))return reply(200,{project,cases});
  if(['change_context','change_submit','change_submit_idempotent','change_updates','change_retest'].includes(route)){
   if(data.version!==version)return reply(409,{error:'AUTHORITY_CHANGED'});
   if(route==='change_context')return reply(200,{project,page:data.page,version:data.version});
   if(route==='change_updates')return reply(200,{updates:cases.map(c=>({case:c.id,revision:1,page:data.page,version,delivery_sha256:newSha,state:'AWAIT_RETEST'}))});
   if(route==='change_retest'){
    if(data.delivery_sha256!==newSha||!cases.some(c=>c.id===data.case))return reply(403,{error:'CURRENT_DELIVERY_REQUIRED'});
    return reply(200,{state:'RETEST_ACCEPTED',final_contract_acceptance:false});
   }
   if(route==='change_submit_idempotent'&&!idempotent)return reply(404,{error:'NOT_FOUND'});
   if(route==='change_submit_idempotent'){
    const key=data.idempotency_key,body=JSON.stringify({...data,idempotency_key:undefined});
    if(seen.has(key)){const old=seen.get(key);return reply(old.body===body?200:409,old.body===body?old.result:{error:'IDEMPOTENCY_CONFLICT'});}
    const result={id:'case-'+(++count),event_id:'event-'+count};cases.push({id:result.id,events:[{kind:'REQUEST',payload:{state:'REQUESTED'}}]});seen.set(key,{body,result});
    if(loseResponse){loseResponse=false;throw Error('RESPONSE_LOST');}
    return reply(200,result);
   }
   const result={id:'case-'+(++count),event_id:'event-'+count};cases.push({id:result.id});if(loseResponse){loseResponse=false;throw Error('RESPONSE_LOST');}return reply(200,result);
  }
  return reply(404,{error:'NOT_FOUND'});
 };
 return {send,cases,calls,claims,setVersion:v=>{version=v},setLose:()=>{loseResponse=true},expire:()=>{expired=true}};
}
test('real endpoint journey: me -> project -> private listing -> context -> submit -> updates -> retest',async()=>{
 const s=server(),a=makeApi(s.send,()=> 'csrf'),j=createIntentJournal(storage(),()=> 'A'.repeat(20));
 const me=await a.me();assert.deepEqual(me.projects.map(v=>v.id),['own']);
 assert.equal((await a.checklist('own')).overall,'PARTIAL');const listing=await a.previews('own');
 assert.equal(verifiedPreviewUrl(listing.pages[0].url),'/customer/center/preview/own/key/'+sha);
 await a.context('own','/index.html',sha);const result=await submitIntent(a,j,x(),{idempotent:true});
 assert.deepEqual(result,{id:'case-1',event_id:'event-1'});assert.equal((await a.changes('own')).cases.length,1);
 const updates=await a.updates('own','/index.html',sha);const u=updates.updates[0];
 const r=await a.retest({project:'own',caseId:u.case,revision:u.revision,page:'/index.html',version:sha,delivery_sha256:u.delivery_sha256,action:'ACCEPT',reason:'checked'});
 assert.equal(r.state,'RETEST_ACCEPTED');assert.equal(r.final_contract_acceptance,false);
 assert.ok(s.calls.every(c=>c.opts.credentials==='same-origin'));
 assert.ok(s.calls.filter(c=>c.opts.method==='POST').every(c=>c.opts.headers['X-CSRF-Token']==='csrf'));
});
test('expired/revoked access and cross-tenant project denied by backend',async()=>{
 const s=server(),a=makeApi(s.send,()=> 'csrf');await assert.rejects(a.previews('tenant-B'),e=>e.status===403);
 s.claims.delete('own');await assert.rejects(a.context('own','/index.html',sha),e=>e.status===403);
 assert.deepEqual((await a.me()).projects,[]);
 const t=server(),ta=makeApi(t.send,()=> 'csrf');t.expire();await assert.rejects(ta.previews('own'),e=>e.status===403);
});
test('version drift rejects context, submit and retest',async()=>{
 const s=server(),a=makeApi(s.send,()=> 'csrf'),j=createIntentJournal(storage(),()=> 'B'.repeat(20));s.setVersion(newSha);
 await assert.rejects(a.context('own','/index.html',sha),e=>e.status===409);
 await assert.rejects(submitIntent(a,j,x(),{idempotent:true}),e=>e.status===409);
 await assert.rejects(a.retest({project:'own',caseId:'x',revision:1,page:'/index.html',version:sha,delivery_sha256:newSha,action:'ACCEPT',reason:'ok'}),e=>e.status===409);
 assert.equal(s.cases.length,0);
});
test('duplicate click and lost response reuse one key and return same case/event',async()=>{
 const s=server({loseResponse:true}),a=makeApi(s.send,()=> 'csrf'),store=storage(),j=createIntentJournal(store,()=> 'C'.repeat(20));
 await assert.rejects(submitIntent(a,j,x(),{idempotent:true}),e=>e.uncertain);
 assert.equal(j.load(x()).state,'unknown');await assert.rejects(submitIntent(a,j,x(),{idempotent:true}),/EXPLICIT_RETRY_REQUIRED/);
 const again=createIntentJournal(store,()=> 'D'.repeat(20));const r=await submitIntent(a,again,x(),{idempotent:true,retryUnknown:true});
 assert.deepEqual(r,{id:'case-1',event_id:'event-1'});assert.equal(s.cases.length,1);
 assert.deepEqual(await submitIntent(a,again,x(),{idempotent:true}),r);
 assert.equal(s.calls.filter(c=>c.url.endsWith('/change_submit_idempotent')).length,2);
});
test('same key different body conflicts locally and backend rejects 409',async()=>{
 const s=server(),a=makeApi(s.send,()=> 'csrf'),j=createIntentJournal(storage(),()=> 'E'.repeat(20));await submitIntent(a,j,x(),{idempotent:true});
 assert.throws(()=>j.prepare(x('own',sha,'changed body')),IntentConflict);
 await assert.rejects(a.submitIdempotent({...x('own',sha,'different'),idempotency_key:'E'.repeat(20)}),e=>e.status===409);
 assert.equal(s.cases.length,1);
});
test('legacy mode never retries ambiguous request, even after reload',async()=>{
 const s=server({loseResponse:true}),a=makeApi(s.send,()=> 'csrf'),store=storage(),j=createIntentJournal(store,()=> 'F'.repeat(20));
 await assert.rejects(submitIntent(a,j,x(),{idempotent:false}),e=>e.uncertain);
 const restored=createIntentJournal(store,()=> 'G'.repeat(20));await assert.rejects(submitIntent(a,restored,x(),{idempotent:false}),/LEGACY_SUBMISSION_ALREADY_ATTEMPTED/);
 assert.equal(s.calls.filter(c=>c.url.endsWith('/change_submit')).length,1);
});
test('candidate endpoint missing: explicit 404, no fallback to legacy POST',async()=>{
 const s=server({idempotent:false}),a=makeApi(s.send,()=> 'csrf'),j=createIntentJournal(storage(),()=> 'H'.repeat(20));
 await assert.rejects(submitIntent(a,j,x(),{idempotent:true}),e=>e.status===404);
 assert.equal(s.calls.filter(c=>c.url.endsWith('/change_submit')).length,0);
});
test('random key validation, new explicit intent, unknown locked pending',async()=>{
 const store=storage(),j=createIntentJournal(store,()=> 'bad');assert.throws(()=>j.prepare(x()),/INVALID_IDEMPOTENCY_KEY/);
 const good=createIntentJournal(store,()=> 'I'.repeat(20));good.prepare(x());good.mark(x(),'unknown');assert.throws(()=>good.newRequest(x()),/UNKNOWN_RESULT_RECONCILE_FIRST/);
 good.mark(x(),'confirmed',{id:'case'});good.newRequest(x());assert.equal(good.load(x()),null);
});
