// Backend transport for the existing __XJ_GEO_CUSTOMER_SERVICE__ hook.
// No origin override, credentials, new account store or automatic retry.
import {BASE,ApiFailure} from './api.js';
export function makeGeoHttpService({fetcher=globalThis.fetch,csrf=()=>sessionStorage.getItem('xj_csrf')||'',requestId=()=>crypto.randomUUID()}={}){
 const pending=new Map();
 const scope=x=>JSON.stringify([x.tenant_id,x.project_id]);
 async function request(op,body,write){
  let r,d;
  try{r=await fetcher(BASE+'geo/'+op,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify(body)})}
  catch{throw new ApiFailure('GEO_TRANSPORT_RESULT_UNKNOWN',0,write)}
  try{d=await r.json()}catch{throw new ApiFailure('GEO_INVALID_SERVER_RESPONSE',r.status,write)}
  if(!r.ok)throw new ApiFailure(d.error||'GEO_REQUEST_REJECTED',r.status,write&&(r.status===408||r.status>=500));
  return d;
 }
 return {
  async snapshot(body){
   const result=await request('snapshot',body,false);
   if(result.tenant_id!==body.tenant_id||result.project_id!==body.project_id||result.customer_id!==body.customer_id)throw new ApiFailure('GEO_SNAPSHOT_SUBJECT_MISMATCH');
   const key=scope(body),id=pending.get(key);
   if(id && result.last_command?.request_id===id && result.last_command?.state==='SUCCEEDED')pending.delete(key);
   return result;
  },
  async command(body){
   const key=scope(body);
   if(pending.has(key))throw new ApiFailure('GEO_COMMAND_QUERY_REQUIRED',0,true);
   const id=requestId();pending.set(key,id);
   try{
    const result=await request('command',{...body,idempotency_key:id},true);
    if(result.state==='UNKNOWN'||result.query_required)throw new ApiFailure('GEO_COMMAND_QUERY_REQUIRED',202,true);
    if(result.state!=='SUCCEEDED'||result.idempotency_key!==id)throw new ApiFailure('GEO_COMMAND_RECEIPT_MISMATCH',0,true);
    pending.delete(key);return result;
   }catch(error){if(error.uncertain!==true)pending.delete(key);throw error}
  }
 };
}
