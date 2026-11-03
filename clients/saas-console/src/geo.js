export const GEO_SECTIONS=Object.freeze(['overview','brand','diagnosis','optimization','versions','results']);
export const GEO_RESULT_STATES=Object.freeze(['IMPROVED','UNCHANGED','DECLINED','INSUFFICIENT_DATA']);
export const GEO_TASK_STATES=Object.freeze(['QUEUED','RUNNING','WAITING_REVIEW','WAITING_EXTERNAL','PAUSED_BUDGET','SUCCEEDED','FAILED','CANCELLED','UNKNOWN']);
const finite=n=>typeof n==='number'&&Number.isFinite(n);
const nonneg=n=>Number.isInteger(n)&&n>=0;

export function assertTenant(record,tenantId){
 if(!record||typeof record!=='object'||typeof tenantId!=='string'||!tenantId)throw Error('GEO_TENANT_REQUIRED');
 if(record.tenant_id!==tenantId)throw Error('GEO_TENANT_MISMATCH');
 return record;
}
export function geoConnectionState(value){
 const allowed=['CONNECTED','DEGRADED','NOT_CONNECTED','UNKNOWN'];
 if(!allowed.includes(value))throw Error('GEO_CONNECTION_STATE');
 return value;
}
export function geoMetric({numerator=null,denominator=null,value=null,source=null,status='UNKNOWN'}={}){
 if(status!=='READY'||!finite(value)||!nonneg(denominator)||denominator===0||!source){
  return{state:'INSUFFICIENT_DATA',value:null,label:'数据不足',source:source||null,numerator:null,denominator:null};
 }
 if(!nonneg(numerator)||numerator>denominator)throw Error('GEO_METRIC_BOUNDS');
 return{state:'READY',value,label:String(value),source,numerator,denominator};
}
export function geoEffect({before=null,after=null,comparable=false}={}){
 if(!comparable||!finite(before)||!finite(after))return{state:'INSUFFICIENT_DATA',delta:null,label:'数据不足'};
 const delta=after-before;
 return{state:delta>0?'IMPROVED':delta<0?'DECLINED':'UNCHANGED',delta,label:delta>0?'提升':delta<0?'下降':'持平'};
}
export function geoRetryDecision(task={}){
 if(task.state==='UNKNOWN')return{action:'QUERY',reason:'结果未知，先查询当前状态'};
 if(task.state==='FAILED'&&task.retryable===true)return{action:'RETRY',reason:'失败且服务端明确允许重试'};
 if(task.state==='FAILED')return{action:'STOP',reason:'失败但未获准重试'};
 if(GEO_TASK_STATES.includes(task.state))return{action:'WAIT',reason:'当前状态不执行重试'};
 throw Error('GEO_TASK_STATE');
}
export function geoEntitlement(input={}){
 const enabled=input.enabled===true;
 const validUntil=Number.isInteger(input.valid_until)?input.valid_until:null;
 const quota=Number.isInteger(input.quota)&&input.quota>=0?input.quota:null;
 const remaining=Number.isInteger(input.remaining)&&input.remaining>=0?input.remaining:null;
 return{enabled,valid_until:validUntil,quota,remaining,plan:typeof input.plan==='string'&&input.plan?input.plan:null,
  status:enabled?'ENABLED':'NOT_ENABLED',quota_status:quota===null||remaining===null?'UNKNOWN':'KNOWN'};
}
export function geoCustomerState(input={}){
 const tenantId=input.tenant_id;
 if(typeof tenantId!=='string'||!tenantId)throw Error('GEO_TENANT_REQUIRED');
 const connection=geoConnectionState(input.connection||'UNKNOWN');
 const entitlement=geoEntitlement(input.entitlement||{});
 const role=input.role;
 if(!['OWNER','EDITOR','VIEWER'].includes(role))throw Error('GEO_ROLE');
 return{
  tenant_id:tenantId,role,sections:[...GEO_SECTIONS],connection,entitlement,
  service_ready:connection==='CONNECTED'&&entitlement.enabled,
  service_label:connection==='CONNECTED'?(entitlement.enabled?'已接通':'未开通模块'):'未接通真实服务',
  limits:{retry_limit:Number.isInteger(input.retry_limit)&&input.retry_limit>=0?input.retry_limit:null,
          timeout_seconds:Number.isInteger(input.timeout_seconds)&&input.timeout_seconds>0?input.timeout_seconds:null},
  approval:{required:input.approval_required===true,state:typeof input.approval_state==='string'?input.approval_state:'UNKNOWN'}
 };
}
export function geoCanExecute(state){
 if(!state||state.service_ready!==true)return{allowed:false,reason:state?.service_label||'未接通真实服务'};
 if(!['OWNER','EDITOR'].includes(state.role))return{allowed:false,reason:'当前角色仅可查看'};
 if(state.approval.required&&state.approval.state!=='APPROVED')return{allowed:false,reason:'等待确认'};
 return{allowed:true,reason:'可执行'};
}
export function geoNoGuaranteeText(){
 return'结果可能提升、持平、下降或数据不足；不承诺固定排名、推荐或增长。';
}
