import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const generated=process.env.WORK17_GENERATED_SITE;
const fixture={'/index.html':{type:'text/html; charset=utf-8',body:Buffer.from('<h1>fixture only</h1>').toString('base64')}};
const source=await readFile(new URL('./worker.mjs',import.meta.url),'utf8');
const {default:worker}=generated ? await import(pathToFileURL(generated+'/index.mjs')) :
  await import('data:text/javascript;base64,'+Buffer.from('const STATIC_FILES='+JSON.stringify(fixture)+';\n'+source).toString('base64'));
const SITE='https://center.wenwenwenyiyiyi.work';
const env={WORK17_OWNER_SITE_USER_ID:'fixture-site-user',WORK17_UK_READ_BEARER:'fixture_only_'.repeat(4)};
const req=(body='{"task_id":"target"}',extra={})=>new Request(SITE+'/api/work17/read',{
  method:'POST',headers:{Origin:SITE,'Content-Type':'application/json',
  'oai-authenticated-user-id':'fixture-site-user',...extra},body});
const kinds=['costs','usage','dependencies','resume','alert','handoff','canary'];
const envelope=()=>({schema:'WORK17_OWNER_HTTP_V1',task_id:'target',snapshot:{
  schema:'WORK_FOUNDATION_INTEGRATION_V1',binding_sha256:'a'.repeat(64),status:'HOLD',
  views:Object.fromEntries(kinds.map(k=>[k,{status:'HOLD',secret:'must-not-escape'}])),
  execution_granted:false,resume_granted:false,release_granted:false,send_performed:false,
  scan_complete:false,task_count_observed:1000,raw_descriptor:'must-not-escape'}});
async function withFetch(mock,body){const old=globalThis.fetch;globalThis.fetch=mock;
  try{await body();}finally{globalThis.fetch=old;}}
const upstream=(data=envelope())=>new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
test('asset bytes, root and HEAD retained (real107 locally; fixture1 on Hosted)',async()=>{
  const hashes=generated ? JSON.parse(await readFile(generated+'/preserved-assets.json')) :
    {'/index.html':createHash('sha256').update('<h1>fixture only</h1>').digest('hex')};
  assert.equal(Object.keys(hashes).length,generated ? 107 : 1);
  for(const [route,hash] of Object.entries(hashes)){
    const response=await worker.fetch(new Request(SITE+route),{});
    assert.equal(response.status,200);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),hash);
  }
  assert.equal((await worker.fetch(new Request(SITE+'/'),{})).status,200);
  assert.equal(await (await worker.fetch(new Request(SITE+'/',{method:'HEAD'}),{})).text(),'');
});
test('missing/wrong identity and service bypass never contacts UK',async()=>{
  await withFetch(()=>{throw new Error('UNEXPECTED_UK');},async()=>{
    for(const id of ['', 'other']) assert.equal((await worker.fetch(req(undefined,{'oai-authenticated-user-id':id}),env)).status,403);
    assert.equal((await worker.fetch(req(),{})).status,403);
    assert.equal((await worker.fetch(req(undefined,{'oai-authenticated-user-id':'','OAI-Sites-Authorization':'Bearer fixture'}),env)).status,403);
  });
});
test('same-origin and literal single task request required',async()=>{
  await withFetch(()=>{throw new Error('UNEXPECTED_UK');},async()=>{
    for(const body of ['{}','[]','{"task_id":"target","task_id":"other"}',
      '{"task_id":"target","authenticated":true}','{"task_id":"../target"}',
      '{"task_id":"target","db":"other"}','x'.repeat(513)])
      assert.equal((await worker.fetch(req(body),env)).status,400);
    for(const headers of [{Origin:'https://other.example'},{Origin:''},{'Content-Type':'text/plain'}])
      assert.equal((await worker.fetch(req(undefined,headers),env)).status,400);
  });
});
test('real fetch shape fixed endpoint/no redirects, summaries bounded and secrets absent',async()=>{
  await withFetch(async(url,options)=>{
    assert.equal(url,'https://uk.wenwenwenyiyiyi.work/api/work17/read');
    assert.equal(options.redirect,'error');assert.equal(options.method,'POST');
    assert.equal(options.headers.Authorization,'Bearer '+env.WORK17_UK_READ_BEARER);
    assert.deepEqual(JSON.parse(options.body),{task_id:'target'});
    assert.equal(options.headers['oai-authenticated-user-id'],undefined);
    return upstream();
  },async()=>{
    const response=await worker.fetch(req(),env);assert.equal(response.status,200);
    assert.equal(response.headers.get('Cache-Control'),'no-store');
    const text=await response.text();assert.ok(!text.includes('must-not-escape'));
    assert.ok(!text.includes(env.WORK17_UK_READ_BEARER));
    const data=JSON.parse(text);assert.equal(data.summary.length,7);
    assert.equal(data.remaining_count,null);assert.equal(data.status,'HOLD');
    assert.equal(data.execution_granted,false);
  });
});
test('missing credentials fail HOLD without UK contact',async()=>{
  await withFetch(()=>{throw new Error('UNEXPECTED_UK');},async()=>{
    const response=await worker.fetch(req(),{WORK17_OWNER_SITE_USER_ID:env.WORK17_OWNER_SITE_USER_ID});
    assert.equal(response.status,503);assert.equal((await response.json()).status,'HOLD');
  });
});
test('cross-task and incompatible original api/state responses rejected',async()=>{
  for(const data of [{tasks:[]},{...envelope(),task_id:'other'}])
    await withFetch(async()=>upstream(data),async()=>assert.equal((await worker.fetch(req(),env)).status,503));
});
test('upstream failure, malformed JSON and redirect cannot yield old success',async()=>{
  for(const mock of [async()=>{throw new Error('secret-path');},async()=>new Response('secret',{status:302}),
    async()=>new Response('{',{headers:{'Content-Type':'application/json'}}),
    async()=>new Response('{}',{headers:{'Content-Type':'text/html'}})])
    await withFetch(mock,async()=>{
      const response=await worker.fetch(req(),env);assert.equal(response.status,503);
      assert.ok(!(await response.text()).includes('secret'));
    });
});
test('snapshot cannot grant any action or omit a view',async()=>{
  for(const mutate of [s=>s.execution_granted=true,s=>s.resume_granted=true,
    s=>s.release_granted=true,s=>s.send_performed=true,s=>delete s.views.costs,
    s=>s.task_count_observed=1001,s=>s.binding_sha256='bad']){
    const data=envelope();mutate(data.snapshot);
    await withFetch(async()=>upstream(data),async()=>assert.equal((await worker.fetch(req(),env)).status,503));
  }
});
test('response byte cap and malformed view status reject',async()=>{
  const data=envelope();data.snapshot.views.costs.status='secret /path';
  const token=envelope();token.snapshot.views.costs.status='SECRET_TOKEN';
  for(const response of [upstream(data),upstream(token),new Response('x'.repeat(262145),{headers:{'Content-Type':'application/json'}})])
    await withFetch(async()=>response,async()=>assert.equal((await worker.fetch(req(),env)).status,503));
});
test('no success cache reused after read failure',async()=>{
  let count=0;
  await withFetch(async()=>{if(++count===1)return upstream();throw new Error('offline');},async()=>{
    assert.equal((await worker.fetch(req(),env)).status,200);
    assert.equal((await worker.fetch(req(),env)).status,503);
  });
});
