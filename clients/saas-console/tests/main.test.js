import test from'node:test';import assert from'node:assert/strict';import{createConsoleApp}from'../src/main.js';
class El{constructor(tag='div'){this.tagName=tag;this.textContent='';this.hidden=false;this.children=[];this.elements={};this.disabled=false;this.value=''}append(...x){this.children.push(...x)}replaceChildren(...x){this.children=[...x]}set className(x){this._class=x}get className(){return this._class||''}}
function doc(){const ids=['status','identity','login','logout','identity-note','projects','detail','title','meta','requirements','previews','changes','qa'],m=new Map(ids.map(x=>[x,new El]));m.get('login').elements={email:{value:'e@x.com'},password:{value:'password1234'}};return{getElementById:id=>m.get(id),createElement:t=>new El(t),m}}
const ss=()=>{const m=new Map;return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};
const v='a'.repeat(64),v2='b'.repeat(64),key='c'.repeat(64);
const pdata=(p,pages=[])=>({checklist:{requirements_revision:1,overall:'PARTIAL',items:[]},previews:{pages},changes:{cases:[]},messages:{messages:[]}});
function deferred(){let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j});return{promise,resolve,reject}}
function apiBase(extra={}){return{me:async()=>({projects:[]}),checklist:async()=>pdata().checklist,previews:async()=>({pages:[]}),changes:async()=>({cases:[]}),messages:async()=>({messages:[]}),...extra}}
function find(root,pred){if(pred(root))return root;for(const c of root.children||[]){const x=find(c,pred);if(x)return x}return null}

test('start with valid cookie but no csrf keeps login visible for write recovery',async()=>{const d=doc(),s=ss(),api=apiBase({me:async()=>({projects:[{id:'A',title:'A',role:'OWNER'}]})});const app=createConsoleApp({document:d,storage:ss(),session:s,api});await app.start();assert.equal(d.m.get('login').hidden,false);assert.equal(d.m.get('logout').hidden,false);assert.match(d.m.get('identity-note').textContent,/没有CSRF/)});

