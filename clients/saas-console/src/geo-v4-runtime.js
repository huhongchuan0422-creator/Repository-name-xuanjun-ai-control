import {makeApi} from './api.js';
import {assertTenant,geoCustomerState,geoCanExecute,geoNoGuaranteeText} from './geo.js';

export const GEO_SERVICE_HOOK='__XJ_GEO_CUSTOMER_SERVICE__';
const ACTIONS={saveSetup:'SAVE_BRAND',advance:'ADVANCE_OPTIMIZATION',addComment:'ADD_VERSION_COMMENT',approvalConfirm:'APPROVE_VERSION',createRound:'CREATE_NEXT_ROUND'};
const cleanProjectId=x=>typeof x==='string'&&/^[-\w]{1,128}$/.test(x)?x:null;
const ready=x=>x&&x.status==='READY';
const safe=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=x=>typeof x==='number'&&Number.isFinite(x)?x:null;

export function resolveGeoProject(me,search=''){
 const projects=Array.isArray(me?.projects)?me.projects:[];
 const hint=cleanProjectId(new URLSearchParams(search).get('project'));
 if(hint){const p=projects.find(x=>x?.id===hint);return p?{status:'READY',project:p}:{status:'PROJECT_FORBIDDEN',project:null}}
 if(projects.length===1)return{status:'READY',project:projects[0]};
 if(projects.length===0)return{status:'NO_PROJECT',project:null};
 return{status:'PROJECT_SELECTION_REQUIRED',project:null};
}

function closed(mode,project=null,me=null,error=null,state=null){return{mode,service:null,project,state,snapshot:null,me,error}}

export async function loadGeoRuntime({api=makeApi(),service=globalThis[GEO_SERVICE_HOOK]||null,search=globalThis.location?.search||''}={}){
 let me;try{me=await api.me()}catch(error){return closed('SIGNED_OUT',null,null,error)}
 const selected=resolveGeoProject(me,search);if(selected.status!=='READY')return closed(selected.status,null,me);
 const p=selected.project,tenant=typeof p.tenant==='string'&&p.tenant?p.tenant:null;
 if(!tenant)return closed('TENANT_UNKNOWN',p,me);
 if(!service||typeof service.snapshot!=='function')return{...closed('NOT_CONNECTED',p,me),state:geoCustomerState({tenant_id:tenant,role:p.role,connection:'NOT_CONNECTED',entitlement:{enabled:false}})};
 let snapshot;
 try{snapshot=await service.snapshot({project_id:p.id,tenant_id:tenant,customer_id:p.customer||null})}
 catch(error){const state=geoCustomerState({tenant_id:tenant,role:p.role,connection:'UNKNOWN',entitlement:{enabled:false}});return{mode:'SERVICE_ERROR',service:null,project:p,state,snapshot:null,me,error}}
 try{
  assertTenant(snapshot,tenant);
  const state=geoCustomerState({tenant_id:tenant,role:p.role,connection:snapshot.connection||'UNKNOWN',entitlement:snapshot.entitlement||{},retry_limit:snapshot.retry_limit,timeout_seconds:snapshot.timeout_seconds,approval_required:snapshot.approval_required,approval_state:snapshot.approval_state});
  return{mode:state.service_ready?'CONNECTED':'NOT_READY',service,project:p,state,snapshot,me};
 }catch(error){
  const state=geoCustomerState({tenant_id:tenant,role:p.role,connection:'UNKNOWN',entitlement:{enabled:false}});
  return{mode:'INTEGRITY_ERROR',service:null,project:p,state,snapshot:null,me,error};
 }
}

export function geoRuntimeNotice(r){
 const m=r?.mode;
 return m==='SIGNED_OUT'?'请先登录后查看 GEO 服务':m==='PROJECT_SELECTION_REQUIRED'?'请选择要管理的客户项目':m==='PROJECT_FORBIDDEN'?'当前账号无权访问该项目':m==='NO_PROJECT'?'当前账号没有可用项目':m==='TENANT_UNKNOWN'?'当前项目缺少租户信息，暂不能使用 GEO':m==='INTEGRITY_ERROR'?'真实服务身份或租户校验失败，已停止展示和执行':m==='SERVICE_ERROR'?'真实 GEO 服务暂时不可用，当前不会创建任务或写入数据':m==='NOT_CONNECTED'?'真实 GEO 服务尚未接通；当前不会把演示数据作为真实结果':m==='NOT_READY'?(r.state?.service_label||'GEO 服务当前不可执行'):(r?.state?.service_label||'GEO 服务已接通');
}

