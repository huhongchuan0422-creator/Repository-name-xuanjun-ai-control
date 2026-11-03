import {makeApi} from './api.js';
import {assertTenant,geoCustomerState,geoCanExecute,geoNoGuaranteeText} from './geo.js';

export const GEO_SERVICE_HOOK='__XJ_GEO_CUSTOMER_SERVICE__';

const cleanProjectId=x=>typeof x==='string'&&/^[-\w]{1,128}$/.test(x)?x:null;
const text=x=>typeof x==='string'?x:'';

export function resolveGeoProject(me,search=''){
 const projects=Array.isArray(me?.projects)?me.projects:[];
 const hint=cleanProjectId(new URLSearchParams(search).get('project'));
 if(hint){
  const p=projects.find(x=>x?.id===hint);
  if(!p) return{status:'PROJECT_FORBIDDEN',project:null};
  return{status:'READY',project:p};
 }
 if(projects.length===1)return{status:'READY',project:projects[0]};
 if(projects.length===0)return{status:'NO_PROJECT',project:null};
 return{status:'PROJECT_SELECTION_REQUIRED',project:null};
}

export async function loadGeoRuntime({api=makeApi(),service=globalThis[GEO_SERVICE_HOOK]||null,search=globalThis.location?.search||''}={}){
 let me;
 try{me=await api.me()}catch(e){return{mode:'SIGNED_OUT',error:e,service:null,project:null,state:null,snapshot:null}}
 const selected=resolveGeoProject(me,search);
 if(selected.status!=='READY')return{mode:selected.status,service:null,project:null,state:null,snapshot:null,me};
 const p=selected.project;
 const tenant=typeof p.tenant==='string'&&p.tenant?p.tenant:null;
 if(!tenant)return{mode:'TENANT_UNKNOWN',service:null,project:p,state:null,snapshot:null,me};
 if(!service||typeof service.snapshot!=='function'){
  const state=geoCustomerState({tenant_id:tenant,role:p.role,connection:'NOT_CONNECTED',entitlement:{enabled:false}});
  return{mode:'NOT_CONNECTED',service:null,project:p,state,snapshot:null,me};
 }
 let snapshot;
 try{snapshot=await service.snapshot({project_id:p.id,tenant_id:tenant,customer_id:p.customer||null})}
 catch(error){
  const state=geoCustomerState({tenant_id:tenant,role:p.role,connection:'UNKNOWN',entitlement:{enabled:false}});
  return{mode:'SERVICE_ERROR',service,project:p,state,snapshot:null,me,error};
 }
 assertTenant(snapshot,tenant);
 const state=geoCustomerState({
  tenant_id:tenant,role:p.role,
  connection:snapshot.connection||'UNKNOWN',
  entitlement:snapshot.entitlement||{},
  retry_limit:snapshot.retry_limit,
  timeout_seconds:snapshot.timeout_seconds,
  approval_required:snapshot.approval_required,
  approval_state:snapshot.approval_state
 });
 return{mode:state.service_ready?'CONNECTED':'NOT_READY',service,project:p,state,snapshot,me};
}

export function geoRuntimeNotice(runtime){
 if(!runtime)return'真实 GEO 服务状态未知';
 if(runtime.mode==='SIGNED_OUT')return'请先登录后查看 GEO 服务';
 if(runtime.mode==='PROJECT_SELECTION_REQUIRED')return'请选择要管理的客户项目';
 if(runtime.mode==='PROJECT_FORBIDDEN')return'当前账号无权访问该项目';
 if(runtime.mode==='NO_PROJECT')return'当前账号没有可用项目';
 if(runtime.mode==='TENANT_UNKNOWN')return'当前项目缺少租户信息，暂不能使用 GEO';
 if(runtime.mode==='SERVICE_ERROR')return'真实 GEO 服务暂时不可用，当前不会创建任务或写入数据';
 if(runtime.mode==='NOT_CONNECTED')return'真实 GEO 服务尚未接通；当前页面仅保留 V4 定稿结构，不把演示数据作为真实结果';
 if(runtime.mode==='NOT_READY')return runtime.state?.service_label||'GEO 服务当前不可执行';
 return runtime.state?.service_label||'GEO 服务已接通';
}

export function maskGeoDemo(document,runtime){
 const live=document.querySelector('.livebadge');
 if(live)live.textContent=runtime?.mode==='CONNECTED'?'真实服务':'真实服务未接通';
 const bar=document.querySelector('.demobar span');
 if(bar)bar.textContent=runtime?.mode==='CONNECTED'?'真实服务数据 · 结果以当前租户状态为准':'真实服务未接通 · V4 冻结演示值不计入真实效果';
 if(runtime?.mode==='CONNECTED')return;
 for(const el of document.querySelectorAll('.metric strong'))el.textContent='—';
 for(const el of document.querySelectorAll('.metric .change'))el.textContent='数据不足';
 for(const el of document.querySelectorAll('.metric .base'))el.textContent='等待真实服务数据';
 for(const el of document.querySelectorAll('.chartnote'))el.textContent='等待真实服务返回可比样本；不会使用演示数字作为真实效果。';
 for(const svg of document.querySelectorAll('.chartplot svg'))svg.replaceChildren();
 const next=document.querySelector('.nextaction');
 if(next){
  const title=next.querySelector('.actiontitle');if(title)title.textContent='等待真实诊断结果';
  const p=next.querySelector(':scope > p');if(p)p.textContent='真实诊断服务未接通，不会生成或执行优化建议。';
 }
}

export function blockGeoDemoMutations(window,document,runtime){
 if(runtime?.mode==='CONNECTED')return;
 const blocked=()=>window.toast?.(geoRuntimeNotice(runtime));
 for(const name of ['saveSetup','advance','addComment','approvalConfirm','createRound'])window[name]=blocked;
 for(const b of document.querySelectorAll('button')){
  if(['刷新诊断','补充安全说明资料','查看并确认建议','查看更新进度','建立下一轮计划'].includes(text(b.textContent).trim()))b.onclick=blocked;
 }
}

export async function installGeoV4Runtime({window=globalThis.window,document=globalThis.document,api=makeApi(),service=globalThis[GEO_SERVICE_HOOK]||null}={}){
 const runtime=await loadGeoRuntime({api,service,search:window?.location?.search||''});
 if(!window||!document)return runtime;
 const original=typeof window.render==='function'?window.render.bind(window):null;
 const hydrate=()=>{maskGeoDemo(document,runtime);blockGeoDemoMutations(window,document,runtime);const status=document.querySelector('.demobar span');if(status)status.title=geoNoGuaranteeText();};
 if(original){window.render=()=>{original();hydrate()};window.render()}else hydrate();
 return runtime;
}

if(typeof window!=='undefined'&&typeof document!=='undefined')installGeoV4Runtime().catch(()=>{});
