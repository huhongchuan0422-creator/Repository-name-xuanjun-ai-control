import test from'node:test';
import assert from'node:assert/strict';
import fs from'node:fs';
import crypto from'node:crypto';
import {resolveGeoProject,loadGeoRuntime,geoRuntimeNotice,buildGeoView,applyGeoRuntimeView,installGeoActionGuards} from'../src/geo-v4-runtime.js';

const root=new URL('../geo-v4/',import.meta.url);
const expected={
 'index.html':'39ba7edef950d05c3ab32c626ff2eb19f00007e5a0e231316103a6ae1ea08456',
 'styles.css':'90bb08cecbfc8c6033497dad09b6cb1c70a9d6a1c767910703ebf9868acf899a',
 'ecosystem.css':'d9973bfc62cc3ee4facce90fa08b299c8701e1746059ccfc59358ea9e6cdb79a',
 'app.js':'d6aa15803319ff60b7ec3b073f73eb85a65d2494d89a7cdf68070504700b6822'
};
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(new URL(p,root))).digest('hex');

test('GEO V4 frozen implementation files remain byte exact',()=>{for(const [p,h] of Object.entries(expected))assert.equal(sha(p),h,p)});
test('GEO live entry changes frozen index only by loading separate runtime adapter',()=>{
 const frozen=fs.readFileSync(new URL('index.html',root),'utf8');
 const live=fs.readFileSync(new URL('live.html',root),'utf8');
 assert.equal(live.replace('<style id="geo-runtime-guard">body{visibility:hidden}</style>','').replace('<script type="module" src="../src/geo-v4-runtime.js"></script>',''),frozen);
});
test('GEO project context never guesses among multiple tenants',()=>{
 const me={projects:[{id:'a',tenant:'ta',role:'OWNER'},{id:'b',tenant:'tb',role:'OWNER'}]};
 assert.equal(resolveGeoProject(me,'').status,'PROJECT_SELECTION_REQUIRED');
 assert.equal(resolveGeoProject(me,'?project=b').project.tenant,'tb');
 assert.equal(resolveGeoProject(me,'?project=x').status,'PROJECT_FORBIDDEN');
});
test('GEO runtime reuses SaaS identity and reports not connected instead of demo success',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'OWNER'}]})};
 const r=await loadGeoRuntime({api,service:null,search:''});
 assert.equal(r.mode,'NOT_CONNECTED');assert.equal(r.project.id,'p');assert.equal(r.state.service_ready,false);
 assert.match(geoRuntimeNotice(r),/真实 GEO 服务尚未接通/);
});
test('GEO runtime rejects cross-tenant service snapshots',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'OWNER'}]})};
 const service={snapshot:async()=>({tenant_id:'tenant-b',connection:'CONNECTED',entitlement:{enabled:true}})};
 const r=await loadGeoRuntime({api,service,search:''});assert.equal(r.mode,'INTEGRITY_ERROR');assert.match(r.error.message,/GEO_TENANT_MISMATCH/);
});
test('GEO runtime only becomes connected with matching tenant and enabled entitlement',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'EDITOR'}]})};
 const service={snapshot:async x=>({tenant_id:x.tenant_id,connection:'CONNECTED',entitlement:{enabled:true,plan:'专业版',quota:1000,remaining:760},approval_required:false})};
 const r=await loadGeoRuntime({api,service,search:''});
 assert.equal(r.mode,'CONNECTED');assert.equal(r.state.service_ready,true);assert.equal(r.state.entitlement.remaining,760);
});
test('GEO service errors do not create fake metrics or execution readiness',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'OWNER'}]})};
 const service={snapshot:async()=>{throw Error('down')}};
 const r=await loadGeoRuntime({api,service,search:''});
 assert.equal(r.mode,'SERVICE_ERROR');assert.equal(r.state.service_ready,false);assert.match(geoRuntimeNotice(r),/不会创建任务或写入数据/);
});