export function buildGeoView(r){
 const s=r?.snapshot||{},ent=r?.state?.entitlement||{};
 const brand=ready(s.brand)?{name:s.brand.name||null,website:s.brand.website||null}:null;
 const usage=ready(s.usage)?{plan:s.usage.plan||ent.plan||null,used:Number.isInteger(s.usage.used)?s.usage.used:null,quota:Number.isInteger(s.usage.quota)?s.usage.quota:ent.quota,valid_until:s.usage.valid_until??ent.valid_until}:null;
 const metrics=ready(s.metrics)?s.metrics:null,diagnosis=ready(s.diagnosis)?s.diagnosis:null,task=ready(s.task)?s.task:null,results=ready(s.results)?s.results:null,versions=ready(s.versions)?s.versions:null,scope=ready(s.scope)?s.scope:null,identity=ready(s.identity)?s.identity:null;
 return{verified:r?.mode==='CONNECTED',brand,usage,metrics,diagnosis,task,results,versions,scope,identity,notice:geoRuntimeNotice(r),actions:s.actions&&typeof s.actions==='object'?s.actions:{},noGuarantee:geoNoGuaranteeText()};
}

function setText(el,v){if(el)el.textContent=v}
function metricText(m){const v=num(m?.value);return v===null?'—':(m.unit==='percent'?(v*100).toFixed(1)+'%':String(v))}
function metricBase(m){return Number.isInteger(m?.numerator)&&Number.isInteger(m?.denominator)?m.numerator+' / '+m.denominator+' 条有效回答':'真实样本明细未接入'}
function maskMetrics(doc,msg='数据不足'){for(const c of doc.querySelectorAll('.metric')){setText(c.querySelector('strong'),'—');setText(c.querySelector('.change'),msg);setText(c.querySelector('.base'),'等待真实服务数据')}}
function bindMetrics(doc,metrics){
 const map={'官网被引用比例':metrics?.citation,'品牌被提及比例':metrics?.mention,'实际网站访问':metrics?.visits,'实际客户询盘':metrics?.inquiries,'初始官网引用比例':metrics?.citation_baseline,'初始品牌提及比例':metrics?.mention_baseline};
 for(const c of doc.querySelectorAll('.metric')){const label=c.querySelector('.metriclabel')?.textContent?.trim();const m=map[label];if(!m){setText(c.querySelector('strong'),'—');setText(c.querySelector('.change'),'数据不足');setText(c.querySelector('.base'),'真实字段未接入');continue}setText(c.querySelector('strong'),metricText(m));setText(c.querySelector('.change'),m.change_label||'真实服务数据');setText(c.querySelector('.base'),metricBase(m))}
}
function maskRegions(doc,selectors,msg){for(const sel of selectors)for(const el of doc.querySelectorAll(sel)){el.setAttribute?.('data-geo-masked','true');el.textContent=msg}}
function maskUnboundDemo(doc,v){
 maskRegions(doc,['.tablewrap','.chartwrap'],'真实明细未接入或数据不足');
 if(!v.scope)maskRegions(doc,['.scope'],'真实观察范围未接入');
 if(!v.diagnosis)maskRegions(doc,['#issuelist','.explain'],'真实诊断数据未接入');
 if(!v.task)maskRegions(doc,['.nextaction','.hero','.planitem','.execstep','.detailhero','.history','.emptyhistory','.sourcebox','.ownerline'],'真实优化任务未接入');
 if(!v.versions)maskRegions(doc,['.review','.comment','.evidencebox','.quotebox'],'真实版本与证据未接入');
 if(!v.results)maskRegions(doc,['.reportbanner','.comparison','.callnext','.rowline'],'真实效果数据未接入或数据不足');
 for(const el of doc.querySelectorAll('select'))if(!v.scope)el.disabled=true;
}
function bindDiagnosis(doc,d){
 const list=doc.querySelector('#issuelist');if(!list)return;
 if(!Array.isArray(d?.items)||!d.items.length){list.textContent='真实诊断数据不足';return}
 list.innerHTML=d.items.map((x,i)=>'<article class="issue"><div class="issueicon">'+(i===0?'!':'↗')+'</div><div><h3>'+safe(x.title||'诊断项')+'</h3><div class="description">'+safe(x.cause||'诊断依据未接入')+'</div><div class="issuemeta"><span>相关页面：'+safe(x.page||'未接入')+'</span><span>观察：'+safe(x.observation||'数据不足')+'</span><span>问题类型：'+safe(x.category||'待确认')+'</span></div></div><div class="issueright"><span class="tag">'+safe(x.level||'待确认')+'</span></div></article>').join('');
}
function bindTask(doc,t){
 const next=doc.querySelector('.nextaction');if(next){setText(next.querySelector('.actiontitle'),t?.title||'当前优化任务');const p=next.querySelector(':scope > p');setText(p,t?.summary||'任务状态来自真实服务')}
 for(const el of doc.querySelectorAll('.emptyhistory'))setText(el,t?.status_label||t?.state||'真实任务状态未接入');
 const hero=doc.querySelector('.detailhero h2');if(hero&&t?.title)setText(hero,t.title);
 const steps=Array.isArray(t?.steps)?t.steps:[];const nodes=[...doc.querySelectorAll('.execstep')];
 if(steps.length)nodes.forEach((el,i)=>{const x=steps[i];if(!x){el.textContent='该步骤真实状态未接入';return}setText(el.querySelector('h3'),x.title||('步骤 '+(i+1)));const ps=el.querySelectorAll('p');if(ps[0])setText(ps[0],x.summary||'');if(ps[1])setText(ps[1],x.status_label||x.state||'')});
 else maskRegions(doc,['.execstep'],'真实任务步骤未接入');
}
function bindResults(doc,r){
 const banner=doc.querySelector('.reportbanner div');if(banner)setText(banner,r?.summary||'真实效果数据已接入；仅展示服务返回的可比结果。');
 for(const el of doc.querySelectorAll('.chartnote'))setText(el,r?.scope_label||'真实结果范围来自服务端');
}

