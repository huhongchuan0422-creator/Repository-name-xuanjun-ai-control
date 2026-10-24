import test from'node:test';import assert from'node:assert/strict';import{createIntentJournal,submitLegacy,submitCandidate}from'../src/submission.js';
const sess=()=>{const m=new Map;return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};const mk=(project='A',page='/x',version='a'.repeat(64),text='first')=>({project,page,version,text,intent:'RECTIFICATION'});
test('legacy unknown is scoped and stores no feedback body',async()=>{const s=sess(),j=createIntentJournal(s),x=mk('A'),api={submit:async()=>{const e=Error('lost');e.uncertain=true;throw e}};await assert.rejects(submitLegacy(api,j,x));assert.ok(j.legacyUnknown(x));assert.equal(JSON.stringify(j.legacyUnknown(x)).includes('first'),false);assert.equal(j.legacyUnknown(mk('B')),null);await assert.rejects(submitLegacy(api,j,x),/RECONCILE_FIRST/)});
test('scoped unknown A does not block B and explicit clear allows A later new request',async()=>{const s=sess(),j=createIntentJournal(s),a=mk('A'),b=mk('B'),seen=[];j.markLegacyUnknown(a);const api={submit:async(...args)=>{seen.push(args);return{id:'c'+seen.length}}};assert.deepEqual(await submitLegacy(api,j,b),{id:'c1'});j.clearLegacyUnknown(a);assert.deepEqual(await submitLegacy(api,j,{...a,text:'later'}),{id:'c2'});assert.equal(j.legacyUnknown(a),null)});
test('definite 400/403/409 do not create unknown marker',async()=>{for(const status of[400,403,409]){const s=sess(),j=createIntentJournal(s),x=mk();await assert.rejects(submitLegacy({submit:async()=>{const e=Error('bad');e.status=status;e.uncertain=false;throw e}},j,x));assert.equal(j.legacyUnknown(x),null)}});
test('candidate definite failure clears memory slot; unknown explicit retry reuses key',async()=>{const s=sess(),j=createIntentJournal(s,()=> 'K'.repeat(20)),x=mk();let n=0;const api={submitIdempotent:async()=>{n++;if(n===1){const e=Error('409');e.status=409;throw e}if(n===2){const e=Error('lost');e.uncertain=true;throw e}return{id:'c',event_id:'e'}}};await assert.rejects(submitCandidate(api,j,x));assert.equal(j.get(x),null);await assert.rejects(submitCandidate(api,j,x));assert.equal(j.get(x).state,'unknown');await assert.rejects(submitCandidate(api,j,x),/EXPLICIT_RETRY/);assert.deepEqual(await submitCandidate(api,j,x,{retryUnknown:true}),{id:'c',event_id:'e'})});

test('legacy backend 503 creates scoped UNKNOWN and candidate 503 retains one key for explicit retry',async()=>{
 const {makeApi}=await import('../src/api.js');
 const legacySession=sess(),legacyJournal=createIntentJournal(legacySession),lx=mk('L');
 const legacyApi=makeApi(async()=>({ok:false,status:503,json:async()=>({error:'processing unknown'})}),()=> 'c');
 await assert.rejects(submitLegacy(legacyApi,legacyJournal,lx),e=>e.status===503&&e.uncertain===true);
 assert.ok(legacyJournal.legacyUnknown(lx));
 assert.equal(legacyJournal.legacyUnknown(mk('M')),null);

 const candidateSession=sess(),candidateJournal=createIntentJournal(candidateSession,()=> 'R'.repeat(20)),cx=mk('C');
 let calls=0,keys=[];
 const candidateApi=makeApi(async(url,o)=>{calls++;keys.push(JSON.parse(o.body).idempotency_key);if(calls===1)return{ok:false,status:503,json:async()=>({error:'unknown'})};return{ok:true,status:200,json:async()=>({id:'case-c',event_id:'event-c'})}},()=> 'c');
 await assert.rejects(submitCandidate(candidateApi,candidateJournal,cx),e=>e.status===503&&e.uncertain===true);
 await assert.rejects(submitCandidate(candidateApi,candidateJournal,cx),/EXPLICIT_RETRY/);
 assert.equal(calls,1);
 assert.deepEqual(await submitCandidate(candidateApi,candidateJournal,cx,{retryUnknown:true}),{id:'case-c',event_id:'event-c'});
 assert.equal(calls,2);assert.equal(keys[0],keys[1]);
});
