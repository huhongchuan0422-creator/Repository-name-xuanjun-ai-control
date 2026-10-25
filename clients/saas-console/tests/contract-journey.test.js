import test from'node:test';import assert from'node:assert/strict';import{makeApi}from'../src/api.js';import{createIntentJournal,submitCandidate}from'../src/submission.js';
const ss=()=>{const m=new Map;return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};const x={project:'p',page:'/index.html',version:'a'.repeat(64),text:'fix',intent:'RECTIFICATION'};
function fake({lost=false,available=true}={}){const seen=new Map,calls=[];return{calls,send:async(u,o)=>{calls.push(u);const b=o.body?JSON.parse(o.body):{},reply=(s,d)=>({ok:s<400,status:s,json:async()=>d});if(!available)return reply(404,{error:'NOT_FOUND'});if(!u.endsWith('/change_submit_idempotent'))return reply(404,{error:'NOT_FOUND'});const body=JSON.stringify({...b,idempotency_key:undefined}),old=seen.get(b.idempotency_key);if(old)return reply(old.body===body?200:409,old.body===body?old.result:{error:'IDEMPOTENCY_CONFLICT'});const result={id:'case-1',event_id:'event-1'};seen.set(b.idempotency_key,{body,result});if(lost){lost=false;throw Error('lost')}return reply(200,result)}}}
test('candidate lost response reuses same key only on explicit retry',async()=>{const f=fake({lost:true}),api=makeApi(f.send,()=> 'c'),j=createIntentJournal(ss(),()=> 'K'.repeat(20));await assert.rejects(submitCandidate(api,j,x),e=>e.uncertain);await assert.rejects(submitCandidate(api,j,x),/EXPLICIT_RETRY/);assert.deepEqual(await submitCandidate(api,j,x,{retryUnknown:true}),{id:'case-1',event_id:'event-1'});assert.equal(f.calls.length,2)});
test('candidate same key changed body returns server 409',async()=>{const f=fake(),api=makeApi(f.send,()=> 'c');await api.submitIdempotent({...x,idempotency_key:'Z'.repeat(20)});await assert.rejects(api.submitIdempotent({...x,text:'different',idempotency_key:'Z'.repeat(20)}),e=>e.status===409)});
test('candidate unavailable never falls back to legacy',async()=>{const f=fake({available:false}),api=makeApi(f.send,()=> 'c'),j=createIntentJournal(ss(),()=> 'Q'.repeat(20));await assert.rejects(submitCandidate(api,j,x),e=>e.status===404);assert.equal(f.calls.some(u=>u.endsWith('/change_submit')),false)});

test('material journey binds PRIVATE_DOCUMENT save and rejects wrong role/type',async()=>{
 const calls=[],api={save:async(...x)=>{calls.push(x);return{revision:2,state:'PARTIAL'}}},j=new (await import('../src/journey.js')).ProjectJourney(api,{});
 const p={id:'project-a',role:'OWNER'},item={id:'license',revision:1,submission_type:'PRIVATE_DOCUMENT',valid_until:null};
 assert.deepEqual(await j.saveMaterial(p,item,'JVBERi0='),{revision:2,state:'PARTIAL'});
 assert.deepEqual(calls[0],['project-a','license',1,'DOCUMENT','JVBERi0=',null]);
 await assert.rejects(j.saveMaterial({id:'project-a',role:'VIEWER'},item,'x'),/MATERIAL_WRITE_REQUIRED/);
 await assert.rejects(j.saveMaterial(p,{...item,submission_type:'OAUTH'},'x'),/PRIVATE_DOCUMENT_REQUIRED/);
});

test('CUS008 customer journey exposes submit only for owner/editor ready states and download uses returned object id',async()=>{
 const calls=[],api={
  transition:async(...x)=>{calls.push(['transition',...x]);return{state:'SUBMITTED',revision:x[2]+1,accepted_revision:null}},
  downloadUrl:(project,object)=>'/customer/center/api/download/'+project+'/'+object
 },j=new (await import('../src/journey.js')).ProjectJourney(api,{});
 const p={id:'project-a',role:'OWNER'},item={id:'license',revision:4,state:'NEEDS_CORRECTION'},v={details:{object_id:'o_'+'b'.repeat(32)}};
 assert.equal((await j.submitMaterial(p,item)).state,'SUBMITTED');
 assert.deepEqual(calls[0],['transition','project-a','license',4,'submit','']);
 assert.equal(j.materialDownloadUrl(p,v),'/customer/center/api/download/project-a/o_'+'b'.repeat(32));
 await assert.rejects(j.submitMaterial({id:'project-a',role:'REVIEWER'},item),/MATERIAL_SUBMIT_REQUIRED/);
 await assert.rejects(j.submitMaterial(p,{...item,state:'IN_REVIEW'}),/MATERIAL_NOT_READY/);
 assert.throws(()=>j.materialDownloadUrl(p,{details:{}}),/MATERIAL_OBJECT_REQUIRED/);
});