test('project switch clears old DOM and stale rejected load cannot clear new project',async()=>{const d=doc(),s=ss(),wait={};s.setItem('xj_csrf','c');const api=apiBase({checklist:async id=>new Promise((res,rej)=>wait[id]={res,rej})});const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'},b={id:'B',title:'B',role:'OWNER'};const pa=app.open(a),pb=app.open(b);assert.equal(d.m.get('title').textContent,'B');wait.B.res({requirements_revision:1,overall:'PARTIAL',items:[]});await pb;wait.A.rej(Object.assign(Error('denied'),{status:403}));await pa;assert.equal(app.current.id,'B');assert.equal(d.m.get('title').textContent,'B');assert.equal(d.m.get('detail').hidden,false)});

test('late Q&A success from A cannot reopen A after switch to B',async()=>{const d=doc(),s=ss(),q=deferred();s.setItem('xj_csrf','c');const api=apiBase({message:async()=>q.promise});const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'},b={id:'B',title:'B',role:'OWNER'};await app.open(a);const form=find(d.m.get('qa'),x=>x.tagName==='form'),ta=find(form,x=>x.tagName==='textarea');ta.value='A question';const pending=form.onsubmit({preventDefault(){}});await app.open(b);q.resolve({id:'m1',status:'ARCHIVED'});await pending;assert.equal(app.current.id,'B');assert.equal(d.m.get('title').textContent,'B')});

test('late Q&A 403 from A cannot globally clear B',async()=>{const d=doc(),s=ss(),q=deferred();s.setItem('xj_csrf','c');const api=apiBase({message:async()=>q.promise,me:async()=>({projects:[{id:'B',title:'B',role:'OWNER'}]})});const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'},b={id:'B',title:'B',role:'OWNER'};await app.open(a);const form=find(d.m.get('qa'),x=>x.tagName==='form'),ta=find(form,x=>x.tagName==='textarea');ta.value='A question';const pending=form.onsubmit({preventDefault(){}});await app.open(b);q.reject(Object.assign(Error('forbidden'),{status:403}));await pending;assert.equal(app.current.id,'B');assert.equal(d.m.get('detail').hidden,false)});

test('late feedback success from A cannot reopen A after switch to B',async()=>{const d=doc(),s=ss(),post=deferred();s.setItem('xj_csrf','c');const page={path:'/index.html',sha256:v,url:'/customer/center/preview/A/'+key+'/'+v};const api=apiBase({previews:async id=>({pages:id==='A'?[page]:[]}),context:async()=>({}),submit:async()=>post.promise});const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'},b={id:'B',title:'B',role:'OWNER'};await app.open(a);const fb=find(d.m.get('previews'),x=>x.tagName==='button'&&x.textContent==='对此版本反馈');await fb.onclick();const form=find(d.m.get('previews'),x=>x.tagName==='form'),ta=find(form,x=>x.tagName==='textarea');ta.value='fix';const pending=form.onsubmit({preventDefault(){}});await app.open(b);post.resolve({id:'case-a',event_id:'event-a'});await pending;assert.equal(app.current.id,'B');assert.equal(d.m.get('title').textContent,'B')});

test('late retest 403 from A cannot clear B',async()=>{const d=doc(),s=ss(),retest=deferred();s.setItem('xj_csrf','c');let previewCalls=0;const old={path:'/index.html',sha256:v,url:'/customer/center/preview/A/'+key+'/'+v},fresh={path:'/index.html',sha256:v2,url:'/customer/center/preview/A/'+key+'/'+v2};const api=apiBase({previews:async id=>id==='A'?{pages:[previewCalls++?fresh:old]}:{pages:[]},updates:async()=>({updates:[{case:'c1',revision:2,before_sha256:v,after_sha256:v2,delivery_sha256:'d'.repeat(64),state:'AWAIT_RETEST'}]}),retest:async()=>retest.promise});const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'},b={id:'B',title:'B',role:'OWNER'};await app.open(a);const upd=find(d.m.get('previews'),x=>x.tagName==='button'&&x.textContent==='刷新并查询新版交付');await upd.onclick();const accept=find(d.m.get('previews'),x=>x.tagName==='button'&&x.textContent==='确认本次修改复验');const pending=accept.onclick();await app.open(b);retest.reject(Object.assign(Error('forbidden'),{status:403}));await pending;assert.equal(app.current.id,'B');assert.equal(d.m.get('detail').hidden,false)});

test('403 distinguishes invalid session from project denial via read-only me',async()=>{const d=doc(),s=ss();s.setItem('xj_csrf','c');let invalid=false;const api=apiBase({me:async()=>{if(invalid)throw Object.assign(Error('auth'),{status:403});return{projects:[{id:'B',title:'B',role:'OWNER'}]}}});const app=createConsoleApp({document:d,storage:ss(),session:s,api});await app.handleError(Object.assign(Error('denied'),{status:403}));assert.equal(s.getItem('xj_csrf'),'c');assert.equal(d.m.get('login').hidden,true);invalid=true;await app.handleError(Object.assign(Error('auth'),{status:403}));assert.equal(s.getItem('xj_csrf'),null);assert.equal(d.m.get('login').hidden,false)});

test('logout transport unknown never claims successful logout',async()=>{const d=doc(),s=ss();s.setItem('xj_csrf','c');const api=apiBase({logout:async()=>{const e=Error('lost');e.uncertain=true;throw e}});const app=createConsoleApp({document:d,storage:ss(),session:s,api});await app.logout();assert.equal(s.getItem('xj_csrf'),null);assert.match(d.m.get('status').textContent,/结果未知/);assert.doesNotMatch(d.m.get('status').textContent,/^已退出/) });

test('A project 403 waits for me probe; switching to B before probe resolves prevents A from clearing B',async()=>{
 const d=doc(),s=ss(),probe=deferred();s.setItem('xj_csrf','c');
 const api=apiBase({checklist:async id=>{if(id==='A')throw Object.assign(Error('denied'),{status:403});return pdata().checklist},me:async()=>probe.promise});
 const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'},b={id:'B',title:'B',role:'OWNER'};
 const pa=app.open(a);await new Promise(r=>setTimeout(r,0));await app.open(b);assert.equal(app.current.id,'B');
 probe.resolve({projects:[b]});await pa;
 assert.equal(app.current.id,'B');assert.equal(d.m.get('title').textContent,'B');assert.equal(d.m.get('detail').hidden,false);assert.equal(s.getItem('xj_csrf'),'c');
});

test('active write 403 with valid cookie clears stale csrf and exposes explicit re-login',async()=>{
 const d=doc(),s=ss();s.setItem('xj_csrf','stale');
 const a={id:'A',title:'A',role:'OWNER'};
 const api=apiBase({me:async()=>({projects:[a]})});const app=createConsoleApp({document:d,storage:ss(),session:s,api});await app.open(a);
 const c={generation:app.generation,project:'A',write:true};await app.handleError(Object.assign(Error('csrf rejected'),{status:403}),c);
 assert.equal(s.getItem('xj_csrf'),null);assert.equal(d.m.get('login').hidden,false);assert.equal(d.m.get('logout').hidden,false);assert.match(d.m.get('identity-note').textContent,/CSRF已清除/);
});

test('same delivery shares one retest latch across ACCEPT and FEEDBACK',async()=>{
 const d=doc(),s=ss(),pending=deferred();s.setItem('xj_csrf','c');let previewCalls=0,retestCalls=0;
 const old={path:'/index.html',sha256:v,url:'/customer/center/preview/A/'+key+'/'+v},fresh={path:'/index.html',sha256:v2,url:'/customer/center/preview/A/'+key+'/'+v2};
 const api=apiBase({previews:async()=>({pages:[previewCalls++?fresh:old]}),updates:async()=>({updates:[{case:'c1',revision:2,before_sha256:v,after_sha256:v2,delivery_sha256:'d'.repeat(64),state:'AWAIT_RETEST'}]}),retest:async()=>{retestCalls++;return pending.promise}});
 const app=createConsoleApp({document:d,storage:ss(),session:s,api}),a={id:'A',title:'A',role:'OWNER'};await app.open(a);
 const upd=find(d.m.get('previews'),x=>x.tagName==='button'&&x.textContent==='刷新并查询新版交付');await upd.onclick();
 const accept=find(d.m.get('previews'),x=>x.tagName==='button'&&x.textContent==='确认本次修改复验');const feedback=find(d.m.get('previews'),x=>x.tagName==='button'&&x.textContent==='本次修改仍需完善');
 const first=accept.onclick();assert.equal(accept.disabled,true);assert.equal(feedback.disabled,true);await feedback.onclick();assert.equal(retestCalls,1);
 pending.resolve({state:'RETEST_ACCEPTED',automatic_charge:false});await first;assert.equal(retestCalls,1);
});
