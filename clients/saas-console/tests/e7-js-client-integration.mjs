import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFile, readdir, stat} from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {makeApi} from '../src/api.js';
import {ProjectJourney} from '../src/journey.js';
import {createIntentJournal} from '../src/submission.js';

const EXPECTED_FRONTEND = {
  api: '8383bee41d2abec68ca580469388e1399cbdab03',
  journey: 'adf27901abf2fe1311d6742367c4fdb1db4a5a7c',
  submission: 'fdcb1dd74d61010e320445a138c4570ba530f1e3',
};
const EXPECTED_BACKEND_COMMIT='e7f75975c4ab4eedba68306212a2bac6c067a1c3';
const EXPECTED_BACKEND_TREE='d001cfd9855ed3a7758f6286db5cae7d45cce403';
const HOST='wenwenwenyiyiyi.work';
const ORIGIN='https://wenwenwenyiyiyi.work';
const COOKIE='__Host-xj_customer';
const here=path.dirname(fileURLToPath(import.meta.url));
const srcRoot=path.resolve(here,'..','src');
const artifactRoot=path.resolve(process.env.XJ_PR122_E7_ROOT||'');
if(!process.env.XJ_PR122_E7_ROOT) throw new Error('HOLD_MISSING_XJ_PR122_E7_ROOT');

