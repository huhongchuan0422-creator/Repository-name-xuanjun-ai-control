import test from 'node:test';
import assert from 'node:assert/strict';
import {FeedbackClient} from '../demos/pr122-delivery-review/feedback-client.mjs';
import {projectProjection} from '../demos/pr122-delivery-review/project-projection.mjs';
const b={project:'project-a',page:'/review/consumer/',version:'a'.repeat(64)};
const response=data=>({ok:true,json:async()=>data});
test('unknown submit is read back by original key, never re-POSTed or replaced by edited text',async()=>{
 let posts=0,committed=false;const client=new FeedbackClient({key:()=> 'logical-request-00001',csrf:()=> 'fixture',fetcher:async(url,opt)=>{
   if(url.endsWith('change_context'))return response({});
   if(url.endsWith('change_submit_idempotent')){posts++;committed=true;throw Error('connection lost after commit');}
   return response({cases:committed?[{id:'change-1',events:[{kind:'REQUEST',payload:{page:b.page,page_sha256:b.version,idempotency_key:'logical-request-00001'}}]}]:[]});
 }});
 assert.equal((await client.submit(b,'原意见')).state,'UNKNOWN');
 assert.deepEqual(await client.submit(b,'改过的意见'),{state:'SAVED',id:'change-1',recovered:true});assert.equal(posts,1);
});
test('unknown with no receipt stays unknown and performs no second write',async()=>{
 let posts=0;const client=new FeedbackClient({key:()=> 'logical-request-00001',csrf:()=>'',fetcher:async url=>{
 if(url.endsWith('change_context'))return response({});if(url.endsWith('change_submit_idempotent')){posts++;throw Error('offline');}return response({cases:[]});}});
 await client.submit(b,'意见');assert.equal((await client.submit(b,'意见')).state,'UNKNOWN');assert.equal(posts,1);
});
test('cross-page/version records are never returned as current history',async()=>{
 const c=new FeedbackClient({csrf:()=>'',fetcher:async url=>response(url.endsWith('change_context')?{}:{cases:[{id:'wrong',events:[{kind:'REQUEST',payload:{page:b.page,page_sha256:'b'.repeat(64)}}]},{id:'right',events:[{kind:'REQUEST',payload:{page:b.page,page_sha256:b.version}}]}]})});
 assert.deepEqual((await c.read(b)).map(x=>x.id),['right']);
});
test('permission failure prevents submit',async()=>{
 let calls=0;const c=new FeedbackClient({csrf:()=>'',fetcher:async()=>{calls++;return {ok:false,status:403,json:async()=>({error:'DENIED'})};}});
 await assert.rejects(c.submit(b,'意见'),/DENIED/);assert.equal(calls,1);
});
test('missing source is unconnected; task/CI success never migrates a project',()=>{
 assert.equal(projectProjection(null).connected,false);
 const p=projectProjection({projects:[{id:'a',title:'项目',phase:'CI PASS',runtime:'SUCCESS'}]});assert.equal(p.developing.length,1);assert.equal(p.cases.length,0);
});
test('delivery requires acceptance and real release, public cases additionally require selected asset approval',()=>{
 const p={id:'a',title:'项目',delivery:{accepted:true,live:true,acceptance_ref:'original-acceptance',release_ref:'original-release'},showcase:{approved:true,approval_ref:'owner-consent',assets:[{kind:'description',value:'已确认说明',public_approved:true},{kind:'image',value:'/private/admin',public_approved:false}]}};
 const q=projectProjection({projects:[p]});assert.equal(q.developing.length,0);assert.equal(q.cases[0].assets.length,1);
 assert.equal(projectProjection({projects:[{...p,showcase:null}]}).cases.length,0);
 assert.equal(projectProjection({projects:[{...p,delivery:{...p.delivery,release_ref:''}}]}).developing.length,1);
});