class E{
 constructor(text=''){this.textContent=text;this.value='';this.disabled=false;this.style={};this.attrs={};this.children={};this.childNodes=[];this.innerHTML=''}
 querySelector(s){return this.children[s]||null}querySelectorAll(s){return this.children[s+'[]']||[]}replaceChildren(...x){this.childNodes=[...x];this.textContent=''}setAttribute(k,v){this.attrs[k]=v}removeAttribute(k){delete this.attrs[k]}remove(){this.removed=true}
}
function fakeDoc(){
 const d=new E(),body=new E();d.body=body;const map=new Map,arr=new Map;
 d.querySelector=s=>map.get(s)||null;d.querySelectorAll=s=>arr.get(s)||[];d.getElementById=id=>map.get('#'+id)||null;
 d.set=(s,e)=>{map.set(s,e);return e};d.setAll=(s,x)=>{arr.set(s,x);return x};
 const side=d.set('.sideplan',new E()),sp=new E(),sb=new E(),ss=new E(),prog=new E();side.children={'span':sp,'b':sb,'small':ss,'.progress i':prog};
 d.set('#sidebarbrand',new E('青禾知识库'));d.set('.brandmini',new E('青'));d.set('.livebadge',new E('演示数据'));d.set('.demobar span',new E('演示数据 · 操作仅模拟'));
 const su=d.set('.sideuser',new E()),suSpan=new E('林'),suDiv=new E('林悦');su.children={'span':suSpan,'div':suDiv};d.set('.useravatar',new E('林'));
 const meta=d.set('meta[name="description"]',new E());meta.setAttribute=(k,v)=>meta.attrs[k]=v;
 const bn=d.set('#brandname',new E());bn.value='青禾知识库';const bu=d.set('#brandurl',new E());bu.value='qinghe.example';
 const cards=[];for(const label of ['官网被引用比例','品牌被提及比例','实际网站访问','实际客户询盘']){const c=new E(),l=new E(label),strong=new E('32.5%'),ch=new E('+12.5'),base=new E('78 / 240 条有效回答');c.children={'.metriclabel':l,'strong':strong,'.change':ch,'.base':base};cards.push(c)}d.setAll('.metric',cards);
 d.setAll('.chartplot svg',[new E()]);d.setAll('.chartnote',[new E('240 条有效回答')]);d.set('#issuelist',new E('演示诊断'));d.set('.nextaction',new E('演示任务'));
 const next=d.querySelector('.nextaction');next.children={'.actiontitle':new E('补齐官网安全说明'),':scope > p':new E('演示说明')};
 d.set('.reportbanner div',new E('本期效果 · 演示数据'));
 for(const sel of ['.tablewrap','.chartwrap','.scope','.explain','.hero','.planitem','.execstep','.detailhero','.history','.emptyhistory','.sourcebox','.ownerline','.review','.comment','.evidencebox','.quotebox','.comparison','.callnext','.rowline','.reportbanner'])d.setAll(sel,d.querySelectorAll(sel).length?d.querySelectorAll(sel):[new E('演示值')]);
 d.setAll('select',[new E('DeepSeek')]);d.setAll('button',[]);
 const guard=d.set('#geo-runtime-guard',new E());return d;
}
test('GEO fail-closed rendering removes sideplan brand metrics and evidence demo values when not connected',()=>{
 const d=fakeDoc(),r={mode:'NOT_CONNECTED',state:{entitlement:{}},snapshot:null};
 applyGeoRuntimeView(d,r);
 assert.equal(d.querySelector('.sideplan').querySelector('span').textContent,'套餐未接入');
 assert.match(d.querySelector('.sideplan').querySelector('b').textContent,/尚未接通/);
 assert.equal(d.querySelector('#sidebarbrand').textContent,'当前品牌未接入');
 for(const c of d.querySelectorAll('.metric'))assert.equal(c.querySelector('strong').textContent,'—');
 assert.match(d.querySelector('#issuelist').textContent,/未接入/);
 assert.equal(d.querySelectorAll('select')[0].disabled,true);
});
test('GEO connected rendering binds real brand usage metrics diagnosis task and results instead of demo values',()=>{
 const d=fakeDoc(),r={mode:'CONNECTED',project:{id:'p',tenant:'ta'},state:{role:'OWNER',entitlement:{enabled:true,plan:'企业版'}},snapshot:{
  tenant_id:'ta',brand:{status:'READY',name:'星河知识库',website:'xinghe.example'},identity:{status:'READY',display_name:'王宁'},usage:{status:'READY',plan:'企业版',used:12,quota:100},
  metrics:{status:'READY',citation:{value:.31,unit:'percent',numerator:31,denominator:100},mention:{value:.42,unit:'percent',numerator:42,denominator:100},visits:{value:88,numerator:88,denominator:100},inquiries:{value:7,numerator:7,denominator:100}},
  diagnosis:{status:'READY',items:[{title:'真实诊断A',cause:'真实原因',page:'/a',observation:'31/100',category:'内容缺口',level:'高优先'}]},
  task:{status:'READY',title:'真实优化任务',summary:'处理中',state:'RUNNING',steps:[{title:'核对资料',summary:'正在核对',state:'RUNNING'}]},
  results:{status:'READY',summary:'真实结果摘要',scope_label:'2026-11-01 至 11-07'},versions:{status:'READY'},scope:{status:'READY',summary:'中国大陆 · 中文'},actions:{}
 }};
 applyGeoRuntimeView(d,r);
 assert.equal(d.querySelector('#sidebarbrand').textContent,'星河知识库');
 assert.equal(d.querySelector('.sideplan').querySelector('small').textContent,'我的观察用量 12 / 100');
 assert.equal(d.querySelectorAll('.metric')[0].querySelector('strong').textContent,'31.0%');
 assert.match(d.querySelector('#issuelist').innerHTML,/真实诊断A/);
 assert.equal(d.querySelector('.nextaction').querySelector('.actiontitle').textContent,'真实优化任务');
 assert.equal(d.querySelector('.reportbanner div').textContent,'真实结果摘要');
});
test('GEO connected mode with missing real fields masks only missing regions and never promotes demo data',()=>{
 const d=fakeDoc(),r={mode:'CONNECTED',project:{id:'p',tenant:'ta'},state:{role:'OWNER',entitlement:{enabled:true}},snapshot:{tenant_id:'ta',actions:{}}};
 applyGeoRuntimeView(d,r);
 assert.equal(d.querySelector('#sidebarbrand').textContent,'当前品牌未接入');
 for(const c of d.querySelectorAll('.metric'))assert.equal(c.querySelector('strong').textContent,'—');
 assert.match(d.querySelector('#issuelist').textContent,/未接入/);
});
test('GEO loading keeps first-paint guard until identity tenant and service state resolve',()=>{
 const d=fakeDoc();applyGeoRuntimeView(d,{mode:'LOADING',snapshot:null,state:null});assert.notEqual(d.querySelector('#geo-runtime-guard').removed,true);
 applyGeoRuntimeView(d,{mode:'NOT_CONNECTED',snapshot:null,state:{entitlement:{}}});assert.equal(d.querySelector('#geo-runtime-guard').removed,true);
});
test('GEO service exception is fail-closed and never CONNECTED',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'ta',role:'OWNER'}]})},service={snapshot:async()=>{throw Error('network')}};
 const r=await loadGeoRuntime({api,service,search:''});assert.equal(r.mode,'SERVICE_ERROR');assert.equal(r.snapshot,null);assert.equal(r.state.service_ready,false);
});
test('GEO real action requires explicit snapshot permission and does not fall back to demo mutation',async()=>{
 const d=fakeDoc(),toasts=[],w={toast:x=>toasts.push(x)},calls=[];
 let runtime={mode:'CONNECTED',project:{id:'p',tenant:'ta'},state:{role:'OWNER'},snapshot:{actions:{SAVE_BRAND:false}},service:{command:async x=>calls.push(x)}};
 const g=installGeoActionGuards(w,d,()=>runtime,async()=>runtime);await w.saveSetup();assert.equal(calls.length,0);assert.ok(toasts.length);
 runtime={...runtime,snapshot:{actions:{SAVE_BRAND:true}}};d.querySelector('#brandname').value='真实品牌';d.querySelector('#brandurl').value='real.example';await w.saveSetup();
 assert.equal(calls.length,1);assert.deepEqual(calls[0].form,{name:'真实品牌',website:'real.example'});g.cancelLate();
});
test('GEO late command result is ignored after a newer command starts',async()=>{
 const d=fakeDoc(),w={toast:()=>{}},deferred=[];let refreshes=0;
 const service={command:()=>new Promise(r=>deferred.push(r))};const runtime={mode:'CONNECTED',project:{id:'p',tenant:'ta'},state:{role:'OWNER'},snapshot:{actions:{SAVE_BRAND:true,CREATE_NEXT_ROUND:true}},service};
 installGeoActionGuards(w,d,()=>runtime,async()=>{refreshes++;return runtime});
 const a=w.saveSetup(),b=w.createRound();deferred[0]({ok:true});await Promise.resolve();assert.equal(refreshes,0);deferred[1]({ok:true});await b;await a;assert.equal(refreshes,1);
});