function gitBlob(raw){return createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${raw.length}\0`),raw])).digest('hex')}
for(const [name,sha] of Object.entries(EXPECTED_FRONTEND)){
  const raw=await readFile(path.join(srcRoot,`${name}.js`));
  assert.equal(gitBlob(raw),sha,`frontend blob mismatch ${name}`);
}
const manifest=JSON.parse(await readFile(path.join(artifactRoot,'CUSTOMER_MANIFEST.json'),'utf8'));
assert.equal(manifest.source_commit,EXPECTED_BACKEND_COMMIT);
assert.equal(manifest.source_tree,EXPECTED_BACKEND_TREE);
assert.equal(manifest.files.length,102);
for(const rec of manifest.files){const raw=await readFile(path.join(artifactRoot,rec.path));assert.equal(createHash('sha256').update(raw).digest('hex'),rec.sha256,rec.path)}

const py=spawn(process.env.PYTHON||'python3',['-B','-m','tests.pr122_customer_browser_server'],{cwd:artifactRoot,stdio:['ignore','pipe','pipe']});
let stderr='';py.stderr.setEncoding('utf8');py.stderr.on('data',x=>stderr+=x);
const firstLine=await new Promise((resolve,reject)=>{let buf='';py.stdout.setEncoding('utf8');const on=x=>{buf+=x;const i=buf.indexOf('\n');if(i>=0){py.stdout.off('data',on);resolve(buf.slice(0,i))}};py.stdout.on('data',on);py.once('exit',code=>reject(new Error(`fixture exited ${code}: ${stderr}`)))});
const info=JSON.parse(firstLine);assert.equal(info.scope,'ISOLATED_FIXTURE_NOT_PRODUCTION');assert.equal(info.fixture_signer,'TEST_ONLY');

function sessionTransport(){
  let cookie='', lastSetCookie='';
  const transport=async(url,opts={})=>new Promise((resolve,reject)=>{
    const headers={Host:HOST,...(opts.headers||{})};
    if(opts.body!==undefined){headers.Origin=ORIGIN;headers['Content-Type']=headers['Content-Type']||'application/json';headers['Content-Length']=Buffer.byteLength(opts.body)}
    if(cookie)headers.Cookie=cookie;
    const req=http.request({host:'127.0.0.1',port:info.port,path:url,method:opts.method||'GET',headers},res=>{
      const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>{
        const body=Buffer.concat(chunks);const sc=res.headers['set-cookie']?.[0];
        if(sc){lastSetCookie=sc;const pair=sc.split(';',1)[0];if(pair.startsWith(COOKIE+'=')){cookie=pair.endsWith('=')?'':pair}}
        resolve(new Response(body,{status:res.statusCode,headers:res.headers}));
      })
    });req.on('error',reject);if(opts.body!==undefined)req.write(opts.body);req.end();
  });
  transport.cookie=()=>cookie;transport.lastSetCookie=()=>lastSetCookie;
  return transport;
}
function storage(){const m=new Map;return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}}
async function rawJson(transport,url,body,csrf){const r=await transport('/customer/center/'+url,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});let d={};try{d=await r.json()}catch{}return{status:r.status,data:d}}
async function control(p){return new Promise((resolve,reject)=>{const q=http.request({host:'127.0.0.1',port:info.control_port,path:p,method:'POST'},r=>{r.resume();r.on('end',()=>resolve(r.statusCode))});q.on('error',reject);q.end()})}

const ownerT=sessionTransport(),reviewerT=sessionTransport(),otherT=sessionTransport();
let ownerCsrf='',reviewerCsrf='',otherCsrf='';
const ownerApi=makeApi(ownerT,()=>ownerCsrf),reviewerApi=makeApi(reviewerT,()=>reviewerCsrf),otherApi=makeApi(otherT,()=>otherCsrf);
let login=await ownerApi.login('owner@example.com','correct-password-123');ownerCsrf=login.csrf;
login=await reviewerApi.login('reviewer@example.com','correct-password-123');reviewerCsrf=login.csrf;
login=await otherApi.login('other@example.com','correct-password-123');otherCsrf=login.csrf;
assert.match(ownerT.lastSetCookie(),/Secure/);assert.match(ownerT.lastSetCookie(),/HttpOnly/);assert.match(ownerT.lastSetCookie(),/SameSite=Strict/);

const journal=createIntentJournal(storage(),()=> 'K'.repeat(20));
const j=new ProjectJourney(ownerApi,journal);
const me=await j.projects();assert.deepEqual(me.projects.map(x=>x.id),['project-a']);const p=me.projects[0];
let project=await j.project(p);
const item=project.checklist.items.find(x=>x.submission_type==='PRIVATE_DOCUMENT');assert.ok(item);
const pdf=Buffer.from('%PDF-1.7\nsynthetic SaaS JS client material\n%%EOF');
const saved=await j.saveMaterial(p,item,pdf.toString('base64'));assert.equal(saved.revision,item.revision+1);
project=await j.project(p);assert.equal(project.checklist.items.find(x=>x.id===item.id).revision,saved.revision);

let denied='';try{await ownerApi.checklist('project-b')}catch(e){denied=e.message;assert.equal(e.status,403)}assert.equal(denied,'权限不足、凭据失效或请求不符合要求');

const page=project.previews.pages.find(x=>x.path==='/preview/consumer/')||project.previews.pages[0];assert.ok(page);const v1=page.sha256;assert.ok(page.url.endsWith('/'+v1));
const html1=await ownerT(page.url,{method:'GET'});assert.equal(html1.status,200);const body1=await html1.text();assert.match(body1,/Welcome to Xuanjun/);assert.match(body1,/data-project-feedback=/);assert.ok(body1.length>100);

await j.feedbackContext(p,page);const created=await j.submitLegacy(p,page,'将「Welcome」改为「Welcomes」');const caseId=created.id;
let cases=await ownerApi.changes('project-a');assert.ok(cases.cases.some(x=>x.id===caseId));

let rcases=await reviewerApi.changes('project-a');const ce=rcases.cases.find(x=>x.id===caseId);const rev=ce.events.at(-1).seq;
let r=await rawJson(reviewerT,'api/change_assess',{project:'project-a',case:caseId,revision:rev,category:'IN_SCOPE_SMALL',minutes:1,lines:[],evidence:[],explanation:'单处已授权展示文案小改'},reviewerCsrf);assert.equal(r.status,200);assert.equal(r.data.state,'FREE_APPROVED');
r=await rawJson(reviewerT,'api/change_small_edit',{project:'project-a',case:caseId},reviewerCsrf);assert.equal(r.status,200);const job=r.data.id;
let state;for(let n=0;n<80;n++){r=await rawJson(reviewerT,'api/edit_candidate/project-a/'+job,undefined,reviewerCsrf);assert.equal(r.status,200);state=r.data;if(['CANDIDATE_READY','HOLD_UNKNOWN'].includes(state.state))break;await new Promise(x=>setTimeout(x,50))}assert.equal(state.state,'CANDIDATE_READY');
assert.equal(await control('/publish-ready'),204);

const fresh=await j.currentPage(p,page.path);const v2=fresh.sha256;assert.notEqual(v2,v1);assert.ok(fresh.url.endsWith('/'+v2));
const html2=await ownerT(fresh.url,{method:'GET'});assert.equal(html2.status,200);const body2=await html2.text();assert.match(body2,/Welcomes to Xuanjun/);assert.doesNotMatch(body2,/>Welcome to Xuanjun</);assert.match(body2,/data-project-feedback=/);
const updates=(await j.updates(p,fresh)).updates;const u=updates.find(x=>x.case===caseId);assert.ok(u);assert.equal(u.before_sha256,v1);assert.equal(u.after_sha256,v2);assert.equal(u.state,'AWAIT_RETEST');
const retest=await j.retest(p,fresh,u,'ACCEPT','同版 JS 客户端隔离复验通过');assert.equal(retest.state,'RETEST_ACCEPTED');assert.equal(retest.automatic_charge,false);
cases=await ownerApi.changes('project-a');assert.equal(cases.cases.find(x=>x.id===caseId).events.at(-1).kind,'RETEST');

await ownerApi.logout();let expired='';try{await ownerApi.me()}catch(e){expired=e.message;assert.equal(e.status,403)}assert.equal(expired,'权限不足、凭据失效或请求不符合要求');

const out={status:'PASS',scope:'SAAS_JS_CLIENT_TO_E7_LOOPBACK',frontend:EXPECTED_FRONTEND,backend:{commit:EXPECTED_BACKEND_COMMIT,tree:EXPECTED_BACKEND_TREE,manifest_files:102},transport:{host:HOST,origin:ORIGIN,secure_cookie:true,csrf:true},save_revision:saved.revision,v1,v2,preview_v1_body_sha256:createHash('sha256').update(body1).digest('hex'),preview_v2_body_sha256:createHash('sha256').update(body2).digest('hex'),preview_v1_has_text:body1.includes('Welcome to Xuanjun'),preview_v2_has_text:body2.includes('Welcomes to Xuanjun'),cross_project_403:denied,post_logout_403:expired,retest:retest.state,browser:'NOT_VERIFIED'};
console.log(JSON.stringify(out));
py.kill('SIGTERM');
await new Promise(resolve=>{const t=setTimeout(resolve,1000);py.once('exit',()=>{clearTimeout(t);resolve()})});
