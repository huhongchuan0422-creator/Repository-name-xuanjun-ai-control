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
