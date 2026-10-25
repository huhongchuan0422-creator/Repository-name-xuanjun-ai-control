import test from'node:test';import assert from'node:assert/strict';import{makeApi,verifiedPreviewUrl}from'../src/api.js';
test('same-origin identity/login/logout and csrf',async()=>{const q=[];const a=makeApi(async(u,o)=>{q.push([u,o]);return{ok:true,status:200,json:async()=>u.endsWith('login')?{csrf:'c'}:{}}},()=> 'csrf');await a.me();await a.login('a@b.com','password1234');await a.logout();assert.equal(q[0][1].credentials,'same-origin');assert.equal(q[1][1].headers['X-CSRF-Token'],'csrf');assert.deepEqual(JSON.parse(q[2][1].body),{})});
test('transport ambiguity only for POST',async()=>{const a=makeApi(async()=>{throw Error('x')},()=> 'c');await assert.rejects(a.me(),e=>e.uncertain===false);await assert.rejects(a.submit('p','/x','a'.repeat(64),'t'),e=>e.uncertain===true)});
test('preview URL normalizes then requires exact project/key/version and rejects encodings/backslash',()=>{const v='a'.repeat(64),k='b'.repeat(64),good='/customer/center/preview/proj/'+k+'/'+v;assert.equal(verifiedPreviewUrl(good,'proj',v),good);for(const x of['/customer/center/preview/proj/'+k+'/../'+v,'/customer/center/preview/proj/%2e%2e/'+v,'/customer/center/preview/proj/'+k+'\\'+v,'//evil/customer/center/preview/proj/'+k+'/'+v,'/customer/center/preview/other/'+k+'/'+v,'/customer/center/preview/proj/nothex/'+v])assert.throws(()=>verifiedPreviewUrl(x,'proj',v),/UNTRUSTED/)});
test('retest exact 4dc body',async()=>{let b;const a=makeApi(async(u,o)=>{b=JSON.parse(o.body);return{ok:true,status:200,json:async()=>({automatic_charge:false})}},()=> 'c');const r=await a.retest({project:'p',caseId:'case',revision:2,page:'/x',version:'a'.repeat(64),delivery_sha256:'d'.repeat(64),action:'ACCEPT',reason:'ok'});assert.deepEqual(Object.keys(b),['project','case','revision','page','version','delivery_sha256','action','reason']);assert.equal(r.automatic_charge,false)});

test('POST 408/5xx JSON responses are ambiguous while GET remains definite',async()=>{
 for(const status of[408,500,503]){
  const post=makeApi(async()=>({ok:false,status,json:async()=>({error:'backend '+status})}),()=> 'c');
  await assert.rejects(post.submit('p','/x','a'.repeat(64),'t'),e=>e.status===status&&e.uncertain===true);
  await assert.rejects(post.logout(),e=>e.status===status&&e.uncertain===true);
  await assert.rejects(post.me(),e=>e.status===status&&e.uncertain===false);
 }
});

test('material save uses exact e7 fields and preserves Chinese backend error text',async()=>{
 let body;
 const api=makeApi(async(u,o)=>{body=JSON.parse(o.body);return{ok:true,status:200,json:async()=>({version:'v1',revision:1,state:'PARTIAL'})}},()=> 'csrf');
 const r=await api.save('project-a','license',0,'DOCUMENT','JVBERi0xLjc=',null);
 assert.deepEqual(body,{project:'project-a',item:'license',revision:0,kind:'DOCUMENT',content:'JVBERi0xLjc=',expires:null});
 assert.equal(r.state,'PARTIAL');
 const denied=makeApi(async()=>({ok:false,status:403,json:async()=>({error:'权限不足、凭据失效或请求不符合要求'})}),()=> 'csrf');
 await assert.rejects(denied.save('project-a','license',0,'DOCUMENT','JVBERi0xLjc=',null),e=>e.status===403&&e.message==='权限不足、凭据失效或请求不符合要求');
});

test('material transition uses exact five fields and history download URL is server object-id bound',async()=>{
 let body;
 const api=makeApi(async(u,o)=>{body=JSON.parse(o.body);return{ok:true,status:200,json:async()=>({state:'SUBMITTED',revision:2,accepted_revision:null})}},()=> 'csrf');
 const r=await api.transition('project-a','license',1,'submit','');
 assert.deepEqual(body,{project:'project-a',item:'license',revision:1,action:'submit',reason:''});
 assert.equal(r.state,'SUBMITTED');
 assert.equal(api.downloadUrl('project-a','o_'+'a'.repeat(32)),'/customer/center/api/download/project-a/o_'+'a'.repeat(32));
 assert.throws(()=>api.downloadUrl('project-a','guessed-object'),/INVALID_OBJECT/);
});
