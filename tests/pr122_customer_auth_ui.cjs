'use strict';
// Dependency-free DOM harness: real app.js and mocked same-origin HTTP only.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.hidden=false;this.disabled=false;this.children=[];this.textContent='';this.value='';this.valid=true;this.listeners={};this.elements={};}
 append(...nodes){this.children.push(...nodes);} prepend(...nodes){this.children.unshift(...nodes);}
 replaceChildren(...nodes){this.children=nodes;this.textContent='';}
 addEventListener(type,fn){this.listeners[type]=fn;}
 reportValidity(){return this.valid;}
 reset(){for(const field of Object.values(this.elements))field.value='';}
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 const ids=[...fs.readFileSync('deploy/pr122-customer-center/ui/index.html','utf8').matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
 const dom=Object.fromEntries(ids.map(id=>[id,new Element()]));
 for(const id of ['login','verification','reset','message','bind','invite','revoke','accept'])for(const field of ['email','password','token','body','subject','user_id','invitation'])dom[id].elements[field]=new Element();
 const requests=[],responses=[],storage=new Map([['xj_csrf','old-csrf']]),events={};let reloads=0;
 const context=vm.createContext({crypto:require('node:crypto').webcrypto,document:{getElementById:id=>dom[id],createElement:()=>new Element()},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},window:{addEventListener:(k,fn)=>events[k]=fn,location:{reload:()=>reloads++}},FormData:class{constructor(form){this.form=form;}*[Symbol.iterator](){for(const [name,input] of Object.entries(this.form.elements))if(['email','password'].includes(name))yield[name,input.value];}},fetch:async(url,options)=>{requests.push({url,options});const response=responses.shift();if(response instanceof Error)throw response;if(typeof response==='function')return response();return {ok:response.status<400,status:response.status,json:async()=>response.body};}});
 const reply=(status,body)=>responses.push({status,body});
 const me={projects:[{id:'p1',title:'Project',role:'OWNER'}],channels:{web_ai:{state:'PENDING_CONNECTION'},telegram:{state:'PENDING_CONNECTION'},feishu:{state:'PENDING_CONNECTION'}}};
 reply(200,me);vm.runInContext(fs.readFileSync('deploy/pr122-customer-center/ui/app.js','utf8'),context);
 return {dom,requests,responses,storage,events,context,reply,me,reloads:()=>reloads,run:code=>vm.runInContext(code,context),click:id=>dom[id].listeners.click()};
}
(async()=>{
 const f=fixture();await tick();assert.equal(f.dom.workspace.hidden,false);
 f.run("project='old-project';role='OWNER'");f.dom.materials.append(new Element());f.dom['project-title'].textContent='Private';f.dom.message.elements.body.value='Private draft';
 f.reply(403,{error:'expired'});await f.run('start()');assert.equal(f.run('project'),'');assert.equal(f.run('role'),'');assert.equal(f.dom.project.hidden,true);assert.equal(f.dom.materials.children.length,0);assert.equal(f.dom['project-title'].textContent,'');assert.equal(f.dom.message.elements.body.value,'');assert.equal(f.storage.has('xj_csrf'),false);assert.equal(f.dom.workspace.hidden,true);
 f.run("csrf='retained'");f.storage.set('xj_csrf','retained');f.reply(503,{error:'maintenance'});await f.run('start()');assert.match(f.dom.notice.textContent,/暂时无法确认登录状态/);assert.equal(f.storage.get('xj_csrf'),'retained');assert.equal(f.dom.logout.hidden,false);
 f.responses.push(new Error('network failed'));await f.run('start()');assert.match(f.dom.notice.textContent,/network failed/);assert.equal(f.reloads(),0);
 f.reply(200,f.me);await f.run('start()');assert.equal(f.dom.workspace.hidden,false);assert.equal(f.dom.projects.children.length,1);
 f.dom.login.valid=false;let before=f.requests.length;await f.click('register');assert.equal(f.requests.length,before);
 f.dom.login.valid=true;f.dom.login.elements.email.valid=false;await f.click('reset-request');assert.equal(f.requests.length,before);
 f.dom.login.elements.email.valid=true;f.dom.login.elements.password.valid=false;f.reply(200,{status:'CHECK_VERIFICATION_CHANNEL'});await f.click('reset-request');assert.equal(f.requests.length,before+1);assert.deepEqual(JSON.parse(f.requests.at(-1).options.body),{email:''});
 let finish;f.responses.push(()=>new Promise(resolve=>finish=()=>resolve({ok:true,status:200,json:async()=>({status:'CHECK_VERIFICATION_CHANNEL'})})));const pending=f.click('register');await tick();assert.equal(f.dom.register.disabled,true);before=f.requests.length;await f.click('register');assert.equal(f.requests.length,before);finish();await pending;assert.equal(f.dom.register.disabled,false);assert.equal(f.dom.login.elements.password.value,'');
 f.responses.push(new Error('offline'));await f.click('logout');assert.equal(f.reloads(),0);assert.equal(f.storage.get('xj_csrf'),'retained');assert.equal(f.dom.logout.disabled,false);
 f.dom.materials.append(new Element());f.reply(200,{logged_out:true});await f.click('logout');assert.equal(f.reloads(),1);assert.equal(f.dom.materials.children.length,0);assert.equal(f.storage.has('xj_csrf'),false);
 f.dom.materials.append(new Element());f.reply(403,{error:'expired'});f.events.pageshow({persisted:true});assert.equal(f.dom.materials.children.length,0);await tick();assert.equal(f.dom.workspace.hidden,true);

 // Delayed private reads cannot redraw a logged-out or different project's DOM.
 let deliver;f.run("project='old-project';role='OWNER'");
 f.responses.push(()=>new Promise(resolve=>deliver=()=>resolve({ok:true,status:200,json:async()=>({overall:'ACCEPTED',requirements_revision:99,items:[]})})));
 const oldRefresh=f.run('refresh()');await tick();f.run('clearSession()');deliver();await oldRefresh;
 assert.equal(f.dom.overall.textContent,'');assert.equal(f.dom.materials.children.length,0);
 f.responses.push(()=>new Promise(resolve=>deliver=()=>resolve({ok:true,status:200,json:async()=>({overall:'ACCEPTED',requirements_revision:99,items:[]})})));
 const projectA=f.run("openProject({id:'A',title:'Private A',role:'VIEWER'})");await tick();
 f.reply(200,{overall:'NOT_STARTED',requirements_revision:2,items:[]});f.reply(200,{messages:[]});f.reply(200,{links:[]});f.reply(200,{cases:[]});
 await f.run("openProject({id:'B',title:'Project B',role:'VIEWER'})");deliver();await projectA;
 assert.equal(f.dom['project-title'].textContent,'Project B');assert.match(f.dom.overall.textContent,/版本 2$/);assert.equal(f.run('project'),'B');
 const exported=f.dom.messages.children.find(x=>x.download==='project-message-evidence.json');assert.ok(exported);assert.equal(exported.href,'/customer/center/api/evidence/B');
 f.run("csrf='still-valid'");f.storage.set('xj_csrf','still-valid');f.dom.materials.append(new Element());f.reply(403,{error:'project revoked'});await f.run('refresh()');assert.equal(f.dom.project.hidden,true);assert.equal(f.dom.materials.children.length,0);assert.equal(f.storage.get('xj_csrf'),'still-valid');assert.equal(f.dom.messages.children.length,0);
 // Privacy UI uses readable protected notices, scoped requests and stable retry keys.
 f.dom['privacy-tools']=new Element();f.run("project='B';role='OWNER'");
 const unknownPrivacy={policy:{},receipts:[],processing:[]};f.reply(200,unknownPrivacy);await f.run('openPrivacy()');
 assert.ok(!f.dom['privacy-tools'].children.some(x=>x.textContent==='记录已阅此版本'));
 const policy={notice_text:'Synthetic readable notice <not markup>',notice_ref:'notice-v1',notice_version:'v1',notice_sha256:'a'.repeat(64),consent_version:'v1',consent_scope:'project',retention_policy:null};
 const privacyData={policy,receipts:[],processing:[]};f.reply(200,privacyData);await f.run('openPrivacy()');
 assert.ok(f.dom['privacy-tools'].children.some(x=>x.textContent===policy.notice_text));
 assert.equal(f.requests.filter(x=>x.url.endsWith('privacy_acknowledge')).length,0);
 const ack=f.dom['privacy-tools'].children.find(x=>x.textContent==='记录已阅此版本');assert.ok(ack);
 f.responses.push(new Error('unknown transport outcome'));await ack.onclick();
 f.reply(200,{status:'RECORDED_NOT_LEGAL_ACCEPTANCE'});f.reply(200,privacyData);await ack.onclick();
 const ackRequests=f.requests.filter(x=>x.url.endsWith('privacy_acknowledge')).map(x=>JSON.parse(x.options.body));
 assert.equal(ackRequests.length,2);assert.equal(ackRequests[0].idempotency_key,ackRequests[1].idempotency_key);assert.equal(ackRequests[0].project,'B');
 assert.deepEqual(Object.keys(ackRequests[0]).sort(),['decision','idempotency_key','notice_sha256','policy_ref','project']);
 const requestForm=f.dom['privacy-tools'].children.find(x=>typeof x.onsubmit==='function');assert.ok(requestForm);
 requestForm.children[0].value='DELETION';requestForm.children[1].children[0].value='Please review removal of my synthetic note.';
 f.reply(200,{status:'RECEIVED',execution_enabled:false});f.reply(200,privacyData);await requestForm.onsubmit({preventDefault(){}});
 const privacyRequest=JSON.parse(f.requests.findLast(x=>x.url.endsWith('privacy_request')).options.body);
 assert.equal(privacyRequest.kind,'DELETION');assert.equal(privacyRequest.project,'B');assert.equal(privacyRequest.request_id,null);assert.equal(privacyRequest.expected_revision,0);
 assert.ok(!('actor_id' in privacyRequest)&&!('status' in privacyRequest));
 // A pending request blocks duplicate submission and retries the same key after network failure.
 const retryForm=f.dom['privacy-tools'].children.find(x=>typeof x.onsubmit==='function');
 retryForm.children[1].children[0].value='Synthetic query';let rejectRequest;
 f.responses.push(()=>new Promise((resolve,reject)=>rejectRequest=reject));
 const pendingRequest=retryForm.onsubmit({preventDefault(){}});await tick();before=f.requests.length;
 await retryForm.onsubmit({preventDefault(){}});assert.equal(f.requests.length,before);
 rejectRequest(new Error('unknown request outcome'));await pendingRequest;
 f.reply(200,{status:'RECEIVED'});f.reply(200,privacyData);await retryForm.onsubmit({preventDefault(){}});
 const retryRequests=f.requests.filter(x=>x.url.endsWith('privacy_request')).slice(-2).map(x=>JSON.parse(x.options.body));
 assert.equal(retryRequests[0].idempotency_key,retryRequests[1].idempotency_key);
 // A delayed privacy response must not restore private content after logout or switching project.
 for(const action of ["clearSession()","clearProject();project='C';role='OWNER'"]){
  f.run("project='B';role='OWNER'");
  f.responses.push(()=>new Promise(resolve=>deliver=()=>resolve({ok:true,status:200,json:async()=>privacyData})));
  const delayedPrivacy=f.run('openPrivacy()');await tick();f.run(action);deliver();await delayedPrivacy;
  assert.equal(f.dom['privacy-tools'].children.length,0);
 }
 f.run("project='B';role='OWNER'");f.reply(200,privacyData);await f.run('openPrivacy()');
 f.reply(403,{error:'revoked'});await f.run('openPrivacy()');
 assert.equal(f.dom['privacy-tools'].children.length,0);assert.equal(f.dom.project.hidden,true);
 f.run('clearSession()');assert.equal(f.dom['privacy-tools'].children.length,0);
 // A rejected historical-provenance read must clear old DOM and export links.
 f.reply(200,{overall:'NOT_STARTED',requirements_revision:3,items:[]});f.reply(403,{error:'historical provenance unavailable'});
 await f.run("openProject({id:'orphan-project',title:'New Project',role:'OWNER'})");
 assert.equal(f.dom.project.hidden,true);assert.equal(f.dom.messages.children.length,0);assert.equal(f.dom.materials.children.length,0);
 assert.ok(!f.dom.messages.textContent.includes('unknown-origin private history'));
 console.log('PASS: session expiry, private DOM/draft clearing, 503/network distinction, recovery, register/reset validation, duplicate click guard, logout failure/success, bfcache revalidation, delayed private response isolation, project switching/revocation, scoped evidence download clearing, privacy notice/no-autoack, stable request retries, stale privacy response isolation and revocation');
})().catch(error=>{console.error(error);process.exitCode=1;});

