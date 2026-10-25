import assert from 'node:assert/strict';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {makeApi} from '../src/api.js';
import {ProjectJourney} from '../src/journey.js';
import {createIntentJournal} from '../src/submission.js';

const ROOT=process.env.XJ_PR122_E7_ROOT;
if(!ROOT) throw Error('HOLD_MISSING_XJ_PR122_E7_ROOT');
const HOST='wenwenwenyiyiyi.work', ORIGIN='https://wenwenwenyiyiyi.work', COOKIE='__Host-xj_customer';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function ss(){const m=new Map;return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}}
function sessionTransport(port){
 let cookie='',lastSet='';
 const t=async(url,o={})=>new Promise((resolve,reject)=>{
  const headers={Host:HOST,...(o.headers||{})};
  if(cookie)headers.Cookie=cookie;
  if(o.body!==undefined){headers.Origin=ORIGIN;headers['Content-Type']=headers['Content-Type']||'application/json';headers['Content-Length']=Buffer.byteLength(o.body)}
  const req=http.request({host:'127.0.0.1',port,path:url,method:o.method||'GET',headers},res=>{const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>{const body=Buffer.concat(chunks),sc=res.headers['set-cookie']?.[0];if(sc){lastSet=sc;const pair=sc.split(';',1)[0];if(pair.startsWith(COOKIE+'='))cookie=pair.endsWith('=')?'':pair}resolve(new Response(body,{status:res.statusCode,headers:res.headers}))})});
  req.on('error',reject);if(o.body!==undefined)req.write(o.body);req.end();
 });
 t.cookie=()=>cookie;t.lastSet=()=>lastSet;return t;
}
async function rawJson(t,op,body,csrf){const r=await t('/customer/center/api/'+op,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});let d={};try{d=await r.json()}catch{}return{status:r.status,data:d,headers:r.headers}}
async function control(port,path){return new Promise((resolve,reject)=>{const q=http.request({host:'127.0.0.1',port,path,method:'POST'},r=>{r.resume();r.on('end',()=>resolve(r.statusCode))});q.on('error',reject);q.end()})}

