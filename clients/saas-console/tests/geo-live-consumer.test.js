// Program-level DOM/stdio integration only. NOT a browser, socket or live service.
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {makeGeoHttpService} from '../src/geo-v4-http-service.js';
const root=fileURLToPath(new URL('../../../',import.meta.url));
let serial=0;
async function fixture(){
 const child=spawn('python3',['-B','-m','tests.pr122_customer_geo_page_fixture'],{cwd:root,env:{PATH:process.env.PATH,PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
 const lines=createInterface({input:child.stdout}),queue=[],waiters=[];let failure=null,stderr='';
 child.stderr.on('data',b=>stderr+=b);lines.on('line',line=>{const value=JSON.parse(line);if(waiters.length)waiters.shift().resolve(value);else queue.push(value)});
 const closed=new Promise(resolve=>child.on('close',()=>{failure=new Error('Synthetic fixture closed: '+stderr);for(const w of waiters.splice(0))w.reject(failure);resolve()}));
 const read=()=>queue.length?Promise.resolve(queue.shift()):failure?Promise.reject(failure):new Promise((resolve,reject)=>waiters.push({resolve,reject}));
 const hello=await read();assert.equal(hello.ready,true);
 return {hello,send:async value=>{child.stdin.write(JSON.stringify(value)+String.fromCharCode(10));return read()},close:async()=>{child.stdin.end();await closed;lines.close()}};
}
class Element{
 constructor(){this.textContent='';this.value='';this.style={};this.children={}}
 querySelector(key){return this.children[key]||null}querySelectorAll(){return []}
 setAttribute(){}removeAttribute(){}replaceChildren(){}
}
function dom(){
 let finish;const complete=new Promise(resolve=>finish=resolve);const map=new Map();
 for(const key of ['.livebadge','#brandname','#brandurl','.demobar span','#geo-runtime-guard'])map.set(key,new Element());
 const review=new Element();review.children['.mini']=new Element();map.get('#geo-runtime-guard').remove=()=>finish();
 return {complete,map,review,body:new Element(),querySelector:key=>map.get(key)||null,querySelectorAll:key=>key==='.review'?[review]:[],getElementById:id=>map.get('#'+id)||null};
}
async function page(f,{csrf=true,project='project-a',hook=false}={}){
 const doc=dom(),requests=[],toasts=[];const win={location:{search:'?project='+project},toast:value=>toasts.push(value),render(){}};
 const previous={};for(const key of ['window','document','fetch','sessionStorage','__XJ_GEO_CUSTOMER_SERVICE__'])previous[key]=globalThis[key];
 globalThis.window=win;globalThis.document=doc;globalThis.sessionStorage={getItem:()=>csrf?f.hello.csrf:''};
 globalThis.fetch=async(url,options)=>{requests.push({url,method:options.method,body:options.body?JSON.parse(options.body):null});const r=await f.send({url,options});return {ok:r.status>=200&&r.status<300,status:r.status,json:async()=>r.body}};
 try{
  const html=readFileSync(new URL('../geo-v4/live.html',import.meta.url),'utf8');assert.ok(html.includes('<script type="module" src="../src/geo-v4-runtime.js"></script>'));
  let hookCalls=0;
  if(hook){const service=makeGeoHttpService();const original=service.snapshot;service.snapshot=async body=>{hookCalls++;return original(body)};globalThis.__XJ_GEO_CUSTOMER_SERVICE__=service}else delete globalThis.__XJ_GEO_CUSTOMER_SERVICE__;
  win.hookCalls=()=>hookCalls;
  await import(new URL('../src/geo-v4-runtime.js?actual-page-entry='+ ++serial,import.meta.url));
  await doc.complete;
  return {doc,win,requests,toasts,restore:()=>{for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value}}};
 }catch(e){for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value}throw e}
}
test('live entry auto-reads canonical version, safely saves same project and reads actual result',{timeout:15000},async()=>{
 const f=await fixture();let p;
 try{
  p=await page(f);assert.equal(p.doc.map.get('.livebadge').textContent,'真实服务');assert.match(p.doc.review.querySelector('.mini').textContent,/第 1 版.*已批准/);
  assert.deepEqual(p.requests.map(r=>r.url),['/customer/center/api/me','/customer/center/api/geo/snapshot']);
  const scope=p.requests[1].body;assert.deepEqual(scope,f.hello.scope);
  const before=p.requests.length;await p.win.approvalConfirm();assert.equal(p.requests.length,before); // unavailable publication never sent
  p.doc.map.get('#brandname').value='隔离合成品牌';p.doc.map.get('#brandurl').value='https://example.invalid';await p.win.saveSetup();
  const command=p.requests.find(r=>r.url.endsWith('/command'));assert.equal(command.body.tenant_id,scope.tenant_id);assert.equal(command.body.project_id,scope.project_id);assert.ok(command.body.idempotency_key);
  assert.equal(p.doc.map.get('#brandname').value,'隔离合成品牌');assert.deepEqual(await f.send({control:'stats'}),{brand_revision:1,commands:1});
 }finally{p?.restore();await f.close()}
});
test('wrong project never calls snapshot or command',{timeout:15000},async()=>{
 const f=await fixture();let p;try{p=await page(f,{project:'foreign-project'});await p.win.saveSetup();assert.deepEqual(p.requests.map(r=>r.url),['/customer/center/api/me']);assert.equal((await f.send({control:'stats'})).commands,0)}finally{p?.restore();await f.close()}
});
test('missing CSRF never promotes fixture source or sends a command',{timeout:15000},async()=>{
 const f=await fixture();let p;try{p=await page(f,{csrf:false});assert.equal(p.doc.map.get('.livebadge').textContent,'真实服务未核实');assert.ok(p.requests.some(r=>r.url.endsWith('/snapshot')));await p.win.saveSetup();assert.equal((await f.send({control:'stats'})).commands,0)}finally{p?.restore();await f.close()}
});
test('entitlement revoked after load refreshes denied state and blocks subsequent command',{timeout:15000},async()=>{
 const f=await fixture();let p;try{p=await page(f);await f.send({control:'disable-entitlement'});p.doc.map.get('#brandname').value='not-saved';p.doc.map.get('#brandurl').value='';await p.win.saveSetup();assert.equal(p.doc.map.get('.livebadge').textContent,'真实服务未核实');const count=p.requests.filter(r=>r.url.endsWith('/command')).length;await p.win.saveSetup();assert.equal(p.requests.filter(r=>r.url.endsWith('/command')).length,count);assert.equal((await f.send({control:'stats'})).brand_revision,0)}finally{p?.restore();await f.close()}
});

test('existing explicit service hook is respected instead of replaced',{timeout:15000},async()=>{
 const f=await fixture();let p;try{p=await page(f,{hook:true});assert.equal(p.win.hookCalls(),1);assert.equal(p.doc.map.get('.livebadge').textContent,'真实服务');assert.match(p.doc.review.querySelector('.mini').textContent,/第 1 版/)}finally{p?.restore();await f.close()}
});