export function applyGeoRuntimeView(document,runtime){
 const v=buildGeoView(runtime),connected=v.verified;
 setText(document.querySelector('.livebadge'),connected?'真实服务':'真实服务未核实');
 const bar=document.querySelector('.demobar span');setText(bar,connected?'真实服务 · 仅展示已核实数据':v.notice);if(bar)bar.title=v.noGuarantee;
 const side=document.querySelector('.sideplan');
 if(side){
  setText(side.querySelector('span'),v.usage?.plan||'套餐未接入');
  setText(side.querySelector('b'),connected?'GEO 服务已核实':v.notice);
  setText(side.querySelector('small'),v.usage&&v.usage.used!==null&&v.usage.quota!==null?'我的观察用量 '+v.usage.used+' / '+v.usage.quota:'观察用量未接入');
  const progress=side.querySelector('.progress i');if(progress)progress.style.width=v.usage&&v.usage.used!==null&&v.usage.quota>0?Math.min(100,Math.max(0,v.usage.used/v.usage.quota*100)).toFixed(1)+'%':'0%';
 }
 setText(document.querySelector('#sidebarbrand'),v.brand?.name||'当前品牌未接入');
 const mini=document.querySelector('.brandmini');if(mini)setText(mini,v.brand?.name?.slice(0,1)||'—');
 const sideUser=document.querySelector('.sideuser');if(sideUser){setText(sideUser.querySelector('span'),v.identity?.display_name?.slice(0,1)||'—');const d=sideUser.querySelector('div');if(d){d.childNodes?.length?d.childNodes[0].textContent=(v.identity?.display_name||'当前账号'):setText(d,v.identity?.display_name||'当前账号')}}
 const avatar=document.querySelector('.useravatar');if(avatar)setText(avatar,v.identity?.display_name?.slice(0,1)||'—');
 const meta=document.querySelector('meta[name="description"]');if(meta)meta.setAttribute('content','玄钧AI新 GEO 品牌增长工作台');
 const bn=document.querySelector('#brandname');if(bn)bn.value=v.brand?.name||'';
 const bu=document.querySelector('#brandurl');if(bu)bu.value=v.brand?.website||'';
 if(v.metrics)bindMetrics(document,v.metrics);else maskMetrics(document);
 for(const svg of document.querySelectorAll('.chartplot svg'))if(!v.results)svg.replaceChildren();
 if(v.diagnosis)bindDiagnosis(document,v.diagnosis);else{const l=document.querySelector('#issuelist');if(l)l.textContent='真实诊断数据未接入'}
 if(v.task)bindTask(document,v.task);else{const n=document.querySelector('.nextaction');if(n)n.textContent='真实优化任务未接入'}
 if(v.results)bindResults(document,v.results);else{const b=document.querySelector('.reportbanner div');if(b)b.textContent='真实效果数据未接入';for(const x of document.querySelectorAll('.chartnote'))x.textContent='数据不足；不会使用 V4 演示数字作为真实效果'}
 maskUnboundDemo(document,v);
 document.body?.removeAttribute('data-geo-loading');
 if(runtime?.mode!=='LOADING')document.getElementById?.('geo-runtime-guard')?.remove?.();
 return v;
}