const py=spawn(process.env.PYTHON||'python3',['-B','-m','tests.pr122_customer_browser_server'],{cwd:ROOT,stdio:['ignore','pipe','pipe']});
let pyerr='';py.stderr.setEncoding('utf8');py.stderr.on('data',x=>pyerr+=x);py.stdout.setEncoding('utf8');
const first=await new Promise((resolve,reject)=>{let b='';const on=x=>{b+=x;const i=b.indexOf('\n');if(i>=0){py.stdout.off('data',on);resolve(b.slice(0,i))}};py.stdout.on('data',on);py.once('exit',c=>reject(Error('fixture exit '+c+' '+pyerr)))});
const info=JSON.parse(first);assert.equal(info.scope,'ISOLATED_FIXTURE_NOT_PRODUCTION');assert.equal(info.fixture_signer,'TEST_ONLY');
try{
 const ownerT=sessionTransport(info.port),reviewerT=sessionTransport(info.port),otherT=sessionTransport(info.port);
 let ownerCsrf='',reviewerCsrf='',otherCsrf='';
 const ownerApi=makeApi(ownerT,()=>ownerCsrf),reviewerApi=makeApi(reviewerT,()=>reviewerCsrf),otherApi=makeApi(otherT,()=>otherCsrf);
 ownerCsrf=(await ownerApi.login('owner@example.com','correct-password-123')).csrf;
 reviewerCsrf=(await reviewerApi.login('reviewer@example.com','correct-password-123')).csrf;
 otherCsrf=(await otherApi.login('other@example.com','correct-password-123')).csrf;
 assert.match(ownerT.lastSet(),/Secure/);assert.match(ownerT.lastSet(),/HttpOnly/);assert.match(ownerT.lastSet(),/SameSite=Strict/);
 const j=new ProjectJourney(ownerApi,createIntentJournal(ss(),()=> 'K'.repeat(20)));
 const me=await j.projects(),p=me.projects[0];assert.equal(p.id,'project-a');assert.equal(p.role,'OWNER');
 let d=await j.project(p);let item=d.checklist.items.find(x=>x.submission_type==='PRIVATE_DOCUMENT');assert.ok(item);
 const pdf1=Buffer.from('%PDF-1.7\nCUS008 first synthetic material\n%%EOF');
 const saved1=await j.saveMaterial(p,item,pdf1.toString('base64'));assert.equal(saved1.revision,item.revision+1);
 d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'PARTIAL');assert.equal(item.revision,saved1.revision);assert.equal(item.accepted_revision,null);
 const firstSave=item.versions.find(v=>v.kind==='SAVE'&&v.details?.object_id);assert.ok(firstSave);
 const dl1=j.materialDownloadUrl(p,firstSave);assert.match(dl1,/\/api\/download\/project-a\/o_[a-f0-9]{32}$/);
 const resp1=await ownerT(dl1,{method:'GET'});assert.equal(resp1.status,200);assert.deepEqual(Buffer.from(await resp1.arrayBuffer()),pdf1);assert.match(resp1.headers.get('cache-control')||'',/no-store/);assert.match(resp1.headers.get('content-disposition')||'',/attachment/);
 let forbidden='';try{await otherT(dl1,{method:'GET'}).then(async r=>{if(r.status!==200){const x=await r.json();const e=Error(x.error);e.status=r.status;throw e}})}catch(e){forbidden=e.message;assert.equal(e.status,403)}assert.equal(forbidden,'权限不足、凭据失效或请求不符合要求');

 // stale revision is a definite 409 and must not mutate state.
 let stale='';try{await ownerApi.transition(p.id,item.id,item.revision-1,'submit','')}catch(e){stale=e.message;assert.equal(e.status,409);assert.equal(e.uncertain,false)}assert.equal(stale,'版本或状态已变化，请刷新后重试');
 // stale CSRF is a definite 403 and must not mutate state.
 const badCsrf=makeApi(ownerT,()=> 'stale-csrf');let csrfErr='';try{await badCsrf.transition(p.id,item.id,item.revision,'submit','')}catch(e){csrfErr=e.message;assert.equal(e.status,403);assert.equal(e.uncertain,false)}assert.equal(csrfErr,'权限不足、凭据失效或请求不符合要求');
 d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'PARTIAL');

 // Simulate lost POST response after the real server commits submit. One call only, no blind retry.
 let submitCalls=0;
 const lostTransport=async(u,o)=>{if(u.endsWith('/api/transition')){submitCalls++;const r=await ownerT(u,o);if(r.ok)throw Error('simulated lost response after commit');return r}return ownerT(u,o)};
 const unknownApi=makeApi(lostTransport,()=>ownerCsrf);const unknownJ=new ProjectJourney(unknownApi,createIntentJournal(ss(),()=> 'U'.repeat(20)));
 let unknown=false;try{await unknownJ.submitMaterial(p,item)}catch(e){unknown=e.uncertain===true;assert.equal(e.status,0)}assert.equal(unknown,true);assert.equal(submitCalls,1);
 d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'SUBMITTED');assert.equal(item.revision,saved1.revision+1);

 // Reviewer progression is fixture-only, never exposed as SaaS customer reviewer UI.
 let r=await rawJson(reviewerT,'transition',{project:p.id,item:item.id,revision:item.revision,action:'begin_review',reason:''},reviewerCsrf);assert.equal(r.status,200);assert.equal(r.data.state,'IN_REVIEW');
 r=await rawJson(reviewerT,'transition',{project:p.id,item:item.id,revision:r.data.revision,action:'request_changes',reason:'缺少授权签字'},reviewerCsrf);assert.equal(r.status,200);assert.equal(r.data.state,'NEEDS_CORRECTION');
 d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'NEEDS_CORRECTION');assert.equal(item.accepted_revision,null);const correction=item.versions.findLast(v=>v.kind==='request_changes');assert.equal(correction.details.reason,'缺少授权签字');

 const pdf2=Buffer.from('%PDF-1.7\nCUS008 corrected signed synthetic material\n%%EOF');const saved2=await j.saveMaterial(p,item,pdf2.toString('base64'));d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'PARTIAL');assert.equal(item.revision,saved2.revision);
 const saves=item.versions.filter(v=>v.kind==='SAVE'&&v.details?.object_id);assert.equal(saves.length,2);for(const [idx,v] of saves.entries()){const rr=await ownerT(j.materialDownloadUrl(p,v),{method:'GET'});assert.equal(rr.status,200);const got=Buffer.from(await rr.arrayBuffer());assert.deepEqual(got,idx===0?pdf1:pdf2)}
 const submitted2=await j.submitMaterial(p,item);assert.equal(submitted2.state,'SUBMITTED');
 r=await rawJson(reviewerT,'transition',{project:p.id,item:item.id,revision:submitted2.revision,action:'begin_review',reason:''},reviewerCsrf);assert.equal(r.status,200);
 r=await rawJson(reviewerT,'transition',{project:p.id,item:item.id,revision:r.data.revision,action:'approve',reason:'材料完整且签字有效'},reviewerCsrf);assert.equal(r.status,200);assert.equal(r.data.state,'ACCEPTED');assert.equal(r.data.accepted_revision,r.data.revision);
 d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'ACCEPTED');assert.equal(item.accepted_revision,r.data.accepted_revision);
 const acceptedRevision=item.accepted_revision;
 const pdf3=Buffer.from('%PDF-1.7\nCUS008 later new synthetic version\n%%EOF');await j.saveMaterial(p,item,pdf3.toString('base64'));d=await j.project(p);item=d.checklist.items.find(x=>x.id===item.id);assert.equal(item.state,'PARTIAL');assert.equal(item.accepted_revision,acceptedRevision);

 // Revoke project and verify the original JS client sees the real Chinese permission boundary.
 assert.equal(await control(info.control_port,'/revoke-owner-project'),204);let revoked='';try{await ownerApi.checklist(p.id)}catch(e){revoked=e.message;assert.equal(e.status,403)}assert.equal(revoked,'权限不足、凭据失效或请求不符合要求');

 console.log(JSON.stringify({status:'PASS',scope:'CUS008_SAAS_JS_TO_E7',source_blobs:{api:'81504cda86684faa671689760dd702dde356ca48',journey:'d28bcd2be278310981404a26117c67df891774ff',submission:'fdcb1dd74d61010e320445a138c4570ba530f1e3'},save1_revision:saved1.revision,unknown_submit_calls:submitCalls,correction_reason:correction.details.reason,accepted_revision:acceptedRevision,accepted_preserved_after_new_save:item.accepted_revision,historical_downloads:saves.length,stale_revision_409:stale,csrf_403:csrfErr,other_download_403:forbidden,revoked_403:revoked,browser:'NOT_VERIFIED'}));
}finally{py.kill('SIGTERM');await Promise.race([new Promise(r=>py.once('exit',r)),sleep(1000)]);if(py.exitCode===null)py.kill('SIGKILL')}