function canAction(runtime,type){if(runtime?.mode!=='CONNECTED'||typeof runtime.service?.command!=='function')return false;const v=buildGeoView(runtime);if(v.actions[type]!==true)return false;return ['OWNER','EDITOR'].includes(runtime.state?.role)}
export function installGeoActionGuards(window,document,getRuntime,refresh){
 let epoch=0;
 const blocked=()=>window.toast?.(geoRuntimeNotice(getRuntime())+'；该操作真实接口未接通或当前无执行权限');
 const run=type=>async(...args)=>{const r=getRuntime();if(!canAction(r,type))return blocked();const mine=++epoch;const payload={type,project_id:r.project.id,tenant_id:r.project.tenant,args};if(type==='SAVE_BRAND')payload.form={name:document.querySelector('#brandname')?.value||'',website:document.querySelector('#brandurl')?.value||''};if(type==='ADD_VERSION_COMMENT')payload.comment=document.querySelector('#commentinput')?.value||'';try{await r.service.command(payload);if(mine!==epoch)return;await refresh()}catch(e){if(mine!==epoch)return;if(e?.uncertain){window.toast?.('结果未知，正在查询当前状态；不会自动重试');await refresh()}else{window.toast?.(e?.message||'操作失败')}}};
 for(const [name,type] of Object.entries(ACTIONS))window[name]=run(type);
 window.issueDetail=i=>{const r=getRuntime(),x=buildGeoView(r).diagnosis?.items?.[i];if(!x||typeof window.drawer!=='function')return blocked();window.drawer('<div class="eyebrow">诊断详情</div><h1>'+safe(x.title||'诊断项')+'</h1><div class="evidencebox"><h3>为什么值得处理</h3><p>'+safe(x.cause||'诊断依据未接入')+'</p><p>'+safe(x.evidence||'证据数据未接入')+'</p></div><h3>用户会怎样问</h3><div class="quotebox">'+safe(x.question||'问题样本未接入')+'</div><h3>对应页面</h3><div class="evidencebox">'+safe(x.page||'页面未接入')+'</div>');};
 window.sampleScope=()=>{const x=buildGeoView(getRuntime()).scope;if(!x||typeof window.drawer!=='function')return blocked();window.drawer('<div class="eyebrow">数据范围与口径</div><h1>同范围，才比较。</h1><div class="evidencebox">'+safe(x.summary||'范围说明未接入')+'</div>')};
 const hydrateButtons=()=>{for(const b of document.querySelectorAll('button')){const t=b.textContent?.trim()||'';const type=t.includes('接受计划')?'ADVANCE_OPTIMIZATION':t==='刷新诊断'?'REFRESH_DIAGNOSIS':null;if(type)b.onclick=canAction(getRuntime(),type)?run(type):blocked}};
 hydrateButtons();return{blocked,run,hydrateButtons,cancelLate:()=>{epoch++}};
}

export async function installGeoV4Runtime({window=globalThis.window,document=globalThis.document,api=makeApi(),service=globalThis[GEO_SERVICE_HOOK]||null}={}){
 let current=closed('LOADING');applyGeoRuntimeView(document,current);
 const refresh=async()=>{const next=await loadGeoRuntime({api,service,search:window?.location?.search||''});current=next;applyGeoRuntimeView(document,current);guards?.hydrateButtons();return current};
 let guards;
 guards=installGeoActionGuards(window,document,()=>current,refresh);
 try{await refresh()}catch(error){current=closed('INTEGRITY_ERROR',null,null,error);applyGeoRuntimeView(document,current)}
 const original=typeof window.render==='function'?window.render.bind(window):null;
 if(original)window.render=()=>{original();applyGeoRuntimeView(document,current);guards.hydrateButtons()};
 if(typeof MutationObserver!=='undefined'&&document.body){let busy=false;const o=new MutationObserver(()=>{if(busy)return;busy=true;queueMicrotask(()=>{try{applyGeoRuntimeView(document,current);guards.hydrateButtons()}finally{busy=false}})});o.observe(document.body,{subtree:true,childList:true})}
 return current;
}

if(typeof window!=='undefined'&&typeof document!=='undefined')installGeoV4Runtime().catch(error=>{try{applyGeoRuntimeView(document,closed('INTEGRITY_ERROR',null,null,error))}catch{}});
